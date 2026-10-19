#!/usr/bin/env python3
"""One-time helper: run on your own computer to get GDRIVE_REFRESH_TOKEN.

    pip install google-auth-oauthlib
    python scripts/get_refresh_token.py path/to/client_secret.json

A browser opens, you sign in with the Google account that owns the Drive
folder, and the script prints the three values to save as GitHub secrets.
"""

import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

if len(sys.argv) != 2:
    sys.exit(__doc__)

flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], ["https://www.googleapis.com/auth/drive"])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
client = json.load(open(sys.argv[1]))["installed"]

print("\nSave these as GitHub repository secrets:\n")
print(f"GDRIVE_CLIENT_ID     = {client['client_id']}")
print(f"GDRIVE_CLIENT_SECRET = {client['client_secret']}")
print(f"GDRIVE_REFRESH_TOKEN = {creds.refresh_token}")
