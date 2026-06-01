# Sales Intelligence MVP Design

## Goal

Добавить в BOT 1 отдельный слой sales intelligence, который поверх уже существующих CRM, enrichment, intelligence и research данных:

- оценивает качество digital-материалов компании;
- оценивает готовность лида по 5 критериям закрытия сделки;
- генерирует вопросы по технике SOPRANO;
- формирует безопасный cold call plan в AI или fallback режиме;
- переиспользуется в Telegram, API, Bot2 context, analytics scoring и proposals.

MVP не добавляет новую таблицу и не делает обязательную миграцию для хранения sales intelligence данных.

## Constraints

- Не переписывать существующий AI call prep с нуля.
- Не ломать CRM, Checko discovery, research queue, scoring, proposals и Bot2 context.
- Не добавлять таблицу `SalesIntelligenceSnapshot`.
- Не делать медицинских или юридических утверждений.
- Не обещать рост заявок, пациентов, продаж или выручки.
- Все выводы по сайту, соцсетям и картам формулировать как гипотезы.
- Если AI недоступен, cold call plan всё равно должен собираться rule-based fallback логикой.

## Recommended Architecture

Создаётся новый модуль `app/modules/sales_intelligence/`, который работает как orchestration layer и не вводит новые ORM-модели.

### Files

- `__init__.py`: экспорт публичных сервисных функций.
- `schemas.py`: Pydantic-контракты sales intelligence payload.
- `scoring.py`: rule-based material scoring и readiness scoring.
- `prompts.py`: prompt builder для AI cold call plan.
- `service.py`: сбор company context, orchestration, AI/fallback generation, persistence.
- `keyboards.py`: inline keyboards для sales intelligence workflow.
- `handlers.py`: Telegram callbacks и render-логика.

### Responsibility Boundaries

- `sales_intelligence` не знает о HTTP-роутах напрямую.
- `sales_intelligence.scoring` не зависит от Telegram, FastAPI и SQLAlchemy ORM объектов.
- `sales_intelligence.service` работает с БД и адаптирует существующие snapshot/context структуры в единый sales context.
- Интеграции в `analytics`, `proposals`, `crm` и `api` используют публичные сервисные функции модуля.

## Data Contracts

### SalesMaterialScore

- `company_id: int`
- `total_score: int`
- `grade: Literal["weak", "basic", "normal", "strong", "excellent"]`
- `website_score: int`
- `socials_score: int`
- `maps_score: int`
- `trust_score: int`
- `conversion_score: int`
- `contact_score: int`
- `reasons: list[str]`
- `risks: list[str]`
- `opportunities: list[str]`
- `next_improvements: list[str]`

Все текстовые пункты формулируются как осторожные гипотезы.

### ClosingCriteriaReadiness

Для каждого критерия создаётся блок с полями:

- `score: int`
- `status: Literal["unknown", "weak", "possible", "strong"]`
- `evidence: list[str]`
- `questions: list[str]`

Критерии:

- `financial_opportunity`
- `conscious_need`
- `trust`
- `decision_maker`
- `here_and_now`

Также:

- `summary: str`
- `risks: list[str]`
- `next_best_question: str`

### SopranoQuestionSet

- `company_id: int`
- `niche: str | None`
- `niche_detected: str | None`
- `niche_confidence: float | None`
- `intro: str`
- `situation: list[str]`
- `experience: list[str]`
- `principles: list[str]`
- `solutions: list[str]`
- `analogies: list[str]`
- `undesired: list[str]`
- `limitations: list[str]`
- `recommended_order: list[str]`

### ObjectionHandlingItem

- `objection: str`
- `response_principle: str`
- `suggested_response: str`

### ColdCallPlan

