# CHANGELOG

## Unreleased

- Added richer Telegram CRM company cards with source, contacts, recent interaction, and next action context.
- Added company inline actions for call logging, notes, decision makers, contacts, status updates, tasks, history, and AI preparation.
- Added Telegram workflows for call outcomes, note capture, decision makers, contacts, status changes, company tasks, history view, and task completion.
- Improved Telegram search and today's tasks dashboard for faster manager workflows.
- Fixed damaged newline formatting across Python, markdown, env, and requirements files.
- Fixed broken Russian text strings in Telegram handlers.
- Added smoke_check.py for basic import validation.
- Validated syntax with compileall.
- Fixed source formatting/newline issues after CRM core expansion.
- Fixed syntax risks in CRM services and migration files.
- Fixed API handlers to avoid mutating Pydantic request payloads directly.
- Validated app imports and migration readiness.
- Added Telegram CRM menu flows for companies, search, and today's tasks.
- Added inline buttons on company cards for refresh, AI call prep, task view, and quick call outcomes.
- Added step-by-step Telegram FSM for company creation.
- Escaped company card HTML output to avoid broken formatting from user-entered data.
- Added `PROJECT_CONTEXT.md` with product and architecture context for BOT 1.
- Added `TASKS.md` as the working backlog for the CRM MVP.
- Added expanded CRM statuses, priorities, contact types, interaction results, and task statuses.
- Added `ContactPoint` model for phones, email, website, messengers, social links, and other contacts.
- Added CRM fields for company `region`, `social_links`, and `priority`.
- Added `source`, `created_at`, and `updated_at` fields to decision makers.
- Added decision-maker linkage, next action, next action date, and author fields to interactions.
- Added `due_at`, `priority`, and `completed_at` fields to follow-up tasks while keeping compatibility with existing `tasks` table.
- Added Alembic migration `0002_expand_crm_core`.
- Added base CRM API endpoints for companies, interactions, decision makers, tasks, CSV import, and AI call preparation.
- Changed CSV deduplication to include company name in addition to INN, phone, and website.
- Changed AI call preparation prompt to include decision makers and interaction history.
- Fixed unreadable Russian text in CRM services, Telegram handlers, CSV importer, call transcription stub, AI prompts, fallback provider, and README.
