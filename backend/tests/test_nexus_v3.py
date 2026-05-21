"""V3 backend tests for Nexus AI.

Covers Square payments swap, MOCKED notifications (email + Slack outbox),
and the new /api/notifications/outbox endpoint.
"""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
DEMO_TOKEN = os.environ.get("DEMO_SESSION_TOKEN", "demo_session_token_persistent")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="session")
def mongo():
    return pymongo.MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="session")
def demo_client():
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEMO_TOKEN}",
    })
    return s


# ---------- Square Payments ----------
class TestSquarePayments:
    def test_packages_returns_operator_and_scale(self):
        r = requests.get(f"{API}/payments/packages", timeout=15)
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()["packages"]}
        assert ids == {"operator", "scale"}

    def test_checkout_session_returns_square_url(self, demo_client, mongo):
        r = demo_client.post(
            f"{API}/payments/checkout/session",
            json={"package_id": "operator", "origin_url": BASE_URL}, timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "url" in d and "session_id" in d
        assert "square.link" in d["url"], f"expected square.link in url, got {d['url']}"
        txn = mongo.payment_transactions.find_one({"session_id": d["session_id"]})
        assert txn is not None
        assert txn["provider"] == "square"
        assert txn["package_id"] == "operator"
        # cleanup
        mongo.payment_transactions.delete_one({"session_id": d["session_id"]})

    def test_checkout_invalid_package_returns_400(self, demo_client):
        r = demo_client.post(
            f"{API}/payments/checkout/session",
            json={"package_id": "bogus", "origin_url": BASE_URL}, timeout=20,
        )
        assert r.status_code == 400

    def test_checkout_status_returns_square_provider(self, demo_client, mongo):
        r = demo_client.post(
            f"{API}/payments/checkout/session",
            json={"package_id": "scale", "origin_url": BASE_URL}, timeout=30,
        )
        assert r.status_code == 200
        sid = r.json()["session_id"]
        r2 = demo_client.get(f"{API}/payments/checkout/status/{sid}", timeout=20)
        assert r2.status_code == 200
        d = r2.json()
        for k in ("payment_status", "status", "amount_total", "currency", "package_id", "provider"):
            assert k in d, f"missing {k}"
        assert d["provider"] == "square"
        assert d["package_id"] == "scale"
        assert d["currency"] == "usd"
        assert isinstance(d["amount_total"], int)
        mongo.payment_transactions.delete_one({"session_id": sid})

    def test_subscription_demo_user_shape(self, demo_client, mongo):
        # Ensure clean state (in case prior test activated it)
        mongo.users.update_one({"user_id": "demo-user-001"},
                               {"$set": {"subscription_active": False}})
        r = demo_client.get(f"{API}/payments/subscription", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("active", "package_id", "package", "subscribed_at", "renews_at"):
            assert k in d
        assert d["active"] is False

    def test_subscription_cancel_404_when_inactive(self, demo_client, mongo):
        mongo.users.update_one({"user_id": "demo-user-001"},
                               {"$set": {"subscription_active": False}})
        r = demo_client.post(f"{API}/payments/subscription/cancel", timeout=15)
        assert r.status_code == 404

    def test_subscription_cancel_200_when_active(self, demo_client, mongo):
        # Activate temporarily
        mongo.users.update_one(
            {"user_id": "demo-user-001"},
            {"$set": {
                "subscription_active": True,
                "subscription_package": "operator",
                "subscribed_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        r = demo_client.post(f"{API}/payments/subscription/cancel", timeout=15)
        assert r.status_code == 200
        assert r.json()["canceled_package"] == "operator"
        # Verify flipped
        u = mongo.users.find_one({"user_id": "demo-user-001"})
        assert u["subscription_active"] is False

    def test_webhook_square_without_signature_returns_400(self):
        r = requests.post(f"{API}/webhook/square", data=b'{"type":"payment.created"}',
                          headers={"Content-Type": "application/json"}, timeout=15)
        assert r.status_code == 400

    def test_webhook_square_bad_signature_returns_400(self):
        r = requests.post(f"{API}/webhook/square", data=b'{"type":"payment.created"}',
                          headers={"Content-Type": "application/json",
                                   "x-square-hmacsha256-signature": "invalid"}, timeout=15)
        assert r.status_code == 400


# ---------- Notifications + Outbox ----------
class TestNotifications:
    @pytest.fixture(scope="class")
    def fresh_target_id(self, demo_client, mongo):
        """Create profile + targets, return one un-promoted target id."""
        payload = {
            "company_name": f"TEST_V3_{uuid.uuid4().hex[:6]}",
            "industry": "B2B SaaS", "company_size": "11-50",
            "icp_description": "Mid-market RevOps",
            "value_proposition": "Speeds GTM 2x",
        }
        rp = demo_client.post(f"{API}/onboarding", json=payload, timeout=20)
        assert rp.status_code == 200
        pid = rp.json()["id"]
        rg = demo_client.post(f"{API}/targets/generate", json={"profile_id": pid}, timeout=180)
        assert rg.status_code == 200, rg.text[:300]
        targets = rg.json()["targets"]
        # pick first un-promoted
        for t in targets:
            if not t.get("promoted_deal_id"):
                yield t["id"]
                break
        else:
            pytest.skip("No un-promoted target available")

    def test_promote_inserts_email_and_slack(self, demo_client, fresh_target_id, mongo):
        emails_before = mongo.email_outbox.count_documents(
            {"user_id": "demo-user-001", "kind": "promote.intro"})
        slacks_before = mongo.slack_outbox.count_documents(
            {"user_id": "demo-user-001", "kind": "target.promoted"})

        r = demo_client.post(f"{API}/targets/{fresh_target_id}/promote", timeout=20)
        assert r.status_code == 200
        assert r.json()["already_promoted"] is False

        emails_after = mongo.email_outbox.count_documents(
            {"user_id": "demo-user-001", "kind": "promote.intro"})
        slacks_after = mongo.slack_outbox.count_documents(
            {"user_id": "demo-user-001", "kind": "target.promoted"})
        assert emails_after == emails_before + 1
        assert slacks_after == slacks_before + 1

        # Verify mocked=True on latest insert
        latest_email = mongo.email_outbox.find_one(
            {"user_id": "demo-user-001", "kind": "promote.intro"},
            sort=[("created_at", -1)])
        assert latest_email["mocked"] is True
        assert latest_email["provider"] == "resend_mock"

    def test_stage_change_inserts_slack(self, demo_client, mongo):
        # Create a deal in prospecting
        rc = demo_client.post(
            f"{API}/pipeline/deals",
            json={"company": f"TEST_StageChg_{uuid.uuid4().hex[:6]}",
                  "contact": "Test Contact", "value": 50000.0,
                  "stage": "prospecting", "probability": 20}, timeout=15,
        )
        assert rc.status_code == 200
        deal_id = rc.json()["id"]

        slacks_before = mongo.slack_outbox.count_documents(
            {"user_id": "demo-user-001", "kind": "deal.stage.qualified"})
        r = demo_client.patch(f"{API}/pipeline/deals/{deal_id}",
                              json={"stage": "qualified"}, timeout=15)
        assert r.status_code == 200
        slacks_after = mongo.slack_outbox.count_documents(
            {"user_id": "demo-user-001", "kind": "deal.stage.qualified"})
        assert slacks_after == slacks_before + 1

        # Now closed_won -> slack AND email
        slacks_won_before = mongo.slack_outbox.count_documents(
            {"user_id": "demo-user-001", "kind": "deal.stage.closed_won"})
        emails_won_before = mongo.email_outbox.count_documents(
            {"user_id": "demo-user-001", "kind": "deal.won"})
        r2 = demo_client.patch(f"{API}/pipeline/deals/{deal_id}",
                               json={"stage": "closed_won"}, timeout=15)
        assert r2.status_code == 200
        slacks_won_after = mongo.slack_outbox.count_documents(
            {"user_id": "demo-user-001", "kind": "deal.stage.closed_won"})
        emails_won_after = mongo.email_outbox.count_documents(
            {"user_id": "demo-user-001", "kind": "deal.won"})
        assert slacks_won_after == slacks_won_before + 1
        assert emails_won_after == emails_won_before + 1

        # cleanup
        mongo.deals.delete_one({"id": deal_id})

    def test_patch_without_stage_change_no_notifications(self, demo_client, mongo):
        # Get an existing deal
        deals = demo_client.get(f"{API}/pipeline/deals", timeout=15).json()["deals"]
        assert len(deals) > 0
        deal_id = deals[0]["id"]
        stage = deals[0]["stage"]
        # Patch only last_action
        emails_before = mongo.email_outbox.count_documents({"user_id": "demo-user-001"})
        slacks_before = mongo.slack_outbox.count_documents({"user_id": "demo-user-001"})
        r = demo_client.patch(f"{API}/pipeline/deals/{deal_id}",
                              json={"last_action": "Test no-op update"}, timeout=15)
        assert r.status_code == 200
        # Same stage update should also not emit notification
        r2 = demo_client.patch(f"{API}/pipeline/deals/{deal_id}",
                               json={"stage": stage}, timeout=15)
        assert r2.status_code == 200
        emails_after = mongo.email_outbox.count_documents({"user_id": "demo-user-001"})
        slacks_after = mongo.slack_outbox.count_documents({"user_id": "demo-user-001"})
        assert emails_after == emails_before
        assert slacks_after == slacks_before


# ---------- Outbox endpoint ----------
class TestOutbox:
    def test_outbox_returns_emails_and_slack(self, demo_client):
        r = demo_client.get(f"{API}/notifications/outbox", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "emails" in d and "slack_messages" in d
        assert isinstance(d["emails"], list)
        assert isinstance(d["slack_messages"], list)
        for e in d["emails"]:
            assert e["user_id"] == "demo-user-001"
            assert "_id" not in e
        for s in d["slack_messages"]:
            assert s["user_id"] == "demo-user-001"
            assert "_id" not in s

    def test_outbox_unauth_returns_401(self):
        r = requests.get(f"{API}/notifications/outbox", timeout=15)
        assert r.status_code == 401

    def test_outbox_scoped_per_user(self, demo_client, mongo):
        # Insert a foreign-user email and make sure demo user does not see it
        foreign = {
            "id": str(uuid.uuid4()), "user_id": "test-foreign-x",
            "to": "foo@bar.com", "subject": "TEST_foreign", "body": "x",
            "kind": "test", "meta": {}, "status": "queued",
            "mocked": True, "provider": "resend_mock",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        mongo.email_outbox.insert_one(dict(foreign))
        r = demo_client.get(f"{API}/notifications/outbox", timeout=15)
        subjects = [e["subject"] for e in r.json()["emails"]]
        assert "TEST_foreign" not in subjects
        mongo.email_outbox.delete_one({"id": foreign["id"]})
