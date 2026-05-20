# Nexus AI — Autonomous CRO · PRD

## Original Problem Statement
Build 'Nexus AI' — the first autonomous AI Chief Revenue Officer for mid-market companies.

Core features: 1) Premium Landing Page, 2) Command Center Dashboard, 3) Autonomous Lead Engine, 4) Pipeline Automation, 5) Beta Interactive Onboarding generating 10 high-value targets. Goal: prototype that feels like a $1M/month product.

## Architecture
- **Frontend**: React 19 + React Router 7 + Tailwind + Framer Motion + Recharts
- **Backend**: FastAPI (lifespan handler) + Motor (async Mongo) + emergentintegrations (LLM + Auth) + squareup (Square SDK wrapped with asyncio.to_thread)
- **AI**: Claude Sonnet 4.5 via Emergent Universal LLM Key
- **Payments**: **Square Sandbox** Checkout (QuickPay payment links) — replaced Stripe
- **Auth**: Emergent-managed Google Auth (cookie + Bearer fallback)
- **Notifications**: Resend (email) + Slack (webhook) — both **MOCKED** behind stubs; persisted to `email_outbox` / `slack_outbox` collections with `mocked:true` until env keys are set
- **DB**: MongoDB collections: `users`, `user_sessions`, `profiles`, `targets`, `deals`, `signals`, `activities`, `payment_transactions`, `email_outbox`, `slack_outbox`

## What's Been Implemented

### v1.0 — Iteration 1
Landing + Dashboard + Lead Engine + Pipeline + Onboarding + Claude Sonnet 4.5 target generation + MongoDB seed.

### v2.0 — Iterations 2-3
Emergent Google Auth + multi-tenant scoping + Recharts (waterfall + productivity) + HTML5 drag-drop kanban + Promote-target-to-deal + Stripe self-serve checkout.

### v3.0 — Iteration 4
- **Square Sandbox replaces Stripe** — `/api/payments/checkout/session` creates Square QuickPay link; `/api/payments/checkout/status/{id}` polls Square order; `/api/webhook/square` validates HMAC-SHA256 signature; `/api/payments/subscription` returns state; `/api/payments/subscription/cancel` flips active flag + logs to Slack
- **Resend email automation (MOCKED stub)** — fires automatically on target-promote and on deal-won; persisted to `email_outbox` with full body
- **Slack notifications (MOCKED stub)** — fires on target-promote, every pipeline stage change, subscription activate/cancel; persisted to `slack_outbox`
- **Agent Outbox page** (`/app/outbox`) — inspect every email + Slack the agents have sent; tabs, counts, MOCKED/LIVE badges
- **FastAPI lifespan handler** replaces deprecated `@on_event`
- **integrations/** module — `square_client.py` + `notifications.py` cleanly separated from `server.py`

## Testing
| Iteration | Backend | Frontend | Status |
|---|---|---|---|
| 1 | 15/15 | 100% | PASS |
| 2 | 13/14 (2 HIGH fixed) | 100% | PASS |
| 3 | 14/14 | 100% | PASS |
| 4 | **29/29** (15 v3 + 14 v2 regression) | **100%** | **PASS** |

## Prioritized Backlog
### P1
- True Square Subscriptions (Subscriptions API + card-on-file flow) — currently QuickPay = first-month one-time
- Resend live integration: drop in RESEND_API_KEY and uncomment the live POST in `notifications.py`
- Slack live integration: drop in SLACK_WEBHOOK_URL and uncomment the httpx POST in `notifications.py`
- Stripe Customer Portal equivalent for Square (manage card on file, view invoices)

### P2
- Split `server.py` (908 lines) into routers (auth/payments/dashboard/leads/pipeline/onboarding/targets/notifications)
- Resend domain verification + reply-tracking
- Recharts: Sankey diagram for pipeline flow
- Mobile-optimized kanban
- Outbox: filter by kind, search, mark-as-read

### P3
- Custom agent configuration UI
- Audit log of agent decisions
- Light theme toggle
- Internationalization

## Next Tasks
1. Flip Resend live (drop API key + sender)
2. Flip Slack live (drop webhook URL)
3. Implement real Square Subscriptions (recurring) using Subscriptions API
4. Split `server.py` into routers
5. Recharts Sankey for pipeline flow
