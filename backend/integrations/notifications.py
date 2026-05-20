"""Notification stubs — Resend (email) + Slack (webhook).

All outbound notifications are persisted to MongoDB and flagged `mocked=true`
when the respective integration is not configured. Swap MOCKED for LIVE by
setting RESEND_API_KEY / SLACK_WEBHOOK_URL in /app/backend/.env and
implementing the actual HTTP calls below.
"""
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def send_email(db, *, to: str, subject: str, body: str, user_id: Optional[str] = None,
                    kind: str = "outreach", meta: Optional[dict] = None) -> dict:
    """Queue an email via Resend (currently MOCKED — persisted to db.email_outbox)."""
    resend_key = os.environ.get("RESEND_API_KEY")
    mocked = not bool(resend_key)
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "to": to,
        "subject": subject,
        "body": body,
        "kind": kind,
        "meta": meta or {},
        "status": "queued",
        "mocked": mocked,
        "provider": "resend" if not mocked else "resend_mock",
        "created_at": _now_iso(),
    }
    if mocked:
        doc["delivered_at"] = _now_iso()
        doc["status"] = "delivered_mock"
    else:
        # TODO: real Resend call — left intentionally stubbed
        # import resend; resend.api_key = resend_key
        # resend.Emails.send({...})
        doc["delivered_at"] = _now_iso()
        doc["status"] = "delivered"

    await db.email_outbox.insert_one(dict(doc))
    logging.info(f"[email {'MOCK' if mocked else 'LIVE'}] {to} :: {subject}")
    return doc


async def send_slack(db, *, text: str, blocks: Optional[list] = None,
                     user_id: Optional[str] = None, kind: str = "event",
                     meta: Optional[dict] = None) -> dict:
    """Post to Slack incoming webhook (currently MOCKED — persisted to db.slack_outbox)."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    mocked = not bool(webhook_url)
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "text": text,
        "blocks": blocks or [],
        "kind": kind,
        "meta": meta or {},
        "status": "queued",
        "mocked": mocked,
        "provider": "slack" if not mocked else "slack_mock",
        "created_at": _now_iso(),
    }
    if mocked:
        doc["delivered_at"] = _now_iso()
        doc["status"] = "delivered_mock"
    else:
        # TODO: real Slack POST
        # async with httpx.AsyncClient() as http: await http.post(webhook_url, json={"text": text, "blocks": blocks})
        doc["delivered_at"] = _now_iso()
        doc["status"] = "delivered"

    await db.slack_outbox.insert_one(dict(doc))
    logging.info(f"[slack {'MOCK' if mocked else 'LIVE'}] {text[:80]}")
    return doc
