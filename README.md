# SHARiK Sales Intelligence Bot

Telegram-first CRM for SHARiK digital. The bot helps a sales manager work cold dental-clinic leads: company cards, decision makers, contacts, touch history, statuses, tasks, AI call prep, CSV import, CRM statistics, export, consultation package, and Bot 2 handoff draft.

The current MVP also includes a dedicated `sales_intelligence` layer for:

- rule-based material scoring
- five closing-criteria readiness checks
- SOPRANO question generation
- AI-or-fallback cold call plan generation
- Russian-localized user-facing sales output for Telegram and API payload text
- Telegram/API/Bot 2/proposals/analytics integrations
- grouped Telegram main menu for faster manual testing

Storage note for the current MVP:

- `CompanyInsightSnapshot` is the universal company-insight storage layer for structured research, sales, and future Bot 2 payloads.
- Snapshot payloads are stored as SQLite-compatible JSON text via `json.dumps` / `json.loads`.
- `sales-intelligence/latest` reads the latest saved `sales_intelligence` insight first.
- If the saved payload is missing or invalid, `sales-intelligence/latest` falls back to on-demand assembly from CRM, enrichment, intelligence, and research context.

Current MVP discovery defaults:

- `Checko HTML` is the primary legal discovery path.
- `Yandex Search API` is the primary real website search path.
- `Camoufox` is optional and lazy-loaded through `BROWSER_BACKEND=camoufox`.
- Smoke scripts stay offline by using fixtures and mock backends.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Set `BOT_TOKEN` in `.env`.

For the new discovery/research MVP also set:

- `LEGAL_DISCOVERY_PROVIDER=checko_html`
- `SEARCH_PROVIDER=yandex`
- `YANDEX_SEARCH_API_KEY`
- `YANDEX_SEARCH_FOLDER_ID`

Optional browser-backed discovery:

- `BROWSER_BACKEND=camoufox`
- `CAMOUFOX_HEADLESS=true`
- `CAMOUFOX_TIMEOUT=20`

Live Checko HTML setup:

- `python -m pip install -U "camoufox[geoip]"`
- `python -m camoufox fetch`
- `BROWSER_BACKEND=camoufox`
- `CHECKO_HTML_ENABLED=true`
- `CHECKO_HTML_HEADLESS=false`
- `CAMOUFOX_HEADLESS=false`

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

## Discovery and Research MVP

The current legal discovery flow is OKVED-first and supports:

- popular OKVED catalog via API and Telegram flow
- Checko HTML preview/import
- Telegram preview length safety with compact rendering capped to 3500 chars
- contact/director mapping into CRM
- optional research queue launch after import

Recommended defaults:

- profile concurrency: `5`
- max concurrency cap: `30`
- keep list pages near-sequential
- treat live Checko/Yandex checks as manual only
- first live Checko run: `CHECKO_HTML_CONCURRENCY=3` and `CHECKO_HTML_MAX_PAGES=1`

### Live Checko validation

- The Checko region tree flow is: open `Все регионы` -> wait for `Регионы и города` -> expand the federal district -> click the region checkbox -> `Готово` -> `Применить`.
- For Saratov the target path is `Приволжский федеральный округ -> 64 Саратовская область`.
- If the numbered region row is not found, the flow falls back to `Быстрый поиск` and selects the first matching checkbox row.
- Telegram preview never sends full HTML/debug JSON; complete diagnostics stay only in `storage/debug/checko/*.json`, `storage/debug/checko/*.html`, `storage/debug/checko/*.txt`, and preview CSV export.

- Start with `limit=5-10`, `CHECKO_HTML_MAX_PAGES=1`, and `CHECKO_HTML_CONCURRENCY=3`.
- Checko list pages do not reliably expose `???` / `????`; requisites are enriched from the company profile page.
- The region filter is applied through the Checko UI modal first and then validated again after parsing, so off-region cards are excluded even if Checko shows them.
- Category-like rows, headers, breadcrumbs, and `Организации 1-50` blocks are skipped before preview.
- Unknown company status is tracked separately and is not counted as inactive.

