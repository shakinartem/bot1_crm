# Checko HTML + Camoufox + Yandex MVP Design

## Goal

Implement a new low-cost legal discovery and website research strategy for BOT 1 on top of branch `codex-proposals-contract-drafts`:

- remove DaData from MVP usage;
- remove Google Search from MVP usage;
- add Yandex Search as the primary real website search provider;
- add a browser backend abstraction with optional Camoufox support;
- add a universal Checko HTML legal discovery flow by OKVED;
- map parsed Checko data into the existing CRM and research models;
- update API, Telegram UX, docs, fixtures, and smoke checks without requiring internet access in smoke mode.

## Scope

This design covers one implementation slice spanning:

- configuration and provider selection;
- Checko HTML list/profile parsing;
- browser abstraction and optional backend loading;
- website search provider selection and resolver wiring;
- legal discovery preview/import flow;
- Telegram discovery UX for OKVED-first flow;
- API schema and endpoint updates;
- fixtures and smoke checks;
- README, `TASKS.md`, and `CHANGELOG.md`.

This slice does not include:

- parsing finance, taxes, lawsuits, licenses, risks, staff, jobs, competitors, branches, or similar non-sales fields;
- replacing the entire intelligence or research architecture;
- adding new CRM tables specifically for founders or social metadata;
- mandatory live browser or live Yandex network tests in smoke scripts.

## Current Codebase Constraints

The current repository already contains:

- `app/modules/legal_discovery/*` for preview/import and Telegram flow;
- `app/modules/intelligence/providers/*` with `dadata`, `google_search`, `yandex_search`, `mock_*`;
- `app/modules/research/*` for website resolution and site research;
- `Company`, `ContactPoint`, `DecisionMaker`, `LeadInteraction`, and `IntelligenceSnapshot` models suitable for storing imported discovery results.

The current architecture is thin and extensible, so the recommended approach is to extend existing modules instead of building a parallel `v2` stack.

## Architectural Decisions

### 1. Reuse Existing Legal Discovery Service

`app/modules/legal_discovery/service.py` remains the orchestrator for:

- running preview;
- storing preview registry entries;
- duplicate detection;
- importing selected rows into CRM.

It will be expanded to carry richer Checko-specific request and preview data instead of being replaced.

### 2. Introduce a Dedicated Browser Backend Abstraction

Create `app/modules/research/browser_backend.py` as the single interface for browser-powered fetching.

It will expose:

- `BrowserBackend`;
- `BrowserPageResult`;
- `DisabledBrowserBackend`;
- `MockBrowserBackend`;
- `CamoufoxBrowserBackend`;
- a small factory to select a backend from settings.

Checko HTML discovery will depend on this abstraction, not on Camoufox directly.

### 3. Keep Optional Dependencies Optional

Camoufox must never be imported at module import time in a way that crashes the app if the package is missing.

The Camoufox backend will:

- attempt lazy import when instantiated;
- expose a friendly error if selected but unavailable;
- allow smoke coverage to pass even if Camoufox is not installed.

### 4. Make Checko HTML the Primary Real Discovery Provider

Add a new provider implementation under:

- `app/modules/legal_discovery/providers/checko_html.py`

This provider becomes the primary real MVP provider, while old providers may remain as disabled stubs if removal would cause unnecessary architectural churn.

### 5. Make Yandex the Primary Real Search Provider

Website resolution will prefer Yandex when `SEARCH_PROVIDER=yandex`.

Google provider code may remain in-tree as a disabled future stub, but it will no longer be reachable as an active MVP recommendation or default path.

DaData will similarly remain only as a disabled future stub if needed for code stability.

## Functional Design

### 1. Configuration

`app/config.py` and `.env.example` will be updated to support:

- `LEGAL_DISCOVERY_PROVIDER=checko_html`
- `CHECKO_HTML_ENABLED`
- `CHECKO_HTML_BASE_URL`
- `CHECKO_HTML_OKVED_DEFAULT`
- `CHECKO_HTML_ONLY_MAIN_OKVED`
- `CHECKO_HTML_ONLY_ACTIVE`
- `CHECKO_HTML_REGION`
- `CHECKO_HTML_MAX_PAGES`
- `CHECKO_HTML_CONCURRENCY`
- `CHECKO_HTML_PROFILE_ENABLED`
- `CHECKO_HTML_PROFILE_CONCURRENCY`
- `CHECKO_HTML_MAX_CONCURRENCY`
- `CHECKO_HTML_PAGE_DELAY_MS`
- `CHECKO_HTML_TIMEOUT`
- `CHECKO_HTML_HEADLESS`
- `SEARCH_PROVIDER=yandex`
- `YANDEX_SEARCH_API_KEY`
- `YANDEX_SEARCH_FOLDER_ID`
- `BROWSER_BACKEND=camoufox`
- `CAMOUFOX_HEADLESS`
- `CAMOUFOX_TIMEOUT`

Legacy `DADATA_*` and `GOOGLE_*` env keys will be removed from `.env.example`.

### 2. OKVED Handling

