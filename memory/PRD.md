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
- **Frontend**: React 19 + React Router 7 + Tailwind + Framer Motion + Recharts
- **Backend**: FastAPI + Motor (async Mongo) + emergentintegrations (LLM + Stripe + Auth)
- **DB**: MongoDB collections: `users`, `user_sessions`, `profiles`, `targets`, `deals`, `signals`, `activities`, `payment_transactions`
- **AI**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) via Emergent Universal LLM Key
- **Payments**: Stripe Checkout via `emergentintegrations.payments.stripe` (test key in env)
- **Auth**: Emergent-managed Google Auth (`auth.emergentagent.com`) — cookie-based sessions, 7-day expiry, Bearer fallback
- **Theme**: Obsidian black (#050505) + Electric Teal (#00F5D4) + Signal Orange (#FF5500), Instrument Serif + Geist Mono

## Personas
- Mid-market CRO / VP Sales (primary buyer)
- RevOps Lead (champion / operator)
- Founder of $5M–$100M ARR company (decision maker)

## What's Been Implemented

### v1.0 (Feb 20, 2026) — Iteration 1
- Landing page (bento hero, sponsor marquee, features, agents, pricing, footer)
- App shell + sidebar nav
- Command Center dashboard (6 ticker metrics, agent activity feed, agent fleet, Q1 forecast)
- Lead Engine with scan simulation + signal table
- Pipeline kanban (5 stages, chevron-advance)
- Beta Onboarding wizard with Claude Sonnet 4.5 generating 10 high-value targets
- MongoDB persistence + auto-seed

### v2.0 (Feb 20, 2026) — Iteration 2 + 3
- **Emergent Google Auth** with multi-tenant scoping — all collections scoped by `user_id`; protected `/app/*` routes; demo data auto-seeds per-user on first `/auth/me` hit
- **Stripe self-serve subscriptions** — Operator $4,800/mo + Scale $18,500/mo, Stripe Checkout via emergentintegrations, polling-based status confirmation, webhook endpoint, `payment_transactions` collection
- **Recharts on Dashboard** — revenue waterfall (Bar) + agent productivity (Area) with custom dark tooltips
- **HTML5 drag-and-drop kanban** on Pipeline (with optimistic UI + PATCH backend sync)
- **Promote target → pipeline deal** — one-click promotion from Beta Onboarding target card; deal auto-created in Prospecting stage with parsed deal size, activity log
- New pages: `/login`, `/auth/callback`, `/app/subscribe`, `/app/checkout-return`
- AuthContext + ProtectedRoute components
- All interactive elements still have `data-testid`

## Testing
- **Iteration 1**: 15/15 backend pytest passing
- **Iteration 2**: 13/14 (2 HIGH bugs found)
- **Iteration 3** (post-fix): **14/14 backend + 100% frontend flows passing**

## Prioritized Backlog
### P1
- Drag-and-drop with multi-card selection
- Email outreach via Resend integration
- Slack notifications on deal stage change
### P2
- Custom agent configuration UI
- Recharts forecast chart + Sankey diagram
- Stripe customer portal (manage subscription)
- Convert checkout to actual recurring subscription mode (currently one-time)
### P3
- Light theme toggle
- Mobile-optimized kanban
- Audit log of agent decisions
- Split server.py into routers; migrate to FastAPI lifespan

## Next Tasks
1. Resend / SendGrid email automation for sequenced outreach
2. Customer portal for billing self-service
3. Convert Stripe one-time → recurring subscription
4. Slack webhook on stage advance
