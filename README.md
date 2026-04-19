# ispmanager mailbox creator

Python script to create mailboxes in bulk in the **ispmanager** panel
(5/6, lite/pro) via its XML API, from a plain text file.

## Features

- Create many mailboxes in one run from a `login;password;note;forward` file.
- Optionally create the mail domain before creating mailboxes.
- Set a forward address and the "do not keep a local copy" option.
- Skip mailboxes that already exist (`--skip-existing`).
- `--dry-run` mode that does not call the panel.
- Works with self-signed certificates (`--insecure`).
- Re-logs in automatically if the session expires.

## Requirements

- Python 3.9+
- Access to the ispmanager panel API (an account that can create mail).

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Input file format

Encoding: UTF-8 (with or without BOM). Field separator: `;`.

```
login;password;note;forward_email
```

Rules:

- Lines starting with `#` and empty lines are skipped.
- `note` and `forward` are optional, but the `;` separators must still be there.
- If `note` contains `;`, wrap the whole field in double quotes:
  `user1;Passw0rd!;"Ivanov; sales";backup@example.com`
- `forward` can hold one address (multiple addresses separated by commas
  work on most panel versions, but it depends on the build).

See `mailboxes.example.txt` for a full example.

## Run

PowerShell (Windows):

```powershell
python .\create_mailboxes.py `
  --panel-url "https://your-server:1500/ispmgr" `
  --panel-user "admin" `
  --domain "example.com" `
  --file ".\mailboxes.example.txt" `
  --create-domain `
  --skip-existing
```

Bash (Linux/macOS):

```bash
python create_mailboxes.py \
  --panel-url "https://your-server:1500/ispmgr" \
  --panel-user "admin" \
  --domain "example.com" \
  --file "mailboxes.txt" \
  --create-domain \
  --skip-existing
```

The password is asked on the prompt. You can also pass it with
`--panel-password`, but that is less safe (it will end up in shell history).

### Preview without calling the panel

```powershell
python .\create_mailboxes.py `
  --panel-url "https://your-server:1500/ispmgr" `
  --panel-user "admin" `
  --domain "example.com" `
  --file ".\mailboxes.example.txt" `
  --dry-run
```

## All flags

| Flag | Description |
| --- | --- |
| `--panel-url` | Panel URL, e.g. `https://host:1500/ispmgr`. Required. |
| `--panel-user` | Panel username. Required. |
| `--panel-password` | Panel password. If not set, will be asked on the prompt. |
| `--domain` | Domain for the mailboxes. Required. |
| `--file` | Path to the input file. Required. |
| `--create-domain` | Create the mail domain before creating mailboxes. |
| `--skip-existing` | Skip the domain/mailbox if it already exists. |
| `--dontsave-forward-copy` | For mailboxes with `forward`, do not keep a local copy. |
| `--insecure` | Do not verify SSL certificate (for self-signed certs). |
| `--timeout` | HTTP timeout in seconds. Default: 30. |
| `--dry-run` | Only show the plan, do not call the panel. |

## Exit codes

- `0` – all good (or dry run).
- `1` – finished, but some mailboxes failed.
- `2` – problem with the input file.
- `3` – login to the panel failed.
- `4` – could not create the domain (and `--skip-existing` was not set).

## Troubleshooting

- **"Panel returned non-XML"** – the `--panel-url` is wrong. Make sure it
  ends with `/ispmgr` (or the path used by your build). Open the URL in a
  browser and check that you see the ispmanager login page.
- **SSL error** – use `--insecure` for self-signed certificates, or
  install a valid certificate on the server.
- **`exists` errors for existing objects** – add `--skip-existing`.
- **API field names (`emaildomain.edit`, `email.edit`) differ between
  ispmanager versions.** If the panel complains about a field, open the
  "create mailbox" form in your browser, check DevTools → Network for the
  field names that are actually sent, and update them in the script
  (in `create_domain` and `create_mailbox`).

