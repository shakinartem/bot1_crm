# Users, Roles, and Assignments Foundation Design

## Goal

Add a stable multi-user foundation to the CRM without changing the current MVP interaction model. This stage introduces CRM users, lightweight roles, assignment fields, Telegram-aware user mapping, minimal assignment UI, minimal API support, and smoke coverage.

## Confirmed Scope

This stage includes:

- `CRMUser` model and `CRMUserRole`
- nullable assignment/audit user foreign keys on `Company`, `FollowUpTask`, and `LeadInteraction`
- Alembic migration `0009_add_crm_users_and_assignments.py`
- `app/modules/users/{__init__.py,schemas.py,service.py}`
- Telegram auto-create/touch helper
- minimal Telegram integration: `/start`, company card assigned-user display, `assign to me`
- company assignment note in `LeadInteraction`
- minimal user/assignment API
- Bot2 context assignment block
- `scripts/smoke_users_roles.py`
- README, TASKS, and CHANGELOG updates

This stage explicitly excludes:

- full "Мои лиды" Telegram workflow
- selecting any manager from Telegram UI
- strict RBAC enforcement
- manager analytics dashboard
- workload or performance reports
- assignment automation after import
- advanced manager filters for hot, overdue, or today-call views

## Architecture

`CRMUser` will be added to `app/modules/crm/models.py` because the assigned entities already live in the CRM model set. User lifecycle, Telegram mapping, and assignment orchestration will live in `app/modules/users/service.py`.

This keeps the data model additive while avoiding an early split of tightly-related persistence models across modules. The users module remains the main service boundary for future RBAC, richer Telegram flows, and web UI management.

## Data Model

### CRMUser

`CRMUser` fields:

- `id`
- `telegram_user_id`, nullable, unique
- `username`, nullable
- `full_name`, nullable
- `role`
- `is_active`, default `true`
- `created_at`
- `updated_at`
- `last_seen_at`, nullable

### Roles

Roles are a lightweight enum/constant set:

- `owner`
- `admin`
- `manager`
- `researcher`
- `viewer`

At this stage roles are informational and support safe defaults plus future expansion. They do not introduce strict access denial across the system.

### Assignment and Attribution Fields

`Company` gains:

- `assigned_user_id -> crm_users.id`, nullable
- `created_by_user_id -> crm_users.id`, nullable
- `updated_by_user_id -> crm_users.id`, nullable

`FollowUpTask` gains:

- `assigned_user_id -> crm_users.id`, nullable
- `created_by_user_id -> crm_users.id`, nullable

`LeadInteraction` gains:

- `created_by_user_id -> crm_users.id`, nullable

Legacy rows remain valid because all fields are nullable.

## Telegram User Creation Rules

The helper will resolve a Telegram actor into a `CRMUser` with these rules:

1. If a matching `telegram_user_id` exists, update `username`, `full_name`, and `last_seen_at`.
2. If no user exists and the Telegram ID is the first CRM user, create an `owner`.
3. If no user exists and the Telegram ID is listed in `CRM_OWNER_TELEGRAM_IDS`, create an elevated user. For this foundation stage, IDs from this list create `owner`.
4. Otherwise create a user with `DEFAULT_NEW_USER_ROLE`, defaulting to `manager`.

`CRM_AUTO_CREATE_USERS` will remain enabled by default in `.env.example`. The helper is intentionally soft-fail friendly for current workflows.

## Service Boundaries

### `app/modules/users/service.py`

Responsibilities:

- get or create CRM users from Telegram payloads
- list and fetch users
- update role and active state
- assign companies
- assign tasks
- return user-bound companies and tasks
- update `last_seen_at`

### Telegram Helper

A minimal helper will accept `Message` or `CallbackQuery` style input, extract the Telegram user, call the service, touch activity, and return the current `CRMUser`.

## Telegram Integration

### `/start`

When a user starts the bot:

- resolve current `CRMUser`
- auto-create if needed
- touch `last_seen_at`
- continue current menu flow as before

### Company Card

The company card will display assigned user compactly:

- assigned user's full name if present
- fallback to username
- fallback to `не назначен`

### Assign to Me

Add a company-card action for self-assignment:

- current Telegram user is resolved via helper
- company is assigned to `current_user.id`
- assignment note is appended to `LeadInteraction`
- company card is re-rendered

No manager-picker UI is added in this phase.

## API Surface

New endpoints:

- `GET /api/users`
- `GET /api/users/{user_id}`
- `PATCH /api/users/{user_id}`
- `POST /api/companies/{company_id}/assign`
- `GET /api/users/{user_id}/companies`
- `GET /api/users/{user_id}/tasks`

These endpoints are foundation-only and do not introduce full authentication or policy enforcement.

## Bot2 Context

The Bot2 consultation context will gain:

- `assigned_user_id`
- `assigned_user_name`
- `assigned_user_role`
- `created_by_user_id`

This information will be grouped in an `assignment` block so downstream consumers can bind consultation work to a human owner later.

## Testing Strategy

Primary verification for this stage:

- compile all Python modules
- migration upgrade
- dedicated `smoke_users_roles.py`
- existing `smoke_bot2_context.py`
- existing `smoke_analytics.py`
- import checks for FastAPI app and bot entrypoint

`smoke_users_roles.py` will verify:

- first Telegram user becomes owner
- second Telegram user gets default role
- company assignment works
- user company lookup works
- task assignment works
- user task lookup works
- interaction attribution persists
- minimal API routes respond correctly
- Bot2 assignment block is present

## Risks and Mitigations

### Risk: current workflows accidentally become dependent on CRM user presence

Mitigation:

- helper auto-creates users
- all new FK fields stay nullable
- existing flows remain compatible

### Risk: circular imports between CRM and users services

Mitigation:

- keep persistence model in `crm.models`
- keep user orchestration in `users.service`
- use narrow imports in handlers/helpers where needed

### Risk: schema drift between API and Bot2 context

Mitigation:

- define explicit Pydantic schemas for user reads and assignment responses
- extend Bot2 context schemas in one place

## Out of Scope for Next Phase

The next stage should build on this foundation with:

- richer Telegram team workflows
- manager list selection and reassignment UI
- real RBAC checks
- manager analytics dashboard
- workload and performance reporting
- import-time assignment automation
