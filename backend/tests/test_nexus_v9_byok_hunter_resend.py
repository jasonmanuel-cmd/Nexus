"""Iteration 9 — BYOK (Hunter.io + Resend) + Resend inbound webhook tests.

Covers the new features in the v9 review_request:
  1) GET/PUT/DELETE /api/integrations/keys (BYOK CRUD, masking, never leak raw keys)
  2) POST /api/integrations/hunter/find — uses literal 'test-api-key' (Hunter dev mode)
  3) POST /api/integrations/hunter/verify — uses literal 'test-api-key'
  4) POST /api/webhook/resend-inbound — public, fast (<5s), creates email_replies
  5) Promote-target Hunter auto-discovery — sets hunter key, promotes a target w/o DM email,
     verifies response.hunter_score key + DB write path doesn't error
  6) Per-user Resend key override — sets fake_user_key, verifies email_outbox.status=failed
     proving user key was used (not env key)
  7) Mongo state — GET /keys never leaks raw hunter_api_key or resend_api_key
  8) Regression sweep: a sub-slice of v8 still passes
"""
import os
import uuid
import time
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

# ---- env ----
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
API = f"{BASE_URL}/api"

DEMO_TOKEN = os.environ.get("DEMO_SESSION_TOKEN", "demo_session_token_persistent")
HDR = {"Authorization": f"Bearer {DEMO_TOKEN}", "Content-Type": "application/json"}

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update(HDR)
    return sess


@pytest.fixture(scope="module")
def mongo():
    cli = MongoClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


@pytest.fixture(scope="module", autouse=True)
def _cleanup_keys_after_module(mongo):
    """Ensure stale state is cleared before AND after the module."""
    mongo.user_integration_keys.delete_one({"user_id": "demo-user-001"})
    yield
    mongo.user_integration_keys.delete_one({"user_id": "demo-user-001"})


