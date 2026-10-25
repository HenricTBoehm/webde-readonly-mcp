from __future__ import annotations

import base64
import imaplib
import re
import ssl
import unicodedata
from collections.abc import Iterable
from contextlib import AbstractContextManager
from datetime import date

from .config import AccountConfig
from .mime import BodyPart, decode_text, decode_transfer, parse_bodystructure, parse_header_summary
from .models import AttachmentData, MessageDetail, MessageSummary, Thread

HEADER_FIELDS = "DATE FROM TO CC SUBJECT MESSAGE-ID IN-REPLY-TO REFERENCES"
FETCH_SUMMARY = (
    f"(UID RFC822.SIZE FLAGS BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS ({HEADER_FIELDS})])"
)


class ImapError(RuntimeError):
    """A safe, user-facing IMAP failure."""


def _quoted_utf8(value: str, *, max_bytes: int = 8_192) -> bytes:
    if any(unicodedata.category(character) in {"Cc", "Cs"} for character in value):
        raise ValueError("Control characters are forbidden in IMAP search values")
    encoded = value.encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError(f"IMAP search value exceeds the {max_bytes}-byte limit")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'.encode()


def _modified_utf7_mailbox(value: str) -> str:
    """Encode an IMAP mailbox name using modified UTF-7 (RFC 3501)."""
    if not value:
        raise ValueError("mailbox must not be empty")
    if "\r" in value or "\n" in value or "\x00" in value:
        raise ValueError("mailbox contains forbidden control characters")
    result: list[str] = []
    non_ascii: list[str] = []

    def flush() -> None:
        if not non_ascii:
            return
        encoded = base64.b64encode("".join(non_ascii).encode("utf-16-be")).decode("ascii")
        result.append("&" + encoded.rstrip("=").replace("/", ",") + "-")
        non_ascii.clear()

    for character in value:
        codepoint = ord(character)
        if 0x20 <= codepoint <= 0x7E:
            flush()
            result.append("&-" if character == "&" else character)
        else:
            non_ascii.append(character)
    flush()
    return "".join(result)


def _quoted_mailbox(value: str) -> str:
    encoded = _modified_utf7_mailbox(value)
    return '"' + encoded.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _first_literal(data) -> bytes:
    for item in data or []:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
            return item[1]
    raise ImapError("The IMAP server did not return the requested message data.")


def _response_prefix(data) -> bytes:
    chunks: list[bytes] = []
    for item in data or []:
        if isinstance(item, tuple) and item and isinstance(item[0], bytes):
            chunks.append(item[0])
        elif isinstance(item, bytes):
            chunks.append(item)
    return b" ".join(chunks)


