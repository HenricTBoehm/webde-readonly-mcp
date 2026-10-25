from __future__ import annotations

import base64
import unittest

from webde_reader.mime import decode_text, parse_bodystructure, parse_header_summary


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
        encoded = base64.b64encode("Grüße".encode("utf-8"))
        self.assertEqual(decode_text(encoded, encoding="BASE64", charset="utf-8"), "Grüße")


if __name__ == "__main__":
    unittest.main()

