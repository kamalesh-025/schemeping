# Deploying SchemePing (AWS Mumbai)

This guide deploys the whole stack on one EC2 instance in **ap-south-1
(Mumbai)**: Caddy (TLS), the FastAPI app, the Celery worker and beat, MySQL,
Redis, the PWA (nginx) and optionally Metabase.

Region matters: the app stores personal data (DPDP Act 2023), so the
database and the servers must stay in India.

---

## 1. Server

| Item | Recommendation |
|---|---|
| Instance | `t3.medium` (2 vCPU, 4 GB) to start; `t3.large` when the worker and Metabase share the box |
| OS | Ubuntu 24.04 LTS |
| Storage | 30 GB gp3 (MySQL data + backups) |
| Region | `ap-south-1` (Mumbai) |
| Security group | allow 22 (your IP only), 80 and 443 (any) |

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker "$USER" && newgrp docker
```

## 2. Get the code and the environment

```bash
sudo mkdir -p /srv/schemeping && sudo chown "$USER" /srv/schemeping
cd /srv/schemeping
git clone <your-repo-url> .
cp .env.example .env
```

Fill `.env` (never commit it):

```bash
# Required, and different for every deployment
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
MYSQL_PASSWORD=$(openssl rand -hex 16)
MYSQL_ROOT_PASSWORD=$(openssl rand -hex 16)
WHATSAPP_WEBHOOK_SECRET=$(openssl rand -hex 16)
ADMIN_API_KEY=$(openssl rand -hex 16)
CADDY_DOMAIN=schemeping.example.in   # your domain, pointing at this host
CORS_ORIGINS=https://schemeping.example.in
```

| Variable | Why it matters |
|---|---|
| `SECRET_KEY` | signs sessions and admin tokens |
| `ENCRYPTION_KEY` | encrypts DOB, income, gender, disability, TOTP secrets |
| `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` | database access |
| `WHATSAPP_WEBHOOK_SECRET` | verifies the provider's delivery callbacks |
| `ADMIN_API_KEY` | guards the machine-to-machine admin endpoints |
| `CADDY_DOMAIN` | the domain Caddy issues the TLS certificate for |
| `CORS_ORIGINS` | must list only your own domain |

> Losing `ENCRYPTION_KEY` means losing every encrypted field. Back it up
> somewhere safe and separately from the server.

## 3. Start the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Apply the migrations and create the first staff account:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
    alembic upgrade head

# The first admin (username, password, role=editor|publisher) - only works
# while the admin table is empty.
curl -X POST https://$CADDY_DOMAIN/api/v1/admin-panel/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"a-long-password","role":"publisher"}'
```

Then sign in at <https://schemeping.example.in/admin> with the username, the
password and a 6-digit TOTP code from your authenticator app. The TOTP secret
is printed by this helper:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
    python -c "from app.models.admin import AdminUser; from app.core.db import SessionLocal; \
s=SessionLocal(); a=s.query(AdminUser).first(); print(a.username, a.totp_secret)"
```

## 4. HTTPS and DNS

- Point an `A` record for the domain at the instance's public IP.
- Caddy obtains a Let's Encrypt certificate automatically on the first
  request. Port 80 must be open for the ACME challenge.
- Renewals are automatic; Caddy stores the certificates in the `caddy-data`
  volume.

## 5. Managed alternatives

The single-host setup is the cheapest option. When traffic grows:

| Piece | Managed option | Notes |
|---|---|---|
| MySQL | **Amazon RDS for MySQL** in `ap-south-1` | set `DATABASE_URL` to the RDS endpoint, enable automated backups and a read replica for analytics |
| Redis | **Amazon ElastiCache for Redis** | set `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` |
| TLS | keep Caddy, or use an **ALB** with ACM certificates | the ALB replaces Caddy; `CORS_ORIGINS` stays the same |
| Static files | **CloudFront** in front of S3 | optional; the PWA is small |

With RDS, remove the `mysql` service and set:

```bash
DATABASE_URL=mysql+pymysql://schemeping:<password>@<rds-endpoint>:3306/schemeping?charset=utf8mb4
```

## 6. Backups

```bash
# Local backups (scripts/backup.sh) - run from cron on the host:
15 2 * * * cd /srv/schemeping && ./scripts/backup.sh >> /var/log/schemeping-backup.log 2>&1
```

Copy the files off the instance (S3 lifecycle rule, or `scp` to a second
host). With RDS, use the automated backups plus a read replica.

Restoring:

```bash
gunzip < backups/schemeping-20260101-020000.sql.gz | \
    docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T mysql \
    mysql -u root -p"$MYSQL_ROOT_PASSWORD" schemeping
