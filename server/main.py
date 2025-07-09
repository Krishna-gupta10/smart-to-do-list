from fastapi import FastAPI, HTTPException, Request, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import re, json, os, secrets
from datetime import datetime, timedelta
import logging
import jwt
from typing import Optional

from utils.gemini import call_gemini
from utils.google_auth import get_credentials_from_token, get_auth_url, exchange_code
from googleapiclient.discovery import build
from utils.calendar_task import (
    create_calendar_event,
    check_schedule,
    check_availability
)
from utils.gmail_task import summarize_emails, send_email, list_unread, search_email

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    logger.warning("SECRET_KEY not found in environment variables. Using a temporary key.")
    SECRET_KEY = secrets.token_hex(32)

JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://evernote-ai.netlify.app", "http://localhost:5173", "https://smart-to-do-list-yy8z.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TaskInput(BaseModel):
    task: str

class AuthCodeInput(BaseModel):
    code: str

def create_jwt_token(credentials_json: str) -> str:
    """Create JWT token containing credentials"""
    payload = {
        "credentials": credentials_json,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

def verify_jwt_token(token: str) -> Optional[str]:
    """Verify JWT token and return credentials JSON"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload.get("credentials")
    except jwt.ExpiredSignatureError:
        logger.info("JWT token expired")
        return None
    except jwt.InvalidTokenError:
        logger.info("Invalid JWT token")
        return None

def get_credentials_from_request(request: Request) -> Optional:
    """Get credentials from JWT token in request"""
    # Try to get token from cookie
    auth_token = request.cookies.get("auth_token")
    
    if not auth_token:
        # Try to get from Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header.split(" ")[1]
    
    if not auth_token:
        return None
    
    credentials_json = verify_jwt_token(auth_token)
    if not credentials_json:
        return None
    
    return get_credentials_from_token(credentials_json)

@app.get("/authorize")
def authorize(request: Request):
    """Get Google OAuth authorization URL"""
    try:
        origin = request.query_params.get("origin")
        auth_url, state = get_auth_url(origin=origin)
        
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get auth URL: {str(e)}")

@app.get("/oauth2callback")
def oauth2callback_get(request: Request):
    """Handle OAuth callback, exchange code, and close the popup."""
    code = request.query_params.get('code')
    error = request.query_params.get('error')
    origin = request.query_params.get('origin')

    logger.info(f"OAuth callback received: code={code is not None}, error={error}, origin={origin}")

    if error:
        logger.error(f"OAuth error from Google: {error}")
        html_response_content = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Authentication Error</title></head>
        <body>
            <script>
                const message = {{
                    type: 'oauth_error',
                    authorized: 'false',
                    error: '{error}'
                }};
                if (window.opener) {{
                    window.opener.postMessage(message, "*");
                }}
                window.close();
            </script>
            <p>Authentication failed: {error}</p>
        </body>
        </html>
        """
        return HTMLResponse(content=html_response_content)

    if not code:
        logger.error("No authorization code received.")
        return HTMLResponse(content="<html><body>Error: No authorization code received.</body></html>", status_code=400)

    try:
        logger.info("Exchanging authorization code for credentials...")
        creds = exchange_code(code, origin)
        
        # Create JWT token
        jwt_token = create_jwt_token(creds.to_json())
        
        html_response_content = """
        <!DOCTYPE html>
        <html>
        <head><title>Authentication Complete</title></head>
        <body>
            <script>
                const message = {
                    type: 'oauth_success',
                    authorized: 'true'
                };
                if (window.opener) {
                    window.opener.postMessage(message, "*");
                }
                window.close();
            </script>
            <p>Authentication successful. You can close this window.</p>
        </body>
        </html>
        """
        
        response = HTMLResponse(content=html_response_content)
        response.set_cookie(
            "auth_token",
            jwt_token,
            max_age=JWT_EXPIRATION_HOURS * 3600,  # Convert hours to seconds
            httponly=True,
            secure=True,
            samesite="lax"
        )
        
        logger.info("JWT token created and set in cookie successfully.")
        return response

    except Exception as e:
        logger.error(f"Failed to exchange code for credentials: {str(e)}")
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Authentication Error</title></head>
        <body>
            <script>
                const message = {{
                    type: 'oauth_error',
                    authorized: 'false',
                    error: 'token_exchange_failed',
                    details: '{str(e)}'
                }};
                if (window.opener) {{
                    window.opener.postMessage(message, "*");
                }}
                window.close();
            </script>
            <p>Authentication failed: {str(e)}</p>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=400)

