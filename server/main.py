from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import re, json, os, secrets
from datetime import datetime
import logging  # ADD THIS

from utils.gemini import call_gemini
from utils.google_auth import get_credentials, get_auth_url, exchange_code
from googleapiclient.discovery import build
from utils.calendar_task import (
    create_calendar_event,
    check_schedule,
    check_availability
)
from utils.gmail_task import summarize_emails, send_email, list_unread, search_email

load_dotenv()

# Set up logging - ADD THIS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Generate a secure secret key
SECRET_KEY = secrets.token_hex(32)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://smart-to-do-list-4bi2.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add session middleware for OAuth state management
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY
)

class TaskInput(BaseModel):
    task: str

class AuthCodeInput(BaseModel):
    code: str

@app.get("/authorize")
def authorize(request: Request):
    """Get Google OAuth authorization URL"""
    try:
        origin = request.query_params.get("origin")
        auth_url, state = get_auth_url(origin=origin)
        
        # Store the origin in the session with the state
        request.session["auth_state"] = {"state": state, "origin": origin}
        
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get auth URL: {str(e)}")

def create_response(origin, params):
    """Helper to create a redirect response with required headers"""
    # Always allow popups from the same origin
    headers = {"Cross-Origin-Opener-Policy": "same-origin-allow-popups"}
    # Construct URL with query parameters
    query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
    url = f"{origin}/oauth_redirect.html?{query_string}"
    return RedirectResponse(url=url, headers=headers)

@app.get("/oauth2callback")
def oauth2callback_get(request: Request):
    """Handle OAuth callback with authorization code (GET request)"""
    auth_state = request.session.get("auth_state", {})
    origin = auth_state.get("origin")

    # Fallback for origin if not in session (e.g., during development)
    if not origin:
        origin = "http://localhost:5173"  # Default to Vite dev server

    try:
        code = request.query_params.get('code')
        error = request.query_params.get('error')

        logger.info(f"oauth2callback_get received - code: {code}, error: {error}, origin: {origin}")

        if error:
            logger.error(f"OAuth error received: {error}")
            return create_response(origin, {"type": "oauth_error", "error": error})

        if not code:
            logger.error("No code received in oauth2callback")
            return create_response(origin, {"type": "oauth_error", "error": "no_code_received"})

        try:
            creds = exchange_code(code, origin)
            logger.info(f"Credentials exchanged successfully")
            request.session["credentials"] = creds.to_json()
            return create_response(origin, {"type": "oauth_success", "authorized": "true"})

        except Exception as auth_error:
            logger.error(f"Authentication failed during code exchange: {str(auth_error)}")
            return create_response(origin, {"type": "oauth_error", "error": "authentication_failed", "details": str(auth_error)})

    except Exception as e:
        logger.error(f"Unexpected error in oauth2callback_get: {str(e)}")
        return create_response(origin, {"type": "oauth_error", "error": "unexpected_error", "details": str(e)})

# Keep your existing POST endpoint for API calls
@app.post("/oauth2callback")
def oauth2callback_post(request: Request, data: AuthCodeInput):
    """Handle OAuth callback with authorization code (POST request)"""
    try:
        creds = exchange_code(data.code)
        
        # Store credentials in session
        request.session["credentials"] = creds.to_json()
        
        return {
            "message": "Authorization successful",
            "authorized": True
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authorization failed: {str(e)}")

@app.get("/check-auth")
def check_auth(request: Request):
    """Check if user is authenticated"""
    try:
        creds = get_credentials(request.session)
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
        return {"authorized": False, "error": str(e)}

@app.post("/logout")
def logout(request: Request):
    """Logout user and clear session credentials"""
    try:
        if "credentials" in request.session:
            del request.session["credentials"]
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Logout failed: {str(e)}")

@app.post("/parse-and-execute")
def parse_and_execute(request: Request, data: TaskInput):
    """Parse natural language task and execute appropriate action"""
    # Check if user is authenticated first
    try:
        creds = get_credentials(request.session)
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