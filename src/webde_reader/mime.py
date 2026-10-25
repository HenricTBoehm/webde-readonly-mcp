from __future__ import annotations

import base64
import binascii
import quopri
import re
from dataclasses import dataclass, field
from datetime import datetime
from email.header import decode_header, make_header
from email.message import Message
from email.parser import BytesHeaderParser
from email.policy import default
from email.utils import getaddresses, parsedate_to_datetime
from urllib.parse import unquote_to_bytes

from .models import AttachmentInfo, MessageSummary


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except (LookupError, UnicodeError):
        return value.strip()


def _addresses(message: Message, header: str) -> list[str]:
    values = message.get_all(header, [])
    result: list[str] = []
    for name, address in getaddresses(values):
        decoded_name = decode_header_value(name)
        result.append(f"{decoded_name} <{address}>" if decoded_name else address)
    return [item for item in result if item]


def _message_ids(value: str | None) -> list[str]:
    if not value:
        return []
    ids = re.findall(r"<[^<>]+>", value)
    return ids or [token for token in value.split() if token]


def parse_header_summary(
    header_bytes: bytes,
    *,
    uid: str,
    mailbox: str,
    size: int | None = None,
    flags: list[str] | None = None,
    attachments: list[AttachmentInfo] | None = None,
) -> MessageSummary:
    message = BytesHeaderParser(policy=default).parsebytes(header_bytes)
    parsed_date: datetime | None = None
    if message.get("Date"):
        try:
            parsed_date = parsedate_to_datetime(str(message["Date"]))
        except (TypeError, ValueError, OverflowError):
            parsed_date = None
    senders = _addresses(message, "From")
    message_ids = _message_ids(str(message.get("Message-ID", "")))
    reply_ids = _message_ids(str(message.get("In-Reply-To", "")))
    return MessageSummary(
        uid=uid,
        mailbox=mailbox,
        subject=decode_header_value(str(message.get("Subject", ""))),
        sender=senders[0] if senders else "",
        to=_addresses(message, "To"),
        cc=_addresses(message, "Cc"),
        date=parsed_date,
        message_id=message_ids[0] if message_ids else None,
        in_reply_to=reply_ids[0] if reply_ids else None,
        references=_message_ids(str(message.get("References", ""))),
        size=size,
        flags=flags or [],
        attachments=attachments or [],
    )


def decode_transfer(data: bytes, encoding: str | None) -> bytes:
    normalized = (encoding or "").upper()
    if normalized == "BASE64":
        try:
            return base64.b64decode(data, validate=False)
        except (binascii.Error, ValueError):
            return data
    if normalized == "QUOTED-PRINTABLE":
        return quopri.decodestring(data)
    return data


def decode_text(data: bytes, *, encoding: str | None, charset: str | None) -> str:
    decoded = decode_transfer(data, encoding)
    for candidate in (charset, "utf-8", "windows-1252", "latin-1"):
        if not candidate:
            continue
        try:
            return decoded.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return decoded.decode("utf-8", errors="replace")


def decode_rfc2231(value: str | None) -> str | None:
    if not value:
        return None
    match = re.match(r"^([^']*)'[^']*'(.*)$", value)
    if match:
        charset = match.group(1) or "utf-8"
        try:
            return decode_header_value(
                unquote_to_bytes(match.group(2)).decode(charset, errors="replace")
            )
        except LookupError:
            return decode_header_value(
                unquote_to_bytes(match.group(2)).decode("utf-8", errors="replace")
            )
    return decode_header_value(value)


@dataclass(slots=True)
class BodyPart:
    section: str
    content_type: str
    params: dict[str, str] = field(default_factory=dict)
    content_id: str | None = None
    encoding: str | None = None
    size: int = 0
    disposition: str | None = None
    disposition_params: dict[str, str] = field(default_factory=dict)
    children: list["BodyPart"] = field(default_factory=list)

    @property
    def filename(self) -> str | None:
        return decode_rfc2231(
            self.disposition_params.get("filename*")
            or self.disposition_params.get("filename")
            or self.params.get("name*")
            or self.params.get("name")
        )

    @property
    def is_attachment(self) -> bool:
        return (self.disposition or "").upper() == "ATTACHMENT" or bool(self.filename)

    def walk(self):
        if not self.children:
            yield self
        for child in self.children:
            yield from child.walk()

    def to_attachment(self) -> AttachmentInfo:
        return AttachmentInfo(
            part=self.section,
            filename=self.filename,
            content_type=self.content_type,
            size=self.size,
            content_id=self.content_id,
            inline=(self.disposition or "").upper() == "INLINE",
        )


