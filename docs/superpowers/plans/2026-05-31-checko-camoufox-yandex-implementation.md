# Checko Camoufox Yandex Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 2026-05-29 legal discovery MVP slice around Checko HTML, optional Camoufox browser fetching, and Yandex-first website resolution.

**Architecture:** Extend the existing legal discovery and research modules instead of introducing a parallel stack. Reuse current CRM/intelligence persistence, add a browser backend abstraction for HTML-powered discovery, and keep live-network dependencies optional by grounding smoke coverage in fixtures and mock backends.

**Tech Stack:** FastAPI, Aiogram, SQLAlchemy async ORM, Pydantic, fixture-based smoke scripts.

---

### Task 1: Browser Backend Foundation

**Files:**
- Create: `app/modules/research/browser_backend.py`
- Modify: `app/config.py`
- Test: `scripts/smoke_browser_backend.py`

- [ ] Add a browser backend abstraction with disabled, mock, and lazy Camoufox implementations.
- [ ] Wire backend selection to settings without importing Camoufox at module import time.
- [ ] Add smoke coverage proving disabled/mock backends work and missing Camoufox fails with a friendly runtime error, not app startup.

### Task 2: Checko Parsing and Fixtures

**Files:**
- Create: `app/modules/legal_discovery/checko_parser.py`
- Create: `storage/imports/checko_select_fixture.html`
- Create: `storage/imports/checko_profile_fixture.html`
- Test: `scripts/smoke_checko_html.py`

- [ ] Add resilient list/profile parsing models and helpers using DOM-first extraction with JSON-LD fallback.
- [ ] Cover normalized OKVED handling, warnings, requisites, contacts, socials, founders, and profile URLs using HTML fixtures.
- [ ] Verify parser output in smoke mode without network access.

### Task 3: Checko Provider and Discovery Mapping

**Files:**
- Create: `app/modules/legal_discovery/providers/checko_html.py`
- Create: `app/modules/legal_discovery/okved_catalog.py`
- Modify: `app/modules/legal_discovery/providers.py`
- Modify: `app/modules/legal_discovery/mock_provider.py`
- Modify: `app/modules/legal_discovery/schemas.py`
- Test: `scripts/smoke_checko_html.py`

- [ ] Implement the Checko HTML discovery provider on top of the browser backend and parser.
- [ ] Expand request/preview schemas for OKVED-first search, richer counts, import modes, and raw payload retention.
- [ ] Keep mock mode compatible with the new request shape and preview metrics.

### Task 4: Import Flow, API, and Telegram UX

**Files:**
- Modify: `app/modules/legal_discovery/service.py`
- Modify: `app/modules/legal_discovery/keyboards.py`
- Modify: `app/modules/legal_discovery/handlers.py`
- Modify: `app/api/routes.py`
- Modify: `app/modules/crm/constants.py`
- Test: `scripts/smoke_checko_html.py`

- [ ] Update preview/import logic for new counters, filters, CRM/contact/decision-maker mapping, duplicate-safe behavior, and snapshot/note persistence.
- [ ] Add the popular OKVED API route and import flags.
- [ ] Replace niche-first Telegram flow with source -> OKVED -> filters -> preview/import flow for MVP providers only.

### Task 5: Yandex-First Research Integration and Docs

**Files:**
- Modify: `app/modules/intelligence/providers/__init__.py`
- Modify: `app/modules/intelligence/website_resolver.py`
- Modify: `app/modules/intelligence/service.py`
- Create: `scripts/smoke_yandex_search.py`
- Modify: `README.md`
- Modify: `TASKS.md`
- Modify: `CHANGELOG.md`

- [ ] Make Yandex the primary active search provider path and keep Google/DaData as disabled stubs only.
- [ ] Preserve company website when already good, only upgrading under the spec’s confidence rules.
- [ ] Add fixture/mock-based Yandex smoke coverage and update documentation for the new MVP defaults.

### Task 6: Final Verification

**Files:**
- Verify only

- [ ] Run `python -m compileall app alembic`
- [ ] Run `python scripts/smoke_browser_backend.py`
- [ ] Run `python scripts/smoke_checko_html.py`
- [ ] Run `python scripts/smoke_yandex_search.py`
- [ ] Run existing smoke scripts affected by discovery/intelligence/research flows
