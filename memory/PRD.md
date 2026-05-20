# Nexus AI — Autonomous CRO · PRD

## Original Problem Statement
Build 'Nexus AI' — the first autonomous AI Chief Revenue Officer for mid-market companies.

Core features:
1. Premium Landing Page — High-converting, enterprise-grade dark-mode bento grid.
2. Dashboard — Live 'Command Center' visualizing AI-driven revenue activities.
3. Autonomous Lead Engine — Simulates web-scanning for high-intent signals.
4. Pipeline Automation — Visual kanban of AI-managed deals across stages.
5. 'Beta' Interactive Onboarding — User onboards their company → AI generates first 10 high-value targets.

Goal: prototype that feels like a $1M/month product. 2026 design trends (glassmorphism, micro-interactions, AI-agent status indicators).

## Architecture
- **Frontend**: React 19 + React Router 7 + Tailwind + Framer Motion + custom glass/bento panels
- **Backend**: FastAPI + Motor (async Mongo)
- **DB**: MongoDB (collections: profiles, targets, deals, signals, activities)
- **AI**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) via emergentintegrations + Emergent Universal LLM Key
- **Theme**: Obsidian black (#050505) + Electric Teal (#00F5D4) + Signal Orange (#FF5500), Instrument Serif + Geist Mono, dark-only, glassmorphic panels, noise overlay, scanning beams

## Personas
- Mid-market CRO / VP Sales (primary buyer)
- RevOps Lead (champion / operator)
- Founder of $5M–$100M ARR company (decision maker)

## What's Been Implemented — v1.0 (Feb 20, 2026)
- **Landing**: Fixed glass nav · Bento hero (headline + live agent feed + 4 stat tiles) · Sponsor marquee · Feature bento (4 asymmetric panels) · 7-agent fleet · Pricing (Operator / Scale-featured / Enterprise) · Final CTA · Footer
- **App shell**: Sidebar nav, agents-online indicator, back-to-site
- **Dashboard (Command Center)**: 6 animated number-ticker metrics, live agent activity feed (auto-refresh 8s), agent fleet load bars, Q1 forecast panel
- **Lead Engine**: Scan-status panel with progress + beam, total-signals tile, signal table with strength bars, "Trigger live scan" adds 3-5 new signals
- **Pipeline**: 5-column kanban, advance/regress via chevron, closing deals get pulsing cyan border + scan beam
- **Beta Onboarding**: 4-step wizard → terminal-style AI processing stream → 10 target cards from real Claude Sonnet 4.5 with fit score, decision maker, intent signal, recommended play
- **Persistence**: All profiles, targets, deals, signals, activities persisted in MongoDB; auto-seed on first startup
- **All interactive elements** have `data-testid` attributes

## Testing — Iteration 1 (PASS)
- Backend: 15/15 pytest passing (incl. real Claude Sonnet 4.5 generation)
- Frontend: All critical flows verified by testing agent (no console errors, no _id leaks)

## Prioritized Backlog
### P1
- Promote a target → pipeline deal (one-click)
- Persist scan-engine signals tied to a profile
- Multi-tenant scoping when auth is added
### P2
- Drag-and-drop kanban (currently chevron-based)
- Recharts revenue waterfall + agent productivity on dashboard
- Stripe billing for self-serve tier
- Email/calendar integration mocks
### P3
- Custom agent configuration UI
- Slack / Webhook outbound integration
- Optional light theme toggle

## Next Tasks
1. "Promote to pipeline" button on target card
2. Stripe self-serve subscription on onboarding
3. Recharts revenue waterfall on dashboard
