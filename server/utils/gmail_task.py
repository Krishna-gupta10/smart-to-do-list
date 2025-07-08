from googleapiclient.discovery import build
from datetime import datetime

def summarize_emails(creds, date_str: str = None, query: str = None):
    service = build("gmail", "v1", credentials=creds)

    if query:
        q = query
    elif date_str:
        q = f"after:{date_str.replace('-', '/')}"
    else:
        # Default fallback — today
        today = datetime.now().strftime("%Y/%m/%d")
        q = f"after:{today}"

    result = service.users().messages().list(userId="me", q=q, maxResults=5).execute()
    messages = result.get("messages", [])

    summaries = []
    for msg in messages:
        msg_data = service.users().messages().get(userId="me", id=msg["id"]).execute()
        payload = msg_data.get("payload", {})
        headers = payload.get("headers", [])
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
        snippet = msg_data.get("snippet", "")
        summaries.append({"subject": subject, "snippet": snippet})

    return summaries



def send_email(creds, to: str, subject: str, body: str):
    from email.mime.text import MIMEText
    import base64

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service = build("gmail", "v1", credentials=creds)
    message = service.users().messages().send(userId="me", body={"raw": raw_message}).execute()

    return {"id": message["id"], "to": to, "subject": subject}


def list_unread(creds, after_date: str):
    service = build("gmail", "v1", credentials=creds)
    query = f"is:unread after:{after_date}"
    result = service.users().messages().list(userId="me", q=query, maxResults=10).execute()
    messages = result.get("messages", [])

    unread_emails = []
    for msg in messages:
        msg_data = service.users().messages().get(userId="me", id=msg["id"]).execute()
        payload = msg_data.get("payload", {})
        headers = payload.get("headers", [])
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
        snippet = msg_data.get("snippet", "")
        unread_emails.append({"subject": subject, "snippet": snippet})

    return unread_emails


def search_email(creds, query: str):
    service = build("gmail", "v1", credentials=creds)
    result = service.users().messages().list(userId="me", q=query, maxResults=5).execute()
    messages = result.get("messages", [])

    matched = []
    for msg in messages:
        msg_data = service.users().messages().get(userId="me", id=msg["id"]).execute()
        payload = msg_data.get("payload", {})
        headers = payload.get("headers", [])
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
        snippet = msg_data.get("snippet", "")
        matched.append({"subject": subject, "snippet": snippet})

    return matched
