from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json
import random
import logging
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from emergentintegrations.llm.chat import LlmChat, UserMessage

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')

app = FastAPI(title="Nexus AI - Autonomous CRO")
api_router = APIRouter(prefix="/api")


# ============== MODELS ==============
def now_iso():
    return datetime.now(timezone.utc).isoformat()


class OnboardingProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str
    industry: str
    company_size: str  # e.g. "11-50", "51-200", etc.
    annual_revenue: Optional[str] = None
    icp_description: str  # ideal customer profile
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
    profile_id: str
    company_name: str
    industry: str
    headquarters: str
    employee_count: str
    estimated_revenue: str
    intent_signal: str
    signal_strength: int  # 0-100
    decision_maker_name: str
    decision_maker_title: str
    estimated_deal_size: str
    recommended_play: str
    fit_score: int  # 0-100
    created_at: str = Field(default_factory=now_iso)


class Deal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company: str
    contact: str
    value: float
    stage: Literal["prospecting", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]
    probability: int
    agent_status: Literal["idle", "scanning", "thinking", "closing"]
    last_action: str
    updated_at: str = Field(default_factory=now_iso)


class DealCreate(BaseModel):
    company: str
    contact: str
    value: float
    stage: str = "prospecting"
    probability: int = 20


class DealUpdate(BaseModel):
    stage: Optional[str] = None
    agent_status: Optional[str] = None
    last_action: Optional[str] = None


class Signal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company: str
    domain: str
    signal_type: str  # "hiring", "funding", "tech_change", "expansion", "social"
    description: str
    strength: int  # 0-100
    source: str
    detected_at: str = Field(default_factory=now_iso)


class Activity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent: str
    action: str
    target: str
    outcome: Optional[str] = None
    status: Literal["scanning", "thinking", "closing", "idle"]
    timestamp: str = Field(default_factory=now_iso)


# ============== ROUTES ==============
@api_router.get("/")
async def root():
    return {"app": "Nexus AI", "status": "operational"}


# ---------- Onboarding ----------
@api_router.post("/onboarding", response_model=OnboardingProfile)
async def create_onboarding(payload: OnboardingCreate):
    profile = OnboardingProfile(**payload.model_dump())
    doc = profile.model_dump()
    await db.profiles.insert_one(dict(doc))
    return profile


@api_router.get("/onboarding/latest", response_model=Optional[OnboardingProfile])
async def latest_onboarding():
    doc = await db.profiles.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    if not doc:
        return None
    return OnboardingProfile(**doc)


@api_router.get("/onboarding/{profile_id}", response_model=OnboardingProfile)
async def get_onboarding(profile_id: str):
    doc = await db.profiles.find_one({"id": profile_id}, {"_id": 0})
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
async def generate_targets(body: dict):
    profile_id = body.get("profile_id")
    if not profile_id:
        raise HTTPException(400, "profile_id required")
    profile_doc = await db.profiles.find_one({"id": profile_id}, {"_id": 0})
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

        # Try to extract JSON
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

    # Persist
    targets: List[Target] = []
    # Clear previous targets for this profile so the user sees fresh ones
    await db.targets.delete_many({"profile_id": profile_id})
    for raw in raw_targets[:10]:
        try:
            t = Target(
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
async def list_targets(profile_id: Optional[str] = None):
    query = {"profile_id": profile_id} if profile_id else {}
    docs = await db.targets.find(query, {"_id": 0}).sort("fit_score", -1).to_list(50)
    return {"targets": docs}


# ---------- Dashboard ----------
@api_router.get("/dashboard/metrics")
async def dashboard_metrics():
    # Pull live counts where possible; derive realistic deltas
    deal_count = await db.deals.count_documents({})
    targets_count = await db.targets.count_documents({})
    activities = await db.activities.count_documents({})

    won = await db.deals.find({"stage": "closed_won"}, {"_id": 0, "value": 1}).to_list(500)
    won_value = sum(d.get("value", 0) for d in won)

    pipeline_open = await db.deals.find(
        {"stage": {"$in": ["prospecting", "qualified", "proposal", "negotiation"]}},
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
async def dashboard_activity(limit: int = 25):
    docs = await db.activities.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return {"activities": docs}


# ---------- Lead Engine ----------
@api_router.get("/leads/signals")
async def list_signals(limit: int = 40):
    docs = await db.signals.find({}, {"_id": 0}).sort("detected_at", -1).to_list(limit)
    return {"signals": docs}


@api_router.post("/leads/scan")
async def trigger_scan():
    """Simulate a fresh scan: log an activity and emit 3-5 new signals."""
    new_signals = []
    sample_pool = SAMPLE_SIGNALS.copy()
    random.shuffle(sample_pool)
    for raw in sample_pool[:random.randint(3, 5)]:
        s = Signal(**raw)
        await db.signals.insert_one(dict(s.model_dump()))
        new_signals.append(s.model_dump())

    act = Activity(
        agent="LeadScout-7",
        action="Web scan completed across 12,400 sources",
        target=f"{len(new_signals)} new high-intent signals captured",
        status="scanning",
    )
    await db.activities.insert_one(dict(act.model_dump()))
    return {"scanned": True, "new_signals": new_signals}


# ---------- Pipeline ----------
@api_router.get("/pipeline/deals")
async def list_deals():
    docs = await db.deals.find({}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return {"deals": docs}


@api_router.post("/pipeline/deals", response_model=Deal)
async def create_deal(payload: DealCreate):
    deal = Deal(
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
async def update_deal(deal_id: str, payload: DealUpdate):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = now_iso()
    res = await db.deals.update_one({"id": deal_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Deal not found")
    doc = await db.deals.find_one({"id": deal_id}, {"_id": 0})
    return Deal(**doc)


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


@app.on_event("startup")
async def seed():
    # Seed only if empty
    if await db.deals.count_documents({}) == 0:
        for d in SAMPLE_DEALS:
            deal = Deal(**d)
            await db.deals.insert_one(dict(deal.model_dump()))
    if await db.signals.count_documents({}) == 0:
        base = datetime.now(timezone.utc)
        for i, s in enumerate(SAMPLE_SIGNALS):
            sig = Signal(**s)
            sig_doc = sig.model_dump()
            # Stagger detected_at so the feed looks live
            sig_doc["detected_at"] = (base - timedelta(minutes=i * 7)).isoformat()
            await db.signals.insert_one(sig_doc)
    if await db.activities.count_documents({}) == 0:
        base = datetime.now(timezone.utc)
        for i, a in enumerate(SAMPLE_ACTIVITIES):
            act = Activity(**a)
            act_doc = act.model_dump()
            act_doc["timestamp"] = (base - timedelta(minutes=i * 3)).isoformat()
            await db.activities.insert_one(act_doc)


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