## Checko Live Debugging

- Enable `CHECKO_HTML_DEBUG=true` to save live list-page diagnostics.
- The default snapshot directory is `CHECKO_HTML_DEBUG_DIR=storage/debug/checko`.
- Each debug run writes `.html`, `.txt`, and `.json` files for the fetched Checko list page.
- The metadata JSON includes requested URL, final URL, title, HTML/text sizes, `/company/` link counts, parser candidate counts, profile-fetch counters, region-UI diagnostics, and captcha/access markers.
- Compare `parser_candidates_count` vs `valid_companies_count` when debugging list/profile validation gaps.

If live preview returns `0` results:

- Check `final_url` to confirm Checko opened the expected list page.
- Check `title` and saved HTML to see whether Checko returned a category page, blank page, or protective page.
- Check how many `/company/` links and parser candidates were detected.
- Try the same OKVED without region to see whether the region post-filter excludes everything.
- Reduce the preview limit and keep `CHECKO_HTML_MAX_PAGES=1`.
- Recheck Camoufox if HTML/text size looks unexpectedly small.

Offline verification commands:

```bash
py scripts/smoke_browser_backend.py
py scripts/smoke_checko_html.py
py scripts/smoke_yandex_search.py
py scripts/smoke_legal_discovery.py
```

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
- `GET /api/companies/{id}/sales-intelligence/material-score`
- `GET /api/companies/{id}/sales-intelligence/closing-criteria`
- `GET /api/companies/{id}/sales-intelligence/soprano-questions`
- `POST /api/companies/{id}/sales-intelligence/cold-call-plan`
- `GET /api/companies/{id}/sales-intelligence/latest`
- `GET /api/companies/{id}/insights`
- `GET /api/companies/{id}/insights/latest`
- `GET /api/companies/{id}/insights/{insight_id}`

`GET /api/companies` supports optional filters:

- `status`
- `city`
- `priority`
- `limit`
- `offset`

Example:

- `GET /api/companies?status=consultation_planned&city=Саратов&priority=high&limit=20`

## Company Insights

`CompanyInsightSnapshot` is a universal storage layer for structured company-level insights. It is intentionally broader than sales intelligence and is designed to support:

- sales intelligence payloads
- website research
- legal / Checko discovery summaries
- social or maps audit payloads
- Bot 2 consultation summaries
- future proposal context and dashboard reads

Each snapshot stores:

- company id and `insight_type`
- optional title and summary
- status such as `success`, `partial`, `failed`, or `on_demand`
- `payload_json` stored as SQLite-safe text
- optional source and version
- created and updated timestamps

Read-only company insights endpoints:

- `GET /api/companies/{id}/insights?insight_type=sales_intelligence&limit=20`
- `GET /api/companies/{id}/insights/latest?insight_type=sales_intelligence`
- `GET /api/companies/{id}/insights/{insight_id}`

The MVP does not expose a public create endpoint. Snapshots are created internally by services.

## Sales Intelligence

The sales intelligence layer still supports the existing on-demand flow, but it now persists successful cold-call-plan generations into `CompanyInsightSnapshot`.

What happens now:

- `POST /api/companies/{id}/sales-intelligence/cold-call-plan` generates the payload and stores a `sales_intelligence` insight snapshot.
- `GET /api/companies/{id}/sales-intelligence/latest` tries to reuse the latest saved snapshot first.
- If the snapshot is absent or its payload is invalid, the API falls back to on-demand assembly and returns `saved_at = null`.
- Bot 2 consultation context follows the same rule: saved snapshot first, on-demand fallback second.

The stored `sales_intelligence` payload currently includes:

- `material_score`
- `closing_criteria`
- `soprano_questions`
- `cold_call_plan`
- `saved_at`

User-facing output notes:

- service enums such as `weak`, `basic`, `normal`, `strong`, `excellent`, `ai`, and `fallback` remain machine-readable
- human-readable explanations, risks, opportunities, SOPRANO questions, and cold-call-plan text are localized to Russian

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
- `sales_intelligence`

