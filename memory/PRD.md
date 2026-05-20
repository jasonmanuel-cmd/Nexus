# Nexus AI — Autonomous CRO · PRD

## Original Problem Statement
Build 'Nexus AI' — first autonomous AI Chief Revenue Officer for mid-market companies. 5 core features: Landing, Command Center Dashboard, Autonomous Lead Engine, Pipeline Automation, Beta Onboarding with AI-generated targets. Goal: $1M/month-feel prototype.

## Architecture
- **Frontend**: React 19 + React Router 7 + Tailwind + Framer Motion + Recharts + Square Web Payments SDK
- **Backend**: FastAPI (lifespan, partial router split) + Motor + emergentintegrations + squareup + resend + httpx
- **AI**: Claude Sonnet 4.5 via Emergent Universal LLM Key
- **Payments**: **Square Sandbox recurring Subscriptions** (real Subscriptions API + card-on-file via Web Payments SDK tokenization)
- **Auth**: Emergent-managed Google Auth (cookie + Bearer)
- **Notifications**: **Resend LIVE** + **Slack LIVE** (Resend currently `status:failed` until user verifies coaibakersfield.com DNS)
- **DB**: users, user_sessions, profiles, targets, deals, signals, activities, payment_transactions, email_outbox, slack_outbox, email_replies, reply_drafts

## Version Map
| v | Iter | Delta | Tests |
|---|---|---|---|
| 1.0 | 1 | Landing + Dashboard + Lead Engine + Pipeline + Onboarding + Claude target gen | 15/15 |
| 2.0 | 2-3 | Auth + multi-tenant + Recharts + DnD kanban + Promote-target + Stripe | 14/14 |
| 3.0 | 4 | Square (replaced Stripe) + MOCKED Resend/Slack + Outbox + lifespan + integrations/ module | 29/29 |
| 4.0 | 5 | Autonomous Reply Loop (Claude buyer-reply + AI-drafted follow-up + Replies Queue) | 10/10 |
| **5.0** | **6** | **Confidence-slider auto-send + LIVE Resend + LIVE Slack + real recurring Square subscriptions (Web Payments SDK) + partial router split** | **14/14 (+1 env-skipped)** |

## v5.0 Details (Feb 20, 2026 — Iteration 6)
- **`/api/settings`** GET/PUT — `auto_send_enabled` + `auto_send_threshold` (50-100, clamped)
- **Auto-send loop** in `simulate_reply`: when `auto_send_enabled` + `sentiment=positive` + `probability_delta ≥ 15` + `confidence ≥ threshold` → draft.status flips to `auto_sent`, follow-up queues immediately, deal probability bumps, `agent_status=closing`, Slack pings "Auto-sent follow-up"
- **`/api/payments/config`** public — exposes Square `application_id` + `location_id` + `environment` for browser SDK
- **`/api/payments/subscribe`** — full path: upsert Square Customer → create Card from Web Payments SDK nonce → create real Square Subscription → mark `subscription_active` + store `square_customer_id` + `square_card_id` + `subscription_id` + `renews_at`
- **`/api/payments/subscription/cancel`** — calls Square `Subscriptions.cancel`, fail-soft if Square errors
- **LIVE Resend** — `integrations/notifications.py` uses Resend SDK when `RESEND_API_KEY` set; writes provider/status/error to `email_outbox`
- **LIVE Slack** — httpx POST to `SLACK_WEBHOOK_URL`; confirmed delivering to user's workspace
- **New `/app/settings`** page — slider + toggle + live counters (auto-sent / manual approvals / awaiting you)
- **Square card modal** — Web Payments SDK loaded from `sandbox.web.squarecdn.com`; `initRef` guard prevents React 18 StrictMode double-mount
- **Partial router split** — `deps.py` (shared db/User/get_current_user/Activity) + `routers/settings.py` extracted; remaining routers staged for next iter

## Personas
- Mid-market CRO / VP Sales (buyer)
- RevOps Lead (champion)
- Founder $5M–$100M ARR (decision maker)

## Known Configurations / Operational Notes
- `RESEND_FROM_EMAIL=nexus@coaibakersfield.com` — user must verify domain DNS at https://resend.com/domains for emails to actually deliver (currently `status:failed` correctly)
- Square test card for sandbox: `4111 1111 1111 1111` · any future date · any CVC · ZIP 94103
- Square `OPERATOR_PLAN_VARIATION_ID=gExEqBXlbrGl5zlMM01fQQ` and `SCALE_PLAN_VARIATION_ID=-u9ZoOWQan3VLZeToy0mzg` — if these are not actual `SUBSCRIPTION_PLAN_VARIATION` catalog objects, subscribe may 502 (user to confirm in Square Dashboard → Subscriptions)

## Prioritized Backlog
### P1
- Verify Resend domain on resend.com (5 min, user-side)
- Confirm Square subscription plan variation IDs (user to confirm in Dashboard)
- Sanitize Square error text leaking to client in `/payments/subscribe` 502 path

### P2
- Finish router split — extract `payments.py`, `notifications.py`, `replies.py`, `onboarding.py`, `dashboard.py`, `pipeline.py`, `leads.py`, `auth.py`
- Square Customer Portal equivalent (manage card, view invoices)
- Recharts Sankey pipeline visualization
- Mobile-optimized kanban + multi-card select
- Add `data-testid="settings-saved-badge"` for deterministic save assertions

### P3
- Custom agent config UI
- Audit log of agent decisions
- Light theme toggle
- I18n
- Outbox filters/search

## Next Tasks
1. User: verify `coaibakersfield.com` DNS on Resend
2. User: confirm Square subscription plan variation IDs
3. Finish router split (payments, replies, notifications first)
4. Sanitize Square error responses
5. Recharts Sankey for pipeline flow
