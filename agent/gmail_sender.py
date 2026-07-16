"""Gmail API sender — creates a draft (or sends) via OAuth refresh token.

Reads credentials from env vars (set via GitHub Actions secrets):
    GMAIL_CLIENT_ID
    GMAIL_CLIENT_SECRET
    GMAIL_REFRESH_TOKEN
    GMAIL_TO

Usage:
    from agent.gmail_sender import create_draft
    create_draft(subject="...", body_md="...", attachments=["path/to/file.pdf"])

Auth setup: see docs/SETUP_GITHUB_ACTIONS.md.
"""
from __future__ import annotations

import base64
import os
import sys
import mimetypes
from email.message import EmailMessage
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_DRAFTS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def _exchange_refresh_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Exchange refresh_token for an access_token. Returns the access_token string."""
    if requests is None:
        raise RuntimeError("requests not installed")
    resp = requests.post(
        GMAIL_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _build_mime(subject: str, to_addr: str, body_text: str, attachments: list[Path]) -> str:
    """Assemble a MIME message and return its base64url-encoded raw form."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["To"] = to_addr
    msg.set_content(body_text)
    for path in attachments:
        ctype, _ = mimetypes.guess_type(str(path))
        if ctype is None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        with open(path, "rb") as f:
            msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=path.name)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return raw


def create_draft(subject: str, body_text: str, attachments: list[str | Path] | None = None,
                 to_addr: str | None = None) -> dict:
    """Create a Gmail draft with optional attachments. Returns the draft resource dict."""
    client_id = os.environ.get("GMAIL_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN", "").strip()
    to_addr = to_addr or os.environ.get("GMAIL_TO", "").strip()
    if not all([client_id, client_secret, refresh_token, to_addr]):
        raise RuntimeError("Gmail OAuth env vars missing (GMAIL_CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN/TO)")

    access_token = _exchange_refresh_token(client_id, client_secret, refresh_token)
    paths = [Path(p) for p in (attachments or []) if Path(p).exists()]
    raw = _build_mime(subject, to_addr, body_text, paths)

    resp = requests.post(
        GMAIL_DRAFTS_URL,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"message": {"raw": raw}},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":  # pragma: no cover
    # Smoke-test usage
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--subject", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--to", default=None)
    p.add_argument("--attach", action="append", default=[])
    args = p.parse_args()
    out = create_draft(args.subject, args.body, args.attach, args.to)
    print(out.get("id"))
