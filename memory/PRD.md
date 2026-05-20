# Nexus AI — Autonomous CRO · PRD

## Original Problem Statement
Build 'Nexus AI' — first autonomous AI Chief Revenue Officer for mid-market companies.

## Architecture
- **Frontend**: React 19 + React Router 7 + Tailwind + Framer Motion + Recharts + Square Web Payments SDK
- **Backend**: FastAPI (lifespan) + Motor + emergentintegrations + squareup + resend + httpx
  - **Routers**: `routers/settings.py`, `routers/payments.py` (extracted) · core CRUD still in `server.py`
  - **deps.py**: shared db / User / get_current_user / Activity / lifespan
  - **integrations/**: `square_client.py`, `square_errors.py`, `notifications.py`
- **AI**: Claude Sonnet 4.5 (Emergent Universal LLM Key)
- **Payments**: Square Sandbox **recurring Subscriptions** via Web Payments SDK card tokenization
- **Auth**: Emergent Google Auth (cookie + Bearer)
- **Notifications**: Resend LIVE + Slack LIVE
- **DB**: users, user_sessions, profiles, targets, deals, signals, activities, payment_transactions, email_outbox, slack_outbox, email_replies, reply_drafts

## Version Timeline
| v | Iter | Delta | Tests |
|---|---|---|---|
| 1.0 | 1 | Landing + Dashboard + Lead Engine + Pipeline + Onboarding + Claude target gen | 15/15 |
| 2.0 | 2-3 | Auth + multi-tenant + Recharts + DnD + Promote-target + Stripe | 14/14 |
| 3.0 | 4 | Square (replaces Stripe) + MOCKED Resend/Slack + Outbox + lifespan | 29/29 |
| 4.0 | 5 | Autonomous Reply Loop (Claude buyer-reply + drafted follow-up + Queue) | 10/10 |
| 5.0 | 6 | Confidence-slider auto-send + LIVE Resend + LIVE Slack + real recurring Square subs (Web SDK) + partial router split | 14/14 |
| **6.0** | **7** | **Per-deal autonomy cap + sanitized Square errors + finished payments+settings router split** | **16/16** |

## v6.0 Details (Feb 20, 2026 — Iteration 7)
- **Per-deal autonomy cap** — `auto_send_deal_value_cap` (default $50K). Drafts for deals above the cap stay manual regardless of confidence. Slider in `/app/settings` ($0 → $500K, step $5K) with `$50K`/`$100K`/`$1M` formatting.
- **Sanitized Square errors** — `integrations/square_errors.py` maps 12 Square error codes to user-friendly strings. Endpoints (`/payments/subscribe`, `/payments/checkout/session`) now return safe messages instead of raw SDK exception text. Verified: bad card token → `"Card details are invalid."` (no traceback, no `squareup` / `api_error` leaks).
- **Router split** — `routers/settings.py` + `routers/payments.py` extracted. `server.py` 1341 → 1029 lines. All endpoints behavior-identical; clean APIRouter mounts at bottom of `server.py`. `deps.py` centralizes db/User/get_current_user/Activity. Zero circular imports.

## Personas
- Mid-market CRO / VP Sales (buyer)
- RevOps Lead (champion)
- Founder $5M–$100M ARR (decision maker)

## Operational Notes
- `RESEND_FROM_EMAIL=nexus@coaibakersfield.com` — domain unverified by user → emails currently `status:failed` (LIVE path, not MOCKED). Verify DNS at https://resend.com/domains to flip to delivered.
- Square `SQUARE_OPERATOR_PLAN_VARIATION_ID=gExEqBXlbrGl5zlMM01fQQ`, `SQUARE_SCALE_PLAN_VARIATION_ID=-u9ZoOWQan3VLZeToy0mzg` — may be catalog item IDs not subscription plan variation IDs; user to confirm in Square Dashboard.
- Sandbox test card: `4111 1111 1111 1111` · any future date · any CVC · ZIP 94103.

## Prioritized Backlog
### P1
- User: verify `coaibakersfield.com` DNS on Resend
- User: confirm Square subscription plan variation IDs
- Extract remaining routers: replies, notifications, dashboard, leads, pipeline, onboarding, targets, auth

### P2
- Square Customer Portal equivalent (manage card, view invoices)
- Recharts Sankey for pipeline flow
- Mobile-optimized kanban + multi-card select drag-drop
- Resend inbound webhook (real buyer replies parse + draft instead of simulate)

### P3
- Custom agent config UI
- Audit log of agent decisions
- Light theme toggle
- Outbox filters + search
- Wrap `square_errors.py` `or/and` expression in explicit parens (lint nit)

## Next Tasks
1. User-side: Resend DNS verification + Square plan ID confirmation
2. Finish router extraction (replies/notifications/dashboard/leads/pipeline/onboarding/targets/auth)
3. Square Customer Portal
4. Real Resend inbound webhook for buyer replies
5. Recharts Sankey pipeline flow
