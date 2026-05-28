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
- `GET /api/bot2/companies/{company_id}/consultation-context`
- `POST /api/bot2/companies/{company_id}/consultation-result`

`GET /api/bot2/consultation-ready` returns companies with status `consultation_planned`.

`GET /api/bot2/companies/{company_id}/consultation-context` returns the structured sales context used by BOT 2 for audit and proposal generation. The payload includes:

- `company`
- `decision_makers`
- `contacts`
- `recent_interactions`
- `open_tasks`
- `latest_proposal`
- `latest_call_result`
- `recommended_next_step`
- `sales_summary`

Example response shape:

```json
{
  "company": {
    "id": 42,
    "name": "Клиника Улыбка",
    "city": "Саратов",
    "status": "consultation_planned",
    "priority": "high"
  },
  "decision_makers": [
    {
      "id": 7,
      "full_name": "Анна Иванова",
      "role": "Владелец",
      "is_primary": true
    }
  ],
  "contacts": [
    {
      "id": 12,
      "type": "telegram",
      "value": "@clinic_owner",
      "is_primary": true
    }
  ],
  "recent_interactions": [],
  "open_tasks": [],
  "latest_proposal": null,
  "latest_call_result": null,
  "recommended_next_step": "Провести консультацию и уточнить узкое место digital-воронки.",
  "sales_summary": "Источник: cold_base. Статус: consultation_planned."
}
```

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
- persist settings per Telegram user in the `digest_settings` table

API endpoints:

- `GET /api/digest/daily`
- `GET /api/digest/weekly`
- `GET /api/digest/overdue-tasks`
- `GET /api/digest/today-tasks`
- `GET /api/digest/hot-leads`
- `GET /api/digest/stale-leads`

## Proposals and Contract Drafts

Use the company card button `📄 КП / Договор` to open the proposal workspace.

What is available:

- service package suggestion based on company card, notes, interactions, and current status
- manual package selection with Telegram inline checkboxes
- commercial proposal draft generation
- contract draft structure generation
- service appendix generation
- proposal and contract file history with re-send from Telegram
- markdown export in `storage/proposals/`

Legal note:

- contract drafts are not final legal documents
- every contract draft must be reviewed by a lawyer and completed manually with requisites and exact terms

API endpoints:

- `GET /api/proposals/packages`
- `POST /api/companies/{id}/proposals/suggest-packages`
- `POST /api/companies/{id}/proposals/generate`
- `POST /api/companies/{id}/contracts/draft`
- `POST /api/companies/{id}/contracts/service-appendix`
- `GET /api/companies/{id}/proposals/history`
- `GET /api/companies/{id}/proposals/{proposal_id}/file`

Smoke check:

```bash
python scripts/smoke_proposals.py
```

## Lead Analytics and Scoring

Use the Telegram main menu button `📈 Аналитика` to open CRM analytics.

What is available:

- CRM funnel analytics by current statuses
- lead source analytics grouped by `company.source`
- city and region analytics with stale lead and overdue task signals
- rule-based lead scoring with `cold`, `warm`, `hot`, and `priority` grades
- hot lead and cold base screens in Telegram
- score block inside company cards
- scoring-aware daily digest prioritization
- analytics CSV export to `storage/exports/analytics/`

API endpoints:

- `GET /api/analytics/funnel`
- `GET /api/analytics/sources`
- `GET /api/analytics/cities`
- `GET /api/analytics/scores`
- `GET /api/analytics/cold-base`
- `GET /api/companies/{id}/score`
- `GET /api/analytics/export?type=funnel`
- `GET /api/analytics/export?type=sources`
- `GET /api/analytics/export?type=cities`
- `GET /api/analytics/export?type=scores`
- `GET /api/analytics/export?type=cold_base`

Score highlights:

- base signals: site, phone, city, LPR, notes/history
- status contribution: `new` to `proposal_sent`, with hard stops for `deal_lost` and `do_not_contact`
- task urgency: today/overdue follow-up boosts priority for warm and hot leads
- freshness: recent touchpoints help, stale leads lose score
- next-best-action recommendation is returned for every lead

Smoke check:

```bash
python scripts/smoke_analytics.py
```

## Website and Social Research Enrichment

Use the company card button `🔎 Research` to open website and social research enrichment.

What is available:

- lightweight single-page website check via `httpx`
- manual website input when the company card has no website
- detection of socials, contacts, maps/platforms, and basic website signals
- cautious rule-based hypotheses about the digital funnel
- optional AI summary on top of the rule-based snapshot
- enrichment snapshot history stored per company
- reuse of enrichment in AI call prep, package suggestion, scoring, and Bot 2 consultation context

Research menu actions:

- `🌐 Проверить сайт`
- `✍️ Ввести сайт вручную`
- `📌 Последний research`
- `📜 История research`
- `🤖 AI-резюме`

Signals include:

- online booking
- callback form
- prices
- doctors page
- reviews section
- contacts page
- social links
- messenger links
- privacy policy
- promotions
- implantation, orthodontics, children dentistry, and emergency keywords

API endpoints:

- `POST /api/companies/{company_id}/enrichment/website`
- `GET /api/companies/{company_id}/enrichment/latest`
- `GET /api/companies/{company_id}/enrichment/history`
- `GET /api/companies/{company_id}/enrichment/{snapshot_id}`

Smoke check:

```bash
python scripts/smoke_enrichment.py
```

Limitations:

- lightweight single-page fetch only
- no Selenium or Playwright
- no aggressive scraping or crawl
- no anti-bot bypass
- no guarantees or hard conclusions when data is limited
- all findings are framed as cautious hypotheses for manager research

## INN-first Company Intelligence

