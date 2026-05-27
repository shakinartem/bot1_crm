# Website / Social Research Enrichment Design

## Goal

Добавить в BOT 1 CRM лёгкий модуль research enrichment, который:

- делает быструю внешнюю проверку сайта клиники через `httpx`
- сохраняет snapshot результата в истории компании
- извлекает сигналы по сайту, соцсетям, картам и контактам
- строит осторожные rule-based гипотезы по digital-воронке
- по запросу дополняет snapshot AI-резюме
- переиспользует enrichment в Telegram card, AI call prep, proposals, scoring и Bot 2 context

## Constraints

- не ломать существующие Telegram workflows
- не ломать Bot 2 handoff/context API
- не ломать digest startup/scheduler
- не ломать proposals и analytics
- не добавлять Selenium, Playwright и тяжёлый scraping
- использовать только lightweight single-page fetch через `httpx`
- не обходить защиты сайта и не делать aggressive crawl
- не собирать лишние персональные данные
- все выводы формулировать как гипотезы, а не как точные выводы

## Recommended Approach

Используем отдельный модуль `app/modules/enrichment` с собственной моделью `EnrichmentSnapshot` и сервисным orchestration-слоем.

Это даёт:

- history of research snapshots
- безопасное повторное использование enrichment в других модулях
- минимальное вторжение в текущую CRM-архитектуру
- возможность mixed AI mode: rule-based by default, AI as optional layer

## Module Structure

Новый модуль:

```text
app/modules/enrichment/
  __init__.py
  models.py
  schemas.py
  service.py
  fetcher.py
  analyzer.py
  prompts.py
  handlers.py
  keyboards.py
```

Responsibilities:

- `models.py` — SQLAlchemy model `EnrichmentSnapshot`
- `schemas.py` — DTO для fetch/analyze/result/API serialization
- `fetcher.py` — safe single-page website fetch
- `analyzer.py` — HTML/text/link/contact/social/map analysis + rule-based hypotheses
- `prompts.py` — AI enrichment summary prompt builder + fallback summary helpers
- `service.py` — orchestration, persistence, integration context builders
- `handlers.py` — Telegram research workflow
- `keyboards.py` — inline keyboards for research actions/history

## Data Model

Новая таблица `enrichment_snapshots`:

- `id`
- `company_id`
- `website_url`
- `status`
- `fetched_at`
- `http_status`
- `page_title`
- `meta_description`
- `detected_links_json`
- `detected_socials_json`
- `detected_maps_json`
- `detected_contacts_json`
- `signals_json`
- `hypotheses_json`
- `ai_summary`
- `raw_text_excerpt`
- `error_message`
- `created_at`

### Storage Format

Для SQLite совместимости JSON-поля храним как `Text`:

- save: `json.dumps(..., ensure_ascii=False)`
- read: safe `json.loads(...)`

В `Company` добавляется relationship:

- `enrichment_snapshots`

Нужна миграция:

- `alembic/versions/0005_add_enrichment_snapshots.py`

## Fetch Flow

`fetch_website(url: str, timeout: int = 10) -> FetchResult`

### URL normalization

- trim whitespace
- if no scheme: prepend `https://`
- reject obviously invalid values

### HTTP behavior

- `httpx.AsyncClient`
- timeout 10 sec
- `follow_redirects=True`
- user-agent: `SHARiK CRM Research Bot/1.0`
- accept only one fetched page
- truncate stored HTML to first 300000 chars

### Failure handling

Return structured `FetchResult` with:

- `url`
- `final_url`
- `status`
- `http_status`
- `html`
- `error_message`

Statuses:

- `success`
- `partial`
- `failed`

Failure cases:

- invalid URL
- timeout
- connection error
- non-HTML content type
- HTTP >= 400

## Analysis Flow

`analyze_website_html(html: str, base_url: str) -> WebsiteAnalysis`

### Extracted fields

- `page_title`
- `meta_description`
- `raw_text_excerpt`
- `detected_links`
- `detected_socials`
- `detected_maps`
- `detected_contacts`
- `signals`

### Link extraction

Detect:

- internal links
- external links

### Social detection

Recognize links or references for:

- VK
- Instagram
- Telegram
- WhatsApp
- YouTube
- TikTok
- Dzen
- TenChat

