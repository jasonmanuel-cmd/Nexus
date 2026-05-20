"""Backend integration tests for Nexus AI (FastAPI + MongoDB + Claude Sonnet 4.5).

Covers: root, dashboard metrics/activity, lead signals + scan, pipeline
CRUD/patch, onboarding create+latest+get, AI-driven /api/targets/generate
(REAL LLM call, allow up to 90s), and /api/targets list.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://nexus-beta-onboard.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Root / health ----------
class TestRoot:
    def test_root_operational(self, session):
        r = session.get(f"{API}/", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("app") == "Nexus AI"
        assert data.get("status") == "operational"


# ---------- Dashboard ----------
class TestDashboard:
    def test_metrics_shape_and_types(self, session):
        r = session.get(f"{API}/dashboard/metrics", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in [
            "revenue_won", "pipeline_value", "weighted_pipeline", "active_deals",
            "targets_identified", "activities_24h", "agents_online", "win_rate",
            "avg_deal_cycle_days", "meetings_booked_week",
        ]:
            assert k in d, f"Missing metric key {k}"
            assert isinstance(d[k], (int, float)), f"{k} not numeric: {d[k]}"
        # Seed data should give us a non-zero pipeline
        assert d["pipeline_value"] > 0
        assert d["active_deals"] >= 1

    def test_activity_seed_present(self, session):
        r = session.get(f"{API}/dashboard/activity", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "activities" in d
        assert isinstance(d["activities"], list)
        assert len(d["activities"]) >= 10
        a = d["activities"][0]
        for k in ["agent", "action", "target", "status", "timestamp"]:
            assert k in a
        # No raw mongo _id leaks
        assert "_id" not in a


# ---------- Lead engine ----------
class TestLeadEngine:
    def test_signals_seeded(self, session):
        r = session.get(f"{API}/leads/signals", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "signals" in d
        assert len(d["signals"]) >= 12
        s0 = d["signals"][0]
        for k in ["id", "company", "domain", "signal_type", "description", "strength", "source", "detected_at"]:
            assert k in s0
        assert "_id" not in s0

    def test_scan_adds_signals_and_logs_activity(self, session):
        before = session.get(f"{API}/leads/signals", timeout=15).json()["signals"]
        before_act = session.get(f"{API}/dashboard/activity", timeout=15).json()["activities"]
        r = session.post(f"{API}/leads/scan", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body.get("scanned") is True
        assert isinstance(body.get("new_signals"), list)
        assert 3 <= len(body["new_signals"]) <= 5
        after = session.get(f"{API}/leads/signals", timeout=15).json()["signals"]
        after_act = session.get(f"{API}/dashboard/activity", timeout=15).json()["activities"]
        assert len(after) >= len(before) + len(body["new_signals"])
        # Activity logged for scan
        assert len(after_act) >= len(before_act) + 1
        assert after_act[0]["agent"] == "LeadScout-7"


# ---------- Pipeline ----------
class TestPipeline:
    def test_deals_seeded(self, session):
        r = session.get(f"{API}/pipeline/deals", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "deals" in d
        assert len(d["deals"]) >= 11
        deal0 = d["deals"][0]
        for k in ["id", "company", "contact", "value", "stage", "probability", "agent_status", "last_action"]:
            assert k in deal0
        assert "_id" not in deal0

    def test_create_and_patch_deal(self, session):
        # CREATE
        payload = {
            "company": "TEST_AcmeCorp",
            "contact": "Test Contact, VP",
            "value": 50000,
            "stage": "prospecting",
            "probability": 25,
        }
        r = session.post(f"{API}/pipeline/deals", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["company"] == payload["company"]
        assert created["stage"] == "prospecting"
        assert created["agent_status"] == "idle"
        assert "id" in created
        deal_id = created["id"]

        # Verify persisted via list
        listing = session.get(f"{API}/pipeline/deals", timeout=15).json()["deals"]
        assert any(d["id"] == deal_id for d in listing)

        # PATCH
        upd = {"stage": "qualified", "agent_status": "thinking", "last_action": "Stage advanced via test"}
        r2 = session.patch(f"{API}/pipeline/deals/{deal_id}", json=upd, timeout=15)
        assert r2.status_code == 200, r2.text
        updated = r2.json()
        assert updated["stage"] == "qualified"
        assert updated["agent_status"] == "thinking"
        assert updated["last_action"] == "Stage advanced via test"

        # Verify persistence
        listing2 = session.get(f"{API}/pipeline/deals", timeout=15).json()["deals"]
        found = next((d for d in listing2 if d["id"] == deal_id), None)
        assert found is not None
        assert found["stage"] == "qualified"

    def test_patch_nonexistent_deal_returns_404(self, session):
        r = session.patch(f"{API}/pipeline/deals/does-not-exist-xyz", json={"stage": "qualified"}, timeout=15)
        assert r.status_code == 404


# ---------- Onboarding ----------
PROFILE_PAYLOAD = {
    "company_name": "TEST_Convex Labs",
    "industry": "B2B SaaS",
    "company_size": "51-200",
    "annual_revenue": "$5-25M",
    "icp_description": "Mid-market SaaS RevOps leaders scaling GTM",
    "value_proposition": "Cuts sales cycle 38%",
    "target_geographies": ["North America", "EMEA"],
}


@pytest.fixture(scope="session")
def created_profile(session):
    r = session.post(f"{API}/onboarding", json=PROFILE_PAYLOAD, timeout=20)
    assert r.status_code == 200, r.text
    prof = r.json()
    assert "_id" not in prof, "Mongo _id leaked in onboarding response"
    assert prof["company_name"] == PROFILE_PAYLOAD["company_name"]
    assert "id" in prof and prof["id"]
    return prof


class TestOnboarding:
    def test_create_returns_profile_without_mongo_id(self, created_profile):
        assert "_id" not in created_profile
        assert created_profile["industry"] == "B2B SaaS"
        assert created_profile["company_size"] == "51-200"

    def test_latest_returns_recent_profile(self, session, created_profile):
        r = session.get(f"{API}/onboarding/latest", timeout=15)
        assert r.status_code == 200
        latest = r.json()
        assert latest is not None
        # latest should be the just-created one (no other writers in test run)
        assert latest["id"] == created_profile["id"]
        assert "_id" not in latest

    def test_get_by_id(self, session, created_profile):
        r = session.get(f"{API}/onboarding/{created_profile['id']}", timeout=15)
        assert r.status_code == 200
        p = r.json()
        assert p["id"] == created_profile["id"]


# ---------- Targets (REAL LLM call) ----------
class TestTargetsLLM:
    def test_generate_targets_real_llm(self, session, created_profile):
        r = session.post(
            f"{API}/targets/generate",
            json={"profile_id": created_profile["id"]},
            timeout=120,
        )
        assert r.status_code == 200, f"LLM call failed: {r.status_code} {r.text[:400]}"
        body = r.json()
        assert body["profile_id"] == created_profile["id"]
        assert "targets" in body
        targets = body["targets"]
        # Allow 8-10 per spec
        assert 8 <= len(targets) <= 10, f"Expected 8-10 targets, got {len(targets)}"
        t = targets[0]
        for k in [
            "id", "profile_id", "company_name", "industry", "headquarters", "employee_count",
            "estimated_revenue", "intent_signal", "signal_strength", "decision_maker_name",
            "decision_maker_title", "estimated_deal_size", "recommended_play", "fit_score",
        ]:
            assert k in t, f"Missing field {k} in target"
        assert isinstance(t["signal_strength"], int)
        assert isinstance(t["fit_score"], int)
        assert "_id" not in t

    def test_list_targets_by_profile(self, session, created_profile):
        # Small delay for persistence
        time.sleep(1)
        r = session.get(f"{API}/targets", params={"profile_id": created_profile["id"]}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "targets" in body
        assert len(body["targets"]) >= 8
        # Sorted by fit_score desc per backend
        scores = [t["fit_score"] for t in body["targets"]]
        assert scores == sorted(scores, reverse=True)

    def test_generate_targets_missing_profile_id(self, session):
        r = session.post(f"{API}/targets/generate", json={}, timeout=15)
        assert r.status_code == 400

    def test_generate_targets_unknown_profile(self, session):
        r = session.post(f"{API}/targets/generate", json={"profile_id": "nonexistent-xyz"}, timeout=15)
        assert r.status_code == 404
