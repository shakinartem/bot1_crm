# Company Insights Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a universal `CompanyInsightSnapshot` storage layer, persist sales intelligence into it without breaking on-demand fallback, and expose read-only company insights API plus smoke coverage.

**Architecture:** Introduce a generic company insight model stored as SQLite-compatible JSON text, wrap it with a focused insights service, and make `sales_intelligence` plus Bot2 read saved snapshots first before falling back to existing on-demand assembly. Keep migration, API, docs, and smoke checks aligned with current project patterns.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, Alembic, SQLite, existing smoke scripts

---

### Task 1: Add insight snapshot coverage

**Files:**
- Create: `scripts/smoke_company_insights.py`
- Modify: `scripts/smoke_call_plan.py`
- Modify: `scripts/smoke_bot2_context.py`

- [ ] Add offline smoke expectations for generic insights CRUD-style reads and saved sales-intelligence fallback behavior.
- [ ] Verify the new smoke expectations fail or are impossible before implementation.

### Task 2: Implement insight persistence layer

**Files:**
- Modify: `app/modules/crm/models.py`
- Create: `app/modules/insights/__init__.py`
- Create: `app/modules/insights/schemas.py`
- Create: `app/modules/insights/service.py`
- Modify: `app/database.py`
- Create: `alembic/versions/0008_add_company_insight_snapshots.py`

- [ ] Add `CompanyInsightSnapshot` ORM model and relationship from `Company`.
- [ ] Add JSON-text-safe insight schemas and service helpers for create/latest/history/by-id/payload-load.
- [ ] Add Alembic migration with SQLite-safe text payload storage and indexes.

### Task 3: Integrate sales intelligence and Bot2

**Files:**
- Modify: `app/modules/sales_intelligence/service.py`
- Modify: `app/modules/crm/service.py`

- [ ] Save aggregated sales-intelligence payload after successful `generate_cold_call_plan()`.
- [ ] Read `sales_intelligence` from the latest saved company insight before on-demand fallback.
- [ ] Keep `LeadInteraction` notes short and avoid storing full call plans.
- [ ] Make Bot2 consume saved snapshot first and fall back safely when missing or invalid.

### Task 4: Expose read-only API and update docs

**Files:**
- Modify: `app/api/routes.py`
- Modify: `README.md`
- Modify: `TASKS.md`
- Modify: `CHANGELOG.md`

- [ ] Add read-only company insights API endpoints.
- [ ] Document the new universal insights layer, fallback behavior, and endpoint surface.

### Task 5: Normalize targeted generated sources and verify

**Files:**
- Modify only targeted files under `app/modules/sales_intelligence/`, `app/modules/legal_discovery/`, `app/modules/research/`, and listed smoke scripts as needed

- [ ] Normalize one-line/generated Python formatting only where required for touched files.
- [ ] Run compile and required smoke checks.
