# FNS-first Discovery and Safe Browser Research Design

## Goal

Add a two-stage pipeline for SHARiK CRM:

1. legal-first company discovery with preview and safe CRM import;
2. controlled public-web research queue that enriches imported companies without aggressive scraping or bypass logic.

The design must stay additive, preserve existing Telegram workflows, and reuse current intelligence/enrichment building blocks where they fit.

## Product Boundaries

This stage is not a crawler and not an anti-bot system.

Allowed:

- legal/FNS-style discovery providers;
- safe preview before import;
- lightweight website resolution;
- public-page fetch with `httpx`;
- optional browser renderer abstraction for public pages only;
- controlled batch execution through queue jobs.

Not allowed:

- captcha bypass;
- login automation;
- paywall bypass;
- aggressive crawl;
- search engine HTML scraping by hand;
- silent overwrite of strong CRM fields without confidence checks.

## Recommended Architecture

### 1. `legal_discovery`

New module:

- `schemas.py`
- `service.py`
- `providers.py`
- `mock_provider.py`
- `handlers.py`
- `keyboards.py`

Responsibility:

- query a legal data provider by niche/city/region;
- normalize discovered legal companies;
- build preview stats;
- detect CRM duplicates;
- import only after explicit confirmation.

This module does not fetch websites.

### 2. `research`

New module:

- `schemas.py`
- `http_fetcher.py`
- `browser_fetcher.py`
- `search_resolver.py`
- `site_parser.py`
- `service.py`

Responsibility:

- resolve likely official website from legal data;
- fetch public pages through safe backends;
- parse contacts, socials, messengers, maps, and digital signals;
- return a normalized research result.

This module is the low-level public-web engine.

### 3. `research_queue`

New module:

- `models.py`
- `schemas.py`
- `service.py`
- `worker.py`
- `handlers.py`
- `keyboards.py`

Responsibility:

- create and track `ResearchJob`;
- enforce one active job per company and job type;
- run batched research with concurrency and delays;
- persist job status, retries, and short result payload.

This module does not contain discovery logic and does not parse HTML itself.

### 4. Existing modules to reuse

- `intelligence` stays as the single-company INN-first flow.
- `enrichment` stays as the lightweight manual website research flow.

The new batch pipeline should reuse:

- legal matching logic and legal/search provider ideas from `intelligence`;
- lightweight HTML signal extraction ideas from `enrichment`;
- scoring/call prep/Bot2 integration paths already introduced.

## Data Model Strategy

### `IntelligenceSnapshot`

Keep the existing `IntelligenceSnapshot` as the canonical durable snapshot for:

- confirmed legal identity;
- website resolution result;
- parsed contacts/socials/signals;
- hypotheses;
- AI summary.

Rationale:

- it already matches most of the new research output;
- adding another final snapshot table would fragment context;
- Bot 2, scoring, proposals, and call prep already benefit from a single latest intelligence snapshot.

### `ResearchJob`

Add a new queue table:

- `company_id`
- `job_type`
- `status`
- `priority`
- `attempts`
- `max_attempts`
- `started_at`
- `finished_at`
- `error_message`
- `result_json`
- `created_at`
- `updated_at`

This stores execution state, not business intelligence.

### Legal discovery preview storage

Previews do not need a permanent relational table in MVP.

Use a service-level preview registry keyed by `preview_id`, holding:

- query parameters;
- provider code;
- normalized preview items;
- counters.

This keeps the import flow simple while still supporting preview -> confirm -> import.

If later product needs auditability for discovery sessions, a DB table can be added without redesigning the modules.

## Legal Discovery Flow

### Provider interface

Providers return normalized `LegalDiscoveredCompany` records with:

- `inn`
- `ogrn`
- `kpp`
- `legal_name`
- `short_name`
- `address`
- `city`
- `region`
- `status`
- `okved`
- `okved_name`
- `raw_payload`
- `confidence`
- `warnings`

### Mock provider

The mock provider must support:

- `query="стоматология"`
- `city="Саратов"`

and return a realistic mixed dataset:

- active companies;
- inactive companies;
- duplicates by INN / OGRN / legal name + city;
- weak entries;
- varied addresses and OKVEDs.

This dataset is the backbone for smoke tests and preview UX.

### Preview logic

`LegalDiscoveryPreview` computes:

- total found;
- active count;
- inactive count;
- new count;
- duplicate count;
- weak count.

Each preview item gets one of:

- `new`
- `duplicate_existing`
- `weak_data`
- `inactive`
- `error`

### Import logic

On import:

- `Company.name = short_name or legal_name`
- `Company.legal_name = legal_name`
- `Company.inn = inn`
- `Company.ogrn = ogrn`
- `Company.address = address`
- `Company.city = city`
- `Company.region = region`
- `Company.source = legal_discovery:{provider}`
- `Company.status = research_needed`
- `Company.priority = medium` for active, `low` for weak/inactive imports

Also create `LeadInteraction` note:

- `Компания найдена через legal discovery: {provider}`

Dedupe checks:

- `inn`
- `ogrn`
- `legal_name + city`

Repeated import must not create duplicates.

## Safe Research Engine

### Fetch abstraction

`FetchBackend` exposes:

