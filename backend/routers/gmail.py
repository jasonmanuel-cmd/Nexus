"""Gmail OAuth + inbox poller + reply detector router."""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from deps import db, get_current_user, User, EMERGENT_LLM_KEY
from emergentintegrations.llm.chat import LlmChat, UserMessage
from integrations.gmail_client import (
    build_consent_url,
    exchange_code_for_tokens,
    fetch_new_replies,
    get_authed_service,
    mark_as_read,
    send_reply,
    get_profile_email,
)

router = APIRouter(prefix="/integrations/gmail", tags=["gmail"])
public_router = APIRouter(tags=["gmail-public"])  # for callback (no auth)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


GMAIL_REPLY_DRAFT_PROMPT = """You are Nexus AI's autonomous follow-up composer.

Given (a) the original outbound email and (b) the buyer's actual reply,
produce a tight, high-converting next-step email plus deal-impact metadata.

Return STRICT JSON in this shape (no markdown):
{
  "subject": "Re: <original subject>",
  "body": "<2-4 short paragraphs, conversational, action-oriented>",
  "sentiment": "positive|neutral|negative",
  "intent": "interested|wants_info|deferring|objecting|not_now",
  "probability_delta": <int -25..+30, change in win probability based on the reply>,
  "confidence": <int 50..99>,
  "suggested_action": "<1 short sentence on what salesperson should do>"
}"""


async def build_draft_from_reply(
    *, user_id: str, original_email: dict, reply_body: str, reply_subject: str,
    reply_id: str, reply_thread_id: Optional[str] = None,
) -> Optional[dict]:
    """Generate a Claude follow-up draft from a real Gmail reply. Persists ReplyDraft."""
    if not EMERGENT_LLM_KEY:
        return None

    meta = original_email.get("meta") or {}
    deal_id = meta.get("deal_id")
    target_id = meta.get("target_id")
    deal_doc = await db.deals.find_one({"id": deal_id, "user_id": user_id}, {"_id": 0}) if deal_id else None
    target_doc = await db.targets.find_one({"id": target_id, "user_id": user_id}, {"_id": 0}) if target_id else None
    company = (deal_doc or {}).get("company") or (target_doc or {}).get("company_name") or "Unknown Co"

    user_prompt = (
        f"Original outbound:\n"
        f"SUBJECT: {original_email.get('subject', '')}\n"
        f"BODY:\n{original_email.get('body', '')}\n\n"
        f"Buyer REAL REPLY (from Gmail):\n"
        f"FROM: {original_email.get('to', '')}\n"
        f"SUBJECT: {reply_subject}\n"
        f"BODY:\n{reply_body}\n\n"
        f"Prospect: {company}\n"
        f"Generate the JSON follow-up draft."
    )

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"gmail-reply-{reply_id[:12]}",
            system_message=GMAIL_REPLY_DRAFT_PROMPT,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        response_text = await chat.send_message(UserMessage(text=user_prompt))
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.rsplit("```", 1)[0]
        parsed = json.loads(cleaned.strip())
    except Exception as e:
        logging.warning(f"Gmail draft LLM failed: {e}")
        return None

    draft = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "reply_id": reply_id,
        "original_email_id": original_email.get("id"),
        "deal_id": deal_id,
        "subject": str(parsed.get("subject", f"Re: {original_email.get('subject', '')}"))[:200],
        "body": str(parsed.get("body", ""))[:4000],
        "sentiment": str(parsed.get("sentiment", "neutral"))[:20],
        "intent": str(parsed.get("intent", "wants_info"))[:30],
        "probability_delta": int(parsed.get("probability_delta", 0)),
        "confidence": int(parsed.get("confidence", 70)),
        "suggested_action": str(parsed.get("suggested_action", ""))[:300],
        "status": "pending",
        "auto_sent": False,
        "source": "gmail",
        "reply_thread_id": reply_thread_id,
        "created_at": now_iso(),
    }
    await db.reply_drafts.insert_one(dict(draft))
    return draft


def _redirect_uri_from(request: Request) -> str:
    """Derive the Gmail OAuth redirect URI from the inbound request host.

    Works automatically on both preview (preview.emergentagent.com) and production
    (emergent.host) so we don't have to maintain per-env config. Honors
    X-Forwarded-Proto if behind a proxy (Emergent's Kubernetes ingress sets this).
    """
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}/api/integrations/gmail/callback"


# ----- OAuth flow -----
@router.post("/connect")
async def connect(request: Request, user: User = Depends(get_current_user)):
    """Generate Google consent URL. Stores state for callback verification.

    Uses dynamic redirect URI so the same code works on preview + production.
    Both URIs must be registered in Google Cloud Console under "Authorized redirect URIs".
    """
    state = uuid.uuid4().hex
    redirect_uri = _redirect_uri_from(request)
    await db.gmail_oauth_states.insert_one({
        "state": state,
        "user_id": user.user_id,
        "redirect_uri": redirect_uri,
        "created_at": now_iso(),
    })
    url = build_consent_url(state, redirect_uri)
    return {"url": url, "state": state, "redirect_uri": redirect_uri}


