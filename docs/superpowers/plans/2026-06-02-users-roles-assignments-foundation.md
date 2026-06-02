# Users, Roles, and Assignments Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add CRM users, lightweight roles, assignment/audit fields, minimal Telegram assignment flow, minimal API endpoints, Bot2 assignment context, and smoke coverage without disrupting existing MVP workflows.

**Architecture:** Keep `CRMUser` in `app/modules/crm/models.py` alongside `Company`, `FollowUpTask`, and `LeadInteraction`, while placing user lifecycle and assignment orchestration in `app/modules/users/service.py`. Extend current handlers and API additively so legacy records and existing flows remain valid through nullable fields and Telegram auto-create behavior.

**Tech Stack:** Python, FastAPI, Aiogram, SQLAlchemy async ORM, Alembic, Pydantic, SQLite

---

### Task 1: Add failing foundation smoke coverage

**Files:**
- Create: `scripts/smoke_users_roles.py`
- Modify: `scripts/smoke_bot2_context.py`

- [ ] **Step 1: Write the failing smoke script for CRM user creation and assignment**

Create assertions for:

```python
owner = await get_or_create_user_from_telegram(session, first_user)
assert owner.role == CRMUserRole.OWNER.value

manager = await get_or_create_user_from_telegram(session, second_user)
assert manager.role == CRMUserRole.MANAGER.value

assignment = await assign_company_to_user(session, company.id, manager.id, actor_user_id=owner.id)
assert assignment.assigned_user_id == manager.id
```

- [ ] **Step 2: Run the smoke script to verify it fails for missing users foundation**

Run: `python scripts/smoke_users_roles.py`
Expected: import or attribute failure because `CRMUser`, role enum, or assignment helpers do not exist yet

### Task 2: Add the CRM user model, role enum, and nullable assignment fields

**Files:**
- Modify: `app/modules/crm/models.py`
- Modify: `app/modules/crm/schemas.py`

- [ ] **Step 1: Add model-level failing coverage references by importing new fields in smoke/API paths**

Use the smoke expectations from Task 1 and extend API-facing schemas to expect:

```python
class CompanyRead(CompanyBase):
    assigned_user_id: int | None = None
    created_by_user_id: int | None = None
    updated_by_user_id: int | None = None
```

- [ ] **Step 2: Run compile/import checks to confirm model/schema symbols are still missing**

Run: `python -m compileall app`
Expected: compile failure or import failure until new enum and model fields are added consistently

- [ ] **Step 3: Add `CRMUserRole`, `CRMUser`, relationships, and nullable FK columns**

Implement:

```python
class CRMUserRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    RESEARCHER = "researcher"
    VIEWER = "viewer"
```

and nullable FK columns on `Company`, `FollowUpTask`, and `LeadInteraction`.

- [ ] **Step 4: Re-run compile to verify model and schema changes are consistent**

Run: `python -m compileall app`
Expected: PASS for model/schema layer

### Task 3: Add migration for users and assignment fields

**Files:**
- Create: `alembic/versions/0009_add_crm_users_and_assignments.py`

- [ ] **Step 1: Write migration to create `crm_users` and assignment columns with indexes**

Include:

```python
op.create_table("crm_users", ...)
op.add_column("companies", sa.Column("assigned_user_id", sa.Integer(), nullable=True))
op.add_column("tasks", sa.Column("assigned_user_id", sa.Integer(), nullable=True))
op.add_column("lead_interactions", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
```

- [ ] **Step 2: Run migration upgrade to verify the schema initially fails or needs fixes**

Run: `alembic upgrade head`
Expected: first pass may fail on naming mismatches or SQLite details and should be corrected before proceeding

- [ ] **Step 3: Fix migration until it upgrades cleanly**

Adjust table names, indexes, and downgrade logic to match actual ORM tables

- [ ] **Step 4: Re-run migration**

Run: `alembic upgrade head`
Expected: PASS

### Task 4: Add users schemas and service layer

