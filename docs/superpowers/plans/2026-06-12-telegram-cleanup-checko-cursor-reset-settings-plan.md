# Telegram Cleanup, Checko Cursor, Reset, and Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify Telegram live UX around one discovery entrypoint, add paginated Checko discovery cursors, expand reset into a safe full dev cleanup workflow, and finish the Telegram settings plus smoke/docs pass.

**Architecture:** Keep Telegram live UX and discovery state in the existing bot handlers, but move persistence for Checko page progress into a dedicated cursor table so next-batch search can survive repeated previews/imports. Centralize destructive reset behavior in `admin_reset.service` and expose it through both API and Telegram only behind explicit admin + env guards. Keep smoke tests offline and fixture-driven so the new flow remains testable without live Checko or Telegram access.

**Tech Stack:** Python, aiogram, SQLAlchemy async, Alembic, FastAPI, pytest-style smoke scripts, SQLite for local smoke runs.

---

### Task 1: Remove mock/dev from live Telegram discovery and make one search entrypoint

**Files:**
- Modify: `app/modules/crm/keyboards.py`
- Modify: `app/modules/crm/handlers.py`
- Modify: `app/modules/legal_discovery/keyboards.py`
- Modify: `app/modules/legal_discovery/handlers.py`
- Modify: `app/modules/legal_discovery/service.py`
- Modify: `app/bot.py`
- Test: `scripts/smoke_legal_discovery.py`
- Test: `scripts/smoke_checko_html.py`

- [ ] **Step 1: Write the failing smoke assertions**

Add assertions that:
- `main_menu()` contains only one discovery entrypoint text, `🔍 Поиск компаний`.
- `search_import_menu_markup()` no longer shows a live Telegram path for `🔍 Поиск и импорт`.
- `discovery_provider_markup()` does not expose `Mock / Dev` to normal Telegram users.
- the old callbacks `menu:search_import:*` and `discovery:provider:mock` still resolve to the live discovery flow only when invoked by legacy paths.

- [ ] **Step 2: Run the smoke scripts to verify the current behavior fails**

Run:
```bash
py scripts/smoke_legal_discovery.py
py scripts/smoke_checko_html.py
```
Expected: failures showing the current Telegram UX still exposes the wrong buttons and/or mock provider path.

- [ ] **Step 3: Implement the minimal Telegram UX rewrite**

Update the menu builders and handlers so the live path is:
- `/start` -> `🔍 Поиск компаний` -> OKVED/niche -> limit -> preview -> import.

Keep legacy callback aliases working by mapping them into the same live discovery handler, but do not render them in normal Telegram keyboards.

Use the existing discovery handlers rather than adding a second live flow. The old `search_import` button becomes a compatibility alias only, not a visible entrypoint.

- [ ] **Step 4: Re-run the smoke scripts**

Run:
```bash
py scripts/smoke_legal_discovery.py
py scripts/smoke_checko_html.py
```
Expected: pass, with no Mock / Dev buttons in live Telegram markup and one visible discovery entrypoint.

- [ ] **Step 5: Commit the UX-only change**

```bash
git add app/modules/crm/keyboards.py app/modules/crm/handlers.py app/modules/legal_discovery/keyboards.py app/modules/legal_discovery/handlers.py app/modules/legal_discovery/service.py app/bot.py scripts/smoke_legal_discovery.py scripts/smoke_checko_html.py
git commit -m "fix: unify telegram discovery entrypoint"
```

### Task 2: Add Checko cursor persistence and next-batch pagination

**Files:**
- Create: `app/modules/legal_discovery/models.py`
- Modify: `app/modules/legal_discovery/service.py`
- Modify: `app/modules/legal_discovery/handlers.py`
- Modify: `app/modules/legal_discovery/keyboards.py`
- Modify: `app/modules/legal_discovery/schemas.py`
- Modify: `app/api/routes.py`
- Modify: `app/modules/crm/telegram_ux.py`
- Modify: `app/modules/crm/telegram_lead_ux_handlers.py`
- Create: `alembic/versions/0011_add_legal_discovery_cursors.py`
- Test: `scripts/smoke_discovery_cursor.py`
- Test: `scripts/smoke_legal_discovery.py`