```

## 7. Observability

- **Sentry**: set `SENTRY_DSN` in `.env` and rebuild. Errors from the API and
  the worker are reported; `send_default_pii=False` keeps personal data out
  of the reports.
- **Health**: `/health` (liveness + database) and `/ready` (readiness for the
  load balancer) are served by the API.
- **Request ids**: every response carries `X-Request-ID`; the same id is in
  the structured logs, so a user can quote it in a support request.
- **Uptime**: point an external monitor at
  `https://your-domain/health` every minute.

## 8. MSG91, DLT and WhatsApp template approval (India)

Business-initiated WhatsApp messages need approved templates and a registered
sender. Do this **before** switching `WHATSAPP_PROVIDER` to `msg91`:

1. **DLT registration** (per TRAI): register the organisation, the sender
   header and every message template on a DLT platform, get your DLT IDs,
   then send the template IDs to MSG91 for approval.
2. **MSG91 account**: create a WhatsApp sender number and request the
   WhatsApp API access.
3. **Template approval**: submit the five templates in
   `docs/whatsapp-templates.md` with their exact sample texts. Approval takes
   a few hours to a few days. Map the approved ids:

   ```bash
   MSG91_WHATSAPP_TEMPLATE_IDS=scheme_summary:1101,new_scheme_eligible:1102,family_milestone:1103,deadline_reminder:1104,festival_benefit:1105
   ```

4. **Webhook**: point the provider's delivery callback at
   `https://your-domain/api/v1/notifications/webhook` and set the same
   secret in `WHATSAPP_WEBHOOK_SECRET`.
5. **SMS OTP (production)**: SMS is also DLT-gated. Set `MESSAGING_PROVIDER=msg91`
   with `MSG91_AUTH_KEY`, `MSG91_SENDER_ID` and `MSG91_OTP_TEMPLATE_ID`.
6. Only then set `WHATSAPP_PROVIDER=msg91` and restart the worker.

Checklist:

- [ ] Organisation registered on a DLT platform
- [ ] Sender header approved
- [ ] All five templates approved with the exact texts from `docs/whatsapp-templates.md`
- [ ] Template ids in `MSG91_WHATSAPP_TEMPLATE_IDS`
- [ ] Webhook URL + shared secret configured
- [ ] `WHATSAPP_PROVIDER=msg91` and a test message delivered end to end

## 9. Costs (India region, small scale)

| Item | Cost |
|---|---|
| EC2 t3.medium | about ₹1,500-2,500/month (varies) |
| EBS 30 GB gp3 | about ₹700/month |
| Data transfer | small at this scale |
| WhatsApp messages | ₹0.115 per delivered utility message, ₹0.8631 per marketing message |
| SMS OTP | per-message DLT rates |

Everything else (Sentry free tier, Metabase, OSM maps, Gemini free tier) is
free.

## 10. Operations

```bash
# Logs
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f worker

# Restart one service
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart api

# Apply a new migration after a pull
git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api alembic upgrade head
```

The daily jobs (eligibility scan 07:30 IST, deadline reminders 10:00 IST,
chat-history purge 03:15 IST) run in the `beat` container - check it is
running with `docker compose ... ps beat`.