class BodyStructureError(ValueError):
    pass


class _BodyStructureParser:
    def __init__(self, value: bytes):
        self.value = value
        self.position = 0

    def parse(self):
        self._skip_space()
        result = self._item()
        return result

    def _skip_space(self) -> None:
        while self.position < len(self.value) and self.value[self.position] in b" \r\n\t":
            self.position += 1

    def _item(self):
        self._skip_space()
        if self.position >= len(self.value):
            raise BodyStructureError("Unexpected end of BODYSTRUCTURE")
        char = self.value[self.position]
        if char == ord("("):
            self.position += 1
            result = []
            while True:
                self._skip_space()
                if self.position >= len(self.value):
                    raise BodyStructureError("Unclosed BODYSTRUCTURE list")
                if self.value[self.position] == ord(")"):
                    self.position += 1
                    return result
                result.append(self._item())
        if char == ord('"'):
            return self._quoted()
        start = self.position
        while self.position < len(self.value) and self.value[self.position] not in b" ()\r\n\t":
            self.position += 1
        atom = self.value[start:self.position].decode("utf-8", errors="replace")
        if atom.upper() == "NIL":
            return None
        if atom.isdigit():
            return int(atom)
        return atom

    def _quoted(self) -> str:
        self.position += 1
        result = bytearray()
        escaped = False
        while self.position < len(self.value):
            char = self.value[self.position]
            self.position += 1
            if escaped:
                result.append(char)
                escaped = False
            elif char == ord("\\"):
                escaped = True
            elif char == ord('"'):
                return result.decode("utf-8", errors="replace")
            else:
                result.append(char)
        raise BodyStructureError("Unclosed quoted string in BODYSTRUCTURE")


def _pairs(value) -> dict[str, str]:
    if not isinstance(value, list):
        return {}
    result: dict[str, str] = {}
    for index in range(0, len(value) - 1, 2):
        key, item = value[index], value[index + 1]
        if key is not None and item is not None:
            result[str(key).lower()] = str(item)
    return result


def _disposition(value) -> tuple[str | None, dict[str, str]]:
    if not isinstance(value, list) or not value:
        return None, {}
    return str(value[0]), _pairs(value[1] if len(value) > 1 else None)


def _build_part(value, section: str = "") -> BodyPart:
    if not isinstance(value, list) or not value:
        raise BodyStructureError("Invalid BODYSTRUCTURE node")
    if isinstance(value[0], list):
        children: list[BodyPart] = []
        child_count = 0
        for item in value:
            if not isinstance(item, list):
                break
            child_count += 1
            child_section = f"{section}.{child_count}" if section else str(child_count)
            children.append(_build_part(item, child_section))
        subtype = str(value[child_count]) if child_count < len(value) else "MIXED"
        return BodyPart(section=section, content_type=f"multipart/{subtype.lower()}", children=children)

    media_type = str(value[0] or "application")
    subtype = str(value[1] or "octet-stream") if len(value) > 1 else "octet-stream"
    params = _pairs(value[2] if len(value) > 2 else None)
    content_id = str(value[3]) if len(value) > 3 and value[3] is not None else None
    encoding = str(value[5]) if len(value) > 5 and value[5] is not None else None
    size = value[6] if len(value) > 6 and isinstance(value[6], int) else 0
    extension_start = 7
    if media_type.upper() == "TEXT":
        extension_start = 8
    elif media_type.upper() == "MESSAGE" and subtype.upper() == "RFC822":
        extension_start = 10
    disposition_value = None
    # Extensions are: MD5, disposition, language, location. Some servers omit MD5.
    for candidate in value[extension_start:]:
        if isinstance(candidate, list) and candidate and str(candidate[0]).upper() in {"ATTACHMENT", "INLINE"}:
            disposition_value = candidate
            break
    disposition, disposition_params = _disposition(disposition_value)
    return BodyPart(
        section=section or "1",
        content_type=f"{media_type.lower()}/{subtype.lower()}",
        params=params,
        content_id=content_id,
        encoding=encoding,
        size=size,
        disposition=disposition,
        disposition_params=disposition_params,
    )


def parse_bodystructure(value: bytes) -> BodyPart:
    return _build_part(_BodyStructureParser(value).parse())

