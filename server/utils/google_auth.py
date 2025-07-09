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
    "openid",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
]

CLIENT_SECRETS_FILE = "credentials.json"

def get_auth_url(origin: str):
    """Generate Google OAuth authorization URL"""
    try:
        if not os.path.exists(CLIENT_SECRETS_FILE):
            raise FileNotFoundError(f"Client secrets file not found: {CLIENT_SECRETS_FILE}")
        
        # TODO: Use a more dynamic way to set the redirect_uri for production
        redirect_uri = f"http://localhost:8000/oauth2callback"
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        
        auth_url, state = flow.authorization_url(
            prompt='consent',
            access_type='offline',
            include_granted_scopes='true'
        )
        
        logger.info(f"Generated auth URL: {auth_url}")
        return auth_url, state
        
    except Exception as e:
        logger.error(f"Error generating auth URL: {str(e)}")
        raise

def exchange_code(code, origin: str):
    """Exchange authorization code for credentials"""
    try:
        logger.info(f"Exchanging code for credentials...")
        
        if not os.path.exists(CLIENT_SECRETS_FILE):
            raise FileNotFoundError(f"Client secrets file not found: {CLIENT_SECRETS_FILE}")
        
        # TODO: Use a more dynamic way to set the redirect_uri for production
        redirect_uri = f"http://localhost:8000/oauth2callback"
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        
        logger.info("Fetching token...")
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        logger.info("Token fetched successfully")
        
        if not creds or not creds.valid:
            raise Exception("Invalid credentials received")
        
        logger.info("Successfully exchanged code for credentials")
        return creds
        
    except Exception as e:
        logger.error(f"Error exchanging code: {str(e)}")
        raise

def get_credentials(session):
    """Get valid credentials from session"""
    try:
        logger.info("Getting credentials from session...")
        creds_json = session.get("credentials")
        
        if not creds_json:
            logger.info("No credentials found in session")
            return None
            
        creds = Credentials.from_authorized_user_info(json.loads(creds_json), SCOPES)
        
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired credentials...")
                creds.refresh(Request())
                session["credentials"] = creds.to_json()
                logger.info("Credentials refreshed and updated in session")
            except RefreshError as e:
                logger.error(f"Failed to refresh credentials: {str(e)}")
                session.pop("credentials", None)
                return None
            except Exception as e:
                logger.error(f"Error refreshing credentials: {str(e)}")
                return None
        
        if creds and creds.valid:
            logger.info("Credentials are valid")
            return creds
        else:
            logger.info("No valid credentials found in session")
            return None
            
    except Exception as e:
        logger.error(f"Error getting credentials from session: {str(e)}")
        return None
