# Website / Social Research Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the approved website/social research enrichment module, persist enrichment snapshots, and integrate enrichment into Telegram, API, AI prep, proposals, scoring, and Bot 2 context without breaking existing flows.

**Architecture:** Implement enrichment as a standalone module with a single orchestration service, then wire it into existing CRM and analytics/proposals entry points through additive context builders and lightweight UI/API endpoints. Keep fetch single-page and safe via `httpx`, store parsed JSON in text columns for SQLite compatibility, and make AI optional on top of a rule-based core.

**Tech Stack:** Python, FastAPI, aiogram, SQLAlchemy async, Alembic, Pydantic, httpx, SQLite-compatible JSON-as-text storage.

---

### Task 1: Add the enrichment data model and migration

**Files:**
- Create: `app/modules/enrichment/models.py`
- Create: `alembic/versions/0005_add_enrichment_snapshots.py`
- Modify: `app/modules/crm/models.py`
- Modify: `app/database.py`

- [ ] Define `EnrichmentSnapshot` with the spec fields and a relationship back to `Company`.
- [ ] Add `Company.enrichment_snapshots` with cascade settings matching the existing child entities.
- [ ] Register the model in `create_db_schema()` so local startup and smoke tests can create the table.
- [ ] Add Alembic migration `0005_add_enrichment_snapshots.py` with indexes for `company_id`, `status`, and `fetched_at`.

### Task 2: Add enrichment DTOs and JSON parsing helpers

**Files:**
- Create: `app/modules/enrichment/schemas.py`
- Modify: `app/modules/crm/schemas.py`

- [ ] Create DTOs for fetch results, website analysis, enrichment requests, parsed snapshot reads, API result payloads, and Bot 2 enrichment context.
- [ ] Add safe JSON parse and dump helpers so the service and API never return raw JSON strings.
- [ ] Extend `Bot2ConsultationContextRead` with an optional additive `enrichment` field.

### Task 3: Implement safe website fetching

**Files:**
- Create: `app/modules/enrichment/fetcher.py`

- [ ] Implement URL normalization with whitespace trimming and automatic `https://` prefixing when scheme is missing.
- [ ] Implement `fetch_website()` using `httpx.AsyncClient`, 10-second timeout, redirects, user-agent, and a 300000-character HTML cap.
- [ ] Return structured failure results for invalid URL, timeout, connection issues, non-HTML content, and HTTP 400+.

### Task 4: Implement website analysis and hypotheses

**Files:**
- Create: `app/modules/enrichment/analyzer.py`

- [ ] Implement HTML text extraction for title, meta description, cleaned excerpt, links, socials, maps, contacts, and boolean signals from the spec.
- [ ] Implement rule-based hypotheses with cautious phrasing only.
- [ ] Keep the parser lightweight and single-page only, using stdlib parsing and regexes instead of scraping dependencies.

### Task 5: Implement prompts and enrichment service

**Files:**
- Create: `app/modules/enrichment/prompts.py`
- Create: `app/modules/enrichment/service.py`

- [ ] Add the AI prompt builder for enrichment summary plus a fallback summary builder.
- [ ] Implement `enrich_company_website()`, `get_latest_enrichment()`, `get_enrichment_history()`, `get_enrichment_snapshot()`, and `build_enrichment_context_for_company()`.
- [ ] Make the service update `company.website` only when manual input succeeded and the website was previously empty.
- [ ] Log a note interaction after successful or partial research completion.

### Task 6: Integrate enrichment into call prep, proposals, scoring, and Bot 2 context

**Files:**
- Modify: `app/modules/ai/service.py`
- Modify: `app/modules/ai/prompts.py`
- Modify: `app/modules/proposals/service.py`
- Modify: `app/modules/analytics/scoring.py`
- Modify: `app/modules/analytics/service.py`
- Modify: `app/modules/crm/service.py`

- [ ] Inject latest enrichment context into AI call prep.
- [ ] Add enrichment-aware package suggestion signals to proposals.
- [ ] Extend scoring context and scoring reasons/risks with enrichment rules from the spec.
- [ ] Extend Bot 2 consultation context with the additive `enrichment` block.
- [ ] Keep all changes backward-compatible when no enrichment snapshot exists.

### Task 7: Add CRM card and Telegram Research workflow

**Files:**
- Create: `app/modules/enrichment/keyboards.py`
- Create: `app/modules/enrichment/handlers.py`
- Modify: `app/modules/crm/keyboards.py`
- Modify: `app/modules/crm/handlers.py`
- Modify: `app/modules/crm/service.py`
- Modify: `app/bot.py`

- [ ] Add a compact research block to the company card text.
- [ ] Add the `🔎 Research` company-card action and the research menu.
- [ ] Implement callbacks and FSM for check website, manual website input, latest snapshot, history, snapshot detail, and AI summary.
- [ ] Keep default Telegram research rule-based and let AI summary be an explicit follow-up action.

### Task 8: Add enrichment API endpoints

**Files:**
- Modify: `app/api/routes.py`

- [ ] Add `POST /api/companies/{company_id}/enrichment/website`.
- [ ] Add `GET /api/companies/{company_id}/enrichment/latest`.
- [ ] Add `GET /api/companies/{company_id}/enrichment/history`.
- [ ] Add `GET /api/companies/{company_id}/enrichment/{snapshot_id}`.
- [ ] Return parsed JSON structures and 404s where appropriate.

### Task 9: Add smoke_enrichment and docs updates

**Files:**
- Create: `scripts/smoke_enrichment.py`
- Modify: `README.md`
- Modify: `TASKS.md`
- Modify: `CHANGELOG.md`

- [ ] Add an offline smoke test using sample HTML or monkeypatched fetching.
- [ ] Verify analyzer output, snapshot persistence, enrichment endpoints, and Bot 2 consultation context enrichment block.
- [ ] Update docs and sprint/changelog entries per the approved spec.

### Task 10: Verify end-to-end and commit

**Files:**
- Verify only

- [ ] Run `python -m compileall app alembic`.
- [ ] Run `python scripts/smoke_check.py`.
- [ ] Run `python scripts/test_csv_import.py`.
- [ ] Run `python scripts/smoke_bot2_handoff.py`.
- [ ] Run `python scripts/test_digest_module.py`.
- [ ] Run `python scripts/smoke_proposals.py`.
- [ ] Run `python scripts/smoke_analytics.py`.
- [ ] Run `python scripts/smoke_bot2_context.py`.
- [ ] Run `python scripts/smoke_enrichment.py`.
- [ ] Run `python -c "from app.main import app; print(app.title)"`.
- [ ] Run `python -c "from app.bot import main; print('bot ok')"`.
- [ ] Run `alembic upgrade head`.
- [ ] Review `git diff`, commit the implementation, and report the SHA.