### Maps/platforms detection

Recognize:

- Yandex Maps
- 2GIS
- Google Maps
- Zoon
- ProDoctorov
- Yell

### Contact detection

Recognize:

- phones
- emails
- WhatsApp links
- Telegram links

### Signals

Boolean signals:

- `has_online_booking`
- `has_callback_form`
- `has_prices`
- `has_doctors_page`
- `has_reviews_section`
- `has_contacts_page`
- `has_social_links`
- `has_messenger_links`
- `has_privacy_policy`
- `has_promotions`
- `has_implantation_keywords`
- `has_orthodontics_keywords`
- `has_children_dentistry_keywords`
- `has_emergency_keywords`

Detection is keyword-based and intentionally shallow. This is not a full audit.

## Hypotheses

`build_enrichment_hypotheses(analysis: WebsiteAnalysis) -> list[str]`

Hypotheses are generated from missing or present signals and always use cautious phrasing:

- "В быстрой проверке не обнаружено..."
- "Возможно..."
- "Стоит проверить..."
- "По доступным данным можно предположить..."

Examples:

- no online booking
- no messenger links
- no doctors page
- no reviews
- no prices
- implantation found without strong trust signals
- no clear contacts block

## AI Summary

`build_enrichment_summary_prompt(company_context, analysis, hypotheses)`

### Output structure

```text
# Быстрое резюме digital-присутствия

## Что видно снаружи
## Возможные слабые места
## Что спросить на звонке
## Что можно предложить как первый шаг
## Осторожные гипотезы
```

### Safety rules

- no invented facts
- no hard conclusions on low data
- no guarantees of growth
- no medical advice
- sales-intelligence tone for SHARiK digital manager
- focus on digital funnel and patient path to booking

### Mixed AI mode

- Telegram website check uses rule-based flow first
- AI summary is opened/generated by separate Telegram action
- API `POST /enrichment/website` may use `use_ai=true` by default
- if AI is unavailable, service returns fallback summary from rule-based data

## Service Design

Main entrypoint:

- `enrich_company_website(session, company_id, website_url=None, use_ai=True)`

Supporting functions:

- `get_latest_enrichment(session, company_id)`
- `get_enrichment_history(session, company_id, limit=10)`
- `get_enrichment_snapshot(session, company_id, snapshot_id)`
- `build_enrichment_context_for_company(session, company_id)`

### Orchestration sequence

1. Load company
2. Resolve website URL from:
   - explicit argument
   - `company.website`
   - primary `ContactPoint(type=website)`
3. If URL missing:
   - create `manual` or `failed` snapshot
   - save error message `Website URL is missing`
4. Run `fetch_website`
5. Save failed or partial result if fetch unsuccessful
6. Run HTML analysis if fetch has usable HTML
7. Build hypotheses
8. Build optional AI summary
9. Persist `EnrichmentSnapshot`
10. Add `LeadInteraction(type=note)` about completed research
11. If manual URL was provided and company website is empty, update `company.website`
12. Return normalized `EnrichmentResult`

## Telegram UX

Add company card button:

- `🔎 Research`

### Research menu

```text
🔎 Research / обогащение

Клиника: {company.name}
Сайт: {company.website or "не указан"}

Выберите действие:
- 🌐 Проверить сайт
- ✍️ Ввести сайт вручную
- 📌 Последний research
- 📜 История research
- 🤖 AI-резюме
- ⬅️ Назад
```

### Check website flow

- if website exists: run enrichment with `use_ai=False`
- show progress message
- show compact result card with:
  - site
  - status
  - HTTP
  - page title
  - socials
  - contacts
  - maps/platforms
  - online booking / form / reviews / prices / doctors
  - up to 3 hypotheses

Actions:

- open AI summary
- add to AI prep
- generate proposal
- back to company card

### Manual website flow

- FSM asks for URL
- normalize/validate URL
- run enrichment
- if success and `company.website` was empty, save it
- show result summary

### Latest/history flow

- latest snapshot screen with date/status/title/signals/hypotheses/short AI summary
- history screen with last 10 snapshots
- drill-down to a specific snapshot

## Company Card Integration

Add compact block to company card:

