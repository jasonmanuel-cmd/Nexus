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
from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from emergentintegrations.llm.chat import LlmChat, UserMessage
from integrations import square_client as sq
from integrations.notifications import send_email, send_slack

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Nexus AI starting up")
    yield
    client.close()
    logging.info("Nexus AI shut down")


app = FastAPI(title="Nexus AI - Autonomous CRO", lifespan=lifespan)
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

    # Fire personalized outreach email (MOCKED via stub) + Slack
    dm_name = target.get("decision_maker_name", "there")
    dm_first = dm_name.split(" ")[0] if dm_name else "there"
    intro_subject = f"Quick thought on {target['company_name']}'s {target.get('signal_strength', 0)}/100 intent signal"
    intro_body = (
        f"Hi {dm_first},\n\n"
        f"Noticed {target['company_name']} just hit a fresh signal: {target.get('intent_signal','')}. "
        f"For teams like yours at that stage, we're typically able to compress sales cycles 30%+.\n\n"
        f"Worth a 15-min look? I'll send 2-3 options.\n\n"
        f"— Nexus AI on behalf of {user.name or user.email}"
    )
    await send_email(
        db,
        to=f"{dm_first.lower()}@{target.get('company_name', 'example').lower().replace(' ', '')}.com",
        subject=intro_subject,
        body=intro_body,
        user_id=user.user_id,
        kind="promote.intro",
        meta={"target_id": target_id, "deal_id": deal.id, "decision_maker": dm_name},
    )
    await send_slack(
        db,
        text=f":sparkles: *{target['company_name']}* promoted to pipeline · ${int(deal.value):,} · DM: {dm_name}",
        user_id=user.user_id,
        kind="target.promoted",
        meta={"target_id": target_id, "deal_id": deal.id},
    )

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
async def dashboard_activity(limit: int = 100, user: User = Depends(get_current_user)):
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
    existing = await db.deals.find_one({"id": deal_id, "user_id": user.user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Deal not found")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = now_iso()
    await db.deals.update_one({"id": deal_id, "user_id": user.user_id}, {"$set": updates})
    doc = await db.deals.find_one({"id": deal_id, "user_id": user.user_id}, {"_id": 0})

    # Slack notification on stage change
    if payload.stage and payload.stage != existing.get("stage"):
        emoji = ":tada:" if payload.stage == "closed_won" else ":chart_with_upwards_trend:"
        await send_slack(
            db,
            text=f"{emoji} *{doc['company']}* moved {existing.get('stage')} → *{payload.stage}* (${doc.get('value', 0):,.0f})",
            user_id=user.user_id,
            kind=f"deal.stage.{payload.stage}",
            meta={"deal_id": deal_id, "from": existing.get("stage"), "to": payload.stage},
        )
        if payload.stage == "closed_won":
            await send_email(
                db,
                to=user.email,
                subject=f"🎉 Deal won: {doc['company']} (${doc.get('value', 0):,.0f})",
                body=f"Congrats — your AI agents just closed {doc['company']} for ${doc.get('value', 0):,.0f}.\n\nContact: {doc.get('contact')}\nLast action: {doc.get('last_action')}",
                user_id=user.user_id,
                kind="deal.won",
                meta={"deal_id": deal_id},
            )
    return Deal(**doc)


# ---------- Square Payments ----------
PACKAGES = sq.PACKAGES


class CheckoutCreate(BaseModel):
    package_id: str
    origin_url: str


@api_router.post("/payments/checkout/session")
async def create_checkout(payload: CheckoutCreate, user: User = Depends(get_current_user)):
    if payload.package_id not in PACKAGES:
        raise HTTPException(400, "Invalid package")
    if not os.environ.get("SQUARE_ACCESS_TOKEN"):
        raise HTTPException(500, "Square not configured")

    origin = payload.origin_url.rstrip("/")
    redirect_url = f"{origin}/app/checkout-return"

    try:
        link = await sq.create_payment_link(
            package_id=payload.package_id,
            redirect_url=redirect_url,
            user_id=user.user_id,
            email=user.email,
        )
    except Exception as e:
        logging.error(f"Square link create failed: {e}")
        raise HTTPException(502, f"Square error: {str(e)[:160]}")

    await db.payment_transactions.insert_one({
        "session_id": link["id"],          # Square payment_link id
        "order_id": link.get("order_id"),
        "user_id": user.user_id,
        "email": user.email,
        "package_id": payload.package_id,
        "amount": PACKAGES[payload.package_id]["amount"],
        "currency": "usd",
        "payment_status": "initiated",
        "status": "open",
        "provider": "square",
        "metadata": {"package_id": payload.package_id, "user_id": user.user_id},
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })

    return {"url": link["url"], "session_id": link["id"]}


@api_router.get("/payments/checkout/status/{session_id}")
async def checkout_status(session_id: str, user: User = Depends(get_current_user)):
    txn = await db.payment_transactions.find_one({"session_id": session_id, "user_id": user.user_id}, {"_id": 0})
    if not txn:
        raise HTTPException(404, "Transaction not found")

    # Try to query Square for order status if we have an order_id
    order_id = txn.get("order_id")
    detected_paid = False
    try:
        if order_id:
            order = await sq.get_order(order_id)
            state = (order.get("state") or "").upper()
            if state == "COMPLETED":
                detected_paid = True
    except Exception as e:
        logging.warning(f"Square order lookup failed for {order_id}: {e}")

    new_payment_status = "paid" if detected_paid else txn.get("payment_status", "initiated")
    if detected_paid and txn["payment_status"] != "paid":
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": "paid", "status": "complete", "updated_at": now_iso()}},
        )
        await db.users.update_one(
            {"user_id": user.user_id},
            {"$set": {
                "subscription_package": txn.get("package_id"),
                "subscription_active": True,
                "subscribed_at": now_iso(),
                "renews_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            }},
        )
        act = Activity(
            user_id=user.user_id,
            agent="Pipeline-Analyst",
            action="Subscription activated",
            target=PACKAGES.get(txn.get("package_id"), {}).get("name", "Plan"),
            outcome=f"${txn.get('amount', 0):,.0f}/mo",
            status="closing",
        )
        await db.activities.insert_one(dict(act.model_dump()))
        await send_slack(
            db,
            text=f":rocket: *{user.email}* activated *{PACKAGES.get(txn.get('package_id'), {}).get('name', 'Plan')}* plan (${txn.get('amount', 0):,.0f}/mo)",
            user_id=user.user_id,
            kind="subscription.activated",
        )

    return {
        "session_id": session_id,
        "status": "complete" if detected_paid else txn.get("status", "open"),
        "payment_status": new_payment_status,
        "amount_total": int(txn.get("amount", 0) * 100),
        "currency": txn.get("currency", "usd"),
        "package_id": txn.get("package_id"),
        "provider": "square",
    }


@api_router.post("/webhook/square")
async def square_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("x-square-hmacsha256-signature", "")
    if not sq.validate_webhook(raw, sig):
        logging.warning("Square webhook signature mismatch")
        return Response(status_code=400)

    try:
        evt = json.loads(raw.decode("utf-8"))
    except Exception:
        return Response(status_code=400)

    event_type = evt.get("type", "")
    data = evt.get("data", {}).get("object", {}) or {}
    logging.info(f"Square webhook: {event_type}")

    # Payment events: mark transaction paid
    if event_type.startswith("payment."):
        payment = data.get("payment") or {}
        order_id = payment.get("order_id")
        status = (payment.get("status") or "").upper()
        if order_id and status == "COMPLETED":
            await db.payment_transactions.update_one(
                {"order_id": order_id},
                {"$set": {"payment_status": "paid", "status": "complete", "updated_at": now_iso()}},
            )
            txn = await db.payment_transactions.find_one({"order_id": order_id}, {"_id": 0})
            if txn:
                await db.users.update_one(
                    {"user_id": txn["user_id"]},
                    {"$set": {
                        "subscription_package": txn.get("package_id"),
                        "subscription_active": True,
                        "subscribed_at": now_iso(),
                        "renews_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                    }},
                )
    return {"ok": True}


@api_router.get("/payments/packages")
async def list_packages():
    return {"packages": [{"id": k, **v} for k, v in PACKAGES.items()]}


@api_router.get("/payments/subscription")
async def get_subscription(user: User = Depends(get_current_user)):
    """Return current subscription state for the authenticated user."""
    u = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    return {
        "active": bool(u.get("subscription_active")),
        "package_id": u.get("subscription_package"),
        "package": PACKAGES.get(u.get("subscription_package") or "", None),
        "subscribed_at": u.get("subscribed_at"),
        "renews_at": u.get("renews_at"),
    }


@api_router.post("/payments/subscription/cancel_legacy")
async def cancel_subscription_legacy(user: User = Depends(get_current_user)):
    """Deprecated — kept for backward compat. New endpoint also at /payments/subscription/cancel uses Square Subscriptions API."""
    u = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    if not u or not u.get("subscription_active"):
        raise HTTPException(404, "No active subscription")
    pkg_id = u.get("subscription_package")
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"subscription_active": False, "canceled_at": now_iso()}},
    )
    return {"ok": True, "canceled_package": pkg_id}


# ---------- Outbox (for inspecting MOCKED notifications) ----------
@api_router.get("/notifications/outbox")
async def get_outbox(user: User = Depends(get_current_user), limit: int = 50):
    emails = await db.email_outbox.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    slacks = await db.slack_outbox.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"emails": emails, "slack_messages": slacks}


# ---------- Autonomous Reply Loop ----------
REPLY_SIMULATION_PROMPT = """You are simulating a realistic B2B buyer's reply to a cold outreach email.

You will receive: (1) the original outreach (subject + body), (2) the prospect company name + decision-maker name/title.

Generate ONE plausible reply. Vary tone naturally — sometimes interested, sometimes skeptical, sometimes deferring, sometimes objecting on price/timing, occasionally enthusiastic. Match how a real executive would write — concise, no fluff, 2-4 sentences max. After the reply, classify it.

Then, draft Nexus AI's CONTEXTUAL follow-up that:
- Directly addresses the specific point the buyer raised (don't repeat the original pitch)
- If positive/interested → propose specific next step (15-min slot, demo Tuesday/Wednesday, send pricing)
- If wants info → send a concrete artifact (ROI model, case study, pricing tier)
- If objecting on price/timing → reframe with a small commitment (pilot, 30-day trial)
- If not_now / deferring → polite nurture, schedule check-in for a future quarter
- Always be specific, never generic. Mention something from their reply.

Also compute a probability_delta (integer):
- positive/interested → +20 to +30
- wants_info → +10
- neutral → 0
- objecting → -5 to -10
- not_now → -15 to -20

RESPOND WITH STRICT JSON ONLY (no markdown, no code fences):
{
  "buyer_reply": {
    "body": "<2-4 sentence realistic reply>",
    "sentiment": "positive|neutral|negative",
    "intent": "interested|wants_info|deferring|objecting|not_now"
  },
  "drafted_followup": {
    "subject": "<concrete subject>",
    "body": "<contextual follow-up, 3-6 sentences>",
    "probability_delta": <int>,
    "confidence": <int 0-100, your confidence the buyer will engage if we send this>,
    "suggested_action": "<one-line action for the human reviewer>"
  }
}"""


class EmailReply(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    original_email_id: str
    from_address: str
    body: str
    sentiment: str
    intent: str
    received_at: str = Field(default_factory=now_iso)


class ReplyDraft(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    reply_id: str
    original_email_id: str
    deal_id: Optional[str] = None
    subject: str
    body: str
    probability_delta: int = 0
    confidence: int = 70
    suggested_action: str = ""
    sentiment: str
    intent: str
    status: Literal["pending", "sent", "dismissed", "auto_sent"] = "pending"
    auto_sent: bool = False
    created_at: str = Field(default_factory=now_iso)
    sent_at: Optional[str] = None


@api_router.post("/notifications/email/{email_id}/simulate-reply")
async def simulate_reply(email_id: str, user: User = Depends(get_current_user)):
    """Generate a plausible buyer reply via Claude + an AI-drafted follow-up. Stores both."""
    email_doc = await db.email_outbox.find_one({"id": email_id, "user_id": user.user_id}, {"_id": 0})
    if not email_doc:
        raise HTTPException(404, "Email not found")
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "LLM key not configured")

    # Resolve deal context if email is linked to a target/deal
    target_meta = email_doc.get("meta") or {}
    deal_id = target_meta.get("deal_id")
    target_id = target_meta.get("target_id")
    deal_doc = None
    target_doc = None
    if deal_id:
        deal_doc = await db.deals.find_one({"id": deal_id, "user_id": user.user_id}, {"_id": 0})
    if target_id:
        target_doc = await db.targets.find_one({"id": target_id, "user_id": user.user_id}, {"_id": 0})

    company = (deal_doc or {}).get("company") or (target_doc or {}).get("company_name") or "Unknown Co"
    contact = (deal_doc or {}).get("contact") or f"{(target_doc or {}).get('decision_maker_name', 'Decision Maker')}, {(target_doc or {}).get('decision_maker_title', 'VP')}"

    user_prompt = f"""Original outreach:
SUBJECT: {email_doc.get('subject', '')}
BODY:
{email_doc.get('body', '')}

Prospect: {company}
Decision-maker: {contact}
Intent signal: {(target_doc or {}).get('intent_signal', 'n/a')}

Generate the buyer reply + Nexus AI's drafted follow-up in strict JSON."""

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"reply-{email_id}-{uuid.uuid4().hex[:8]}",
            system_message=REPLY_SIMULATION_PROMPT,
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
    except Exception as e:
        logging.error(f"Reply simulation LLM error: {e}")
        raise HTTPException(500, f"AI failed: {str(e)[:160]}")

    buyer = parsed.get("buyer_reply", {})
    draft = parsed.get("drafted_followup", {})

    reply = EmailReply(
        user_id=user.user_id,
        original_email_id=email_id,
        from_address=email_doc.get("to", ""),
        body=str(buyer.get("body", "")),
        sentiment=str(buyer.get("sentiment", "neutral")),
        intent=str(buyer.get("intent", "wants_info")),
    )
    await db.email_replies.insert_one(dict(reply.model_dump()))

    draft_obj = ReplyDraft(
        user_id=user.user_id,
        reply_id=reply.id,
        original_email_id=email_id,
        deal_id=deal_id,
        subject=str(draft.get("subject", f"Re: {email_doc.get('subject', '')}")),
        body=str(draft.get("body", "")),
        probability_delta=int(draft.get("probability_delta", 0)),
        confidence=int(draft.get("confidence", 70)),
        suggested_action=str(draft.get("suggested_action", "")),
        sentiment=reply.sentiment,
        intent=reply.intent,
    )

    # Auto-send guard: user settings + Claude confidence + positive sentiment + meaningful delta
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    auto_send_enabled = bool(user_doc.get("auto_send_enabled", False))
    threshold = int(user_doc.get("auto_send_threshold", 85))
    will_auto_send = (
        auto_send_enabled
        and draft_obj.confidence >= threshold
        and draft_obj.sentiment == "positive"
        and draft_obj.probability_delta >= 15
    )
    if will_auto_send:
        draft_obj.status = "auto_sent"
        draft_obj.auto_sent = True
        draft_obj.sent_at = now_iso()

    await db.reply_drafts.insert_one(dict(draft_obj.model_dump()))

    # Log activity
    act = Activity(
        user_id=user.user_id,
        agent="Outreach-Composer",
        action=f"Buyer replied ({reply.sentiment}) — draft awaiting review",
        target=company,
        outcome=f"{reply.intent} · Δ{draft_obj.probability_delta:+d}%",
        status="thinking",
    )
    await db.activities.insert_one(dict(act.model_dump()))
    await send_slack(
        db,
        text=f":speech_balloon: *{company}* replied ({reply.sentiment}/{reply.intent}). " +
             ("*Auto-sent* follow-up." if will_auto_send else "Draft ready for review."),
        user_id=user.user_id,
        kind="reply.received",
        meta={"reply_id": reply.id, "draft_id": draft_obj.id, "auto_sent": will_auto_send},
    )

    # If auto-sent: actually fire the email + update deal probability
    if will_auto_send:
        await send_email(
            db,
            to=reply.from_address,
            subject=draft_obj.subject,
            body=draft_obj.body,
            user_id=user.user_id,
            kind="reply.followup",
            meta={"draft_id": draft_obj.id, "in_reply_to": email_id, "auto_sent": True},
        )
        if deal_id:
            deal_doc_pre = await db.deals.find_one({"id": deal_id, "user_id": user.user_id}, {"_id": 0})
            if deal_doc_pre:
                new_prob = max(0, min(100, int(deal_doc_pre.get("probability", 0)) + draft_obj.probability_delta))
                await db.deals.update_one(
                    {"id": deal_id, "user_id": user.user_id},
                    {"$set": {
                        "probability": new_prob,
                        "agent_status": "closing",
                        "last_action": f"Auto-replied to buyer (confidence {draft_obj.confidence}%) · prob {deal_doc_pre.get('probability',0)}%→{new_prob}%",
                        "updated_at": now_iso(),
                    }},
                )

    return {"reply": reply.model_dump(), "draft": draft_obj.model_dump(), "auto_sent": will_auto_send}


@api_router.get("/replies/queue")
async def list_drafts(user: User = Depends(get_current_user)):
    """Pending drafts awaiting review. Joins the original email + buyer reply."""
    drafts = await db.reply_drafts.find({"user_id": user.user_id, "status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(100)
    enriched = []
    for d in drafts:
        reply = await db.email_replies.find_one({"id": d["reply_id"], "user_id": user.user_id}, {"_id": 0})
        original = await db.email_outbox.find_one({"id": d["original_email_id"], "user_id": user.user_id}, {"_id": 0})
        deal = None
        if d.get("deal_id"):
            deal = await db.deals.find_one({"id": d["deal_id"], "user_id": user.user_id}, {"_id": 0})
        enriched.append({"draft": d, "reply": reply, "original": original, "deal": deal})
    return {"drafts": enriched}


class DraftSend(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


@api_router.post("/replies/{draft_id}/send")
async def send_draft(draft_id: str, payload: DraftSend, user: User = Depends(get_current_user)):
    d = await db.reply_drafts.find_one({"id": draft_id, "user_id": user.user_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Draft not found")
    if d["status"] != "pending":
        raise HTTPException(409, "Draft already actioned")

    final_subject = payload.subject if payload.subject is not None else d["subject"]
    final_body = payload.body if payload.body is not None else d["body"]
    reply = await db.email_replies.find_one({"id": d["reply_id"], "user_id": user.user_id}, {"_id": 0})

    # Queue the actual outbound email (MOCKED)
    await send_email(
        db,
        to=(reply or {}).get("from_address", ""),
        subject=final_subject,
        body=final_body,
        user_id=user.user_id,
        kind="reply.followup",
        meta={"draft_id": draft_id, "in_reply_to": d["original_email_id"]},
    )

    await db.reply_drafts.update_one(
        {"id": draft_id, "user_id": user.user_id},
        {"$set": {"status": "sent", "sent_at": now_iso(), "subject": final_subject, "body": final_body}},
    )

    # Adjust deal probability + agent_status
    if d.get("deal_id"):
        deal = await db.deals.find_one({"id": d["deal_id"], "user_id": user.user_id}, {"_id": 0})
        if deal:
            new_prob = max(0, min(100, int(deal.get("probability", 0)) + int(d.get("probability_delta", 0))))
            await db.deals.update_one(
                {"id": d["deal_id"], "user_id": user.user_id},
                {"$set": {
                    "probability": new_prob,
                    "agent_status": "closing" if d.get("sentiment") == "positive" else "thinking",
                    "last_action": f"Replied to buyer ({d.get('intent')}) · prob {deal.get('probability',0)}%→{new_prob}%",
                    "updated_at": now_iso(),
                }},
            )

    act = Activity(
        user_id=user.user_id,
        agent="Outreach-Composer",
        action="Reply sent",
        target=(reply or {}).get("from_address", ""),
        outcome=f"Δ{d.get('probability_delta', 0):+d}% probability",
        status="closing" if d.get("sentiment") == "positive" else "thinking",
    )
    await db.activities.insert_one(dict(act.model_dump()))
    return {"ok": True, "draft_id": draft_id}


@api_router.delete("/replies/{draft_id}")
async def dismiss_draft(draft_id: str, user: User = Depends(get_current_user)):
    res = await db.reply_drafts.update_one(
        {"id": draft_id, "user_id": user.user_id, "status": "pending"},
        {"$set": {"status": "dismissed"}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Draft not found or already actioned")
    return {"ok": True}


@api_router.get("/replies/stats")
async def reply_stats(user: User = Depends(get_current_user)):
    pending = await db.reply_drafts.count_documents({"user_id": user.user_id, "status": "pending"})
    sent = await db.reply_drafts.count_documents({"user_id": user.user_id, "status": {"$in": ["sent", "auto_sent"]}})
    received = await db.email_replies.count_documents({"user_id": user.user_id})
    auto_sent = await db.reply_drafts.count_documents({"user_id": user.user_id, "status": "auto_sent"})
    return {"pending": pending, "sent": sent, "received": received, "auto_sent": auto_sent}


# ---------- Square Recurring Subscriptions (real, via Web Payments SDK) ----------
@api_router.get("/payments/config")
async def payments_config():
    """Public — frontend needs these to mount Square Web Payments SDK."""
    return {
        "application_id": os.environ.get("SQUARE_APPLICATION_ID"),
        "location_id": os.environ.get("SQUARE_LOCATION_ID"),
        "environment": os.environ.get("SQUARE_ENVIRONMENT", "sandbox"),
    }


class SubscribePayload(BaseModel):
    package_id: str
    source_id: str  # Square Web Payments SDK card-nonce
    cardholder_name: Optional[str] = None


@api_router.post("/payments/subscribe")
async def create_recurring_subscription(payload: SubscribePayload, user: User = Depends(get_current_user)):
    if payload.package_id not in sq.PACKAGES:
        raise HTTPException(400, "Invalid package")

    try:
        customer_id = await sq.upsert_customer(email=user.email, name=user.name or user.email, user_id=user.user_id)
        card_id = await sq.create_card_on_file(customer_id=customer_id, source_id=payload.source_id, cardholder=payload.cardholder_name or user.name or user.email)
        sub = await sq.create_subscription(package_id=payload.package_id, customer_id=customer_id, card_id=card_id)
    except Exception as e:
        logging.error(f"Square subscription error: {e}")
        raise HTTPException(502, f"Square error: {str(e)[:200]}")

    await db.payment_transactions.insert_one({
        "session_id": sub["id"],
        "subscription_id": sub["id"],
        "user_id": user.user_id,
        "email": user.email,
        "package_id": payload.package_id,
        "amount": sq.PACKAGES[payload.package_id]["amount"],
        "currency": "usd",
        "payment_status": "paid",
        "status": "complete",
        "provider": "square_subscription",
        "square_customer_id": customer_id,
        "square_card_id": card_id,
        "metadata": {"package_id": payload.package_id, "user_id": user.user_id},
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {
            "subscription_package": payload.package_id,
            "subscription_active": True,
            "subscription_id": sub["id"],
            "square_customer_id": customer_id,
            "square_card_id": card_id,
            "subscribed_at": now_iso(),
            "renews_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }},
    )
    act = Activity(
        user_id=user.user_id,
        agent="Pipeline-Analyst",
        action="Recurring subscription activated",
        target=sq.PACKAGES[payload.package_id]["name"],
        outcome=f"${sq.PACKAGES[payload.package_id]['amount']:,.0f}/mo · Square sub {sub['id']}",
        status="closing",
    )
    await db.activities.insert_one(dict(act.model_dump()))
    await send_slack(
        db,
        text=f":rocket: *{user.email}* started recurring *{sq.PACKAGES[payload.package_id]['name']}* (${sq.PACKAGES[payload.package_id]['amount']:,.0f}/mo)",
        user_id=user.user_id,
        kind="subscription.recurring.activated",
    )

    return {"ok": True, "subscription_id": sub["id"], "status": sub.get("status")}


@api_router.post("/payments/subscription/cancel")
async def cancel_recurring_subscription(user: User = Depends(get_current_user)):
    u = await db.users.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    if not u.get("subscription_active"):
        raise HTTPException(404, "No active subscription")
    sub_id = u.get("subscription_id")
    canceled_remote = None
    if sub_id:
        try:
            canceled_remote = await sq.cancel_subscription(sub_id)
        except Exception as e:
            logging.warning(f"Square cancel failed (will still mark locally): {e}")
    pkg_id = u.get("subscription_package")
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"subscription_active": False, "canceled_at": now_iso()}},
    )
    act = Activity(
        user_id=user.user_id,
        agent="Pipeline-Analyst",
        action="Subscription canceled",
        target=sq.PACKAGES.get(pkg_id or "", {}).get("name", "Plan"),
        status="idle",
    )
    await db.activities.insert_one(dict(act.model_dump()))
    await send_slack(
        db,
        text=f":wave: *{user.email}* canceled *{sq.PACKAGES.get(pkg_id or '', {}).get('name', 'Plan')}* plan",
        user_id=user.user_id,
        kind="subscription.canceled",
    )
    return {"ok": True, "canceled_package": pkg_id, "square_status": (canceled_remote or {}).get("status")}


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

# Modular routers (extracted from server.py for maintainability)
from routers.settings import router as settings_router
app.include_router(settings_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
