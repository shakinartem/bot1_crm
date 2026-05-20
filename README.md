# SHARiK Sales Intelligence Bot

MVP Telegram-first CRM для холодных продаж стоматологическим клиникам. Бот помогает агентству «ШАРиК digital» хранить базу клиник, ЛПР, контакты, историю касаний, задачи менеджера, записи звонков и AI-подготовку к звонку.

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

```bash
alembic upgrade head
```

Для локального MVP приложение также создает таблицы при старте, но новые изменения схемы нужно проводить через Alembic.

## CRM-ядро

Основные сущности:

- `Company` — клиника или компания.
- `DecisionMaker` — ЛПР.
- `ContactPoint` — отдельная контактная точка: телефон, email, сайт, Telegram, WhatsApp, VK, Instagram, другое.
- `LeadInteraction` — касание: звонок, сообщение, email, встреча, консультация, КП, заметка.
- `FollowUpTask` — задача менеджера.
- `CallRecord` — запись звонка и будущая транскрибация.

## API

Health:

- `GET /health`
- `GET /api/health`

CRM:

- `GET /api/companies`
- `POST /api/companies`
- `GET /api/companies/{id}`
- `PATCH /api/companies/{id}`
- `DELETE /api/companies/{id}`
- `GET /api/companies/{id}/interactions`
- `POST /api/companies/{id}/interactions`
- `GET /api/companies/{id}/decision-makers`
- `POST /api/companies/{id}/decision-makers`
- `GET /api/tasks`
- `POST /api/tasks`
- `PATCH /api/tasks/{id}`
- `POST /api/imports/csv`
- `POST /api/companies/{id}/ai/call-prep`

## AI Providers

Переключаются через `AI_PROVIDER`:

- `fallback` — локальный понятный ответ без внешних запросов.
- `openrouter` — OpenRouter Chat Completions, нужен `OPENROUTER_API_KEY`.
- `ollama` — локальная Ollama API, настройте `OLLAMA_BASE_URL` и `OLLAMA_MODEL`.

Если ключей нет, бот и API не падают: используется fallback-подготовка.

## CSV импорт

Поддерживаемые колонки:

```text
name,legal_name,inn,ogrn,city,region,address,phone,website,social_links,maps_url,vk_url,instagram_url,telegram_url,rating,reviews_count,source,notes
```

Дубли пропускаются по `inn`, `phone`, `website`, `name`. Отчет содержит:

- `added`
- `skipped`
- `errors`

В Telegram отправьте CSV документом с подписью `import_csv`. В API используйте `POST /api/imports/csv`.

## Базовый Telegram-сценарий

1. Добавить компанию: `/new_company Название; телефон; сайт; город; заметки`
2. Посмотреть список: `/leads`
3. Открыть карточку: `/company 1`
4. Подготовить звонок: `/prepare_call 1`
5. Загрузить запись: отправить audio/voice/document с подписью `call:1`
6. Сохранить результат: `/call_result 1; назначена консультация`

## Документы проекта

- `PROJECT_CONTEXT.md` — продуктовый и архитектурный контекст.
- `TASKS.md` — текущий sprint/backlog.
- `CHANGELOG.md` — журнал изменений.

## Следующие этапы

- Стабилизировать Telegram CRM после последних изменений и зафиксировать smoke-check.
- Добавить сценарии добавления ЛПР и контактов прямо из карточки компании.
- История касаний и задачи менеджера в Telegram.
- Интеграция с БОТ 2 Consultation AI.
