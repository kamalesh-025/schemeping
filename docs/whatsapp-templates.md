# WhatsApp template approval pack (Phase 5)

These are the five pre-approved templates SchemePing uses. Business-initiated
WhatsApp messages must match an approved template exactly; sending anything
else outside the 24-hour customer-service window is rejected by the provider.

All texts are mirrored in `backend/app/services/messaging.py`
(`WHATSAPP_TEMPLATES`). Meta Cloud API sends the named template with the
recipient's language and ordered body parameters. The optional MSG91 provider
maps the same names to provider template IDs.

## 1. scheme_summary (utility)

Trigger: user taps "Send to WhatsApp" on a scheme detail page.
Not governed by notification preferences (the user asked for it).
Rate limited to `SEND_WHATSAPP_HOURLY_LIMIT` (default 10/hour/user).

Variables (in order):
1. `scheme_name`
2. `benefit`
3. `eligibility_line`
4. `documents`
5. `deadline`
6. `facility_name`
7. `closing_line`

Sample:

```
Scheme: {{scheme_name}}
Benefit: {{benefit}}
Eligibility: {{eligibility_line}}
Documents Needed: {{documents}}
Apply Before: {{deadline}}
Nearest Center: {{facility_name}}
{{closing_line}}
```

The closing line is fixed product copy per language:

| Language | Text |
|---|---|
| en | For full details visit SchemePing. |
| ta | முழு விவரங்களுக்கு SchemePing பார்க்கவும். |
| hi | पूरी जानकारी के लिए SchemePing देखें। |
| te | పూర్తి వివరాలకు SchemePing చూడండి. |
| kn | ಪೂರ್ತಿ ವಿವರಗಳಿಗೆ SchemePing ನೋಡಿ. |
| ml | മുഴുവൻ വിവരങ്ങൾക്ക് SchemePing കാണുക. |

## 2. new_scheme_eligible (utility, prefs: new_schemes)

Trigger: the daily scan finds a newly published scheme that someone is now
eligible for.

Variables: `person_name_line`, `scheme_name`, `benefit`, `deadline_line`

Sample:

```
Good news{{person_name_line}}: you are eligible for {{scheme_name}}.
Benefit: {{benefit}}
{{deadline_line}}
Open SchemePing for details and documents.
```

## 3. family_milestone (utility, prefs: family_milestones)

Trigger: a birthday (18th, 60th) or status change makes a family member newly
eligible.

Variables: `person_name`, `milestone_line`, `scheme_name`, `benefit`

Sample:

```
{{person_name}} has become eligible for {{scheme_name}} because {{milestone_line}}.
Benefit: {{benefit}}
Open SchemePing for details and documents.
```

## 4. deadline_reminder (utility, prefs: deadlines)

Trigger: deadline in 7 / 3 / 1 days for a scheme the person qualifies for.
Sent daily at 10:00 IST by Celery Beat.

Variables: `scheme_name`, `job_name`, `days_left`, `deadline_line`

Sample:

```
Reminder: {{job_name}} is eligible for {{scheme_name}}.
{{days_left}}
{{deadline_line}}
Open SchemePing to apply.
```

## 5. festival_benefit (marketing, prefs: festival)

Trigger: an admin publishes a festival-window benefit scheme.
India rate note: marketing templates cost ~₹0.8631 per delivered message;
the other four are ~₹0.115 utility.

Variables: `greeting`, `scheme_name`, `benefit`, `deadline_line`

Sample:

```
{{greeting}}
You are eligible for {{scheme_name}} this season.
Benefit: {{benefit}}
{{deadline_line}}
```

## Configuration checklist (Meta Cloud API)

1. Create a Meta developer app and add WhatsApp Cloud API. Add the business
   phone number and, for initial tests, register the recipient as a permitted
   test number if the app is still in development mode.
2. Create and get approval for the five templates above in WhatsApp Manager,
   with the exact names, body text, variable order, and language versions.
   SchemePing sends the recipient's selected language (`en_US`, `ta`, `hi`,
   `te`, `kn`, or `ml`); Meta must have that language version approved.
3. Create a long-lived access token with the `whatsapp_business_messaging`
   permission and note the phone number ID from the WhatsApp API setup.
4. Set `WHATSAPP_PROVIDER=meta`, `META_WHATSAPP_PHONE_NUMBER_ID`,
   `META_WHATSAPP_ACCESS_TOKEN`, `META_WHATSAPP_API_VERSION`,
   `META_WHATSAPP_VERIFY_TOKEN`, and `META_WHATSAPP_APP_SECRET` in the
   untracked root `.env`. Never put these credentials in frontend variables.
5. Make the API reachable over public HTTPS, then configure the Meta webhook
   callback at `/api/v1/notifications/webhook` with the verify token, and
   subscribe to WhatsApp message status updates. Callback signatures are
   checked with `META_WHATSAPP_APP_SECRET` and Meta's `X-Hub-Signature-256`.
6. Restart the API and worker with
   `docker compose up -d --build api worker`. Confirm the worker is running;
   it consumes queued send jobs. Start `beat` for scheduled notifications.
7. In SchemePing, explicitly opt in to WhatsApp in Settings. The scheme-summary
   action then queues a send; check `docker compose logs -f worker` and the
   notification status if delivery does not complete.
8. To use the optional MSG91 provider instead, set
   `WHATSAPP_PROVIDER=msg91`, configure the approved template IDs in
   `MSG91_WHATSAPP_TEMPLATE_IDS`, and set `MSG91_WHATSAPP_NUMBER` and
   `MSG91_AUTH_KEY`.
9. Keep `WHATSAPP_PROVIDER=mock` or `log` in development: neither contacts
   a network and no template approval is needed there. The scheme detail page
   also provides a user-initiated `wa.me` share link as a free fallback.
10. Quiet hours (21:00–08:00 IST) hold the proactive categories; held
   messages are released at 08:00 IST.

The defaults are intentionally non-delivering: `WHATSAPP_PROVIDER=mock`
records a simulated send, and `MESSAGING_PROVIDER=log` prints OTP codes to
the backend console. The `wa.me` fallback opens WhatsApp for the user to send
the message themselves; it does not use SchemePing's business API.
