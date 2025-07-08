import os
import requests
import json
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")


def call_gemini(task: str):
    today = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""
You are a smart assistant. Today's date is {today}.

If the user asks something casual, general, or conversational 
(e.g. "How was my day?", "Tell me a joke", "What's new in tech?"), 
reply with a short natural message.

If the user gives a task to be executed, respond ONLY with a valid JSON:
- action: "schedule_call" | "add_event" | "summarize_emails" | "send_email" | "check_schedule" | "check_availability" | "list_unread" | "search_email"
- person: string or null
- email: string or null
- date_time: ISO 8601 datetime (for scheduling) OR date only (for checking)
- repeat: "none" | "daily" | "weekly" | "monthly"
- missing_fields: list of fields not present in the user input (e.g. ["email", "date_time"])
- subject: string (write a short default if not given)
- body: string
- query: string

Examples:
✔ If everything is present:
{{
  "action": "schedule_call",
  "person": "Prachi",
  "email": "prachi@email.com",
  "date_time": "2025-07-09T18:00:00",
  "repeat": "none",
  "missing_fields": []
}}

❗ If something is missing:
{{
  "action": "schedule_call",
  "person": "Prachi",
  "email": null,
  "date_time": null,
  "repeat": "none",
  "missing_fields": ["email", "date_time"]
}}

If it's not a task at all, just respond with a short human-friendly message.
DO NOT mix natural text and JSON together.

User input:
\"{task}\"
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        res = requests.post(url, json=payload)
        res.raise_for_status()
        content = res.json()
        text = content["candidates"][0]["content"]["parts"][0]["text"]
        return text.strip() if text else "[Empty response from Gemini]"
    except Exception as e:
        return f"ERROR: {e}"
