"""V2 backend tests for Nexus AI.

Covers auth gating, per-user scoping, /dashboard/charts, target promotion
idempotency, and Stripe checkout session/status (Stripe checkout is mocked
upstream via emergentintegrations — we just verify the URL/session are
returned and the payment_transactions row is created).
"""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pymongo
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://nexus-beta-onboard.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

DEMO_TOKEN = "demo_session_token_persistent"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# ---------- Mongo helper for second-user setup / cleanup ----------
@pytest.fixture(scope="session")
def mongo():
    client = pymongo.MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="session")
def second_user(mongo):
    """Create an isolated second user + session, yield (token, user_id), cleanup."""
    user_id = f"test-user-{uuid.uuid4().hex[:10]}"
    token = f"test_session_{uuid.uuid4().hex[:16]}"
    mongo.users.insert_one({
        "user_id": user_id,
        "email": f"TEST_{user_id}@example.com",
        "name": "Test Second User",
        "picture": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield token, user_id
    # cleanup
    mongo.users.delete_one({"user_id": user_id})
    mongo.user_sessions.delete_one({"session_token": token})
    for coll in ("profiles", "targets", "deals", "signals", "activities", "payment_transactions"):
        mongo[coll].delete_many({"user_id": user_id})


@pytest.fixture(scope="session")
def demo_client():
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEMO_TOKEN}",
    })
    return s


