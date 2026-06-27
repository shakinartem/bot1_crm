# Design Report: Telegram CSV Import как основной CRM-сценарий

> Дата: 2026-06-20
> Ветка: `codex-proposals-contract-drafts`
> Коммит: a46d263

## 1. Существующие import-модули

В `app/modules/imports/` расположены два параллельных потока:

### 1.1. Новый поток — `csv_company_import.py` (867 строк)

**Назначение:** Легковесный модуль для импорта компаний из CSV.

**Экспортируемые символы:**
- `ImportMode` — `Literal["create_only", "update_existing", "upsert"]`
- `RowResult`, `CsvPreviewResult`, `CsvCompanyImportResult` — dataclass'ы
- `detect_csv_dialect()` — определение кодировки (UTF-8, UTF-8 BOM, CP1251) и разделителя (`,`, `;`, `\t`)
- `normalize_csv_headers()` — маппинг русских/английских заголовков на канонические имена
- `parse_company_csv()` — парсинг CSV bytes → list[dict]
- `preview_csv()` — превью без импорта
- `import_companies_from_csv()` — асинхронный импорт в БД с дедупликацией

**Колонки:** display_name, legal_name, inn, ogrn, city, region, address, phone, email, website, checko_profile_url, yandex_maps_url, status, priority, notes, source.

**Используется:** Telegram handlers (`handlers.py`) + API (`routes.py`).

### 1.2. Старый поток — `service.py` (708 строк)

**Назначение:** Предыдущая версия сервиса импорта (legacy).

**Отличия от нового потока:**
- Использует `DeduplicationIndex` (in-memory индекс из `dedupe.py`)
- Поддерживает дополнительные колонки: `social_links`, `vk_url`, `instagram_url`, `telegram_url`, `rating`, `reviews_count`
- Возвращает `dict` вместо dataclass'ов
- Функции: `preview_companies_from_csv()`, `import_companies_from_csv()`

**Не ломается:** Старый поток продолжает существовать и экспортироваться через `app/api/routes.py` (строка 59 — `from app.modules.imports.service import import_companies_from_csv, preview_companies_from_csv, save_import_file`), но не используется в новых API эндпоинтах.

### 1.3. Вспомогательные модули

- **`dedupe.py`** — дедупликация компаний через `CompanyIdentity` и `DeduplicationIndex`. Используется обоими потоками (`service.py` использует напрямую, `csv_company_import.py` — через `build_company_identity`).
- **`handlers.py`** — Telegram handler'ы на aiogram. Использует новый поток.
- **`states.py`** — FSM: `ImportCsvStates.awaiting_file → awaiting_commit`.
- **`keyboards.py`** — InlineKeyboardMarkup для выбора режима импорта и отчёта.

## 2. Что можно переиспользовать

1. **`csv_company_import.py`** — полностью готов; используется как Telegram-сценарием, так и API.
2. **`dedupe.build_company_identity()`** — используется для дедупликации в новом потоке.
3. **`app.modules.research.phone_parser.normalize_phone_ru()`** — нормализация телефонов.
4. **`app.modules.research.website_resolver.normalize_website_url()`** / `is_denied_website_url()` — валидация URL.
5. **`app.modules.crm.service.create_company()`** — создание компании.
6. **`app.modules.lead_fit.service.recalculate_companies_lead_fit()`** — расчёт lead fit после импорта.
7. **API эндпоинты** (1163-1216) — уже существуют, работают через новый поток.

## 3. Модели для расширения

**Никакие модели не требуют расширения.**

Существующие модели полностью покрывают сценарий:
- `Company` — хранит name, legal_name, inn, ogrn, phone, email, website и т.д.
- `ContactPoint` — для дополнительных контактов (email, maps_url, phone dupes)
- `LeadInteraction` — для логирования импорта

Если потребуется в будущем:
- `email` поле в `Company` — сейчас email сохраняется через `ContactPoint`, что нормально.

## 4. Telegram CSV Flow

```
[Пользователь] → /import_csv или кнопка "📥 Импорт CSV"
    ↓
[Бот показывает инструкцию] → ждёт файл
    ↓
[Пользователь отправляет CSV]
    ↓
[Бот скачивает файл] → preview_csv()
    ↓
[Бот показывает предпросмотр]:
  • количество строк
  • кол-во с ИНН/телефоном/сайтом
  • распознанные колонки
  • первые 5 строк
  • предупреждения
  • кнопки выбора режима: "Только новые" / "Обновить существующие" / "Создать/обновить"
  • кнопки "Импортировать" / "Отмена"
    ↓
[Пользователь выбирает режим] → inline callback
    ↓
[Пользователь нажимает "Импортировать"]
    ↓
[Бот запускает import_companies_from_csv()]
    ↓
[Бот показывает отчёт]:
  • всего строк, импортировано, обновлено, дублей, пропущено, ошибок
  • группы лидов после импорта
  • кнопки: "Группы лидов", "В главное меню"
```

## 5. API Contract

### POST /api/companies/import/csv/preview

**Request:** `multipart/form-data` с полем `file` (CSV файл).

**Response (200):**
```json
{
  "detected_columns": ["name", "inn", "phone"],
  "total_rows": 10,
  "sample_rows": [
    {
      "row_number": 2,
      "legal_name": "—",
      "display_name": "ООО Тест",
      "inn": "7712345678",
      "phone": "+7 (495) 123-45-67",
      "website": "example.ru",
      "city": "Москва"
    }
  ],
  "inn_count": 5,
  "phone_count": 8,
  "website_count": 3,
  "warnings": [],
  "can_import": true
}
```

### POST /api/companies/import/csv

**Request:** `multipart/form-data` с полем `file` (CSV файл) + query params:
- `mode` (string, optional): `create_only | update_existing | upsert` (default: `upsert`)
- `source` (string, optional): источник (default: `api_upload`)

**Response (200):**
```json
{
  "total_rows": 10,
  "imported_count": 5,
  "updated_count": 2,
  "duplicate_count": 1,
  "skipped_count": 1,
  "error_count": 1,
  "warnings": ["..."],
  "row_results": [
    {"row_number": 2, "status": "imported", "company_id": 1, "inn": "7712345678", "legal_name": "ООО Тест", "message": "Создана компания #1"}
  ]
}
```

## 6. Миграции

**Не требуются.**

Текущая схема БД (модели `Company`, `ContactPoint`, `LeadInteraction`) полностью покрывает сценарий CSV-импорта. Поле `email` отсутствует напрямую в `Company` — email сохраняется через `ContactPoint(type=EMAIL)`, что является корректным для текущей архитектуры.

## 7. Smoke тесты

### Существующие:
- `scripts/smoke_csv_company_import.py` — 17 тестов (парсинг, диалекты, колонки, кодировки, превью, структура данных)
- `scripts/smoke_csv_company_import_api.py` — 3 теста (preview_csv, CsvCompanyImportResult, ImportMode)

### Изменения:
- **Не требуются** — тесты уже покрывают новый поток.
- Smoke‑скрипты используют `csv_company_import.py` (новый поток).

## 8. Заключение

Архитектура уже подготовлена:
- ✅ Новый модуль `csv_company_import.py` существует и используется
- ✅ API эндпоинты существуют и работают через новый поток
- ✅ Telegram handlers используют новый поток
- ✅ Старый поток (`service.py`) остаётся без изменений
- ✅ Миграции не требуются
- ✅ Smoke тесты покрывают новый поток

**Текущее состояние:** Новый поток уже является основным. Telegram CSV импорт уже использует `csv_company_import.py`. Никаких дополнительных изменений для переключения не требуется — всё уже работает.