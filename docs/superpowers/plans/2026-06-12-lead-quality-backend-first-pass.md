# Lead Quality Backend First Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend-first lead quality pipeline with website research foundation, post-import lead fit scoring, soft delete, admin reset, touch-plan services, API endpoints, smoke checks, and docs.

**Architecture:** Extend the CRM data model with nullable lead-fit and soft-delete fields for fast filtering, while storing detailed website and lead-fit payloads in `CompanyInsightSnapshot`. Add focused foundation modules for phone parsing, website resolution, lead fit scoring, touch-plan orchestration, and admin reset, then wire them into import, legal discovery, API, and smoke scripts.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, Pydantic, httpx, existing CRM/research/intelligence modules, smoke scripts.

---

### Task 1: Data Model And Migrations

**Files:**
- Modify: `app/modules/crm/models.py`
- Modify: `app/modules/crm/schemas.py`
- Modify: `app/modules/crm/constants.py`
- Create: `alembic/versions/0010_add_lead_fit_soft_delete_and_touch_fields.py`

- [ ] Add company lead-fit and soft-delete fields plus touch-stage support.
- [ ] Add Alembic migration for new nullable columns and indexes.
- [ ] Expose new fields in read schemas only where safe.

### Task 2: Research Foundation

**Files:**
- Create: `app/modules/research/phone_parser.py`
- Create: `app/modules/research/website_resolver.py`
- Modify: `app/config.py`
- Modify: `app/modules/imports/service.py`
- Modify: `app/modules/legal_discovery/service.py`
- Modify: `app/modules/research/service.py`

- [ ] Implement RU phone normalization and extraction helpers.
- [ ] Implement website denylist, URL normalization, alive check, and search-based resolution.
- [ ] Reuse Yandex search provider safely when configured, otherwise degrade cleanly.
- [ ] Apply normalization to import and discovery flows without filtering imports by lead fit.

### Task 3: Lead Fit And Touch Workflow

**Files:**
- Create: `app/modules/lead_fit/__init__.py`
- Create: `app/modules/lead_fit/schemas.py`
- Create: `app/modules/lead_fit/rules.py`
- Create: `app/modules/lead_fit/service.py`
- Create: `app/modules/crm/touch_service.py`
- Modify: `app/modules/sales_intelligence/service.py`

- [ ] Add lead-fit scoring service and insight persistence.
- [ ] Trigger post-import lead-fit recalculation after CSV and Checko imports.
- [ ] Add seven-touch task creation and retrieval services.
- [ ] Feed website/maps scoring into sales material scoring paths.

### Task 4: Admin, API, Smokes, Docs

**Files:**
- Create: `app/modules/admin_reset/service.py`
- Modify: `app/api/routes.py`
- Create: `scripts/smoke_phone_parser.py`
- Create: `scripts/smoke_website_resolver.py`
- Create: `scripts/smoke_touch_plan.py`
- Create: `scripts/smoke_company_delete.py`
- Create: `scripts/smoke_admin_reset.py`
- Create: `scripts/smoke_lead_fit.py`
- Modify: `scripts/smoke_material_scoring.py`
- Modify: `scripts/smoke_checko_html.py`
- Modify: `README.md`
- Modify: `TASKS.md`
- Modify: `CHANGELOG.md`
- Modify: `.env.example`

- [ ] Add website research, lead-fit, touch-plan, delete, and admin reset endpoints.
- [ ] Add smokes covering denylist, lead-fit post-processing, touch-plan, soft delete, and reset.
- [ ] Update docs and env examples.