- `fetch(url) -> FetchResult`

Backends:

- `http_fetcher`: default MVP backend via `httpx`
- `browser_fetcher`: safe optional abstraction, disabled by default

### Safe browser rules

Browser backend is allowed only to render public pages.

If page shows signs of:

- captcha;
- login wall;
- access denied;
- anti-bot block;
- challenge page;

then it returns:

- `status=blocked`
- `blocked_reason=<detected reason>`

and the job ends without bypass attempts.

### Website resolution

Resolver must:

1. build INN/legal-name based queries;
2. use configured search provider abstraction;
3. filter aggregator/check-company domains;
4. score candidates from page evidence;
5. return selected site only when confidence is sufficient.

If confidence is low:

- do not auto-update `company.website`;
- return `needs_manual_review`.

### Site parsing

Parse:

- title and meta description;
- phones;
- emails;
- WhatsApp and Telegram links;
- VK, Instagram, YouTube, TikTok, Dzen links;
- Yandex Maps and `2GIS` links;
- online booking, callback, prices, doctors, reviews, contacts, privacy policy signals;
- service keywords for implantation, braces, aligners, children dentistry, emergency pain.

Create `ContactPoint` entries for:

- phone;
- email;
- website;
- whatsapp;
- telegram;
- vk;
- instagram.

## Research Queue Flow

### Job creation

`create_research_jobs_for_companies(...)`:

- skips duplicates where same `company_id + job_type` is already `pending` or `running`;
- supports priority;
- stores initial metadata.

### Batch execution

`run_research_batch(...)`:

- pulls pending jobs;
- runs with configured concurrency;
- respects request delay between jobs/fetches;
- retries until `max_attempts`;
- stores compact `result_json`.

### Job statuses

- `pending`
- `running`
- `success`
- `failed`
- `blocked`
- `needs_manual_review`
- `cancelled`

### Research result handling

`run_company_research(...)`:

1. load company;
2. require at least INN or legal identity;
3. resolve website;
4. fetch through selected backend;
5. stop early on block/login/captcha;
6. parse site;
7. build hypotheses;
8. save contacts/socials;
9. update `company.website` only for medium/high confidence;
10. save/update `IntelligenceSnapshot`;
11. create note interaction.

## Telegram UX

### Main menu

Add:

- `🔍 Поиск компаний`

### Discovery wizard

Steps:

1. source provider;
2. niche;
3. city/region;
4. limit;
5. preview screen.

Preview actions:

- `✅ Импортировать активные новые`
- `✅ Импортировать все новые`
- `❌ Отмена`
- `📤 Экспорт preview CSV`

### After import

Offer:

- `🧠 Запустить research`

Options:

- only new companies;
- only without website;
- top-50;
- all from latest import.

### Queue screens

Show:

- total companies;
- jobs created;
- concurrency;
- batch results;
- links to found websites;
- blocked/manual review subset;
- export results.

## API Design

Add:

- `POST /api/legal-discovery/search`
- `POST /api/legal-discovery/import`
- `POST /api/research/jobs`
- `GET /api/research/jobs`
- `POST /api/research/jobs/run-batch`
- `GET /api/research/jobs/status`
- `POST /api/companies/{company_id}/research/run`
- `GET /api/companies/{company_id}/research/latest`
- `GET /api/companies/{company_id}/research/history`

These endpoints should complement, not replace:

- existing enrichment endpoints;
- existing intelligence endpoints.

## Integration Strategy

### Analytics and scoring

- `source=legal_discovery:*` appears in source analytics.
- scoring gains legal/research signals:
  - `+10` INN confirmed
  - `+10` official website found with medium/high confidence
  - `+5` contacts found
  - `-10` no website found
  - `-10` blocked / needs manual review

### AI call prep

Use latest intelligence/research context alongside existing enrichment context.

### Proposals

Use latest site signals:

- no booking -> audit/landing
- no socials -> smm/audit
- no reviews -> maps reputation

### Bot 2 context

Add a `research` block backed by latest intelligence snapshot plus queue outcome status when relevant.

### Company card

Compact status lines:

- `Legal: confirmed / not confirmed`
- `Website: found / not found`
- `Research: success / blocked / manual / failed`

## CLI

Add `scripts/run_research_batch.py` with:

- `--limit`
- `--concurrency`
- `--source`
- `--only-without-website`
- `--dry-run`

This script is a manual operator tool, not a daemon.

## Testing Strategy

### `smoke_legal_discovery.py`

Must verify:

- mock provider returns companies;
- preview counters are correct;
- import creates companies;
- repeated import is idempotent;
- API endpoints work.

### `smoke_research_queue.py`

Must verify:

- companies with INN can create jobs;
- batch run processes jobs;
- mock resolver/fetcher find websites;
- contacts are created;
- snapshots are created;
- statuses are updated correctly;
- duplicate jobs are prevented;
- API endpoints work.

No smoke test may require real internet.

## Future-facing Hooks

The design intentionally leaves room for:

- real API-FNS and DaData credentials;
- real Yandex/Google search APIs;
- optional disabled-by-default browser renderer;
- future experiments with Crawlee or Camoufox as renderers, without bypass behavior.
