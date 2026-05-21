"""Public webhooks — Resend inbound email parser.

Resend POSTs parsed inbound mail to this endpoint when configured at
Resend Dashboard → Webhooks → subscribe `email.received`.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from deps import db

router = APIRouter(tags=["webhooks"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Resend's `email.received` payload normalization.

    Resend's exact shape may evolve; we try common keys and fall back gracefully.
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    headers = data.get("headers") or {}
    if isinstance(headers, list):  # sometimes array of {name,value}
        headers = {h.get("name", "").lower(): h.get("value") for h in headers if isinstance(h, dict)}
    else:
        headers = {k.lower(): v for k, v in headers.items()}
    return {
        "from": data.get("from") or data.get("from_address") or "",
        "to": data.get("to") or data.get("to_address") or "",
        "subject": data.get("subject") or "",
        "text": data.get("text") or data.get("body_text") or "",
        "html": data.get("html") or data.get("body_html") or "",
        "in_reply_to": headers.get("in-reply-to") or "",
        "references": headers.get("references") or "",
        "message_id": data.get("id") or headers.get("message-id") or "",
        "received_at": data.get("created_at") or _now_iso(),
        "raw": data,
    }


@router.post("/webhook/resend-inbound")
async def resend_inbound(request: Request):
    """Receive Resend inbound payload, match to an outbound email_outbox row,
    create email_replies row + Claude follow-up draft."""
    payload: Dict[str, Any] = {}
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    event_type = payload.get("type") or payload.get("event") or ""
    # We only care about inbound events; ignore everything else (e.g. delivered/bounced)
    if event_type and "received" not in event_type and "inbound" not in event_type:
        return {"ok": True, "ignored": event_type}

    e = _extract(payload)
    if not e["from"] or not e["text"]:
        logging.warning(f"[resend-inbound] dropping incomplete payload: keys={list(payload.keys())}")
        return {"ok": True, "ignored": "missing_fields"}

    # Match: by In-Reply-To header → provider_id of the outbound email
    in_reply = (e["in_reply_to"] or "").strip("<>").strip()
    refs = (e["references"] or "").strip()
    candidate_ids = [in_reply] + [r.strip("<>") for r in refs.split() if r.strip("<>")]
    candidate_ids = [c for c in candidate_ids if c]

    outbound = None
    for cid in candidate_ids:
        outbound = await db.email_outbox.find_one({"provider_id": cid}, {"_id": 0})
        if outbound:
            break
    if not outbound:
        # Fallback: match by to=from-of-reply (recipient of inbound == sender of inbound's reply target)
        outbound = await db.email_outbox.find_one(
            {"to": e["from"], "kind": "promote.intro"},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
    if not outbound:
        logging.warning(f"[resend-inbound] unmatched reply from {e['from']}")
        # Still store it for visibility
        await db.email_replies.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": None,
            "from": e["from"],
            "subject": e["subject"],
            "body": e["text"],
            "received_at": _now_iso(),
            "linked": False,
            "source": "resend",
            "raw_message_id": e["message_id"],
        })
        return {"ok": True, "matched": False}

    user_id: Optional[str] = outbound.get("user_id")
    # Persist reply
    reply_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "from": e["from"],
        "subject": e["subject"],
        "body": e["text"],
        "received_at": _now_iso(),
        "original_email_id": outbound.get("id"),
        "linked": True,
        "source": "resend",
        "raw_message_id": e["message_id"],
    }
    await db.email_replies.insert_one(dict(reply_doc))

    # Draft follow-up via Claude (reuses Gmail draft helper) — fire-and-forget so we ACK Resend fast
    import asyncio as _asyncio

    async def _draft_bg():
        try:
            from routers.gmail import build_draft_from_reply
            await build_draft_from_reply(
                user_id=user_id,
                original_email=outbound,
                reply_body=reply_doc["body"],
                reply_subject=reply_doc["subject"],
                reply_id=reply_doc["id"],
                reply_thread_id=None,
            )
        except Exception as ex:
            logging.warning(f"Resend inbound: Claude draft failed: {ex}")

    _asyncio.create_task(_draft_bg())

    return {"ok": True, "matched": True, "reply_id": reply_doc["id"]}
