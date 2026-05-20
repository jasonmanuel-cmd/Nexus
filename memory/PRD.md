# Nexus AI — Autonomous CRO · PRD

## Original Problem Statement
Build 'Nexus AI' — the first autonomous AI Chief Revenue Officer for mid-market companies. 5 core features: Landing, Command Center Dashboard, Autonomous Lead Engine, Pipeline Automation, Beta Onboarding with AI-generated targets. Goal: $1M/month-feel prototype.

## Architecture
- **Frontend**: React 19 + React Router 7 + Tailwind + Framer Motion + Recharts
- **Backend**: FastAPI (lifespan) + Motor + emergentintegrations + squareup
- **AI**: Claude Sonnet 4.5 via Emergent Universal LLM Key
- **Payments**: Square Sandbox QuickPay
- **Auth**: Emergent-managed Google Auth (cookie + Bearer)
- **Notifications**: Resend + Slack — MOCKED until env keys set
- **DB collections**: users, user_sessions, profiles, targets, deals, signals, activities, payment_transactions, email_outbox, slack_outbox, **email_replies, reply_drafts**

## Versions Shipped
| v | Iter | Feature delta | Result |
|---|---|---|---|
| 1.0 | 1 | Landing + Dashboard + Lead Engine + Pipeline + Onboarding + Claude target gen + MongoDB | 15/15 PASS |
| 2.0 | 2-3 | Google Auth + multi-tenant + Recharts + DnD kanban + Promote-target + Stripe | 14/14 PASS |
| 3.0 | 4 | Square (replaces Stripe) + Resend/Slack MOCKED stubs + Outbox page + FastAPI lifespan + integrations/ module | 29/29 PASS |
| 4.0 | 5 | **Autonomous Reply Loop** — Claude buyer-reply simulation + AI-drafted contextual follow-up + human-in-the-loop Replies Queue + send/edit/dismiss + auto deal-probability adjustment | **10/10 PASS** |

## v4.0 Details (Feb 20, 2026 — Iteration 5)
- `POST /api/notifications/email/{id}/simulate-reply` → Claude generates a realistic buyer reply (varied sentiment) + a contextual follow-up draft in a single LLM call
- `GET /api/replies/queue` — enriched pending drafts (joins reply + original outreach + deal)
- `POST /api/replies/{id}/send` — send as-is or with edits; bumps deal probability by `probability_delta` (clamped 0-100); sets `agent_status=closing` on positive sentiment; logs activity + sends queued follow-up to email_outbox
- `DELETE /api/replies/{id}` — dismiss
- `GET /api/replies/stats` — counters
- New page `/app/replies` — two-column conversation view (your outreach + buyer reply on left, AI draft on right) with Edit/Send-as-is/Dismiss
- Outbox `Simulate buyer reply` button on every `promote.intro` / `reply.followup` email

## Personas
- Mid-market CRO / VP Sales (primary buyer)
- RevOps Lead (champion / operator)
- Founder of $5M–$100M ARR company

## Prioritized Backlog
### P1
- **Flip Resend live** (drop API key + verified sender in `.env`, uncomment POST in `integrations/notifications.py`)
- **Flip Slack live** (drop webhook URL, uncomment POST)
- Real Square Subscriptions (Subscriptions API + card-on-file) — currently QuickPay first-month only

### P2
- Split `server.py` (1170 lines) into routers (auth / payments / dashboard / leads / pipeline / onboarding / targets / notifications / replies)
- Stripe Customer Portal equivalent (manage card, view invoices)
- Recharts Sankey for pipeline flow
- Mobile-optimized kanban
- Multi-card-select drag-drop

### P3
- Custom agent configuration UI
- Audit log of agent decisions
- Light theme toggle
- Internationalization
- Outbox: filter by kind, search, mark-as-read

## Next Tasks
1. Flip Resend live (5 min)
2. Flip Slack live (5 min)
3. Real Square recurring Subscriptions
4. Router split of server.py
5. Recharts Sankey pipeline visualization
