from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import re, json, os
from datetime import datetime

from utils.gemini import call_gemini
from utils.google_auth import get_credentials, get_auth_url, exchange_code
from utils.calendar_task import (
    create_calendar_event,
    check_schedule,
    check_availability
)
from utils.gmail_task import summarize_emails, send_email, list_unread, search_email

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add session middleware for OAuth state management
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key-change-this-in-production"
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

@app.get("/oauth2callback")
def oauth2callback_get(request: Request):
    """Handle OAuth callback with authorization code (GET request)"""
    try:
        # Get state from session
        auth_state = request.session.get("auth_state")
        print(f"Debug: auth_state from session: {auth_state}")
        
        # Get origin from state
        origin = auth_state.get("origin") if auth_state else "https://smart-to-do-list-4bi2.onrender.com"
        print(f"Debug: using origin: {origin}")
        
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        print(f"Debug: received code: {code is not None}, error: {error}")
        
        if error:
            # Return error page that notifies parent
            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authorization Error</title>
            </head>
            <body>
                <script>
                    // Notify parent window about the error
                    if (window.opener) {{
                        window.opener.postMessage({{ 
                            type: 'oauth_error', 
                            error: '{error}' 
                        }}, '{origin}');
                    }}
                    window.close();
                </script>
            </body>
            </html>
            """)
        
        if not code:
            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authorization Error</title>
            </head>
            <body>
                <script>
                    if (window.opener) {{
                        window.opener.postMessage({{ 
                            type: 'oauth_error', 
                            error: 'No authorization code received' 
                        }}, '{origin}');
                    }}
                    window.close();
                </script>
            </body>
            </html>
            """)
        
        # Exchange code for credentials
        try:
            print(f"Debug: attempting to exchange code for credentials")
            creds = exchange_code(code)
            print(f"Debug: credentials exchange successful: {creds is not None}")
            
            # Return success page that properly notifies parent and closes
            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authorization Complete</title>
            </head>
            <body>
                <script>
                    // Notify parent window with success message
                    if (window.opener && !window.opener.closed) {{
                        window.opener.postMessage({{ 
                            type: 'oauth_success',
                            data: {{ authorized: true }}
                        }}, '{origin}');
                    }}
                    window.close();
                </script>
            </body>
            </html>
            """)
            
        except Exception as auth_error:
            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authorization Error</title>
            </head>
            <body>
                <script>
                    // Notify parent window about the error
                    if (window.opener) {{
                        window.opener.postMessage({{ 
                            type: 'oauth_error', 
                            error: 'Authentication failed: {str(auth_error)}' 
                        }}, '{origin}');
                    }}
                    window.close();
                </script>
            </body>
            </html>
            """)
        
    except Exception as e:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authorization Error</title>
        </head>
        <body>
            <script>
                // Notify parent window about the error
                if (window.opener) {{
                    window.opener.postMessage({{ 
                        type: 'oauth_error', 
                        error: 'Unexpected error: {str(e)}' 
                    }}, 'https://smart-to-do-list-4bi2.onrender.com');
                }}
                window.close();
            </script>
        </body>
        </html>
        """)

# Keep your existing POST endpoint for API calls
@app.post("/oauth2callback")
def oauth2callback_post(data: AuthCodeInput):
    """Handle OAuth callback with authorization code (POST request)"""
    try:
        creds = exchange_code(data.code)
        return {
            "message": "Authorization successful",
            "authorized": True
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authorization failed: {str(e)}")

@app.get("/check-auth")
def check_auth():
    """Check if user is authenticated"""
    try:
        creds = get_credentials()
        return {"authorized": creds is not None and creds.valid}
    except Exception as e:
        return {"authorized": False, "error": str(e)}

@app.post("/parse-and-execute")
def parse_and_execute(data: TaskInput):
    """Parse natural language task and execute appropriate action"""
    # Check if user is authenticated first
    try:
        creds = get_credentials()
        if not creds or not creds.valid:
            raise HTTPException(status_code=401, detail="User not authenticated. Please authorize with Google first.")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Authentication required. Please authorize with Google first.")

    try:
        raw_response = call_gemini(data.task)

        # Check if Gemini responded with a JSON task
        if "{" in raw_response:
            try:
                json_str = re.search(r"\{.*\}", raw_response, re.DOTALL)[0]
                parsed = json.loads(json_str)
                
                if parsed.get("missing_fields"):
                    return {
                        "status": "Need Info ❓",
                        "message": f"To proceed, I need: {', '.join(parsed['missing_fields'])}.",
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

                # 7. Search Emails
                elif parsed["action"] == "search_email":
                    matches = search_email(creds, parsed["query"])
                    return {
                        "status": "Results ✅",
                        "emails": matches,
                        "parsed": parsed
                    }

                else:
                    return {
                        "status": "Parsed only",
                        "parsed": parsed,
                        "note": "Execution for this action not yet implemented"
                    }

            except json.JSONDecodeError as e:
                return {
                    "status": "Parse Error",
                    "error": f"Failed to parse JSON: {str(e)}",
                    "raw": raw_response
                }
            except Exception as e:
                return {
                    "status": "Execution Error",
                    "error": str(e),
                    "raw": raw_response
                }

        # If response wasn't JSON, return it as a general message
        return {
            "status": "Message 💬",
            "message": raw_response
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing task: {str(e)}")

@app.get("/")
def root():
    """Root endpoint"""
    return {"message": "Smart To-Do List API is running"}

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}