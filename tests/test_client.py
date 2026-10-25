from __future__ import annotations

import unittest
from datetime import date

from webde_reader.client import ImapError, ReadOnlyImapClient, _quoted_utf8
from webde_reader.config import AccountConfig

BODYSTRUCTURE = (
    b'(("TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 5 1 NIL NIL NIL NIL)'
    b'("APPLICATION" "PDF" ("NAME" "a.pdf") NIL NIL "BASE64" 12 NIL '
    b'("ATTACHMENT" ("FILENAME" "a.pdf")) NIL NIL) "MIXED" ("BOUNDARY" "x") NIL NIL NIL)'
)
HEADERS = (
    b"Date: Sun, 25 Oct 2026 10:00:00 +0100\r\n"
    b"From: sender@example.com\r\n"
    b"To: me@web.de\r\n"
    b"Subject: Test\r\n"
    b"Message-ID: <one@example.com>\r\n\r\n"
)


class FakeImap:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def login(self, username, password):
        self.calls.append(("LOGIN", username, password))
        return "OK", [b"logged in"]

    def select(self, mailbox, readonly=False):
        self.calls.append(("SELECT", mailbox, readonly))
        return "OK", [b"1"]

    def uid(self, command, *args):
        self.calls.append(("UID", command, *args))
        if command == "SEARCH":
            return "OK", [b"7"]
        query = str(args[1])
        if "HEADER.FIELDS" in query:
            prefix = b"1 (UID 7 RFC822.SIZE 321 FLAGS (\\Seen) BODYSTRUCTURE " + BODYSTRUCTURE + b" {150}"
            return "OK", [(prefix, HEADERS), b")"]
        if "BODY.PEEK[1]" in query:
            return "OK", [(b"1 (UID 7 BODY[1] {5}", b"hello"), b")"]
        if "BODY.PEEK[2]" in query:
            return "OK", [(b"1 (UID 7 BODY[2] {12}", b"UERGREFUQQ=="), b")"]
        raise AssertionError(args)

    def logout(self):
        self.calls.append(("LOGOUT",))
        return "BYE", [b"bye"]


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeImap()
        self.client = ReadOnlyImapClient(
            AccountConfig("me@web.de", "secret"),
            connection_factory=lambda *args, **kwargs: self.fake,
        )

    def test_search_uses_examine_and_body_peek_only(self):
        with self.client as client:
            result = client.search(
                since=date(2026, 10, 1),
                sender="sender@example.com",
                subject="Test",
            )
        self.assertEqual(result[0].uid, "7")
        self.assertEqual(result[0].attachments[0].part, "2")
        self.assertIn(("SELECT", '"INBOX"', True), self.fake.calls)
        transcript = repr(self.fake.calls)
        self.assertIn("BODY.PEEK", transcript)
        self.assertNotIn("STORE", transcript)
        self.assertNotIn("EXPUNGE", transcript)

    def test_show_fetches_text_but_not_attachment(self):
        with self.client as client:
            result = client.get_message("7")
        self.assertEqual(result.text, "hello")
        fetches = [call for call in self.fake.calls if call[:2] == ("UID", "FETCH")]
        self.assertTrue(any("BODY.PEEK[1]" in str(call) for call in fetches))
        self.assertFalse(any("BODY.PEEK[2]" in str(call) for call in fetches))

    def test_attachment_is_explicit_and_transfer_decoded(self):
        with self.client as client:
            result = client.get_attachment("7", "2")
        self.assertEqual(result.content, b"PDFDATA")
        self.assertEqual(result.info.filename, "a.pdf")
        attachment_fetches = [
            call
            for call in self.fake.calls
            if call[:2] == ("UID", "FETCH") and "BODY.PEEK[2]" in str(call)
        ]
        self.assertEqual(len(attachment_fetches), 1)
        self.assertNotIn("<0.", str(attachment_fetches[0]))

    def test_search_rejects_all_control_characters_before_imap(self):
        for value in ("safe\r\nSTORE 7 +FLAGS \\Seen", "nul\x00byte", "del\x7fbyte", "c1\x85"):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError, "Control characters"):
                    _quoted_utf8(value)

        with self.client as client:
            with self.assertRaisesRegex(ValueError, "Control characters"):
                client.search(subject="invoice\r\nUID STORE 7 +FLAGS \\Seen")
        self.assertFalse(any(call[:2] == ("UID", "SEARCH") for call in self.fake.calls))

    def test_search_value_length_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "byte limit"):
            _quoted_utf8("x" * 8_193)

    def test_mutating_commands_are_rejected(self):
        with self.client as client:
            with self.assertRaisesRegex(Exception, "not allowed"):
                client._uid("STORE", "7", "+FLAGS", "\\Seen")

    def test_mailbox_control_characters_are_rejected_before_select(self):
        with self.client as client:
            with self.assertRaisesRegex(ValueError, "control characters"):
                client.examine("INBOX\r\nSTORE 7 +FLAGS \\Seen")
        self.assertFalse(any(call[0] == "SELECT" for call in self.fake.calls))

    def test_mailbox_is_quoted_and_modified_utf7_encoded(self):
        with self.client as client:
            client.examine("Gesendet & Entwürfe")
        self.assertIn(("SELECT", '"Gesendet &- Entw&APw-rfe"', True), self.fake.calls)


