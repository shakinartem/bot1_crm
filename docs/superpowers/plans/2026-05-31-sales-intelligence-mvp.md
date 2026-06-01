# Sales Intelligence MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `sales_intelligence` layer that scores company digital materials, evaluates five closing criteria, generates SOPRANO questions and cold call plans, and integrates the results into Telegram, API, Bot2, analytics, proposals, and docs without adding a new table.

**Architecture:** Implement `app/modules/sales_intelligence/` as a pure orchestration module over existing CRM, intelligence, enrichment, research, and research-queue data. Persist payloads only under the `sales_intelligence` key inside existing `IntelligenceSnapshot` JSON fields, with safe merge and on-demand fallback when merge is unsafe.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Aiogram, Pydantic, existing AI provider abstraction, smoke scripts.

---

## File Structure

### New files

- `app/modules/sales_intelligence/__init__.py`
- `app/modules/sales_intelligence/schemas.py`
- `app/modules/sales_intelligence/scoring.py`
- `app/modules/sales_intelligence/prompts.py`
- `app/modules/sales_intelligence/service.py`
- `app/modules/sales_intelligence/keyboards.py`
- `app/modules/sales_intelligence/handlers.py`
- `scripts/smoke_material_scoring.py`
- `scripts/smoke_call_plan.py`

### Modified files

- `app/bot.py`
- `app/api/routes.py`
- `app/modules/crm/schemas.py`
- `app/modules/crm/service.py`
- `app/modules/crm/keyboards.py`
- `app/modules/crm/handlers.py`
- `app/modules/analytics/scoring.py`
- `app/modules/analytics/service.py`
- `app/modules/proposals/service.py`
- `README.md`
- `TASKS.md`
- `CHANGELOG.md`

---

### Task 1: Add Sales Intelligence Schemas And Request Contracts

**Files:**
- Create: `app/modules/sales_intelligence/schemas.py`
- Create: `app/modules/sales_intelligence/__init__.py`
- Modify: `app/modules/crm/schemas.py`
- Test: `scripts/smoke_material_scoring.py`

- [ ] **Step 1: Write the failing smoke expectations for schema-driven payload shape**

```python
score = await calculate_company_material_score(session, company_id)
assert score.total_score >= 0
assert score.website_score >= 0
assert score.grade in {"weak", "basic", "normal", "strong", "excellent"}
```

- [ ] **Step 2: Run the smoke to verify it fails because the module does not exist yet**

Run: `python scripts/smoke_material_scoring.py`
Expected: FAIL with `ModuleNotFoundError` or missing symbol from `app.modules.sales_intelligence`

- [ ] **Step 3: Add the core Pydantic contracts**

```python
class SalesMaterialScore(BaseModel):
    company_id: int
    total_score: int
    grade: Literal["weak", "basic", "normal", "strong", "excellent"]
    website_score: int
    socials_score: int
    maps_score: int
    trust_score: int
    conversion_score: int
    contact_score: int
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    next_improvements: list[str] = Field(default_factory=list)
```

```python
class ColdCallPlanRequest(BaseModel):
    use_ai: bool = True
    force_regenerate: bool = False
    niche: str | None = None
```

```python
class LatestSalesIntelligenceRead(BaseModel):
    material_score: SalesMaterialScore
    closing_criteria: ClosingCriteriaReadiness
    soprano_questions: SopranoQuestionSet
    cold_call_plan: ColdCallPlan | None = None
    saved_at: datetime | None = None
```

- [ ] **Step 4: Expose exports from `__init__.py`**

```python
from app.modules.sales_intelligence.schemas import (
    ColdCallPlan,
    ColdCallPlanRequest,
    LatestSalesIntelligenceRead,
    SalesMaterialScore,
)
```

- [ ] **Step 5: Extend Bot2 schema container with a typed sales intelligence block**

```python
class Bot2SalesIntelligenceContext(BaseModel):
    material_score: dict | None = None
    closing_criteria: dict | None = None
    cold_call_plan_summary: str | None = None
    soprano_questions: dict | None = None
    first_offer: str | None = None
    risks: list[str] = Field(default_factory=list)
    generation_mode: str | None = None
```