@app.post("/oauth2callback")
def oauth2callback_post(request: Request, data: AuthCodeInput):
    """Handle OAuth callback with authorization code (POST request)"""
    try:
        creds = exchange_code(data.code, None)
        
        # Create JWT token
        jwt_token = create_jwt_token(creds.to_json())
        
        return {
            "message": "Authorization successful",
            "authorized": True,
            "token": jwt_token
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authorization failed: {str(e)}")

@app.get("/check-auth")
def check_auth(request: Request):
    """Check if user is authenticated"""
    try:
        creds = get_credentials_from_request(request)
        if not creds or not creds.valid:
            return {"authorized": False, "error": "Invalid credentials"}

        # Fetch user info
        service = build('oauth2', 'v2', credentials=creds)
        user_info = service.userinfo().get().execute()
        
        return {
            "authorized": True,
            "name": user_info.get("name"),
            "email": user_info.get("email"),
            "picture": user_info.get("picture")
        }
    except Exception as e:
        logger.error(f"Error checking auth: {str(e)}")
        return {"authorized": False, "error": str(e)}

@app.post("/logout")
def logout(request: Request):
    """Logout user and clear auth token"""
    try:
        response = {"message": "Logged out successfully"}
        
        # Create response and clear the cookie
        from fastapi.responses import JSONResponse
        json_response = JSONResponse(content=response)
        json_response.delete_cookie("auth_token")
        
        return json_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Logout failed: {str(e)}")

@app.post("/parse-and-execute")
def parse_and_execute(request: Request, data: TaskInput):
    """Parse natural language task and execute appropriate action"""
    # Check if user is authenticated first
    try:
        creds = get_credentials_from_request(request)
        if not creds or not creds.valid:
            raise HTTPException(status_code=401, detail="User not authenticated. Please authorize with Google first.")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Authentication required. Please authorize with Google first.")

    try:
        raw_response = call_gemini(data.task)
        print(f"Raw response from Gemini: {raw_response}")

        # Check if Gemini responded with a JSON task
        if "{" in raw_response:
            try:
                # Extract JSON string from the raw response
                match = re.search(r"\{.*\}", raw_response, re.DOTALL)
                if not match:
                    # Fallback if no JSON is found
                    return {"status": "Processed ✅", "message": raw_response}

                json_str = match.group(0)
                parsed = json.loads(json_str)

                if parsed.get("missing_fields"):
                    # Properly format the list of missing fields
                    missing_fields_str = ', '.join(parsed['missing_fields'])
                    return {
                        "status": "Need Info ❓",
                        "message": f"To proceed, I need: {missing_fields_str}.",
                        "parsed": parsed
                    }
                
                # 1. Schedule Call
                if parsed["action"] == "schedule_call":
                    event_link = create_calendar_event(
                        creds,
                        parsed.get("person", "someone"),
                        parsed["date_time"],
                        parsed.get("email"),
                        parsed.get("repeat", "none")
                    )

                    dt = datetime.fromisoformat(parsed["date_time"])
                    formatted_time = dt.strftime("%I:%M %p on %B %d")
                    person = parsed.get("person", "someone")
                    email = parsed.get("email", None)

                    message = f"✅ Scheduled a 30-minute call with {person} at {formatted_time}."
                    if email:
                        message += f" Invite sent to {email}."

                    return {
                        "status": "Scheduled ✅",
                        "event": event_link,
                        "parsed": parsed,
                        "message": message
                    }

                # 2. Check Schedule
                elif parsed["action"] == "check_schedule":
                    schedule = check_schedule(creds, parsed["date_time"])
                    return {
                        "status": "Schedule ✅",
                        "events": schedule,
                        "parsed": parsed
                    }

                # 3. Check Availability
                elif parsed["action"] == "check_availability":
                    free_slots = check_availability(creds, parsed["date_time"])
                    return {
                        "status": "Free Slots ✅",
                        "slots": free_slots,
                        "parsed": parsed
                    }

                # 4. Summarize Emails
                elif parsed["action"] == "summarize_emails":
                    emails = summarize_emails(
                        creds,
                        parsed.get("date_time"),
                        parsed.get("query")
                    )
                    return {
                        "status": "Summary ✅",
                        "emails": emails,
                        "parsed": parsed
                    }

                # 5. Send Email
                elif parsed["action"] == "send_email":
                    result = send_email(creds, parsed["email"], parsed["subject"], parsed["body"])
                    return {
                        "status": "Email Sent ✅",
                        "result": result,
                        "parsed": parsed
                    }

                # 6. List Unread Emails
                elif parsed["action"] == "list_unread":
                    emails = list_unread(creds, parsed["date_time"])
                    return {
                        "status": "Unread ✅",
                        "emails": emails,
                        "parsed": parsed
                    }

                # 7. Search Email
                elif parsed["action"] == "search_email":
                    emails = search_email(creds, parsed["query"])
                    return {
                        "status": "Search ✅",
                        "emails": emails,
                        "parsed": parsed
                    }

            except (json.JSONDecodeError, KeyError) as e:
                # Fallback for parsing errors
                return {"status": "Error ❌", "error": f"Failed to parse action: {e}"}
        
        else:
            # Fallback for non-JSON responses
            return {"status": "Message 💬", "message": raw_response}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    """Root endpoint"""
    return {"message": "Smart To-Do List API is running"}

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}