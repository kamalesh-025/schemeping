# SchemePing

SchemePing is a mobile-first, installable web app (PWA) that helps Indian
citizens discover, understand, and apply for the government welfare schemes they
are eligible for. A person registers once, adds their family, and SchemePing
matches each member against a verified scheme database, explains each scheme in
plain language, lists the documents and office needed, and nudges them on
WhatsApp when something new applies.

Read [`AGENTS.md`](./AGENTS.md) before writing code. It is the single source of
truth for scope, stack, design principles, and the phase roadmap.

## How it works (short version)

- **The AI never decides eligibility.** A deterministic, auditable rules engine
  evaluates structured JSON rules and returns `eligible`, `not_eligible`, or
  `needs_info`, always with a human-readable reason.
- **The AI only explains and translates** verified scheme records, and powers
  the chatbot, which answers strictly from the scheme database and the user's own
  profile.
- **Privacy first.** Income, date of birth, and disability data are encrypted at
  the application level; accounts can delete all their data; hosting is in India.

## Stack

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript, Vite, MUI, i18n (6 Indian languages), PWA |
| Backend | FastAPI (Python 3.12), SQLAlchemy 2, Alembic, Pydantic |
| Database | MySQL 8 |
| Auth | Mobile number + password (scrypt) + JWT access token and rotating refresh cookie; OTP available with `AUTH_MODE=otp` |
| Jobs | Celery + Redis (Celery Beat for schedules) |
| AI | Gemini Flash free tier behind an `LLMProvider` interface |
| Messaging | Meta WhatsApp Cloud API (log provider in development) |
| Hosting | Docker Compose on Oracle Cloud Always Free, Mumbai (Hyderabad fallback), Caddy + Let's Encrypt |

Everything runs at zero cost during development: every paid dependency sits
behind an interface with a free default (see `AGENTS.md` section 18).

## Repository layout

```
schemeping/
├── AGENTS.md                 # project context, read first
├── docker-compose.yml        # mysql, redis, api, worker, beat
├── docker-compose.prod.yml   # production overrides (Caddy, no dev mounts)
├── Caddyfile
├── .env.example
├── backend/
│   ├── app/                  # core, models, schemas, api, services, eligibility, workers, admin
│   ├── alembic/              # migrations
│   ├── seed/                 # verified scheme data + seed script
│   └── tests/
└── frontend/
    ├── src/                  # pages, components, api, auth, i18n, theme
    ├── public/               # manifest, icons, service worker
    └── scripts/              # icon generator
```

## Prerequisites

- Docker Desktop (for MySQL + Redis)
- Python 3.12 (Python 3.14 is not supported)
- Node.js 20+ and npm

## Quick start

### 1. Configuration

```bash
cp .env.example .env
```

For running the backend on the host machine (not in Docker), point the database
URL at the published MySQL port:

```
DATABASE_URL=mysql+pymysql://schemeping:schemeping@127.0.0.1:3307/schemeping?charset=utf8mb4
```

The backend reads configuration from the process environment, the root `.env`,
or `backend/.env` (the backend-level file takes precedence when both exist).
Set `GEMINI_API_KEY` in one of those untracked local files to use Gemini for
the assistant. Compose passes the key only to backend containers.

### 2. Start MySQL and Redis

```bash
docker compose up -d mysql redis
```

MySQL is published on host port `3307` (override with `MYSQL_HOST_PORT`) to avoid
clashing with a local MySQL on `3306`.

If the backend logs
`sqlalchemy.exc.OperationalError: (2003, "Can't connect to MySQL server on '127.0.0.1' ... ConnectionRefusedError")`,
the MySQL container is not running, so nothing is listening on `3307`. That is
the usual state right after a reboot: the Docker engine has not started yet.
Check and fix with:

```bash
docker ps --filter name=schemeping-mysql      # is it up and healthy?
docker compose up -d mysql redis              # start (or restart) it
```

Starting Docker Desktop is enough to bring the containers back, because they use
`restart: unless-stopped`. Confirm with `GET /health`, which reports
`"database": "ok"` only when the API can reach MySQL. A local MySQL on `3306`
does not help: it is a different server with its own credentials, and the app is
configured for the container on `3307`.

