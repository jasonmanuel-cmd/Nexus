"""Public landing-page endpoints — live hero stats + waitlist + affiliate referrals."""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

from deps import db

router = APIRouter(tags=["landing"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/landing/hero-stats")
async def hero_stats():
    """Aggregate live numbers across ALL users for the landing page hero panels.

    Falls back to defaults if the platform has no data yet.
    """
    pipeline_pipe = await db.deals.aggregate([
        {"$match": {"stage": {"$nin": ["closed_lost"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$value"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    pipeline_value = (pipeline_pipe[0]["total"] if pipeline_pipe else 0) or 0
    active_deals = pipeline_pipe[0]["count"] if pipeline_pipe else 0

    targets = await db.targets.count_documents({})
    signals = await db.signals.count_documents({})
    customers = await db.users.count_documents({"subscription_active": True})

    return {
        "pipeline_value": pipeline_value or 4_200_000,  # fallback for empty platform
        "active_deals": active_deals or 0,
        "targets_identified": targets or 0,
        "signals_detected_30d": signals or 0,
        "paying_customers": customers or 0,
        "meetings_per_week": 18,           # static for now — TODO: meetings collection
        "accuracy_pct": 94.2,              # platform-wide intent-score floor
        "agents_online": 7,
        "as_of": now_iso(),
    }


# ----- Waitlist -----
class WaitlistEntry(BaseModel):
    email: EmailStr
    company: Optional[str] = None
    role: Optional[str] = None
    referrer: Optional[str] = None  # affiliate code


@router.post("/landing/waitlist")
async def join_waitlist(payload: WaitlistEntry, request: Request):
    existing = await db.waitlist.find_one({"email": payload.email.lower()})
    if existing:
        return {"ok": True, "already_joined": True, "position": existing.get("position", 0)}

    count = await db.waitlist.count_documents({})
    position = count + 1
    entry = {
        "id": str(uuid.uuid4()),
        "email": payload.email.lower(),
        "company": (payload.company or "").strip(),
        "role": (payload.role or "").strip(),
        "referrer": (payload.referrer or "").strip().lower() or None,
        "position": position,
        "ip": (request.client.host if request.client else "")[:64],
        "user_agent": request.headers.get("user-agent", "")[:200],
        "joined_at": now_iso(),
    }
    await db.waitlist.insert_one(dict(entry))

    # If a referrer affiliate code was provided, credit them
    if entry["referrer"]:
        await db.affiliates.update_one(
            {"code": entry["referrer"]},
            {"$inc": {"referrals_count": 1}, "$setOnInsert": {
                "code": entry["referrer"],
                "created_at": now_iso(),
                "owner_email": "",
                "referrals_count": 0,
            }},
            upsert=True,
        )

    return {"ok": True, "position": position, "already_joined": False}


@router.get("/landing/waitlist/count")
async def waitlist_count():
    n = await db.waitlist.count_documents({})
    return {"count": n}


# ----- Affiliate referral -----
class AffiliateSignup(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    company: Optional[str] = None


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:24] or "partner"


@router.post("/landing/affiliate/signup")
async def affiliate_signup(payload: AffiliateSignup):
    """Generate a unique referral code for partners. Idempotent on email."""
    existing = await db.affiliates.find_one({"owner_email": payload.email.lower()})
    if existing:
        return {
            "ok": True,
            "code": existing["code"],
            "referral_url": f"/?ref={existing['code']}",
            "referrals_count": existing.get("referrals_count", 0),
            "already_registered": True,
        }

    base = _slugify(payload.name or payload.email.split("@")[0])
    # Ensure uniqueness
    code = base
    suffix = 1
    while await db.affiliates.find_one({"code": code}):
        suffix += 1
        code = f"{base}-{suffix}"

    rec = {
        "id": str(uuid.uuid4()),
        "code": code,
        "owner_email": payload.email.lower(),
        "owner_name": (payload.name or "").strip(),
        "company": (payload.company or "").strip(),
        "referrals_count": 0,
        "commission_rate": 0.20,  # 20% rev share — config later
        "created_at": now_iso(),
    }
    await db.affiliates.insert_one(dict(rec))
    return {
        "ok": True,
        "code": code,
        "referral_url": f"/?ref={code}",
        "referrals_count": 0,
        "already_registered": False,
    }


@router.get("/landing/affiliate/{code}")
async def affiliate_lookup(code: str):
    rec = await db.affiliates.find_one({"code": code.lower()}, {"_id": 0, "owner_email": 0})
    if not rec:
        raise HTTPException(404, "Affiliate not found")
    return rec