```python
class Bot2ConsultationContextRead(BaseModel):
    ...
    sales_intelligence: Bot2SalesIntelligenceContext | None = None
```

- [ ] **Step 6: Run the smoke again to verify imports and contract creation work**

Run: `python scripts/smoke_material_scoring.py`
Expected: FAIL later in service/scoring flow, not on missing schemas

- [ ] **Step 7: Commit**

```bash
git add app/modules/sales_intelligence/__init__.py app/modules/sales_intelligence/schemas.py app/modules/crm/schemas.py scripts/smoke_material_scoring.py
git commit -m "feat: add sales intelligence schemas"
```

---

### Task 2: Implement Rule-Based Material Scoring

**Files:**
- Create: `app/modules/sales_intelligence/scoring.py`
- Test: `scripts/smoke_material_scoring.py`

- [ ] **Step 1: Write the failing scoring assertions**

```python
score = calculate_material_quality_score(company_context)
assert score.website_score > 0
assert score.contact_score > 0
assert score.total_score <= 100
assert score.grade == "normal"
```

- [ ] **Step 2: Run the smoke to verify it fails in missing scoring logic**

Run: `python scripts/smoke_material_scoring.py`
Expected: FAIL with `NameError`, import error, or assertion on zero scores

- [ ] **Step 3: Implement score clamping, grading, and weighted total helpers**

```python
def _clamp_score(value: int) -> int:
    return max(0, min(100, value))


def _grade(value: int) -> str:
    if value <= 24:
        return "weak"
    if value <= 44:
        return "basic"
    if value <= 64:
        return "normal"
    if value <= 84:
        return "strong"
    return "excellent"
```

```python
def _weighted_total(component_scores: dict[str, int]) -> int:
    total = (
        component_scores["website"] * 0.25
        + component_scores["conversion"] * 0.20
        + component_scores["trust"] * 0.20
        + component_scores["contact"] * 0.15
        + component_scores["socials"] * 0.10
        + component_scores["maps"] * 0.10
    )
    return _clamp_score(int(round(total)))
```

- [ ] **Step 4: Implement the main scoring function against normalized context**

```python
def calculate_material_quality_score(company_context: dict) -> SalesMaterialScore:
    website_score = _score_website(company_context)
    socials_score = _score_socials(company_context)
    maps_score = _score_maps(company_context)
    trust_score = _score_trust(company_context)
    conversion_score = _score_conversion(company_context)
    contact_score = _score_contacts(company_context)
    total_score = _weighted_total(
        {
            "website": website_score,
            "socials": socials_score,
            "maps": maps_score,
            "trust": trust_score,
            "conversion": conversion_score,
            "contact": contact_score,
        }
    )
    return SalesMaterialScore(...)
```

- [ ] **Step 5: Make hypothesis language reusable**

```python
def _hypothesis(text: str) -> str:
    return f"По доступным данным можно предположить, что {text}"
```

- [ ] **Step 6: Run the smoke and verify component scores and grade now exist**

Run: `python scripts/smoke_material_scoring.py`
Expected: PASS and print `smoke_material_scoring ok`

- [ ] **Step 7: Commit**

```bash
git add app/modules/sales_intelligence/scoring.py scripts/smoke_material_scoring.py
git commit -m "feat: add material quality scoring"
```

---

### Task 3: Implement Service Context Assembly, Closing Criteria, SOPRANO, And Fallback Plan

**Files:**
- Create: `app/modules/sales_intelligence/service.py`
- Create: `app/modules/sales_intelligence/prompts.py`
- Test: `scripts/smoke_call_plan.py`

- [ ] **Step 1: Write the failing fallback call-plan smoke**

```python
plan = await generate_cold_call_plan(session, company_id, use_ai=True)
assert plan.generation_mode == "fallback"
assert len(plan.copyable_short_script) < 1200
assert plan.first_offer
```

- [ ] **Step 2: Run the smoke to verify it fails because service orchestration does not exist**

