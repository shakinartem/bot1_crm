# SHARiK Sales Intelligence Bot

MVP Telegram-бота для холодных продаж стоматологиям: CRM, ЛПР, контакты, история взаимодействий, CSV-импорт, AI-подготовка к звонку и хранение записей.

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Заполните `BOT_TOKEN` в `.env`.

## Запуск

API:

```bash
uvicorn app.main:app --reload
```

Telegram-бот:

```bash
python -m app.bot
```

Docker:

```bash
docker compose up --build
```

## Миграции

Создать/обновить базу:

```bash
alembic upgrade head
```

Для MVP приложение также создает таблицы при старте, чтобы локальный запуск был быстрым.

## AI Providers

Переключаются через `AI_PROVIDER`:

- `fallback` — локальный шаблонный ответ без внешних запросов.
- `openrouter` — OpenRouter Chat Completions, нужен `OPENROUTER_API_KEY`.
- `ollama` — локальная Ollama API, настройте `OLLAMA_BASE_URL` и `OLLAMA_MODEL`.

AI-подготовка строится функцией `build_cold_call_prompt(company_data)` и покрывает ФВ, ОП, доверие, ЛПР, здесь-и-сейчас, а также СОПРАНО.

## CSV импорт

Колонки:

```text
name,legal_name,inn,ogrn,city,address,phone,website,maps_url,vk_url,instagram_url,telegram_url,rating,reviews_count,source,notes
```

Дубли пропускаются по `phone`, `website`, `inn`. Отчет содержит:

- `added`
- `skipped`
- `errors`

В Telegram отправьте CSV документом с подписью `import_csv`. В API используйте `POST /api/imports/csv`.

## Сценарий звонка

1. Добавить компанию: `/new_company Название; телефон; сайт; город; заметки`
2. Посмотреть список: `/leads`
3. Открыть карточку: `/company 1`
4. Подготовить звонок: `/prepare_call 1`
5. Загрузить запись: отправить audio/voice/document с подписью `call:1`
6. Сохранить результат: `/call_result 1; назначена консультация`

Если результат — `назначена консультация`, система обновит статус, создаст interaction и задачу.

## Архитектура

- `app/modules/crm` — компании, ЛПР, взаимодействия, задачи.
- `app/modules/sales` — зарезервировано под расширение формулы продаж.
- `app/modules/ai` — abstraction layer и провайдеры.
- `app/modules/calls` — записи звонков и stub транскрибации.
- `app/modules/imports` — CSV импорт.
- `app/modules/files` — будущие политики хранения файлов.

## Следующие этапы

- Парсинг карт и обогащение компаний.
- Интеграция с ФНС для проверки юр. данных.
- Реальная транскрибация через `faster-whisper` или `whisper.cpp`.
- Интеграция телефонии.
- Расширение qualification pipeline и передача в отдельный бот консультаций через очередь/API.
