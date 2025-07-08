from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import re, json, os
from datetime import datetime

from utils.gemini import call_gemini
from utils.google_auth import get_credentials
from utils.calendar_task import (
    create_calendar_event,
    check_schedule,
    check_availability
)
from utils.gmail_task import summarize_emails, send_email, list_unread, search_email
from fastapi.responses import RedirectResponse
from utils.google_auth import get_auth_url, exchange_code


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
def authorize():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri="https://smart-to-do-list-4bi2.onrender.com/oauth2callback"
    )
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    # Save state temporarily (you can use session, db, cache, etc.)
    request.session = {"state": flow.credentials_to_dict()}
    return RedirectResponse(auth_url)

@app.get("/oauth2callback")
def oauth2callback(request: Request):
    state = request.session.get("state")

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri="https://your-backend-domain.com/oauth2callback"
    )

    flow.fetch_token(authorization_response=str(request.url))

    creds = flow.credentials

    with open("token.json", "w") as token_file:
        token_file.write(creds.to_json())

    return HTMLResponse("<h2>✅ Authorization successful. You can close this tab.</h2><script>window.close();</script>")

@app.get("/check-auth")
def check_auth():
    try:
        creds = get_credentials()
        return {"authorized": creds is not None}
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