Run: `python scripts/smoke_call_plan.py`
Expected: FAIL with missing `generate_cold_call_plan`, `generate_soprano_questions`, or `build_closing_criteria_readiness`

- [ ] **Step 3: Implement context collection and snapshot/research loaders**

```python
async def get_company_sales_context(session: AsyncSession, company_id: int) -> CompanySalesContext:
    company = await get_company(session, company_id)
    latest_intelligence = await get_latest_intelligence(session, company_id)
    latest_research = await get_latest_research(session, company_id)
    latest_enrichment = await get_latest_enrichment(session, company_id)
    latest_job = await _get_latest_research_job(session, company_id)
    return CompanySalesContext(...)
```

- [ ] **Step 4: Implement readiness and SOPRANO generators with safe defaults**

```python
async def build_closing_criteria_readiness(session: AsyncSession, company_id: int) -> ClosingCriteriaReadiness:
    context = await get_company_sales_context(session, company_id)
    return build_closing_criteria_from_context(context.model_dump())
```

```python
async def generate_soprano_questions(session: AsyncSession, company_id: int, niche: str | None = None) -> SopranoQuestionSet:
    context = await get_company_sales_context(session, company_id)
    detected_niche = niche or _detect_niche(context)
    return build_soprano_questions(context, detected_niche)
```

- [ ] **Step 5: Implement fallback cold call plan builder**

```python
def build_fallback_cold_call_plan(
    company_context: CompanySalesContext,
    material_score: SalesMaterialScore,
    closing_criteria: ClosingCriteriaReadiness,
    soprano_questions: SopranoQuestionSet,
) -> ColdCallPlan:
    return ColdCallPlan(
        company_id=company_context.company_id,
        company_name=company_context.company_name,
        generation_mode="fallback",
        confidence="medium",
        opener="Добрый день ...",
        copyable_short_script="Добрый день, ..."
    )
```

- [ ] **Step 6: Implement AI prompt builder and AI-to-fallback downgrade**

```python
def build_cold_call_plan_prompt(... ) -> str:
    return "\n".join(
        [
            "Собери безопасный cold call plan.",
            "Все выводы формулируй как гипотезы.",
            ...
        ]
    )
```

```python
if use_ai and get_settings().ai_provider.lower() != "fallback":
    try:
        raw = await get_ai_provider().generate(prompt)
        plan = ColdCallPlan.model_validate_json(raw)
    except Exception:
        plan = build_fallback_cold_call_plan(...)
else:
    plan = build_fallback_cold_call_plan(...)
```

- [ ] **Step 7: Run the smoke and verify fallback generation passes**

Run: `python scripts/smoke_call_plan.py`
Expected: PASS through fallback generation and fail later only on persistence or route integration

- [ ] **Step 8: Commit**

```bash
git add app/modules/sales_intelligence/service.py app/modules/sales_intelligence/prompts.py scripts/smoke_call_plan.py
git commit -m "feat: add sales intelligence service orchestration"
```

---

### Task 4: Persist Sales Intelligence Payloads Safely In Intelligence Snapshots

**Files:**
- Modify: `app/modules/sales_intelligence/service.py`
- Test: `scripts/smoke_call_plan.py`

- [ ] **Step 1: Write the failing persistence assertions**

```python
payload = await get_latest_sales_intelligence(session, company_id)
assert payload.material_score.total_score >= 0
assert payload.saved_at is None or payload.saved_at
```

```python
latest_note = await get_company_last_interaction(session, company_id)
assert "Material score:" in (latest_note.summary or "")
assert "copyable_short_script" not in (latest_note.summary or "")
```

- [ ] **Step 2: Run the smoke to verify it fails because persistence is missing**

Run: `python scripts/smoke_call_plan.py`
Expected: FAIL on missing latest payload or wrong note contents

- [ ] **Step 3: Implement safe JSON merge and snapshot update**

