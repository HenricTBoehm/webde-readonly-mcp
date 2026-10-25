from __future__ import annotations

import base64
import unittest

from webde_reader.mime import (
    decode_text,
    decode_transfer,
    parse_bodystructure,
    parse_header_summary,
)

BODYSTRUCTURE = (
    b'(("TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "QUOTED-PRINTABLE" 12 1 NIL NIL NIL NIL)'
    b'("APPLICATION" "PDF" ("NAME" "invoice.pdf") NIL NIL "BASE64" 16 NIL '
    b'("ATTACHMENT" ("FILENAME" "invoice.pdf")) NIL NIL) "MIXED" '
    b'("BOUNDARY" "abc") NIL NIL NIL)'
)


class MimeTests(unittest.TestCase):
    def test_parse_bodystructure_discovers_text_and_attachment(self):
        root = parse_bodystructure(BODYSTRUCTURE)
        parts = list(root.walk())
        self.assertEqual([part.section for part in parts], ["1", "2"])
        self.assertEqual(parts[0].content_type, "text/plain")
        self.assertEqual(parts[1].filename, "invoice.pdf")
        self.assertTrue(parts[1].is_attachment)

    def test_header_decoding_and_thread_headers(self):
        headers = (
            b"Date: Sun, 25 Oct 2026 10:00:00 +0100\r\n"
            b"From: =?utf-8?q?J=C3=B6rg?= <joerg@example.com>\r\n"
            b"To: Me <me@web.de>\r\n"
            b"Subject: =?utf-8?q?Pr=C3=BCfung?=\r\n"
            b"Message-ID: <child@example.com>\r\n"
            b"In-Reply-To: <root@example.com>\r\n"
            b"References: <root@example.com> <middle@example.com>\r\n\r\n"
        )
        result = parse_header_summary(headers, uid="4", mailbox="INBOX")
        self.assertEqual(result.subject, "Prüfung")
        self.assertEqual(result.sender, "Jörg <joerg@example.com>")
        self.assertEqual(result.references, ["<root@example.com>", "<middle@example.com>"])

    def test_transfer_and_charset_decoding(self):
        encoded = base64.b64encode("Grüße".encode())
        self.assertEqual(decode_text(encoded, encoding="BASE64", charset="utf-8"), "Grüße")

    def test_strict_transfer_decoding_rejects_malformed_data(self):
        with self.assertRaisesRegex(ValueError, "base64"):
            decode_transfer(b"%%%INVALID%%", "BASE64", strict=True)
        with self.assertRaisesRegex(ValueError, "quoted-printable"):
            decode_transfer(b"broken=QZ", "QUOTED-PRINTABLE", strict=True)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            decode_transfer(b"data", "X-UNKNOWN", strict=True)

    def test_rfc2231_filename_is_decoded(self):
        structure = (
            b'("APPLICATION" "PDF" NIL NIL NIL "BASE64" 4 NIL '
            b'("ATTACHMENT" ("FILENAME*" "UTF-8\'\'Pr%C3%BCfung.pdf")) NIL NIL)'
        )
        part = parse_bodystructure(structure)
        self.assertEqual(part.filename, "Prüfung.pdf")

    def test_attached_message_rfc822_is_handled_as_one_attachment(self):
        structure = (
            b'("MESSAGE" "RFC822" ("NAME" "forwarded.eml") NIL NIL "7BIT" 120 '
            b'NIL ("DATE" "SUBJECT" NIL NIL NIL NIL NIL NIL NIL NIL) '
            b'("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1) 5 NIL '
            b'("ATTACHMENT" ("FILENAME" "forwarded.eml")) NIL NIL)'
        )
        part = parse_bodystructure(structure)
        self.assertEqual(part.content_type, "message/rfc822")
        self.assertEqual(part.filename, "forwarded.eml")
        self.assertTrue(part.is_attachment)


if __name__ == "__main__":
    unittest.main()