```text
🔎 Research:
Последний: 21.05.2026 — success
Сайт: site.ru
Сигналы: онлайн-запись: да, отзывы: нет, мессенджеры: да
Гипотезы: 2
```

If absent:

```text
🔎 Research: не проводился
```

This block must stay short and not overload the card.

## AI Call Prep Integration

If latest enrichment exists, inject into call prep context:

- `page_title`
- `meta_description`
- `signals`
- `hypotheses`
- `ai_summary`
- `detected_socials`
- `detected_maps`
- `detected_contacts`

Expected impact:

- better website-related call questions
- better first-step suggestions
- better understanding of funnel leakage risks

## Proposals Integration

Package suggestions should consider enrichment:

- no online booking or callback form -> `landing_start` or `audit_roadmap`
- no reviews or empty maps -> `maps_reputation`
- no social links -> `smm_funnel` or `audit_roadmap`
- implantation keywords -> cautious boost for `complex_growth` or `landing_start`
- patient-loss style hypotheses -> `audit_roadmap` or `crm_bot`

This should enrich, not replace, existing package suggestion logic.

## Scoring Integration

Additional score adjustments:

- `+5` if research success
- `+5` if site exists and research found booking or callback
- `+5` if social links found
- `+5` if maps or review signals found
- `-10` if website failed quick check
- `-5` if no detected contacts and no `company.phone`
- `-5` if no booking and no callback
- `-5` if no trust signals: reviews and doctors

Reasons/risks should include enrichment-aware phrases:

- `проведен research сайта`
- `на сайте не найден явный блок отзывов`
- `не обнаружены быстрые мессенджеры`
- `сайт недоступен при быстрой проверке`

## Bot 2 Context Integration

Extend `GET /api/bot2/companies/{company_id}/consultation-context` with:

```json
"enrichment": {
  "latest_snapshot_at": "...",
  "website_url": "...",
  "status": "...",
  "signals": {},
  "hypotheses": [],
  "ai_summary": "...",
  "detected_socials": {},
  "detected_maps": {}
}
```

This must be additive and backward-compatible.

## API Additions

New endpoints:

- `POST /api/companies/{company_id}/enrichment/website`
- `GET /api/companies/{company_id}/enrichment/latest`
- `GET /api/companies/{company_id}/enrichment/history`
- `GET /api/companies/{company_id}/enrichment/{snapshot_id}`

Response models must return parsed JSON structures, not raw JSON strings.

## Testing Strategy

Add `scripts/smoke_enrichment.py`.

It should:

- create a test company
- avoid external internet dependency
- use sample HTML or monkeypatched fetcher
- validate analyzer output
- create and read snapshots
- verify latest/history API endpoints through `TestClient`
- verify Bot 2 consultation context contains enrichment block
- print `smoke_enrichment ok`

## Verification Checklist

Before final completion:

- `python -m compileall app alembic`
- `python scripts/smoke_check.py`
- `python scripts/test_csv_import.py`
- `python scripts/smoke_bot2_handoff.py`
- `python scripts/test_digest_module.py`
- `python scripts/smoke_proposals.py`
- `python scripts/smoke_analytics.py`
- `python scripts/smoke_bot2_context.py`
- `python scripts/smoke_enrichment.py`
- `python -c "from app.main import app; print(app.title)"`
- `python -c "from app.bot import main; print('bot ok')"`
- `alembic upgrade head` if migration added

## File Impact Summary

Expected new files:

- `app/modules/enrichment/*`
- `alembic/versions/0005_add_enrichment_snapshots.py`
- `scripts/smoke_enrichment.py`

Expected touched integration files:

- `app/modules/crm/models.py`
- `app/modules/crm/service.py`
- `app/modules/crm/handlers.py`
- `app/modules/crm/keyboards.py`
- `app/modules/crm/schemas.py`
- `app/modules/ai/service.py`
- `app/modules/ai/prompts.py`
- `app/modules/proposals/service.py`
- `app/modules/analytics/scoring.py`
- `app/modules/analytics/service.py`
- `app/api/routes.py`
- `app/main.py`
- `app/bot.py`
- `README.md`
- `TASKS.md`
- `CHANGELOG.md`

## Non-Goals

- full SEO audit
- multi-page crawl
- browser automation
- login flows
- anti-bot bypass
- scraping protected data
- guaranteed business recommendations
