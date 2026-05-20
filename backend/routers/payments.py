"""Payments router: Square Checkout (QuickPay), recurring Subscriptions, webhook, packages, config."""
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from deps import db, get_current_user, now_iso, User, Activity
from integrations import square_client as sq
from integrations.notifications import send_slack
from integrations.square_errors import sanitize_square_error

router = APIRouter(prefix="/api", tags=["payments"])


PACKAGES = sq.PACKAGES


class CheckoutCreate(BaseModel):
    package_id: str
    origin_url: str


@router.get("/payments/packages")
async def list_packages():
    return {"packages": [{"id": k, "amount": v["amount"], "name": v["name"], "description": v["description"]} for k, v in PACKAGES.items()]}


@router.get("/payments/config")
async def payments_config():
    return {
        "application_id": os.environ.get("SQUARE_APPLICATION_ID"),
        "location_id": os.environ.get("SQUARE_LOCATION_ID"),
        "environment": os.environ.get("SQUARE_ENVIRONMENT", "sandbox"),
    }


# ---- QuickPay (legacy demo) ----
@router.post("/payments/checkout/session")
async def create_checkout(payload: CheckoutCreate, user: User = Depends(get_current_user)):
    if payload.package_id not in PACKAGES:
        raise HTTPException(400, "Invalid package")
    if not os.environ.get("SQUARE_ACCESS_TOKEN"):
        raise HTTPException(500, "Square not configured")
    origin = payload.origin_url.rstrip("/")
    redirect_url = f"{origin}/app/checkout-return"
    try:
        link = await sq.create_payment_link(payload.package_id, redirect_url, user.user_id, user.email)
    except Exception as e:
        logging.error(f"Square link create failed: {e}")
        raise HTTPException(502, sanitize_square_error(e))
    await db.payment_transactions.insert_one({
        "session_id": link["id"],
        "order_id": link.get("order_id"),
        "user_id": user.user_id,
        "email": user.email,
        "package_id": payload.package_id,
        "amount": PACKAGES[payload.package_id]["amount"],
        "currency": "usd",
        "payment_status": "initiated",
        "status": "open",
        "provider": "square",
        "metadata": {"package_id": payload.package_id, "user_id": user.user_id},
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    return {"url": link["url"], "session_id": link["id"]}


@router.get("/payments/checkout/status/{session_id}")
async def checkout_status(session_id: str, user: User = Depends(get_current_user)):
    txn = await db.payment_transactions.find_one({"session_id": session_id, "user_id": user.user_id}, {"_id": 0})
    if not txn:
        raise HTTPException(404, "Transaction not found")
    detected_paid = False
    order_id = txn.get("order_id")
    try:
        if order_id:
            order = await sq.get_order(order_id)
            if (order.get("state") or "").upper() == "COMPLETED":
                detected_paid = True
    except Exception as e:
        logging.warning(f"Square order lookup failed: {e}")
    new_status = "paid" if detected_paid else txn.get("payment_status", "initiated")
    if detected_paid and txn["payment_status"] != "paid":
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": "paid", "status": "complete", "updated_at": now_iso()}},
        )
        await db.users.update_one(
            {"user_id": user.user_id},
            {"$set": {
                "subscription_package": txn.get("package_id"),
                "subscription_active": True,
                "subscribed_at": now_iso(),
                "renews_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            }},
        )
    return {
        "session_id": session_id,
        "status": "complete" if detected_paid else txn.get("status", "open"),
        "payment_status": new_status,
        "amount_total": int(txn.get("amount", 0) * 100),
        "currency": txn.get("currency", "usd"),
        "package_id": txn.get("package_id"),
        "provider": "square",
    }


# ---- Recurring Subscriptions (real) ----
class SubscribePayload(BaseModel):
    package_id: str
    source_id: str
    cardholder_name: Optional[str] = None


@router.post("/payments/subscribe")
async def create_recurring(payload: SubscribePayload, user: User = Depends(get_current_user)):
    if payload.package_id not in PACKAGES:
        raise HTTPException(400, "Invalid package")
    try:
        customer_id = await sq.upsert_customer(email=user.email, name=user.name or user.email, user_id=user.user_id)
        card_id = await sq.create_card_on_file(customer_id=customer_id, source_id=payload.source_id, cardholder=payload.cardholder_name or user.name or user.email)
        sub = await sq.create_subscription(payload.package_id, customer_id, card_id)
    except Exception as e:
        logging.error(f"Square subscription error: {e}")
        raise HTTPException(502, sanitize_square_error(e))
    await db.payment_transactions.insert_one({
        "session_id": sub["id"], "subscription_id": sub["id"],
        "user_id": user.user_id, "email": user.email,
        "package_id": payload.package_id, "amount": PACKAGES[payload.package_id]["amount"],
        "currency": "usd", "payment_status": "paid", "status": "complete",
        "provider": "square_subscription",
        "square_customer_id": customer_id, "square_card_id": card_id,
        "metadata": {"package_id": payload.package_id, "user_id": user.user_id},
        "created_at": now_iso(), "updated_at": now_iso(),
    })
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {
            "subscription_package": payload.package_id,
            "subscription_active": True,
            "subscription_id": sub["id"],
            "square_customer_id": customer_id,
            "square_card_id": card_id,
            "subscribed_at": now_iso(),
            "renews_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }},
    )
    act = Activity(
        user_id=user.user_id, agent="Pipeline-Analyst",
        action="Recurring subscription activated",
        target=PACKAGES[payload.package_id]["name"],
        outcome=f"${PACKAGES[payload.package_id]['amount']:,.0f}/mo",
        status="closing",
    )
    await db.activities.insert_one(dict(act.model_dump()))
    await send_slack(db, text=f":rocket: *{user.email}* started recurring *{PACKAGES[payload.package_id]['name']}* (${PACKAGES[payload.package_id]['amount']:,.0f}/mo)", user_id=user.user_id, kind="subscription.recurring.activated")
    return {"ok": True, "subscription_id": sub["id"], "status": sub.get("status")}


@router.get("/payments/subscription")
async def get_subscription_state(user: User = Depends(get_current_user)):
    u = await db.users.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    return {
        "active": bool(u.get("subscription_active")),
        "package_id": u.get("subscription_package"),
        "package": PACKAGES.get(u.get("subscription_package") or "", None),
        "subscribed_at": u.get("subscribed_at"),
        "renews_at": u.get("renews_at"),
    }


@router.post("/payments/subscription/cancel")
async def cancel_recurring(user: User = Depends(get_current_user)):
    u = await db.users.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    if not u.get("subscription_active"):
        raise HTTPException(404, "No active subscription")
    sub_id = u.get("subscription_id")
    canceled_remote = None
    if sub_id:
        try:
            canceled_remote = await sq.cancel_subscription(sub_id)
        except Exception as e:
            logging.warning(f"Square cancel failed (still marking locally): {e}")
    pkg_id = u.get("subscription_package")
    await db.users.update_one({"user_id": user.user_id}, {"$set": {"subscription_active": False, "canceled_at": now_iso()}})
    act = Activity(user_id=user.user_id, agent="Pipeline-Analyst", action="Subscription canceled", target=PACKAGES.get(pkg_id or "", {}).get("name", "Plan"), status="idle")
    await db.activities.insert_one(dict(act.model_dump()))
    await send_slack(db, text=f":wave: *{user.email}* canceled *{PACKAGES.get(pkg_id or '', {}).get('name', 'Plan')}* plan", user_id=user.user_id, kind="subscription.canceled")
    return {"ok": True, "canceled_package": pkg_id, "square_status": (canceled_remote or {}).get("status")}


@router.post("/webhook/square")
async def square_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("x-square-hmacsha256-signature", "")
    if not sq.validate_webhook(raw, sig):
        return Response(status_code=400)
    try:
        evt = json.loads(raw.decode("utf-8"))
    except Exception:
        return Response(status_code=400)
    event_type = evt.get("type", "")
    data = evt.get("data", {}).get("object", {}) or {}
    if event_type.startswith("payment."):
        payment = data.get("payment") or {}
        order_id = payment.get("order_id")
        status = (payment.get("status") or "").upper()
        if order_id and status == "COMPLETED":
            await db.payment_transactions.update_one(
                {"order_id": order_id},
                {"$set": {"payment_status": "paid", "status": "complete", "updated_at": now_iso()}},
            )
            txn = await db.payment_transactions.find_one({"order_id": order_id}, {"_id": 0})
            if txn:
                await db.users.update_one(
                    {"user_id": txn["user_id"]},
                    {"$set": {
                        "subscription_package": txn.get("package_id"),
                        "subscription_active": True,
                        "subscribed_at": now_iso(),
                        "renews_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                    }},
                )
    return {"ok": True}