class InvalidBase64Imap(FakeImap):
    def uid(self, command, *args):
        if command == "FETCH" and "BODY.PEEK[2]" in str(args[1]):
            self.calls.append(("UID", command, *args))
            return "OK", [(b"1 (UID 7 BODY[2] {12}", b"%%%INVALID%%"), b")"]
        return super().uid(command, *args)


class TruncatedAttachmentImap(FakeImap):
    def uid(self, command, *args):
        if command == "FETCH" and "BODY.PEEK[2]" in str(args[1]):
            self.calls.append(("UID", command, *args))
            return "OK", [(b"1 (UID 7 BODY[2] {4}", b"UERG"), b")"]
        return super().uid(command, *args)


class AttachmentIntegrityTests(unittest.TestCase):
    def _client(self, fake):
        return ReadOnlyImapClient(
            AccountConfig("me@web.de", "secret"),
            connection_factory=lambda *args, **kwargs: fake,
        )

    def test_invalid_base64_is_an_error(self):
        with self._client(InvalidBase64Imap()) as client:
            with self.assertRaisesRegex(ImapError, "invalid"):
                client.get_attachment("7", "2")

    def test_incomplete_attachment_is_an_error(self):
        with self._client(TruncatedAttachmentImap()) as client:
            with self.assertRaisesRegex(ImapError, "incomplete"):
                client.get_attachment("7", "2")

    def test_encoded_and_decoded_limits_are_independent(self):
        with self._client(FakeImap()) as client:
            with self.assertRaisesRegex(ImapError, "encoded-data limit"):
                client.get_attachment("7", "2", max_encoded_bytes=11)
        with self._client(FakeImap()) as client:
            with self.assertRaisesRegex(ImapError, "Decoded attachment"):
                client.get_attachment("7", "2", max_bytes=6)


class ThreadFakeImap(FakeImap):
    CHILD_HEADERS = (
        b"Date: Sun, 25 Oct 2026 11:00:00 +0100\r\n"
        b"From: reply@example.com\r\n"
        b"To: me@web.de\r\n"
        b"Subject: Re: Test\r\n"
        b"Message-ID: <two@example.com>\r\n"
        b"In-Reply-To: <one@example.com>\r\n"
        b"References: <one@example.com>\r\n\r\n"
    )

    def uid(self, command, *args):
        self.calls.append(("UID", command, *args))
        if command == "SEARCH":
            transcript = repr(args)
            if "two@example.com" in transcript:
                return "OK", [b"8"]
            return "OK", [b"7 8"]
        uid, query = str(args[0]), str(args[1])
        if "HEADER.FIELDS" in query:
            headers = self.CHILD_HEADERS if uid == "8" else HEADERS
            prefix = (
                f"1 (UID {uid} RFC822.SIZE 321 FLAGS () BODYSTRUCTURE ".encode()
                + BODYSTRUCTURE
                + b" {150}"
            )
            return "OK", [(prefix, headers), b")"]
        return super().uid(command, *args)


class ThreadTests(unittest.TestCase):
    def test_reconstructs_parent_and_child(self):
        fake = ThreadFakeImap()
        client = ReadOnlyImapClient(
            AccountConfig("me@web.de", "secret"),
            connection_factory=lambda *args, **kwargs: fake,
        )
        with client:
            thread = client.get_thread("8")
        self.assertEqual([message.uid for message in thread.messages], ["7", "8"])
        self.assertEqual(thread.root_message_id, "<one@example.com>")

    def test_thread_search_has_a_hard_query_budget(self):
        fake = ThreadFakeImap()
        client = ReadOnlyImapClient(
            AccountConfig("me@web.de", "secret"),
            connection_factory=lambda *args, **kwargs: fake,
        )
        with client:
            with self.assertRaisesRegex(ImapError, "limit of 1 IMAP searches"):
                client.get_thread("8", max_searches=1)


if __name__ == "__main__":
    unittest.main()

