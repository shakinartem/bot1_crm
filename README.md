# SHARiK Sales Intelligence Bot

Telegram-first CRM for SHARiK digital. The bot helps a sales manager work cold dental-clinic leads: company cards, decision makers, contacts, touch history, statuses, tasks, AI call prep, CSV import, CRM statistics, export, consultation package, and Bot 2 handoff draft.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Set `BOT_TOKEN` in `.env`.

## Run

API:

```bash
uvicorn app.main:app --reload
```

Telegram bot:

```bash
python -m app.bot
```

Docker:

```bash
docker compose up --build
```

## Migrations

```bash
alembic upgrade head
```

For local MVP startup the app also creates tables automatically, but schema changes should still go through Alembic.

## CRM Core

Main entities:

- `Company` — clinic or company card.
- `DecisionMaker` — decision maker / LPR.
- `ContactPoint` — phone, email, website, Telegram, WhatsApp, VK, Instagram, or other contact.
- `LeadInteraction` — call, message, email, meeting, consultation, proposal, or note.
- `FollowUpTask` — manager follow-up task.
- `CallRecord` — uploaded call record and future transcript/summary.

## API

Health:

- `GET /health`
- `GET /api/health`

CRM:

- `GET /api/companies`
- `POST /api/companies`
- `GET /api/companies/export`
- `GET /api/companies/{id}`
- `PATCH /api/companies/{id}`
- `DELETE /api/companies/{id}`
- `GET /api/companies/{id}/interactions`
- `POST /api/companies/{id}/interactions`
- `GET /api/companies/{id}/decision-makers`
- `POST /api/companies/{id}/decision-makers`
- `GET /api/tasks`
- `POST /api/tasks`
- `PATCH /api/tasks/{id}`
- `POST /api/imports/csv`
- `POST /api/imports/csv/preview`
- `POST /api/imports/csv/commit`
- `POST /api/companies/{id}/ai/call-prep`

`GET /api/companies` supports optional filters:

- `status`
- `city`
- `priority`
- `limit`
- `offset`

Example:

- `GET /api/companies?status=consultation_planned&city=Саратов&priority=high&limit=20`

## Bot 2 handoff API

Preferred endpoints for SHARiK digital Consultation AI:

- `GET /api/bot2/consultation-ready`
- `POST /api/bot2/companies/{company_id}/consultation-result`

`GET /api/bot2/consultation-ready` returns companies with status `consultation_planned`.

`POST /api/bot2/companies/{company_id}/consultation-result` accepts:

```json
{
  "result": "thinking",
  "summary": "Клиника хочет обсудить договор после консультации",
  "source": "bot2"
}
```

`BOT2_API_TOKEN` controls auth only for `/api/bot2/*`:

- empty `BOT2_API_TOKEN` => dev mode, no auth required
- non-empty `BOT2_API_TOKEN` => send `Authorization: Bearer <BOT2_API_TOKEN>`

Status mapping for Bot 2 handoff:

- `consultation_planned` -> company is ready for BOT 2
- `refused` -> `deal_lost`
- `thinking` -> `interested`
- `contract_sent` -> `proposal_sent`
- `signed` -> `deal_won`

Side effects:

- always creates `LeadInteraction` with `type=consultation`
- `thinking` also creates task `Повторно связаться после консультации` for `now + 3 days`
- `contract_sent` also creates task `Проверить статус договора` for `now + 2 days`

## AI Providers

Switch with `AI_PROVIDER`:

