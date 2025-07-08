import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
]

def authorize_user():
    """Authorize user and save credentials"""
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=8080)
    
    # Save credentials
    with open('token.json', 'w') as token_file:
        token_file.write(creds.to_json())
    
    return {"message": "Authorized ✅"}

def get_credentials():
    """Get valid credentials, refreshing if necessary"""
    creds = None
    
    # Load existing credentials
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If there are no valid credentials, return None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Save refreshed credentials
                with open('token.json', 'w') as token_file:
                    token_file.write(creds.to_json())
            except Exception as e:
                # If refresh fails, return None so user needs to re-authorize
                return None
        else:
            return None
    
    return creds