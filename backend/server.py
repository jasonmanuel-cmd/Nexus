from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Cookie, Header
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json
import random
import logging
import httpx
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout, CheckoutSessionResponse, CheckoutStatusResponse, CheckoutSessionRequest
)

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY')

app = FastAPI(title="Nexus AI - Autonomous CRO")
api_router = APIRouter(prefix="/api")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ============== MODELS ==============
class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class OnboardingProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    company_name: str
    industry: str
    company_size: str
    annual_revenue: Optional[str] = None
    icp_description: str
    value_proposition: str
    target_geographies: Optional[List[str]] = []
    created_at: str = Field(default_factory=now_iso)


class OnboardingCreate(BaseModel):
    company_name: str
    industry: str
    company_size: str
    annual_revenue: Optional[str] = None
    icp_description: str
    value_proposition: str
    target_geographies: Optional[List[str]] = []


class Target(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    profile_id: str
    company_name: str
    industry: str
    headquarters: str
    employee_count: str
    estimated_revenue: str
    intent_signal: str
    signal_strength: int
    decision_maker_name: str
    decision_maker_title: str
    estimated_deal_size: str
    recommended_play: str
    fit_score: int
    promoted_deal_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class Deal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    company: str
    contact: str
    value: float
    stage: Literal["prospecting", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]
    probability: int
    agent_status: Literal["idle", "scanning", "thinking", "closing"]
    last_action: str
    source_target_id: Optional[str] = None
    updated_at: str = Field(default_factory=now_iso)


class DealCreate(BaseModel):
    company: str
    contact: str
    value: float
    stage: str = "prospecting"
    probability: int = 20


class DealUpdate(BaseModel):
    stage: Optional[str] = None
    probability: Optional[int] = None
    agent_status: Optional[str] = None
    last_action: Optional[str] = None


class Signal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    company: str
    domain: str
    signal_type: str
    description: str
    strength: int
    source: str
    detected_at: str = Field(default_factory=now_iso)


class Activity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    agent: str
    action: str
    target: str
    outcome: Optional[str] = None
    status: Literal["scanning", "thinking", "closing", "idle"]
    timestamp: str = Field(default_factory=now_iso)


# ============== AUTH ==============
EMERGENT_AUTH_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> User:
    """Resolve current user from cookie or Bearer header."""
    token = session_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(401, "Not authenticated")

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(401, "Invalid session")

    expires_at = session.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(401, "Session expired")

    user_doc = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(401, "User not found")
    return User(**user_doc)


async def ensure_seed_data(user_id: str):
    """Seed per-user demo data on first login if their collections are empty."""
    if await db.deals.count_documents({"user_id": user_id}) == 0:
        for d in SAMPLE_DEALS:
            deal = Deal(user_id=user_id, **d)
            await db.deals.insert_one(dict(deal.model_dump()))
    if await db.signals.count_documents({"user_id": user_id}) == 0:
        base = datetime.now(timezone.utc)
        for i, s in enumerate(SAMPLE_SIGNALS):
            sig = Signal(user_id=user_id, **s)
            sig_doc = sig.model_dump()
            sig_doc["detected_at"] = (base - timedelta(minutes=i * 7)).isoformat()
            await db.signals.insert_one(sig_doc)
    if await db.activities.count_documents({"user_id": user_id}) == 0:
        base = datetime.now(timezone.utc)
        for i, a in enumerate(SAMPLE_ACTIVITIES):
            act = Activity(user_id=user_id, **a)
            act_doc = act.model_dump()
            act_doc["timestamp"] = (base - timedelta(minutes=i * 3)).isoformat()
            await db.activities.insert_one(act_doc)


@api_router.post("/auth/session")
async def auth_session(request: Request, response: Response):
    """Exchange Emergent session_id for a session token + cookie."""
    body = await request.json()
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(400, "session_id required")

    async with httpx.AsyncClient(timeout=15.0) as http:
        r = await http.get(EMERGENT_AUTH_URL, headers={"X-Session-ID": session_id})
    if r.status_code != 200:
        raise HTTPException(401, "Auth exchange failed")
    data = r.json()
    email = data["email"]

    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": data.get("name", existing.get("name")), "picture": data.get("picture")}},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one(User(
            user_id=user_id, email=email, name=data.get("name", ""), picture=data.get("picture"),
        ).model_dump())

    session_token = data["session_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Seed demo data per user on first login
    await ensure_seed_data(user_id)

    response.set_cookie(
        key="session_token", value=session_token,
        httponly=True, secure=True, samesite="none",
        path="/", max_age=7 * 24 * 3600,
    )
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"user": user_doc, "session_token": session_token}