**Files:**
- Create: `app/modules/users/__init__.py`
- Create: `app/modules/users/schemas.py`
- Create: `app/modules/users/service.py`
- Modify: `app/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add failing usage in smoke/API flow for user service functions**

Expected functions:

```python
get_or_create_user_from_telegram
get_user_by_telegram_id
get_user_by_id
list_users
update_user_role
assign_company_to_user
assign_task_to_user
get_user_companies
get_user_tasks
touch_user_last_seen
```

- [ ] **Step 2: Run the new smoke script to verify service functions are still missing**

Run: `python scripts/smoke_users_roles.py`
Expected: FAIL on missing `app.modules.users.service`

- [ ] **Step 3: Implement schemas, config parsing, and service logic**

Add config fields:

```python
default_new_user_role: str = Field(default="manager", alias="DEFAULT_NEW_USER_ROLE")
crm_auto_create_users: bool = Field(default=True, alias="CRM_AUTO_CREATE_USERS")
crm_owner_telegram_ids: str = Field(default="", alias="CRM_OWNER_TELEGRAM_IDS")
```

Implement role resolution, Telegram mapping, company/task assignment, and compact display helpers.

- [ ] **Step 4: Re-run the dedicated smoke script**

Run: `python scripts/smoke_users_roles.py`
Expected: some later-stage failures remain, but user creation and assignment service calls should now work

### Task 5: Add Telegram helper and minimal company assignment UI

**Files:**
- Modify: `app/utils/telegram.py`
- Modify: `app/modules/crm/keyboards.py`
- Modify: `app/modules/crm/handlers.py`

- [ ] **Step 1: Add failing integration expectations in smoke or handler imports**

Expected behavior:

```python
current_user = await get_current_crm_user(session, message)
assert current_user.telegram_user_id == message.from_user.id
```

- [ ] **Step 2: Run compile/import checks to verify helper/UI wiring is not complete yet**

Run: `python -m compileall app`
Expected: fail until helper and callback wiring are added consistently

- [ ] **Step 3: Implement `/start` touch flow, compact assigned-user display, and `assign to me` action**

Handler behavior:

```python
crm_user = await get_current_crm_user(session, message)
await assign_company_to_user(session, company_id, crm_user.id, actor_user_id=crm_user.id)
```

- [ ] **Step 4: Re-run compile checks**

Run: `python -m compileall app`
Expected: PASS

### Task 6: Add minimal API endpoints for users and company assignment

**Files:**
- Modify: `app/api/routes.py`

- [ ] **Step 1: Extend smoke coverage to call minimal API endpoints**

Add checks for:

```python
GET /api/users
GET /api/users/{id}
PATCH /api/users/{id}
POST /api/companies/{id}/assign
GET /api/users/{id}/companies
GET /api/users/{id}/tasks
```

- [ ] **Step 2: Run `python scripts/smoke_users_roles.py` to confirm API routes are missing**

Expected: FAIL with 404 or import errors for the new routes

- [ ] **Step 3: Implement the API routes using `users.service`**

Return Pydantic responses from the new user schemas and assignment result schema.

- [ ] **Step 4: Re-run the smoke script**

Run: `python scripts/smoke_users_roles.py`
Expected: API checks move to green or reveal only Bot2-context gaps

### Task 7: Extend Bot2 consultation context with assignment block

**Files:**
- Modify: `app/modules/crm/schemas.py`
- Modify: `app/modules/crm/service.py`

- [ ] **Step 1: Add failing expectation in Bot2 context smoke**

Expected:

```python
context = await build_bot2_consultation_context(session, company.id)
assert context.assignment.assigned_user_id == manager.id
```

- [ ] **Step 2: Run `python scripts/smoke_bot2_context.py` to verify the field is absent**

Expected: FAIL on missing `assignment`

- [ ] **Step 3: Implement assignment block schema and serialization**

Populate:

```python
{
    "assigned_user_id": ...,
    "assigned_user_name": ...,
    "assigned_user_role": ...,
    "created_by_user_id": ...
}
```

- [ ] **Step 4: Re-run Bot2 smoke**

Run: `python scripts/smoke_bot2_context.py`
Expected: PASS

### Task 8: Update docs and run verification suite

**Files:**
- Modify: `README.md`
- Modify: `TASKS.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Document the foundation feature and remaining next-phase work**

Update docs to describe users, roles, auto-create, assignment endpoints, and scope limits.

- [ ] **Step 2: Run the required verification suite**

Run:

```bash
python -m compileall app alembic
python scripts/smoke_users_roles.py
python scripts/smoke_bot2_context.py
python scripts/smoke_analytics.py
python -c "from app.main import app; print(app.title)"
python -c "from app.bot import main; print('bot ok')"
```

Expected: all commands pass cleanly

- [ ] **Step 3: Commit the finished foundation scope**

```bash
git add app alembic scripts README.md TASKS.md CHANGELOG.md .env.example docs/superpowers/specs/2026-06-02-users-roles-assignments-foundation-design.md docs/superpowers/plans/2026-06-02-users-roles-assignments-foundation.md
git commit -m "feat: add CRM users and assignments foundation"
```
