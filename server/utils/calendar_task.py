from googleapiclient.discovery import build
from datetime import datetime, timedelta

def create_calendar_event(creds, person: str, date_time: str, person_email: str = None, repeat: str = "none", summary_override: str = None):

    service = build('calendar', 'v3', credentials=creds)

    start_time = datetime.fromisoformat(date_time)
    end_time = start_time + timedelta(minutes=30)

    event = {
        'summary': summary_override or f'Call with {person}',
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'attendees': [{'email': person_email}] if person_email else []
    }

    # ✅ Add recurrence rule if repeat is set
    if repeat and repeat != "none":
        rrule = build_rrule_from_repeat(repeat, start_time)
        if rrule:
            event["recurrence"] = [rrule]

    created_event = service.events().insert(
        calendarId='primary',
        body=event,
        sendUpdates='all'  # Sends email to attendees
    ).execute()

    return created_event.get('htmlLink')


from googleapiclient.discovery import build
from datetime import datetime, timedelta

def check_schedule(creds, date_str: str):
    service = build("calendar", "v3", credentials=creds)

    start = datetime.fromisoformat(date_str)
    end = start + timedelta(days=1)

    events_result = service.events().list(
        calendarId="primary",
        timeMin=start.isoformat() + "Z",
        timeMax=end.isoformat() + "Z",
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = events_result.get("items", [])
    output = []

    for e in events:
        output.append({
            "summary": e.get("summary"),
            "start": e["start"].get("dateTime", e["start"].get("date"))
        })

    return output

def check_availability(creds, date_str: str):
    service = build("calendar", "v3", credentials=creds)

    date = datetime.fromisoformat(date_str)
    start = datetime(date.year, date.month, date.day, 9, 0)
    end = datetime(date.year, date.month, date.day, 18, 0)

    body = {
        "timeMin": start.isoformat() + "Z",
        "timeMax": end.isoformat() + "Z",
        "items": [{"id": "primary"}]
    }

    busy = service.freebusy().query(body=body).execute()["calendars"]["primary"]["busy"]
    free_slots = []

    last_end = start
    for block in busy:
        busy_start = datetime.fromisoformat(block["start"].replace("Z", "+00:00"))
        if busy_start > last_end:
            free_slots.append({
                "from": last_end.strftime("%H:%M"),
                "to": busy_start.strftime("%H:%M")
            })
        last_end = datetime.fromisoformat(block["end"].replace("Z", "+00:00"))

    if last_end < end:
        free_slots.append({
            "from": last_end.strftime("%H:%M"),
            "to": end.strftime("%H:%M")
        })

    return free_slots


def build_rrule_from_repeat(repeat: str, start_time: datetime):
    if repeat == "daily":
        return "RRULE:FREQ=DAILY"
    elif repeat == "weekly":
        byday = start_time.strftime("%a").upper()[:2]
        return f"RRULE:FREQ=WEEKLY;BYDAY={byday}"
    elif repeat == "monthly":
        return "RRULE:FREQ=MONTHLY"
    return ""