@api_router.get("/auth/me")
async def auth_me(user: User = Depends(get_current_user)):
    # Self-heal: seed demo data if user has none (idempotent)
    await ensure_seed_data(user.user_id)
    return user.model_dump()


@api_router.post("/auth/logout")
async def auth_logout(response: Response, request: Request, session_token: Optional[str] = Cookie(None)):
    token = session_token
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


# ============== ROUTES ==============
@api_router.get("/")
async def root():
    return {"app": "Nexus AI", "status": "operational"}


# ---------- Onboarding ----------
@api_router.post("/onboarding", response_model=OnboardingProfile)
async def create_onboarding(payload: OnboardingCreate, user: User = Depends(get_current_user)):
    profile = OnboardingProfile(user_id=user.user_id, **payload.model_dump())
    await db.profiles.insert_one(dict(profile.model_dump()))
    return profile


@api_router.get("/onboarding/latest", response_model=Optional[OnboardingProfile])
async def latest_onboarding(user: User = Depends(get_current_user)):
    doc = await db.profiles.find_one({"user_id": user.user_id}, {"_id": 0}, sort=[("created_at", -1)])
    if not doc:
        return None
    return OnboardingProfile(**doc)


@api_router.get("/onboarding/{profile_id}", response_model=OnboardingProfile)
async def get_onboarding(profile_id: str, user: User = Depends(get_current_user)):
    doc = await db.profiles.find_one({"id": profile_id, "user_id": user.user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Profile not found")
    return OnboardingProfile(**doc)


# ---------- Targets (AI-Generated) ----------
TARGETS_SYSTEM_PROMPT = """You are Nexus AI, an autonomous Chief Revenue Officer. You produce highly accurate, B2B-grade sales intelligence.

Your task: Given a company's profile (industry, ICP, value prop), generate exactly 10 realistic, highly relevant prospect companies that match their ICP.

For EACH prospect produce:
- company_name (realistic sounding mid-market company, not a Fortune 500)
- industry (specific)
- headquarters (city, country)
- employee_count (e.g. "150-300")
- estimated_revenue (e.g. "$25M - $50M ARR")
- intent_signal (specific recent signal: hiring spike, funding round, tech change, expansion, executive change, etc.)
- signal_strength (integer 60-98, with most between 75-92)
- decision_maker_name (realistic full name)
- decision_maker_title (Director/VP/Head of <function>)
- estimated_deal_size (e.g. "$85K ACV")
- recommended_play (1-line specific outreach strategy)
- fit_score (integer 70-99)

RESPOND WITH STRICT JSON ONLY. Schema:
{"targets": [ {...}, ... ]}

No markdown, no commentary, no code fences. Just raw JSON."""


@api_router.post("/targets/generate")
async def generate_targets(body: dict, user: User = Depends(get_current_user)):
    profile_id = body.get("profile_id")
    if not profile_id:
        raise HTTPException(400, "profile_id required")
    profile_doc = await db.profiles.find_one({"id": profile_id, "user_id": user.user_id}, {"_id": 0})
    if not profile_doc:
        raise HTTPException(404, "Profile not found")

    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "LLM key not configured")

    user_prompt = f"""Company Profile:
- Name: {profile_doc['company_name']}
- Industry: {profile_doc['industry']}
- Size: {profile_doc['company_size']}
- Annual Revenue: {profile_doc.get('annual_revenue', 'N/A')}
- Ideal Customer Profile: {profile_doc['icp_description']}
- Value Proposition: {profile_doc['value_proposition']}
- Target Geographies: {', '.join(profile_doc.get('target_geographies', []) or ['Global'])}

Generate 10 high-value prospect targets in strict JSON."""

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"targets-{profile_id}-{uuid.uuid4().hex[:8]}",
            system_message=TARGETS_SYSTEM_PROMPT,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")

        response_text = await chat.send_message(UserMessage(text=user_prompt))
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()
        parsed = json.loads(cleaned)
        raw_targets = parsed.get("targets", [])
    except Exception as e:
        logging.error(f"LLM error: {e}")
        raise HTTPException(500, f"AI generation failed: {str(e)[:200]}")

    if not raw_targets:
        raise HTTPException(500, "AI returned no targets — try again")

    await db.targets.delete_many({"profile_id": profile_id, "user_id": user.user_id})
    targets: List[Target] = []
    for raw in raw_targets[:10]:
        try:
            t = Target(
                user_id=user.user_id,
                profile_id=profile_id,
                company_name=str(raw.get("company_name", "Unknown")),
                industry=str(raw.get("industry", "")),
                headquarters=str(raw.get("headquarters", "")),
                employee_count=str(raw.get("employee_count", "")),
                estimated_revenue=str(raw.get("estimated_revenue", "")),
                intent_signal=str(raw.get("intent_signal", "")),
                signal_strength=int(raw.get("signal_strength", 75)),
                decision_maker_name=str(raw.get("decision_maker_name", "")),
                decision_maker_title=str(raw.get("decision_maker_title", "")),
                estimated_deal_size=str(raw.get("estimated_deal_size", "")),
                recommended_play=str(raw.get("recommended_play", "")),
                fit_score=int(raw.get("fit_score", 80)),
            )
            await db.targets.insert_one(dict(t.model_dump()))
            targets.append(t)
        except Exception as ex:
            logging.warning(f"Bad target row skipped: {ex}")

    return {"profile_id": profile_id, "count": len(targets), "targets": [t.model_dump() for t in targets]}


@api_router.get("/targets")
async def list_targets(user: User = Depends(get_current_user), profile_id: Optional[str] = None):
    query = {"user_id": user.user_id}
    if profile_id:
        query["profile_id"] = profile_id
    docs = await db.targets.find(query, {"_id": 0}).sort("fit_score", -1).to_list(50)
    return {"targets": docs}


def _parse_deal_size(s: str) -> float:
    """Extract a float from a deal-size string like '$85K ACV' or '$120,000'."""
    import re
    if not s:
        return 50000.0
    s_clean = s.replace(",", "").upper()
    m = re.search(r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*([KM]?)", s_clean)
    if not m:
        return 50000.0
    val = float(m.group(1))
    mult = m.group(2)
    if mult == "K":
        val *= 1000
    elif mult == "M":
        val *= 1_000_000
    return val


@api_router.post("/targets/{target_id}/promote")
async def promote_target(target_id: str, user: User = Depends(get_current_user)):
    """Promote a target to a pipeline deal."""
    target = await db.targets.find_one({"id": target_id, "user_id": user.user_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Target not found")
    if target.get("promoted_deal_id"):
        existing = await db.deals.find_one({"id": target["promoted_deal_id"], "user_id": user.user_id}, {"_id": 0})
        if existing:
            return {"deal": existing, "already_promoted": True}

    deal = Deal(
        user_id=user.user_id,
        company=target["company_name"],
        contact=f"{target['decision_maker_name']}, {target['decision_maker_title']}",
        value=_parse_deal_size(target["estimated_deal_size"]),
        stage="prospecting",
        probability=min(40, max(15, target.get("signal_strength", 75) // 3)),
        agent_status="scanning",
        last_action=f"Promoted from target · {target['recommended_play'][:80]}",
        source_target_id=target_id,
    )
    await db.deals.insert_one(dict(deal.model_dump()))
    await db.targets.update_one(
        {"id": target_id, "user_id": user.user_id},
        {"$set": {"promoted_deal_id": deal.id}},
    )
    # Log activity
    act = Activity(
        user_id=user.user_id,
        agent="Pipeline-Analyst",
        action="Target promoted to pipeline",
        target=target["company_name"],
        outcome=f"${int(deal.value):,} ACV",
        status="thinking",
    )
    await db.activities.insert_one(dict(act.model_dump()))
    return {"deal": deal.model_dump(), "already_promoted": False}


# ---------- Dashboard ----------
@api_router.get("/dashboard/metrics")
async def dashboard_metrics(user: User = Depends(get_current_user)):
    uid = user.user_id
    targets_count = await db.targets.count_documents({"user_id": uid})
    activities = await db.activities.count_documents({"user_id": uid})

    won = await db.deals.find({"user_id": uid, "stage": "closed_won"}, {"_id": 0, "value": 1}).to_list(500)
    won_value = sum(d.get("value", 0) for d in won)

    pipeline_open = await db.deals.find(
        {"user_id": uid, "stage": {"$in": ["prospecting", "qualified", "proposal", "negotiation"]}},
        {"_id": 0, "value": 1, "probability": 1}
    ).to_list(500)
    pipeline_value = sum(d.get("value", 0) for d in pipeline_open)
    weighted = sum(d.get("value", 0) * d.get("probability", 0) / 100 for d in pipeline_open)

    return {
        "revenue_won": won_value,
        "pipeline_value": pipeline_value,
        "weighted_pipeline": round(weighted, 2),
        "active_deals": len(pipeline_open),
        "targets_identified": targets_count,
        "activities_24h": activities,
        "agents_online": 7,
        "win_rate": 0.34,
        "avg_deal_cycle_days": 23,
        "meetings_booked_week": 18,
    }


@api_router.get("/dashboard/activity")
async def dashboard_activity(limit: int = 25, user: User = Depends(get_current_user)):
    docs = await db.activities.find({"user_id": user.user_id}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return {"activities": docs}


@api_router.get("/dashboard/charts")
async def dashboard_charts(user: User = Depends(get_current_user)):
    """Data for Recharts visuals: revenue waterfall and agent productivity."""
    uid = user.user_id
    stages = ["prospecting", "qualified", "proposal", "negotiation", "closed_won"]
    waterfall = []
    for s in stages:
        deals = await db.deals.find({"user_id": uid, "stage": s}, {"_id": 0, "value": 1, "probability": 1}).to_list(200)
        total = sum(d.get("value", 0) for d in deals)
        weighted = sum(d.get("value", 0) * d.get("probability", 0) / 100 for d in deals)
        waterfall.append({"stage": s.replace("_", " ").upper(), "total": total, "weighted": round(weighted, 0), "count": len(deals)})

    # Agent productivity: count activities per agent
    agents = ["LeadScout-7", "Outreach-Composer", "Researcher-3", "Meeting-Booker", "Negotiator-Prime", "Pipeline-Analyst", "Forecaster"]
    productivity = []
    for a in agents:
        c = await db.activities.count_documents({"user_id": uid, "agent": a})
        productivity.append({"agent": a.replace("-", " "), "actions": c})

    return {"waterfall": waterfall, "productivity": productivity}


# ---------- Lead Engine ----------
@api_router.get("/leads/signals")
async def list_signals(limit: int = 40, user: User = Depends(get_current_user)):
    docs = await db.signals.find({"user_id": user.user_id}, {"_id": 0}).sort("detected_at", -1).to_list(limit)
    return {"signals": docs}


@api_router.post("/leads/scan")
async def trigger_scan(user: User = Depends(get_current_user)):
    new_signals = []
    sample_pool = SAMPLE_SIGNALS.copy()
    random.shuffle(sample_pool)
    for raw in sample_pool[:random.randint(3, 5)]:
        s = Signal(user_id=user.user_id, **raw)
        await db.signals.insert_one(dict(s.model_dump()))
        new_signals.append(s.model_dump())

    act = Activity(
        user_id=user.user_id,
        agent="LeadScout-7",
        action="Web scan completed across 12,400 sources",
        target=f"{len(new_signals)} new high-intent signals captured",
        status="scanning",
    )
    await db.activities.insert_one(dict(act.model_dump()))
    return {"scanned": True, "new_signals": new_signals}


# ---------- Pipeline ----------
@api_router.get("/pipeline/deals")
async def list_deals(user: User = Depends(get_current_user)):
    docs = await db.deals.find({"user_id": user.user_id}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return {"deals": docs}


@api_router.post("/pipeline/deals", response_model=Deal)
async def create_deal(payload: DealCreate, user: User = Depends(get_current_user)):
    deal = Deal(
        user_id=user.user_id,
        company=payload.company,
        contact=payload.contact,
        value=payload.value,
        stage=payload.stage,
        probability=payload.probability,
        agent_status="idle",
        last_action="Deal created",
    )
    await db.deals.insert_one(dict(deal.model_dump()))
    return deal


@api_router.patch("/pipeline/deals/{deal_id}", response_model=Deal)
async def update_deal(deal_id: str, payload: DealUpdate, user: User = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = now_iso()
    res = await db.deals.update_one({"id": deal_id, "user_id": user.user_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Deal not found")
    doc = await db.deals.find_one({"id": deal_id, "user_id": user.user_id}, {"_id": 0})
    return Deal(**doc)


# ---------- Stripe Payments ----------
PACKAGES = {
    "operator": {"amount": 4800.0, "name": "Operator", "description": "3 AI agents · 500 prospects/mo"},
    "scale":    {"amount": 18500.0, "name": "Scale",   "description": "7 AI agents · Unlimited prospects"},
}


class CheckoutCreate(BaseModel):
    package_id: str
    origin_url: str


@api_router.post("/payments/checkout/session")
async def create_checkout(payload: CheckoutCreate, request: Request, user: User = Depends(get_current_user)):
    pkg = PACKAGES.get(payload.package_id)
    if not pkg:
        raise HTTPException(400, "Invalid package")
    if not STRIPE_API_KEY:
        raise HTTPException(500, "Stripe not configured")

    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe".replace("//api", "/api")
    stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    origin = payload.origin_url.rstrip("/")
    success_url = f"{origin}/app/checkout-return?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/app/dashboard"

    req = CheckoutSessionRequest(
        amount=pkg["amount"],
        currency="usd",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": user.user_id, "package_id": payload.package_id, "email": user.email},
    )
    session = await stripe.create_checkout_session(req)

    await db.payment_transactions.insert_one({
        "session_id": session.session_id,
        "user_id": user.user_id,
        "email": user.email,
        "package_id": payload.package_id,
        "amount": pkg["amount"],
        "currency": "usd",
        "payment_status": "initiated",
        "status": "open",
        "metadata": {"package_id": payload.package_id, "user_id": user.user_id},
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })

    return {"url": session.url, "session_id": session.session_id}


@api_router.get("/payments/checkout/status/{session_id}")
async def checkout_status(session_id: str, request: Request, user: User = Depends(get_current_user)):
    if not STRIPE_API_KEY:
        raise HTTPException(500, "Stripe not configured")
    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe".replace("//api", "/api")
    stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    txn = await db.payment_transactions.find_one({"session_id": session_id, "user_id": user.user_id}, {"_id": 0})
    if not txn:
        raise HTTPException(404, "Transaction not found")

    status: CheckoutStatusResponse = await stripe.get_checkout_status(session_id)

    new_payment_status = status.payment_status
    if txn["payment_status"] != "paid" and new_payment_status == "paid":
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": new_payment_status, "status": status.status, "updated_at": now_iso()}},
        )
        await db.users.update_one(
            {"user_id": user.user_id},
            {"$set": {"subscription_package": txn.get("package_id"), "subscription_active": True, "subscribed_at": now_iso()}},
        )
        # Activity log
        act = Activity(
            user_id=user.user_id,
            agent="Pipeline-Analyst",
            action="Subscription activated",
            target=PACKAGES.get(txn.get("package_id"), {}).get("name", "Plan"),
            outcome=f"${txn.get('amount', 0):,.0f}/mo",
            status="closing",
        )
        await db.activities.insert_one(dict(act.model_dump()))
    elif txn["payment_status"] != new_payment_status:
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": new_payment_status, "status": status.status, "updated_at": now_iso()}},
        )

    return {
        "session_id": session_id,
        "status": status.status,
        "payment_status": new_payment_status,
        "amount_total": status.amount_total,
        "currency": status.currency,
        "package_id": txn.get("package_id"),
    }


@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    if not STRIPE_API_KEY:
        return {"ok": False}
    body = await request.body()
    sig = request.headers.get("Stripe-Signature")
    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe".replace("//api", "/api")
    stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    try:
        evt = await stripe.handle_webhook(body, sig)
    except Exception as e:
        logging.error(f"Stripe webhook error: {e}")
        return {"ok": False}

    if evt.session_id:
        await db.payment_transactions.update_one(
            {"session_id": evt.session_id},
            {"$set": {"payment_status": evt.payment_status, "webhook_event": evt.event_type, "updated_at": now_iso()}},
        )
    return {"ok": True}


@api_router.get("/payments/packages")
async def list_packages():
    return {"packages": [{"id": k, **v} for k, v in PACKAGES.items()]}


# ============== SEED DATA ==============
SAMPLE_SIGNALS = [
    {"company": "Linearflow Systems", "domain": "linearflow.io", "signal_type": "hiring", "description": "Posted 14 SDR + AE roles in 6 days", "strength": 92, "source": "LinkedIn Jobs"},
    {"company": "Vantix Health", "domain": "vantix.health", "signal_type": "funding", "description": "Series B closed — $48M led by Insight Partners", "strength": 96, "source": "Crunchbase"},
    {"company": "Northwind Robotics", "domain": "northwind.ai", "signal_type": "tech_change", "description": "Detected Salesforce → HubSpot migration in progress", "strength": 84, "source": "BuiltWith"},
    {"company": "Cobalt Logistics", "domain": "cobaltlogistics.com", "signal_type": "expansion", "description": "Opened EMEA HQ, hired regional CRO", "strength": 89, "source": "Press release"},
    {"company": "Polaris Bioworks", "domain": "polarisbio.com", "signal_type": "social", "description": "Founder posted: 'rebuilding GTM team from zero'", "strength": 78, "source": "LinkedIn"},
    {"company": "Helios Energy Grid", "domain": "heliosgrid.io", "signal_type": "funding", "description": "Series C — $120M for North American expansion", "strength": 94, "source": "TechCrunch"},
    {"company": "Kestrel Defense", "domain": "kestrel.aero", "signal_type": "hiring", "description": "9 GTM roles posted, including VP Sales", "strength": 88, "source": "LinkedIn Jobs"},
    {"company": "Tessera Analytics", "domain": "tessera.ai", "signal_type": "tech_change", "description": "Replaced legacy BI stack — actively evaluating vendors", "strength": 81, "source": "G2"},
    {"company": "Mendel Genomics", "domain": "mendelgenomics.com", "signal_type": "expansion", "description": "Launched commercial division — new CRO appointed", "strength": 86, "source": "Press release"},
    {"company": "Quantica Materials", "domain": "quantica.io", "signal_type": "funding", "description": "Series A — $22M to scale enterprise GTM", "strength": 83, "source": "Crunchbase"},
    {"company": "Solace Fintech", "domain": "solace.finance", "signal_type": "hiring", "description": "Posted Head of Revenue Operations role", "strength": 80, "source": "LinkedIn"},
    {"company": "Atlas Manufacturing", "domain": "atlasmfg.com", "signal_type": "tech_change", "description": "Implementing ERP modernization — RFP active", "strength": 77, "source": "Procurement signal"},
]

SAMPLE_DEALS = [
    {"company": "Linearflow Systems", "contact": "Marcus Chen, VP Sales Ops", "value": 145000, "stage": "negotiation", "probability": 75, "agent_status": "closing", "last_action": "Sent redline contract — awaiting legal"},
    {"company": "Vantix Health", "contact": "Priya Raman, CRO", "value": 280000, "stage": "proposal", "probability": 55, "agent_status": "thinking", "last_action": "Drafting ROI model based on call notes"},
    {"company": "Northwind Robotics", "contact": "Erik Lindqvist, Head of GTM", "value": 92000, "stage": "qualified", "probability": 40, "agent_status": "scanning", "last_action": "Researching org chart depth"},
    {"company": "Cobalt Logistics", "contact": "Diane Okafor, VP Commercial", "value": 165000, "stage": "qualified", "probability": 45, "agent_status": "thinking", "last_action": "Composing multithreaded outreach"},
    {"company": "Polaris Bioworks", "contact": "Dr. Helena Voss, COO", "value": 220000, "stage": "prospecting", "probability": 20, "agent_status": "scanning", "last_action": "Monitoring founder LinkedIn cadence"},
    {"company": "Helios Energy Grid", "contact": "Rafael Mendes, CFO", "value": 410000, "stage": "proposal", "probability": 60, "agent_status": "closing", "last_action": "Sent procurement-ready proposal v3"},
    {"company": "Kestrel Defense", "contact": "Col. (Ret.) James Park, VP Sales", "value": 320000, "stage": "negotiation", "probability": 80, "agent_status": "closing", "last_action": "Final pricing approved by buyer"},
    {"company": "Tessera Analytics", "contact": "Amelia Kwon, Head of Data", "value": 88000, "stage": "prospecting", "probability": 15, "agent_status": "idle", "last_action": "Queued for next-cycle outreach"},
    {"company": "Mendel Genomics", "contact": "Sven Almqvist, CRO", "value": 195000, "stage": "qualified", "probability": 50, "agent_status": "thinking", "last_action": "Personalizing exec brief"},
    {"company": "Quantica Materials", "contact": "Lina Park, VP Revenue", "value": 76000, "stage": "closed_won", "probability": 100, "agent_status": "idle", "last_action": "Closed — $76K ACV won"},
    {"company": "Solace Fintech", "contact": "Tomás García, Head of RevOps", "value": 120000, "stage": "closed_won", "probability": 100, "agent_status": "idle", "last_action": "Closed — $120K ACV won"},
]

SAMPLE_ACTIVITIES = [
    {"agent": "LeadScout-7", "action": "Identified 3 high-intent signals", "target": "Vantix Health", "outcome": "Score 96/100", "status": "scanning"},
    {"agent": "Outreach-Composer", "action": "Generated multithreaded sequence", "target": "Linearflow Systems", "outcome": "5 personas, 14 touches", "status": "thinking"},
    {"agent": "Negotiator-Prime", "action": "Drafted redline counter-proposal", "target": "Kestrel Defense", "outcome": "$320K — 80% close prob", "status": "closing"},
    {"agent": "Pipeline-Analyst", "action": "Flagged stale deal for re-engagement", "target": "Tessera Analytics", "outcome": "Queued nurture", "status": "idle"},
    {"agent": "LeadScout-7", "action": "Funding signal detected", "target": "Helios Energy Grid", "outcome": "Series C — $120M", "status": "scanning"},
    {"agent": "Meeting-Booker", "action": "Booked discovery call", "target": "Cobalt Logistics", "outcome": "Wed 2:30pm with VP Commercial", "status": "closing"},
    {"agent": "Researcher-3", "action": "Built org-chart depth map", "target": "Northwind Robotics", "outcome": "9 personas surfaced", "status": "thinking"},
    {"agent": "Outreach-Composer", "action": "A/B test variant launched", "target": "Mendel Genomics", "outcome": "v2 opens +37%", "status": "thinking"},
    {"agent": "Negotiator-Prime", "action": "Pricing model recalibrated", "target": "Helios Energy Grid", "outcome": "Discount band locked", "status": "closing"},
    {"agent": "LeadScout-7", "action": "Tech-stack migration detected", "target": "Atlas Manufacturing", "outcome": "ERP RFP underway", "status": "scanning"},
    {"agent": "Pipeline-Analyst", "action": "Velocity report generated", "target": "Q1 Pipeline", "outcome": "Avg cycle: 23d (-6d MoM)", "status": "idle"},
    {"agent": "Meeting-Booker", "action": "3 meetings booked", "target": "Polaris, Vantix, Quantica", "outcome": "All this week", "status": "closing"},
]


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