The `sales_intelligence` block contains:

- `material_score`
- `closing_criteria`
- `cold_call_plan_summary`
- `soprano_questions`
- `first_offer`
- `risks`
- `generation_mode`

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

## Bot2 API Authorization

Use this header format for Swagger, curl, and any external Bot2 client:

```text
Authorization: Bearer <BOT2_API_KEY>
```

Example:

```bash
curl -H "Authorization: Bearer YOUR_BOT2_API_KEY" \
  http://127.0.0.1:8000/api/bot2/companies/1/consultation-context
```

If the header is wrong, the API returns:

```json
{
  "detail": "Invalid BOT2 API token. Use header: Authorization: Bearer <BOT2_API_KEY>"
}
```

## Telegram Menu Structure

The Telegram main menu is now grouped for daily manager work:

- `🔍 Поиск и импорт`
- `🏢 CRM / Компании`
- `👤 Мои лиды`
- `📞 Продажи`
- `📄 КП и документы`
- `🧠 AI / Research`
- `📊 Аналитика`
- `⚙️ Настройки`
- `🔍 Поиск компаний`

Notes:

- `🔍 Поиск компаний` is the direct entrypoint into the existing legal discovery flow
- the flow remains `источник -> ОКВЭД -> регион -> лимит -> preview -> import`
- if a section is prepared but not fully implemented yet, the bot shows a placeholder instead of failing

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

Search/import workflow:

- open `🔍 Поиск и импорт` for grouped navigation
- use `🔍 Поиск компаний` for legal discovery
- use `📥 Импорт CSV` for bulk import
- use `🔎 Поиск по CRM` for existing cards

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

## Users, Roles and Assignments

This foundation stage adds team-ready CRM users without turning the current MVP into a full RBAC system.

What was added:

- `CRMUser` in `app/modules/crm/models.py`
- lightweight roles: `owner`, `admin`, `manager`, `researcher`, `viewer`
- nullable assignment and audit fields on `Company`, `FollowUpTask`, and `LeadInteraction`
- Telegram-aware auto-create of CRM users
- minimal company self-assignment flow in Telegram
- minimal user and assignment API endpoints
- Bot 2 assignment context block

Auto-create from Telegram:

- the first Telegram user in an empty `crm_users` table becomes `owner`
- next users get `DEFAULT_NEW_USER_ROLE`, default `manager`
- `CRM_OWNER_TELEGRAM_IDS` can pre-elevate selected Telegram IDs to `owner`
- every `/start` updates `last_seen_at`

Assignment behavior in this stage:

- company cards show the currently assigned user compactly
- company cards expose `Назначить на себя`
- company assignment writes an audit note into `LeadInteraction`
- task records support `assigned_user_id` and `created_by_user_id`
- interaction records support `created_by_user_id`

Environment variables:

- `DEFAULT_NEW_USER_ROLE=manager`
- `CRM_AUTO_CREATE_USERS=true`
- `CRM_OWNER_TELEGRAM_IDS=123456789,987654321`

Minimal assignment API:

- `GET /api/users`
- `GET /api/users/{user_id}`
- `PATCH /api/users/{user_id}`

## Known Limitations

- PDF/DOCX export is intentionally not part of this UX pass and will be implemented in the separate `Document Export PDF/DOCX` stage.
- Some Telegram sections currently serve as grouped entrypoints and placeholders rather than full sub-menus.
- Bot2 endpoint protection remains enabled; only docs, Swagger description, and the 401 hint were improved.
- `POST /api/companies/{company_id}/assign`
- `GET /api/users/{user_id}/companies`
- `GET /api/users/{user_id}/tasks`

Bot 2 context now includes:

- `assignment.assigned_user_id`
- `assignment.assigned_user_name`
- `assignment.assigned_user_role`
- `assignment.created_by_user_id`

Smoke check:

```bash
py -3 scripts/smoke_users_roles.py
```

Current limitation:

- this is an MVP foundation layer, not full security or enterprise RBAC