def _bearer(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Auth gating ----------
class TestAuthGating:
    def test_unauth_metrics_returns_401(self):
        r = requests.get(f"{API}/dashboard/metrics", timeout=15)
        assert r.status_code == 401

    def test_auth_me_returns_user(self, demo_client):
        r = demo_client.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("user_id", "email", "name"):
            assert k in d, f"missing {k}"
        assert d["user_id"] == "demo-user-001"
        assert d["email"] == "demo@nexus.ai"
        assert "_id" not in d

    def test_metrics_authenticated_returns_scoped_data(self, demo_client):
        r = demo_client.get(f"{API}/dashboard/metrics", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["pipeline_value"] > 0
        assert d["active_deals"] >= 1

    def test_logout_invalidates_a_token(self, mongo):
        # Create a throwaway token, logout, ensure it's gone
        token = f"test_logout_{uuid.uuid4().hex[:10]}"
        user_id = f"test-user-logout-{uuid.uuid4().hex[:6]}"
        mongo.users.insert_one({
            "user_id": user_id, "email": f"TEST_{user_id}@x.com",
            "name": "Logout U", "created_at": datetime.now(timezone.utc).isoformat(),
        })
        mongo.user_sessions.insert_one({
            "user_id": user_id, "session_token": token,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        # logout
        r = requests.post(f"{API}/auth/logout", headers=_bearer(token), timeout=15)
        assert r.status_code == 200
        # session row should be deleted
        assert mongo.user_sessions.find_one({"session_token": token}) is None
        # subsequent protected call should 401
        r2 = requests.get(f"{API}/dashboard/metrics", headers=_bearer(token), timeout=15)
        assert r2.status_code == 401
        mongo.users.delete_one({"user_id": user_id})


# ---------- Charts ----------
class TestCharts:
    def test_charts_shape(self, demo_client):
        r = demo_client.get(f"{API}/dashboard/charts", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "waterfall" in d and "productivity" in d
        assert isinstance(d["waterfall"], list) and len(d["waterfall"]) == 5
        assert isinstance(d["productivity"], list) and len(d["productivity"]) == 7
        wf0 = d["waterfall"][0]
        for k in ("stage", "total", "weighted", "count"):
            assert k in wf0
        prod0 = d["productivity"][0]
        assert "agent" in prod0 and "actions" in prod0


# ---------- Stripe payments ----------
class TestPayments:
    def test_packages_public(self):
        r = requests.get(f"{API}/payments/packages", timeout=15)
        assert r.status_code == 200
        d = r.json()
        ids = {p["id"] for p in d["packages"]}
        assert ids == {"operator", "scale"}
        amts = {p["id"]: p["amount"] for p in d["packages"]}
        assert amts["operator"] == 4800.0
        assert amts["scale"] == 18500.0

    def test_checkout_session_requires_auth(self):
        r = requests.post(f"{API}/payments/checkout/session",
                          json={"package_id": "operator", "origin_url": BASE_URL}, timeout=20)
        assert r.status_code == 401

    def test_checkout_invalid_package(self, demo_client):
        r = demo_client.post(f"{API}/payments/checkout/session",
                             json={"package_id": "bogus", "origin_url": BASE_URL}, timeout=20)
        assert r.status_code == 400

    def test_checkout_session_creates_url_and_txn(self, demo_client, mongo):
        r = demo_client.post(f"{API}/payments/checkout/session",
                             json={"package_id": "operator", "origin_url": BASE_URL}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "url" in d and d["url"].startswith("http")
        assert "session_id" in d
        # Mongo row
        txn = mongo.payment_transactions.find_one({"session_id": d["session_id"]})
        assert txn is not None
        assert txn["payment_status"] == "initiated"
        assert txn["package_id"] == "operator"
        assert txn["user_id"] == "demo-user-001"
        # cleanup
        mongo.payment_transactions.delete_one({"session_id": d["session_id"]})

    def test_checkout_status_open(self, demo_client):
        # Create then immediately query status
        r = demo_client.post(f"{API}/payments/checkout/session",
                             json={"package_id": "scale", "origin_url": BASE_URL}, timeout=30)
        assert r.status_code == 200
        sid = r.json()["session_id"]
        # Stripe may need a moment
        time.sleep(1)
        r2 = demo_client.get(f"{API}/payments/checkout/status/{sid}", timeout=20)
        assert r2.status_code == 200
        d2 = r2.json()
        # Don't expect paid; either open/expired/complete depending on stripe state
        assert d2["payment_status"] in ("unpaid", "no_payment_required", "initiated", "paid")
        assert "status" in d2


# ---------- Promote target ----------
class TestPromote:
    @pytest.fixture(scope="class")
    def profile_with_target(self, demo_client):
        # Create profile
        profile_payload = {
            "company_name": f"TEST_Promote_{uuid.uuid4().hex[:6]}",
            "industry": "B2B SaaS", "company_size": "11-50",
            "icp_description": "Mid-market RevOps", "value_proposition": "Speeds GTM 2x",
        }
        rp = demo_client.post(f"{API}/onboarding", json=profile_payload, timeout=20)
        assert rp.status_code == 200, rp.text
        pid = rp.json()["id"]
        # Generate targets (real LLM)
        rg = demo_client.post(f"{API}/targets/generate", json={"profile_id": pid}, timeout=120)
        assert rg.status_code == 200, rg.text[:300]
        targets = rg.json()["targets"]
        assert len(targets) >= 1
        return pid, targets[0]["id"]

    def test_promote_creates_deal_and_logs_activity(self, demo_client, profile_with_target):
        _, target_id = profile_with_target
        before_acts = demo_client.get(f"{API}/dashboard/activity", timeout=15).json()["activities"]
        r = demo_client.post(f"{API}/targets/{target_id}/promote", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["already_promoted"] is False
        deal = body["deal"]
        assert deal["stage"] == "prospecting"
        assert "id" in deal
        # Activity logged
        after = demo_client.get(f"{API}/dashboard/activity", timeout=15).json()["activities"]
        assert len(after) >= len(before_acts) + 1
        assert any(a.get("action") == "Target promoted to pipeline" for a in after[:5])
        # Deal now in pipeline listing
        deals = demo_client.get(f"{API}/pipeline/deals", timeout=15).json()["deals"]
        assert any(d["id"] == deal["id"] for d in deals)

    def test_promote_twice_idempotent(self, demo_client, profile_with_target):
        _, target_id = profile_with_target
        r1 = demo_client.post(f"{API}/targets/{target_id}/promote", timeout=20)
        assert r1.status_code == 200
        r2 = demo_client.post(f"{API}/targets/{target_id}/promote", timeout=20)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["already_promoted"] is True
        assert d2["deal"]["id"] == r1.json()["deal"]["id"]


# ---------- Per-user scoping ----------
class TestUserScoping:
    def test_second_user_has_empty_pipeline(self, second_user, demo_client):
        token, uid = second_user
        # On first /auth/me call, ensure_seed_data should populate sample data for this user
        r = requests.get(f"{API}/auth/me", headers=_bearer(token), timeout=15)
        assert r.status_code == 200
        # Now they should have seed data (not the demo user's data)
        d2 = requests.get(f"{API}/pipeline/deals", headers=_bearer(token), timeout=15).json()["deals"]
        demo_deals = demo_client.get(f"{API}/pipeline/deals", timeout=15).json()["deals"]
        # IDs should not overlap with demo user's deals
        demo_ids = {d["id"] for d in demo_deals}
        user2_ids = {d["id"] for d in d2}
        assert demo_ids.isdisjoint(user2_ids), "User scoping broken: deal IDs overlap"

    def test_second_user_cannot_see_demo_targets(self, second_user):
        token, _ = second_user
        r = requests.get(f"{API}/targets", headers=_bearer(token), timeout=15)
        assert r.status_code == 200
        # Should be empty or only their own
        for t in r.json()["targets"]:
            assert t["user_id"] != "demo-user-001"
