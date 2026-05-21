"""Hunter.io API wrapper — per-call api_key (multi-tenant BYOK).

Endpoints used:
- /v2/email-finder — predict email from domain + first/last
- /v2/email-verifier — validate an email
- /v2/domain-search — list emails for a domain (fallback when no name)
"""
import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)
BASE_URL = "https://api.hunter.io/v2"


class HunterError(Exception):
    def __init__(self, status: int, code: Optional[str], message: str):
        self.status = status
        self.code = code
        self.message = message
        super().__init__(f"Hunter {status} ({code}): {message}")


class HunterRateLimit(HunterError):
    pass


async def _request(path: str, params: Dict[str, Any], api_key: str, max_retries: int = 2) -> Dict[str, Any]:
    query = {**params, "api_key": api_key}
    url = f"{BASE_URL}{path}"
    attempt = 0
    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            resp = await client.get(url, params=query)
            if resp.status_code == 200:
                return resp.json()

            payload: Optional[Dict[str, Any]] = None
            try:
                payload = resp.json()
            except Exception:
                payload = None
            code: Optional[str] = None
            message = resp.text[:300]
            if isinstance(payload, dict):
                errs = payload.get("errors") or []
                if isinstance(errs, list) and errs:
                    code = str(errs[0].get("id") or errs[0].get("code") or "")
                    message = str(errs[0].get("details") or errs[0].get("message") or message)

            if resp.status_code in (403, 429):
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    attempt += 1
                    continue
                raise HunterRateLimit(resp.status_code, code, message)
            raise HunterError(resp.status_code, code, message)


async def email_finder(api_key: str, *, domain: Optional[str] = None, company: Optional[str] = None,
                      first_name: Optional[str] = None, last_name: Optional[str] = None,
                      full_name: Optional[str] = None) -> Dict[str, Any]:
    if not (domain or company):
        raise ValueError("domain or company required")
    if not (full_name or (first_name and last_name)):
        raise ValueError("full_name or first_name+last_name required")
    params: Dict[str, Any] = {}
    if domain:
        params["domain"] = domain
    if company:
        params["company"] = company
    if full_name:
        params["full_name"] = full_name
    else:
        params["first_name"] = first_name
        params["last_name"] = last_name
    return await _request("/email-finder", params, api_key)


async def email_verifier(api_key: str, email: str) -> Dict[str, Any]:
    return await _request("/email-verifier", {"email": email}, api_key)


async def find_decision_maker_email(api_key: str, *, company_name: str, first_name: str,
                                    last_name: str, domain_hint: Optional[str] = None) -> Dict[str, Any]:
    """Convenience: try email-finder with domain hint first, fall back to company name.

    Returns {email, score, verified, source}. Returns {email: None} if not found.
    """
    try:
        if domain_hint:
            r = await email_finder(api_key, domain=domain_hint,
                                   first_name=first_name, last_name=last_name)
        else:
            r = await email_finder(api_key, company=company_name,
                                   first_name=first_name, last_name=last_name)
        data = r.get("data") or {}
        email = data.get("email")
        score = data.get("score") or 0
        return {
            "email": email,
            "score": score,
            "verified": (data.get("verification") or {}).get("status") == "valid",
            "source": "hunter",
        }
    except HunterError as e:
        logger.warning(f"Hunter find failed for {company_name} {first_name} {last_name}: {e}")
        return {"email": None, "score": 0, "verified": False, "source": "hunter_error", "error": str(e)}
