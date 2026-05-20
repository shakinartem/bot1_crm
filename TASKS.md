# TASKS — BOT 1 CRM

## Current Sprint

- [x] Repair formatting and syntax after stage 1 push.
- [x] Validate Python imports and compileall.
- [x] Validate Alembic migration formatting.
- [x] Add Telegram CRM menu.
- [x] Add company card inline buttons.
- [x] Add company creation FSM.

## Backlog

- Добавить пошаговое добавление компании через FSM.
- Добавить Telegram-кнопки карточки компании.
- Добавить сценарий добавления ЛПР из карточки.
- Добавить сценарий добавления контакта из карточки.
- Добавить список задач на сегодня.
- Добавить предпросмотр CSV перед подтверждением импорта.

## Done

- Создан MVP FastAPI + aiogram + SQLAlchemy + Alembic.
- Добавлен AI abstraction layer для OpenRouter, Ollama и fallback.
- Добавлен CSV импорт с дедупликацией.
- Этап 1: расширено CRM-ядро, добавлены `ContactPoint`, новые поля ЛПР, взаимодействий и задач.
- Этап 1: добавлены `PROJECT_CONTEXT.md`, `TASKS.md`, `CHANGELOG.md`.
- Этап 1: исправлена кодировка пользовательских сообщений в текущих Telegram handlers.
- Stabilization: repaired source formatting, syntax risks, API payload handling, and Alembic batch settings.
- Telegram CRM: added main menu flows, company card inline actions, tasks digest, and step-by-step company creation FSM.

## Bugs

- Проверить кодировку сообщений Telegram в Windows-консоли после правок.
- Проверить Alembic batch migration на чистой SQLite и существующей базе.

## Technical Debt

- Постепенно разделить `app/api/routes.py` на модули `companies`, `interactions`, `decision_makers`, `tasks`, `imports`, `ai`.
- Вынести Telegram handlers в структуру `app/bot/handlers` без резкого переноса.
- Добавить repository-слой после стабилизации сервисов.
- Добавить тесты для CSV импорта, CRM сервисов и API.

## Future Integrations

- Передача клиента в БОТ 2 Consultation AI через API/events/export.
- Парсинг карт и обогащение клиник.
- Проверка юр. данных через ФНС.
- Транскрибация через `faster-whisper` или `whisper.cpp`.
- Интеграция телефонии.
