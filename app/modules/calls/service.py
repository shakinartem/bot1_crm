from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.calls.models import CallRecord


class TranscriptionStubService:
    async def transcribe(self, audio_path: str) -> str:
        return f"Транскрибация пока не подключена. Файл сохранен: {audio_path}"


async def save_call_record(
    session: AsyncSession,
    company_id: int,
    filename: str,
    content: bytes,
    manager_result: str | None = None,
) -> CallRecord:
    settings = get_settings()
    directory = settings.storage_path / "calls" / str(company_id)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / Path(filename).name
    target.write_bytes(content)

    transcript = await TranscriptionStubService().transcribe(str(target))
    record = CallRecord(company_id=company_id, audio_path=str(target), transcript=transcript, manager_result=manager_result)
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record
