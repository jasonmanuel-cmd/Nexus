# Nexus AI — Autonomous Chief Revenue Officer

## Original Problem Statement
Build 'Nexus AI' — the first autonomous AI Chief Revenue Officer for mid-market companies.
Core features: Premium Landing Page, live Command Center Dashboard, Autonomous Lead Engine (web-scanning sim), Pipeline Automation (kanban), Beta Interactive Onboarding (AI generates 10 high-value targets). Looks/feels like a $1M/month enterprise product. 2026 design trends (glassmorphism, micro-interactions, AI-agent status indicators).

## Locked-In Choices
- LLM: **Claude Sonnet 4.5** (`claude-sonnet-4-5-20250929`) via Emergent Universal LLM Key + `emergentintegrations` library
- Theme: **Deep obsidian black** + **electric cyan/teal** + secondary amber/orange accents
- Auth: **None** (open prototype)
- Persistence: **MongoDB** (motor async driver)
- Fonts: **Instrument Serif** (headings) + **Geist Mono** (body / dashboard)

## Architecture
- **Backend**: FastAPI on `:8001`, all routes prefixed `/api`. MongoDB via `MONGO_URL`. Seeds 12 signals, 11 deals, 12 activities at startup if empty.
- **Frontend**: React 19 + React Router 7 + Tailwind + Framer Motion + shadcn/ui primitives.
- Routes: `/` landing, `/app/dashboard`, `/app/lead-engine`, `/app/pipeline`, `/app/onboarding`.

## User Personas
1. **CRO at $50M ARR SaaS** — wants pipeline visibility + autonomous outreach to replace 6-12 SDRs.
2. **CEO at Series B startup** — needs revenue compounding without scaling headcount.
3. **VP RevOps** — wants signal-based ICP refinement.

## Core Requirements (Static)
- Premium dark landing with bento hero, social proof marquee, feature grid, 7-agent panel, 3-tier pricing, final CTA.
- Live Command Center with animated tickers, agent fleet load bars, real-time activity feed (8s poll).
- Lead Engine table with intent signals, signal-strength bars, "Trigger live scan" CTA.
- Pipeline kanban with 5 stages, AI-status-tagged cards, chevron-based stage progression.
- 4-step onboarding wizard → LLM call → terminal-style processing → 10 target cards.

## What's Implemented (May 20, 2026)
- ✅ Landing page with all sections
- ✅ App shell with persistent sidebar
- ✅ Command Center dashboard (live metrics, agent fleet, activity feed)
- ✅ Autonomous Lead Engine (signals table, scan trigger, scanning beam)
- ✅ Pipeline Kanban (drag-less via chevrons; PATCH to backend)
- ✅ Beta Onboarding wizard + real Claude Sonnet 4.5 target generation
- ✅ MongoDB persistence for profiles, targets, deals, signals, activities
- ✅ Seed data on startup
- ✅ Backend tests: **15/15 passing** (includes 32s real LLM E2E test)

## API Surface
- `GET /api/` health
- `GET /api/dashboard/metrics`, `GET /api/dashboard/activity`
- `GET /api/leads/signals`, `POST /api/leads/scan`
- `GET/POST/PATCH /api/pipeline/deals`
- `POST /api/onboarding`, `GET /api/onboarding/latest`, `GET /api/onboarding/{id}`
- `POST /api/targets/generate`, `GET /api/targets`

## Prioritized Backlog
**P0** — None outstanding.
**P1** — Add Stripe billing for paid tiers; export targets as CSV.
**P2** — Real-time WebSocket activity stream; drag-and-drop pipeline; email-send integration (Resend/SendGrid); CRM connectors (HubSpot/Salesforce); team multi-user.
**P3** — Voice agent for call summaries; Slack notifications; forecast accuracy backtest.

## Next Tasks
- User review of MVP
- Optional: real outbound (Resend), Stripe pricing tier checkout, target export