- [ ] **Step 1: Write failing cursor tests**

Create tests in the smoke script that assert:
- first discovery preview starts at `page=1` and stores `current_page=1`;
- `➡️ Следующая пачка` advances to `page=2` without asking for OKVED again;
- `🔄 Начать сначала` resets the cursor back to `page=1`;
- preview counters include `Страница Checko`, `Следующая страница`, `Новых / дублей`, and `Импортируемых active_new`;
- repeated imports on the same page do not crash when duplicates dominate.

- [ ] **Step 2: Run the new smoke script and watch it fail**

Run:
```bash
py scripts/smoke_discovery_cursor.py
```
Expected: failure because the cursor table and next-batch behavior do not exist yet.

- [ ] **Step 3: Add the cursor model and migration**

Create a dedicated `legal_discovery_cursors` table with:
- provider
- okved_code
- niche_label
- query_hash
- current_page
- last_profile_url
- last_inn
- last_ogrn
- imported_count
- previewed_count
- duplicate_count
- created_at
- updated_at
- reset_at

The migration should leave existing discovery tables intact and only add the new cursor table plus indexes/uniqueness needed to find a cursor by `(provider, okved_code, query_hash)`.

- [ ] **Step 4: Thread cursor state through discovery service and handlers**

Update discovery preview/import logic so:
- the first search creates or resets a cursor at page 1;
- the next batch uses `current_page + 1`;
- preview text shows page/counter summary;
- import updates `imported_count` and preserves the page state;
- `discovery:next_batch` and `discovery:restart` callbacks are wired into the preview keyboard.

Keep the current import filtering rules unchanged: lead fit still runs after import, not before.

- [ ] **Step 5: Re-run cursor and discovery smokes**

Run:
```bash
py scripts/smoke_discovery_cursor.py
py scripts/smoke_legal_discovery.py
```
Expected: pass, with page progression, reset-to-page-1, and duplicate-heavy pages handled safely.

- [ ] **Step 6: Commit the cursor work**

```bash
git add app/modules/legal_discovery/models.py app/modules/legal_discovery/service.py app/modules/legal_discovery/handlers.py app/modules/legal_discovery/keyboards.py app/modules/legal_discovery/schemas.py app/api/routes.py app/modules/crm/telegram_ux.py app/modules/crm/telegram_lead_ux_handlers.py alembic/versions/0011_add_legal_discovery_cursors.py scripts/smoke_discovery_cursor.py scripts/smoke_legal_discovery.py
git commit -m "feat: add checko discovery cursor"
```

### Task 3: Expand reset into safe crm_only and all_data workflows

