"""Tavily web/news search wrapper for real B2B intent signal extraction.

Searches recent funding rounds, hiring spikes, exec changes, product launches
across an ICP-filtered query window, then feeds condensed results to Claude
Sonnet 4.5 for structured signal extraction.
"""
import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from tavily import TavilyClient
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)


def _tavily() -> TavilyClient:
    return TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


SIGNAL_EXTRACTION_PROMPT = """You are a B2B sales intelligence analyst extracting intent signals from real-time web search results.

For each interesting article, output a signal in this exact JSON shape:
{
  "signals": [
    {
      "company": "<company name>",
      "domain": "<best-guess domain>",
      "signal_type": "<one of: funding | hiring | exec_change | product_launch | tech_migration | expansion>",
      "description": "<1 sentence summary of the event>",
      "intent_score": <int 60-99 — confidence this is a buying signal for the ICP>,
      "source_url": "<exact source URL>",
      "detected_at": "<ISO date if known, else today>",
      "play": "<1 sentence sales play recommendation tailored to ICP>"
    }
  ]
}

Rules:
- Return 3-8 signals MAX. Quality over quantity.
- Skip generic news. Only buying signals (growth, change, pain).
- Score intent based on ICP fit + signal recency + decision-maker visibility.
- If no good signals, return {"signals": []}.
- Output ONLY the JSON, no markdown fences or commentary."""


def _build_query(industry: str, icp_description: str, geographies: List[str]) -> str:
    """Compact ICP-aware Tavily query (under 400 chars per Tavily best-practice)."""
    geo = ", ".join(geographies[:3]) if geographies else ""
    geo_clause = f" in {geo}" if geo else ""
    icp_short = (icp_description or "").strip()[:120]
    industry_clean = (industry or "").strip()[:60]
    q = (
        f"Recent {industry_clean} company news: "
        f"funding rounds, executive hires, hiring spikes, product launches, expansions"
        f"{geo_clause}. Focus: {icp_short}"
    )
    return q[:400]


def _condense_results(raw: Dict[str, Any], cap: int = 12) -> List[Dict[str, Any]]:
    """Strip Tavily result bloat — keep title, content snippet, url, date, score."""
    out = []
    for r in (raw.get("results") or [])[:cap]:
        out.append({
            "title": r.get("title", "")[:200],
            "content": (r.get("content") or "")[:600],
            "url": r.get("url"),
            "published_date": r.get("published_date"),
            "score": r.get("score"),
        })
    return out


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    return text.strip()


async def scan_real_signals(
    industry: str,
    icp_description: str,
    geographies: Optional[List[str]] = None,
    emergent_llm_key: Optional[str] = None,
    session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Full pipeline: Tavily news search → Claude signal extraction → list[dict].

    Returns rows shaped to fit the `Signal` Pydantic model used by the lead engine.
    Raises RuntimeError if Tavily or Claude fail.
    """
    query = _build_query(industry, icp_description, geographies or [])

    # Tavily client is sync — run in thread to avoid blocking the event loop
    def _do_search():
        return _tavily().search(
            query=query,
            topic="news",
            time_range="month",
            search_depth="advanced",
            max_results=12,
            include_answer=False,
            include_raw_content=False,
        )

    try:
        tavily_resp = await asyncio.to_thread(_do_search)
    except Exception as e:
        logger.error(f"Tavily search failed: {e}")
        raise RuntimeError(f"Tavily search failed: {e}")

    condensed = _condense_results(tavily_resp, cap=12)
    if not condensed:
        logger.warning("Tavily returned no results for query: %s", query)
        return []

    user_msg = (
        f"Industry: {industry}\n"
        f"ICP: {icp_description}\n"
        f"Geographies: {', '.join(geographies or []) or 'global'}\n\n"
        f"Search results from the past 30 days:\n"
        f"{json.dumps(condensed, ensure_ascii=False)}"
    )

    chat = LlmChat(
        api_key=emergent_llm_key or os.environ["EMERGENT_LLM_KEY"],
        session_id=session_id or f"tavily-extract-{abs(hash(query)) % 10**8}",
        system_message=SIGNAL_EXTRACTION_PROMPT,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    try:
        response_text = await chat.send_message(UserMessage(text=user_msg))
    except Exception as e:
        logger.error(f"Claude extraction failed: {e}")
        raise RuntimeError(f"Claude extraction failed: {e}")

    try:
        parsed = json.loads(_strip_json_fence(response_text))
    except Exception as e:
        logger.error(f"Failed to parse Claude JSON: {e} — raw: {response_text[:300]}")
        raise RuntimeError("Claude returned invalid JSON")

    signals = parsed.get("signals", [])
    # Coerce + sanitize for our Signal model
    cleaned: List[Dict[str, Any]] = []
    for s in signals:
        if not isinstance(s, dict):
            continue
        signal_type_raw = (s.get("signal_type") or "").lower().strip()
        # Map to the broad bucket our Signal model expects
        type_map = {
            "funding": "funding",
            "hiring": "hiring",
            "exec_change": "exec_change",
            "exec": "exec_change",
            "product_launch": "product",
            "product": "product",
            "tech_migration": "tech_migration",
            "expansion": "expansion",
        }
        signal_type = type_map.get(signal_type_raw, "funding")
        intent_score = s.get("intent_score", 75)
        try:
            intent_score = max(60, min(99, int(intent_score)))
        except (TypeError, ValueError):
            intent_score = 75
        domain = (s.get("domain") or "").strip().lower()
        # Strip protocol if present
        domain = re.sub(r"^https?://", "", domain).split("/")[0]
        cleaned.append({
            "company": (s.get("company") or "Unknown")[:120],
            "domain": domain[:120] if domain else "",
            "signal_type": signal_type,
            "description": (s.get("description") or "")[:400],
            "strength": intent_score,
            "source": (s.get("source_url") or "Tavily/web")[:500],
        })

    return cleaned[:8]
