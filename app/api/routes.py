from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.modules.crm import service as crm_service
from app.modules.crm.schemas import CompanyCreate, CompanyRead
from app.modules.imports.service import import_companies_from_csv

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/companies", response_model=CompanyRead)
async def create_company(payload: CompanyCreate, session: AsyncSession = Depends(get_session)):
    return await crm_service.create_company(session, payload)


@router.get("/companies", response_model=list[CompanyRead])
async def list_companies(session: AsyncSession = Depends(get_session), limit: int = 20, offset: int = 0):
    return await crm_service.list_companies(session, limit=limit, offset=offset)


@router.post("/imports/csv")
async def import_csv(file: UploadFile, session: AsyncSession = Depends(get_session)):
    content = await file.read()
    return await import_companies_from_csv(session, content.decode("utf-8-sig"))