```python
async def save_sales_intelligence_payload(session: AsyncSession, company_id: int, payload: LatestSalesIntelligenceRead) -> LatestSalesIntelligenceRead:
    snapshot = await _get_latest_snapshot_model(session, company_id)
    if not snapshot:
        return payload
    merged = _merge_sales_intelligence_payload(snapshot.raw_payload_json, snapshot.result_json, payload)
    if merged is None:
        await _save_summary_note(...)
        return payload
    snapshot.raw_payload_json = merged["raw_payload_json"]
    snapshot.result_json = merged["result_json"]
    ...
```

- [ ] **Step 4: Implement deduplicated summary note**

```python
summary = (
    f"Сформирован план холодного звонка. "
    f"Material score: {score.total_score}/100 ({score.grade}). "
    f"Первый оффер: {plan.first_offer}. "
    f"Mode: {plan.generation_mode}."
)
```

- [ ] **Step 5: Implement latest loader with on-demand fallback**

```python
async def get_latest_sales_intelligence(session: AsyncSession, company_id: int) -> LatestSalesIntelligenceRead:
    snapshot = await get_latest_intelligence(session, company_id)
    persisted = _extract_sales_intelligence(snapshot)
    if persisted:
        return persisted
    ...
```

- [ ] **Step 6: Run the smoke and verify persistence/note rules pass**

Run: `python scripts/smoke_call_plan.py`
Expected: PASS through payload save/load and note assertions, fail later only on route or Telegram integration

- [ ] **Step 7: Commit**

```bash
git add app/modules/sales_intelligence/service.py scripts/smoke_call_plan.py
git commit -m "feat: persist sales intelligence payloads"
```

---

### Task 5: Add API Endpoints And Bot2 Context Integration

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/modules/crm/service.py`
- Modify: `app/modules/crm/schemas.py`
- Test: `scripts/smoke_call_plan.py`

- [ ] **Step 1: Write the failing API endpoint assertions**

```python
assert client.get(f"/api/companies/{company_id}/sales-intelligence/material-score").status_code == 200
assert client.get(f"/api/companies/{company_id}/sales-intelligence/closing-criteria").status_code == 200
assert client.get(f"/api/companies/{company_id}/sales-intelligence/soprano-questions").status_code == 200
assert client.post(f"/api/companies/{company_id}/sales-intelligence/cold-call-plan", json={"use_ai": True}).status_code == 200
assert client.get(f"/api/companies/{company_id}/sales-intelligence/latest").status_code == 200
```

- [ ] **Step 2: Run the smoke to verify it fails with 404 endpoints**

Run: `python scripts/smoke_call_plan.py`
Expected: FAIL with 404 or missing response models

- [ ] **Step 3: Add the new routes**

```python
@api_router.get("/companies/{company_id}/sales-intelligence/material-score", response_model=SalesMaterialScore)
async def company_sales_material_score(...):
    return await calculate_company_material_score(session, company_id)
```

```python
@api_router.post("/companies/{company_id}/sales-intelligence/cold-call-plan", response_model=ColdCallPlan)
async def company_sales_cold_call_plan(...):
    return await generate_cold_call_plan(session, company_id, use_ai=payload.use_ai, force_regenerate=payload.force_regenerate, niche=payload.niche)
