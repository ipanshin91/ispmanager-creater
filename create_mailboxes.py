#!/usr/bin/env python3
"""Create ispmanager mailboxes in bulk from a text file.

Input line format:
    login;password;note;forward_email

Fields are separated by `;`. Empty lines and lines starting with `#` are
skipped. If the `note` field contains `;`, wrap the field in double quotes:
    user1;Passw0rd!;"Ivanov; sales dept";backup@example.com
"""
from __future__ import annotations

import argparse
import csv
import getpass
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
import urllib3

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass


@dataclass
class MailboxRow:
    line_no: int
    login: str
    password: str
    note: str
    forward: str


class ISPManagerAPIError(Exception):
    def __init__(self, err_type: str, message: str, raw: str = "") -> None:
        self.err_type = err_type or "api_error"
        self.message = message or "Unknown API error"
        self.raw = raw
        super().__init__(f"{self.err_type}: {self.message}")


class ISPManagerClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        verify_ssl: bool = True,
        timeout: int = 30,
        lang: str = "en",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.lang = lang

        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.auth_id: str | None = None

        if not verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def authenticate(self) -> None:
        payload = {
            "out": "xml",
            "lang": self.lang,
            "func": "auth",
            "username": self.username,
            "password": self.password,
        }
        root = self._post(payload)

        auth_el = root.find("auth")
        auth_value = ""
        if auth_el is not None:
            auth_value = (auth_el.text or "").strip() or (auth_el.get("id") or "").strip()

        if not auth_value:
            raise RuntimeError(
                "Could not get auth session id. "
                "Check the panel URL, username/password and API access."
            )

        self.auth_id = auth_value

    def create_domain(self, domain: str) -> None:
        self._action(
            "emaildomain.edit",
            sok="ok",
            name=domain,
        )

    def create_mailbox(
        self,
        *,
        domain: str,
        login: str,
        password: str,
        note: str = "",
        forward: str = "",
        dontsave_forward_copy: bool = False,
    ) -> None:
        params: dict[str, str] = {
            "sok": "ok",
            "name": login,
            "domainname": domain,
            "passwd": password,
            "confirm": password,
        }
        if note:
            params["note"] = note
        if forward:
            params["forward"] = forward
            if dontsave_forward_copy:
                params["dontsave"] = "on"

        self._action("email.edit", **params)

    def _action(self, func: str, **params: str) -> None:
        if not self.auth_id:
            self.authenticate()

        root = self._call(func, params)

        if root.find("ok") is None:
            raise RuntimeError(
                f"Panel returned an unexpected response for func={func}: "
                f"{ET.tostring(root, encoding='unicode')}"
            )

    def _call(self, func: str, params: dict[str, str]) -> ET.Element:
        payload = {
            "out": "xml",
            "lang": self.lang,
            "auth": self.auth_id or "",
            "func": func,
            **params,
        }

        try:
            return self._post(payload)
        except ISPManagerAPIError as exc:
            # Session may have expired: re-auth and retry once.
            if exc.err_type in {"auth", "badauth", "session"}:
                self.authenticate()
                payload["auth"] = self.auth_id or ""
                return self._post(payload)
            raise

    def _post(self, payload: dict[str, str]) -> ET.Element:
        try:
            response = self.session.post(
                self.base_url,
                data=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"HTTP error while calling the panel: {exc}") from exc

        text = response.text.strip()

        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise RuntimeError(
                "Panel returned non-XML or broken XML.\n"
                f"First 500 chars of the response:\n{text[:500]}"
            ) from exc

        error_el = root.find("error")
        if error_el is not None:
            err_type = error_el.get("type", "api_error")
            msg_el = error_el.find("msg")
            group_el = error_el.find("group")

            if msg_el is not None and msg_el.text:
                message = msg_el.text.strip()
            elif group_el is not None and group_el.text:
                message = group_el.text.strip()
            else:
                message = "Unknown API error"

            raise ISPManagerAPIError(err_type=err_type, message=message, raw=text)

        return root


