# FNS-first Discovery and Safe Browser Research Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a legal-first company discovery flow with preview/import, plus a safe queued public-web research pipeline that enriches CRM companies without bypassing blocks or breaking existing intelligence, enrichment, analytics, digest, or Bot 2 flows.

**Architecture:** Add three additive modules: `legal_discovery` for provider-backed preview/import, `research` for safe website resolution and parsing, and `research_queue` for controlled batch execution. Reuse current `intelligence` snapshot storage and existing CRM integration points so new batch research lands in the same downstream scoring, Bot 2, proposal, and call-prep surfaces.

**Tech Stack:** FastAPI, aiogram, SQLAlchemy async ORM, Alembic, Pydantic, httpx, asyncio, existing SHARiK CRM modules.

---

## File Map

**Create:**
- `app/modules/legal_discovery/__init__.py`
- `app/modules/legal_discovery/schemas.py`
- `app/modules/legal_discovery/providers.py`
- `app/modules/legal_discovery/mock_provider.py`
- `app/modules/legal_discovery/service.py`
- `app/modules/legal_discovery/keyboards.py`
- `app/modules/legal_discovery/handlers.py`
- `app/modules/research/__init__.py`
- `app/modules/research/schemas.py`
- `app/modules/research/http_fetcher.py`
- `app/modules/research/browser_fetcher.py`
- `app/modules/research/search_resolver.py`
- `app/modules/research/site_parser.py`
- `app/modules/research/service.py`
- `app/modules/research_queue/__init__.py`
- `app/modules/research_queue/models.py`
- `app/modules/research_queue/schemas.py`
- `app/modules/research_queue/service.py`
- `app/modules/research_queue/worker.py`
- `app/modules/research_queue/keyboards.py`
- `app/modules/research_queue/handlers.py`
- `alembic/versions/0007_add_research_jobs.py`
- `scripts/smoke_legal_discovery.py`
- `scripts/smoke_research_queue.py`
- `scripts/run_research_batch.py`

**Modify:**
- `.env.example`
- `README.md`
- `TASKS.md`
- `CHANGELOG.md`
- `app/config.py`
- `app/database.py`
- `app/api/routes.py`
- `app/bot.py`
- `app/modules/crm/models.py`
- `app/modules/crm/schemas.py`
- `app/modules/crm/service.py`
- `app/modules/crm/keyboards.py`
- `app/modules/analytics/scoring.py`
- `app/modules/analytics/service.py`
- `app/modules/ai/prompts.py`
- `app/modules/ai/service.py`
- `app/modules/proposals/service.py`
- `app/modules/digest/service.py`
- `app/modules/intelligence/service.py`
- `app/modules/intelligence/schemas.py`

**Verification targets:**
- `python -m compileall app alembic`
- `python scripts/smoke_check.py`
- `python scripts/test_csv_import.py`
- `python scripts/smoke_bot2_handoff.py`
- `python scripts/test_digest_module.py`
- `python scripts/smoke_proposals.py`
- `python scripts/smoke_analytics.py`
- `python scripts/smoke_bot2_context.py`
- `python scripts/smoke_legal_discovery.py`
- `python scripts/smoke_research_queue.py`
- `python -c "from app.main import app; print(app.title)"`
- `python -c "from app.bot import main; print('bot ok')"`
- `alembic upgrade head`

### Task 1: Wire Config and Persistence

**Files:**
- Create: `app/modules/research_queue/models.py`
- Create: `alembic/versions/0007_add_research_jobs.py`
- Modify: `app/config.py`
- Modify: `app/database.py`
- Modify: `app/modules/crm/models.py`

- [ ] **Step 1: Add failing migration expectation to smoke workflow notes**

Record the intended table shape before coding:

