# CRM Research Quality and Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve company enrichment quality, separate official websites from reference/map/registry links, add Checko profile visibility, add Yandex Maps research/scoring, expose manual company editing from Telegram, and keep Telegram render output safe and understandable.

**Architecture:** Extend the existing CRM/research/sales-intelligence pipeline instead of introducing new subsystems. Website and maps research should produce structured snapshots that feed both Telegram rendering and sales scoring; manual edits should go through a single validated service layer so audit trails and normalization stay consistent.

**Tech Stack:** Python, FastAPI, SQLAlchemy async, Pydantic, aiogram, Alembic, pytest-style smoke scripts.

---

### Task 1: Company data model and API surface

**Files:**
- Modify: `app/modules/crm/models.py`
- Modify: `app/modules/crm/schemas.py`
- Modify: `app/modules/crm/service.py`
- Modify: `app/api/routes.py`
- Modify: `alembic/versions/*`

- [ ] **Step 1: Add a nullable `checko_profile_url` field to `Company` and expose it in read/update payloads**

```python
# Company model
checko_profile_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

# Company schemas
checko_profile_url: str | None = None
```

- [ ] **Step 2: Add `PATCH /api/companies/{company_id}` payload handling for manual edits**

```python
class CompanyManualUpdate(BaseModel):
    legal_name: str | None = None
    display_name: str | None = None
    city: str | None = None
    region: str | None = None
    address: str | None = None
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    map_url: str | None = None
    status: str | None = None
    priority: str | None = None
    notes: str | None = None
```

- [ ] **Step 3: Implement `update_company_manual_fields(session, company_id, payload, user_id)` with validation and audit logging**

```python
async def update_company_manual_fields(session, company_id, payload, user_id):
    ...
```

- [ ] **Step 4: Add Alembic migration for `checko_profile_url`**
- [ ] **Step 5: Add a smoke test for manual edits and website denylist protection**

### Task 2: Website resolver quality

**Files:**
- Modify: `app/modules/research/website_resolver.py`
- Modify: `app/modules/research/search_resolver.py`
- Modify: `app/modules/intelligence/website_resolver.py`
- Modify: `app/modules/research/schemas.py`
- Modify: `app/modules/research/service.py`
- Create: `scripts/smoke_website_denylist_quality.py`
- Modify: `scripts/smoke_website_resolver.py`

- [ ] **Step 1: Expand denylist and preserve denied URLs as references only**
- [ ] **Step 2: Build richer query order with INN-first search and fallback variants**
- [ ] **Step 3: Persist candidate and confidence data without writing low-confidence URLs into `Company.website`**
- [ ] **Step 4: Store/return Checko profile URLs separately from official websites**
- [ ] **Step 5: Add smoke coverage that rejects Chrome Web Store, Checko, Nalog, maps, and registries as official websites**

### Task 3: Yandex Maps research

**Files:**
- Create: `app/modules/research/maps_research.py`
- Modify: `app/modules/research/schemas.py`
- Modify: `app/modules/crm/telegram_ux.py`
- Modify: `app/modules/crm/keyboards.py`
- Modify: `app/modules/sales_intelligence/service.py`
- Create: `scripts/smoke_maps_research.py`

- [ ] **Step 1: Add `MapsScore` schema and candidate scoring rules**
- [ ] **Step 2: Implement Yandex Maps query building and candidate selection**
- [ ] **Step 3: Persist map candidates into insight snapshots and verified `map_url` when appropriate**
- [ ] **Step 4: Surface maps status/score in Telegram and Sales Intelligence**
- [ ] **Step 5: Add smoke checks for verified, candidate, mismatch, and not-found outcomes**

### Task 4: Telegram company card UX

**Files:**
- Modify: `app/modules/crm/telegram_ux.py`
- Modify: `app/modules/crm/telegram_lead_ux_handlers.py`
- Modify: `app/modules/crm/keyboards.py`
- Modify: `app/modules/analytics/service.py`
- Modify: `app/modules/crm/service.py`
- Create: `scripts/smoke_telegram_company_card.py`
- Modify: `scripts/smoke_material_scoring.py`

- [ ] **Step 1: Update card rendering to clearly separate website, Checko, maps, and social links**
- [ ] **Step 2: Add pagination text, counters, and next/prev controls for company lists**
- [ ] **Step 3: Add Telegram actions for website research, maps research, and manual edit**
- [ ] **Step 4: Keep card output under render safety limits and truncate long URLs/reasons**
- [ ] **Step 5: Add smoke tests for count labels, pagination, and render limits**

### Task 5: Manual edit flow

**Files:**
- Create: `app/modules/crm/manual_edit.py`
- Modify: `app/modules/crm/states.py`
- Modify: `app/modules/crm/handlers.py`
- Modify: `app/modules/crm/telegram_lead_ux_handlers.py`
- Create: `scripts/smoke_company_manual_edit.py`

- [ ] **Step 1: Add FSM-driven field selection and preview**
- [ ] **Step 2: Validate phone/email/url inputs and normalize phone through existing parser**
- [ ] **Step 3: Log audit interactions/notes after save**
- [ ] **Step 4: Restrict dangerous identifiers like INN/OGRN in MVP**
- [ ] **Step 5: Smoke-test manual website clearing, phone normalization, and audit writes**

### Task 6: Scoring integration and docs

**Files:**
- Modify: `app/modules/sales_intelligence/scoring.py`
- Modify: `app/modules/analytics/service.py`
- Modify: `README.md`
- Modify: `TASKS.md`
- Modify: `CHANGELOG.md`
- Create/Modify smoke scripts under `scripts/`

- [ ] **Step 1: Fold website health, maps status, official website presence, verified map presence, and contact quality into scoring**
- [ ] **Step 2: Add human-readable warnings for manual review scenarios**
- [ ] **Step 3: Update README/TASKS/CHANGELOG with the new workflows**
- [ ] **Step 4: Run compileall, alembic upgrade, and all requested smoke scripts**