def read_rows(path: Path) -> Iterable[MailboxRow]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";", quotechar='"')
        for line_no, row in enumerate(reader, start=1):
            if not row:
                continue

            row = [cell.strip() for cell in row]

            if not any(row):
                continue

            if row[0].startswith("#"):
                continue

            if len(row) < 4:
                row.extend([""] * (4 - len(row)))

            if len(row) > 4:
                raise ValueError(
                    f"Line {line_no}: expected 4 fields "
                    f"(login;password;note;forward_email), got {len(row)}. "
                    f"If the note contains ';', wrap the field in double quotes."
                )

            login, password, note, forward = row

            if not login:
                raise ValueError(f"Line {line_no}: empty login")
            if not password:
                raise ValueError(f"Line {line_no}: empty password")

            yield MailboxRow(
                line_no=line_no,
                login=login,
                password=password,
                note=note,
                forward=forward,
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create ispmanager mailboxes in bulk from a text file.",
    )
    parser.add_argument(
        "--panel-url",
        required=True,
        help="Panel URL, for example: https://server.example.com:1500/ispmgr",
    )
    parser.add_argument(
        "--panel-user",
        required=True,
        help="ispmanager panel username",
    )
    parser.add_argument(
        "--panel-password",
        help="Panel password. If not set, will be asked on the prompt.",
    )
    parser.add_argument(
        "--domain",
        required=True,
        help="Mail domain for the mailboxes, for example example.com",
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to the input file with mailbox data",
    )
    parser.add_argument(
        "--create-domain",
        action="store_true",
        help="Create the mail domain first (emaildomain.edit)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip the mailbox/domain if it already exists and keep going",
    )
    parser.add_argument(
        "--dontsave-forward-copy",
        action="store_true",
        help="If forward is set, do not keep a local copy in the mailbox",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Do not verify the panel SSL certificate",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be created, do not call the panel",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.file)
    if not input_path.exists():
        print(f"File not found: {input_path}", file=sys.stderr)
        return 2

    try:
        rows = list(read_rows(input_path))
    except Exception as exc:
        print(f"Error reading file: {exc}", file=sys.stderr)
        return 2

    if not rows:
        print("Input file has no data.")
        return 0

    if args.dry_run:
        print("DRY RUN")
        print(f"Domain: {args.domain}")
        print(f"Rows: {len(rows)}")
        for row in rows:
            addr = f"{row.login}@{args.domain}"
            print(
                f"[line {row.line_no}] create {addr} "
                f"(note={row.note!r}, forward={row.forward!r})"
            )
        return 0

    password = args.panel_password or getpass.getpass("Password for ispmanager: ")

    client = ISPManagerClient(
        base_url=args.panel_url,
        username=args.panel_user,
        password=password,
        verify_ssl=not args.insecure,
        timeout=args.timeout,
    )

    try:
        client.authenticate()
    except Exception as exc:
        print(f"Login error: {exc}", file=sys.stderr)
        return 3

    if args.create_domain:
        try:
            client.create_domain(args.domain)
            print(f"[OK] Mail domain created: {args.domain}")
        except ISPManagerAPIError as exc:
            if args.skip_existing and exc.err_type == "exists":
                print(f"[SKIP] Domain already exists: {args.domain}")
            else:
                print(f"[ERROR] Failed to create domain {args.domain}: {exc}",
                      file=sys.stderr)
                return 4
        except Exception as exc:
            print(f"[ERROR] Failed to create domain {args.domain}: {exc}",
                  file=sys.stderr)
            return 4

    created = 0
    skipped = 0
    errors = 0

    for row in rows:
        address = f"{row.login}@{args.domain}"
        try:
            client.create_mailbox(
                domain=args.domain,
                login=row.login,
                password=row.password,
                note=row.note,
                forward=row.forward,
                dontsave_forward_copy=args.dontsave_forward_copy,
            )
            created += 1
            print(f"[OK] {address}")
        except ISPManagerAPIError as exc:
            if args.skip_existing and exc.err_type == "exists":
                skipped += 1
                print(f"[SKIP] {address} already exists")
                continue
            errors += 1
            print(f"[ERROR] {address}: {exc}", file=sys.stderr)
        except Exception as exc:
            errors += 1
            print(f"[ERROR] {address}: {exc}", file=sys.stderr)

    print(
        f"\nDone\n"
        f"Created: {created}\n"
        f"Skipped: {skipped}\n"
        f"Errors : {errors}"
    )

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