```

- [ ] **Step 4: Inject sales intelligence into Bot2 context**

```python
sales_intelligence = await get_latest_sales_intelligence(session, company_id)
return Bot2ConsultationContextRead(
    ...
    sales_intelligence=Bot2SalesIntelligenceContext(
        material_score=sales_intelligence.material_score.model_dump(),
        closing_criteria=sales_intelligence.closing_criteria.model_dump(),
        cold_call_plan_summary=sales_intelligence.cold_call_plan.call_script_short if sales_intelligence.cold_call_plan else None,
        ...
    ),
)
```

- [ ] **Step 5: Run the smoke and verify endpoints and Bot2 context pass**

Run: `python scripts/smoke_call_plan.py`
Expected: PASS API and Bot2 assertions, fail later only on Telegram or proposal/analytics integration

- [ ] **Step 6: Commit**

```bash
git add app/api/routes.py app/modules/crm/service.py app/modules/crm/schemas.py scripts/smoke_call_plan.py
git commit -m "feat: add sales intelligence api and bot2 context"
```

---

### Task 6: Integrate Into Analytics Scoring And Proposal Suggestions

**Files:**
- Modify: `app/modules/analytics/scoring.py`
- Modify: `app/modules/analytics/service.py`
- Modify: `app/modules/proposals/service.py`
- Test: `scripts/smoke_analytics.py`
- Test: `scripts/smoke_proposals.py`

- [ ] **Step 1: Write failing integration checks inside existing smokes**

```python
score = await get_company_lead_score(session, company_id)
assert any("digital" in item.lower() for item in score.risks)
```

```python
suggestions = await suggest_packages_for_company(session, company_id)
assert suggestions
assert any(item.code in {"audit_roadmap", "landing_start", "maps_reputation"} for item in suggestions)
```

- [ ] **Step 2: Run targeted smokes to verify missing integration**

Run: `python scripts/smoke_analytics.py`
Expected: FAIL on absent sales-intelligence bonus/risk behavior

Run: `python scripts/smoke_proposals.py`
Expected: FAIL on absent material-score-aware package suggestions

- [ ] **Step 3: Add lazy-loaded sales intelligence enrichment to lead scoring**

```python
try:
    from app.modules.sales_intelligence.service import get_latest_sales_intelligence
except Exception:
    get_latest_sales_intelligence = None
```

```python
if material_score >= 70:
    score += 10
elif material_score >= 50:
    score += 5
elif material_score < 30:
    score -= 10
```

- [ ] **Step 4: Add material-score-aware suggestion rules**

```python
sales_intelligence = await get_latest_sales_intelligence(session, company_id)
if sales_intelligence.material_score.total_score < 30:
    suggestions.setdefault("audit_roadmap", _make_suggestion(...))
    suggestions.setdefault("maps_reputation", _make_suggestion(...))
    suggestions.setdefault("landing_start", _make_suggestion(...))
```

- [ ] **Step 5: Run targeted smokes and verify both integrations pass**

Run: `python scripts/smoke_analytics.py`
Expected: PASS

Run: `python scripts/smoke_proposals.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/modules/analytics/scoring.py app/modules/analytics/service.py app/modules/proposals/service.py scripts/smoke_analytics.py scripts/smoke_proposals.py
git commit -m "feat: integrate sales intelligence into scoring and proposals"
```

---

### Task 7: Add Telegram Workflow And Company Card Integration

**Files:**
- Create: `app/modules/sales_intelligence/keyboards.py`
- Create: `app/modules/sales_intelligence/handlers.py`
- Modify: `app/modules/crm/keyboards.py`
- Modify: `app/modules/crm/service.py`
- Modify: `app/modules/crm/handlers.py`
- Modify: `app/bot.py`

- [ ] **Step 1: Write the failing UI expectations in local helper-level assertions**

```python
text = format_company_card(company)
assert "Материалы:" in text
assert "План звонка:" in text
```

```python
markup = company_card_actions_markup(company_id)
assert any("План звонка" in button.text for row in markup.inline_keyboard for button in row)
```

- [ ] **Step 2: Run a targeted import check to verify missing Telegram symbols**

Run: `python -c "from app.bot import main; print('bot ok')"`
Expected: FAIL on missing sales intelligence router or keyboard symbol until implementation is added

- [ ] **Step 3: Add keyboards and callbacks**

```python
def sales_intelligence_menu_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧠 Сгенерировать план", callback_data=f"sales:plan:{company_id}")],
            [InlineKeyboardButton(text="📊 Оценить материалы", callback_data=f"sales:score:{company_id}")],
            ...
        ]
    )
```

```python
@router.callback_query(F.data.startswith("sales:open:"))
async def sales_open_menu(callback: CallbackQuery) -> None:
    ...
