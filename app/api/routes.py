from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.modules.ai.service import prepare_cold_call
from app.modules.crm import service as crm_service
from app.modules.crm.schemas import (
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
from app.modules.exports.service import ExportFilters, export_companies_to_csv
from app.modules.imports.service import import_companies_from_csv, preview_companies_from_csv, save_import_file

router = APIRouter()


@router.get("/health")
async def root_health() -> dict[str, str]:
    return {"status": "ok"}


api_router = APIRouter(prefix="/api")


@api_router.get("/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok"}


@api_router.get("/companies", response_model=list[CompanyRead])
async def list_companies(
    session: AsyncSession = Depends(get_session),
    limit: int = 20,
    offset: int = 0,
):
    return await crm_service.list_companies(session, limit=limit, offset=offset)


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


@api_router.get("/companies/{company_id}", response_model=CompanyRead)
async def get_company(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    company = await crm_service.get_company(session, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


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


router.include_router(api_router)