The discovery request becomes OKVED-first instead of niche-text-first.

Request fields:

- `provider`
- `query`
- `okved_code`
- `okved_title`
- `city`
- `region`
- `only_main_okved`
- `only_active`
- `limit`
- `include_profiles`
- `concurrency`

Normalization rules:

- `86.23 -> 862300`
- `862300 -> 862300`
- `56.10 -> 561000`
- `69.10 -> 691000`

Heuristic mapping:

- `стоматология` or close variants suggest `86.23`
- unknown free-text without parseable OKVED yields a validation error prompting manual OKVED input

### 3. Popular OKVED Catalog

Add a reusable popular OKVED catalog in the legal discovery module for:

- Telegram keyboards;
- API `GET /api/legal-discovery/okved/popular`;
- validation/memo rendering.

The catalog will include the requested MVP entries such as `86.23`, `56.10`, `69.10`, `68.31`, `45.20`, `96.02`, `93.13`, `73.11`, `62.01`, `85.41`, and others from the requirement.

### 4. Checko URL Building

Add a helper to build:

- `https://checko.ru/company/select?code={okved_code}`
- `https://checko.ru/company/select?code=all` when code is absent

If list filter query params turn out unstable, the provider will still open the base URL and continue with warning-based best effort.

### 5. Checko List Parsing

Add `app/modules/legal_discovery/checko_parser.py` with:

- `CheckoListItem`
- `CheckoFounder`
- `CheckoProfileData`
- `parse_checko_list_page`
- `parse_checko_profile_page`

List parsing extracts only:

- organization name;
- profile URL;
- address;
- director name and position when available;
- registration date when available;
- active/inactive hint;
- warnings.

The list parser must remain resilient by using:

- `/company/` links;
- nearby text markers;
- textual labels such as `Дата регистрации`, `Директор`, `Генеральный директор`, `Руководитель`;
- limited CSS selector assumptions.

### 6. Checko Profile Parsing

The profile parser extracts only sales-useful fields:

- short and legal names;
- INN, OGRN, KPP, OKPO;
- legal address;
- status;
- main OKVED code and name;
- phones, emails, websites;
- social and messenger links;
- map links;
- director identity metadata;
- founders;
- Checko profile URL;
- short raw text excerpt;
- parser warnings.

It explicitly does not parse:

- finance;
- taxes;
- staff;
- salaries;
- reliability;
- risks;
- licenses;
- trademarks;
- branches;
- related entities;
- inspections;
- lawsuits;
- debts;
- vacancies;
- history;
- competitors;
- descriptive marketing text.

### 7. JSON-LD Fallback

If DOM parsing misses key requisites, the parser will read JSON-LD `Organization` data and map:

- `name -> short_name`
- `legalName -> legal_name`
- `taxID -> inn`
- `identifier[propertyID=ОГРН] -> ogrn`
- `identifier[propertyID=ИНН] -> inn`
- `identifier[propertyID=КПП] -> kpp`
- `identifier[propertyID=ОКПО] -> okpo`
- `address -> legal_address`
- `url -> checko_profile_url`

DOM remains primary; JSON-LD is fallback, not the other way around.

### 8. Provider Flow

`CheckoHtmlLegalDiscoveryProvider.search_companies(...)` will:

1. resolve or normalize the OKVED input;
2. compute effective concurrency and cap it;
3. compute page count from `limit` and `CHECKO_HTML_MAX_PAGES`;
4. open list pages through the browser backend;
5. parse list pages;
6. optionally fetch profile pages with bounded concurrency;
7. merge list and profile data;
8. map items into `LegalDiscoveredCompany`.

Confidence rules:

- `high` when `inn` and `ogrn` are present;
- `medium` when profile parse succeeded but requisites are incomplete;
- `low` when only list data exists.

Warnings include:

- `missing_inn`
- `missing_profile`
- `weak_data`

### 9. CRM Mapping

During import:

- `Company.name = short_name or legal_name`
- `Company.legal_name = legal_name`
- `Company.inn = inn`
- `Company.ogrn = ogrn`
- `Company.address = legal_address`
- `Company.website = first website if blank`
- `Company.source = legal_discovery:checko_html`
- `Company.status = research_needed`
- `Company.priority = medium` when phone, email, or website exists, otherwise `low`

Contact points:

- phones -> `phone`
- emails -> `email`
- websites -> `website`
- telegram -> `telegram`
- vk -> `vk`
- instagram -> `instagram`
- whatsapp -> `whatsapp`
- youtube -> `youtube`
- map links -> `map_url`

Decision maker:

- create or update one director record from Checko data;
- notes include director INN and since-date when present.

Founders:

- no new dedicated model;
- founders persist in snapshot/raw payload and optionally in a short note.

Each import also writes:

- a `LeadInteraction` note summarizing the Checko import;
- an `IntelligenceSnapshot` carrying raw Checko discovery data.

### 10. Preview Design

Preview counters expand to include:

- found companies;
- with INN;
- with OGRN;
- with phones;
- with email;
- with websites;
- with socials;
- with director;
- with founders;
- new;
- duplicates;
- weak.

