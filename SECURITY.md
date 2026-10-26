# Security Policy

## Supported versions

Security fixes are provided for the latest release line.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Earlier versions | No |

The current `main` branch may contain unreleased fixes, but it is not a substitute for a
supported release.

## Reporting a vulnerability

Please do not disclose suspected vulnerabilities in a public issue, discussion, pull request,
or chat. Use GitHub's
[private vulnerability reporting](https://github.com/HenricTBoehm/webde-readonly-mcp/security/advisories/new)
instead.

Include, where possible:

- the affected version or commit;
- a concise description of the impact and attack prerequisites;
- reproducible steps or a minimal proof of concept;
- any suggested mitigation; and
- confirmation that the report contains no mailbox credentials, private email content, or
  downloaded attachments.

The maintainer aims to acknowledge a report within seven days and provide a status update at
least every fourteen days until it is resolved or declined. Remediation and disclosure timing
depend on severity and complexity. Please allow time for a fix before public disclosure.

## Credential incidents

The application enforces read-only IMAP behavior, but a WEB.DE app password is not itself a
read-only credential. If an app password may have been exposed, revoke it immediately in the
WEB.DE account, create a replacement, and update the operating-system keyring. Never include
the password in a vulnerability report.
