import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


def get_drive_service():
    """
    Authenticate with Google Drive.
    """

    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE,
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build(
        "drive",
        "v3",
        credentials=creds
    )


def make_public(service, file_id):
    """
    Make a Google Drive file publicly readable.
    """

    service.permissions().create(
        fileId=file_id,
        body={
            "type": "anyone",
            "role": "reader"
        }
    ).execute()


def get_public_url(file_id):
    """
    Return a public Google Drive URL.
    """

    return f"https://drive.google.com/file/d/{file_id}/view"


def find_existing_file(service, filename):
    """
    Search Google Drive for an existing file with the same name.
    """

    results = service.files().list(
        q=f"name='{filename}' and trashed=false",
        fields="files(id,name)"
    ).execute()

    files = results.get("files", [])

    if files:
        return files[0]["id"]

    return None


def upload_to_drive(file_path):
    """
    Upload a PDF to Google Drive.

    If the file already exists, return its URL instead of uploading again.
    """

    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    service = get_drive_service()

    filename = os.path.basename(file_path)

    # -------------------------
    # Check existing file
    # -------------------------

    existing_id = find_existing_file(
        service,
        filename
    )

    if existing_id:

        print("✓ Already exists on Drive")

        return get_public_url(existing_id)

    # -------------------------
    # Upload
    # -------------------------

    media = MediaFileUpload(
        file_path,
        mimetype="application/pdf"
    )

    uploaded = service.files().create(
        body={
            "name": filename
        },
        media_body=media,
        fields="id"
    ).execute()

    file_id = uploaded["id"]

    make_public(service, file_id)

    print("✓ Uploaded to Drive")

    return get_public_url(file_id)