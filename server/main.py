from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import re, json, os
from datetime import datetime

from utils.gemini import call_gemini
from utils.google_auth import get_credentials, authorize_user
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

@app.get("/authorize")
def auth():
    try:
        result = authorize_user()
        # Return HTML that closes the window and notifies parent
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authorization Complete</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background-color: #f0f2f5;
                }
                .container {
                    text-align: center;
                    background: white;
                    padding: 2rem;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                .success {
                    color: #10b981;
                    font-size: 1.2rem;
                    margin-bottom: 1rem;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success">✅ Authorization successful!</div>
                <p>You can now close this window.</p>
            </div>
            <script>
                setTimeout(() => {
                    window.close();
                }, 2000);
            </script>
        </body>
        </html>
        """)
    except Exception as e:
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authorization Error</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background-color: #f0f2f5;
                }}
                .container {{
                    text-align: center;
                    background: white;
                    padding: 2rem;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .error {{
                    color: #ef4444;
                    font-size: 1.2rem;
                    margin-bottom: 1rem;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error">❌ Authorization failed</div>
                <p>Error: {str(e)}</p>
                <p>Please try again.</p>
            </div>
            <script>
                setTimeout(() => {{
                    window.close();
                }}, 3000);
            </script>
        </body>
        </html>
        """)

@app.get("/check-auth")
def check_auth():
    """Check if user is authenticated"""
    try:
        if os.path.exists('token.json'):
            # Try to load credentials to verify they're valid
            creds = get_credentials()
            if creds and creds.valid:
                return {"authorized": True}
            else:
                return {"authorized": False}
        else:
            return {"authorized": False}
    except Exception as e:
        return {"authorized": False, "error": str(e)}

@app.post("/parse-and-execute")
def parse_and_execute(data: TaskInput):
    # Check if user is authenticated first
    try:
        creds = get_credentials()
        if not creds or not creds.valid:
            raise HTTPException(status_code=401, detail="User not authenticated. Please authorize with Google first.")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Authentication required. Please authorize with Google first.")

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

            elif parsed["action"] == "send_email":
                result = send_email(creds, parsed["email"], parsed["subject"], parsed["body"])
                return {
                    "status": "Email Sent ✅",
                    "result": result,
                    "parsed": parsed
                    }

            elif parsed["action"] == "list_unread":
                emails = list_unread(creds, parsed["date_time"])
                return {
                    "status": "Unread ✅",
                    "emails": emails,
                    "parsed": parsed
                    }

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

        except Exception as e:
            return {"error": str(e), "raw": raw_response}

    # 👉 If response wasn't JSON, return it as a general message
    return {
        "status": "Message 💬",
        "message": raw_response
    }