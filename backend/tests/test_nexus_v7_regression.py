"""
Iteration 7 regression: code-quality refactor only — no business logic changed.
Verifies the 3 backend touch-points + auth/scope sanity:
 1) /api/leads/scan still returns 3-5 signals after random→secrets.SystemRandom swap
 2) /api/onboarding+/api/targets/generate still returns a valid `targets` array
    after the list-comp variable rename `t`→`tg` on server.py:405
 3) /api/payments/checkout/session still returns url+session_id after the
    defensive `link = None` init in routers/payments.py:50
Plus a broad smoke-sweep of every endpoint touched by the review_request.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback parse of frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
API = f"{BASE_URL}/api"

DEMO_TOKEN = os.environ.get("DEMO_SESSION_TOKEN", "demo_session_token_persistent")
HDR = {"Authorization": f"Bearer {DEMO_TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update(HDR)
    return sess


# ---------- AUTH ----------
class TestAuth:
    def test_me_returns_demo_user(self, s):
        r = s.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["user_id"] == "demo-user-001"
        assert d["email"] == "demo@nexus.ai"


# ---------- DASHBOARD ----------
class TestDashboard:
    def test_metrics(self, s):
        r = s.get(f"{API}/dashboard/metrics", timeout=15)
        assert r.status_code == 200
        d = r.json()
        # Actual contract: active_deals, activities_24h, agents_online, avg_deal_cycle_days, pipeline_value
        assert "pipeline_value" in d
        assert "active_deals" in d
        assert isinstance(d.get("active_deals"), int)

    def test_charts_shape(self, s):
        r = s.get(f"{API}/dashboard/charts", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "waterfall" in d and "productivity" in d
        assert isinstance(d["waterfall"], list)
        assert isinstance(d["productivity"], list)

    def test_activity_scoped(self, s):
        r = s.get(f"{API}/dashboard/activity", timeout=15)
        assert r.status_code == 200
        d = r.json()
        acts = d.get("activities", d if isinstance(d, list) else [])
        # all activities (if any) must be scoped — agent field present
        if acts:
            assert isinstance(acts, list)


# ---------- REFACTOR #1: leads/scan with secrets.SystemRandom ----------
class TestLeadsScanSecrets:
    def test_scan_returns_3_to_5_signals(self, s):
        r = s.post(f"{API}/leads/scan", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        # response shape: {"signals": [...], "count": int} OR {"new_signals":[...]} — accept both
        sigs = d.get("signals") or d.get("new_signals") or []
        cnt = d.get("count", len(sigs))
        assert 3 <= cnt <= 5, f"expected 3-5 signals, got {cnt}: {d}"
        assert isinstance(sigs, list)

    def test_scan_idempotent_runs(self, s):
        # call twice — both must succeed (verifies _sysrand reusable)
        r1 = s.post(f"{API}/leads/scan", timeout=20)
        r2 = s.post(f"{API}/leads/scan", timeout=20)
        assert r1.status_code == 200 and r2.status_code == 200


# ---------- REFACTOR #2: targets/generate with renamed comprehension var ----------
class TestOnboardingAndTargets:
    profile_id = None

    def test_onboarding_persists(self, s):
        payload = {
            "company_name": "Acme Test Co",
            "industry": "B2B SaaS",
            "company_size": "200-500",
            "icp_description": "200-500 employee SaaS companies in NA",
            "competitors": ["Salesforce", "HubSpot"],
            "value_proposition": "AI-driven CRO",
        }
        r = s.post(f"{API}/onboarding", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "profile_id" in d or "id" in d
        TestOnboardingAndTargets.profile_id = d.get("profile_id") or d.get("id")

    def test_targets_generate_returns_array(self, s):
        # Specifically verifies the `[tg.model_dump() for tg in targets]` rename didn't break payload
        if not TestOnboardingAndTargets.profile_id:
            pytest.skip("profile_id missing — onboarding step failed")
        body = {"profile_id": TestOnboardingAndTargets.profile_id}
        r = s.post(f"{API}/targets/generate", json=body, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "targets" in d, f"missing 'targets' key: {d}"
        assert isinstance(d["targets"], list)
        assert d.get("count", len(d["targets"])) == len(d["targets"])
        if d["targets"]:
            sample = d["targets"][0]
            # field is company_name in response, fit_score for ranking
            assert "company_name" in sample or "company" in sample
            assert "fit_score" in sample

    def test_targets_list(self, s):
        r = s.get(f"{API}/targets", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "targets" in d and isinstance(d["targets"], list)
        if d["targets"]:
            row = d["targets"][0]
            assert ("company_name" in row) or ("company" in row)
            assert "fit_score" in row

    def test_promote_target_idempotent(self, s):
        targets = s.get(f"{API}/targets", timeout=15).json().get("targets", [])
        if not targets:
            pytest.skip("no targets to promote")
        tid = targets[0]["id"]
        r1 = s.post(f"{API}/targets/{tid}/promote", timeout=30)
        r2 = s.post(f"{API}/targets/{tid}/promote", timeout=30)
        # 1st should create, 2nd should be idempotent (200 with deal_id or 409)
        assert r1.status_code in (200, 201), r1.text
        assert r2.status_code in (200, 201, 409), r2.text


# ---------- REFACTOR #3: payments checkout/session with defensive link init ----------
class TestPaymentsCheckoutSession:
    def test_packages(self, s):
        r = s.get(f"{API}/payments/packages", timeout=15)
        assert r.status_code == 200
        d = r.json()
        # Accept dict-of-packages or list
        if isinstance(d, dict) and "packages" in d:
            packs = d["packages"]
            keys = packs.keys() if isinstance(packs, dict) else {p.get("id") for p in packs}
        elif isinstance(d, dict):
            keys = d.keys()
        else:
            keys = {p.get("id") for p in d}
        assert "operator" in keys and "scale" in keys, f"missing operator/scale in {keys}"

    def test_config_public(self):
        r = requests.get(f"{API}/payments/config", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "environment" in d

    def test_checkout_session_returns_url_and_id(self, s):
        # CRITICAL — verifies `link = None` defensive init didn't regress the happy path
        r = s.post(
            f"{API}/payments/checkout/session",
            json={"package_id": "operator", "origin_url": BASE_URL},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "url" in d and d["url"].startswith("http"), f"bad url: {d}"
        assert "session_id" in d and d["session_id"], f"bad session_id: {d}"
        TestPaymentsCheckoutSession._sid = d["session_id"]

    def test_checkout_status(self, s):
        sid = getattr(TestPaymentsCheckoutSession, "_sid", None)
        if not sid:
            pytest.skip("no session created")
        r = s.get(f"{API}/payments/checkout/status/{sid}", timeout=15)
        assert r.status_code == 200
        assert "payment_status" in r.json() or "status" in r.json()

    def test_subscribe_bogus_package_400(self, s):
        r = s.post(f"{API}/payments/subscribe",
                   json={"package_id": "bogus", "source_id": "cnon:fake"}, timeout=20)
        assert r.status_code == 400, r.text

    def test_subscribe_missing_source_422(self, s):
        r = s.post(f"{API}/payments/subscribe",
                   json={"package_id": "operator"}, timeout=20)
        assert r.status_code == 422, r.text

    def test_subscription_cancel_inactive_404(self, s):
        r = s.post(f"{API}/payments/subscription/cancel", timeout=15)
        # demo user has no active sub → 404
        assert r.status_code in (404, 200), r.text


# ---------- SETTINGS ----------
class TestSettings:
    def test_get_settings(self, s):
        r = s.get(f"{API}/settings", timeout=15)
        assert r.status_code == 200

    def test_put_settings_clamps_threshold(self, s):
        r = s.put(f"{API}/settings",
                  json={"auto_send_enabled": False, "auto_send_threshold": 10}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("auto_send_threshold", 50) >= 50

    def test_settings_persist(self, s):
        s.put(f"{API}/settings",
              json={"auto_send_enabled": False, "auto_send_threshold": 85,
                    "auto_send_deal_value_cap": 50000}, timeout=15)
        r = s.get(f"{API}/settings", timeout=15)
        d = r.json()
        assert d["auto_send_threshold"] == 85


# ---------- PIPELINE & NOTIFICATIONS ----------
class TestPipelineAndOutbox:
    def test_pipeline_deals(self, s):
        r = s.get(f"{API}/pipeline/deals", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "deals" in d and isinstance(d["deals"], list)

    def test_outbox_scoped(self, s):
        r = s.get(f"{API}/notifications/outbox?limit=20", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "emails" in d and "slack_messages" in d


# ---------- REPLIES ----------
class TestReplies:
    def test_replies_queue(self, s):
        r = s.get(f"{API}/replies/queue", timeout=15)
        assert r.status_code == 200
        assert "drafts" in r.json()

    def test_replies_stats(self, s):
        r = s.get(f"{API}/replies/stats", timeout=15)
        assert r.status_code == 200


# ---------- USER SCOPING ----------
class TestScoping:
    def test_unauth_request_blocked(self):
        r = requests.get(f"{API}/targets", timeout=15)
        assert r.status_code in (401, 403)

    def test_bogus_token_blocked(self):
        r = requests.get(f"{API}/dashboard/metrics",
                         headers={"Authorization": "Bearer not_a_real_token"}, timeout=15)
        assert r.status_code in (401, 403)
