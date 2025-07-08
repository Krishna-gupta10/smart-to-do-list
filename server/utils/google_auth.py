import os
import json
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send"
]

CLIENT_SECRETS_FILE = "credentials.json"

# 🔁 This should match what you registered in Google Cloud Console
REDIRECT_URI = "https://transcendent-selkie-ae3052.netlify.app/oauth2callback"

def get_auth_url():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')
    # Save flow state to use later
    with open("flow_session.json", "w") as f:
        f.write(json.dumps(flow.credentials_to_dict()))
    
    return auth_url

def exchange_code(code):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    flow.fetch_token(code=code)
    creds = flow.credentials
    
    # Save token
    with open("token.json", "w") as token_file:
        token_file.write(creds.to_json())

    return creds

def get_credentials():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open("token.json", "w") as token_file:
                token_file.write(creds.to_json())
        except Exception:
            return None

    return creds if creds and creds.valid else None