```

- [ ] **Step 4: Add compact company-card block and button entrypoint**

```python
sales_block = (
    f"\n\n📊 <b>Материалы:</b>\n"
    f"Оценка: {score.total_score}/100 — {score.grade}\n"
    f"Сайт: {score.website_score}\n"
    f"Соцсети: {score.socials_score}\n"
    f"Карты: {score.maps_score}\n"
    f"Доверие: {score.trust_score}\n"
    f"Конверсия: {score.conversion_score}\n"
    f"\n📞 <b>План звонка:</b>\n{'готов' if has_plan else 'не готов'}"
)
```

- [ ] **Step 5: Register the router**

```python
from app.modules.sales_intelligence.handlers import router as sales_intelligence_router
...
dp.include_router(sales_intelligence_router)
```

- [ ] **Step 6: Run the import check and smoke bot context checks**

Run: `python -c "from app.bot import main; print('bot ok')"`
Expected: PASS and print `bot ok`

- [ ] **Step 7: Commit**

```bash
git add app/modules/sales_intelligence/keyboards.py app/modules/sales_intelligence/handlers.py app/modules/crm/keyboards.py app/modules/crm/service.py app/modules/crm/handlers.py app/bot.py
git commit -m "feat: add sales intelligence telegram workflow"
```

---

### Task 8: Finish Smoke Scripts, Docs, And Full Verification

**Files:**
- Create: `scripts/smoke_material_scoring.py`
- Create: `scripts/smoke_call_plan.py`
- Modify: `README.md`
- Modify: `TASKS.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Finalize both new smoke scripts end-to-end**

```python
print("smoke_material_scoring ok")
```

```python
print("smoke_call_plan ok")
```

- [ ] **Step 2: Update README/TASKS/CHANGELOG**

```markdown
## Sales Intelligence: Cold Call Plan and Material Scoring
- material scoring for website, socials, maps, trust, conversion, and contacts
- 5 closing criteria readiness
- SOPRANO questions
- AI and fallback cold call planning
```

- [ ] **Step 3: Run compile and all required verification commands**

Run: `python -m compileall app alembic`
Expected: successful compile output with no syntax errors

Run: `python scripts/smoke_check.py`
Expected: PASS

Run: `python scripts/test_csv_import.py`
Expected: PASS

Run: `python scripts/smoke_bot2_handoff.py`
Expected: PASS

Run: `python scripts/test_digest_module.py`
Expected: PASS

Run: `python scripts/smoke_proposals.py`
Expected: PASS

Run: `python scripts/smoke_analytics.py`
Expected: PASS

Run: `python scripts/smoke_bot2_context.py`
Expected: PASS

Run: `python scripts/smoke_legal_discovery.py`
Expected: PASS

Run: `python scripts/smoke_research_queue.py`
Expected: PASS

Run: `python scripts/smoke_checko_html.py`
Expected: PASS if script exists in this branch

Run: `python scripts/smoke_yandex_search.py`
Expected: PASS if script exists in this branch

Run: `python scripts/smoke_browser_backend.py`
Expected: PASS if script exists in this branch

Run: `python scripts/smoke_material_scoring.py`
Expected: PASS and print `smoke_material_scoring ok`

Run: `python scripts/smoke_call_plan.py`
Expected: PASS and print `smoke_call_plan ok`

Run: `python -c "from app.main import app; print(app.title)"`
Expected: print app title

Run: `python -c "from app.bot import main; print('bot ok')"`
Expected: print `bot ok`

- [ ] **Step 4: Commit**

```bash
git add README.md TASKS.md CHANGELOG.md scripts/smoke_material_scoring.py scripts/smoke_call_plan.py
git commit -m "docs: document sales intelligence mvp"
```

---

## Self-Review Checklist

- Spec coverage:
  - new module and data contracts: Tasks 1-3
  - material scoring: Task 2
  - five closing criteria and SOPRANO: Task 3
  - AI/fallback cold call plan: Task 3
  - snapshot persistence strategy: Task 4
  - API and Bot2: Task 5
  - analytics and proposals: Task 6
  - Telegram and company card: Task 7
  - smoke tests and docs: Task 8

- Placeholder scan:
  - no `TODO`, `TBD`, or “implement later” placeholders left in steps

- Type consistency:
  - request payload uses `ColdCallPlanRequest`
  - latest payload uses `LatestSalesIntelligenceRead`
  - persistence target remains existing `IntelligenceSnapshot`

