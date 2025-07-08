import os
import json
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send"
]

CLIENT_SECRETS_FILE = "credentials.json"

REDIRECT_URI = "https://evernote-ai.netlify.app/oauth2callback"

def get_auth_url():
    """Generate Google OAuth authorization URL"""
    try:
        if not os.path.exists(CLIENT_SECRETS_FILE):
            raise FileNotFoundError(f"Client secrets file not found: {CLIENT_SECRETS_FILE}")
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        auth_url, _ = flow.authorization_url(
            prompt='consent',
            access_type='offline',
            include_granted_scopes='true'
        )
        
        logger.info(f"Generated auth URL: {auth_url}")
        return auth_url
        
    except Exception as e:
        logger.error(f"Error generating auth URL: {str(e)}")
        raise

def exchange_code(code):
    """Exchange authorization code for credentials"""
    try:
        if not os.path.exists(CLIENT_SECRETS_FILE):
            raise FileNotFoundError(f"Client secrets file not found: {CLIENT_SECRETS_FILE}")
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        # Save credentials to file
        save_credentials(creds)
        
        logger.info("Successfully exchanged code for credentials")
        return creds
        
    except Exception as e:
        logger.error(f"Error exchanging code: {str(e)}")
        raise

def save_credentials(creds):
    """Save credentials to token.json file"""
    try:
        with open("token.json", "w") as token_file:
            token_file.write(creds.to_json())
        logger.info("Credentials saved to token.json")
    except Exception as e:
        logger.error(f"Error saving credentials: {str(e)}")
        raise

def get_credentials():
    """Get valid credentials from token.json file"""
    try:
        creds = None
        
        # Load existing credentials
        if os.path.exists("token.json"):
            try:
                creds = Credentials.from_authorized_user_file("token.json", SCOPES)
                logger.info("Loaded credentials from token.json")
            except Exception as e:
                logger.error(f"Error loading credentials: {str(e)}")
                return None
        
        # If credentials exist but are expired, try to refresh
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired credentials")
                creds.refresh(Request())
                save_credentials(creds)
                logger.info("Credentials refreshed successfully")
            except RefreshError as e:
                logger.error(f"Failed to refresh credentials: {str(e)}")
                # Delete invalid token file
                if os.path.exists("token.json"):
                    os.remove("token.json")
                return None
            except Exception as e:
                logger.error(f"Error refreshing credentials: {str(e)}")
                return None
        
        # Return credentials if valid
        if creds and creds.valid:
            logger.info("Credentials are valid")
            return creds
        else:
            logger.info("No valid credentials found")
            return None
            
    except Exception as e:
        logger.error(f"Error getting credentials: {str(e)}")
        return None

def revoke_credentials():
    """Revoke and delete stored credentials"""
    try:
        creds = get_credentials()
        if creds:
            # Revoke the credentials
            creds.revoke(Request())
            logger.info("Credentials revoked")
        
        # Delete token file
        if os.path.exists("token.json"):
            os.remove("token.json")
            logger.info("Token file deleted")
            
    except Exception as e:
        logger.error(f"Error revoking credentials: {str(e)}")
        raise

def is_authenticated():
    """Check if user is currently authenticated"""
    creds = get_credentials()
    return creds is not None and creds.valid