def _balanced_parenthesized(value: bytes, start: int) -> bytes:
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(value)):
        char = value[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == ord("\\"):
                escaped = True
            elif char == ord('"'):
                quoted = False
            continue
        if char == ord('"'):
            quoted = True
        elif char == ord("("):
            depth += 1
        elif char == ord(")"):
            depth -= 1
            if depth == 0:
                return value[start : index + 1]
    raise ImapError("The server returned an invalid BODYSTRUCTURE response.")


def _bodystructure_from_response(data) -> BodyPart:
    prefix = _response_prefix(data)
    match = re.search(rb"\bBODYSTRUCTURE\s+", prefix, flags=re.IGNORECASE)
    if not match:
        raise ImapError("The server response did not contain BODYSTRUCTURE.")
    start = prefix.find(b"(", match.end())
    if start < 0:
        raise ImapError("The server returned an invalid BODYSTRUCTURE response.")
    return parse_bodystructure(_balanced_parenthesized(prefix, start))


def _number_field(data, field: bytes) -> int | None:
    match = re.search(rb"\b" + field + rb"\s+(\d+)", _response_prefix(data), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _flags(data) -> list[str]:
    match = re.search(rb"\bFLAGS\s+\(([^)]*)\)", _response_prefix(data), flags=re.IGNORECASE)
    if not match:
        return []
    return [flag.decode("ascii", errors="replace") for flag in match.group(1).split()]


class ReadOnlyImapClient(AbstractContextManager["ReadOnlyImapClient"]):
    """A deliberately constrained IMAP client with no mutation methods."""

    def __init__(self, config: AccountConfig, *, connection_factory=None):
        self.config = config
        self._connection_factory = connection_factory or imaplib.IMAP4_SSL
        self._imap = None
        self._mailbox: str | None = None

    def __enter__(self) -> ReadOnlyImapClient:
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            self._imap = self._connection_factory(
                self.config.host,
                self.config.port,
                ssl_context=context,
                timeout=self.config.timeout,
            )
            status, _ = self._imap.login(self.config.username, self.config.password)
            if status != "OK":
                raise ImapError("WEB.DE rejected the login.")
        except (imaplib.IMAP4.error, OSError, ssl.SSLError) as exc:
            self._imap = None
            raise ImapError(f"Could not connect to WEB.DE IMAP: {exc}") from exc
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._imap is not None:
            try:
                self._imap.logout()
            except (imaplib.IMAP4.error, OSError):
                pass
        self._imap = None
        self._mailbox = None

    @property
    def imap(self):
        if self._imap is None:
            raise ImapError("The IMAP client is not connected.")
        return self._imap

    def examine(self, mailbox: str = "INBOX") -> None:
        """Open a mailbox read-only. imaplib sends EXAMINE for readonly=True."""
        if self._mailbox == mailbox:
            return
        status, _ = self.imap.select(_quoted_mailbox(mailbox), readonly=True)
        if status != "OK":
            raise ImapError(f"Could not examine mailbox {mailbox!r} read-only.")
        self._mailbox = mailbox

    def _uid(self, command: str, *args):
        if command.upper() not in {"SEARCH", "FETCH"}:
            raise ImapError(f"IMAP command {command!r} is not allowed by the read-only client.")
        status, data = self.imap.uid(command, *args)
        if status != "OK":
            raise ImapError(f"IMAP {command.upper()} failed.")
        return data

    def _search_tokens(self, tokens: Iterable[str | bytes], *, mailbox: str) -> list[str]:
        self.examine(mailbox)
        data = self._uid("SEARCH", "CHARSET", "UTF-8", *tokens)
        if not data or not isinstance(data[0], bytes):
            return []
        return [item.decode("ascii") for item in data[0].split() if item.isdigit()]

    def search(
        self,
        *,
        mailbox: str = "INBOX",
        since: date | None = None,
        before: date | None = None,
        sender: str | None = None,
        subject: str | None = None,
        limit: int = 50,
    ) -> list[MessageSummary]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        tokens: list[str | bytes] = []
        if since:
            tokens.extend(["SINCE", since.strftime("%d-%b-%Y")])
        if before:
            tokens.extend(["BEFORE", before.strftime("%d-%b-%Y")])
        if sender:
            tokens.extend(["FROM", _quoted_utf8(sender)])
        if subject:
            tokens.extend(["SUBJECT", _quoted_utf8(subject)])
        if not tokens:
            tokens.append("ALL")
        uids = self._search_tokens(tokens, mailbox=mailbox)
        # Most recent UIDs first; UID ordering is monotonically increasing per mailbox.
        return [self.get_summary(uid, mailbox=mailbox) for uid in reversed(uids[-limit:])]

    def get_summary(self, uid: str, *, mailbox: str = "INBOX") -> MessageSummary:
        self._validate_uid(uid)
        self.examine(mailbox)
        data = self._uid("FETCH", uid, FETCH_SUMMARY)
        structure = _bodystructure_from_response(data)
        attachments = [part.to_attachment() for part in structure.walk() if part.is_attachment]
        return parse_header_summary(
            _first_literal(data),
            uid=uid,
            mailbox=mailbox,
            size=_number_field(data, b"RFC822.SIZE"),
            flags=_flags(data),
            attachments=attachments,
        )

    def get_message(
        self,
        uid: str,
        *,
        mailbox: str = "INBOX",
        max_body_bytes: int = 2_000_000,
    ) -> MessageDetail:
        if max_body_bytes < 1 or max_body_bytes > 20_000_000:
            raise ValueError("max_body_bytes must be between 1 and 20,000,000")
        self._validate_uid(uid)
        self.examine(mailbox)
        summary_data = self._uid("FETCH", uid, FETCH_SUMMARY)
        structure = _bodystructure_from_response(summary_data)
        attachments = [part.to_attachment() for part in structure.walk() if part.is_attachment]
        summary = parse_header_summary(
            _first_literal(summary_data),
            uid=uid,
            mailbox=mailbox,
            size=_number_field(summary_data, b"RFC822.SIZE"),
            flags=_flags(summary_data),
            attachments=attachments,
        )
        text: str | None = None
        html: str | None = None
        truncated = False
        remaining = max_body_bytes
        for part in structure.walk():
            if part.is_attachment or part.content_type not in {"text/plain", "text/html"}:
                continue
            if remaining <= 0:
                truncated = True
                break
            request_size = min(remaining, max(part.size, 1))
            payload = self._fetch_part(uid, part.section, partial=request_size)
            if part.size > request_size:
                truncated = True
            remaining -= len(payload)
            decoded = decode_text(
                payload,
                encoding=part.encoding,
                charset=part.params.get("charset"),
            )
            if part.content_type == "text/plain" and text is None:
                text = decoded
            elif part.content_type == "text/html" and html is None:
                html = decoded
        return MessageDetail(summary=summary, text=text, html=html, truncated=truncated)

    def get_attachment(
        self,
        uid: str,
        part_number: str,
        *,
        mailbox: str = "INBOX",
        max_bytes: int = 25_000_000,
        max_encoded_bytes: int = 40_000_000,
    ) -> AttachmentData:
        if max_bytes < 1 or max_bytes > 100_000_000:
            raise ValueError("max_bytes must be between 1 and 100,000,000")
        if max_encoded_bytes < 1 or max_encoded_bytes > 150_000_000:
            raise ValueError("max_encoded_bytes must be between 1 and 150,000,000")
        self._validate_uid(uid)
        if not re.fullmatch(r"\d+(?:\.\d+)*", part_number):
            raise ValueError("part_number must look like '2' or '1.2'")
        self.examine(mailbox)
        summary_data = self._uid("FETCH", uid, FETCH_SUMMARY)
        structure = _bodystructure_from_response(summary_data)
        part = next((item for item in structure.walk() if item.section == part_number), None)
        if part is None or not part.is_attachment:
            raise ImapError(f"Part {part_number!r} is not an attachment in message UID {uid}.")
        if part.size <= 0:
            raise ImapError("Attachment has no trustworthy encoded size; refusing to fetch it.")
        if part.size > max_encoded_bytes:
            raise ImapError(
                f"Encoded attachment is {part.size} bytes, above the configured "
                f"{max_encoded_bytes}-byte encoded-data limit."
            )
        payload = self._fetch_part(uid, part.section)
        if len(payload) != part.size:
            raise ImapError(
                "Attachment transfer was incomplete: "
                f"expected {part.size} encoded bytes, received {len(payload)}."
            )
        try:
            content = decode_transfer(payload, part.encoding, strict=True)
        except ValueError as exc:
            raise ImapError(f"Attachment transfer encoding is invalid: {exc}") from exc
        if len(content) > max_bytes:
            raise ImapError("Decoded attachment exceeds the configured size limit.")
        return AttachmentData(info=part.to_attachment(), content=content)

    def get_thread(
        self,
        uid: str,
        *,
        mailbox: str = "INBOX",
        max_messages: int = 100,
        max_searches: int = 300,
        max_reference_ids: int = 500,
    ) -> Thread:
        if max_messages < 1 or max_messages > 500:
            raise ValueError("max_messages must be between 1 and 500")
        if max_searches < 1 or max_searches > 1_500:
            raise ValueError("max_searches must be between 1 and 1,500")
        if max_reference_ids < 1 or max_reference_ids > 2_000:
            raise ValueError("max_reference_ids must be between 1 and 2,000")
        seed = self.get_summary(uid, mailbox=mailbox)
        found: dict[str, MessageSummary] = {seed.uid: seed}
        pending_ids = set(seed.references)
        if seed.message_id:
            pending_ids.add(seed.message_id)
        if seed.in_reply_to:
            pending_ids.add(seed.in_reply_to)
        if len(pending_ids) > max_reference_ids:
            raise ImapError("Thread contains more reference IDs than the configured limit.")
        searched_ids: set[str] = set()
        search_count = 0
        while pending_ids and len(found) < max_messages:
            message_id = pending_ids.pop()
            if message_id in searched_ids:
                continue
            searched_ids.add(message_id)
            candidate_uids: set[str] = set()
            for field in ("MESSAGE-ID", "IN-REPLY-TO", "REFERENCES"):
                if search_count >= max_searches:
                    raise ImapError(
                        f"Thread search exceeded the configured limit of {max_searches} IMAP searches."
                    )
                search_count += 1
                candidate_uids.update(
                    self._search_tokens(
                        ["HEADER", field, _quoted_utf8(message_id)],
                        mailbox=mailbox,
                    )
                )
            for candidate_uid in sorted(candidate_uids, key=int):
                if candidate_uid in found or len(found) >= max_messages:
                    continue
                message = self.get_summary(candidate_uid, mailbox=mailbox)
                found[candidate_uid] = message
                pending_ids.update(message.references)
                if message.message_id:
                    pending_ids.add(message.message_id)
                if message.in_reply_to:
                    pending_ids.add(message.in_reply_to)
                if len(pending_ids | searched_ids) > max_reference_ids:
                    raise ImapError("Thread contains more reference IDs than the configured limit.")
        messages = sorted(
            found.values(),
            key=lambda item: (item.date is None, item.date.isoformat() if item.date else "", int(item.uid)),
        )
        root = next((item.references[0] for item in messages if item.references), None)
        root = root or (messages[0].message_id if messages else None)
        return Thread(root_message_id=root, messages=messages)

    def _fetch_part(self, uid: str, section: str, *, partial: int | None = None) -> bytes:
        self._validate_uid(uid)
        if not re.fullmatch(r"\d+(?:\.\d+)*", section):
            raise ValueError("Invalid MIME section")
        item = f"BODY.PEEK[{section}]"
        if partial is not None:
            item += f"<0.{partial}>"
        return _first_literal(self._uid("FETCH", uid, f"({item})"))

    @staticmethod
    def _validate_uid(uid: str) -> None:
        if not re.fullmatch(r"[1-9]\d*", str(uid)):
            raise ValueError("UID must be a positive decimal number")

