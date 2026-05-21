"""Notification senders — Resend (email) + Slack (webhook).

Both flip from MOCKED → LIVE automatically when their env keys are present.
Every send is persisted to MongoDB (`email_outbox` / `slack_outbox`).
"""
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def send_email(db, *, to: str, subject: str, body: str, user_id: Optional[str] = None,
                    kind: str = "outreach", meta: Optional[dict] = None,
                    api_key_override: Optional[str] = None,
                    from_email_override: Optional[str] = None) -> dict:
    """Send via Resend. Per-user `api_key_override` + `from_email_override` take priority.
    Falls back to env. If neither present, send is MOCKED to db.email_outbox.
    """
    resend_key = api_key_override or os.environ.get("RESEND_API_KEY")
    from_email = from_email_override or os.environ.get("RESEND_FROM_EMAIL", "nexus@example.com")
    mocked = not bool(resend_key)

    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "to": to,
        "from": from_email,
        "subject": subject,
        "body": body,
        "kind": kind,
        "meta": meta or {},
        "status": "queued",
        "mocked": mocked,
        "provider": "resend" if not mocked else "resend_mock",
        "created_at": _now_iso(),
        "error": None,
    }

    if mocked:
        doc["delivered_at"] = _now_iso()
        doc["status"] = "delivered_mock"
    else:
        try:
            import resend
            resend.api_key = resend_key
            resp = resend.Emails.send({
                "from": from_email,
                "to": [to],
                "subject": subject,
                "text": body,
            })
            doc["provider_id"] = resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", None)
            doc["delivered_at"] = _now_iso()
            doc["status"] = "delivered"
        except Exception as e:
            doc["status"] = "failed"
            doc["error"] = str(e)[:200]
            logging.error(f"[resend FAIL] {to} :: {subject} :: {e}")

    await db.email_outbox.insert_one(dict(doc))
    logging.info(f"[email {'MOCK' if mocked else doc['status'].upper()}] {to} :: {subject}")
    return doc


async def send_slack(db, *, text: str, blocks: Optional[list] = None,
                     user_id: Optional[str] = None, kind: str = "event",
                     meta: Optional[dict] = None) -> dict:
    """POST to Slack incoming webhook if SLACK_WEBHOOK_URL is set; otherwise MOCKED."""
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
        "error": None,
    }

    if mocked:
        doc["delivered_at"] = _now_iso()
        doc["status"] = "delivered_mock"
    else:
        try:
            payload = {"text": text}
            if blocks:
                payload["blocks"] = blocks
            async with httpx.AsyncClient(timeout=10.0) as http:
                r = await http.post(webhook_url, json=payload)
                if r.status_code >= 400:
                    raise RuntimeError(f"Slack {r.status_code}: {r.text[:120]}")
            doc["delivered_at"] = _now_iso()
            doc["status"] = "delivered"
        except Exception as e:
            doc["status"] = "failed"
            doc["error"] = str(e)[:200]
            logging.error(f"[slack FAIL] :: {e}")

    await db.slack_outbox.insert_one(dict(doc))
    logging.info(f"[slack {'MOCK' if mocked else doc['status'].upper()}] {text[:80]}")
    return doc
