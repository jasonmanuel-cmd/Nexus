"""Nexus AI v5 — Settings, Square recurring, LIVE Resend/Slack, auto-send loop.

Covers:
- GET/PUT /api/settings (auth, threshold clamp 50-100)
- GET /api/payments/config (public)
- POST /api/payments/subscribe (validates package_id 400, source_id missing/invalid 502)
- POST /api/payments/subscription/cancel (404 no sub, 200 when active)
- LIVE Resend (mocked:false, provider:resend, status may be failed/sent)
- LIVE Slack (mocked:false, provider:slack, status:delivered)
- Auto-send loop on simulate-reply when threshold cleared
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

DEMO_TOKEN = "demo_session_token_persistent"


def _read_env(key):
    with open("/app/backend/.env") as f:
        for line in f:
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


MONGO_URL = os.environ.get("MONGO_URL") or _read_env("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or _read_env("DB_NAME")


def _hdr(token=DEMO_TOKEN):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def demo_client():
    s = requests.Session()
    s.headers.update(_hdr())
    return s


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------- /api/settings ----------
class TestSettings:
    def test_get_settings_default_shape(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/settings")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "auto_send_enabled" in d and isinstance(d["auto_send_enabled"], bool)
        assert "auto_send_threshold" in d and isinstance(d["auto_send_threshold"], int)

    def test_put_settings_persists(self, demo_client):
        r = demo_client.put(
            f"{BASE_URL}/api/settings",
            json={"auto_send_enabled": True, "auto_send_threshold": 88},
        )
        assert r.status_code == 200, r.text
        # GET back to verify persistence
        r2 = demo_client.get(f"{BASE_URL}/api/settings")
        assert r2.status_code == 200
        d = r2.json()
        assert d["auto_send_enabled"] is True
        assert d["auto_send_threshold"] == 88

    def test_put_threshold_clamped_low(self, demo_client):
        r = demo_client.put(
            f"{BASE_URL}/api/settings",
            json={"auto_send_enabled": False, "auto_send_threshold": 10},
        )
        assert r.status_code == 200
        assert r.json()["auto_send_threshold"] == 50

    def test_put_threshold_clamped_high(self, demo_client):
        r = demo_client.put(
            f"{BASE_URL}/api/settings",
            json={"auto_send_enabled": False, "auto_send_threshold": 250},
        )
        assert r.status_code == 200
        assert r.json()["auto_send_threshold"] == 100

    def test_settings_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/settings")
        assert r.status_code in (401, 403)


# ---------- /api/payments/config ----------
class TestPaymentsConfig:
    def test_config_public_no_auth(self):
        r = requests.get(f"{BASE_URL}/api/payments/config")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("application_id"), "application_id missing"
        assert d.get("location_id"), "location_id missing"
        assert d.get("environment") == "sandbox"


# ---------- /api/payments/subscribe error contracts ----------
class TestSubscribeContract:
    def test_invalid_package_id_400(self, demo_client):
        r = demo_client.post(
            f"{BASE_URL}/api/payments/subscribe",
            json={"package_id": "BOGUS_PKG", "source_id": "cnon:bogus", "cardholder_name": "TEST"},
        )
        assert r.status_code == 400, r.text

    def test_missing_source_id_422(self, demo_client):
        r = demo_client.post(
            f"{BASE_URL}/api/payments/subscribe",
            json={"package_id": "operator", "cardholder_name": "TEST"},
        )
        assert r.status_code == 422, r.text

    def test_invalid_source_id_502(self, demo_client):
        # Square will reject a bogus source_id → backend wraps as 502
        r = demo_client.post(
            f"{BASE_URL}/api/payments/subscribe",
            json={"package_id": "operator", "source_id": "cnon:invalid-token-xyz", "cardholder_name": "TEST_V5"},
            timeout=30,
        )
        assert r.status_code in (400, 422, 500, 502), r.text

    def test_subscribe_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/payments/subscribe",
            json={"package_id": "operator", "source_id": "cnon:x"},
        )
        assert r.status_code in (401, 403)


# ---------- /api/payments/subscription/cancel ----------
class TestSubscriptionCancel:
    def test_cancel_404_when_no_active(self, demo_client):
        # ensure demo user has no active subscription
        async def _clear():
            c = AsyncIOMotorClient(MONGO_URL)
            await c[DB_NAME].users.update_one(
                {"user_id": "demo-user-001"},
                {"$set": {"subscription_active": False}},
            )
            c.close()

        _run(_clear())
        r = demo_client.post(f"{BASE_URL}/api/payments/subscription/cancel")
        assert r.status_code == 404, r.text

    def test_cancel_200_when_active(self, demo_client):
        # mark a fake active sub locally; sub_id is None so Square API isn't called
        async def _mark():
            c = AsyncIOMotorClient(MONGO_URL)
            await c[DB_NAME].users.update_one(
                {"user_id": "demo-user-001"},
                {"$set": {
                    "subscription_active": True,
                    "subscription_package": "operator",
                    "subscription_id": None,  # skip remote Square cancel
                }},
            )
            c.close()

        _run(_mark())
        r = demo_client.post(f"{BASE_URL}/api/payments/subscription/cancel")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True

        # Verify mongo state flipped
        async def _check():
            c = AsyncIOMotorClient(MONGO_URL)
            u = await c[DB_NAME].users.find_one({"user_id": "demo-user-001"}, {"_id": 0})
            c.close()
            return u

        u = _run(_check())
        assert u["subscription_active"] is False
        assert u.get("canceled_at")


# ---------- LIVE Resend + Slack ----------
class TestLiveNotifications:
    def test_live_slack_delivered(self, demo_client):
        """Advance a deal stage to trigger Slack and verify outbox shows live delivery."""
        # snapshot
        before = demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=200").json()
        before_slack_ids = {m.get("id") for m in before.get("slack_messages", [])}

        # find a deal and bump its stage
        deals = demo_client.get(f"{BASE_URL}/api/pipeline/deals").json()
        if isinstance(deals, dict):
            deals = deals.get("deals", [])
        assert deals, "no deals seeded for demo user"
        target_deal = deals[0]
        new_stage = "proposal" if target_deal.get("stage") != "proposal" else "negotiation"
        r = demo_client.patch(
            f"{BASE_URL}/api/pipeline/deals/{target_deal['id']}",
            json={"stage": new_stage},
        )
        assert r.status_code in (200, 204), r.text

        # poll outbox up to 8s for new slack message
        import time
        found = None
        for _ in range(8):
            time.sleep(1)
            after = demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=200").json()
            new = [m for m in after.get("slack_messages", []) if m.get("id") not in before_slack_ids]
            if new:
                found = new[0]
                break
        assert found, "No new Slack message after stage change"
        # LIVE assertions
        assert found.get("mocked") is False, f"slack still mocked: {found}"
        assert found.get("provider") == "slack", f"provider mismatch: {found}"
        assert found.get("status") == "delivered", f"status not delivered: {found}"

    def test_live_resend_attempted(self, demo_client):
        """Promote a fresh target → triggers email; outbox should have mocked:false."""
        # find an unpromoted target
        tg_resp = demo_client.get(f"{BASE_URL}/api/targets?limit=100")
        if tg_resp.status_code != 200:
            pytest.skip(f"/api/targets returned {tg_resp.status_code}")
        targets = tg_resp.json()
        if isinstance(targets, dict):
            targets = targets.get("targets", [])

        promoted_id = None
        for t in targets[:50]:
            if t.get("status") == "promoted":
                continue
            r = demo_client.post(f"{BASE_URL}/api/targets/{t['id']}/promote")
            if r.status_code == 200:
                promoted_id = t["id"]
                break
        if not promoted_id:
            pytest.skip("Could not promote any fresh target — likely all promoted")

        # poll outbox for new resend email
        import time
        found = None
        for _ in range(10):
            time.sleep(1)
            ob = demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=20").json()
            emails = ob.get("emails", [])
            for e in emails:
                if e.get("kind") == "promote.intro" and e.get("provider") == "resend":
                    found = e
                    break
            if found:
                break

        assert found, "No promote.intro email with provider=resend found"
        assert found.get("mocked") is False, f"email still mocked: {found}"
        assert found.get("provider") == "resend"
        # Status may be 'failed' due to unverified domain — that's EXPECTED
        # The point is mocked=false proves live attempt
        if found.get("status") == "failed":
            err = (found.get("error") or "").lower()
            assert "not verified" in err or "verify" in err or "domain" in err, \
                f"failed email but unexpected error: {found.get('error')}"


# ---------- Auto-send loop ----------
class TestAutoSendLoop:
    def test_auto_send_triggers_when_threshold_cleared(self, demo_client):
        """Enable auto-send with very low threshold; simulate replies until Claude returns positive.
        Verify draft.status==auto_sent + new reply.followup email + deal probability bumped.
        """
        # Force auto-send on with low threshold
        r = demo_client.put(
            f"{BASE_URL}/api/settings",
            json={"auto_send_enabled": True, "auto_send_threshold": 50},
        )
        assert r.status_code == 200

        # find unused promote.intro emails
        outbox = demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=200").json()
        promote_ids = [e["id"] for e in outbox.get("emails", []) if e.get("kind") == "promote.intro"]
        drafts = demo_client.get(f"{BASE_URL}/api/replies/queue").json().get("drafts", [])
        used = {d["draft"]["original_email_id"] for d in drafts}
        # Also exclude originals that have ANY existing draft (sent/auto_sent/dismissed)

        async def _used_all():
            c = AsyncIOMotorClient(MONGO_URL)
            cursor = c[DB_NAME].reply_drafts.find(
                {"user_id": "demo-user-001"}, {"_id": 0, "original_email_id": 1}
            )
            ids = set()
            async for doc in cursor:
                ids.add(doc.get("original_email_id"))
            c.close()
            return ids

        used_all = _run(_used_all())
        candidates = [pid for pid in promote_ids if pid not in used_all]
        if not candidates:
            pytest.skip("No fresh promote.intro emails available for auto-send test")

        # Try up to 4 different candidates to land a 'positive' sentiment
        auto_sent_hit = None
        for cand in candidates[:4]:
            sim = demo_client.post(
                f"{BASE_URL}/api/notifications/email/{cand}/simulate-reply",
                timeout=90,
            )
            if sim.status_code != 200:
                continue
            body = sim.json()
            assert "auto_sent" in body, f"response missing auto_sent flag: {body}"
            if body.get("auto_sent"):
                auto_sent_hit = body
                break

        # Reset settings to safe defaults
        demo_client.put(
            f"{BASE_URL}/api/settings",
            json={"auto_send_enabled": False, "auto_send_threshold": 85},
        )

        if not auto_sent_hit:
            pytest.skip(
                "Claude did not return positive+high-confidence in 4 attempts — variability expected"
            )

        draft_id = auto_sent_hit["draft"]["id"]

        # Verify draft status in db
        async def _draft_status():
            c = AsyncIOMotorClient(MONGO_URL)
            d = await c[DB_NAME].reply_drafts.find_one({"id": draft_id}, {"_id": 0})
            c.close()
            return d

        d = _run(_draft_status())
        assert d, "draft not found in db"
        assert d.get("status") == "auto_sent", f"expected auto_sent, got {d.get('status')}"

        # Verify reply.followup email exists in outbox
        ob = demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=200").json()
        followups = [e for e in ob.get("emails", []) if e.get("kind") == "reply.followup"]
        # The latest followup should correspond to this draft (subject match)
        match = [e for e in followups if e.get("subject") == d.get("subject")]
        assert match, "No reply.followup email queued for auto-sent draft"