@public_router.get("/integrations/gmail/callback")
async def callback(request: Request, code: str = Query(...), state: str = Query(...)):
    """Receive OAuth code → exchange → persist credentials → redirect to /app/settings."""
    rec = await db.gmail_oauth_states.find_one({"state": state})
    if not rec:
        raise HTTPException(400, "Invalid or expired OAuth state")
    user_id = rec["user_id"]
    redirect_uri = rec.get("redirect_uri") or _redirect_uri_from(request)
    await db.gmail_oauth_states.delete_one({"state": state})

    try:
        tokens = exchange_code_for_tokens(code, redirect_uri)
    except Exception as e:
        logging.error(f"Gmail token exchange failed: {e}")
        raise HTTPException(502, f"Token exchange failed: {e}")

    # Probe profile email for display purposes
    profile_email = ""
    try:
        svc = await get_authed_service(tokens)
        profile_email = await get_profile_email(svc)
    except Exception as e:
        logging.warning(f"Could not fetch Gmail profile: {e}")

    await db.gmail_credentials.update_one(
        {"user_id": user_id},
        {"$set": {
            **tokens,
            "user_id": user_id,
            "email": profile_email,
            "connected_at": now_iso(),
        }},
        upsert=True,
    )
    # Redirect back to settings page in the app
    return RedirectResponse(url="/app/settings?gmail=connected")


@router.get("/status")
async def status(user: User = Depends(get_current_user)):
    rec = await db.gmail_credentials.find_one({"user_id": user.user_id}, {"_id": 0, "access_token": 0, "refresh_token": 0, "client_secret": 0})
    if not rec:
        return {"connected": False}
    return {
        "connected": True,
        "email": rec.get("email", ""),
        "connected_at": rec.get("connected_at"),
        "last_polled_at": rec.get("last_polled_at"),
    }


@router.post("/disconnect")
async def disconnect(user: User = Depends(get_current_user)):
    res = await db.gmail_credentials.delete_one({"user_id": user.user_id})
    return {"disconnected": res.deleted_count > 0}


# ----- Poll inbox for replies -----
class PollResponse(BaseModel):
    polled: bool
    new_replies: int
    drafts_created: int
    messages: list


async def _persist_credentials(user_id: str, new_rec: dict):
    await db.gmail_credentials.update_one({"user_id": user_id}, {"$set": new_rec})


@router.post("/poll", response_model=PollResponse)
async def poll(user: User = Depends(get_current_user)):
    """Fetch unread Gmail replies and convert them into reply_drafts via Claude."""
    rec = await db.gmail_credentials.find_one({"user_id": user.user_id}, {"_id": 0})
    if not rec:
        raise HTTPException(400, "Gmail not connected — connect first")

    async def _on_refresh(new_rec):
        await _persist_credentials(user.user_id, new_rec)

    try:
        service = await get_authed_service(rec, on_refresh=_on_refresh)
    except Exception as e:
        logging.error(f"Gmail auth failed: {e}")
        raise HTTPException(502, f"Gmail auth failed: {e}")

    try:
        msgs = await fetch_new_replies(service, query="is:unread newer_than:7d in:inbox", max_msgs=25)
    except Exception as e:
        raise HTTPException(502, f"Gmail fetch failed: {e}")

    # Lazy import to avoid circular: helper lives in this same module
    drafts_created = 0
    seen_messages: list = []
    for m in msgs:
        # Skip if we've already ingested this message
        existing = await db.email_replies.find_one({"gmail_message_id": m["message_id"], "user_id": user.user_id})
        if existing:
            continue

        # Match this reply to an outbound email by thread_id
        outbound = None
        if m.get("thread_id"):
            outbound = await db.email_outbox.find_one({"user_id": user.user_id, "gmail_thread_id": m["thread_id"]}, {"_id": 0})

        # Store the inbound reply
        reply_doc = {
            "id": str(uuid.uuid4()),
            "user_id": user.user_id,
            "gmail_message_id": m["message_id"],
            "gmail_thread_id": m["thread_id"],
            "from": m["from"],
            "subject": m["subject"],
            "body": m["body"] or m["snippet"],
            "received_at": now_iso(),
            "original_email_id": outbound.get("id") if outbound else None,
            "linked": bool(outbound),
            "source": "gmail",
        }
        await db.email_replies.insert_one(dict(reply_doc))
        seen_messages.append({"from": m["from"], "subject": m["subject"], "linked": bool(outbound)})

        # Generate Claude follow-up draft when we have an outbound email match
        if outbound:
            try:
                draft = await build_draft_from_reply(
                    user_id=user.user_id,
                    original_email=outbound,
                    reply_body=reply_doc["body"],
                    reply_subject=reply_doc["subject"],
                    reply_id=reply_doc["id"],
                    reply_thread_id=m["thread_id"],
                )
                if draft:
                    drafts_created += 1
            except Exception as e:
                logging.warning(f"Draft generation failed for {m['message_id']}: {e}")

        # Mark as read in gmail
        await mark_as_read(service, m["message_id"])

    await db.gmail_credentials.update_one(
        {"user_id": user.user_id},
        {"$set": {"last_polled_at": now_iso()}},
    )

    return PollResponse(
        polled=True,
        new_replies=len(seen_messages),
        drafts_created=drafts_created,
        messages=seen_messages[:10],
    )


# ----- Send-as-reply (so we use the user's gmail rather than Resend) -----
class SendReplyPayload(BaseModel):
    to: str
    subject: str
    body: str
    thread_id: Optional[str] = None
    in_reply_to: Optional[str] = None


@router.post("/send")
async def send(payload: SendReplyPayload, user: User = Depends(get_current_user)):
    rec = await db.gmail_credentials.find_one({"user_id": user.user_id}, {"_id": 0})
    if not rec:
        raise HTTPException(400, "Gmail not connected")

    async def _on_refresh(new_rec):
        await _persist_credentials(user.user_id, new_rec)

    service = await get_authed_service(rec, on_refresh=_on_refresh)
    try:
        result = await send_reply(
            service,
            to=payload.to,
            subject=payload.subject,
            body=payload.body,
            thread_id=payload.thread_id,
            in_reply_to=payload.in_reply_to,
        )
    except Exception as e:
        raise HTTPException(502, f"Gmail send failed: {e}")

    return {"sent": True, "message_id": result.get("id"), "thread_id": result.get("threadId")}
