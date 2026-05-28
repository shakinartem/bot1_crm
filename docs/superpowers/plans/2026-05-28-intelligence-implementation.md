# INN-first Company Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an INN-first legal lookup and website intelligence pipeline with Telegram, API, CRM snapshot, and downstream integrations.

**Architecture:** Introduce a new `intelligence` module and `IntelligenceSnapshot` table, keep `enrichment` as manual website research, and reuse lightweight fetch/signal extraction patterns where appropriate. Wire the latest intelligence snapshot into call prep, scoring, proposals, and Bot 2 context.

**Tech Stack:** FastAPI, aiogram, SQLAlchemy, Alembic, httpx, Pydantic

---

### Task 1: Foundation

**Files:**
- Create: `app/modules/intelligence/*`
- Modify: `app/config.py`, `app/database.py`, `app/modules/crm/models.py`
- Create: `alembic/versions/0006_add_intelligence_snapshots.py`

- [ ] Add intelligence settings, provider abstractions, snapshot model, parser/resolver/service, and migration.
- [ ] Keep all network integrations optional and disabled when credentials are missing.

### Task 2: App Integrations

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/bot.py`
- Modify: `app/modules/crm/keyboards.py`
- Modify: `app/modules/crm/schemas.py`
- Modify: `app/modules/crm/service.py`

- [ ] Add intelligence API endpoints and Telegram workflow.
- [ ] Add Bot 2 context support and company card entry points.

### Task 3: Intelligence Consumers

**Files:**
- Modify: `app/modules/ai/prompts.py`, `app/modules/ai/service.py`
- Modify: `app/modules/proposals/service.py`
- Modify: `app/modules/analytics/service.py`, `app/modules/analytics/scoring.py`

- [ ] Feed latest intelligence into call prep, proposal suggestions, and scoring while keeping enrichment support intact.

### Task 4: Verification and Docs

**Files:**
- Create: `scripts/smoke_intelligence.py`
- Modify: `README.md`, `TASKS.md`, `CHANGELOG.md`

- [ ] Add mock-provider smoke coverage.
- [ ] Run compile, smoke checks, and Alembic upgrade.
