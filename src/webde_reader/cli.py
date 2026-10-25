from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import date
from pathlib import Path

from .client import ImapError, ReadOnlyImapClient
from .config import AccountConfig, ConfigurationError, delete_password, save_password


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use YYYY-MM-DD") from exc


def _print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="webde-reader",
        description="Strictly read-only access to WEB.DE over IMAP/TLS.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    credentials = sub.add_parser("credentials", help="Manage the app password in the OS keyring")
    credential_sub = credentials.add_subparsers(dest="credential_command", required=True)
    set_password = credential_sub.add_parser("set", help="Store an app password")
    set_password.add_argument("username")
    remove_password = credential_sub.add_parser("remove", help="Delete a stored app password")
    remove_password.add_argument("username")

    check = sub.add_parser("check", help="Verify TLS, login, and read-only mailbox access")
    check.add_argument("--mailbox", default="INBOX")

    search = sub.add_parser("search", help="Search by date, sender, and subject")
    search.add_argument("--mailbox", default="INBOX")
    search.add_argument("--since", type=_date)
    search.add_argument("--before", type=_date)
    search.add_argument("--from", dest="sender")
    search.add_argument("--subject")
    search.add_argument("--limit", type=int, default=50)

    show = sub.add_parser("show", help="Fetch text bodies without downloading attachments")
    show.add_argument("uid")
    show.add_argument("--mailbox", default="INBOX")
    show.add_argument("--max-body-bytes", type=int, default=2_000_000)

    thread = sub.add_parser("thread", help="Reconstruct a thread from message headers")
    thread.add_argument("uid")
    thread.add_argument("--mailbox", default="INBOX")
    thread.add_argument("--max-messages", type=int, default=100)

    attachment = sub.add_parser("attachment", help="Download one selected MIME attachment")
    attachment.add_argument("uid")
    attachment.add_argument("part", help="MIME part number shown by search/show, e.g. 2 or 1.2")
    attachment.add_argument("--mailbox", default="INBOX")
    attachment.add_argument("--output", type=Path, required=True)
    attachment.add_argument("--max-bytes", type=int, default=25_000_000)
    attachment.add_argument("--force", action="store_true")
    return parser


def _credentials(args: argparse.Namespace) -> int:
    if args.credential_command == "set":
        first = getpass.getpass("WEB.DE app password: ")
        second = getpass.getpass("Repeat app password: ")
        if first != second:
            raise ConfigurationError("The entered passwords do not match.")
        save_password(args.username, first)
        print("App password stored in the operating-system keyring.")
    else:
        delete_password(args.username)
        print("Stored app password removed.")
    return 0


def run(args: argparse.Namespace) -> int:
    if args.command == "credentials":
        return _credentials(args)
    config = AccountConfig.from_environment()
    with ReadOnlyImapClient(config) as client:
        if args.command == "check":
            client.examine(args.mailbox)
            print(f"Connected to {config.host}:{config.port}; {args.mailbox!r} opened read-only.")
        elif args.command == "search":
            _print_json(
                [
                    item.to_dict()
                    for item in client.search(
                        mailbox=args.mailbox,
                        since=args.since,
                        before=args.before,
                        sender=args.sender,
                        subject=args.subject,
                        limit=args.limit,
                    )
                ]
            )
        elif args.command == "show":
            _print_json(
                client.get_message(
                    args.uid,
                    mailbox=args.mailbox,
                    max_body_bytes=args.max_body_bytes,
                ).to_dict()
            )
        elif args.command == "thread":
            _print_json(
                client.get_thread(
                    args.uid,
                    mailbox=args.mailbox,
                    max_messages=args.max_messages,
                ).to_dict()
            )
        elif args.command == "attachment":
            if args.output.exists() and not args.force:
                raise ConfigurationError(
                    f"Output path already exists: {args.output}. Use --force to overwrite it."
                )
            result = client.get_attachment(
                args.uid,
                args.part,
                mailbox=args.mailbox,
                max_bytes=args.max_bytes,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(result.content)
            print(f"Wrote {len(result.content)} bytes to {args.output}")
    return 0


def main(argv: list[str] | None = None) -> None:
    try:
        raise SystemExit(run(build_parser().parse_args(argv)))
    except (ConfigurationError, ImapError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()

