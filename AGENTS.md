# SchemePing: Project Context

> Read this file fully before writing any code. Every phase prompt assumes you have read this.
> Coding agents: Claude Code reads `CLAUDE.md` (a pointer to this file), Codex and others read `AGENTS.md`.

---

## 1. What we are building

**SchemePing** is a mobile-first web app (installable PWA) that helps Indian citizens discover, understand, and apply for government welfare schemes they are eligible for.

**Mission:** *Every citizen should know every benefit they are eligible for, without needing to understand complex government language or search across multiple websites.*

A user registers once, adds their family members, and SchemePing:
1. Matches the user and each family member against a verified database of schemes.
2. Explains each scheme in simple, citizen-friendly language, in 6 languages.
3. Tells them exactly which documents to bring and which office to visit.
4. Proactively messages them on WhatsApp when something new applies to them (new scheme, age milestone, festival benefit).

## 2. The core problem (why this exists)

Schemes exist, but people never benefit because of four gaps:

| Gap | Reality today |
|---|---|
| **Discovery** | Thousands of central and state schemes are spread across many websites. People do not know what to search for. |
| **Understanding** | Eligibility rules and notices are written in legal or bureaucratic language. |
| **Timing** | Deadlines and new schemes are missed because nobody tells the person in time. |
| **Last mile** | Even when eligible, people do not know which documents to bring or which office to visit. |

SchemePing's real job is **matching + translation + proactive nudging + last-mile guidance**.

## 3. Non-negotiable design principles

These override convenience. If a task seems to conflict with one, stop and flag it.

1. **The AI never decides eligibility.** Eligibility is computed by a deterministic, auditable rules engine over structured JSON rules. The LLM is used only to *explain* verified scheme records in simple language, to translate them, and to power the chatbot.
2. **The chatbot never invents schemes.** It answers only from the scheme database and the user's own profile. If it does not know, it says so and points to the official source.
3. **Wrong eligibility destroys trust.** The engine returns three states: `eligible`, `not_eligible`, `needs_info`, always with a human-readable reason. Never guess.
4. **Every scheme has a "last verified on" date**, shown in the UI. Only admin-reviewed schemes with `status = published` are visible to users.
5. **Privacy first.** We store sensitive family, income, and disability data. India's DPDP Act 2023 applies: explicit consent, data minimisation, encrypted sensitive fields, ability to delete an account and all its data, hosting in an Indian region.
6. **WhatsApp rules are strict.** Business-initiated messages must use **pre-approved templates** and go only to users who **opted in**. Never send free-form text outside the 24-hour customer-service window.
7. **Accessibility for elderly and low-literacy users.** Large tap targets (minimum 48px), high contrast, large readable type, minimal navigation depth, icons with text labels, plain language.
8. **Start narrow.** The MVP data scope is **Tamil Nadu plus central schemes**, around 50 to 100 well-verified schemes. Accuracy beats coverage. Schema design must still allow other states later.
9. **Simple over clever.** One service, one database, one worker. No microservices, no premature abstractions.
10. **Zero-cost first.** The project must run end to end at ₹0. Every paid dependency sits behind an interface with a free default. See section 18.

## 4. Tech stack (fixed; one tool per layer, do not substitute)

| Layer | Choice |
|---|---|
| Frontend | **React** (TypeScript) as a mobile-first **PWA**, built with **Vite** |
| UI components | **Material UI (MUI)** |
| Backend | **FastAPI** (Python 3.12) |
| ORM and migrations | **SQLAlchemy 2.x + Alembic** |
| Database | **MySQL 8** |
| Auth | **Mobile number + password login + JWT** (access + refresh tokens); OTP login remains available with `AUTH_MODE=otp` (see 18.4) |
| SMS OTP | **MSG91** when `AUTH_MODE=otp`; **log provider** in development (see 18.4) |
| WhatsApp | **Meta WhatsApp Cloud API** (see 18.4) |
| Eligibility engine | **Custom Python rules engine** (JSON rules, pure functions, no AI) |
| AI (explain, translate, chatbot) | **Gemini Flash free tier** via a provider interface; Claude adapter retained for later (see 18.3) |
| Background jobs and scheduling | **Celery** with **Redis** as the broker; **Celery Beat** for schedules |
| Maps and nearest facility | **Leaflet + OpenStreetMap** on the frontend; distance via MySQL spatial functions on our own `facilities` table |
| Admin panel | **SQLAdmin** (mounted inside FastAPI) |
| Analytics | **Metabase** (reads the MySQL database) |
| Packaging and hosting | **Docker + docker-compose**; **Oracle Cloud Always Free, Mumbai (India West)** with Hyderabad (India South) fallback |
| Error monitoring | **Sentry** (frontend and backend), Developer free plan |
| Testing | **pytest** (backend), **Vitest + React Testing Library** (frontend) |

