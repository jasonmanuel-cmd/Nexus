"""
Iteration 8 — NEW FEATURE testing (out-of-mock-mode wiring):
 1) Landing public endpoints — hero-stats, waitlist, affiliate
 2) Billing trial-status + 402 trial-gate on /api/leads/scan
 3) Gmail OAuth scaffolding — /connect, /status, /poll (negative path)
 4) Tavily-powered /api/leads/scan returning live=true once profile exists
 5) Square production env in /api/payments/config
 6) Regression sweep on previously-working core endpoints
"""
import os
import uuid
import time
from datetime import datetime, timezone, timedelta

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


# ============= LANDING — hero-stats =============
class TestLandingHeroStats:
    def test_hero_stats_public_no_auth(self):
        r = requests.get(f"{API}/landing/hero-stats", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["pipeline_value", "active_deals", "targets_identified",
                  "signals_detected_30d", "paying_customers", "agents_online",
                  "accuracy_pct", "as_of"]:
            assert k in d, f"missing key {k} in hero-stats: {d}"
        assert isinstance(d["pipeline_value"], (int, float))
        assert isinstance(d["active_deals"], int)
        assert isinstance(d["targets_identified"], int)
        assert isinstance(d["signals_detected_30d"], int)


# ============= LANDING — waitlist =============
class TestLandingWaitlist:
    test_email = f"TEST_wait_{uuid.uuid4().hex[:8]}@example.com"

    def test_join_waitlist_valid(self):
        r = requests.post(f"{API}/landing/waitlist",
                          json={"email": self.test_email, "company": "TestCo", "role": "Founder"},
                          timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert isinstance(d["position"], int) and d["position"] >= 1
        assert d["already_joined"] is False
        TestLandingWaitlist._position = d["position"]

    def test_join_waitlist_idempotent(self):
        r = requests.post(f"{API}/landing/waitlist",
                          json={"email": self.test_email}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["already_joined"] is True

    def test_join_waitlist_invalid_email_422(self):
        r = requests.post(f"{API}/landing/waitlist",
                          json={"email": "not-an-email"}, timeout=15)
        assert r.status_code == 422, r.text

    def test_waitlist_count_public(self):
        r = requests.get(f"{API}/landing/waitlist/count", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "count" in d and isinstance(d["count"], int) and d["count"] >= 1


# ============= LANDING — affiliate =============
class TestLandingAffiliate:
    test_email = f"TEST_aff_{uuid.uuid4().hex[:8]}@example.com"
    code = None

    def test_affiliate_signup_creates_code(self):
        r = requests.post(f"{API}/landing/affiliate/signup",
                          json={"email": self.test_email, "name": "Test Partner", "company": "Partner LLC"},
                          timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["code"] and isinstance(d["code"], str)
        assert d["referral_url"].startswith("/?ref=")
        assert d["referrals_count"] == 0
        assert d["already_registered"] is False
        TestLandingAffiliate.code = d["code"]

    def test_affiliate_signup_idempotent(self):
        r = requests.post(f"{API}/landing/affiliate/signup",
                          json={"email": self.test_email}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["already_registered"] is True
        assert d["code"] == TestLandingAffiliate.code

    def test_affiliate_lookup_no_owner_email_leak(self):
        if not TestLandingAffiliate.code:
            pytest.skip("no code created")
        r = requests.get(f"{API}/landing/affiliate/{TestLandingAffiliate.code}", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["code"] == TestLandingAffiliate.code
        assert "owner_email" not in d, f"owner_email LEAKED: {d}"
        assert "_id" not in d

    def test_affiliate_lookup_404_for_unknown(self):
        r = requests.get(f"{API}/landing/affiliate/notreal-{uuid.uuid4().hex[:8]}", timeout=15)
        assert r.status_code == 404


# ============= BILLING — trial-status =============
class TestBillingTrialStatus:
    def test_trial_status_auth_required(self):
        r = requests.get(f"{API}/billing/trial-status", timeout=15)
        assert r.status_code in (401, 403)

    def test_trial_status_returns_full_shape(self, s):
        r = s.get(f"{API}/billing/trial-status", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["subscription_active", "trial_active", "trial_started_at",
                  "trial_ends_at", "days_remaining", "locked", "subscription_package"]:
            assert k in d, f"missing key {k} in trial-status: {d}"
        assert isinstance(d["subscription_active"], bool)
        assert isinstance(d["trial_active"], bool)
        assert isinstance(d["days_remaining"], int)
        assert isinstance(d["locked"], bool)


# ============= TRIAL GATE on /api/leads/scan + simulate-reply =============
class TestTrialGate:
    """Use a FRESH test user (not demo-user-001) so we don't break other tests."""
    test_user_id = f"trial-test-{uuid.uuid4().hex[:10]}"
    test_token = f"trial-test-token-{uuid.uuid4().hex[:10]}"

    @classmethod
    def setup_class(cls):
        cli = MongoClient(MONGO_URL)
        db = cli[DB_NAME]
        # Insert user with created_at >8 days ago + no subscription
        old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        db.users.insert_one({
            "user_id": cls.test_user_id,
            "email": f"{cls.test_user_id}@test.example.com",
            "name": "Trial Expired Tester",
            "picture": "",
            "subscription_active": False,
            "created_at": old,
        })
        db.user_sessions.insert_one({
            "user_id": cls.test_user_id,
            "session_token": cls.test_token,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        cli.close()

    @classmethod
    def teardown_class(cls):
        cli = MongoClient(MONGO_URL)
        db = cli[DB_NAME]
        db.user_sessions.delete_one({"session_token": cls.test_token})
        db.users.delete_one({"user_id": cls.test_user_id})
        # cleanup any data this user might have generated
        for col in ["signals", "activities", "email_outbox"]:
            db[col].delete_many({"user_id": cls.test_user_id})
        cli.close()

    def _hdr(self):
        return {"Authorization": f"Bearer {self.test_token}", "Content-Type": "application/json"}

    def test_trial_status_locked_true(self):
        r = requests.get(f"{API}/billing/trial-status", headers=self._hdr(), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["locked"] is True, f"expected locked=True: {d}"
        assert d["subscription_active"] is False
        assert d["trial_active"] is False

    def test_leads_scan_blocked_402(self):
        r = requests.post(f"{API}/leads/scan", headers=self._hdr(), timeout=30)
        assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text}"
        d = r.json()
        # FastAPI wraps detail dict under 'detail'
        detail = d.get("detail", d)
        assert detail.get("error") == "trial_expired", f"unexpected detail: {d}"

    def test_simulate_reply_blocked_402(self):
        # endpoint requires an email_id but the trial-gate should fire first
        fake_id = uuid.uuid4().hex
        r = requests.post(f"{API}/notifications/email/{fake_id}/simulate-reply",
                          headers=self._hdr(), timeout=30)
        # Either 402 trial_expired (gate fires first) or 404 if route checks email_id first
        assert r.status_code in (402,), f"expected 402, got {r.status_code}: {r.text}"
        d = r.json()
        detail = d.get("detail", d)
        assert detail.get("error") == "trial_expired"


# ============= GMAIL — connect/status/poll =============
class TestGmail:
    def test_status_auth_required(self):
        r = requests.get(f"{API}/integrations/gmail/status", timeout=15)
        assert r.status_code in (401, 403)

    def test_status_returns_not_connected_for_demo(self, s, mongo):
        # ensure demo has no credentials (cleanup any prior state from test)
        mongo.gmail_credentials.delete_many({"user_id": "demo-user-001"})
        r = s.get(f"{API}/integrations/gmail/status", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json() == {"connected": False} or r.json().get("connected") is False

    def test_connect_returns_google_oauth_url(self, s):
        r = s.post(f"{API}/integrations/gmail/connect", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "url" in d and "state" in d
        assert d["url"].startswith("https://accounts.google.com/"), f"bad url: {d['url']}"
        assert d["state"] and len(d["state"]) >= 16

    def test_poll_returns_400_when_not_connected(self, s, mongo):
        mongo.gmail_credentials.delete_many({"user_id": "demo-user-001"})
        r = s.post(f"{API}/integrations/gmail/poll", timeout=15)
        assert r.status_code == 400, r.text
        assert "Gmail not connected" in r.text or "not connected" in r.text.lower()


# ============= TAVILY-POWERED LEADS SCAN =============
class TestLeadsScanLive:
    def test_ensure_profile_exists_then_scan_live(self, s, mongo):
        # Ensure demo user has an onboarding profile w/ industry + icp_description
        existing = mongo.profiles.find_one({"user_id": "demo-user-001",
                                            "industry": {"$exists": True},
                                            "icp_description": {"$exists": True}})
        if not existing:
            payload = {
                "company_name": "TestCo",
                "industry": "B2B SaaS",
                "company_size": "11-50",
                "icp_description": "Mid-market RevOps teams",
                "competitors": ["Salesforce", "HubSpot"],
                "value_proposition": "Speeds GTM 2x",
            }
            r = s.post(f"{API}/onboarding", json=payload, timeout=30)
            assert r.status_code == 200, r.text

        # Allow up to 90s for Tavily+Claude
        r = s.post(f"{API}/leads/scan", timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("scanned") is True
        assert "live" in d
        assert "new_signals" in d and isinstance(d["new_signals"], list)
        # We strongly prefer live=true but accept live=false (fallback) as non-fatal
        # because Tavily occasionally rate-limits.
        if d["live"] is not True:
            pytest.skip(f"Tavily fallback path hit (live=false). Signals returned: {len(d['new_signals'])}")
        assert len(d["new_signals"]) >= 1


# ============= SQUARE PRODUCTION ENV =============
class TestSquareEnv:
    def test_payments_config_returns_production(self):
        r = requests.get(f"{API}/payments/config", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("environment") == "production", f"expected environment=production, got {d}"


# ============= REGRESSION SWEEP =============
class TestRegression:
    def test_auth_me(self, s):
        r = s.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json()["user_id"] == "demo-user-001"

    def test_dashboard_metrics(self, s):
        r = s.get(f"{API}/dashboard/metrics", timeout=15)
        assert r.status_code == 200
        assert "pipeline_value" in r.json()

    def test_payments_packages(self, s):
        r = s.get(f"{API}/payments/packages", timeout=15)
        assert r.status_code == 200

    def test_payments_checkout_session(self, s):
        r = s.post(f"{API}/payments/checkout/session",
                   json={"package_id": "operator", "origin_url": BASE_URL}, timeout=30)
        # Production keys may not be wired to a live plan; accept 200 OR 502 with Square error
        assert r.status_code in (200, 502), r.text
        if r.status_code == 200:
            d = r.json()
            assert "url" in d and "session_id" in d

    def test_replies_queue(self, s):
        r = s.get(f"{API}/replies/queue", timeout=15)
        assert r.status_code == 200
        assert "drafts" in r.json()

    def test_notifications_outbox(self, s):
        r = s.get(f"{API}/notifications/outbox?limit=20", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "emails" in d and "slack_messages" in d
