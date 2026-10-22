# Analytics with Metabase (Phase 6 Part C)

Metabase is the admin-facing analytics tool. It reads the SchemePing MySQL
database **read-only** - it never writes to application data.

## 1. What ships in the box

| Piece | Where |
|---|---|
| Metabase service | `docker-compose.prod.yml` (profile `analytics`) |
| Read-only DB user | `docker/mysql/init/02-analytics-readonly.sql` |
| SQL views | created by migration `e4f8a2c6d907` |

Start it:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    --profile analytics up -d metabase
```

Metabase listens on `127.0.0.1:3000` only. Reach it over SSH:

```bash
ssh -L 3000:localhost:3000 user@your-server
```

Then open <http://localhost:3000>.

## 2. Connect the database

1. Metabase first run: choose **Try Metabase** or set up an account.
2. **Admin > Settings > Add a data source > MySQL**.
3. Connection details:

   | Field | Value |
   |---|---|
   | Database name | `schemeping` |
   | Host | `mysql` (the compose network name) |
   | Port | `3306` |
   | Username | `analytics_ro` |
   | Password | the password you set in `02-analytics-readonly.sql` |
   | SSL | off (the database is inside the compose network) |

4. Click **Save and continue** and select the `schemeping` schema.

> The `analytics_ro` user has `SELECT` only. If Metabase tries to write, the
> database refuses - that is the point.

## 3. The views

All views live in the application schema and are safe to use as-is.

| View | Rows | Use it for |
|---|---|---|
| `v_users_by_geo` | one per state + district | "Where are our users?" |
| `v_family_counts` | one per state + district | users and family members per region |
| `v_eligible_matches` | one per scheme + result status | how many people match each scheme |
| `v_notification_stats` | one per template + status | messages sent / delivered / failed |
| `v_scheme_events` | one per scheme + kind + day | scheme views and apply clicks per day |

The `analytics_events` table behind `v_scheme_events` records `scheme_view`,
`apply_click`, `whatsapp_send` and `chat_question` events. It stores the user
id and scheme id only - no message content, no personal data.

## 4. Suggested dashboards

### "Reach" (weekly, for the team)

- **Users by state** - a table from `v_users_by_geo`, sorted by `users`.
- **New users per week** - a native query:

  ```sql
  SELECT DATE(created_at) AS week, COUNT(*) AS signups
  FROM users
  WHERE deleted_at IS NULL
  GROUP BY DATE(created_at)
  ORDER BY week DESC
  ```

- **Family members per district** - a bar chart from `v_family_counts`.

### "Schemes that matter"

- **Eligible matches per scheme** - a table from `v_eligible_matches`
  filtered to `result_status = 'eligible'`, ordered by `people` desc.
- **Needs-info schemes** - the same view filtered to
  `result_status = 'needs_info'`: these are the schemes where a small data
  change would unlock a benefit for many people.
- **Top schemes by views** - from `v_scheme_events` where `kind = 'scheme_view'`.
- **Apply clicks per scheme** - from `v_scheme_events` where
  `kind = 'apply_click'`. Compare with the views to see the drop-off.

### "Messaging health"

- **Notifications by status** - a pie chart from `v_notification_stats`.
- **Failure rate** - a native query:

  ```sql
  SELECT template_name,
         SUM(status = 'sent') AS sent,
         SUM(status = 'delivered') AS delivered,
         SUM(status = 'failed') AS failed
  FROM notifications
  GROUP BY template_name
  ```

- **Opt-in funnel** - how many users have `consent_whatsapp = 1`.

## 5. Notes and limits

- The views are plain SQL, so Metabase can use them directly; you can also
  write native questions against the tables.
- The daily eligibility scan (07:30 IST) is what keeps `v_eligible_matches`
  current; a "just published" scheme shows up within a day.
- Never give Metabase the application user's credentials. The read-only user
  exists for exactly this reason.
- Metabase stores its own database in the `metabase-data` volume; back it up
  with the rest of the stack if you care about saved questions.