Secrets live in environment variables (`.env`, never committed). Provide a `.env.example`.

## 5. Repository layout

```
schemeping/
├── AGENTS.md                 # this file
├── CLAUDE.md                 # pointer to AGENTS.md
├── docker-compose.yml        # api, worker, beat, mysql, redis, (metabase)
├── docker-compose.prod.yml   # production overrides (Caddy, no dev mounts)
├── .env.example
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/             # config, security, db session, logging, crypto
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic request/response models
│   │   ├── api/              # routers: auth, profile, family, schemes, eligibility, notifications, chat, facilities, admin
│   │   ├── services/         # business logic: otp, eligibility, llm, whatsapp, facilities
│   │   ├── eligibility/      # the rules engine (pure Python, fully unit-tested)
│   │   ├── workers/          # Celery app and tasks
│   │   └── admin/            # SQLAdmin views
│   ├── alembic/
│   ├── seed/                 # verified scheme data (JSON/YAML) + seed script
│   └── tests/
└── frontend/
    ├── src/
    │   ├── pages/            # Login, Profile, Family, Dashboard, SchemeDetail, Apply, Chat
    │   ├── components/
    │   ├── api/              # typed API client
    │   ├── i18n/             # translations for the 6 UI languages
    │   └── theme/            # MUI theme
    └── public/               # PWA manifest, icons, service worker
```

## 6. Users and their data

### 6.1 Registered user (the head of household / account owner)
Full name, age, gender, occupation, annual income, education level, marital status, full address, state, district, village/town/city, pincode, mobile number, **password hash** (scrypt; never the password), preferred language, consent flags (data processing, WhatsApp opt-in). In the default password mode nothing proves ownership of the mobile number (`mobile_verified_at` stays NULL); an OTP sign-in is what sets it.

### 6.2 Family member (many per user)
Name, age (or date of birth), gender, relationship to user, occupation, education status, annual income, disability status, student status, widow status, senior-citizen status.

> **Store date of birth, not just age.** Age-based triggers (daughter turns 18, someone reaches pension age) must be computed from DOB by the daily job. Derived flags like `is_senior` are computed, not typed by the user, where possible.

### 6.3 Admin
Staff who add and verify schemes, publish them, send bulk alerts, and view analytics. Separate role, separate login, full audit logging.

## 7. Data model (high level)

| Table | Key fields | Relationships |
|---|---|---|
| `users` | id, name, mobile (unique), password_hash, mobile_verified_at, dob, gender, occupation, annual_income, education, marital_status, state, district, locality, pincode, language, consent fields, created_at | has many `family_members`, `notifications` |
| `family_members` | id, user_id, name, relationship, dob, gender, occupation, education_status, annual_income, is_disabled, is_student, is_widow | belongs to `users` |
| `schemes` | id, slug, name, department, level (central/state), state, category, scope (individual/family/event), benefit_summary, benefit_amount, benefit_type, eligibility_rules (JSON), required_documents (JSON), application_steps (JSON), apply_url, deadline, status (draft/published/archived), last_verified_on, source_url | has many `scheme_translations`, `eligibility_results` |
| `scheme_translations` | scheme_id, language, simple_title, simple_description, simple_benefits, simple_steps | belongs to `schemes`; **cached LLM output** |
| `eligibility_results` | id, user_id, family_member_id (nullable), scheme_id, status (eligible/not_eligible/needs_info), reasons (JSON), missing_fields (JSON), computed_at | links a person to a scheme |
| `facilities` | id, name, type (csc/taluk_office/collector_office/e_sevai/welfare_office), address, district, state, lat, lon (POINT), working_hours, phone, verified_on | independent |
| `notifications` | id, user_id, type, template_name, payload (JSON), status (queued/sent/delivered/failed), provider_message_id, created_at, sent_at | belongs to `users` |
| `otp_requests` | id, mobile, otp_hash, expires_at, attempts, created_at | rate-limited |
| `admin_audit_logs` | id, admin_id, action, entity, entity_id, diff (JSON), created_at | immutable |
| `chat_messages` | id, user_id, role, content, language, created_at | optional, for chatbot history |