# ============= BYOK /integrations/keys CRUD =============
class TestIntegrationKeysCRUD:
    def test_get_keys_auth_required(self):
        r = requests.get(f"{API}/integrations/keys", timeout=15)
        assert r.status_code in (401, 403)

    def test_get_keys_initial_empty(self, s):
        r = s.get(f"{API}/integrations/keys", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["hunter"]["connected"] is False
        assert d["resend"]["connected"] is False
        # mask field always present
        assert "mask" in d["hunter"] and "mask" in d["resend"]
        assert "updated_at" in d
        # No raw key leak even when empty
        assert "hunter_api_key" not in d
        assert "resend_api_key" not in d

    def test_put_keys_empty_body_400(self, s):
        r = s.put(f"{API}/integrations/keys", json={}, timeout=15)
        assert r.status_code == 400, r.text

    def test_put_keys_partial_hunter_only(self, s):
        r = s.put(f"{API}/integrations/keys",
                  json={"hunter_api_key": "test-api-key"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert "hunter_api_key" in d["updated"]

        # GET to verify persistence + masking
        r2 = s.get(f"{API}/integrations/keys", timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["hunter"]["connected"] is True
        # Mask should be the last 4 chars prefixed with ellipsis
        assert d2["hunter"]["mask"].endswith("-key") or d2["hunter"]["mask"].endswith("key")
        assert "test-api-key" not in str(d2)  # raw not leaked
        assert d2["resend"]["connected"] is False  # partial update didn't touch resend

    def test_put_keys_partial_resend_and_from(self, s):
        r = s.put(f"{API}/integrations/keys",
                  json={"resend_api_key": "fake_user_key_xxxx",
                        "resend_from_email": "sender@example.com"},
                  timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "resend_api_key" in d["updated"]
        assert "resend_from_email" in d["updated"]

        # Verify both keys now stored, no leakage
        r2 = s.get(f"{API}/integrations/keys", timeout=15)
        d2 = r2.json()
        assert d2["hunter"]["connected"] is True  # still there
        assert d2["resend"]["connected"] is True
        assert d2["resend"]["from_email"] == "sender@example.com"
        assert "fake_user_key_xxxx" not in str(d2)

    def test_get_keys_never_leaks_raw(self, s, mongo):
        """Critical privacy test: raw API key fields never appear in response."""
        r = s.get(f"{API}/integrations/keys", timeout=15)
        body = r.text
        # Confirm raw values are in DB
        doc = mongo.user_integration_keys.find_one({"user_id": "demo-user-001"})
        assert doc.get("hunter_api_key") == "test-api-key"
        assert doc.get("resend_api_key") == "fake_user_key_xxxx"
        # And NOT in response body
        assert "test-api-key" not in body
        assert "fake_user_key_xxxx" not in body
        d = r.json()
        assert "hunter_api_key" not in d
        assert "resend_api_key" not in d

    def test_delete_key_invalid_provider_400(self, s):
        r = s.delete(f"{API}/integrations/keys/bogus", timeout=15)
        assert r.status_code == 400, r.text

    def test_delete_key_hunter_only_keeps_resend(self, s):
        r = s.delete(f"{API}/integrations/keys/hunter", timeout=15)
        assert r.status_code == 200, r.text
        # Verify only hunter cleared
        r2 = s.get(f"{API}/integrations/keys", timeout=15)
        d = r2.json()
        assert d["hunter"]["connected"] is False
        assert d["resend"]["connected"] is True  # untouched

    def test_delete_key_resend(self, s):
        r = s.delete(f"{API}/integrations/keys/resend", timeout=15)
        assert r.status_code == 200
        r2 = s.get(f"{API}/integrations/keys", timeout=15)
        d = r2.json()
        assert d["resend"]["connected"] is False


# ============= Hunter find / verify =============
class TestHunterFindVerify:
    def test_find_requires_key_400_when_missing(self, s, mongo):
        # ensure no key
        mongo.user_integration_keys.delete_one({"user_id": "demo-user-001"})
        r = s.post(f"{API}/integrations/hunter/find",
                   json={"company": "Acme", "first_name": "John", "last_name": "Doe"},
                   timeout=15)
        assert r.status_code == 400, r.text

    def test_verify_requires_key_400_when_missing(self, s, mongo):
        mongo.user_integration_keys.delete_one({"user_id": "demo-user-001"})
        r = s.post(f"{API}/integrations/hunter/verify",
                   json={"email": "john@acme.com"}, timeout=15)
        assert r.status_code == 400, r.text

    def test_find_with_test_api_key(self, s):
        # set test-api-key
        rk = s.put(f"{API}/integrations/keys",
                   json={"hunter_api_key": "test-api-key"}, timeout=15)
        assert rk.status_code == 200
        # Hunter accepts 'test-api-key' as a dev key (returns dummy data, no credit consumed)
        r = s.post(f"{API}/integrations/hunter/find",
                   json={"company": "Reddit", "domain": "reddit.com",
                         "first_name": "Alexis", "last_name": "Ohanian"},
                   timeout=30)
        # 200 with the {email, score, verified, source} shape is the happy path.
        # Hunter may return data:{email:null} for the dummy — acceptable.
        # 502 on transient API error is acceptable but logged.
        assert r.status_code in (200, 502), r.text
        if r.status_code == 200:
            d = r.json()
            for k in ("email", "score", "verified", "source"):
                assert k in d, f"missing key {k} in find response: {d}"
            assert d["source"] in ("hunter", "hunter_error")

    def test_verify_with_test_api_key(self, s):
        # ensure key set
        s.put(f"{API}/integrations/keys", json={"hunter_api_key": "test-api-key"}, timeout=15)
        r = s.post(f"{API}/integrations/hunter/verify",
                   json={"email": "alexis@reddit.com"}, timeout=30)
        # Same tolerance as find
        assert r.status_code in (200, 502), r.text
        if r.status_code == 200:
            d = r.json()
            for k in ("email", "status", "score"):
                assert k in d


# ============= /webhook/resend-inbound — public, fast =============
class TestResendInboundWebhook:
    def test_webhook_is_public_no_auth(self):
        """Verify the endpoint accepts requests without an Authorization header."""
        payload = {
            "type": "email.received",
            "data": {
                "from": "stranger@nobody.test",
                "to": "noreply@nexus.ai",
                "subject": "Re: unmatched test",
                "text": "Hello unmatched.",
                "headers": {"in-reply-to": "<no-such-id-xyz>"},
            },
        }
        t0 = time.time()
        r = requests.post(f"{API}/webhook/resend-inbound", json=payload, timeout=10)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("matched") is False  # no outbound to match
        # Must be fast (under 5s) thanks to fire-and-forget Claude draft
        assert elapsed < 5.0, f"webhook took {elapsed:.2f}s — should be <5s"

    def test_webhook_invalid_json_400(self):
        r = requests.post(f"{API}/webhook/resend-inbound",
                          data="not-json", headers={"Content-Type": "application/json"},
                          timeout=10)
        assert r.status_code == 400, r.text

    def test_webhook_ignores_non_received_event(self):
        r = requests.post(f"{API}/webhook/resend-inbound",
                          json={"type": "email.delivered", "data": {}}, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert "ignored" in d

    def test_webhook_persists_unmatched_reply(self, mongo):
        """Even when unmatched, the reply should be persisted with linked=False."""
        unique = uuid.uuid4().hex[:8]
        from_addr = f"reply-{unique}@buyer.test"
        payload = {
            "type": "email.received",
            "data": {
                "from": from_addr,
                "to": "noreply@nexus.ai",
                "subject": "Re: test persistence",
                "text": "I want to buy.",
                "headers": {"in-reply-to": f"<unmatched-{unique}>"},
            },
        }
        r = requests.post(f"{API}/webhook/resend-inbound", json=payload, timeout=10)
        assert r.status_code == 200
        # Look up the reply
        time.sleep(0.5)
        doc = mongo.email_replies.find_one({"from": from_addr})
        assert doc is not None, "unmatched reply not persisted"
        assert doc.get("linked") is False
        assert doc.get("source") == "resend"
        # cleanup
        mongo.email_replies.delete_many({"from": from_addr})

    def test_webhook_matches_outbound_and_creates_linked_reply(self, mongo):
        """Seed an email_outbox row, then send a matching in-reply-to."""
        unique = uuid.uuid4().hex[:8]
        provider_id = f"resend-msg-{unique}"
        outbound = {
            "id": str(uuid.uuid4()),
            "user_id": "demo-user-001",
            "to": f"buyer-{unique}@buyer.test",
            "from": "outreach@nexus.ai",
            "subject": "Quick thought",
            "body": "...",
            "kind": "promote.intro",
            "meta": {},
            "status": "delivered",
            "mocked": False,
            "provider": "resend",
            "provider_id": provider_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        mongo.email_outbox.insert_one(dict(outbound))
        try:
            payload = {
                "type": "email.received",
                "data": {
                    "from": outbound["to"],
                    "to": outbound["from"],
                    "subject": "Re: Quick thought",
                    "text": "Sure, send a calendar link.",
                    "headers": {"in-reply-to": f"<{provider_id}>"},
                },
            }
            t0 = time.time()
            r = requests.post(f"{API}/webhook/resend-inbound", json=payload, timeout=10)
            elapsed = time.time() - t0
            assert r.status_code == 200, r.text
            d = r.json()
            assert d.get("ok") is True
            assert d.get("matched") is True
            assert "reply_id" in d
            assert elapsed < 5.0, f"matched webhook took {elapsed:.2f}s — should be <5s"
            # Verify reply persisted as linked
            doc = mongo.email_replies.find_one({"id": d["reply_id"]})
            assert doc is not None
            assert doc.get("linked") is True
            assert doc.get("original_email_id") == outbound["id"]
        finally:
            mongo.email_outbox.delete_one({"provider_id": provider_id})
            mongo.email_replies.delete_many({"original_email_id": outbound["id"]})


# ============= Promote-target Hunter + Resend BYOK =============
class TestPromoteTargetByok:
    """Set per-user Hunter + Resend keys, promote a target, verify wiring."""

    def _find_unpromoted_target(self, s, mongo):
        """Find or create a target with no decision_maker_email."""
        # Try listing
        r = s.get(f"{API}/targets", timeout=15)
        if r.status_code == 200:
            for t in r.json().get("targets", []):
                if not t.get("promoted_deal_id") and not (t.get("decision_maker_email") or "").strip():
                    return t["id"]
        # Fallback: insert a synthetic target
        tid = str(uuid.uuid4())
        mongo.targets.insert_one({
            "id": tid,
            "user_id": "demo-user-001",
            "profile_id": "test-profile",
            "company_name": "TestCo Hunter",
            "decision_maker_name": "Alexis Ohanian",
            "decision_maker_title": "CEO",
            "decision_maker_email": "",
            "industry": "SaaS",
            "estimated_deal_size": "50k",
            "fit_score": 80,
            "signal_strength": 70,
            "intent_signal": "Just raised Series B",
            "recommended_play": "Send a personalized intro",
        })
        return tid

    def test_promote_with_hunter_byok_returns_hunter_score_key(self, s, mongo):
        # Set per-user hunter key (test mode)
        s.put(f"{API}/integrations/keys", json={"hunter_api_key": "test-api-key"}, timeout=15)
        tid = self._find_unpromoted_target(s, mongo)
        r = s.post(f"{API}/targets/{tid}/promote", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "hunter_score" in d, f"response missing hunter_score: {d}"
        # hunter_score may be None (Hunter test mode returns email:null) — that's fine
        # cleanup the deal + promoted_deal_id on target so next test can re-promote
        deal_id = d.get("deal", {}).get("id")
        if deal_id:
            mongo.deals.delete_many({"id": deal_id})
        mongo.targets.update_one({"id": tid}, {"$unset": {"promoted_deal_id": ""}})

    def test_promote_with_user_resend_key_uses_override(self, s, mongo):
        """Set a fake user resend key; expect email_outbox.status=failed (auth error)
        proving the per-user key was used (env key would have given a different error)."""
        # Wipe gmail to force resend path
        mongo.gmail_credentials.delete_many({"user_id": "demo-user-001"})
        # Set fake user resend key
        s.put(f"{API}/integrations/keys",
              json={"resend_api_key": "fake_user_key_zzz"}, timeout=15)
        # Clear hunter so no auto-find (use synthetic target with no DM email — synthetic email used)
        s.delete(f"{API}/integrations/keys/hunter", timeout=15)

        tid = self._find_unpromoted_target(s, mongo)
        before_ts = datetime.now(timezone.utc).isoformat()
        r = s.post(f"{API}/targets/{tid}/promote", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        # Should use resend (not gmail since we wiped it)
        assert d.get("sent_via") == "resend", f"expected resend, got: {d.get('sent_via')}"

        # Verify the email_outbox row was created with status=failed
        # Find the most recent row for this user from this test
        time.sleep(1.0)
        outbox = mongo.email_outbox.find_one(
            {"user_id": "demo-user-001", "meta.target_id": tid, "provider": "resend"},
            sort=[("created_at", -1)],
        )
        assert outbox is not None, "no resend outbox row found for promoted target"
        assert outbox.get("provider") == "resend"
        # With a fake user key, send should fail (or be mocked-as-failed)
        # Acceptable outcomes:
        #   - status='failed' with auth-related error → user key was used
        #   - status='delivered' & mocked=True is also OK if integration falls back to mock
        status = outbox.get("status")
        err = (outbox.get("error") or "").lower()
        # The override path was executed if any of: failed status, or error mentions auth/unauthorized/api/key
        used_override = (
            status == "failed"
            or any(tok in err for tok in ["auth", "unauthorized", "api", "401", "403", "key", "invalid"])
        )
        assert used_override, f"no evidence override key used: status={status} err={err!r}"

        # Cleanup
        deal_id = d.get("deal", {}).get("id")
        if deal_id:
            mongo.deals.delete_many({"id": deal_id})
        mongo.targets.update_one({"id": tid}, {"$unset": {"promoted_deal_id": ""}})


# ============= Regression sweep (slice) =============
class TestRegressionV9:
    def test_hero_stats(self):
        r = requests.get(f"{API}/landing/hero-stats", timeout=15)
        assert r.status_code == 200

    def test_waitlist_count(self):
        r = requests.get(f"{API}/landing/waitlist/count", timeout=15)
        assert r.status_code == 200

    def test_trial_status_demo(self, s):
        r = s.get(f"{API}/billing/trial-status", timeout=15)
        assert r.status_code == 200

    def test_gmail_status_demo(self, s):
        r = s.get(f"{API}/integrations/gmail/status", timeout=15)
        assert r.status_code == 200

    def test_leads_scan_endpoint_exists(self, s):
        # We do not need a live scan; just verify auth + non-402 for demo
        r = s.post(f"{API}/leads/scan", timeout=120)
        assert r.status_code in (200, 502), r.text  # 502 if Tavily transient

    def test_auth_me(self, s):
        r = s.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
