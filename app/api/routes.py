from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.modules.analytics.schemas import (
    AnalyticsExportResult,
    CityAnalyticsItem,
    ColdBaseItem,
    FunnelAnalyticsRead,
    LeadScoreListRead,
    LeadScoreRead,
    SourceAnalyticsItem,
)
from app.modules.analytics.service import (
    build_city_analytics,
    build_cold_base,
    build_funnel_analytics,
    build_source_analytics,
    export_analytics_csv,
    get_company_lead_score,
    list_lead_scores,
)
from app.modules.ai.service import prepare_cold_call
from app.modules.crm import service as crm_service
from app.modules.crm.schemas import (
    Bot2ConsultationContextRead,
    Bot2ConsultationResultCreate,
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
    DecisionMakerCreate,
    DecisionMakerRead,
    FollowUpTaskCreate,
    FollowUpTaskRead,
    FollowUpTaskUpdate,
    InteractionCreate,
    InteractionRead,
)
from app.modules.digest.schemas import DailyDigestRead, LeadDigestItem, TaskDigestItem, WeeklySummaryRead
from app.modules.digest.service import (
    build_daily_digest,
    build_weekly_summary,
    get_hot_leads,
    get_overdue_tasks,
    get_stale_leads,
    get_today_tasks,
)
from app.modules.exports.service import ExportFilters, export_companies_to_csv
from app.modules.imports.service import import_companies_from_csv, preview_companies_from_csv, save_import_file
from app.modules.enrichment.schemas import EnrichmentRequest, EnrichmentResultRead, EnrichmentSnapshotRead
from app.modules.enrichment.service import (
    enrich_company_website,
    get_enrichment_history,
    get_enrichment_snapshot,
    get_latest_enrichment,
)
from app.modules.proposals.keyboards import package_catalog_payload
from app.modules.proposals.schemas import (
    ContractActionRequest,
    ContractDraftResultRead,
    PackageRead,
    PackageSuggestion,
    ProposalActionRequest,
    ProposalDraftRead,
    ProposalGenerationResultRead,
    ServiceAppendixResultRead,
)
from app.modules.proposals.service import (
    generate_commercial_proposal,
    generate_contract_draft,
    generate_service_appendix,
    get_proposal_draft,
    list_company_proposal_drafts,
    parse_selected_packages,
    suggest_packages_for_company,
)

router = APIRouter()


@router.get("/health")
async def root_health() -> dict[str, str]:
    return {"status": "ok"}


api_router = APIRouter(prefix="/api")
bot2_router = APIRouter(prefix="/api/bot2")


async def require_bot2_auth(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.bot2_api_token:
        return
    expected = f"Bearer {settings.bot2_api_token}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid BOT2 API token")


@api_router.get("/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok"}


@api_router.get("/companies", response_model=list[CompanyRead])
async def list_companies(
    session: AsyncSession = Depends(get_session),
    status: str | None = None,
    city: str | None = None,
    priority: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    return await crm_service.list_companies(
        session,
        limit=limit,
        offset=offset,
        status=status,
        city=city,
        priority=priority,
    )


@api_router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreate,
    session: AsyncSession = Depends(get_session),
):
    return await crm_service.create_company(session, payload)


@api_router.get("/companies/export")
async def export_companies(
    session: AsyncSession = Depends(get_session),
    status: str | None = None,
    city: str | None = None,
    source: str | None = None,
    priority: str | None = None,
    limit: int | None = None,
):
    result = await export_companies_to_csv(
        session,
        ExportFilters(
            status=status,
            city=city,
            source=source,
            priority=priority,
            limit=limit,
        ),
    )
    return FileResponse(
        result.file_path,
        media_type="text/csv",
        filename=result.filename,
    )


@api_router.get("/digest/daily", response_model=DailyDigestRead)
async def digest_daily(
    session: AsyncSession = Depends(get_session),
    manager_id: int | None = None,
):
    return await build_daily_digest(session, manager_id=manager_id)


@api_router.get("/digest/weekly", response_model=WeeklySummaryRead)
async def digest_weekly(
    session: AsyncSession = Depends(get_session),
    manager_id: int | None = None,
):
    return await build_weekly_summary(session, manager_id=manager_id)


