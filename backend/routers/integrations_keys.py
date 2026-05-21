"""Per-user BYOK API keys + Hunter.io test endpoints.

Stored plaintext in `user_integration_keys` (one doc per user).
Never returned raw — only the last-4 mask on GET.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from deps import db, get_current_user, User
from integrations.hunter_client import (
    HunterError,
    HunterRateLimit,
    email_finder,
    email_verifier,
    find_decision_maker_email,
)

router = APIRouter(prefix="/integrations", tags=["integrations-keys"])


def _mask(key: str) -> str:
    if not key or len(key) < 6:
        return "****"
    return f"…{key[-4:]}"


async def get_user_key(user_id: str, provider: str) -> Optional[str]:
    """Return the raw API key for `provider` for this user, or None."""
    doc = await db.user_integration_keys.find_one({"user_id": user_id}, {"_id": 0}) or {}
    return doc.get(f"{provider}_api_key")


# ----- CRUD on per-user keys -----
class KeysUpdate(BaseModel):
    hunter_api_key: Optional[str] = None
    resend_api_key: Optional[str] = None
    resend_from_email: Optional[EmailStr] = None


@router.get("/keys")
async def get_keys(user: User = Depends(get_current_user)):
    """Returns booleans + masked tails (never the raw key)."""
    doc = await db.user_integration_keys.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    return {
        "hunter": {
            "connected": bool(doc.get("hunter_api_key")),
            "mask": _mask(doc.get("hunter_api_key", "")),
        },
        "resend": {
            "connected": bool(doc.get("resend_api_key")),
            "mask": _mask(doc.get("resend_api_key", "")),
            "from_email": doc.get("resend_from_email", ""),
        },
        "updated_at": doc.get("updated_at"),
    }


@router.put("/keys")
async def put_keys(payload: KeysUpdate, user: User = Depends(get_current_user)):
    update: dict = {}
    if payload.hunter_api_key is not None:
        update["hunter_api_key"] = payload.hunter_api_key.strip()
    if payload.resend_api_key is not None:
        update["resend_api_key"] = payload.resend_api_key.strip()
    if payload.resend_from_email is not None:
        update["resend_from_email"] = str(payload.resend_from_email)
    if not update:
        raise HTTPException(400, "Nothing to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.user_integration_keys.update_one(
        {"user_id": user.user_id},
        {"$set": {**update, "user_id": user.user_id}},
        upsert=True,
    )
    return {"ok": True, "updated": list(update.keys())}


@router.delete("/keys/{provider}")
async def delete_key(provider: str, user: User = Depends(get_current_user)):
    if provider not in {"hunter", "resend"}:
        raise HTTPException(400, "Unknown provider")
    unset = {f"{provider}_api_key": ""}
    if provider == "resend":
        unset["resend_from_email"] = ""
    await db.user_integration_keys.update_one(
        {"user_id": user.user_id},
        {"$unset": unset, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "cleared": provider}


# ----- Hunter test endpoints -----
class FinderRequest(BaseModel):
    company: Optional[str] = None
    domain: Optional[str] = None
    first_name: str
    last_name: str


@router.post("/hunter/find")
async def hunter_find(payload: FinderRequest, user: User = Depends(get_current_user)):
    api_key = await get_user_key(user.user_id, "hunter")
    if not api_key:
        raise HTTPException(400, "No Hunter API key configured. Add yours in Settings → Integrations.")
    if not (payload.company or payload.domain):
        raise HTTPException(400, "company or domain required")
    try:
        r = await find_decision_maker_email(
            api_key,
            company_name=payload.company or "",
            first_name=payload.first_name,
            last_name=payload.last_name,
            domain_hint=payload.domain,
        )
        return r
    except HunterRateLimit as e:
        raise HTTPException(429, {"message": e.message, "code": e.code})
    except HunterError as e:
        raise HTTPException(502, {"message": e.message, "code": e.code})


class VerifyRequest(BaseModel):
    email: EmailStr


@router.post("/hunter/verify")
async def hunter_verify(payload: VerifyRequest, user: User = Depends(get_current_user)):
    api_key = await get_user_key(user.user_id, "hunter")
    if not api_key:
        raise HTTPException(400, "No Hunter API key configured.")
    try:
        r = await email_verifier(api_key, payload.email)
        d = r.get("data") or {}
        return {"email": d.get("email"), "status": d.get("status"), "score": d.get("score")}
    except HunterError as e:
        raise HTTPException(502, {"message": e.message, "code": e.code})