### 3. Backend

```bash
cd backend
py -3.12 -m venv --clear .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m seed.load_schemes            # sample draft schemes + facilities
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

If you already created `.venv` with a different Python version, recreate it with
Python 3.12 before installing dependencies. Stop any running Uvicorn process
first so Windows can replace the environment files. If Python 3.12 is not
available through the Windows `py` launcher, install it with `uv` and install
the dependencies into the new environment:

```powershell
uv python install 3.12
uv venv --python 3.12 --clear .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

Native extensions such as `pydantic-core` are specific to the Python version
they were built for.

The API is served at `http://127.0.0.1:8000` with the OpenAPI docs at `/docs`
and a health check at `/health`.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs on `http://localhost:5173` and proxies `/api` and `/health`
to `http://127.0.0.1:8000` (the API target), so cookies stay same-origin and no
CORS setup is needed. If either port is already taken — for example by another
project on your machine — copy `frontend/.env.example` to `frontend/.env.local`
and point it somewhere free:

```
VITE_API_TARGET=http://127.0.0.1:8010
VITE_DEV_PORT=5180
```

### 5. Sign in during development

**Password sign-in is the default.** On the sign-in screen, open **Create
account**, enter any valid Indian mobile number and a password of at least 8
characters, and continue to onboarding. No SMS is sent and no SMS vendor is
configured, so the app runs at zero cost from the first minute.

- Passwords are hashed with `hashlib.scrypt` (standard library, memory-hard).
  The parameters are stored in the hash, so they can be raised later and old
  hashes are upgraded on the next successful sign-in.
- A mobile number is **not verified** in this mode. Anyone can register any
  number, so WhatsApp messages could reach a mistyped number. This trade-off is
  recorded in `AGENTS.md` section 18.4.
- There is no self-service password reset, because there is no verified contact
  channel. An operator resets a password after checking who they are talking to:

  ```bash
  cd backend
  python -m app.scripts.reset_password 9876543210
  ```

  The command prompts for the new password, hashes it, and signs the account out
  on every device. Inside Docker, run it with
  `docker compose exec api python -m app.scripts.reset_password 9876543210`.

To use SMS OTP instead, set `AUTH_MODE=otp`. The OTP code paths (backend-sent
code and the MSG91 widget) are kept and tested; the rest of this section
describes them.

#### OTP sign-in with the log provider

The default messaging provider is `log`: the OTP is **printed to the backend
console** (`[DEV OTP] ...`) and never sent by SMS and never stored in plaintext.
After requesting the code, look in the terminal where you started the backend.
If the backend runs in Docker, use `docker compose logs -f api` from the
repository root. Enter any valid Indian mobile number, read the code from the
`[DEV OTP]` line, and finish onboarding. To deliver real SMS, configure MSG91
credentials and DLT-approved sender/template details.

#### Configure real SMS OTP with MSG91

Real SMS is not enabled by default; the default auth mode is password. To use
SMS OTP, set `AUTH_MODE=otp` and, before switching to MSG91:

1. Create an MSG91 account and configure an OTP flow/template for India.
2. Complete DLT registration for the sender ID and OTP template. The template
   must include the OTP variable expected by MSG91 and be approved by the
   relevant telecom operator.
3. In the untracked root `.env`, set:

   ```dotenv
   MESSAGING_PROVIDER=msg91
   MSG91_AUTH_KEY=your_msg91_auth_key
   MSG91_SENDER_ID=your_approved_sender_id
   MSG91_OTP_TEMPLATE_ID=your_approved_otp_template_id
   ```

4. Restart the API so it receives the credentials:
   `docker compose up -d --build api`, or restart the host-run Uvicorn process.
5. Request a code and check `docker compose logs -f api` if the provider
   reports an error. In `msg91` mode the OTP is delivered by MSG91, not printed
   to the backend console.
