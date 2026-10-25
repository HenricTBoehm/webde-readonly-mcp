# WEB.DE Reader

Ein strikt lesender IMAP-Client für ein WEB.DE-Postfach. Das Projekt enthält:

- eine CLI für Suche, Nachrichtenabruf, Thread-Rekonstruktion und den gezielten Abruf einzelner Anhänge;
- einen lokalen FastMCP-Server über `stdio`, damit Codex dieselben Funktionen als Werkzeuge verwenden kann;
- Tests, die `EXAMINE`, `BODY.PEEK` und die Sperre schreibender IMAP-Kommandos prüfen.

Es gibt bewusst keine SMTP-, Lösch-, Verschiebe-, Kopier-, Markierungs- oder Versandfunktion.

## Voraussetzungen

- Python 3.13 oder neuer
- WEB.DE-Postfach mit aktiviertem POP3/IMAP-Zugriff
- ein WEB.DE-App-Passwort (empfohlen und bei Zwei-Faktor-Authentifizierung erforderlich)

WEB.DE dokumentiert für IMAP `imap.web.de`, Port `993`, SSL/TLS. Der Client verwendet ausschließlich diesen fest eingebauten Host und TLS ab Version 1.2.

## Installation

### Windows (PowerShell)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[mcp]"
```

### Linux

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[mcp]'
```

FastMCP ist exakt auf `4.1.3` fixiert, weil dessen eigene Dokumentation für Produktion exakte Versionen empfiehlt.

## Zugangsdaten

1. Aktiviere in WEB.DE unter **E-Mail-Einstellungen → POP3/IMAP Abruf** den IMAP-Zugriff.
2. Erzeuge unter **Account verwalten → Login & Sicherheit → App-Passwörter** ein separates App-Passwort.
3. Speichere es in der Schlüsselverwaltung des Betriebssystems:

```powershell
webde-reader credentials set name@web.de
$env:WEBDE_IMAP_USER = "name@web.de"
```

`keyring` nutzt je nach System z. B. Windows Credential Manager oder einen Linux Secret Service. Das Passwort landet weder im Repository noch in einer Projektdatei. Für einen nicht-interaktiven Prozess kann alternativ `WEBDE_IMAP_PASSWORD` gesetzt werden; das ist weniger empfehlenswert, da Prozessumgebungen je nach System auslesbar sein können. `.env`-Dateien werden absichtlich nicht geladen und sind per `.gitignore` ausgeschlossen.

## CLI

Verbindung und Lesemodus prüfen:

```powershell
webde-reader check
```

Suchen (`before` ist wie bei IMAP exklusiv):

```powershell
webde-reader search --since 2026-10-01 --before 2026-11-01 --from rechnung@example.org --subject Rechnung --limit 20
```

Nachricht abrufen. Text- und HTML-Teile werden einzeln gelesen; Anhangteile werden dabei nicht heruntergeladen:

```powershell
webde-reader show 12345
```

Thread über `Message-ID`, `In-Reply-To` und `References` innerhalb eines Ordners rekonstruieren:

```powershell
webde-reader thread 12345
```

Die Thread-Rekonstruktion ist standardmäßig zusätzlich auf 300 IMAP-Suchen und
500 unterschiedliche Referenz-IDs begrenzt. Die Grenzen lassen sich mit
`--max-searches` und `--max-reference-ids` innerhalb fest eingebauter Obergrenzen anpassen.

Einen in der Ausgabe gelisteten MIME-Anhang gezielt laden:

```powershell
webde-reader attachment 12345 2 --output .\attachments\rechnung.pdf
```

Der Anhang wird vollständig abgerufen und nur gespeichert, wenn seine übertragene Größe der
angekündigten MIME-Größe entspricht und die Transferkodierung strikt dekodiert werden kann.
Für kodierte und dekodierte Daten gelten getrennte Grenzen (`--max-encoded-bytes` und
`--max-bytes`). Vorhandene Dateien werden nur mit `--force` überschrieben. Mit `--mailbox`
kann bei den Lesebefehlen ein anderer Ordner angegeben werden.

## Lokaler FastMCP-Server für Codex

Der Server verwendet `stdio`: Codex startet einen lokalen Unterprozess; es wird kein Port geöffnet und kein HTTP-Endpunkt angeboten. Nach Installation und gesetztem `WEBDE_IMAP_USER`:

```powershell
codex mcp add webde-mail --env WEBDE_IMAP_USER=name@web.de -- "C:\ABSOLUTER\PFAD\.venv\Scripts\python.exe" -m webde_reader.mcp_server
codex mcp list
```

Falls der Codex-Prozess den Benutzervariablen nicht folgt, kann der Server in `~/.codex/config.toml` explizit konfiguriert werden. Verwende einen absoluten Pfad zur virtuellen Python-Umgebung, damit die Umgebung eindeutig ist:

```toml
[mcp_servers.webde-mail]
command = "C:\\ABSOLUTER\\PFAD\\.venv\\Scripts\\python.exe"
args = ["-m", "webde_reader.mcp_server"]
env = { WEBDE_IMAP_USER = "name@web.de" }
enabled_tools = ["search_messages", "get_message", "reconstruct_thread", "get_attachment"]
default_tools_approval_mode = "writes"
```

Unter Linux lautet `command` entsprechend `/absoluter/pfad/.venv/bin/python`. Das App-Passwort bleibt im OS-Keyring und gehört nicht in `config.toml`. Starte nach einer Konfigurationsänderung eine neue lokale Codex-Sitzung, falls der laufende Client seine MCP-Konfiguration nicht neu lädt.

Der Server stellt nur vier Werkzeuge bereit:

