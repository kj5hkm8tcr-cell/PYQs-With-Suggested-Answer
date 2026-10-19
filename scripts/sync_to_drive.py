#!/usr/bin/env python3
"""Mirror a local folder (default: dist/) into a Google Drive folder.

Folders are created as needed; a file is uploaded only when it is new or its
contents changed (compared by MD5), so re-running is cheap.

Authentication (pick one, via environment variables):

  A) Your own Google account (works with a normal Gmail Drive):
       GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN
     Get the refresh token once with scripts/get_refresh_token.py.

  B) Service account (only works with a *Shared Drive*, because service
     accounts have no storage of their own):
       GDRIVE_SERVICE_ACCOUNT_JSON  (the full JSON key as text)

Always required:
  GDRIVE_ROOT_FOLDER_ID  the ID from the Drive folder URL
                         https://drive.google.com/drive/folders/<THIS_PART>
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"
LIST_KW = {"supportsAllDrives": True, "includeItemsFromAllDrives": True}


def get_service():
    sa_json = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        creds = service_account.Credentials.from_service_account_info(json.loads(sa_json), scopes=SCOPES)
    else:
        try:
            creds = Credentials(
                token=None,
                refresh_token=os.environ["GDRIVE_REFRESH_TOKEN"],
                client_id=os.environ["GDRIVE_CLIENT_ID"],
                client_secret=os.environ["GDRIVE_CLIENT_SECRET"],
                token_uri="https://oauth2.googleapis.com/token",
                scopes=SCOPES,
            )
        except KeyError as e:
            sys.exit(f"Missing environment variable {e}. See the docstring at the top of this script.")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def q_escape(name):
    return name.replace("\\", "\\\\").replace("'", "\\'")


def list_children(svc, parent_id):
    """Return {name: file} for everything directly inside parent_id."""
    children, token = {}, None
    while True:
        resp = svc.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, md5Checksum)",
            pageSize=1000, pageToken=token, **LIST_KW,
        ).execute()
        for f in resp.get("files", []):
            children[f["name"]] = f
        token = resp.get("nextPageToken")
        if not token:
            return children


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sync_dir(svc, local, parent_id, args, rel=""):
    existing = list_children(svc, parent_id)
    seen = set()
    for item in sorted(local.iterdir()):
        if item.name.startswith("."):
            continue
        seen.add(item.name)
        path = f"{rel}/{item.name}"
        remote = existing.get(item.name)

        if item.is_dir():
            if remote is None:
                print(f"[mkdir]  {path}")
                if args.dry_run:
                    continue
                remote = svc.files().create(
                    body={"name": item.name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
                    fields="id", supportsAllDrives=True,
                ).execute()
            sync_dir(svc, item, remote["id"], args, path)
            continue

        media = None if args.dry_run else MediaFileUpload(str(item), resumable=True)
        if remote is None:
            print(f"[upload] {path}")
            if media:
                svc.files().create(body={"name": item.name, "parents": [parent_id]},
                                   media_body=media, fields="id", supportsAllDrives=True).execute()
        elif remote.get("md5Checksum") != md5(item):
            print(f"[update] {path}")
            if media:
                # Updating in place keeps the same file ID, so shared links keep working.
                svc.files().update(fileId=remote["id"], media_body=media, supportsAllDrives=True).execute()
        else:
            print(f"[same]   {path}")

    if args.prune:
        for name, f in existing.items():
            if name not in seen:
                print(f"[trash]  {rel}/{name}")
                if not args.dry_run:
                    svc.files().update(fileId=f["id"], body={"trashed": True}, supportsAllDrives=True).execute()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--local", default="dist", help="local folder to upload (default: dist)")
    ap.add_argument("--root", default=os.environ.get("GDRIVE_ROOT_FOLDER_ID"), help="Drive folder ID")
    ap.add_argument("--prune", action="store_true", help="move Drive files that no longer exist locally to trash")
    ap.add_argument("--dry-run", action="store_true", help="show what would change without changing anything")
    args = ap.parse_args()

    if not args.root:
        sys.exit("Set GDRIVE_ROOT_FOLDER_ID or pass --root.")
    local = Path(args.local)
    if not local.is_dir():
        sys.exit(f"{local} does not exist. Run scripts/build_chapters.py first.")

    sync_dir(get_service(), local, args.root, args)
    print("Sync complete.")


if __name__ == "__main__":
    main()