- `fallback` — local safe fallback response without external AI calls.
- `openrouter` — OpenRouter Chat Completions, requires `OPENROUTER_API_KEY`.
- `ollama` — local Ollama API, configure `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.

If no provider is configured, the bot and API do not fail: fallback templates are used for call prep and mini-audit draft.

## CSV Import

Supported canonical columns:

```text
name,legal_name,inn,ogrn,city,region,address,phone,website,social_links,maps_url,vk_url,instagram_url,telegram_url,rating,reviews_count,source,notes
```

Highlights:

- Preview before commit in Telegram and API.
- Header mapping for Russian and English column names.
- UTF-8 and Windows-1251 decoding.
- Delimiter detection for comma, semicolon, and tab.
- Deduplication by `inn`, `ogrn`, normalized `phone`, normalized `website`, and normalized `name + city`.
- Import modes: skip duplicates or update existing cards.

Telegram flow:

- Press `Импорт CSV`.
- Upload the CSV as a document.
- Review preview, mapping, and counters.
- Confirm import in `skip` or `update` mode.

API flow:

- `POST /api/imports/csv?mode=preview`
- `POST /api/imports/csv?mode=commit&import_mode=skip`

## Export

Use the Telegram main menu button `📤 Экспорт`.

Available filters:

- all companies
- new leads
- interested
- consultation planned
- proposal sent
- deals
- city
- source
- priority

Files are saved to `storage/exports/`.

Examples:

- `GET /api/companies/export?status=interested`
- `GET /api/companies/export?city=Уфа`
- `GET /api/companies/export?priority=high`

## Manager Daily Digest

Use the Telegram main menu button `🗓 План дня` or the commands:

- `/daily`
- `/week`
- `/overdue`
- `/hot`
- `/stale`

The daily digest shows:

- overdue tasks
- tasks due today
- hot leads
- stale leads without recent touchpoints
- yesterday activity summary
- AI or rule-based recommendation for the manager

Hot leads are prioritized when at least one condition matches:

- company status is `interested`, `consultation_planned`, or `proposal_sent`
- company priority is `high`
- there is an overdue task or a task due today
- the latest interaction result is interest/callback/consultation/proposal related

Stale leads are companies that are not closed or blocked and have no touchpoints for N days, or no touchpoints at all.

Overdue and today task screens support:

- open company
- complete task
- snooze task to tomorrow, in two hours, or a custom `DD.MM.YYYY HH:MM`

Weekly summary shows 7-day sales activity, completed tasks, new companies, and the recommended next focus.

Automatic morning digest is available with a lightweight in-process scheduler inside the Telegram bot. Settings are available from `⚙️ Настройки дайджеста`:

- enable or disable auto-digest
- change send time
- change stale lead period

API endpoints:

- `GET /api/digest/daily`
- `GET /api/digest/weekly`
- `GET /api/digest/overdue-tasks`
- `GET /api/digest/today-tasks`
- `GET /api/digest/hot-leads`
- `GET /api/digest/stale-leads`

## Smoke Checks

Basic repo smoke check:

```bash
python scripts/smoke_check.py
```

Bot 2 handoff smoke check:

```bash
python scripts/smoke_bot2_handoff.py
```

It verifies:

- test company with `consultation_planned`
- `GET /api/bot2/consultation-ready`
- `POST /api/bot2/companies/{id}/consultation-result`
- company status update to `interested`
- consultation interaction creation
- follow-up task creation

Export CSV includes:

- company core fields
- status and priority
- source and notes
- aggregated decision makers and contacts
- last interaction date/result
- next open task title/date
- created/updated timestamps

## Consultation Package

Open a company card and choose `📦 Пакет консультации`.

The package includes:

- clinic data
- decision makers
- contacts
- recent interactions
- current sales status and next task
- manager notes
- AI call prep
- recommended next step
- latest mini-audit / proposal draft if available

From the package screen the manager can:

- generate a mini-audit
- prepare Bot 2 handoff draft
- export the company as Markdown

Single-company package files are saved as:

- `storage/exports/company_{id}_consultation_package_YYYYMMDD_HHMMSS.md`

## Mini Audit Draft

Use `🤖 Сгенерировать мини-аудит` inside the consultation package flow.

How it works:

- The bot builds context from company data, city, website, notes, and recent interactions.
- It sends the prompt to the active AI provider.
- If AI is unavailable, it falls back to a cautious local template.
- The generated draft is saved to company history as a proposal interaction.
- The manager can re-open the text, export it to `.txt`, or use it as part of the consultation package.

The draft intentionally avoids invented precision. When data is limited, it uses cautious phrasing such as “По имеющимся данным можно предположить...” and “Для точной оценки нужно проверить...”.

## Basic Telegram Scenarios

1. Add a company: `/new_company Название; телефон; сайт; город; заметки`
2. Open companies list: `/leads`
3. Open company card: `/company 1`
4. Prepare a cold call: `/prepare_call 1`
5. Upload a call recording with caption `call:1`
6. Save call result: `/call_result 1; назначена консультация`

## Project Docs

- `PROJECT_CONTEXT.md` — product and architecture context.
- `TASKS.md` — current sprint and backlog.
- `CHANGELOG.md` — change log.

## Final Local Check With Bot 2

1. Start BOT 1:

```bash
uvicorn app.main:app --reload --port 8000
```

2. Create or keep a company with status `consultation_planned`.

3. Start BOT 2 with:

```bash
CRM_ADAPTER=http_api
CRM_API_BASE_URL=http://localhost:8000
CRM_API_TOKEN=<BOT2_API_TOKEN if enabled>
uvicorn app.main:app --reload --port 8002
```

4. In BOT 2 Telegram:

- open `Клиенты на консультацию`
- confirm the company from BOT 1 is visible
- open the card
- generate audit
- generate DOCX
- set result `Думает` or `Договор отправлен`

5. In BOT 1 verify company status, interaction, and follow-up task were updated.
