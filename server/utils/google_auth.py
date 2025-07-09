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
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email"
]

CLIENT_SECRETS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

REDIRECT_URI = "https://smart-to-do-list-4bi2.onrender.com/oauth2callback"

def get_auth_url(origin: str = None):
    """Generate Google OAuth authorization URL"""
    try:
        if not os.path.exists(CLIENT_SECRETS_FILE):
            raise FileNotFoundError(f"Client secrets file not found: {CLIENT_SECRETS_FILE}")
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        auth_url, state = flow.authorization_url(
            prompt='consent',
            access_type='offline',
            include_granted_scopes='true'
        )
        
        # State will be handled by session middleware in main.py
        
        logger.info(f"Generated auth URL: {auth_url}")
        return auth_url, state
        
    except Exception as e:
        logger.error(f"Error generating auth URL: {str(e)}")
        raise

def exchange_code(code):
    """Exchange authorization code for credentials"""
    try:
        logger.info(f"Exchanging code for credentials...")
        
        if not os.path.exists(CLIENT_SECRETS_FILE):
            raise FileNotFoundError(f"Client secrets file not found: {CLIENT_SECRETS_FILE}")
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        logger.info("Fetching token...")
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        logger.info("Token fetched successfully")
        
        # Verify credentials are valid
        if not creds or not creds.valid:
            raise Exception("Invalid credentials received")
        
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
        logger.info("Saving credentials...")
        
        # Create backup if existing file exists
        if os.path.exists(TOKEN_FILE):
            backup_file = f"{TOKEN_FILE}.backup"
            os.rename(TOKEN_FILE, backup_file)
            logger.info(f"Created backup: {backup_file}")
        
        with open(TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())
            
        logger.info(f"Credentials saved to {TOKEN_FILE}")
        
        # Verify the saved file
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "r") as token_file:
                saved_data = json.load(token_file)
                logger.info(f"Saved credentials contain: {list(saved_data.keys())}")
        
    except Exception as e:
        logger.error(f"Error saving credentials: {str(e)}")
        raise

def get_credentials():
    """Get valid credentials from token.json file"""
    try:
        logger.info("Getting credentials...")
        creds = None
        
        # Load existing credentials
        if os.path.exists(TOKEN_FILE):
            try:
                logger.info(f"Loading credentials from {TOKEN_FILE}")
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                logger.info("Credentials loaded successfully")
                
                # Log credential status
                logger.info(f"Credentials valid: {creds.valid}")
                logger.info(f"Credentials expired: {creds.expired}")
                logger.info(f"Has refresh token: {creds.refresh_token is not None}")
                
            except Exception as e:
                logger.error(f"Error loading credentials: {str(e)}")
                return None
        else:
            logger.info(f"No token file found at {TOKEN_FILE}")
            return None
        
        # If credentials exist but are expired, try to refresh
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired credentials...")
                creds.refresh(Request())
                save_credentials(creds)
                logger.info("Credentials refreshed successfully")
            except RefreshError as e:
                logger.error(f"Failed to refresh credentials: {str(e)}")
                # Delete invalid token file
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                    logger.info("Deleted invalid token file")
                return None
            except Exception as e:
                logger.error(f"Error refreshing credentials: {str(e)}")
                return None
        
        # Return credentials if valid
        if creds and creds.valid:
            logger.info("Credentials are valid and ready to use")
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
        logger.info("Revoking credentials...")
        creds = get_credentials()
        if creds:
            # Revoke the credentials
            creds.revoke(Request())
            logger.info("Credentials revoked")
        
        # Delete token file
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            logger.info("Token file deleted")
            
    except Exception as e:
        logger.error(f"Error revoking credentials: {str(e)}")
        raise

def is_authenticated():
    """Check if user is currently authenticated"""
    try:
        creds = get_credentials()
        is_auth = creds is not None and creds.valid
        logger.info(f"User authenticated: {is_auth}")
        return is_auth
    except Exception as e:
        logger.error(f"Error checking authentication: {str(e)}")
        return False