Use Alembic migrations for every schema change. Index `users.mobile`, `eligibility_results (user_id, scheme_id)`, `schemes (status, category)`, and a spatial index on `facilities`.

## 8. Eligibility engine (the heart of the product)

### 8.1 Rule format
Each scheme stores `eligibility_rules` as JSON using nested `all` / `any` / `not` groups of conditions:

```json
{
  "applies_to": "individual",
  "rules": {
    "all": [
      {"field": "age", "op": ">=", "value": 18},
      {"field": "annual_income", "op": "<=", "value": 250000},
      {"field": "state", "op": "==", "value": "Tamil Nadu"},
      {"any": [
        {"field": "is_student", "op": "==", "value": true},
        {"field": "occupation", "op": "in", "value": ["farmer", "agricultural_labourer"]}
      ]}
    ]
  }
}
```

Supported operators: `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not_in`, `between`, `exists`.

### 8.2 Evaluation
- `applies_to` is `individual` or `family`.
- **Individual** schemes are evaluated for the user and for each family member separately.
- **Family** schemes are evaluated at household level against aggregated fields (e.g. `household_income`, `family_size`, `has_senior`, `has_girl_child`, `has_disabled_member`).
- Each condition evaluates to `true`, `false`, or `unknown` (field missing). Combine with three-valued logic:
  - any required condition false → `not_eligible`
  - all true → `eligible`
  - otherwise → `needs_info` with `missing_fields` listed
- Every result carries `reasons`: a list of plain structured items such as `{"field": "annual_income", "ok": true, "user_value": 180000, "required": "<= 250000"}`. The UI turns these into "Why you qualify".

### 8.3 Requirements
- Pure functions, no database or network calls inside the engine.
- 100% deterministic. Same input, same output.
- Heavily unit-tested (table-driven tests with real profiles).
- Re-run when a profile changes, when a scheme is published or edited, and in the daily job.

## 9. LLM usage

Used for exactly three things:
1. **Simplify:** take a verified scheme record and produce "What is this scheme?", benefits, and steps in simple language.
2. **Translate** into English, Tamil, Hindi, Telugu, Kannada, Malayalam. **Cache every result** in `scheme_translations`; regenerate only when the scheme changes.
3. **Chatbot** (multilingual), grounded only in retrieved scheme records plus the user's profile and eligibility results.

Rules:
- The prompt always includes the structured scheme record; the model must not add facts not present in it.
- Output is requested as strict JSON where structured, and validated before saving.
- Chatbot system prompt forbids inventing schemes, amounts, deadlines, or documents. If unsure, it says so and suggests contacting the listed office.
- Log token usage; handle API errors with retries and a graceful fallback (show the original English admin text).
- Never send raw sensitive identifiers (full address, exact income) to the model unless required for the answer; prefer eligibility results over raw profile data.
- **Provider-agnostic.** All LLM calls go through `app/services/llm/base.py::LLMProvider`. Default implementation is Gemini (section 18.3); a Claude adapter exists but is not the default.

## 10. Notifications and WhatsApp

### 10.1 Password login (default)
1. The sign-in screen offers **Sign in** and **Create account** for the same mobile number and password. No SMS is sent.
2. Registration stores `users.password_hash`, hashed with `hashlib.scrypt` (stdlib, memory-hard; parameters stored inside the hash so they can be raised later and old hashes are upgraded on the next sign-in). The password itself is never stored or logged.
3. Login checks the password in constant time. An unknown number and a wrong password return the identical 401 message, and an unknown number still runs one hash so response time does not reveal which accounts exist.
4. On success, issue JWT access and refresh tokens (httpOnly cookies).
5. Rate limits: 10 attempts per mobile per 15 minutes, 30 per IP per 15 minutes, 20 registrations per IP per hour (higher because carrier NAT shares one IP between many people).
6. Changing the password requires the current one and revokes every other session (the device that made the change stays signed in).
7. Nothing verifies that the mobile number belongs to the caller. Consequences: WhatsApp messages may reach a mistyped number, and account recovery is operator-assisted (`python -m app.scripts.reset_password <mobile>`), not self-service.