@api_router.get("/digest/overdue-tasks", response_model=list[TaskDigestItem])
async def digest_overdue_tasks(
    session: AsyncSession = Depends(get_session),
    limit: int = 20,
):
    return await get_overdue_tasks(session, limit=limit)


@api_router.get("/digest/today-tasks", response_model=list[TaskDigestItem])
async def digest_today_tasks(
    session: AsyncSession = Depends(get_session),
    limit: int = 20,
):
    return await get_today_tasks(session, limit=limit)


@api_router.get("/digest/hot-leads", response_model=list[LeadDigestItem])
async def digest_hot_leads(
    session: AsyncSession = Depends(get_session),
    limit: int = 20,
):
    return await get_hot_leads(session, limit=limit)


@api_router.get("/digest/stale-leads", response_model=list[LeadDigestItem])
async def digest_stale_leads(
    session: AsyncSession = Depends(get_session),
    days_without_interaction: int = 7,
    limit: int = 20,
):
    return await get_stale_leads(session, days_without_interaction=days_without_interaction, limit=limit)


@api_router.get("/analytics/funnel", response_model=FunnelAnalyticsRead)
async def analytics_funnel(
    session: AsyncSession = Depends(get_session),
    status: str | None = None,
    source: str | None = None,
    city: str | None = None,
):
    return await build_funnel_analytics(session, status=status, source=source, city=city)


@api_router.get("/analytics/sources", response_model=list[SourceAnalyticsItem])
async def analytics_sources(
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    status: str | None = None,
    source: str | None = None,
    city: str | None = None,
):
    return await build_source_analytics(session, status=status, source=source, city=city, limit=limit)


@api_router.get("/analytics/cities", response_model=list[CityAnalyticsItem])
async def analytics_cities(
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    status: str | None = None,
    source: str | None = None,
    city: str | None = None,
):
    return await build_city_analytics(session, status=status, source=source, city=city, limit=limit)


@api_router.get("/analytics/scores", response_model=LeadScoreListRead)
async def analytics_scores(
    session: AsyncSession = Depends(get_session),
    limit: int = 20,
    status: str | None = None,
    source: str | None = None,
    city: str | None = None,
    grade: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
):
    items = await list_lead_scores(
        session,
        limit=limit,
        status=status,
        source=source,
        city=city,
        grade=grade,
        min_score=min_score,
        max_score=max_score,
    )
    return LeadScoreListRead(total=len(items), items=items)


@api_router.get("/analytics/cold-base", response_model=list[ColdBaseItem])
async def analytics_cold_base(
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    source: str | None = None,
    city: str | None = None,
):
    return await build_cold_base(session, limit=limit, source=source, city=city)


@api_router.get("/analytics/export")
async def analytics_export(
    type: str,
    session: AsyncSession = Depends(get_session),
    limit: int = 200,
    status: str | None = None,
    source: str | None = None,
    city: str | None = None,
    grade: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
):
    result = await export_analytics_csv(
        session,
        type,
        limit=limit,
        status=status,
        source=source,
        city=city,
        grade=grade,
        min_score=min_score,
        max_score=max_score,
    )
    return FileResponse(
        result.file_path,
        media_type="text/csv",
        filename=result.filename,
    )


@api_router.get("/proposals/packages", response_model=list[PackageRead])
async def proposals_packages():
    return package_catalog_payload()