```python
class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    priority: Mapped[str] = mapped_column(String(32), index=True, default="medium")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: Add config fields for discovery and research controls**

Update `app/config.py` with:

```python
    legal_discovery_provider: str = Field(default="mock", alias="LEGAL_DISCOVERY_PROVIDER")
    legal_discovery_default_limit: int = Field(default=50, alias="LEGAL_DISCOVERY_DEFAULT_LIMIT")
    legal_discovery_request_timeout: int = Field(default=10, alias="LEGAL_DISCOVERY_REQUEST_TIMEOUT")
    research_fetch_backend: str = Field(default="httpx", alias="RESEARCH_FETCH_BACKEND")
    research_browser_backend: str = Field(default="disabled", alias="RESEARCH_BROWSER_BACKEND")
    research_concurrency: int = Field(default=5, alias="RESEARCH_CONCURRENCY")
    research_request_timeout: int = Field(default=10, alias="RESEARCH_REQUEST_TIMEOUT")
    research_request_delay_ms: int = Field(default=500, alias="RESEARCH_REQUEST_DELAY_MS")
    research_max_pages_per_site: int = Field(default=3, alias="RESEARCH_MAX_PAGES_PER_SITE")
    research_max_html_chars: int = Field(default=300_000, alias="RESEARCH_MAX_HTML_CHARS")