**Files:**
- Modify: `app/modules/admin_reset/service.py`
- Modify: `app/modules/crm/telegram_ux.py`
- Modify: `app/modules/crm/telegram_lead_ux_handlers.py`
- Modify: `app/modules/crm/keyboards.py`
- Modify: `app/api/routes.py`
- Create: `scripts/reset_dev_database.py`
- Create: `scripts/smoke_reset_clean_import.py`
- Modify: `scripts/smoke_admin_reset.py`
- Modify: `scripts/smoke_legal_discovery.py`
- Modify: `scripts/smoke_checko_html.py`
- Modify: `README.md`
- Modify: `TASKS.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write failing reset coverage**

Add smoke assertions that:
- `crm_only` requires exact text `RESET CRM`;
- `all_data` requires exact text `RESET ALL DATA`;
- reset buttons only render for admins when `ALLOW_DB_RESET=true`;
- `all_data` clears companies, contacts, tasks, interactions, insights, research jobs, proposals, discovery cursors, and debug files;
- `keep_users=true` preserves CRM users by default;
- the first import after reset reports `new=N` and `duplicate=0`.

- [ ] **Step 2: Run the current reset smoke and confirm the gaps**

Run:
```bash
py scripts/smoke_admin_reset.py
```
Expected: the current service is too narrow for the full cleanup requirements.

- [ ] **Step 3: Implement the reset service contract**

Update `reset_database` so it supports:
- `mode="crm_only"` and `mode="all_data"`
- `keep_users=True` by default
- explicit confirmation string checks
- optional `clear_debug_files`
- detailed summary counts for deleted rows and files

The service should delete all CRM/discovery/research/proposal/insight data, but preserve schema and `alembic_version`.

- [ ] **Step 4: Update Telegram and API reset flows**

Expose the safe reset flow from Telegram settings only for admins with `ALLOW_DB_RESET=true`.

Add the API payload shape:
```json
{
  "mode": "crm_only",
  "keep_users": true,
  "clear_debug_files": true,
  "confirmation": "RESET CRM"
}
```

and the full-reset variant:
```json
{
  "mode": "all_data",
  "keep_users": true,
  "clear_debug_files": true,
  "confirmation": "RESET ALL DATA"
}
```

Add the CLI script `scripts/reset_dev_database.py` with explicit `--crm-only` / `--all-data` / `--keep-users` / `--clear-debug-files` / `--confirm` flags, and fail closed when the confirmation text is missing or incorrect.

- [ ] **Step 5: Add a clean-import smoke**

Create `scripts/smoke_reset_clean_import.py` to verify:
- reset clears everything but schema;
- `alembic_version` remains present;
- `/start` can recreate/update the CRM user;
- the first post-reset import shows `new_count=N`, `duplicate_count=0`, `imported_count=N`.

- [ ] **Step 6: Re-run reset and import smokes**

Run:
```bash
py scripts/smoke_admin_reset.py
py scripts/smoke_reset_clean_import.py
py scripts/smoke_legal_discovery.py
py scripts/smoke_checko_html.py
```
Expected: pass, with summary counts matching the deleted data and the clean post-reset import state.

- [ ] **Step 7: Commit the reset work**

```bash
git add app/modules/admin_reset/service.py app/modules/crm/telegram_ux.py app/modules/crm/telegram_lead_ux_handlers.py app/modules/crm/keyboards.py app/api/routes.py scripts/reset_dev_database.py scripts/smoke_reset_clean_import.py scripts/smoke_admin_reset.py scripts/smoke_legal_discovery.py scripts/smoke_checko_html.py README.md TASKS.md CHANGELOG.md
git commit -m "feat: add safe dev reset flow"
```

### Task 4: Finish Telegram settings, read-only search config, and docs

**Files:**
- Modify: `app/modules/crm/handlers.py`
- Modify: `app/modules/crm/telegram_ux.py`
- Modify: `app/modules/crm/telegram_lead_ux_handlers.py`
- Modify: `app/modules/crm/keyboards.py`
- Modify: `scripts/smoke_telegram_settings.py`
- Modify: `scripts/smoke_telegram_lead_groups.py`
- Modify: `scripts/smoke_lead_fit.py`
- Modify: `scripts/smoke_company_regions.py`
- Modify: `scripts/smoke_legal_discovery.py`
- Modify: `README.md`
- Modify: `TASKS.md`
- Modify: `CHANGELOG.md`
- Create: `scripts/smoke_telegram_settings.py`

- [ ] **Step 1: Write failing settings assertions**

Add smoke coverage that checks:
- settings renders system status with provider, backend, headless flags, AI provider, DB URL summary, reset flag, current CRM user, CRM counts, and discovery cursor count;
- search settings are visible as read-only;
- `ALLOW_DB_RESET=false` hides reset actions and shows the disabled warning text;
- normal Telegram users never see Mock / Dev controls in the live UX.

- [ ] **Step 2: Run the settings smoke before implementing it**

Run:
```bash
py scripts/smoke_telegram_settings.py
```
Expected: failure because the screen is not fully implemented yet.

- [ ] **Step 3: Implement the settings screen and helpers**

Extend the Telegram settings section to show:
- `LEGAL_DISCOVERY_PROVIDER`
- `BROWSER_BACKEND`
- `CHECKO_HTML_ENABLED`
- `CAMOUFOX_HEADLESS` / `CHECKO_HTML_HEADLESS`
- Yandex search configured yes/no
- `AI_PROVIDER`
- short `DB_URL`
- `ALLOW_DB_RESET`
- current user role/id
- CRM counts
- active company count
- deleted company count
- tasks count
- lead-group count
- discovery cursor count

Keep search settings read-only in this pass, but show the active values for:
- `LEGAL_DISCOVERY_DEFAULT_LIMIT`
- `CHECKO_HTML_MAX_PAGES`
- `CHECKO_HTML_CONCURRENCY`
- `CHECKO_HTML_PROFILE_CONCURRENCY`
- `CHECKO_HTML_DEBUG`

- [ ] **Step 4: Update smoke coverage for adjacent screens**

Refresh the existing smoke scripts so they assert the new menu and status behavior without depending on Mock / Dev buttons.

- [ ] **Step 5: Re-run the full smoke set**

Run:
```bash
py scripts/smoke_telegram_settings.py
py scripts/smoke_telegram_lead_groups.py
py scripts/smoke_lead_fit.py
py scripts/smoke_company_regions.py
py scripts/smoke_admin_reset.py
py scripts/smoke_reset_clean_import.py
```
Expected: pass.

- [ ] **Step 6: Update project docs**

Make the README/TASKS/CHANGELOG reflect:
- the single live Telegram discovery entrypoint
- removal of live Mock / Dev UX
- Checko pagination cursor
- next batch flow
- safe all-data reset
- Telegram settings status screen
- new smoke scripts

- [ ] **Step 7: Commit the docs/settings pass**

```bash
git add app/modules/crm/handlers.py app/modules/crm/telegram_ux.py app/modules/crm/telegram_lead_ux_handlers.py app/modules/crm/keyboards.py scripts/smoke_telegram_settings.py scripts/smoke_telegram_lead_groups.py scripts/smoke_lead_fit.py scripts/smoke_company_regions.py scripts/smoke_legal_discovery.py README.md TASKS.md CHANGELOG.md
git commit -m "feat: finish telegram settings and docs"
```

### Task 5: Final verification sweep

**Files:**
- Verify: all modified files above

- [ ] **Step 1: Run compilation and migration checks**

Run:
```bash
py -m compileall app alembic
py -m alembic upgrade head
```

- [ ] **Step 2: Run the targeted smoke suite**

Run:
```bash
py scripts/smoke_discovery_cursor.py
py scripts/smoke_telegram_settings.py
py scripts/smoke_admin_reset.py
py scripts/smoke_reset_clean_import.py
py scripts/smoke_legal_discovery.py
py scripts/smoke_checko_html.py
py scripts/smoke_telegram_lead_groups.py
py scripts/smoke_lead_fit.py
py scripts/smoke_company_regions.py
```

- [ ] **Step 3: Run import sanity checks**

Run:
```bash
py -c "from app.main import app; print(app.title)"
py -c "from app.bot import main; print('bot ok')"
```

- [ ] **Step 4: Confirm the post-reset clean import invariant**

Manually verify the first import after a clean reset prints:
- `new_count=N`
- `duplicate_count=0`
- `imported_count=N`

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete telegram cleanup reset and cursor pass"
```

### Coverage Check

This plan covers every requested requirement:
- one live Telegram discovery entrypoint
- hidden Mock / Dev from live Telegram
- Checko page cursor and next-batch flow
- safe `crm_only` and `all_data` reset
- `keep_users=true` by default
- Telegram settings and read-only search config
- updated smoke scripts and documentation

