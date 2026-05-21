"""Billing trial + subscription gating helpers."""
from datetime import datetime, timezone, timedelta
from typing import Tuple

from fastapi import HTTPException, APIRouter, Depends

from deps import db, get_current_user, User

router = APIRouter(prefix="/api", tags=["billing"])

TRIAL_DAYS = 7


async def get_trial_status(user_id: str) -> dict:
    udoc = await db.users.find_one({"user_id": user_id}, {"_id": 0}) or {}
    sub_active = bool(udoc.get("subscription_active", False))
    created_at_raw = udoc.get("created_at")
    trial_started: datetime
    if isinstance(created_at_raw, str):
        try:
            trial_started = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        except Exception:
            trial_started = datetime.now(timezone.utc)
    elif isinstance(created_at_raw, datetime):
        trial_started = created_at_raw
    else:
        trial_started = datetime.now(timezone.utc)
    if trial_started.tzinfo is None:
        trial_started = trial_started.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    trial_ends = trial_started + timedelta(days=TRIAL_DAYS)
    days_remaining = max(0, (trial_ends - now).days + (1 if (trial_ends - now).seconds > 0 else 0))
    trial_active = now < trial_ends and not sub_active
    locked = (not sub_active) and (now >= trial_ends)

    return {
        "subscription_active": sub_active,
        "trial_active": trial_active,
        "trial_started_at": trial_started.isoformat(),
        "trial_ends_at": trial_ends.isoformat(),
        "days_remaining": days_remaining,
        "locked": locked,
        "subscription_package": udoc.get("subscription_package"),
    }


async def require_unlocked(user: User = Depends(get_current_user)) -> User:
    """Raise 402 Payment Required if user's trial is over and no subscription."""
    status_ = await get_trial_status(user.user_id)
    if status_["locked"]:
        raise HTTPException(
            402,
            detail={
                "error": "trial_expired",
                "message": f"Your {TRIAL_DAYS}-day Nexus AI trial has ended. Activate a subscription to keep your autonomous CRO running.",
                "upgrade_url": "/app/subscribe",
            },
        )
    return user


@router.get("/billing/trial-status")
async def trial_status(user: User = Depends(get_current_user)):
    return await get_trial_status(user.user_id)
