from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.database import create_db_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    for child in ("calls", "imports", "companies"):
        (settings.storage_path / child).mkdir(parents=True, exist_ok=True)
    await create_db_schema()
    yield


app = FastAPI(title="SHARiK Sales Intelligence Bot", version="0.1.0", lifespan=lifespan)
app.include_router(router)
