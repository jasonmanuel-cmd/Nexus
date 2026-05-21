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
| 6.0 | 7 | Per-deal autonomy cap + sanitized Square errors + finished payments+settings router split | 16/16 |
| 7.0 | 8 | Deployer Code-Quality Fixes (P0+P1): undefined vars · empty catches · hook deps · stable React keys · `secrets.SystemRandom` · env-driven test config | 26/26 |
| **8.0** | **9** | **OUT OF MOCK MODE: Tavily real lead signals · Gmail OAuth + inbox poller · live landing hero stats · waitlist + affiliate (20% rev share) · 7-day trial gating · Square sandbox → PRODUCTION** | **26/26** |

## v8.0 Details (Feb 21, 2026 — Iteration 9) — REAL MONEY MODE
- **Tavily live web search** — `/api/leads/scan` now invokes `tavily.search(topic=news, time_range=month, search_depth=advanced, max_results=12)` filtered by user's onboarding ICP, then pipes condensed results to Claude Sonnet 4.5 for structured signal extraction. Response includes `live: bool`. Falls back to SAMPLE_SIGNALS if profile missing or Tavily fails. `integrations/tavily_client.py`.
- **Gmail OAuth inbox poller** — `routers/gmail.py` exposes `/connect`, `/callback` (public), `/status`, `/disconnect`, `/poll`, `/send`. Poll fetches `is:unread newer_than:7d in:inbox`, matches via `threadId` → existing outbound email, generates Claude follow-up draft into `reply_drafts`, marks Gmail message as read. Scopes: `gmail.readonly + gmail.modify + gmail.send + openid + userinfo.email`. Token auto-refresh built in.
- **Live landing hero stats** — `/api/landing/hero-stats` aggregates real pipeline_value, active_deals, targets_identified, signals_detected_30d, paying_customers. Public endpoint, no auth.
- **Waitlist** — `/api/landing/waitlist` POST + `/count` GET. Email-deduped, captures referrer (affiliate code), tracks position. UI form on Landing with success state.
- **Affiliate program** — `/api/landing/affiliate/signup` generates unique slug from name/email; `/{code}` lookup is privacy-safe (no `owner_email` leak via Mongo projection). 20% lifetime rev share configured. UI on Landing.
- **7-day trial gate** — `routers/billing.py` exposes `/api/billing/trial-status`; trial = 7 days from `users.created_at`. After expiry + no subscription → `/api/leads/scan` and `/api/notifications/email/{id}/simulate-reply` return HTTP 402 with `{detail.error: "trial_expired", upgrade_url: "/app/subscribe"}`. Gate runs BEFORE LLM/Tavily calls. AppShell shows top banner with countdown + upgrade CTA.
- **Square sandbox → production** — `SQUARE_ENVIRONMENT=production`, fresh production `SQUARE_ACCESS_TOKEN`, `SQUARE_APPLICATION_ID=sq0idp-1CJTgQMcbAUiQw2qPVq7Xw`, `SQUARE_LOCATION_ID=L8W4Z600ATSXF` (auto-fetched from `/v2/locations`), plan variation IDs `Operator=P6foteJBLdWOH4mfQyKfyA` / `Scale=GR3cpbJ4c1KybmF1TRFocg`. Checkout creates real payment links — **real cards charged**.
- **Real-email outreach loop (NEW Feb 21)** — `Target` model gained optional `decision_maker_email`. New `PATCH /api/targets/{id}` lets user paste the verified email after LinkedIn lookup. Promote-target flow: if `decision_maker_email` set AND Gmail connected → sends via Gmail (stores `gmail_thread_id` for poll-back matching) ELSE Resend (status:failed until DNS verified). Response includes `sent_via: "gmail"|"resend"` + `sent_to`. UI: inline email input on every target card in `/app/onboarding`.

## How Nexus AI Makes Money (Production-Live)
- **Operator** $4,800/mo · **Scale** $18,500/mo · **Enterprise** custom (sales@nexus.ai)
- Revenue model: 10 Operators = $48K MRR · 3 Scale = $55.5K MRR · combined Y1 path to $1M ARR
- Affiliate engine wired (20% lifetime rev share) — partners can self-onboard from landing
- 7-day trial → forced upgrade on lock + banner CTA throughout app

## v7.0 Details (Feb 21, 2026 — Iteration 8)
- **server.py:405** — renamed list-comp loop var `t` → `tg` (removed shadow of outer for-loop var; lint clean).
- **routers/payments.py:50** — defensive `link = None` init + post-try guard `if not link: raise HTTPException(502, ...)`.
- **Empty catch blocks eliminated** — `AuthContext.jsx` (refresh + logout), `Subscribe.jsx` (Square card destroy), `Onboarding.jsx` (profile fetch), `CheckoutReturn.jsx` (sub check) now log non-401/404 errors via `console.error`.
- **Stable React keys** — `Landing.jsx` agent feed (`key={a.agent}`), bento stats (`key={s.label}`), sponsor marquee (`key={`${s}-${i}`}`), feature grid (`key={f.title}`); `Dashboard.jsx` ChartTooltip uses `p.dataKey || p.name`; `Onboarding.jsx` terminal uses composite key.
- **`random` → `secrets.SystemRandom()`** — module-level `_sysrand` in `server.py` (`/api/leads/scan`) cryptographically secure.
- **Env-driven tests** — `test_nexus_v2.py`, `v3`, `v4`, `v5`, `v6`, `test_nexus_backend.py` all now use `os.environ.get("REACT_APP_BACKEND_URL")` + `os.environ.get("DEMO_SESSION_TOKEN", "demo_session_token_persistent")`. No hardcoded preview URLs or session token literals.
- **Regression**: 26/26 tests pass in `test_nexus_v7_regression.py` — Auth · Dashboard · Leads (secrets) · Onboarding+Claude · Payments (link init) · Settings · Pipeline · Replies · Scoping.

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
- Refactor extreme function complexity in `server.py` (`simulate_reply` 144 lines, `generate_targets`)
- Refactor extreme component complexity in `Onboarding.jsx` (399 lines), `Outbox.jsx`, `Pipeline.jsx`, `Dashboard.jsx`

### P2
- Square Customer Portal equivalent (manage card, view invoices)
- Recharts Sankey for pipeline flow
- Mobile-optimized kanban + multi-card select drag-drop
- Resend inbound webhook (real buyer replies parse + draft instead of simulate)
- Update legacy `test_nexus_backend.py` session fixture to inject Bearer token (or retire — fully duplicated by v3..v7)
- Update `test_nexus_v3.py::test_promote_inserts_email_and_slack` to drop stale `mocked is True` assertion (Resend is real now)

### P3
- Custom agent config UI
- Audit log of agent decisions
- Light theme toggle
- Outbox filters + search
- Wrap `square_errors.py` `or/and` expression in explicit parens (lint nit)
- Strip `console.log/error` for production builds

## Next Tasks
1. User-side: Resend DNS verification + Square plan ID confirmation
2. Finish router extraction (replies/notifications/dashboard/leads/pipeline/onboarding/targets/auth)
3. Refactor `simulate_reply` and `Onboarding.jsx` into smaller pieces (P1 complexity)
4. Square Customer Portal
5. Real Resend inbound webhook for buyer replies
6. Recharts Sankey pipeline flow