Preview actions expand to:

- import active new;
- import all new;
- import new with websites;
- export preview CSV;
- run research after import;
- cancel.

### 11. Telegram UX

Legal discovery Telegram flow becomes:

1. choose source: `Checko HTML` or `Mock / Dev`;
2. choose OKVED mode:
   - popular;
   - manual input;
   - open Checko directory;
3. if popular, choose from a catalog list;
4. if manual, accept formats like `86.23`, `862300`, `56.10`, `691000`;
5. ask region, `only_main_okved`, `only_active`, `limit`, depth, concurrency;
6. run discovery and show enriched preview.

DaData and Google are removed from the MVP Telegram source list.

### 12. API Changes

`POST /api/legal-discovery/search` is extended to accept Checko parameters.

`POST /api/legal-discovery/import` is extended to support:

- `mode`
- `include_weak`
- `run_research_after_import`

Add:

- `GET /api/legal-discovery/okved/popular`

The existing routes remain in place to minimize surface churn.

### 13. Research Queue Integration

If Checko yields websites, they are stored immediately.

If not, the research pipeline will use Yandex-only fallback queries such as:

- `{inn} официальный сайт`
- `{legal_name} официальный сайт`
- `{short_name} {city}`

Resolver behavior remains graceful when Yandex is disabled.

## Concurrency and Safety

Concurrency policy:

- list pages stay sequential or near-sequential;
- profile pages use configured concurrency, default `5`;
- cap is `CHECKO_HTML_MAX_CONCURRENCY`, default `30`;
- values above `10` log a warning;
- values above cap are clamped.

Implementation uses `asyncio.Semaphore`.

Single-page errors must not fail the whole batch.

Every opened browser page must be closed after processing.

## Testing Strategy

### Fixtures

Add HTML fixtures for:

- Checko select results page;
- Checko company profile page.

These become the basis for parser and provider smoke coverage.

### Smoke Scripts

Add:

- `scripts/smoke_checko_html.py`
- `scripts/smoke_yandex_search.py`
- `scripts/smoke_browser_backend.py`

These scripts must not require internet and must use:

- fixtures;
- mock browser backend;
- mock payload mapping.

### Regression Checks

After implementation run:

- `python -m compileall app alembic`
- existing smoke scripts already listed by the user
- new Checko/Yandex/browser smoke scripts
- app import checks

## Documentation Changes

Update:

- `README.md`
- `TASKS.md`
- `CHANGELOG.md`

Documentation must clearly state:

- Checko HTML is the primary MVP legal discovery path;
- Yandex Search API is the primary MVP real website search path;
- DaData and Google are removed from MVP usage;
- Camoufox is optional;
- smoke scripts use fixtures and mock backends;
- concurrency defaults and recommendations.

## Risks and Mitigations

### 1. Checko DOM Drift

Risk:

- HTML structure may change over time.

Mitigation:

- resilient parsing with multiple selector/text heuristics;
- JSON-LD fallback;
- parser warnings rather than hard crashes.

### 2. Missing Camoufox Package

Risk:

- selecting Camoufox without installation could crash startup or discovery.

Mitigation:

- lazy import;
- clear runtime error message;
- mock/disabled fallback path remains available.

### 3. Import Duplication

Risk:

- repeated preview imports could duplicate companies, contacts, or decision makers.

Mitigation:

- reuse existing duplicate matching;
- add per-company contact dedupe;
- idempotent decision maker/contact creation rules in import path;
- smoke coverage for repeated import.

### 4. Too-Broad Scope

Risk:

- legal discovery, Telegram UX, research, and docs all change together.

Mitigation:

- keep schema changes minimal;
- avoid adding new domain tables;
- prefer additive extensions over rewrites;
- rely on smoke checks after each integrated slice.

## Implementation Readiness

The scope is cohesive enough for one implementation plan because all changes serve one end-to-end user flow:

- choose Checko HTML;
- choose OKVED;
- parse list and profiles;
- preview;
- import into CRM;
- resolve missing sites via Yandex;
- continue research queue.

No further project decomposition is required before planning.

Additional acceptance criteria:

1. Smoke tests must not open live checko.ru or live Yandex.
2. Live Checko/Yandex tests are manual only.
3. Repeated Checko import must not duplicate:
   - Company by INN/OGRN;
   - ContactPoint by company_id + type + value;
   - DecisionMaker by company_id + name;
   - LeadInteraction notes should not be spammed on repeated import unless data changed.
4. Founders must be stored primarily in IntelligenceSnapshot, not as a large LeadInteraction note.
5. If Checko provides website, save it.
6. If Yandex finds another website, do not overwrite existing company.website automatically unless confidence is high and the current website is empty or clearly invalid.
7. Preview should allow importing:
   - active new;
   - all new;
   - new with websites;
   - new with phone or website.
8. Camoufox must be lazy-loaded and optional.
9. If Camoufox is missing, app startup must still work.
10. If BROWSER_BACKEND=camoufox but package is missing, discovery should show a friendly runtime error.