# INN-first Company Intelligence Design

## Goal

Add an INN-first intelligence pipeline to SHARiK CRM so a manager can enrich a clinic card through legal lookup, official website resolution, lightweight site parsing, and a saved intelligence snapshot without introducing heavy scraping or breaking existing Telegram and Bot 2 flows.

## Architecture

- `app/modules/intelligence/` is a new orchestration module.
- `app/modules/enrichment/` remains the lightweight manual website research module.
- Intelligence reuses lightweight HTTP fetch patterns and compatible website signal logic, but stores its own snapshots and provider results.
- A new `IntelligenceSnapshot` model stores legal lookup, website resolution, parsed contacts/socials/signals, hypotheses, AI summary, and references.

## Core Flow

1. Determine INN:
   - explicit input;
   - `company.inn`;
   - legal search by name and city.
2. Resolve legal company:
   - if multiple candidates, return `needs_review` and ask manager to choose;
   - if one strong candidate, update safe empty company fields and log a note.
3. Resolve official website:
   - search by INN and legal name through a pluggable search provider;
   - filter aggregators and directory domains;
   - fetch candidate homepages with lightweight `httpx`;
   - score confidence from INN, legal name, city/address, known phone, and dentistry keywords.
4. Parse selected website:
   - title, meta description, excerpt;
   - phones, emails, addresses, messengers, socials, maps links;
   - website signals and service keywords.
5. Save CRM changes cautiously:
   - add missing company fields;
   - add missing `ContactPoint` rows;
   - update `company.website` only when blank or high-confidence;
   - store snapshot and `LeadInteraction` note.

## Providers

- Legal lookup providers:
  - `mock`;
  - `api_fns`;
  - `dadata`.
- Search providers:
  - `mock`;
  - `yandex_search`;
  - `google_search`.
- Providers are configured through env vars and disabled automatically when required credentials are missing.

## Data Model

`IntelligenceSnapshot` fields:

- `company_id`
- `status`
- `inn`
- `legal_name`
- `ogrn`
- `legal_address`
- `legal_status`
- `okved`
- `website_url`
- `website_confidence`
- `website_candidates_json`
- `parsed_contacts_json`
- `parsed_socials_json`
- `parsed_signals_json`
- `hypotheses_json`
- `ai_summary`
- `raw_references_json`
- `error_message`
- `created_at`

JSON payloads are stored as `Text` with `json.dumps/json.loads` for SQLite compatibility.

## Telegram UX

Company card gets a new button: `🧾 INN / Intelligence`.

Menu:

- `🔎 Найти ИНН по названию`
- `🧾 Проверить по ИНН`
- `🌐 Найти сайт по ИНН`
- `🌐 Найти сайт по юр. названию`
- `🧠 Полное обогащение`
- `📌 Последний результат`
- `📜 История`

If legal lookup returns multiple candidates, Telegram shows a chooser and only continues after manager selection.

## Integrations

- AI call prep adds latest intelligence context.
- Proposal package suggestions consider intelligence signals.
- Lead scoring adds legal/site-confidence signals and risks.
- Bot 2 consultation context gains an `intelligence` block.

## Safety

- No Selenium or Playwright.
- No HTML scraping of search engine result pages.
- No aggressive crawling.
- No anti-bot bypass.
- All weak conclusions are phrased as cautious hypotheses.