### 10.1a OTP login (`AUTH_MODE=otp`)
1. User enters mobile number.
2. Backend generates a 6-digit OTP, stores only its **hash** with expiry (5 minutes) and attempt count.
3. OTP sent by SMS through the configured SMS provider.
4. User submits OTP; on success, issue JWT access and refresh tokens and set `mobile_verified_at`.
5. Rate limits: max 3 OTP requests per mobile per 15 minutes, max 5 verification attempts per OTP, plus IP-based limits.
6. India SMS requires **DLT registration** (sender ID and templates) when a real SMS provider is used; document this in the README as a deployment prerequisite.
7. In development the log provider prints the OTP to the server console and never sends SMS.
8. The frontend is config-driven: `GET /api/v1/auth/config` returns `mode: password | server | widget`, and the sign-in screen renders the matching form.

### 10.2 WhatsApp opt-in
WhatsApp notifications are enabled only after the user ticks an explicit opt-in during onboarding. Store the consent timestamp. Provide an opt-out in settings and honour a "STOP" reply.

### 10.3 Message types (all template-based)
| Template | Trigger |
|---|---|
| `scheme_summary` | User taps "Send to WhatsApp" on a scheme |
| `new_scheme_eligible` | A new or edited scheme turns eligible for someone |
| `family_milestone` | Age/status change makes a family member newly eligible |
| `deadline_reminder` | Deadline in 7 / 3 / 1 days for a scheme the user qualifies for |
| `festival_benefit` | Admin publishes a festival scheme |

Example `scheme_summary` content:

```
Scheme: {{scheme_name}}
Benefit: {{benefit}}
Eligibility: {{eligibility_line}}
Documents Needed: {{documents}}
Apply Before: {{deadline}}
Nearest Center: {{facility_name}}
For full details visit SchemePing.
```

### 10.4 Background jobs (Celery)
- **Daily job:** recompute age-based flags from DOB, re-run eligibility for changed people, diff against previous results, and queue notifications for newly eligible schemes.
- **Deadline job:** queue reminders at 7/3/1 days.
- **Send job:** drains the notification queue with retries, rate limiting, and delivery-status updates (webhook from the messaging provider).
- **Festival broadcast job:** admin-triggered for a published scheme, batched by state.
- Deduplicate: never send the same template for the same scheme to the same user twice.

## 11. Core user flow

1. **Register:** mobile number and password (sign up), then the profile form, then WhatsApp opt-in and data-consent checkboxes.
2. **Add family:** add, edit, or remove members.
3. **Dashboard:** eligible schemes appear as cards (name, benefit amount, eligibility status, deadline, department, priority). Filter chips: Individual, Family, Education, Healthcare, Agriculture, Housing. A person selector lets the user view results for themselves or any family member.
4. **Scheme detail:** What is this scheme (simple language), Benefits, Eligibility ("why you qualify"), Required Documents, Application Deadline with days remaining, "last verified on".
5. **How to Apply:** step-by-step guide (collect documents, visit office, fill application, submit, track) plus **nearest government facilities** by geolocation (name, address, distance, working hours, phone), with a fallback to pincode/district if location permission is denied.
6. **Send to WhatsApp:** one tap, sends the `scheme_summary` template.
7. **Chatbot:** floating assistant in the user's language.

## 12. Admin panel (SQLAdmin)

- Create and edit schemes with a validated JSON rule editor and a "test rule against sample profile" check.
- Draft, review, and publish workflow; "last verified" updated on publish.
- Manage facilities.
- Trigger bulk WhatsApp alerts (with a confirm step and recipient count preview).
- View audit logs.
- Statistics (users, families, eligible matches, messages sent, applications clicked) via **Metabase** dashboards on the database.
- Admin auth is separate from citizen login (password or OTP) (username/password + 2FA recommended) and every action is written to `admin_audit_logs`.

## 13. UI and design system

- **Style:** government trust plus modern fintech: clean, calm, spacious.
- **Palette:** deep blue (primary), white (background), green (success and eligible states). Accent colours for warnings (amber) and errors (red).
- **IMPORTANT STYLING RULE:** in all HTML, CSS, and theme code, **use CSS color names** (for example `navy`, `white`, `seagreen`, `darkgreen`, `whitesmoke`, `gray`, `firebrick`, `orange`) **instead of hex codes or RGB values**. Do this in the MUI theme, global CSS, and any inline styles.
- **Mobile first**, responsive up to desktop. Bottom navigation on mobile.
- **Large buttons** (min 48px height), large readable font (base 16 to 18px), strong contrast, clear focus states.
- Every icon has a text label. Support font-size increase. Respect `prefers-reduced-motion`.
- Language switcher always visible; UI strings live in i18n files (English, Tamil, Hindi, Telugu, Kannada, Malayalam).
- Loading, empty, and error states for every screen.
- PWA: manifest, icons, offline shell, installable.