- `company_id: int`
- `company_name: str`
- `niche: str | None`
- `niche_detected: str | None`
- `niche_confidence: float | None`
- `generation_mode: Literal["ai", "fallback"]`
- `confidence: Literal["low", "medium", "high"]`
- `created_at: datetime`
- `call_goal: str`
- `opener: str`
- `reason_for_call: str`
- `personalization_points: list[str]`
- `digital_observations: list[str]`
- `likely_pains: list[str]`
- `closing_criteria: dict`
- `soprano_questions: dict`
- `objection_preparation: list[ObjectionHandlingItem]`
- `first_offer: str`
- `next_best_action: str`
- `call_script_short: str`
- `call_script_detailed: str`
- `copyable_short_script: str`
- `manager_checklist: list[str]`
- `risks: list[str]`
- `do_not_say: list[str]`

`copyable_short_script` должен быть plain text без markdown-таблиц и длинных пояснений, рассчитанным на 30-60 секунд чтения.

### LatestSalesIntelligenceRead

- `material_score: SalesMaterialScore`
- `closing_criteria: ClosingCriteriaReadiness`
- `soprano_questions: SopranoQuestionSet`
- `cold_call_plan: ColdCallPlan | None`
- `saved_at: datetime | None`

## Company Sales Context

`service.py` собирает нормализованный `company_context`, включающий:

- `Company`
- `ContactPoint`
- `DecisionMaker`
- latest `IntelligenceSnapshot`
- latest enrichment snapshot
- latest research snapshot
- latest `ResearchJob.result_json`, если доступен
- recent `LeadInteraction`
- open `FollowUpTask`
- derived feature flags и normalized signal lists

Контекст должен быть устойчивым к частично пустым данным. Отсутствие snapshot или research job не является ошибкой.

## Material Scoring Design

Функция:

- `calculate_material_quality_score(company_context) -> SalesMaterialScore`

Компонентные score считаются в диапазоне `0..100`, после чего собирается итоговый score по весам:

- website: 25%
- conversion: 20%
- trust: 20%
- contact: 15%
- socials: 10%
- maps: 10%

### Grade Mapping

- `0..24 -> weak`
- `25..44 -> basic`
- `45..64 -> normal`
- `65..84 -> strong`
- `85..100 -> excellent`

### Website Score Signals

Плюсы:

- найден сайт;
- высокий confidence сайта;
- есть телефон;
- есть email или форма;
- есть мессенджер;
- есть онлайн-запись или явный CTA;
- есть блок услуг;
- есть блок команда/врачи/специалисты;
- есть отзывы/кейсы/доверительные блоки;
- есть privacy policy.

Минусы:

- сайт не найден;
- сайт найден, но не открылся;
- нет явного контакта;
- нет CTA, формы или записи;
- нет доверительных блоков.

### Socials Score Signals

Плюсы:

- найдены соцсети;
- есть VK, Telegram, Instagram, YouTube/Reels/Shorts признаки;
- видна регулярность публикаций, если это доступно в snapshot;
- есть доверительный контент: врачи, процессы, отзывы, кейсы, экспертность.

Минусы:

- соцсети не найдены;
- соцсети выглядят пустыми или неактивными;
- нет доверительного контента.

### Maps Score Signals

Плюсы:

- есть Yandex Maps, 2GIS или Google Maps ссылки;
- есть карточка на карте;
- есть рейтинг или отзывы;
- адрес и телефон совпадают с сайтом или legal data;
- есть фото, описание или список услуг.

Минусы:

- карты не найдены;
- адрес или телефон не совпадают;
- нет отзывов или рейтинга.

### Trust Score Signals

Плюсы:

- найден ЛПР или руководитель;
- есть ИНН/ОГРН;
- есть сайт;
- есть адрес;
- есть отзывы;
- есть врачи или команда;
- есть лицензии или сертификаты, если найдены;
- есть соцсети;
- есть прозрачные контакты.

Минусы:

- мало доверительных элементов;
- нет команды/врачей;
- нет отзывов;
- нет прозрачных контактов.

### Conversion Score Signals

Плюсы:

- есть понятный CTA;
- есть онлайн-запись;
- есть форма заявки;
- есть мессенджер;
- телефон виден на первом экране или в контактах;
- услуги упакованы понятно;
- есть цены, ориентиры или первичная консультация.

Минусы:

- нет понятного следующего шага;
- нет мессенджеров;
- нет формы;
- нет онлайн-записи.

