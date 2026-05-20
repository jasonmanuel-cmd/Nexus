"""Square Sandbox integration wrapper.

Supports:
- QuickPay one-time payment links (legacy demo flow)
- Customer + Card-on-file creation (Web Payments SDK nonce flow)
- Real recurring Subscriptions via Subscriptions API
- Webhook HMAC validation
"""
import asyncio
import hashlib
import hmac
import base64
import os
import uuid
from typing import Optional

from square import Square
from square.environment import SquareEnvironment


def _client() -> Square:
    env_name = os.environ.get("SQUARE_ENVIRONMENT", "sandbox").lower()
    env = SquareEnvironment.SANDBOX if env_name == "sandbox" else SquareEnvironment.PRODUCTION
    return Square(environment=env, token=os.environ["SQUARE_ACCESS_TOKEN"])


PACKAGES = {
    "operator": {
        "amount": 4800.0,
        "name": "Operator",
        "description": "3 AI agents · 500 prospects/mo",
        "plan_variation_env": "SQUARE_OPERATOR_PLAN_VARIATION_ID",
    },
    "scale": {
        "amount": 18500.0,
        "name": "Scale",
        "description": "7 AI agents · Unlimited prospects",
        "plan_variation_env": "SQUARE_SCALE_PLAN_VARIATION_ID",
    },
}


# ---------------- QuickPay link (legacy demo) ----------------
def _create_quick_pay_link_sync(package_id: str, redirect_url: str, user_id: str, email: str) -> dict:
    pkg = PACKAGES[package_id]
    location_id = os.environ["SQUARE_LOCATION_ID"]
    c = _client()
    resp = c.checkout.payment_links.create(
        idempotency_key=str(uuid.uuid4()),
        quick_pay={
            "name": f"Nexus AI · {pkg['name']} (first month)",
            "price_money": {"amount": int(pkg["amount"] * 100), "currency": "USD"},
            "location_id": location_id,
        },
        checkout_options={"redirect_url": redirect_url, "ask_for_shipping_address": False},
        pre_populated_data={"buyer_email": email},
        description=f"Nexus AI {pkg['name']} subscription · user={user_id}",
    )
    pl = resp.payment_link
    return {"id": pl.id, "url": pl.url, "order_id": getattr(pl, "order_id", None)}


async def create_payment_link(package_id: str, redirect_url: str, user_id: str, email: str) -> dict:
    return await asyncio.to_thread(_create_quick_pay_link_sync, package_id, redirect_url, user_id, email)


def _get_order_sync(order_id: str) -> dict:
    c = _client()
    resp = c.orders.get(order_id=order_id)
    o = resp.order
    return {"id": o.id, "state": getattr(o, "state", None)}


async def get_order(order_id: str) -> dict:
    return await asyncio.to_thread(_get_order_sync, order_id)


# ---------------- Customer + Card-on-file ----------------
def _upsert_customer_sync(email: str, name: str, user_id: str) -> str:
    c = _client()
    # Search for existing
    try:
        search = c.customers.search(query={"filter": {"email_address": {"exact": email}}})
        customers = getattr(search, "customers", None) or []
        if customers:
            return customers[0].id
    except Exception:
        pass
    parts = (name or "").split(" ", 1)
    given = parts[0] if parts else ""
    family = parts[1] if len(parts) > 1 else ""
    resp = c.customers.create(
        idempotency_key=str(uuid.uuid4()),
        given_name=given or "Nexus",
        family_name=family or "User",
        email_address=email,
        reference_id=user_id,
    )
    return resp.customer.id


async def upsert_customer(email: str, name: str, user_id: str) -> str:
    return await asyncio.to_thread(_upsert_customer_sync, email, name, user_id)


def _create_card_sync(customer_id: str, source_id: str, cardholder: str) -> str:
    """Create a card on file from a Web Payments SDK nonce (source_id)."""
    c = _client()
    resp = c.cards.create(
        idempotency_key=str(uuid.uuid4()),
        source_id=source_id,
        card={"customer_id": customer_id, "cardholder_name": cardholder or "Nexus User"},
    )
    return resp.card.id


async def create_card_on_file(customer_id: str, source_id: str, cardholder: str) -> str:
    return await asyncio.to_thread(_create_card_sync, customer_id, source_id, cardholder)


# ---------------- Subscriptions ----------------
def _create_subscription_sync(package_id: str, customer_id: str, card_id: str) -> dict:
    c = _client()
    location_id = os.environ["SQUARE_LOCATION_ID"]
    plan_variation_id = os.environ.get(PACKAGES[package_id]["plan_variation_env"])
    if not plan_variation_id:
        raise RuntimeError(f"Missing plan variation env for {package_id}")
    resp = c.subscriptions.create(
        idempotency_key=str(uuid.uuid4()),
        location_id=location_id,
        plan_variation_id=plan_variation_id,
        customer_id=customer_id,
        card_id=card_id,
    )
    s = resp.subscription
    return {
        "id": s.id,
        "status": getattr(s, "status", None),
        "created_at": getattr(s, "created_at", None),
        "plan_variation_id": getattr(s, "plan_variation_id", plan_variation_id),
        "card_id": getattr(s, "card_id", card_id),
        "customer_id": getattr(s, "customer_id", customer_id),
    }


async def create_subscription(package_id: str, customer_id: str, card_id: str) -> dict:
    return await asyncio.to_thread(_create_subscription_sync, package_id, customer_id, card_id)


def _cancel_subscription_sync(subscription_id: str) -> dict:
    c = _client()
    resp = c.subscriptions.cancel(subscription_id=subscription_id)
    s = resp.subscription
    return {"id": s.id, "status": getattr(s, "status", None), "canceled_date": getattr(s, "canceled_date", None)}


async def cancel_subscription(subscription_id: str) -> dict:
    return await asyncio.to_thread(_cancel_subscription_sync, subscription_id)


def _get_subscription_sync(subscription_id: str) -> dict:
    c = _client()
    resp = c.subscriptions.get(subscription_id=subscription_id)
    s = resp.subscription
    return {
        "id": s.id,
        "status": getattr(s, "status", None),
        "plan_variation_id": getattr(s, "plan_variation_id", None),
        "card_id": getattr(s, "card_id", None),
        "canceled_date": getattr(s, "canceled_date", None),
    }


async def get_subscription(subscription_id: str) -> dict:
    return await asyncio.to_thread(_get_subscription_sync, subscription_id)


# ---------------- Webhook validation ----------------
def validate_webhook(raw_body: bytes, signature: str) -> bool:
    if not signature:
        return False
    key = os.environ.get("SQUARE_WEBHOOK_SIGNATURE_KEY", "").encode("utf-8")
    url = os.environ.get("SQUARE_WEBHOOK_NOTIFICATION_URL", "").encode("utf-8")
    message = url + raw_body
    digest = hmac.new(key, message, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)
