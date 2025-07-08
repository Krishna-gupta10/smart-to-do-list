from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
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

class TaskInput(BaseModel):
    task: str

class AuthCodeInput(BaseModel):
    code: str

@app.get("/authorize")
def authorize():
    """Get Google OAuth authorization URL"""
    try:
        auth_url = get_auth_url()
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get auth URL: {str(e)}")

@app.get("/oauth2callback")
def oauth2callback_get(request: Request):
    """Handle OAuth callback with authorization code (GET request)"""
    try:
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        
        if error:
            # Return error page that notifies parent
            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authorization Error</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .error {{ color: #e74c3c; }}
                </style>
            </head>
            <body>
                <h2 class="error">❌ Authorization Failed</h2>
                <p>Error: {error}</p>
                <p>This window will close automatically...</p>
                <script>
                    // Notify parent window about the error
                    if (window.opener) {{
                        window.opener.postMessage({{ 
                            type: 'oauth_error', 
                            error: '{error}' 
                        }}, '*');
                    }}
                    
                    // Auto-close after 3 seconds
                    setTimeout(() => {{
                        window.close();
                    }}, 3000);
                </script>
            </body>
            </html>
            """)
        
        if not code:
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authorization Error</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .error { color: #e74c3c; }
                </style>
            </head>
            <body>
                <h2 class="error">❌ Authorization Failed</h2>
                <p>No authorization code received</p>
                <p>This window will close automatically...</p>
                <script>
                    // Notify parent window about the error
                    if (window.opener) {
                        window.opener.postMessage({ 
                            type: 'oauth_error', 
                            error: 'No authorization code received' 
                        }, '*');
                    }
                    
                    // Auto-close after 3 seconds
                    setTimeout(() => {
                        window.close();
                    }, 3000);
                </script>
            </body>
            </html>
            """)
        
        # Exchange code for credentials
        try:
            creds = exchange_code(code)
            print(f"Credentials obtained: {creds is not None}")
            print(f"Credentials valid: {creds.valid if creds else False}")
            
            # Return success page that properly notifies parent and closes
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authorization Complete</title>
                <style>
                    body { 
                        font-family: Arial, sans-serif; 
                        text-align: center; 
                        padding: 50px; 
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        margin: 0;
                    }
                    .success { 
                        color: #27ae60; 
                        font-size: 48px;
                        margin-bottom: 20px;
                    }
                    .message {
                        font-size: 24px;
                        margin-bottom: 20px;
                    }
                    .sub-message {
                        font-size: 16px;
                        opacity: 0.8;
                    }
                </style>
            </head>
            <body>
                <div class="success">✅</div>
                <div class="message">Authorization Successful!</div>
                <div class="sub-message">You can close this window and return to the app.</div>
                <script>
                    console.log('OAuth callback: Success');
                    
                    // Notify parent window with success message
                    if (window.opener && !window.opener.closed) {
                        console.log('Notifying parent window...');
                        window.opener.postMessage({ 
                            type: 'oauth_success',
                            data: { authorized: true }
                        }, '*');
                    } else {
                        console.log('No parent window found or parent window is closed');
                    }
                    
                    // Auto-close after 2 seconds
                    setTimeout(() => {
                        console.log('Closing window...');
                        window.close();
                    }, 2000);
                </script>
            </body>
            </html>
            """)
            
        except Exception as auth_error:
            print(f"Error during credential exchange: {str(auth_error)}")
            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authorization Error</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .error {{ color: #e74c3c; }}
                </style>
            </head>
            <body>
                <h2 class="error">❌ Authorization Failed</h2>
                <p>Error during authentication: {str(auth_error)}</p>
                <p>This window will close automatically...</p>
                <script>
                    // Notify parent window about the error
                    if (window.opener) {{
                        window.opener.postMessage({{ 
                            type: 'oauth_error', 
                            error: 'Authentication failed: {str(auth_error)}' 
                        }}, '*');
                    }}
                    
                    // Auto-close after 3 seconds
                    setTimeout(() => {{
                        window.close();
                    }}, 3000);
                </script>
            </body>
            </html>
            """)
        
    except Exception as e:
        print(f"Unexpected error in OAuth callback: {str(e)}")
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authorization Error</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .error {{ color: #e74c3c; }}
            </style>
        </head>
        <body>
            <h2 class="error">❌ Unexpected Error</h2>
            <p>Error: {str(e)}</p>
            <p>This window will close automatically...</p>
            <script>
                // Notify parent window about the error
                if (window.opener) {{
                    window.opener.postMessage({{ 
                        type: 'oauth_error', 
                        error: 'Unexpected error: {str(e)}' 
                    }}, '*');
                }}
                
                // Auto-close after 3 seconds
                setTimeout(() => {{
                    window.close();
                }}, 3000);
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