### Contact Score Signals

Плюсы:

- есть телефон;
- есть email;
- есть сайт;
- есть мессенджеры;
- есть адрес;
- есть соцсети;
- есть карта или маршрут.

Минусы:

- нет телефона;
- нет сайта;
- нет email или формы;
- нет мессенджера.

### Output Language Rules

`reasons`, `risks`, `opportunities`, `next_improvements` формулируются как:

- "По доступным данным можно предположить ..."
- "Вероятно, ..."
- "Стоит проверить, ..."

Никаких категоричных оценок и обещаний результата.

## Closing Criteria Readiness Design

Функция:

- `build_closing_criteria_readiness(session, company_id) -> ClosingCriteriaReadiness`

### financial_opportunity

Использует:

- legal/checko data;
- наличие сайта, контактов, команды;
- размер/системность организации, если это видно;
- косвенные признаки организованного бизнеса.

Запрещено делать жёсткие выводы о бюджете. Выход должен содержать вероятностную оценку и вопросы на уточнение.

### conscious_need

Использует:

- слабые места сайта;
- слабые места воронки;
- отсутствие записи/формы;
- слабые соцсети;
- недостаток доверительных сигналов;
- research/enrichment/intelligence hypotheses.

### trust

Использует:

- сайт;
- отзывы;
- соцсети;
- руководителя/ЛПР;
- команду;
- прозрачность контактов;
- общую прозрачность digital presence.

### decision_maker

Использует:

- primary `DecisionMaker`;
- legal/intelligence-derived руководителя;
- историю контактов;
- признаки доступности лица, принимающего решение.

### here_and_now

Использует:

- свежесть взаимодействий;
- статус компании;
- наличие follow-up task;
- признаки срочности из заметок, задач, interactions;
- research/intelligence hypotheses, если они указывают на активную потребность.

### Status Rules

- `unknown`: данных почти нет;
- `weak`: признаки есть, но они слабые;
- `possible`: есть несколько полезных сигналов;
- `strong`: есть прямые или почти прямые подтверждения.

`next_best_question` выбирается из наиболее полезного вопроса по самому слабому или самому важному критерию.

## SOPRANO Questions Design

Функция:

- `generate_soprano_questions(session, company_id, niche=None) -> SopranoQuestionSet`

Источник:

- derived niche из company data, website/research/intelligence signals;
- material scoring risks/opportunities;
- closing criteria gaps.

Если niche определить нельзя:

- `niche_detected = null`
- `niche_confidence = null`
- вопросы остаются универсальными для digital sales discovery.

Каждый блок вопросов:

- `situation`
- `experience`
- `principles`
- `solutions`
- `analogies`
- `undesired`
- `limitations`

Порядок по умолчанию:

- `intro`
- `situation`
- `experience`
- `principles`
- `solutions`
- `analogies`
- `undesired`
- `limitations`

## Cold Call Plan Design

Функция:

- `generate_cold_call_plan(session, company_id, use_ai=True) -> ColdCallPlan`

### AI Mode

AI mode использует новый prompt builder из `sales_intelligence.prompts` и не меняет текущий `prepare_cold_call`.

Prompt получает:

- company identity;
- concise material score summary;
- concise closing criteria summary;
- SOPRANO questions;
- selected digital observations;
- safety rules and forbidden claims;
- required output contract.

Если AI вернул пустой или невалидный ответ, сервис автоматически падает в fallback mode.

### Fallback Mode

Функция:

- `build_fallback_cold_call_plan(company_context, material_score, closing_criteria, soprano_questions) -> ColdCallPlan`

Fallback должен:

- всегда возвращать валидный `ColdCallPlan`;
- строить безопасный opener;
- давать 30-60 секундный `copyable_short_script`;
- использовать гипотезы вместо утверждений;
- избегать медицинских, юридических и финансовых обещаний.

### Safety Rules In Plan

`do_not_say` всегда включает:

- "У вас всё плохо."
- "Мы гарантируем рост."
- "Сколько у вас бюджет?"
- "Мы лучше ваших текущих подрядчиков."
- медицинские советы.