## 14. Security and compliance checklist

- Encrypt sensitive columns (income, disability, DOB) at the application level; TLS everywhere.
- JWT with short-lived access tokens and rotating refresh tokens; httpOnly cookies preferred over localStorage.
- Strict input validation (Pydantic), parameterised queries (SQLAlchemy), CORS locked to known origins, security headers.
- Password, OTP and API rate limiting; brute-force protection. Passwords are hashed with scrypt; never log them or accept them in a query string.
- Consent records (what, when, version of policy).
- **Account deletion** endpoint that erases the user and all family data.
- Privacy policy and terms pages.
- Do not log OTPs, tokens, or full personal data. Mask mobile numbers in logs.
- Secrets in env vars only. Dependency scanning in CI.
- Hosting region: India (Oracle Mumbai, see 18.2).

## 15. Quality bar (definition of done for every task)

- Code typed and linted (ruff + mypy on backend, eslint + tsc on frontend).
- Unit tests for new logic; the eligibility engine requires table-driven tests.
- API documented via FastAPI's OpenAPI schema.
- No secrets or personal data committed. `.env.example` updated.
- Works at a 360px-wide mobile viewport.
- README updated with run instructions for anything new.
- Small, focused commits with clear messages.

## 16. How to work (instructions for the AI coding agent)

- Work **one phase at a time**. Do not build features from later phases.
- Before coding, restate the phase goal and list the files you will create or change.
- Prefer the simplest implementation that satisfies the acceptance criteria.
- Do not add libraries outside the stack in section 4 without asking. If something seems missing, ask.
- When requirements are ambiguous, make a reasonable choice, state it in one line, and continue.
- After each phase: run tests, list what was built, list any deviations, and list what the next phase will need.
- Never fabricate real scheme data. Seed data must be clearly marked `source_url` + `last_verified_on` and flagged for human verification before publishing.

## 17. Phase roadmap

| Phase | Focus |
|---|---|
| 1 | Foundation: repo skeleton, Docker, database models, migrations, seed pipeline |
| 2 | Identity: password login (OTP available behind `AUTH_MODE=otp`), JWT, profile, family members, consent, frontend shell |
| 3 | Brain: eligibility engine, results API, dashboard with filters |
| 4 | Understanding and last mile: scheme detail, LLM simplification and translation, how-to-apply, nearest facility |
| 5 | Reach: WhatsApp templates, send-to-WhatsApp, Celery notifications, festival alerts |
| 6 | Assistant, admin, and launch: multilingual chatbot, SQLAdmin, Metabase, security hardening, deployment |

## 18. Zero-cost operating decisions

The project must run end to end for ₹0 during development and early launch. Paid services are allowed only behind an interface with a free default. These decisions were confirmed by the project owner.

### 18.1 Cost reality (do not pretend otherwise)

| Service | Free? | Reality |
|---|---|---|
| Compute, database, Redis, object storage | Yes | Oracle Cloud Always Free |
| LLM simplify/translate/chat | Yes | Gemini Flash free tier |
| Analytics, admin, maps, TLS, CI | Yes | Metabase OSS, SQLAdmin, OSM, Let's Encrypt, GitHub Actions |
| Error monitoring | Yes, limited | Sentry Developer: 5k errors/month, 1 user |
| SMS OTP at production volume | **No** | DLT registration plus per-SMS charges |
| Business-initiated WhatsApp templates | **No** | India rates: ₹0.115 utility, ₹0.8631 marketing per delivered message. Only 1,000 *service* messages/month per business number are free |

Consequence: the app ships with a **free development messaging mode** and a **paid production mode**, switched by env var. No feature may hard-code a paid vendor.

### 18.2 Hosting

- Target: **Oracle Cloud Infrastructure Always Free**, home region **India West (Mumbai)**, fallback **India South (Hyderabad)**. Both satisfy DPDP India-region hosting.
- Shape: `VM.Standard.A1.Flex`, 2 OCPU / 12 GB ARM (within the always-free 1,500 OCPU-hour and 9,000 GB-hour allowance).
- Everything runs via `docker-compose` on that single VM: Caddy, api, worker, beat, mysql, redis, and optionally metabase.
- Known constraints, document them in the README:
  - A1 capacity is often unavailable in Mumbai; retry or use Hyderabad.
  - Oracle may reclaim accounts idle for 30 days; keep a health check and periodic activity.
  - ARM64 images are required. `mysql`, `redis`, `metabase`, `python:3.12-slim`, and `node` all publish arm64 tags.