6. **A `200 OK` from MSG91 does not mean the SMS reached the phone.** The API
   only confirms that MSG91 accepted the request; Indian operators scrub every
   message against DLT and drop non-compliant ones without telling the sender.
   Two different failures therefore exist:

   - *Request rejected by MSG91.* MSG91 still answers HTTP 200 and puts the
     reason in the body (`{"type": "error", "message": "..."}`). The provider
     now parses that envelope, logs `otp_delivery_failed` and returns 502
     instead of a false "OTP sent". Look for that log line first.
   - *Message accepted, then scrubbed by the operator.* The log shows
     `otp_sent` with a `request_id`, and nothing arrives. Open the MSG91
     dashboard → **OTP → Logs / Delivery Reports** and search that
     `request_id`. Typical causes:
     - error 211 — no DLT template ID, or an invalid one: the DLT template is
       not mapped to the MSG91 OTP template;
     - error 203 — sender/header or PE (entity) ID missing or not approved
       (`MSG91_SENDER_ID` empty is a strong hint);
     - "SMS not matched with DLT template" — the approved template text differs
       from what MSG91 sends (an extra space, punctuation or an unapproved
       variable is enough);
     - empty wallet, or an account that is not activated yet.

   Fix these on the MSG91/DLT side; no application change can bypass DLT. While
   they are open, keep `MESSAGING_PROVIDER=log` locally so development is never
   blocked by SMS delivery.

#### OTP without DLT registration: the MSG91 OTP Widget

Every A2P SMS to an Indian number is scrubbed against DLT, so switching SMS
vendors does not remove the requirement. There is one exception: MSG91's **OTP
Widget** sends with MSG91's own DLT-registered sender and default template, so
*you* do not register anything. MSG91 also generates and verifies the code, so
the OTP never passes through SchemePing code.

1. In the MSG91 dashboard go to **OTP → Widget → Create New Widget**. Pick the
   free plan, choose *Login using OTP → Mobile → SMS*, and save. Copy the
   **Widget ID** and the **Token** (`tokenAuth`).
2. In the untracked `.env` (`backend/.env` takes precedence over the repo-root
   `.env`) set:

   ```dotenv
   AUTH_MODE=otp
   MESSAGING_PROVIDER=msg91_widget
   MSG91_AUTH_KEY=your_msg91_auth_key
   MSG91_WIDGET_ID=your_widget_id
   MSG91_WIDGET_TOKEN=your_widget_token
   ```

3. Restart the API. `GET /api/v1/auth/config` now returns
   `{"mode": "widget", "widget_id": ..., "widget_token": ...}` and the sign-in
   screen drives MSG91's SDK with its own form. The auth key never leaves the
   server; only the widget id and its public token are served to the browser.
4. After the user types the code, MSG91 returns an `access-token`. The SPA posts
   it to `POST /api/v1/auth/otp/widget/verify`, and the API exchanges it with
   MSG91 for the mobile number that was actually verified before issuing the
   JWT. A mobile number posted by the client is ignored.

Things to know before choosing this mode:

- **MSG91 owns send and verify.** In widget mode `POST /auth/otp/request` and
  `POST /auth/otp/verify` answer `409`, and MSG91 (not `otp_requests`) enforces
  expiry, attempt limits and resends. Sessions, consent and profile handling are
  unchanged.
- **The SMS shows MSG91's sender**, not "SchemePing", because the DLT header
  belongs to MSG91.
- reCAPTCHA is on by default in a new widget. For local development either turn
  it off in the widget settings or allow `localhost` as a domain; otherwise
  sending fails with a captcha error.

Do not commit `.env` or paste provider keys into frontend configuration.

Seed data is clearly marked sample data (`source_url` + `last_verified_on`) and
must be reviewed by a human before publishing. Only schemes with
`status = published` are visible to users.

To see the dashboard with sample schemes while developing, load the seed and
publish it in development (the flag is refused when `APP_ENV=production`):

```bash
python -m seed.load_schemes --publish-sample-schemes
```

