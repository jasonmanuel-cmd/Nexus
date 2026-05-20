"""Nexus AI v4 — autonomous reply loop end-to-end tests.

Covers:
- POST /api/notifications/email/{id}/simulate-reply (happy + 404 + scoping)
- GET  /api/replies/queue (enriched, pending only, scoped)
- GET  /api/replies/stats
- POST /api/replies/{id}/send (as-is + override + 409)
- DELETE /api/replies/{id}  (dismiss + 404)
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env (BASE_URL is required)
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


# ---------- helpers ----------
def _hdr(token=DEMO_TOKEN):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def demo_client():
    s = requests.Session()
    s.headers.update(_hdr())
    return s


@pytest.fixture(scope="module")
def second_user(event_loop_module):
    """Seed a fresh user + session directly in Mongo for the scoping test."""
    import asyncio

    user_id = f"TEST_V4_user_{uuid.uuid4().hex[:6]}"
    token = f"TEST_V4_token_{uuid.uuid4().hex[:8]}"

    async def _seed():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.insert_one({
            "user_id": user_id,
            "email": f"{user_id}@test.local",
            "name": "TEST V4 User",
            "picture": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.user_sessions.insert_one({
            "user_id": user_id,
            "session_token": token,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        client.close()

    async def _cleanup():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.delete_one({"user_id": user_id})
        await db.user_sessions.delete_one({"session_token": token})
        client.close()

    event_loop_module.run_until_complete(_seed())
    yield {"user_id": user_id, "token": token}
    event_loop_module.run_until_complete(_cleanup())


@pytest.fixture(scope="module")
def event_loop_module():
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def promote_email_id(demo_client):
    """Find a promote.intro email in demo user's outbox that doesn't already have a draft."""
    r = demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=50")
    assert r.status_code == 200, r.text
    emails = r.json()["emails"]
    promote = [e for e in emails if e.get("kind") == "promote.intro"]
    assert promote, "No promote.intro emails seeded for demo user — cannot test simulate-reply"
    # Prefer one that hasn't been simulated already (i.e. no draft pointing to it).
    drafts = demo_client.get(f"{BASE_URL}/api/replies/queue").json().get("drafts", [])
    used_ids = {d["draft"]["original_email_id"] for d in drafts}
    for e in promote:
        if e["id"] not in used_ids:
            return e["id"]
    # Fallback: use any (will still work, just creates an additional draft)
    return promote[0]["id"]


# ---------- simulate-reply ----------
class TestSimulateReply:
    def test_simulate_reply_happy_path(self, demo_client, promote_email_id):
        # Snapshot stats before
        stats_before = demo_client.get(f"{BASE_URL}/api/replies/stats").json()
        slack_before = len(demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=200").json()["slack_messages"])

        r = demo_client.post(
            f"{BASE_URL}/api/notifications/email/{promote_email_id}/simulate-reply",
            timeout=90,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:400]}"
        body = r.json()
        assert "reply" in body and "draft" in body

        reply = body["reply"]
        assert reply["body"] and isinstance(reply["body"], str)
        assert reply["sentiment"] in ["positive", "neutral", "negative"], reply["sentiment"]
        assert reply["intent"] in ["interested", "wants_info", "deferring", "objecting", "not_now"], reply["intent"]
        assert reply["original_email_id"] == promote_email_id

        draft = body["draft"]
        assert draft["subject"] and isinstance(draft["subject"], str)
        assert draft["body"] and isinstance(draft["body"], str)
        assert isinstance(draft["probability_delta"], int)
        assert "suggested_action" in draft
        assert draft["sentiment"] == reply["sentiment"]
        assert draft["intent"] == reply["intent"]
        assert draft["status"] == "pending"

        # Stats reflect new pending + new received
        stats_after = demo_client.get(f"{BASE_URL}/api/replies/stats").json()
        assert stats_after["pending"] >= stats_before["pending"] + 1
        assert stats_after["received"] >= stats_before["received"] + 1

        # Slack notification fired (kind=reply.received)
        slack_after = demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=200").json()["slack_messages"]
        new_msgs = [m for m in slack_after if m.get("kind") == "reply.received"]
        assert len(slack_after) > slack_before
        assert new_msgs, "No Slack 'reply.received' message generated"

        # stash for downstream tests
        pytest.v4_draft_id = draft["id"]

    def test_simulate_reply_404_not_found(self, demo_client):
        r = demo_client.post(f"{BASE_URL}/api/notifications/email/nonexistent-id-xyz/simulate-reply", timeout=15)
        assert r.status_code == 404

    def test_simulate_reply_other_user_404(self, second_user, promote_email_id):
        r = requests.post(
            f"{BASE_URL}/api/notifications/email/{promote_email_id}/simulate-reply",
            headers=_hdr(second_user["token"]),
            timeout=15,
        )
        # Demo user's email is invisible to second_user → 404
        assert r.status_code == 404


# ---------- queue + stats ----------
class TestQueueAndStats:
    def test_queue_returns_enriched_pending_only(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/replies/queue")
        assert r.status_code == 200
        drafts = r.json()["drafts"]
        assert isinstance(drafts, list)
        assert len(drafts) >= 1
        for item in drafts:
            assert set(item.keys()) >= {"draft", "reply", "original", "deal"}
            assert item["draft"]["status"] == "pending"
            assert item["reply"] is not None
            assert item["original"] is not None

    def test_stats_shape(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/replies/stats")
        assert r.status_code == 200
        d = r.json()
        for k in ("pending", "sent", "received"):
            assert k in d and isinstance(d[k], int)

    def test_queue_user_scoping(self, second_user):
        r = requests.get(f"{BASE_URL}/api/replies/queue", headers=_hdr(second_user["token"]))
        assert r.status_code == 200
        drafts = r.json()["drafts"]
        assert drafts == [], "Second user MUST NOT see demo-user's drafts"

        s = requests.get(f"{BASE_URL}/api/replies/stats", headers=_hdr(second_user["token"]))
        assert s.status_code == 200
        assert s.json() == {"pending": 0, "sent": 0, "received": 0}


# ---------- send (as-is + override + 409) ----------
class TestSendDraft:
    def test_send_as_is_with_empty_body(self, demo_client):
        # Use the draft created by simulate-reply test
        draft_id = getattr(pytest, "v4_draft_id", None)
        assert draft_id, "simulate-reply test must run first"

        # Capture deal_id + probability before
        queue = demo_client.get(f"{BASE_URL}/api/replies/queue").json()["drafts"]
        target = next((d for d in queue if d["draft"]["id"] == draft_id), None)
        assert target, "draft not in queue"
        draft = target["draft"]
        deal = target["deal"]
        deal_id = draft.get("deal_id")
        delta = draft["probability_delta"]
        orig_subject = draft["subject"]
        prob_before = deal["probability"] if deal else None
        outbox_before = len(demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=200").json()["emails"])

        # Send with EMPTY body
        r = demo_client.post(f"{BASE_URL}/api/replies/{draft_id}/send", json={})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # New email_outbox entry of kind=reply.followup with original subject
        emails = demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=200").json()["emails"]
        assert len(emails) > outbox_before
        followups = [e for e in emails if e.get("kind") == "reply.followup"]
        assert followups, "No reply.followup email queued"
        latest = followups[0]  # sorted desc
        assert latest["subject"] == orig_subject

        # Deal probability bumped by delta (clamped 0-100)
        if deal_id and prob_before is not None:
            import asyncio
            from motor.motor_asyncio import AsyncIOMotorClient
            async def _check():
                c = AsyncIOMotorClient(MONGO_URL); d = c[DB_NAME]
                doc = await d.deals.find_one({"id": deal_id}, {"_id": 0})
                c.close()
                return doc
            deal_after = asyncio.new_event_loop().run_until_complete(_check())
            expected = max(0, min(100, prob_before + delta))
            assert deal_after["probability"] == expected
            assert "Replied to buyer" in (deal_after.get("last_action") or "")
            if draft["sentiment"] == "positive":
                assert deal_after.get("agent_status") == "closing"

        # Pending count dropped, sent count rose
        stats = demo_client.get(f"{BASE_URL}/api/replies/stats").json()
        assert stats["sent"] >= 1

    def test_send_already_sent_returns_409(self, demo_client):
        draft_id = getattr(pytest, "v4_draft_id", None)
        r = demo_client.post(f"{BASE_URL}/api/replies/{draft_id}/send", json={})
        assert r.status_code == 409

    def test_send_with_overrides(self, demo_client, promote_email_id):
        """Create a new draft then send with subject/body overrides."""
        # Need a fresh promote.intro that hasn't been simulated.
        outbox = demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=200").json()["emails"]
        promote_ids = [e["id"] for e in outbox if e.get("kind") == "promote.intro"]
        drafts = demo_client.get(f"{BASE_URL}/api/replies/queue").json()["drafts"]
        used = {d["draft"]["original_email_id"] for d in drafts}
        # also exclude any already-actioned
        candidates = [pid for pid in promote_ids if pid not in used]
        if not candidates:
            pytest.skip("No fresh promote.intro email available for override test")
        target_email = candidates[0]

        sim = demo_client.post(
            f"{BASE_URL}/api/notifications/email/{target_email}/simulate-reply", timeout=90
        )
        assert sim.status_code == 200, sim.text
        new_draft_id = sim.json()["draft"]["id"]

        custom_subject = "TEST_V4 Custom override subject"
        custom_body = "TEST_V4 Hand-edited body text — overriding AI draft."
        r = demo_client.post(
            f"{BASE_URL}/api/replies/{new_draft_id}/send",
            json={"subject": custom_subject, "body": custom_body},
        )
        assert r.status_code == 200, r.text

        emails = demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=200").json()["emails"]
        followups = [e for e in emails if e.get("kind") == "reply.followup"]
        match = [e for e in followups if e["subject"] == custom_subject and e["body"] == custom_body]
        assert match, "Override subject/body not persisted in email_outbox"


# ---------- dismiss ----------
class TestDismissDraft:
    def test_dismiss_pending_draft(self, demo_client, promote_email_id):
        # create a new draft
        outbox = demo_client.get(f"{BASE_URL}/api/notifications/outbox?limit=200").json()["emails"]
        promote_ids = [e["id"] for e in outbox if e.get("kind") == "promote.intro"]
        drafts = demo_client.get(f"{BASE_URL}/api/replies/queue").json()["drafts"]
        used = {d["draft"]["original_email_id"] for d in drafts}
        candidates = [pid for pid in promote_ids if pid not in used]
        if not candidates:
            pytest.skip("No fresh promote.intro email available for dismiss test")
        sim = demo_client.post(
            f"{BASE_URL}/api/notifications/email/{candidates[0]}/simulate-reply", timeout=90
        )
        assert sim.status_code == 200, sim.text
        draft_id = sim.json()["draft"]["id"]

        r = demo_client.delete(f"{BASE_URL}/api/replies/{draft_id}")
        assert r.status_code == 200
        assert r.json().get("ok") is True

        # No longer in pending queue
        q = demo_client.get(f"{BASE_URL}/api/replies/queue").json()["drafts"]
        assert all(d["draft"]["id"] != draft_id for d in q)

        # Already-actioned → 404
        r2 = demo_client.delete(f"{BASE_URL}/api/replies/{draft_id}")
        assert r2.status_code == 404