```

- [ ] **Step 3: Implement `ResearchJob` model and relationship**

Add the model in `app/modules/research_queue/models.py` and link it from `Company`:

```python
    research_jobs: Mapped[list["ResearchJob"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
```

And at the bottom of `app/modules/crm/models.py`:

```python
from app.modules.research_queue.models import ResearchJob  # noqa: E402,F401
```

- [ ] **Step 4: Register the model in database metadata**

Ensure `app/database.py` imports the new module alongside existing module imports so Alembic/autoload sees it.

- [ ] **Step 5: Add Alembic migration**

Create `alembic/versions/0007_add_research_jobs.py` with upgrade/downgrade creating and dropping:
- `research_jobs`
- indexes on `company_id`, `job_type`, `status`, `priority`

- [ ] **Step 6: Verify migration locally**

Run: `python -m alembic upgrade head`
Expected: migration applies without touching existing tables.

- [ ] **Step 7: Commit**

```bash
git add app/config.py app/database.py app/modules/crm/models.py app/modules/research_queue/models.py alembic/versions/0007_add_research_jobs.py
git commit -m "add research job persistence"
```

### Task 2: Build Legal Discovery Contracts and Mock Provider

**Files:**
- Create: `app/modules/legal_discovery/__init__.py`
- Create: `app/modules/legal_discovery/schemas.py`
- Create: `app/modules/legal_discovery/providers.py`
- Create: `app/modules/legal_discovery/mock_provider.py`
- Modify: `.env.example`

- [ ] **Step 1: Define Pydantic contracts**

Create `schemas.py` with:

```python
class LegalDiscoveredCompany(BaseModel):
    provider: str
    inn: str
    ogrn: str
    kpp: str | None = None
    legal_name: str
    short_name: str | None = None
    address: str | None = None
    city: str | None = None
    region: str | None = None
    status: str | None = None
    okved: str | None = None
    okved_name: str | None = None
    raw_payload: dict[str, Any] | None = None
    confidence: Literal["low", "medium", "high"] = "medium"
    warnings: list[str] = Field(default_factory=list)
```

Also define `LegalDiscoveryPreviewItem`, `LegalDiscoveryPreview`, and `LegalDiscoveryImportResult`.

- [ ] **Step 2: Define provider interface**

Create `providers.py`:

```python
class LegalDiscoveryProvider(Protocol):
    code: str
    title: str
    enabled: bool

    async def search_companies(
        self,
        query: str,
        city: str | None = None,
        region: str | None = None,
        limit: int = 50,
    ) -> list[LegalDiscoveredCompany]:
        ...
```

Add a `get_legal_discovery_provider(settings)` selector that returns mock by default and disabled stubs for future providers.

- [ ] **Step 3: Implement realistic mock dataset**

Create `mock_provider.py` with a deterministic dataset for `стоматология` / `Саратов`:

```python
MOCK_COMPANIES = [
    {"inn": "6453001001", "ogrn": "1026403050001", "legal_name": 'ООО "ДЕНТАЛ БРАВО"', "status": "active"},
    {"inn": "6453001002", "ogrn": "1026403050002", "legal_name": 'ООО "СМАЙЛ КЛИНИК"', "status": "active"},
]
```

Expand to 20-30 records with:
- duplicates by `inn`, `ogrn`, or `legal_name + city`
- inactive items
- weak items with warnings
- varied `okved` and addresses

- [ ] **Step 4: Add `.env.example` knobs**

Append:

```env
LEGAL_DISCOVERY_PROVIDER=mock
LEGAL_DISCOVERY_DEFAULT_LIMIT=50
LEGAL_DISCOVERY_REQUEST_TIMEOUT=10
RESEARCH_FETCH_BACKEND=httpx
RESEARCH_BROWSER_BACKEND=disabled
RESEARCH_CONCURRENCY=5
RESEARCH_REQUEST_TIMEOUT=10
RESEARCH_REQUEST_DELAY_MS=500
RESEARCH_MAX_PAGES_PER_SITE=3
RESEARCH_MAX_HTML_CHARS=300000
```

- [ ] **Step 5: Sanity check the provider in isolation**

Run:

```bash
python -c "import asyncio; from app.modules.legal_discovery.mock_provider import MockLegalDiscoveryProvider; print(len(asyncio.run(MockLegalDiscoveryProvider().search_companies('стоматология', city='Саратов', limit=25))))"
```

Expected: `25`

- [ ] **Step 6: Commit**

```bash
git add .env.example app/modules/legal_discovery
git commit -m "add legal discovery schemas and mock provider"
```

### Task 3: Implement Legal Discovery Preview and Import

**Files:**
- Create: `app/modules/legal_discovery/service.py`
- Modify: `app/modules/crm/service.py`
- Modify: `app/modules/crm/schemas.py`

- [ ] **Step 1: Add helper tests as executable smoke targets**

Draft expected behaviors directly in service docstrings/tests:

```python
preview = await run_legal_discovery_preview(session, query="стоматология", city="Саратов", limit=25)
assert preview.total_found == 25
assert preview.new_count >= 1
assert preview.duplicate_count >= 1
```

- [ ] **Step 2: Implement preview registry and duplicate detection**

In `service.py`, add:

```python
_PREVIEW_REGISTRY: dict[str, LegalDiscoveryPreview] = {}

async def run_legal_discovery_preview(...):
    provider = get_legal_discovery_provider(get_settings())
    companies = await provider.search_companies(...)
    items = [await build_preview_item(session, company) for company in companies]
    preview = LegalDiscoveryPreview(...)
    _PREVIEW_REGISTRY[preview.preview_id] = preview
    return preview
```

`build_preview_item()` should mark:
- `duplicate_existing` when CRM matches by `inn`, `ogrn`, `legal_name + city`
- `inactive` when status is not active
- `weak_data` when warnings or missing core fields
- `new` otherwise

- [ ] **Step 3: Implement import with confirmation modes**

Add:

```python
async def import_legal_discovery_preview(
    session: AsyncSession,
    preview_id: str,
    mode: Literal["active_new", "all_new"],
) -> LegalDiscoveryImportResult:
```

Rules:
- `active_new`: only `status == "active"` and preview status `new`
- `all_new`: include `new` plus optionally weak/inactive new entries
- never re-create duplicates
- create `LeadInteraction` note with provider code

- [ ] **Step 4: Use CRM-safe field mapping**

Create companies with:

```python
CompanyCreate(
    name=item.company.short_name or item.company.legal_name,
    legal_name=item.company.legal_name,
    inn=item.company.inn,
    ogrn=item.company.ogrn,
    address=item.company.address,
    city=item.company.city,
    region=item.company.region,
    source=f"legal_discovery:{preview.provider}",
    status="research_needed",
    priority="medium" if item.company.status == "active" else "low",
)
```

- [ ] **Step 5: Verify duplicate-safe import**

Run:

```bash
python -c "import asyncio; from app.database import SessionLocal; from app.modules.legal_discovery.service import run_legal_discovery_preview, import_legal_discovery_preview; async def main():\n    async with SessionLocal() as session:\n        preview = await run_legal_discovery_preview(session, query='стоматология', city='Саратов', limit=10)\n        first = await import_legal_discovery_preview(session, preview.preview_id, 'active_new')\n        second = await import_legal_discovery_preview(session, preview.preview_id, 'active_new')\n        print(first.added_count, second.added_count)\nasyncio.run(main())"
```

Expected: second import adds `0`.

- [ ] **Step 6: Commit**

```bash
git add app/modules/legal_discovery/service.py app/modules/crm/service.py app/modules/crm/schemas.py
git commit -m "add legal discovery preview and import"
```

### Task 4: Add Safe Research Schemas and Fetch Backends

**Files:**
- Create: `app/modules/research/__init__.py`
- Create: `app/modules/research/schemas.py`
- Create: `app/modules/research/http_fetcher.py`
- Create: `app/modules/research/browser_fetcher.py`

- [ ] **Step 1: Define fetch/result models**

Create `schemas.py` with:

```python
class FetchResult(BaseModel):
    url: str
    final_url: str | None = None
    status: Literal["success", "failed", "blocked", "non_html", "timeout"]
    http_status: int | None = None
    html: str | None = None
    text_excerpt: str | None = None
    error_message: str | None = None
    blocked_reason: str | None = None
```

Also define `WebsiteCandidate`, `WebsiteResolutionResult`, `ParsedSiteSignals`, `ParsedCompanySite`, and `ResearchResult`.

- [ ] **Step 2: Implement httpx fetcher**

Create `http_fetcher.py`:

```python
async def fetch_url(url: str, timeout: int = 10, max_chars: int = 300_000) -> FetchResult:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": "SHARiK CRM Research Bot/1.0"}) as client:
        response = await client.get(normalize_url(url))
```

Rules:
- trim whitespace
- default to `https://`
- reject non-html content types
- cap stored HTML/text
- map timeout/connection/http errors to `FetchResult.status`

- [ ] **Step 3: Implement disabled-by-default browser abstraction**

Create `browser_fetcher.py`:

```python
async def fetch_with_browser(url: str) -> FetchResult:
    return FetchResult(
        url=url,
        status="failed",
        error_message="Browser backend is disabled",
    )
```

Later-safe hook:
- if browser backend enabled in future, return `blocked` when page contains captcha/login/block markers

- [ ] **Step 4: Add backend selector**

In `schemas.py` or a helper:

```python
def get_fetch_backend(settings: Settings) -> Callable[[str], Awaitable[FetchResult]]:
    if settings.research_fetch_backend == "browser":
        return fetch_with_browser
    return partial(fetch_url, timeout=settings.research_request_timeout, max_chars=settings.research_max_html_chars)
```

- [ ] **Step 5: Verify fetcher with local sample HTML**

Run a tiny module check:

```bash
python -c "import asyncio; from app.modules.research.http_fetcher import normalize_url; print(asyncio.run(asyncio.sleep(0, result=normalize_url('example.com'))))"
```

Expected: `https://example.com`

- [ ] **Step 6: Commit**

```bash
git add app/modules/research
git commit -m "add safe research fetch backends"
```

### Task 5: Implement Website Resolver and Site Parser

**Files:**
- Create: `app/modules/research/search_resolver.py`
- Create: `app/modules/research/site_parser.py`
- Modify: `app/modules/intelligence/service.py`
- Modify: `app/modules/intelligence/schemas.py`

- [ ] **Step 1: Reuse existing intelligence provider ideas without coupling the modules**

In `search_resolver.py`, define candidate filtering and aggregator domain list:

```python
AGGREGATOR_DOMAINS = {
    "rusprofile.ru",
    "list-org.com",
    "zachestnyibiznes.ru",
    "checko.ru",
    "sbis.ru",
    "spark-interfax.ru",
    "kartoteka.ru",
    "nalog.gov.ru",
    "egrul.nalog.ru",
    "2gis.ru",
    "zoon.ru",
    "prodoctorov.ru",
    "yell.ru",
}
```

- [ ] **Step 2: Implement query generation and candidate scoring**

Create:

```python
async def resolve_company_website(company: Company, known_phone: str | None = None) -> WebsiteResolutionResult:
    queries = [
        company.inn,
        f"ИНН {company.inn}",
        f"{company.inn} официальный сайт",
        f"{company.legal_name} официальный сайт",
        f"{company.legal_name} {company.city or ''}".strip(),
        f"{company.name} стоматология {company.city or ''}".strip(),
    ]
```

Scoring rules:
- `+50` INN on page
- `+25` legal name / short name
- `+20` city / address
- `+15` known phone
- `+10` dental keywords
- `-30` aggregator
- `-50` clearly unrelated

- [ ] **Step 3: Implement parser with lightweight extraction**

Create `site_parser.py` with regex/text extraction for:
- `page_title`
- `meta_description`
- phones
- emails
- whatsapp/telegram/vk/instagram/youtube/tiktok/dzen
- yandex maps / `2gis`
- signals: booking, callback, prices, doctors, reviews, contacts, privacy policy
- services: implantation, braces, aligners, children dentistry, emergency

- [ ] **Step 4: Build cautious hypotheses**

Add:

```python
def build_site_hypotheses(parsed: ParsedCompanySite) -> list[str]:
    hypotheses = []
    if not parsed.signals.has_online_booking:
        hypotheses.append("В быстрой проверке не обнаружена явная онлайн-запись. Возможно, часть обращений теряется до записи.")
    return hypotheses
```

- [ ] **Step 5: Verify parser against a sample fixture**

Run target example:

```bash
python -c "from app.modules.research.site_parser import parse_company_site; html='<html><title>Dental Bravo</title><body>ИНН 6453001001 Онлайн-запись Отзывы +7 900 111-22-33 info@bravo.ru <a href=\"https://vk.com/bravo\">vk</a></body></html>'; parsed=parse_company_site(html, 'https://bravo.ru'); print(parsed.page_title, parsed.signals.has_online_booking, parsed.signals.has_reviews, parsed.phones[0])"
```

Expected: title plus `True True +7 900 111-22-33`

- [ ] **Step 6: Commit**

```bash
git add app/modules/research/search_resolver.py app/modules/research/site_parser.py app/modules/intelligence/service.py app/modules/intelligence/schemas.py
git commit -m "add website resolver and site parser"
```

### Task 6: Implement Company Research Service and Snapshot Updates

**Files:**
- Create: `app/modules/research/service.py`
- Modify: `app/modules/intelligence/service.py`
- Modify: `app/modules/crm/service.py`

- [ ] **Step 1: Define the main orchestration function**

Add:

```python
async def run_company_research(session: AsyncSession, company_id: int, force: bool = False) -> ResearchResult:
    company = await get_company_or_raise(session, company_id)
    if not company.inn and not company.legal_name:
        return ResearchResult(status="needs_manual_review", error_message="Company needs legal identification before research")
```

- [ ] **Step 2: Reuse `IntelligenceSnapshot` as the durable output**

After resolve/fetch/parse:

```python
snapshot = IntelligenceSnapshot(
    company_id=company.id,
    status=status,
    inn=company.inn,
    legal_name=company.legal_name,
    ogrn=company.ogrn,
    legal_address=company.address,
    website_url=selected_url,
    website_confidence=resolution.confidence,
    website_candidates_json=json.dumps([candidate.model_dump() for candidate in resolution.candidates], ensure_ascii=False),
    parsed_contacts_json=json.dumps(parsed.contacts_payload(), ensure_ascii=False),
    parsed_socials_json=json.dumps(parsed.socials_payload(), ensure_ascii=False),
    parsed_signals_json=json.dumps(parsed.signals.model_dump(), ensure_ascii=False),
    hypotheses_json=json.dumps(hypotheses, ensure_ascii=False),
)
```

- [ ] **Step 3: Add blocked/manual-review handling**

Rules:
- blocked page -> snapshot status `blocked`
- no confident website -> `needs_manual_review`
- resolver/fetch failure -> `failed` or `partial`

- [ ] **Step 4: Save contacts and safe company updates**

Create contact points for:
- `phone`
- `email`
- `website`
- `whatsapp`
- `telegram`
- `vk`
- `instagram`

Only update `company.website` automatically when confidence is medium/high. Never overwrite with empty values.

- [ ] **Step 5: Add research interaction note**

```python
await add_interaction_note(
    session,
    company.id,
    "Проведен research сайта/публичных данных",
)
```

- [ ] **Step 6: Verify single-company research via direct call**

Run:

```bash
python -c "print('covered by smoke_research_queue.py after service implementation')"
```

Expected: use dedicated smoke instead of ad-hoc manual checking.

- [ ] **Step 7: Commit**

```bash
git add app/modules/research/service.py app/modules/intelligence/service.py app/modules/crm/service.py
git commit -m "add company research service"
```

### Task 7: Implement Research Queue Service and Worker

**Files:**
- Create: `app/modules/research_queue/schemas.py`
- Create: `app/modules/research_queue/service.py`
- Create: `app/modules/research_queue/worker.py`
- Modify: `app/modules/digest/service.py`

- [ ] **Step 1: Define queue schemas**

Create `schemas.py` with:

```python
class ResearchJobRead(BaseModel):
    id: int
    company_id: int
    job_type: str
    status: str
    priority: str
    attempts: int
    max_attempts: int
    error_message: str | None = None
    result: dict[str, Any] | None = None
```

Also define `ResearchJobCreateRequest`, `ResearchBatchRunRequest`, `ResearchQueueStatusRead`.

- [ ] **Step 2: Implement deduplicated job creation**

Add:

```python
async def create_research_jobs_for_companies(session, company_ids, job_type="full_research"):
    existing = await find_open_jobs(session, company_ids, job_type)
    ...
```

Rules:
- one `pending/running` job per `company_id + job_type`
- default priority `medium`

- [ ] **Step 3: Implement `run_research_job()`**

Pseudo-code:

```python
job.status = "running"
job.attempts += 1
result = await run_company_research(session, job.company_id)
job.status = result.status if result.status in {"success", "blocked", "needs_manual_review"} else "failed"
job.result_json = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
```

- [ ] **Step 4: Implement controlled batch runner**

In `worker.py`:

```python
async def run_research_batch(session_factory, concurrency=5, limit=100, delay_ms=500):
    semaphore = asyncio.Semaphore(concurrency)
```

Between jobs:
- `await asyncio.sleep(delay_ms / 1000)`

No infinite loop, no background daemon by default.

- [ ] **Step 5: Add status/cancel helpers**

Add:
- `get_pending_jobs`
- `get_research_jobs`
- `get_queue_status`
- `cancel_job`

- [ ] **Step 6: Verify queue semantics**

Run:

```bash
python -c "print('queue semantics verified by smoke_research_queue.py')"
```

Expected: smoke test covers dedupe, batch, and statuses.

- [ ] **Step 7: Commit**

```bash
git add app/modules/research_queue app/modules/digest/service.py
git commit -m "add research queue service and worker"
```

### Task 8: Add API Endpoints and CLI Entry Point

**Files:**
- Modify: `app/api/routes.py`
- Create: `scripts/run_research_batch.py`

- [ ] **Step 1: Add legal discovery API**

In `app/api/routes.py`, add:

```python
@api_router.post("/legal-discovery/search", response_model=LegalDiscoveryPreview)
async def legal_discovery_search(...):
    ...

@api_router.post("/legal-discovery/import", response_model=LegalDiscoveryImportResult)
async def legal_discovery_import(...):
    ...
```

- [ ] **Step 2: Add research queue API**

Add:

```python
@api_router.post("/research/jobs", response_model=list[ResearchJobRead])
@api_router.get("/research/jobs", response_model=list[ResearchJobRead])
@api_router.post("/research/jobs/run-batch", response_model=ResearchQueueStatusRead)
@api_router.get("/research/jobs/status", response_model=ResearchQueueStatusRead)
```

- [ ] **Step 3: Add company research API**

Add:

```python
@api_router.post("/companies/{company_id}/research/run", response_model=ResearchResultRead)
@api_router.get("/companies/{company_id}/research/latest", response_model=IntelligenceSnapshotRead | None)
@api_router.get("/companies/{company_id}/research/history", response_model=list[IntelligenceSnapshotRead])
```

- [ ] **Step 4: Add CLI runner**

Create `scripts/run_research_batch.py`:

```python
parser.add_argument("--limit", type=int, default=100)
parser.add_argument("--concurrency", type=int, default=5)
parser.add_argument("--source", type=str, default=None)
parser.add_argument("--only-without-website", action="store_true")
parser.add_argument("--dry-run", action="store_true")
```

It should:
- select companies
- optionally print candidates only in `--dry-run`
- create jobs
- run batch manually

- [ ] **Step 5: Verify routes import cleanly**

Run:

```bash
python -c "from app.main import app; print(app.title)"
```

Expected: app starts and imports routes without schema errors.

- [ ] **Step 6: Commit**

```bash
git add app/api/routes.py scripts/run_research_batch.py
git commit -m "add discovery and research api endpoints"
```

### Task 9: Add Telegram Discovery and Queue Workflow

**Files:**
- Create: `app/modules/legal_discovery/keyboards.py`
- Create: `app/modules/legal_discovery/handlers.py`
- Create: `app/modules/research_queue/keyboards.py`
- Create: `app/modules/research_queue/handlers.py`
- Modify: `app/modules/crm/keyboards.py`
- Modify: `app/modules/crm/service.py`
- Modify: `app/bot.py`

- [ ] **Step 1: Add buttons for discovery and company status**

In CRM keyboards:

```python
InlineKeyboardButton(text="🔍 Поиск компаний", callback_data="discovery:menu")
InlineKeyboardButton(text="🧠 Запустить research", callback_data=f"research_queue:start:{company_id}")
```

Add compact card block:
- `Legal: confirmed/not confirmed`
- `Website: found/not found`
- `Research: success/blocked/manual/failed`

- [ ] **Step 2: Implement discovery FSM**

Add a simple step-by-step flow:
- provider
- niche
- city/region
- limit
- preview

Preview message should include:

```text
🔍 Поиск компаний завершён

Найдено юрлиц: {total_found}
Активных: {active_count}
Неактивных: {inactive_count}
Новые для CRM: {new_count}
Дубли в CRM: {duplicate_count}
Слабые данные: {weak_count}
```

- [ ] **Step 3: Implement preview actions**

Buttons:
- `✅ Импортировать активные новые`
- `✅ Импортировать все новые`
- `❌ Отмена`
- `📤 Экспорт preview CSV`

CSV export can reuse existing storage/export patterns and include basic preview rows.

- [ ] **Step 4: Implement research queue Telegram actions**

After import, offer:
- `Только новые компании`
- `Только без сайта`
- `Top-50`
- `Все из последнего импорта`

Then show:

```text
🧠 Очередь research создана

Компаний: {count}
Задач создано: {jobs}
Параллельность: {concurrency}
```

- [ ] **Step 5: Register routers in bot startup**

In `app/bot.py`, include the new handler routers without disrupting existing menus and callbacks.

- [ ] **Step 6: Smoke the bot import path**

Run:

```bash
python -c "from app.bot import main; print('bot ok')"
```

Expected: bot module imports with the new handlers.

- [ ] **Step 7: Commit**

```bash
git add app/modules/legal_discovery/keyboards.py app/modules/legal_discovery/handlers.py app/modules/research_queue/keyboards.py app/modules/research_queue/handlers.py app/modules/crm/keyboards.py app/modules/crm/service.py app/bot.py
git commit -m "add discovery and research telegram workflow"
```

### Task 10: Integrate Research into AI, Proposals, Analytics, and Bot 2

**Files:**
- Modify: `app/modules/ai/prompts.py`
- Modify: `app/modules/ai/service.py`
- Modify: `app/modules/proposals/service.py`
- Modify: `app/modules/analytics/scoring.py`
- Modify: `app/modules/analytics/service.py`
- Modify: `app/modules/crm/schemas.py`

- [ ] **Step 1: Extend call prep context**

Add latest research/intelligence snapshot data to AI prep:
- website status/confidence
- contacts found
- socials found
- signals
- hypotheses

- [ ] **Step 2: Extend proposal suggestion rules**

Map signals:
- no online booking -> `audit_roadmap` / `landing_start`
- no socials -> `smm_funnel` / `audit_roadmap`
- no reviews -> `maps_reputation`

- [ ] **Step 3: Extend scoring rules**

Add:
- `+10` INN confirmed
- `+10` official website found medium/high confidence
- `+5` contacts found
- `-10` no website
- `-10` research blocked/needs_manual_review

Reasons/risks should mention discovery/research outcomes explicitly.

- [ ] **Step 4: Extend Bot 2 consultation context**

In `Bot2ConsultationContextRead`, include a `research` block with:
- status
- website
- website confidence
- contacts/socials/signals
- hypotheses
- ai summary if available

- [ ] **Step 5: Verify API schema stability**

Run:

```bash
python -c "from app.main import app; print(app.title)"
```

Expected: no FastAPI response-model errors.

- [ ] **Step 6: Commit**

```bash
git add app/modules/ai/prompts.py app/modules/ai/service.py app/modules/proposals/service.py app/modules/analytics/scoring.py app/modules/analytics/service.py app/modules/crm/schemas.py
git commit -m "integrate research into downstream modules"
```

### Task 11: Add Smoke Coverage and Documentation

**Files:**
- Create: `scripts/smoke_legal_discovery.py`
- Create: `scripts/smoke_research_queue.py`
- Modify: `README.md`
- Modify: `TASKS.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Implement `smoke_legal_discovery.py`**

Scenario:
- mock provider returns companies
- preview counters computed
- import creates companies
- repeated import creates no duplicates
- legal discovery API endpoints respond
- print `smoke_legal_discovery ok`

- [ ] **Step 2: Implement `smoke_research_queue.py`**

Scenario:
- create companies with INN
- create jobs
- monkeypatch/mock resolver and fetcher
- run batch
- website found
- contacts created
- intelligence snapshot created
- job statuses become success
- repeated pending job not duplicated
- research API endpoints respond
- print `smoke_research_queue ok`

- [ ] **Step 3: Update documentation**

README section should cover:
- legal discovery first
- preview/import
- queue and safe fetch/browser abstraction
- no bypass policy
- env vars
- Telegram/API/CLI usage
- smoke tests

TASKS and CHANGELOG should reflect the exact Done items from the spec.

- [ ] **Step 4: Run required verification suite**

Run:

```bash
python -m compileall app alembic
python scripts/smoke_check.py
python scripts/test_csv_import.py
python scripts/smoke_bot2_handoff.py
python scripts/test_digest_module.py
python scripts/smoke_proposals.py
python scripts/smoke_analytics.py
python scripts/smoke_bot2_context.py
python scripts/smoke_legal_discovery.py
python scripts/smoke_research_queue.py
python -c "from app.main import app; print(app.title)"
python -c "from app.bot import main; print('bot ok')"
python -m alembic upgrade head
```

Expected:
- every smoke prints its `ok` marker
- `compileall` succeeds
- app and bot import checks succeed

- [ ] **Step 5: Commit**

```bash
git add scripts/smoke_legal_discovery.py scripts/smoke_research_queue.py README.md TASKS.md CHANGELOG.md
git commit -m "add research smoke coverage and docs"
```

## Self-Review

- Spec coverage: the plan covers new modules, env/config, legal discovery preview/import, queue persistence, safe fetch abstraction, resolver/parser, Telegram/API/CLI, downstream integrations, smoke checks, docs, and migration.
- Placeholder scan: all tasks identify concrete files, functions, and commands; no `TODO` placeholders remain.
- Type consistency: `ResearchJob`, `LegalDiscoveryPreview`, `FetchResult`, `WebsiteResolutionResult`, and `ResearchResult` are used consistently across queue, API, and smoke tasks; durable snapshot storage remains `IntelligenceSnapshot` throughout.
