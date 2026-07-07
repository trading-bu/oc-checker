"""
One-time Google OAuth2 setup script.

Run this ONCE on your local machine to authorise the OC checker to access
your Google Drive. It will open a browser window, ask you to sign in, and
save a credentials.json file. The content of that file becomes the
GOOGLE_CREDENTIALS GitHub Secret.

Requirements:
  pip install google-auth-oauthlib google-api-python-client

Steps:
  1. Go to https://console.cloud.google.com/
  2. Create a project (or use an existing one)
  3. Enable the Google Drive API
  4. Go to APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID
  5. Application type: Desktop app
  6. Download the client_secret JSON file → save it as client_secret.json in this folder
  7. Run: python setup_google_auth.py
  8. Complete the browser sign-in
  9. Copy the ENTIRE content of the generated credentials.json
  10. In GitHub → repo Settings → Secrets → New secret:
      Name:  GOOGLE_CREDENTIALS
      Value: (paste the credentials.json content)
"""

import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES          = ["https://www.googleapis.com/auth/drive"]
CLIENT_SECRET   = "client_secret.json"
CREDENTIALS_OUT = "credentials.json"


def main():
    if not Path(CLIENT_SECRET).exists():
        print("ERROR: %s not found." % CLIENT_SECRET)
        print("Download it from Google Cloud Console:")
        print("  APIs & Services → Credentials → OAuth 2.0 Client ID → Download JSON")
        print("Then rename it to client_secret.json and re-run this script.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(port=0)

    # Save in the format google.oauth2.credentials.Credentials.to_json() produces
    creds_dict = {
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri":     creds.token_uri,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
        "scopes":        creds.scopes,
    }

    Path(CREDENTIALS_OUT).write_text(json.dumps(creds_dict, indent=2))
    print("\n✅ Done! credentials.json written.")
    print("\nNext step: copy the content of credentials.json to GitHub Secrets as GOOGLE_CREDENTIALS")
    print("\nContent to copy:\n")
    print(json.dumps(creds_dict))


if __name__ == "__main__":
    main()
