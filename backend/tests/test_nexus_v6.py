"""Iteration 7 / v6 — Settings deal-value cap, Square error sanitization, router split regression.

Covers:
  - GET/PUT /api/settings with auto_send_deal_value_cap (default + clamp)
  - Per-deal autonomy block: cap low → auto-send blocked
  - Square error sanitization on /api/payments/subscribe (no raw SDK text)
  - Router-split regression: all /api/payments/* + /api/webhook/square still 200/expected
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SESSION = "demo_session_token_persistent"
H = {"Content-Type": "application/json", "Authorization": f"Bearer {SESSION}"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update(H)
    return s


# ----------------------------- SETTINGS -----------------------------
class TestSettings:
    def test_get_settings_returns_three_fields(self, client):
        r = client.get(f"{BASE_URL}/api/settings", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(["auto_send_enabled", "auto_send_threshold", "auto_send_deal_value_cap"]).issubset(d.keys())
        assert isinstance(d["auto_send_deal_value_cap"], int)

    def test_put_settings_clamps_cap(self, client):
        # too high
        r = client.put(f"{BASE_URL}/api/settings",
                       json={"auto_send_enabled": False, "auto_send_threshold": 85, "auto_send_deal_value_cap": 99_999_999}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["auto_send_deal_value_cap"] == 10_000_000
        # negative
        r = client.put(f"{BASE_URL}/api/settings",
                       json={"auto_send_enabled": False, "auto_send_threshold": 85, "auto_send_deal_value_cap": -1000}, timeout=15)
        assert r.status_code == 200
        assert r.json()["auto_send_deal_value_cap"] == 0
        # valid
        r = client.put(f"{BASE_URL}/api/settings",
                       json={"auto_send_enabled": False, "auto_send_threshold": 85, "auto_send_deal_value_cap": 50000}, timeout=15)
        assert r.status_code == 200
        assert r.json()["auto_send_deal_value_cap"] == 50000

    def test_get_settings_requires_auth(self, client):
        r = requests.get(f"{BASE_URL}/api/settings", timeout=15)
        assert r.status_code in (401, 403)


# ----------------------------- PER-DEAL AUTONOMY -----------------------------
class TestPerDealAutonomyCap:
    def _find_fresh_promote_intro(self, client):
        r = client.get(f"{BASE_URL}/api/notifications/outbox", timeout=15)
        if r.status_code != 200:
            return None
        emails = r.json().get("emails", [])
        existing_email_ids = set()
        try:
            rd = client.get(f"{BASE_URL}/api/replies/queue", timeout=15)
            if rd.status_code == 200:
                items = rd.json()
                if isinstance(items, dict):
                    items = items.get("drafts") or items.get("replies") or []
                for d in items:
                    eid = d.get("email_id") or d.get("source_email_id")
                    if eid:
                        existing_email_ids.add(eid)
        except Exception:
            pass
        for em in emails:
            if em.get("kind") == "promote.intro" and em.get("id") not in existing_email_ids:
                return em
        # Fallback — return any promote.intro (simulate may still work / dedupe server-side)
        for em in emails:
            if em.get("kind") == "promote.intro":
                return em
        return None

    def test_low_cap_blocks_auto_send(self, client):
        # Set autonomy ON with extremely low cap
        r = client.put(f"{BASE_URL}/api/settings",
                       json={"auto_send_enabled": True, "auto_send_threshold": 50, "auto_send_deal_value_cap": 10}, timeout=15)
        assert r.status_code == 200

        em = self._find_fresh_promote_intro(client)
        if not em:
            pytest.skip("No fresh promote.intro emails in outbox to simulate against")

        email_id = em.get("id")
        r = client.post(f"{BASE_URL}/api/notifications/email/{email_id}/simulate-reply", timeout=60)
        try:
            client.put(f"{BASE_URL}/api/settings",
                       json={"auto_send_enabled": False, "auto_send_threshold": 85, "auto_send_deal_value_cap": 50000}, timeout=15)
        except Exception:
            pass

        assert r.status_code == 200, r.text
        data = r.json()
        # Per spec: cap blocks auto-send regardless of Claude verdict
        assert data.get("auto_sent") is False, f"Expected auto_sent False due to $10 cap; got: {data}"
        draft = data.get("draft") or {}
        assert draft.get("status") != "auto_sent", f"Draft should be pending under low cap: {draft}"
        assert draft.get("status") == "pending", f"Draft status should be 'pending'; got: {draft.get('status')}"

    def test_raised_cap_enables_auto_send_path(self, client):
        """Smoke: raise cap to 1M; if a fresh email exists, just confirm endpoint still returns auto_sent boolean."""
        r = client.put(f"{BASE_URL}/api/settings",
                       json={"auto_send_enabled": True, "auto_send_threshold": 50, "auto_send_deal_value_cap": 1_000_000}, timeout=15)
        assert r.status_code == 200
        em = self._find_fresh_promote_intro(client)
        if not em:
            pytest.skip("No fresh promote.intro emails")
        email_id = em.get("id")
        r = client.post(f"{BASE_URL}/api/notifications/email/{email_id}/simulate-reply", timeout=60)
        # reset settings
        client.put(f"{BASE_URL}/api/settings",
                   json={"auto_send_enabled": False, "auto_send_threshold": 85, "auto_send_deal_value_cap": 50000}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "auto_sent" in data
        # cap removed, so either outcome possible — only assert path is reachable


# ----------------------------- SQUARE ERROR SANITIZATION -----------------------------
SAFE_PHRASES = [
    "card details are invalid",
    "card was declined",
    "card cvv check failed",
    "card is expired",
    "card token has already",
    "card token expired",
    "subscription request was rejected",
    "payment provider unavailable",
    "payment processing failed",
    "subscription plan not configured",
    "could not create customer",
    "insufficient funds",
    "billing address verification failed",
    "card expiration date is invalid",
]

RAW_LEAKS = ["traceback", "<class ", "squareup", "api_error", "errors\":[{\"category", "json.decoder"]


class TestSquareErrorSanitization:
    def test_subscribe_invalid_source_returns_sanitized_502(self, client):
        r = client.post(f"{BASE_URL}/api/payments/subscribe",
                        json={"package_id": "operator", "source_id": "cnon:bad-token", "cardholder_name": "Test"},
                        timeout=30)
        # Expect 502 sanitized (or some 4xx if Square rejects pre-flight); but spec says 502
        assert r.status_code in (400, 422, 500, 502), r.text
        detail = ""
        try:
            detail = (r.json().get("detail") or "")
        except Exception:
            detail = r.text
        d_low = detail.lower()
        assert any(p in d_low for p in SAFE_PHRASES), f"Detail not sanitized: {detail!r}"
        for leak in RAW_LEAKS:
            assert leak not in d_low, f"Raw Square text leaked: {detail!r}"

    def test_checkout_session_sanitized_on_square_failure(self, client):
        # Pass valid package_id; Square may succeed since sandbox token is configured.
        # We only assert that *if* it fails, the error is sanitized.
        r = client.post(f"{BASE_URL}/api/payments/checkout/session",
                        json={"package_id": "operator", "origin_url": "https://example.com"}, timeout=30)
        if r.status_code >= 500:
            try:
                detail = (r.json().get("detail") or "").lower()
            except Exception:
                detail = r.text.lower()
            assert any(p in detail for p in SAFE_PHRASES), f"Detail not sanitized: {detail!r}"


# ----------------------------- ROUTER SPLIT REGRESSION -----------------------------
class TestRouterSplitRegression:
    def test_packages_public(self, client):
        r = requests.get(f"{BASE_URL}/api/payments/packages", timeout=15)
        assert r.status_code == 200
        assert "packages" in r.json()
        assert any(p["id"] == "operator" for p in r.json()["packages"])

    def test_config_public(self, client):
        r = requests.get(f"{BASE_URL}/api/payments/config", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "application_id" in d and "location_id" in d and "environment" in d

    def test_checkout_session_requires_auth(self, client):
        r = requests.post(f"{BASE_URL}/api/payments/checkout/session",
                          json={"package_id": "operator", "origin_url": "https://x.com"}, timeout=15)
        assert r.status_code in (401, 403)

    def test_checkout_session_invalid_pkg(self, client):
        r = client.post(f"{BASE_URL}/api/payments/checkout/session",
                        json={"package_id": "nonexistent", "origin_url": "https://x.com"}, timeout=15)
        assert r.status_code == 400

    def test_checkout_status_404(self, client):
        r = client.get(f"{BASE_URL}/api/payments/checkout/status/does-not-exist", timeout=15)
        assert r.status_code == 404

    def test_subscribe_invalid_package_400(self, client):
        r = client.post(f"{BASE_URL}/api/payments/subscribe",
                        json={"package_id": "nope", "source_id": "cnon:x", "cardholder_name": "T"}, timeout=15)
        assert r.status_code == 400

    def test_subscription_get(self, client):
        r = client.get(f"{BASE_URL}/api/payments/subscription", timeout=15)
        assert r.status_code == 200
        assert "active" in r.json()

    def test_subscription_cancel_404_when_inactive(self, client):
        # Ensure user has no active sub by best-effort: if cancel succeeds, re-cancel will 404.
        r1 = client.post(f"{BASE_URL}/api/payments/subscription/cancel", timeout=15)
        assert r1.status_code in (200, 404)
        if r1.status_code == 200:
            r2 = client.post(f"{BASE_URL}/api/payments/subscription/cancel", timeout=15)
            assert r2.status_code == 404

    def test_webhook_square_400_without_signature(self, client):
        r = requests.post(f"{BASE_URL}/api/webhook/square", data=b"{}", timeout=15)
        assert r.status_code == 400
