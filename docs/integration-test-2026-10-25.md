# Kontrollierter WEB.DE-Integrationstest

Datum: 25. Oktober 2026

Version: 0.1.0

Umgebung: Windows, Python 3.13, lokaler Codex-Client

Der Test wurde gegen ein echtes WEB.DE-Postfach ausgeführt. Zugangsdaten kamen aus dem
Windows Credential Manager. Es wurden keine E-Mail-Adresse, UIDs, Absender, Betreffzeilen,
Nachrichteninhalte, Dateinamen, Anhänge oder Hashwerte protokolliert oder im Repository
gespeichert.

## Aussagekraft und Grenzen

Dieser Bericht ist ein anonymisierter, vom Projektbetreiber erstellter Funktionsnachweis. Der
Test wurde nicht von einer unabhängigen Stelle reproduziert und ist weder ein Audit noch ein
Nachweis gegenüber Dritten. GitHub Actions prüft die Anwendung mit simulierten
IMAP-Antworten; der Zugriff auf das echte WEB.DE-Postfach ist bewusst nicht Teil der CI.

Die geprüfte MCP-Verbindung gilt für einen lokalen Codex-Client auf demselben Rechner. Sie
stellt keine automatische Verbindung zu einer bestehenden ChatGPT-Web-Unterhaltung her.

Die Nur-Lese-Grenze wird durch die Anwendung (`EXAMINE`, zugelassene Kommandos und
`BODY.PEEK`) erzwungen. Das verwendete WEB.DE-App-Passwort ist kein auf Nur-Lese-Zugriff
beschränkter Berechtigungsnachweis und muss weiterhin wie ein vollwertiges Geheimnis
geschützt werden.

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
