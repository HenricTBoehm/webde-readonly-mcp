# Kontrollierter WEB.DE-Integrationstest

Datum: 25. Oktober 2026

Version: 0.1.0

Umgebung: Windows, Python 3.13, lokaler Codex-Client

Der Test wurde gegen ein echtes WEB.DE-Postfach ausgeführt. Zugangsdaten kamen aus dem
Windows Credential Manager. Es wurden keine E-Mail-Adresse, UIDs, Absender, Betreffzeilen,
Nachrichteninhalte, Dateinamen, Anhänge oder Hashwerte protokolliert oder im Repository
gespeichert.

## Ergebnis

| Abnahmekriterium | Ergebnis |
| --- | --- |
| Anmeldung mit App-Passwort aus dem Windows Credential Manager | Bestanden |
| `INBOX` über `EXAMINE` öffnen und Nachrichten suchen | Bestanden |
| Umlaute, Anführungszeichen und Backslash in einem Suchbegriff | Bestanden |
| Nachricht über `BODY.PEEK` abrufen | Bestanden |
| Mehrteiligen Thread rekonstruieren | Bestanden (3 Nachrichten) |
| PDF-Anhang vollständig abrufen und Integrität prüfen | Bestanden |
| Eine zuvor ungelesene Nachricht bleibt ungelesen | Bestanden |
| Registriertes `search_messages`-Werkzeug aus Codex aufrufen | Bestanden (`MCP_PASS`) |

## Prüfverfahren

- Für die Flag-Prüfung wurden die IMAP-Flags unmittelbar vor und nach dem Textabruf gelesen.
  Die Flags waren identisch; der ungelesene Zustand blieb erhalten.
- Der Anhangabruf musste die angekündigte kodierte Länge exakt erfüllen und die strikte
  Transferdekodierung bestehen. Zusätzlich wurden PDF-Signatur, EOF-Markierung und die lokale
  Berechnung eines SHA-256-Werts geprüft. Der Wert selbst wurde nicht gespeichert.
- Der MCP-Transport wurde zuerst direkt über `stdio` initialisiert. Anschließend rief ein
  isolierter Codex-CLI-Lauf `webde-mail/search_messages` mit einem garantiert ergebnislosen
  Testbegriff auf und erhielt `MCP_PASS`.
- Die Integrationstests bleiben absichtlich außerhalb von GitHub Actions, da CI weder Zugang
  zum persönlichen Postfach noch zu dessen App-Passwort erhalten soll.

## Lokale Codex-Einstellung

Der Python-/FastMCP-Prozess benötigt auf dem geprüften Windows-System länger als die kurze
Wartefrist für optionale MCP-Server. Der lokale Server wurde deshalb als erforderlich markiert
und erhält 30 Sekunden Startzeit. Diese benutzerspezifische Einstellung liegt ausschließlich in
der lokalen Codex-Konfiguration und nicht im Repository.
