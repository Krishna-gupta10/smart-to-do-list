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

@app.post("/oauth2callback")
def oauth2callback(data: AuthCodeInput):
    """Handle OAuth callback with authorization code"""
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