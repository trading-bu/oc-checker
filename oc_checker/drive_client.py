"""
Google Drive client for the OC checker.

Reads PDF files from the "OC Inbox" Drive folder and moves them to
"OC Processed" when done, creating "OC Processed" if it doesn't exist.

Authentication:
  Expects a JSON string in the GOOGLE_CREDENTIALS environment variable.
  This is the content of a credentials.json file from an OAuth2 flow
  (run setup_google_auth.py once locally to generate it).

Environment variables:
  GOOGLE_CREDENTIALS  — full JSON content of the credentials file
  DRIVE_INBOX_NAME    — optional, defaults to "OC Inbox"
  DRIVE_PROCESSED_NAME — optional, defaults to "OC Processed"
"""

import os
import json
import io
import urllib.request
import urllib.parse


# ---------------------------------------------------------------------------
# Folder name config
# ---------------------------------------------------------------------------

INBOX_FOLDER_NAME     = os.environ.get("DRIVE_INBOX_NAME",     "OC Inbox")
PROCESSED_FOLDER_NAME = os.environ.get("DRIVE_PROCESSED_NAME", "OC Processed")

DRIVE_API  = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"

SCOPES = ["https://www.googleapis.com/auth/drive"]


# ---------------------------------------------------------------------------
# Minimal OAuth2 token refresh (no external library required)
# ---------------------------------------------------------------------------

class _Token:
    """Holds an access token and refreshes it when needed."""

    def __init__(self, creds: dict):
        self._client_id     = creds.get("client_id", "")
        self._client_secret = creds.get("client_secret", "")
        self._refresh_token = creds.get("refresh_token", "")
        self._access_token  = creds.get("token", "")
        self._token_uri     = creds.get("token_uri", "https://oauth2.googleapis.com/token")

    def get(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        if not self._access_token:
            self._refresh()
        return self._access_token

    def _refresh(self):
        if not self._refresh_token:
            raise RuntimeError(
                "No refresh_token in GOOGLE_CREDENTIALS. "
                "Run setup_google_auth.py to re-authorise."
            )
        payload = urllib.parse.urlencode({
            "client_id":     self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
            "grant_type":    "refresh_token",
        }).encode("utf-8")
        req = urllib.request.Request(
            self._token_uri, data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
        if "access_token" not in body:
            raise RuntimeError("Token refresh failed: %s" % body)
        self._access_token = body["access_token"]


def _load_token() -> _Token:
    raw = os.environ.get("GOOGLE_CREDENTIALS", "")
    if not raw:
        raise RuntimeError("GOOGLE_CREDENTIALS environment variable not set.")
    try:
        creds = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError("GOOGLE_CREDENTIALS is not valid JSON: %s" % e)
    return _Token(creds)


# ---------------------------------------------------------------------------
# Drive API helpers
# ---------------------------------------------------------------------------

def _api(token: _Token, method: str, url: str, params: dict = None,
         body: dict = None) -> dict:
    """Make a Drive API call. Returns parsed JSON."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {
        "Authorization": "Bearer " + token.get(),
        "Accept": "application/json",
    }
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _download(token: _Token, file_id: str) -> bytes:
    """Download the binary content of a Drive file."""
    url = "%s/files/%s?alt=media" % (DRIVE_API, file_id)
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + token.get()}, method="GET"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


# ---------------------------------------------------------------------------
# Folder lookup / creation
# ---------------------------------------------------------------------------

def _find_folder(token: _Token, name: str) -> str | None:
    """Return the Drive folder ID for a given name, or None if not found."""
    result = _api(token, "GET", DRIVE_API + "/files", params={
        "q":      "mimeType='application/vnd.google-apps.folder' "
                  "and name='%s' and trashed=false" % name.replace("'", "\\'"),
        "fields": "files(id, name)",
        "spaces": "drive",
    })
    files = result.get("files", [])
    return files[0]["id"] if files else None


def _get_or_create_folder(token: _Token, name: str) -> str:
    """Return (or create) a Drive folder and return its ID."""
    folder_id = _find_folder(token, name)
    if folder_id:
        return folder_id
    print("  Creating Drive folder: %s" % name)
    result = _api(token, "POST", DRIVE_API + "/files", body={
        "name":     name,
        "mimeType": "application/vnd.google-apps.folder",
    })
    return result["id"]


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def list_new_pdfs() -> list[dict]:
    """
    List PDF files in the "OC Inbox" Drive folder.

    Returns a list of dicts:
        { "id": str, "title": str, "status": "inbox", "created_at": str }
    """
    token     = _load_token()
    folder_id = _find_folder(token, INBOX_FOLDER_NAME)

    if not folder_id:
        print("  Drive folder '%s' not found — nothing to process." % INBOX_FOLDER_NAME)
        return []

    result = _api(token, "GET", DRIVE_API + "/files", params={
        "q":      "'%s' in parents and mimeType='application/pdf' and trashed=false" % folder_id,
        "fields": "files(id, name, createdTime)",
        "orderBy": "createdTime",
    })

    files = result.get("files", [])
    print("  Drive '%s': %d PDF(s) found" % (INBOX_FOLDER_NAME, len(files)))
    return [
        {
            "id":         f["id"],
            "title":      f.get("name", f["id"]),
            "status":     "inbox",
            "created_at": f.get("createdTime", ""),
        }
        for f in files
    ]


def download_pdf(file_id: str) -> bytes:
    """Download a PDF file from Drive by its file ID. Returns raw bytes."""
    token = _load_token()
    return _download(token, file_id)


def mark_processed(file_id: str):
    """
    Move a Drive file from "OC Inbox" to "OC Processed".
    Preserves the file — just changes the parent folder.
    """
    token        = _load_token()
    inbox_id     = _find_folder(token, INBOX_FOLDER_NAME)
    processed_id = _get_or_create_folder(token, PROCESSED_FOLDER_NAME)

    _api(token, "PATCH",
         "%s/files/%s" % (DRIVE_API, file_id),
         params={
             "addParents":    processed_id,
             "removeParents": inbox_id or "",
             "fields":        "id, parents",
         })
    print("  Moved to '%s': %s" % (PROCESSED_FOLDER_NAME, file_id))


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Listing Drive inbox...")
    docs = list_new_pdfs()
    for d in docs:
        print("  %(id)s | %(title)s | %(created_at)s" % d)
    print("Total: %d file(s)" % len(docs))
