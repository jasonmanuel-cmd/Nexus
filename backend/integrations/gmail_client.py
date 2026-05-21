"""Gmail OAuth + inbox poller + send-as-reply for Nexus AI.

Single-user flow:
1. POST /api/integrations/gmail/connect → returns Google consent URL
2. GET  /api/integrations/gmail/callback?code=&state= → stores creds in mongo
3. POST /api/integrations/gmail/poll → fetches unread replies, links via threadId
4. POST /api/integrations/gmail/send-reply → reply within an existing thread
"""
import asyncio
import base64
import logging
import os
import warnings
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]


def _client_config() -> dict:
    return {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [os.environ["GMAIL_REDIRECT_URI"]],
        }
    }


def build_consent_url(state: str) -> str:
    """Return Google consent URL for Gmail scopes."""
    flow = Flow.from_client_config(
        _client_config(),
        scopes=GMAIL_SCOPES,
        redirect_uri=os.environ["GMAIL_REDIRECT_URI"],
    )
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        include_granted_scopes="true",
    )
    return url


def exchange_code_for_tokens(code: str) -> dict:
    """Exchange OAuth code → credentials dict for Mongo storage."""
    flow = Flow.from_client_config(
        _client_config(),
        scopes=GMAIL_SCOPES,
        redirect_uri=os.environ["GMAIL_REDIRECT_URI"],
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # scope-order warning is benign
        flow.fetch_token(code=code)
    c = flow.credentials
    expires_at = c.expiry.replace(tzinfo=timezone.utc) if c.expiry else (datetime.now(timezone.utc) + timedelta(minutes=55))
    return {
        "access_token": c.token,
        "refresh_token": c.refresh_token,
        "token_uri": c.token_uri,
        "client_id": c.client_id,
        "client_secret": c.client_secret,
        "scopes": list(c.scopes or GMAIL_SCOPES),
        "expires_at": expires_at.isoformat(),
    }


def _creds_from_record(rec: dict) -> Credentials:
    expires_at = rec.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except Exception:
            expiry = None
    else:
        expiry = expires_at
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    creds = Credentials(
        token=rec["access_token"],
        refresh_token=rec.get("refresh_token"),
        token_uri=rec["token_uri"],
        client_id=rec["client_id"],
        client_secret=rec["client_secret"],
        scopes=rec.get("scopes", GMAIL_SCOPES),
    )
    # google-auth refresh check uses creds.expiry (naive UTC)
    if expiry:
        creds.expiry = expiry.replace(tzinfo=None) if expiry.tzinfo else expiry
    return creds


async def get_authed_service(rec: dict, on_refresh=None):
    """Build a Gmail service, refreshing tokens if needed.

    `on_refresh(new_record)` callback receives an updated dict to persist back.
    """
    creds = _creds_from_record(rec)

    def _refresh_if_needed():
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            return True
        return False

    refreshed = await asyncio.to_thread(_refresh_if_needed)
    if refreshed and on_refresh:
        new_expiry = creds.expiry or (datetime.utcnow() + timedelta(minutes=55))
        await on_refresh({
            **rec,
            "access_token": creds.token,
            "expires_at": new_expiry.replace(tzinfo=timezone.utc).isoformat() if new_expiry.tzinfo is None else new_expiry.isoformat(),
        })

    def _build():
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    return await asyncio.to_thread(_build)


def _extract_plain_text(payload: dict) -> str:
    """Extract plain-text body from a Gmail message payload (handles multipart)."""
    if not payload:
        return ""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")
    if mime == "text/plain" and data:
        try:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        except Exception:
            return ""
    for part in payload.get("parts") or []:
        text = _extract_plain_text(part)
        if text:
            return text
    return ""


def _header(headers: List[dict], name: str) -> str:
    for h in headers or []:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


async def fetch_new_replies(service, query: str = "is:unread newer_than:7d in:inbox", max_msgs: int = 25) -> List[Dict[str, Any]]:
    """Fetch new unread inbox messages, return parsed reply records."""
    def _list():
        return service.users().messages().list(userId="me", q=query, maxResults=max_msgs).execute()

    def _get(msg_id):
        return service.users().messages().get(userId="me", id=msg_id, format="full").execute()

    try:
        listing = await asyncio.to_thread(_list)
    except HttpError as e:
        logger.error(f"Gmail list failed: {e}")
        raise

    ids = [m["id"] for m in (listing.get("messages") or [])]
    out: List[Dict[str, Any]] = []
    for mid in ids:
        try:
            full = await asyncio.to_thread(_get, mid)
        except HttpError as e:
            logger.warning(f"Gmail get failed for {mid}: {e}")
            continue
        payload = full.get("payload", {})
        headers = payload.get("headers", [])
        out.append({
            "message_id": full.get("id"),
            "thread_id": full.get("threadId"),
            "from": _header(headers, "From"),
            "subject": _header(headers, "Subject"),
            "in_reply_to": _header(headers, "In-Reply-To"),
            "references": _header(headers, "References"),
            "received_at": full.get("internalDate"),
            "snippet": full.get("snippet", ""),
            "body": _extract_plain_text(payload),
            "label_ids": full.get("labelIds", []),
        })
    return out


async def mark_as_read(service, message_id: str):
    def _modify():
        return service.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()
    try:
        await asyncio.to_thread(_modify)
    except HttpError as e:
        logger.warning(f"Failed to mark read {message_id}: {e}")


async def send_reply(service, *, to: str, subject: str, body: str, thread_id: Optional[str] = None, in_reply_to: Optional[str] = None) -> dict:
    """Send a Gmail message (optionally threaded as a reply)."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to
    # Reply subject prefix
    if subject and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    body_dict = {"raw": raw}
    if thread_id:
        body_dict["threadId"] = thread_id

    def _send():
        return service.users().messages().send(userId="me", body=body_dict).execute()

    return await asyncio.to_thread(_send)


async def get_profile_email(service) -> str:
    def _profile():
        return service.users().getProfile(userId="me").execute()
    try:
        p = await asyncio.to_thread(_profile)
        return p.get("emailAddress", "")
    except HttpError:
        return ""
