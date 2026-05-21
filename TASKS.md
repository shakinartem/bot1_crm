# TASKS — BOT 1 CRM

## Current Sprint

- [ ] Real Bot 2 API integration
- [ ] Contract generation draft
- [ ] Manager daily digest
- [ ] Lead source analytics
- [ ] Website/social research enrichment

## Backlog

- Add task reschedule workflow in Telegram.
- Split `app/api/routes.py` into domain modules.
- Move Telegram handlers into a more modular package structure.
- Add repository layer after service stabilization.
- Add tests for CRM services, export, handoff, and API.

## Done

- CSV import preview
- CSV column mapping
- CSV deduplication
- CSV import report
- CRM statistics screen
- Consultation handoff payload draft
- Company CSV export
- Export filters by status/city/source/priority
- Single company consultation package
- Mini audit AI draft
- Company markdown export
- Handoff payload v2
- Handoff JSON export
- MVP FastAPI + aiogram + SQLAlchemy + Alembic
- AI abstraction layer for OpenRouter, Ollama, and fallback
- Expanded CRM core with contacts, richer interactions, statuses, and tasks
- Telegram CRM flows for company cards, tasks, notes, contacts, decision makers, search, and AI call prep

## Bugs

- Recheck Telegram text rendering on Windows console after future edits.
- Recheck Alembic batch migration behavior on clean SQLite and existing DB.

## Future Integrations

- Bot 2 Consultation AI handoff via real API/events/export.
- Clinic enrichment from website/social/maps research.
- Legal-data verification via ФНС.
- Transcription via `faster-whisper` or `whisper.cpp`.
- Telephony integration.
