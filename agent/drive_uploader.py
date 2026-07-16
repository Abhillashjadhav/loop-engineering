"""Google Drive API uploader — uploads files via OAuth refresh token.

Reads credentials from env vars (set via GitHub Actions secrets):
    GDRIVE_CLIENT_ID
    GDRIVE_CLIENT_SECRET
    GDRIVE_REFRESH_TOKEN
    GDRIVE_PARENT_FOLDER_ID

Usage:
    from agent.drive_uploader import upload_file, ensure_subfolder
    folder_id = ensure_subfolder("2026-05-04")
    upload_file("path/to/resume.pdf", parent_id=folder_id)

Auth setup: see docs/SETUP_GITHUB_ACTIONS.md.
"""
from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


DRIVE_TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"


def _exchange_refresh_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    if requests is None:
        raise RuntimeError("requests not installed")
    resp = requests.post(
        DRIVE_TOKEN_URL,
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


def _get_access_token() -> str:
    cid = os.environ.get("GDRIVE_CLIENT_ID", "").strip()
    cs = os.environ.get("GDRIVE_CLIENT_SECRET", "").strip()
    rt = os.environ.get("GDRIVE_REFRESH_TOKEN", "").strip()
    if not all([cid, cs, rt]):
        raise RuntimeError("Drive OAuth env vars missing (GDRIVE_CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN)")
    return _exchange_refresh_token(cid, cs, rt)


def _list_children(access_token: str, parent_id: str, name: str) -> list[dict]:
    """Return matching files under parent_id with the given name."""
    q = f"'{parent_id}' in parents and name='{name}' and trashed=false"
    resp = requests.get(
        DRIVE_FILES_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": q, "fields": "files(id,name,mimeType)"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("files", [])


def ensure_subfolder(name: str, parent_id: str | None = None) -> str:
    """Return the Drive folder ID for `name` under `parent_id`, creating if missing."""
    access = _get_access_token()
    parent_id = parent_id or os.environ.get("GDRIVE_PARENT_FOLDER_ID", "").strip()
    if not parent_id:
        raise RuntimeError("GDRIVE_PARENT_FOLDER_ID not set")

    existing = _list_children(access, parent_id, name)
    folders = [f for f in existing if f.get("mimeType") == "application/vnd.google-apps.folder"]
    if folders:
        return folders[0]["id"]

    resp = requests.post(
        DRIVE_FILES_URL,
        headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
        json={
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def upload_file(path: str | Path, parent_id: str, drive_name: str | None = None) -> dict:
    """Multipart-upload a file to Drive under parent_id. Returns the file resource dict.

    If a file with the same name already exists in the folder, it is updated in place
    (so re-running the workflow doesn't create duplicates).
    """
    access = _get_access_token()
    p = Path(path)
    drive_name = drive_name or p.name
    mime, _ = mimetypes.guess_type(p.name)
    if mime is None:
        mime = "application/octet-stream"

    existing = _list_children(access, parent_id, drive_name)
    file_id = existing[0]["id"] if existing else None

    metadata = {"name": drive_name}
    if file_id is None:
        metadata["parents"] = [parent_id]

    boundary = "drive-upload-boundary-7c9f3e2a"
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    body += p.read_bytes()
    body += f"\r\n--{boundary}--".encode("utf-8")

    if file_id:
        url = f"{DRIVE_UPLOAD_URL}/{file_id}?uploadType=multipart"
        method = "PATCH"
    else:
        url = f"{DRIVE_UPLOAD_URL}?uploadType=multipart"
        method = "POST"

    resp = requests.request(
        method, url,
        headers={
            "Authorization": f"Bearer {access}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        data=body,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--folder", required=True, help="Subfolder name under GDRIVE_PARENT_FOLDER_ID")
    p.add_argument("--file", required=True)
    args = p.parse_args()
    folder_id = ensure_subfolder(args.folder)
    out = upload_file(args.file, folder_id)
    print(out.get("id"), out.get("name"))