## Persistence Strategy

Новая таблица не добавляется.

При сохранении сервис пытается положить payload в последний доступный `IntelligenceSnapshot` под ключом:

```json
{
  "sales_intelligence": {
    "material_score": {},
    "closing_criteria": {},
    "soprano_questions": {},
    "cold_call_plan": {},
    "saved_at": "..."
  }
}
```

### Merge Rules

- Не затирать существующий `raw_payload_json` или `result_json`.
- Делать аккуратный merge только по ключу `sales_intelligence`.
- Если безопасный merge невозможен, snapshot не ломать.
- В таком случае возвращать on-demand payload и фиксировать только короткую note в `LeadInteraction`.

### LeadInteraction Note Rules

Сохраняется короткая deduplicated note:

`Сформирован план холодного звонка. Material score: {score}/100 ({grade}). Первый оффер: {first_offer}. Mode: {generation_mode}.`

Запрещено сохранять:

- полный план;
- полный short script;
- длинный detailed script.

Новая note создаётся только если план реально регенерирован или изменились score/offer/mode.

## Telegram Workflow

В карточку компании добавляется кнопка:

- `📞 План звонка`

Экран плана звонка показывает:

- company name;
- material score и grade;
- 5 критериев readiness в compact виде;
- кнопки на генерацию плана, material scoring, SOPRANO, criteria, proposal/task actions.

После генерации плана экран показывает:

- generation mode;
- confidence;
- goal;
- opener;
- digital observations;
- main questions;
- first offer;
- actions:
  - показать полный план;
  - скопировать short script;
  - создать задачу на звонок;
  - сформировать КП;
  - передать в BOT 2;
  - назад.

`copyable_short_script` используется без markdown-оформления.

## Company Card Integration

`format_company_card` получает компактный блок:

- material total score и grade;
- component snapshot без перегруза;
- статус готовности плана звонка: `готов`/`не готов`.

Детализация остаётся только в отдельном sales intelligence workflow.

## Analytics Integration

Текущий lead scoring дообогащается сигналами sales intelligence:

- `+10`, если `material_score >= 70`
- `+5`, если `material_score >= 50`
- `-10`, если `material_score < 30`
- `+5`, если есть готовый `cold_call_plan`
- `+5`, если найден ЛПР
- `+5`, если `conscious_need` имеет `possible|strong`
- `+5`, если `here_and_now` имеет `possible|strong`

Дополнительные risks:

- низкое качество digital-материалов;
- не найден ЛПР;
- непонятна срочность;
- нет сайта/соцсетей/карт.

Чтобы избежать circular imports, интеграция делается через shared helper или lazy import внутри функций.

## Proposals Integration

`suggest_packages_for_company()` начинает учитывать sales intelligence:

