import os
import json
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
import logging
from dotenv import load_dotenv

load_dotenv()

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
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
REDIRECT_URI = f"{API_BASE_URL}/oauth2callback"

def get_auth_url(origin: str):
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
        
        logger.info(f"Generated auth URL: {auth_url}")
        return auth_url, state
        
    except Exception as e:
        logger.error(f"Error generating auth URL: {str(e)}")
        raise

def exchange_code(code, origin: str):
    """Exchange authorization code for credentials"""
    try:
        logger.info(f"Exchanging code for credentials... Code: {code[:10]}..., Origin: {origin}")

        if not os.path.exists(CLIENT_SECRETS_FILE):
            raise FileNotFoundError(f"Client secrets file not found: {CLIENT_SECRETS_FILE}")

        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )

        logger.info(f"Attempting to fetch token with redirect_uri: {REDIRECT_URI}")
        try:
            flow.fetch_token(code=code)
        except Exception as e:
            logger.error(f"Error during flow.fetch_token(): {str(e)}")
            raise

        creds = flow.credentials

        logger.info(f"Token fetched. Credentials valid: {creds.valid}, expired: {creds.expired}")

        if not creds or not creds.valid:
            raise Exception("Invalid credentials received after token fetch")

        logger.info("Successfully exchanged code for credentials")
        return creds

    except Exception as e:
        logger.error(f"Error exchanging code: {str(e)}")
        raise

def get_credentials_from_token(credentials_json: str):
    """Get valid credentials from JSON string (for JWT usage)"""
    try:
        logger.info("Getting credentials from token...")
        
        if not credentials_json:
            logger.info("No credentials JSON provided")
            return None

        logger.info("Credentials JSON found. Attempting to load...")
        creds = Credentials.from_authorized_user_info(json.loads(credentials_json), SCOPES)

        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired credentials...")
                creds.refresh(Request())
                logger.info("Credentials refreshed successfully")
            except RefreshError as e:
                logger.error(f"Failed to refresh credentials: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"Error refreshing credentials: {str(e)}")
                return None

        if creds and creds.valid:
            logger.info("Credentials are valid")
            return creds
        else:
            logger.info("No valid credentials found after check/refresh")
            return None

    except Exception as e:
        logger.error(f"Error getting credentials from token: {str(e)}")
        return None

# Keep the old function for backward compatibility (though it won't work with JWT)
def get_credentials(session):
    """Get valid credentials from session - DEPRECATED for JWT implementation"""
    logger.warning("get_credentials(session) is deprecated. Use get_credentials_from_token() instead.")
    try:
        logger.info("Getting credentials from session...")
        creds_json = session.get("credentials")

        if not creds_json:
            logger.info("No credentials found in session")
            return None

        logger.info("Credentials found in session. Attempting to load...")
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
            logger.info("No valid credentials found in session after check/refresh")
            return None

    except Exception as e:
        logger.error(f"Error getting credentials from session: {str(e)}")
        return None