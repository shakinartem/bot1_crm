# TASKS - BOT 1 CRM

## Current Sprint

- [ ] Improve PDF visual design
- [ ] Add real agency document templates
- [ ] Add manager workspace full UI
- [ ] Live Checko testing
- [ ] Live Yandex testing
- [ ] Full RBAC
- [ ] Web dashboard planning

## Backlog

- Add task reschedule workflow in Telegram.
- Split `app/api/routes.py` into domain modules.
- Move Telegram handlers into a more modular package structure.
- Add repository layer after service stabilization.
- Add tests for CRM services, export, handoff, and API.

## Done

- Fixed Checko validation for candidates without INN on list page.
- Added real Checko profile URL validation.
- Added Checko region UI filtering diagnostics.
- Improved Checko profile enrichment flow.
- CRMUser model
- User roles foundation
- Telegram user auto-create
- Company assignment
- Task assignment
- Interaction attribution
- Minimal user assignment API endpoints
- Bot2 assignment context
- Users roles smoke test
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
- Sales intelligence schemas and scoring
- Sales intelligence API endpoints
- Sales intelligence Telegram workflow
- Sales intelligence Bot 2 context block
- Sales intelligence cold-call-plan smoke check
- Sales intelligence integration with analytics and proposals
- Source formatting normalization
- CompanyInsightSnapshot model
- Company insights service
- Company insights API endpoints
- Sales intelligence persistence through CompanyInsightSnapshot
- Company insights smoke test
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
- Russian localization for sales intelligence
- Russian package display names
- Bot2 auth documentation
- Commercial proposal markdown flow retained as current draft format
- Telegram document section placeholder
- Grouped Telegram main menu
- Search companies menu entry
- Localization smoke test
- Fixed Checko category/header parsing
- Added Checko region post-filter
- Improved Checko preview counters
- Localized Checko preview buttons
- Hardened Checko import safety
- Added Checko live debug snapshots
- Added Checko parser diagnostics
- Added fallback company link extraction
- Added zero-result debug preview

## Bugs

- Recheck Telegram text rendering on Windows console after future edits.
- Recheck Alembic batch migration behavior on clean SQLite and existing DB.

## Future Integrations

- Bot 2 Consultation AI handoff via real API/events/export.
- Legal-data verification via ФНС.
- Transcription via `faster-whisper` or `whisper.cpp`.
- Telephony integration.
- Legal discovery module hardening
- Research queue scheduling
- Batch research scaling