Use the company card button `🧾 INN / Intelligence` to launch the legal-first enrichment pipeline.

What it does:

- starts from `ИНН`, or finds a likely legal entity by company name and city
- enriches legal fields such as `legal_name`, `inn`, `ogrn`, address, status, and `okved`
- resolves a likely official website through a pluggable search provider
- fetches only the main page with lightweight `httpx`
- extracts contacts, socials, maps links, and website signals
- stores an `IntelligenceSnapshot` in CRM and reuses it in call prep, proposals, scoring, and Bot 2 context

Providers:

- legal lookup: `mock`, `api_fns`, `dadata`
- search: `mock`, `yandex_search`, `google_search`

Recommended env variables:

```text
LEGAL_PROVIDER=mock
SEARCH_PROVIDER=mock
API_FNS_KEY=
API_FNS_BASE_URL=https://api-fns.ru/api
DADATA_TOKEN=
DADATA_SECRET=
YANDEX_SEARCH_API_KEY=
YANDEX_SEARCH_FOLDER_ID=
GOOGLE_SEARCH_API_KEY=
GOOGLE_SEARCH_ENGINE_ID=
INTELLIGENCE_REQUEST_TIMEOUT=10
INTELLIGENCE_SEARCH_LIMIT=10
```

Telegram workflow:

- `🔎 Найти ИНН по названию`
- `🧾 Проверить по ИНН`
- `🌐 Найти сайт по ИНН`
- `🌐 Найти сайт по юр. названию`
- `🧠 Полное обогащение`
- `📌 Последний результат`
- `📜 История`

API endpoints:

- `POST /api/companies/{company_id}/intelligence/enrich`
- `POST /api/companies/{company_id}/intelligence/find-legal`
- `POST /api/companies/{company_id}/intelligence/resolve-website`
- `GET /api/companies/{company_id}/intelligence/latest`
- `GET /api/companies/{company_id}/intelligence/history`
- `GET /api/companies/{company_id}/intelligence/{snapshot_id}`

Smoke check:

```bash
python scripts/smoke_intelligence.py
```

Limitations:

- no aggressive scraping
- no Selenium or Playwright
- real web search requires configured search APIs
- official site matching is confidence-based and may still need manager review
- a website may not publish INN directly

## Smoke Checks

Basic repo smoke check:

```bash
python scripts/smoke_check.py
```

Bot 2 handoff smoke check:

```bash
python scripts/smoke_bot2_handoff.py
```

Bot 2 consultation context smoke check:

```bash
python scripts/smoke_bot2_context.py
```

Digest module smoke test:

```bash
python scripts/test_digest_module.py
```

It verifies:

- test company with `consultation_planned`
- `GET /api/bot2/consultation-ready`
- `POST /api/bot2/companies/{id}/consultation-result`
- company status update to `interested`
- consultation interaction creation
- follow-up task creation

Consultation context smoke verifies:

- company creation
- decision maker creation
- contact creation
- call interaction
- proposal interaction
- open task
- `GET /api/bot2/companies/{id}/consultation-context`
- auth via `BOT2_API_TOKEN`
- required response blocks for BOT 2

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
- generate proposal
- generate DOCX
- set result `Думает` or `Договор отправлен`

5. In BOT 1 verify company status, interaction, and follow-up task were updated.

## Docker Future / Local Compose Notes

Dev files in this repo:

- `Dockerfile.dev`
- `.dockerignore`

The local 2-bot compose example lives in the BOT 2 repository at `docker/docker-compose.dev.yml`. Right now it is intended to start only:

- `bot1-crm`
- `bot2-consultation`

Future placeholders for `bot3-content`, `bot4-autoposter`, and `bot5-reporter` are documented there but are not active yet.

Inside Docker networking, BOT 2 should call BOT 1 with:

```text
http://bot1-crm:8000
```

The MVP still uses SQLite. PostgreSQL and Redis can be introduced later for production orchestration.

## FNS-first Discovery and Safe Browser Research

This stage adds a legal-first pipeline:

1. discover companies from a legal provider by niche and city;
2. review a preview with duplicate and weak-data flags;
3. import only after explicit confirmation;
4. create queued research jobs for safe public-web enrichment.

Included in MVP:

- `legal_discovery` preview/import workflow
- mock legal discovery provider for local development and smoke tests
- `research_queue` with deduplicated `ResearchJob` records
- safe `httpx` fetch backend for public HTML pages
- disabled-by-default browser backend abstraction
- website resolution by INN / legal name
- site parsing for contacts, socials, messengers, and website signals
- Telegram callbacks for discovery and research queue launch
- API endpoints for discovery, queue control, and company research
- CLI script: `scripts/run_research_batch.py`
- smoke tests: `scripts/smoke_legal_discovery.py`, `scripts/smoke_research_queue.py`

Key env variables:

- `LEGAL_DISCOVERY_PROVIDER=mock`
- `LEGAL_DISCOVERY_DEFAULT_LIMIT=50`
- `LEGAL_DISCOVERY_REQUEST_TIMEOUT=10`
- `RESEARCH_FETCH_BACKEND=httpx`
- `RESEARCH_BROWSER_BACKEND=disabled`
- `RESEARCH_CONCURRENCY=5`
- `RESEARCH_REQUEST_TIMEOUT=10`
- `RESEARCH_REQUEST_DELAY_MS=500`
- `RESEARCH_MAX_PAGES_PER_SITE=3`
- `RESEARCH_MAX_HTML_CHARS=300000`

Safety and limitations:

- no captcha, login, paywall, or anti-bot bypass
- no aggressive crawling
- no search-engine HTML scraping by hand
- browser rendering is only an optional future abstraction
- if a site is blocked or confidence is low, the result goes to manual review
