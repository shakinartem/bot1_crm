# TASKS — BOT 1 CRM

## Current Sprint

- [ ] Real Bot 2 API integration
- [ ] Contract generation draft
- [ ] Lead source analytics
- [ ] Website/social research enrichment
- [ ] Manager roles and multi-user CRM

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
- Company filters by status/city/priority
- Bot 2 handoff API ready
- Bot 2 handoff smoke check
- Manager daily digest
- Overdue tasks screen
- Today tasks screen
- Hot leads prioritization
- Stale leads screen
- Weekly sales summary
- Digest Telegram commands
- Digest API endpoints
- AI/rule-based daily recommendation
- Automatic morning digest
- Digest settings
- Bot 2 handoff API via `/api/bot2/*`
- Bot 2 consultation result -> CRM status / interaction / follow-up task mapping
- `GET /api/companies` filters by status/city/priority
- `scripts/smoke_bot2_handoff.py`
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
