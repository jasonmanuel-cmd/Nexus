"""User preferences (auto-send threshold, etc.)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from deps import db, get_current_user, User

router = APIRouter(prefix="/api/settings", tags=["settings"])


class UserSettings(BaseModel):
    auto_send_enabled: bool = False
    auto_send_threshold: int = 85  # 50-100
    auto_send_deal_value_cap: int = 50000  # $ — drafts for deals above this stay manual


@router.get("")
async def get_settings(user: User = Depends(get_current_user)):
    u = await db.users.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    return {
        "auto_send_enabled": bool(u.get("auto_send_enabled", False)),
        "auto_send_threshold": int(u.get("auto_send_threshold", 85)),
        "auto_send_deal_value_cap": int(u.get("auto_send_deal_value_cap", 50000)),
    }


@router.put("")
async def update_settings(payload: UserSettings, user: User = Depends(get_current_user)):
    threshold = max(50, min(100, payload.auto_send_threshold))
    cap = max(0, min(10_000_000, payload.auto_send_deal_value_cap))
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {
            "auto_send_enabled": payload.auto_send_enabled,
            "auto_send_threshold": threshold,
            "auto_send_deal_value_cap": cap,
        }},
    )
    return {"auto_send_enabled": payload.auto_send_enabled, "auto_send_threshold": threshold, "auto_send_deal_value_cap": cap}