Recalculating your matches is automatic when you change your profile or family.
You can also `POST /api/v1/eligibility/recompute` (or use the dashboard, which
calls it live on the server's own schedule later). Dashboard priorities follow
a documented rule: `high` = an active relief event or a deadline within 14 days;
`medium` = benefit at least ₹10,000 or deadline within 30 days; otherwise
`normal`.

## Tests, lint, and types

Backend (from `backend/`):

```bash
.venv/Scripts/python -m pytest -q        # tests
.venv/Scripts/python -m ruff check .     # lint
.venv/Scripts/python -m mypy app seed tests
```

Backend tests need a MySQL server the test user can create databases on. They
create and migrate `schemeping_test` automatically. The base URL is configured
with `TEST_DATABASE_BASE_URL` (default
`mysql+pymysql://schemeping:schemeping@127.0.0.1:3307`). If your test MySQL user
cannot create databases, grant it once as root:

```sql
GRANT ALL PRIVILEGES ON *.* TO 'schemeping'@'%';
FLUSH PRIVILEGES;
```

Frontend (from `frontend/`):

```bash
npm run test        # Vitest + React Testing Library
npm run lint        # ESLint
npm run typecheck   # tsc --noEmit
npm run build       # production build
```

## Styling rule (important)

All HTML, CSS, and theme colours use **CSS colour names** (`navy`, `seagreen`,
`whitesmoke`, ...) instead of hex or rgb values. MUI's own colour helpers cannot
parse colour names, so:

- `frontend/src/theme/colorManipulator.ts` implements MUI's `colorManipulator`
  API with CSS `color-mix()`, and
- `vite.config.ts` aliases `@mui/system/colorManipulator` to it.

Because Vitest loads MUI as externalised CommonJS, which bypasses bundler
aliases, `vitest.setup.ts` installs the same helpers into MUI's CJS exports for
tests. Keep both in sync if you ever change the helpers.

`frontend/scripts/generate_icons.py` renders the PWA PNG icons with the standard
library only (no image library needed):

```bash
cd frontend && python scripts/generate_icons.py
```

## Configuration reference

`backend/app/core/config.py` is the authority; `.env.example` lists every
variable. Highlights:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Signs JWTs and hashes OTPs |
| `ENCRYPTION_KEY` | Fernet key(s) for sensitive columns; first key encrypts |
| `AUTH_MODE` | `password` (default; no SMS vendor) or `otp` |
| `PASSWORD_MIN_LENGTH` | Minimum password length (default 8) |
| `MESSAGING_PROVIDER` | `log` (free default), `msg91` (DLT required) or `msg91_widget` (DLT-free OTP Widget); only used when `AUTH_MODE=otp` |
| `LLM_PROVIDER` | `gemini` (free tier) with a Claude adapter kept for later |
| `COOKIE_SECURE` | Defaults to true in production, false elsewhere |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `SEED_ON_START` | Load sample data when the API container starts |

## Deployment notes

- Target: one small Linux VM in an **India** region. The current guide targets
  AWS EC2 in `ap-south-1` (Mumbai) — see
  [`docs/deployment-aws-mumbai.md`](docs/deployment-aws-mumbai.md). The
  Oracle Cloud Always Free alternative still works: point the same compose
  file at an ARM64 `VM.Standard.A1.Flex` in Hyderabad.
- Everything runs with
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`.
- TLS: Caddy obtains Let's Encrypt certificates automatically for the domain
  in `CADDY_DOMAIN`.
- Backups: nightly `mysqldump` through `scripts/backup.sh`; with RDS use the
  managed automated backups.
- **SMS OTP in production requires DLT registration** (registered sender ID and
  templates) with MSG91 before real OTP SMS can be delivered. This is a paid
  prerequisite, not a code change, and it is why password login is the default.
  If you enable `AUTH_MODE=otp`, either complete DLT registration or set
  `MESSAGING_PROVIDER=msg91_widget`, which uses MSG91's OTP Widget (MSG91's own
  registered sender and default template, no registration on our side); see the
  OTP Widget section above.
- WhatsApp business-initiated messages use the Meta Cloud API by setting
  `WHATSAPP_PROVIDER=meta` and configuring the phone-number ID, access token,
  webhook verify token, app secret, and approved templates in the untracked
  `.env`. Configure callback verification and delivery status at
  `/api/v1/notifications/webhook`. The user must opt in before SchemePing
  sends a business-initiated template. The exact template texts and setup are
  in [`docs/whatsapp-templates.md`](docs/whatsapp-templates.md). After changing
  provider settings, restart both the API and the Celery worker:
  `docker compose up -d --build api worker`. The worker is required to deliver
  queued messages; start `beat` too for scheduled reminders. Scheme detail also
  offers a user-initiated `wa.me` sharing link that requires no provider
  credentials or template. `GET /api/v1/features` reports
  `whatsapp_delivery` (true only when a real provider has every credential, so
  the UI never promises a message it cannot deliver) and
  `whatsapp_click_to_chat`.
- The Gemini assistant uses `GEMINI_API_KEY` on the backend. Add your own key
  to the untracked root `.env`; it is passed only to the API and worker
  containers and is never exposed to the frontend. Without a key the assistant
  falls back to the offline mock provider. If Gemini is unreachable or out of
  quota mid-conversation, the assistant still answers from the retrieved
  scheme records (documents, benefits, deadlines) and reports
  `grounded: false`, instead of showing a dead-end error.
- The staff panel lives at `/admin` (SQLAdmin, username + password + TOTP).

## Phase status

| Phase | Focus | State |
|---|---|---|
| 1 | Foundation: repo skeleton, Docker, models, migrations, seed pipeline | Done |
| 2 | Identity: password login (OTP behind `AUTH_MODE=otp`), JWT, profile, family, consent, frontend shell | Done |
| 3 | Brain: eligibility engine, results API, dashboard with filters | Done |
| 4 | Understanding and last mile: scheme detail, LLM simplify/translate, apply guide, nearest facility | Done |
| 5 | Reach: WhatsApp templates, Celery notifications, festival alerts | Done |
| 6 | Assistant, admin, launch: multilingual chatbot, SQLAdmin, Metabase, hardening, deployment | Done |

### Phase 5 notes

- **Five pre-approved templates** live in `app/services/messaging.py`
  (`WHATSAPP_TEMPLATES`); the approval pack is
  [`docs/whatsapp-templates.md`](docs/whatsapp-templates.md). A template that
  is not registered can never be sent.
- **Queueing guarantees.** `services/notifications.py` checks the WhatsApp
  opt-in, the per-category preferences, the 21:00–08:00 IST quiet hours and
  a per-user hourly rate limit before a row is written. Every message carries
  a `dedupe_key` with a unique index, so the same template can never be sent
  twice for the same scheme, person and window.
- **Jobs.** `daily_eligibility_scan` (07:30 IST) diffs the stored results and
  queues `new_scheme_eligible` / `family_milestone`;
  `deadline_reminders` (10:00 IST) queues 7/3/1-day reminders;
  `festival_benefit_broadcast` is admin-triggered for a published scheme.
- **Delivery status.** `send_notification` retries with exponential backoff
  and records the provider message id. Meta webhook verification uses the app
  secret HMAC signature; the optional MSG91 provider uses its shared secret.
  Delivery callbacks flip notification rows to `delivered` or `failed`.
- **Scheme-only product.** The disaster-event and broadcast subsystem was
  removed in Phase 6: there is no `disaster_events` table, no disaster
  template, and no `scope=event` scheme. Everything the app surfaces comes
  from a published scheme record.

### Phase 6 notes

- **The assistant is grounded by construction.** `services/chat.py` retrieves
  published scheme records (the user's stored ELIGIBLE results first, then
  keyword matches) and adds a *minimal* profile summary (language, district,
  age band, income band — never the name, the mobile number, the address or
  the exact income). The retrieved text is passed as a DATA block, and the
  system prompt forbids inventing schemes, amounts, deadlines, documents or
  offices. The assistant can also hold a normal conversation and answer
  general questions (for example, how applications usually work, common
  documents, or which office to visit). If a specific scheme is not in the
  verified records, it says so and points at the official source or nearest
  office. Opening the chat with an empty history shows a greeting, and a bare
  greeting does not trigger scheme cards.
- **Provider.** The assistant, simplification, and translation all use
  Gemini by default (`GEMINI_API_KEY`, `LLM_PROVIDER=gemini`). The Claude
  adapter remains optional for later. Without a Gemini key the app falls back
  to the deterministic mock provider.
- **The staff panel is separate from the citizen login.** `admin_users` holds
  PBKDF2 password hashes and TOTP seeds; `app/api/admin.py` is the API
  (editor / publisher roles, scheme workflow, rule testing, facilities,
  bulk alerts with a confirm step, read-only audit log) and `app/admin_panel.py`
  mounts SQLAdmin at `/admin` with the same credentials and 2FA. Every write
  is written to `admin_audit_logs` with the before/after diff.
- **Analytics.** `analytics_events` records scheme views, apply clicks and
  chat questions (no message content). Five SQL views
  (`v_users_by_geo`, `v_family_counts`, `v_eligible_matches`,
  `v_notification_stats`, `v_scheme_events`) feed Metabase, which connects
  with a read-only database user. See
  [`docs/analytics.md`](docs/analytics.md).
- **Hardening.** Security headers and an `X-Request-ID` on every response,
  in-process rate limits on the public endpoints, per-user assistant quota,
  chat history purged after 14 days, a consent record view, a full data
  export (`GET /me/export`) and verified account deletion.
- **Delivery.** `backend/Dockerfile.prod` and `frontend/Dockerfile.prod` are
  multi-stage and run as non-root; `docker-compose.prod.yml` adds Caddy for
  TLS, optional Metabase and strict environment variables; GitHub Actions
  runs lint, types, tests and image builds.

### Phase 4 notes

- **LLM layer.** `app/services/llm/` holds the provider protocol
  (`simplify_and_translate`) with two implementations: `GeminiProvider`
  (default, plain `httpx`, JSON responses, 3 retries with exponential backoff
  + jitter, token usage logged) and a deterministic `MockProvider` used in
  tests and when no `GEMINI_API_KEY` is set. A Claude adapter can be added
  behind the same interface. `GEMINI_MODEL` defaults to the free-tier alias
  `gemini-flash-lite-latest`; do not pin a dated model, because Google retires
  them for new keys (HTTP 404). If a pinned model does disappear,
  `GeminiProvider` retries once with the alias and logs
  `llm_model_unavailable_using_fallback`.
- **Translation cache.** Every generated translation is cached in
  `scheme_translations` keyed by a SHA-256 hash over the scheme's
  public text. Editing any cached field invalidates the entry; LLM failures
  fall back to the admin-written English text so the app never blocks.
- **Scheme detail + apply guide.** `GET /schemes/{id}?lang=&person=` serves
  the cached translation, the deterministic why-you-qualify facts
  (`explain_facts` — never LLM-generated), documents, deadline urgency and
  the last-verified date. The apply page shows the seeded step-by-step
  guide and offers `apply_url` when present.
- **Facilities.** `GET /facilities/nearest` ranks by `ST_Distance_Sphere`
  around the user's coordinates; `GET /facilities` filters by district or
  pincode as the no-geolocation fallback. The frontend explains what the
  location is used for before asking, stores nothing, and offers a
  Leaflet/OpenStreetMap map, `tel:` and directions links. 40 sample
  facilities ship in `seed/facilities.yaml` (marked for verification).

### Known tooling notes

- `StarletteDeprecationWarning` about `httpx` in `starlette.testclient`, and an
  Alembic `path_separator` deprecation warning, are third-party warnings and do
  not affect behaviour.
- The production CSS minifier rewrites the colour names it finds in authored CSS
  to hex at build time. Authored HTML, CSS, and theme code always uses colour
  names; component styles injected at runtime keep the names.
- The browser tab icon and the PWA icons are generated from the single source
  logo `frontend/public/icons/schemeping_logo.png`. After replacing that file,
  regenerate them with `python scripts/generate_icons.py` (needs Pillow). The
  script writes `favicon.ico`, `icons/icon-192.png`, `icons/icon-512.png`,
  `icons/icon-maskable-512.png`, `icons/apple-touch-icon.png`, and the lighter
  `icons/schemeping_logo-320.png` used by the header and the sign-in screen.
  The small sizes use the emblem only, because the wordmark is unreadable below
  roughly 100px.
