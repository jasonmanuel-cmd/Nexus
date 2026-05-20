"""Square Sandbox integration wrapper.

The Square Python SDK is synchronous; we use asyncio.to_thread for non-blocking I/O.
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
    "operator": {"amount": 4800.0, "name": "Operator", "description": "3 AI agents · 500 prospects/mo"},
    "scale":    {"amount": 18500.0, "name": "Scale",   "description": "7 AI agents · Unlimited prospects"},
}


def _create_quick_pay_link_sync(package_id: str, redirect_url: str, user_id: str, email: str) -> dict:
    """Create a Square hosted payment link (QuickPay) for the first month of a subscription."""
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
        checkout_options={
            "redirect_url": redirect_url,
            "ask_for_shipping_address": False,
        },
        pre_populated_data={"buyer_email": email},
        description=f"Nexus AI {pkg['name']} subscription · user={user_id}",
    )
    pl = resp.payment_link
    return {
        "id": pl.id,
        "url": pl.url,
        "order_id": getattr(pl, "order_id", None),
        "long_url": getattr(pl, "long_url", None),
    }


async def create_payment_link(package_id: str, redirect_url: str, user_id: str, email: str) -> dict:
    return await asyncio.to_thread(_create_quick_pay_link_sync, package_id, redirect_url, user_id, email)


def _get_payment_link_sync(link_id: str) -> dict:
    c = _client()
    resp = c.checkout.payment_links.get(id=link_id)
    pl = resp.payment_link
    order_id = getattr(pl, "order_id", None)
    return {
        "id": pl.id,
        "url": pl.url,
        "order_id": order_id,
    }


async def get_payment_link(link_id: str) -> dict:
    return await asyncio.to_thread(_get_payment_link_sync, link_id)


def _get_order_sync(order_id: str) -> dict:
    c = _client()
    resp = c.orders.get(order_id=order_id)
    o = resp.order
    return {
        "id": o.id,
        "state": getattr(o, "state", None),
        "total_money": getattr(o.total_money, "amount", None) if getattr(o, "total_money", None) else None,
        "tenders": [t.dict() if hasattr(t, "dict") else dict(t.__dict__) for t in (getattr(o, "tenders", None) or [])],
    }


async def get_order(order_id: str) -> dict:
    return await asyncio.to_thread(_get_order_sync, order_id)


def validate_webhook(raw_body: bytes, signature: str) -> bool:
    """Validate Square webhook HMAC-SHA256 signature."""
    if not signature:
        return False
    key = os.environ.get("SQUARE_WEBHOOK_SIGNATURE_KEY", "").encode("utf-8")
    url = os.environ.get("SQUARE_WEBHOOK_NOTIFICATION_URL", "").encode("utf-8")
    message = url + raw_body
    digest = hmac.new(key, message, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)