- если `material_score < 30`: предлагать `audit_roadmap`, `maps_reputation`, `landing_start`;
- если низкий `website_score`: `landing_start`, `website_packaging`, `audit_roadmap`;
- если низкий `socials_score`: `smm_funnel`, `content_packaging`;
- если низкий `maps_score`: `maps_reputation`;
- если низкий `conversion_score`: `landing_start`, `crm_bot`, `audit_roadmap`;
- если низкий `trust_score`: `reputation_content`, nearest available reviews/maps package`.

Если точного package code нет в каталоге, используется ближайший существующий аналог без падения API.

## Bot2 Context Integration

`GET /api/bot2/companies/{company_id}/consultation-context` получает новый блок:

```json
{
  "sales_intelligence": {
    "material_score": {},
    "closing_criteria": {},
    "cold_call_plan_summary": null,
    "soprano_questions": {},
    "first_offer": null,
    "risks": [],
    "generation_mode": null
  }
}
```

Если плана нет:

- `material_score` и `closing_criteria` можно собрать on-demand;
- `cold_call_plan_summary = null`;
- `generation_mode = null`.

Bot2 не должен зависеть от обязательного наличия AI-generated плана.

## API Design

Добавляются endpoints:

- `GET /api/companies/{company_id}/sales-intelligence/material-score`
- `GET /api/companies/{company_id}/sales-intelligence/closing-criteria`
- `GET /api/companies/{company_id}/sales-intelligence/soprano-questions`
- `POST /api/companies/{company_id}/sales-intelligence/cold-call-plan`
- `GET /api/companies/{company_id}/sales-intelligence/latest`

`latest` возвращает:

- `material_score`
- `closing_criteria`
- `soprano_questions`
- `cold_call_plan`
- `saved_at`

Если сохранённого payload нет, `latest` может собрать данные on-demand и вернуть `saved_at = null`.

## Testing Design

### New Smoke Scripts

#### `scripts/smoke_material_scoring.py`

Проверяет:

- создание компании;
- создание website/contact/social/map contacts;
- создание `IntelligenceSnapshot` с сигналами;
- возврат `calculate_material_quality_score`;
- наличие component scores;
- корректный `grade`;
- печать `smoke_material_scoring ok`.

#### `scripts/smoke_call_plan.py`

Проверяет:

- создание компании с Checko/research context;
- расчёт closing criteria;
- генерацию SOPRANO questions;
- fallback при недоступном AI;
- `generation_mode == "fallback"`;
- наличие короткого `copyable_short_script`;
- HTTP 200 для новых endpoints;
- наличие `sales_intelligence` в Bot2 context;
- отсутствие полного call plan в `LeadInteraction` note;
- печать `smoke_call_plan ok`.

### Required Validation

После реализации должны быть прогнаны:

- `python -m compileall app alembic`
- существующие smoke scripts текущей ветки;
- `python scripts/smoke_material_scoring.py`
- `python scripts/smoke_call_plan.py`
- `python -c "from app.main import app; print(app.title)"`
- `python -c "from app.bot import main; print('bot ok')"`

Если каких-то старых smoke scripts нет в ветке, это должно быть явно отражено в финальном отчёте, а не скрыто удалением из документации.

## Documentation Updates

Нужно обновить:

- `README.md`
- `TASKS.md`
- `CHANGELOG.md`

README получает новый раздел про sales intelligence, material scoring, 5 критериев, SOPRANO, AI/fallback, Telegram workflow, API, Bot2/scoring/proposals integration и safety rules.

## Error Handling

- Отсутствие части данных не приводит к падению scoring или fallback plan generation.
- AI failures автоматически переводят генерацию в fallback mode.
- Невозможность merge в snapshot не должна ломать snapshot или endpoint.
- Telegram обработчики должны показывать понятные manager-facing сообщения, если данных мало.

## Open Implementation Decisions Resolved

- Хранение: только в существующем `IntelligenceSnapshot` через merge по ключу `sales_intelligence`.
- Основной источник контекста: агрегированный `company_context` из нескольких модулей.
- AI prompt isolation: через новый prompt builder, без переписывания старого call prep.
- Fallback обязателен и является first-class режимом, а не аварийным заглушечным текстом.
- Bot2 и API могут собирать sales intelligence on-demand, если persisted payload отсутствует.


## Additional Implementation Clarifications

1. Add internal CompanySalesContext DTO in schemas.py or service.py.
   Scoring functions must receive normalized dict/schema data, not raw ORM objects.

2. Every component score and total_score must be clamped to 0..100.

3. AI output must be parsed and validated into ColdCallPlan.
   If parsing or validation fails, fallback mode must be used automatically.

4. Avoid circular imports between analytics, proposals and sales_intelligence.
   Use lazy imports or small shared helpers when needed.

5. POST /api/companies/{company_id}/sales-intelligence/cold-call-plan accepts:
   {
     "use_ai": true,
     "force_regenerate": false,
     "niche": null
   }

6. If force_regenerate=false and latest valid cold_call_plan exists, endpoint may return saved/latest plan.
   If force_regenerate=true, regenerate and update sales_intelligence payload.

7. copyable_short_script must be plain text and suitable for direct manager copy-paste.
   No markdown table, no JSON, no headings longer than necessary.

8. Full cold call plan must never be stored as LeadInteraction note.
   Only short summary note is allowed.