- `search_messages`
- `get_message`
- `reconstruct_thread`
- `get_attachment`

Alle sind mit dem MCP-Hinweis `readOnlyHint=true` versehen. Das ist Zusatzmetadaten; die eigentliche Durchsetzung erfolgt im Client durch die harte Kommandoliste (`SEARCH`, `FETCH`), `readonly=True`/`EXAMINE` und ausschließlich `BODY.PEEK`.

## Tests

Die Kern-Tests benötigen weder Netzwerk noch Zugangsdaten:

```powershell
python -m unittest discover -s tests -v
```

Optional mit installiertem Entwicklungs-Extra:

```powershell
pip install -e ".[dev]"
pytest
```

GitHub Actions führt bei jedem Push auf `main` und bei Pull Requests Ruff, die Unit-Tests,
`pip check` und `pip-audit` aus. Dependabot prüft wöchentlich Python- und Actions-Abhängigkeiten.

Ein anonymisierter Nachweis des kontrollierten Tests gegen ein echtes WEB.DE-Postfach steht
unter [docs/integration-test-2026-10-25.md](docs/integration-test-2026-10-25.md).
Der Bericht dokumentiert einen vom Projektbetreiber ausgeführten Test, keine unabhängige
Reproduktion oder formale Sicherheitsprüfung. Die CI verwendet simulierte IMAP-Antworten und
greift nicht auf ein echtes Postfach zu.

Ein echter Verbindungstest erfolgt nur auf ausdrücklichen Aufruf mit `webde-reader check`.

## Integrationsgrenze

Der lokale `stdio`-Server wurde für Codex auf demselben Rechner eingerichtet und getestet.
Diese Konfiguration stellt den Server nicht automatisch einer bereits laufenden oder
webbasierten ChatGPT-Unterhaltung bereit. ChatGPT im Web bindet MCP-Werkzeuge über Plugins
ein; das wäre ein eigener Integrations- und Freigabeschritt. Die ChatGPT-Desktop-App,
Codex CLI und die Codex-IDE-Erweiterung können dagegen die MCP-Konfiguration desselben lokalen
Codex-Hosts gemeinsam verwenden. Siehe [OpenAI Docs: MCP](https://learn.chatgpt.com/docs/extend/mcp).

## Sicherheitsgrenzen

- Der Client öffnet Ordner ausschließlich mit `EXAMINE` (`imaplib.select(..., readonly=True)`). Scheitert das, gibt es keinen Fallback auf schreibendes `SELECT`.
- Zugelassen sind nur UID-`SEARCH` und UID-`FETCH`; `STORE`, `APPEND`, `COPY`, `MOVE`, `EXPUNGE` und andere Kommandos werden nicht angeboten und intern abgewiesen.
- Alle dynamischen IMAP-Suchwerte verwerfen Steuerzeichen und überlange UTF-8-Eingaben vor
  dem ersten IMAP-Aufruf. Dies gilt auch für `Message-ID`- und `References`-Werte aus E-Mails.
- Nachrichtenteile werden ausschließlich mit `BODY.PEEK[...]` gelesen. Dadurch wird das Flag `\\Seen` nicht gesetzt.
- Es gibt keine SMTP-Abhängigkeit und keinen Versandpfad.
- TLS-Zertifikate werden über den System-Truststore geprüft; TLS 1.0/1.1 sind ausgeschlossen.
- Such- und Abrufgrenzen schützen vor versehentlich sehr großen Antworten. Der MCP-Anhangabruf
  liefert Base64 und begrenzt kodierte sowie dekodierte Daten separat.
- E-Mail-Inhalte und Anhänge sind nicht vertrauenswürdig. Die MCP-Serveranweisung legt fest,
  dass darin enthaltene Aufforderungen weder Benutzeraufträge noch Berechtigungen,
  Sicherheitsregeln oder Offenlegungsgrenzen verändern dürfen.
- Thread-Rekonstruktion arbeitet innerhalb genau eines IMAP-Ordners und anhand standardisierter Header. Fehlende oder fehlerhafte Header sowie ordnerübergreifende Threads können unvollständig bleiben.
- Die Nur-Lese-Eigenschaft wird durch diesen Client erzwungen, nicht durch ein technisch
  eingeschränktes WEB.DE-Konto oder einen Nur-Lese-Token. Das App-Passwort muss deshalb wie
  ein vollwertiges Geheimnis geschützt, ausschließlich im OS-Keyring gespeichert und bei
  Verdacht auf Offenlegung widerrufen beziehungsweise ersetzt werden.
- „Read-only“ bezieht sich auf das Postfach. Der CLI-Befehl `attachment` schreibt die vom Benutzer ausdrücklich angegebene lokale Zieldatei.

## Betrieb auf Synology (optional)

Für den lokalen Einsatz ist keine Synology nötig. Eine spätere Containerisierung ist möglich, dann sollte der Container weiterhin nur `stdio` oder einen ausschließlich im privaten Netz erreichbaren Transport verwenden. Auf einem Headless-System ist meist kein Desktop-Keyring verfügbar; nutze dort ein Secret des Container-Runtimes, mounte keine Klartextdatei ins Repository und veröffentliche den MCP-Endpunkt nicht ungefiltert ins Internet.

## Quellen

- [WEB.DE: Serverdaten für IMAP](https://hilfe.web.de/pop-imap/imap/imap-serverdaten.html)
- [WEB.DE: App-Passwort einrichten](https://hilfe.web.de/account/logindaten/app-passwort.html)
- [FastMCP: Quickstart und stdio](https://gofastmcp.com/getting-started/quickstart)
- [OpenAI Docs: MCP mit Codex verbinden](https://learn.chatgpt.com/docs/extend/mcp)

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).