- Fallback for demos without any cloud account: run the same compose file locally and expose it with a free tunnel (Cloudflare Quick Tunnel or Tailscale Funnel). Identical code.
- TLS and domain: **Caddy** with automatic Let's Encrypt certificates on a free DuckDNS subdomain. No paid domain required.
- Backups: nightly `mysqldump` to OCI Object Storage always-free tier.

### 18.3 LLM provider

- Default: **Gemini Flash free tier** via `google-genai` or plain `httpx`, implemented as `GeminiProvider`.
- `LLMProvider` protocol exposes `simplify(scheme_record, language)`, `translate(text, language)`, and `chat(messages, context)`.
- `ClaudeProvider` is written but not enabled by default; selecting it is one env var.
- Free-tier data-use caveat: prompts must contain only public scheme text plus the minimum derived profile facts needed to answer. Never send name, mobile, address, or raw income. Prefer eligibility results ("eligible for X because income is under the limit") over raw values.
- Rate-limit handling: exponential backoff with jitter, daily-quota awareness, and a graceful fallback to the admin-written English text. Translation and simplification are cached, so quota is consumed once per scheme per language.

### 18.4 Messaging providers

- Interface: `MessagingProvider` with `send_otp(mobile, code)` and `send_template(mobile, template_name, params)`.
- **Chosen WhatsApp provider from day one: Meta WhatsApp Cloud API**, direct integration with `httpx`. Business number, Meta Business verification, and pre-approved templates are required. 1,000 free service messages/month; business-initiated utility templates are billed at ₹0.115 in India. Wiring it in Phase 5; the code and env vars are designed for it from Phase 1.
- Default for development and CI: `LogProvider`. It writes OTPs to the console (never to the DB in plaintext) and records WhatsApp sends as `queued` notifications without contacting a network. Switching to Meta is one env var plus credentials.
- Production SMS: **MSG91**, requires DLT registration.
- **Chosen OTP channel (decision, Oct 2026): MSG91 OTP Widget** (`MESSAGING_PROVIDER=msg91_widget`), because DLT registration is a paid, paperwork-heavy prerequisite that would block launch. The widget sends from MSG91's own DLT-registered sender and default template, so the project registers nothing. Consequence: MSG91, not our `otp_requests` table, owns OTP generation, expiry, attempts and resends, and the SMS header shows MSG91 rather than "SchemePing". The backend must never trust a client-supplied mobile in this mode: it verifies the widget's `access-token` server-side (`POST /api/v1/auth/otp/widget/verify`) and only then issues a session. `msg91` (own DLT sender) and `log` (development) remain supported; the decision is revisited when a registered entity and DLT registration exist.
- The "Send to WhatsApp" button always also offers a `https://wa.me/?text=...` click-to-chat fallback that costs nothing and needs no template. Use it when no provider is configured.
- **Chosen citizen auth (decision, Oct 2026): password login is the default** (`AUTH_MODE=password`; `POST /auth/register`, `POST /auth/login`, `POST /auth/password`). DLT registration and per-SMS charges blocked an OTP-only launch, so the mobile number plus a scrypt-hashed password now authenticate the account. Accepted consequences: the mobile number is **unverified** (a mistyped or borrowed number can register, and a WhatsApp message may reach it), and password reset is operator-assisted (`python -m app.scripts.reset_password <mobile>`), not self-service. The OTP code is not deleted: `AUTH_MODE=otp` re-enables it with the same `MESSAGING_PROVIDER` switch, and it remains the only thing that sets `mobile_verified_at`. Two notification rules follow: a user-initiated summary requires consent only (`can_send_on_request`), while business-initiated templates still require a verified mobile (`can_notify`); the festival broadcast uses consent plus no opt-out, because password accounts would otherwise never receive it.
- Webhook endpoints for delivery status live in `app/api/notifications.py` and verify the provider signature.

### 18.5 Other free-tier notes

- Metabase runs in its own container with a separate MySQL schema, bound to localhost and reachable over an SSH tunnel or an authenticated Caddy route. Never expose it publicly without auth.
- Sentry is optional; if `SENTRY_DSN` is empty the app starts normally.
- No paid geocoding API. Seed facility lat/lon manually from official sources. If Nominatim is ever used, respect its 1 request/second policy and cache results.
- CI (lint, typecheck, tests, Docker build) runs on GitHub Actions free minutes. Docker images publish to GHCR.
- Do not introduce a paid dependency without an explicit decision recorded in this section.
