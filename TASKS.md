# TASKS - BOT 1 CRM

## Current Sprint

- [ ] Manager roles and multi-user CRM
- [ ] Real document templates with реквизиты
- [ ] Real Bot 2 push integration
- [ ] Advanced conversion attribution
- [ ] External maps/reviews enrichment
- [ ] Batch intelligence enrichment
- [ ] Real FNS/DaData credentials testing
- [ ] Real Yandex/Google search provider testing

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
- Bot 2 consultation context endpoint
- Bot 2 consultation context smoke check
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
- Service package catalog
- Package suggestion workflow
- Manual package selection
- Commercial proposal draft generation
- Contract draft generation
- Service appendix generation
- Proposal/contract file export
- Proposal history
- Proposal API endpoints
- Proposal smoke check
- CRM funnel analytics
- Lead source analytics
- City/region analytics
- Rule-based lead scoring
- Cold base screen
- Score block in company card
- Digest scoring integration
- Analytics CSV export
- Analytics API endpoints
- Analytics smoke check
- Website research enrichment
- Enrichment snapshots
- Social/contact/map detection
- Website signals and hypotheses
- AI enrichment summary
- Research Telegram workflow
- Enrichment API endpoints
- Enrichment integration with call prep
- Enrichment integration with proposals
- Enrichment integration with scoring
- Enrichment Bot2 context block
- Enrichment smoke check
- INN-first intelligence pipeline
- Legal lookup provider interface
- Mock legal provider
- Search provider interface
- Mock search provider
- Website resolver by INN and legal name
- Site parser for contacts/socials/signals
- Intelligence Telegram workflow
- Intelligence API endpoints
- Intelligence smoke check
- Intelligence integration with call prep/proposals/scoring/Bot2 context
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
- Legal-data verification via ФНС.
- Transcription via `faster-whisper` or `whisper.cpp`.
- Telephony integration.
- Legal discovery module
- Mock legal discovery provider
- Legal discovery preview/import
- Research queue
- Safe fetch/browser abstraction
- Website resolver by INN/legal name
- Site parser for contacts/socials/signals
- Research Telegram workflow
- Research API endpoints
- Research batch CLI script
- Research smoke checks
- Real API-FNS/DaData credentials testing
- Real Yandex/Google search provider testing
- Optional Crawlee backend experiment
- Optional Camoufox renderer experiment without bypass logic
- Batch research scheduling