@api_router.post("/companies/{company_id}/proposals/suggest-packages", response_model=list[PackageSuggestion])
async def proposals_suggest_packages(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    return await suggest_packages_for_company(session, company_id)


@api_router.post("/companies/{company_id}/proposals/generate", response_model=ProposalGenerationResultRead)
async def proposals_generate(
    company_id: int,
    payload: ProposalActionRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await generate_commercial_proposal(
        session,
        company_id,
        selected_package_codes=payload.selected_package_codes,
        use_ai=payload.use_ai,
    )
    return ProposalGenerationResultRead(
        title=result.title,
        content=result.content,
        file_path=str(result.file_path),
        selected_packages=result.selected_packages,
        used_ai=result.used_ai,
    )


@api_router.post("/companies/{company_id}/contracts/draft", response_model=ContractDraftResultRead)
async def contracts_draft(
    company_id: int,
    payload: ContractActionRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await generate_contract_draft(
        session,
        company_id,
        selected_package_codes=payload.selected_package_codes,
    )
    return ContractDraftResultRead(
        title=result.title,
        content=result.content,
        file_path=str(result.file_path),
        selected_packages=result.selected_packages,
    )


@api_router.post("/companies/{company_id}/contracts/service-appendix", response_model=ServiceAppendixResultRead)
async def contracts_service_appendix(
    company_id: int,
    payload: ContractActionRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await generate_service_appendix(
        session,
        company_id,
        selected_package_codes=payload.selected_package_codes,
    )
    return ServiceAppendixResultRead(
        title=result.title,
        content=result.content,
        file_path=str(result.file_path),
        selected_packages=result.selected_packages,
    )


@api_router.get("/companies/{company_id}/proposals/history", response_model=list[ProposalDraftRead])
async def proposals_history(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    drafts = await list_company_proposal_drafts(session, company_id)
    return [
        ProposalDraftRead(
            id=draft.id,
            company_id=draft.company_id,
            draft_type=draft.draft_type,
            title=draft.title,
            content=draft.content,
            file_path=draft.file_path,
            selected_packages=parse_selected_packages(draft.selected_packages),
            used_ai=draft.used_ai,
            created_by=draft.created_by,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )
        for draft in drafts
    ]


@api_router.get("/companies/{company_id}/proposals/{proposal_id}/file")
async def proposals_file(
    company_id: int,
    proposal_id: int,
    session: AsyncSession = Depends(get_session),
):
    draft = await get_proposal_draft(session, company_id, proposal_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Proposal draft not found")
    return FileResponse(
        draft.file_path,
        media_type="text/markdown",
        filename=draft.file_path.replace("\\", "/").split("/")[-1],
    )


@api_router.get("/companies/{company_id}", response_model=CompanyRead)
async def get_company(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    company = await crm_service.get_company(session, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@api_router.get("/companies/{company_id}/score", response_model=LeadScoreRead)
async def company_score(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await get_company_lead_score(session, company_id)
    if not result:
        raise HTTPException(status_code=404, detail="Company not found")
    return result


@api_router.post("/companies/{company_id}/enrichment/website", response_model=EnrichmentResultRead)
async def company_enrichment_website(
    company_id: int,
    payload: EnrichmentRequest,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await enrich_company_website(
            session,
            company_id,
            website_url=payload.website_url,
            use_ai=payload.use_ai,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.get("/companies/{company_id}/enrichment/latest", response_model=EnrichmentSnapshotRead)
async def company_enrichment_latest(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    snapshot = await get_latest_enrichment(session, company_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Enrichment snapshot not found")
    return snapshot


@api_router.get("/companies/{company_id}/enrichment/history", response_model=list[EnrichmentSnapshotRead])
async def company_enrichment_history(
    company_id: int,
    session: AsyncSession = Depends(get_session),
    limit: int = 10,
):
    return await get_enrichment_history(session, company_id, limit=limit)


@api_router.get("/companies/{company_id}/enrichment/{snapshot_id}", response_model=EnrichmentSnapshotRead)
async def company_enrichment_snapshot(
    company_id: int,
    snapshot_id: int,
    session: AsyncSession = Depends(get_session),
):
    snapshot = await get_enrichment_snapshot(session, company_id, snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Enrichment snapshot not found")
    return snapshot


@api_router.patch("/companies/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: int,
    payload: CompanyUpdate,
    session: AsyncSession = Depends(get_session),
):
    company = await crm_service.update_company(session, company_id, payload)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@api_router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    deleted = await crm_service.delete_company(session, company_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Company not found")


@api_router.get("/companies/{company_id}/interactions", response_model=list[InteractionRead])
async def list_interactions(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    return await crm_service.list_interactions(session, company_id)


@api_router.post(
    "/companies/{company_id}/interactions",
    response_model=InteractionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_interaction(
    company_id: int,
    payload: InteractionCreate,
    session: AsyncSession = Depends(get_session),
):
    data = payload.model_dump()
    data["company_id"] = company_id
    return await crm_service.add_interaction(session, InteractionCreate(**data))


@api_router.get("/companies/{company_id}/decision-makers", response_model=list[DecisionMakerRead])
async def list_decision_makers(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    return await crm_service.list_decision_makers(session, company_id)


@api_router.post(
    "/companies/{company_id}/decision-makers",
    response_model=DecisionMakerRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_decision_maker(
    company_id: int,
    payload: DecisionMakerCreate,
    session: AsyncSession = Depends(get_session),
):
    data = payload.model_dump()
    data["company_id"] = company_id
    return await crm_service.add_decision_maker(session, DecisionMakerCreate(**data))


@api_router.get("/tasks", response_model=list[FollowUpTaskRead])
async def list_tasks(
    session: AsyncSession = Depends(get_session),
    status: str | None = None,
):
    return await crm_service.list_tasks(session, status=status)


@api_router.post("/tasks", response_model=FollowUpTaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: FollowUpTaskCreate,
    session: AsyncSession = Depends(get_session),
):
    return await crm_service.create_task(session, payload)


@api_router.patch("/tasks/{task_id}", response_model=FollowUpTaskRead)
async def update_task(
    task_id: int,
    payload: FollowUpTaskUpdate,
    session: AsyncSession = Depends(get_session),
):
    task = await crm_service.update_task(session, task_id, payload)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@api_router.post("/imports/csv")
async def import_csv(
    file: UploadFile,
    mode: str = Query(default="preview", pattern="^(preview|commit)$"),
    import_mode: str = Query(default="skip", pattern="^(skip|update)$"),
    session: AsyncSession = Depends(get_session),
):
    content = await file.read()
    saved_path = save_import_file(content, file.filename)
    if mode == "commit":
        return await import_companies_from_csv(
            session,
            content,
            file_name=file.filename,
            file_path=str(saved_path),
            import_mode=import_mode,
        )
    return await preview_companies_from_csv(
        session,
        content,
        file_name=file.filename,
        file_path=str(saved_path),
    )


@api_router.post("/imports/csv/preview")
async def import_csv_preview(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
):
    content = await file.read()
    saved_path = save_import_file(content, file.filename)
    return await preview_companies_from_csv(
        session,
        content,
        file_name=file.filename,
        file_path=str(saved_path),
    )


@api_router.post("/imports/csv/commit")
async def import_csv_commit(
    file: UploadFile,
    import_mode: str = Query(default="skip", pattern="^(skip|update)$"),
    session: AsyncSession = Depends(get_session),
):
    content = await file.read()
    saved_path = save_import_file(content, file.filename)
    return await import_companies_from_csv(
        session,
        content,
        file_name=file.filename,
        file_path=str(saved_path),
        import_mode=import_mode,
    )


@api_router.post("/companies/{company_id}/ai/call-prep")
async def ai_call_prep(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await prepare_cold_call(session, company_id)
    if not result:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"company_id": company_id, "call_prep": result}


@bot2_router.get(
    "/consultation-ready",
    response_model=list[CompanyRead],
    dependencies=[Depends(require_bot2_auth)],
)
async def bot2_consultation_ready(
    session: AsyncSession = Depends(get_session),
    limit: int = 100,
    offset: int = 0,
):
    return await crm_service.list_bot2_consultation_ready(session, limit=limit, offset=offset)


@bot2_router.get(
    "/companies/{company_id}/consultation-context",
    response_model=Bot2ConsultationContextRead,
    dependencies=[Depends(require_bot2_auth)],
)
async def bot2_consultation_context(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    context = await crm_service.build_bot2_consultation_context(session, company_id)
    if not context:
        raise HTTPException(status_code=404, detail="Company not found")
    return context


@bot2_router.post(
    "/companies/{company_id}/consultation-result",
    response_model=CompanyRead,
    dependencies=[Depends(require_bot2_auth)],
)
async def bot2_consultation_result(
    company_id: int,
    payload: Bot2ConsultationResultCreate,
    session: AsyncSession = Depends(get_session),
):
    company = await crm_service.apply_bot2_consultation_result(session, company_id, payload)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


router.include_router(api_router)
router.include_router(bot2_router)
