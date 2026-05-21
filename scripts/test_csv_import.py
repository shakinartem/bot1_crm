import asyncio
import shutil
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base
from app.modules.calls.models import CallRecord  # noqa: F401
from app.modules.crm.models import Company, ContactPoint, DecisionMaker, FollowUpTask, LeadInteraction  # noqa: F401
from app.modules.imports.service import import_companies_from_csv, preview_companies_from_csv


async def main() -> None:
    temp_dir = PROJECT_ROOT / "storage" / "test_csv_import_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    db_path = temp_dir / "csv_import_test.db"
    if db_path.exists():
        db_path.unlink()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sample = (
            "Название;ИНН;Телефон;Сайт;Город;Источник\n"
            "Клиника Улыбка;1234567890;+7 (999) 000-00-01;https://ulybka.ru/;Уфа;CSV база\n"
            "Клиника Дент;2234567890;8 999 000 00 02;http://dent.ru;Казань;CSV база\n"
            ";3234567890;+7 (999) 000-00-03;https://bad.ru;Самара;CSV база\n"
        ).encode("cp1251")

        async with session_factory() as session:
            preview = await preview_companies_from_csv(session, sample, file_name="sample.csv")
            assert preview["delimiter"] == "semicolon (;)"
            assert preview["valid_rows"] == 2
            assert preview["empty_name_rows"] == 1

            report = await import_companies_from_csv(session, sample, file_name="sample.csv", import_mode="skip")
            assert report["added"] == 2
            assert report["skipped_duplicates"] == 0
            assert report["error_rows"] == 1

        async with session_factory() as session:
            repeat = await import_companies_from_csv(session, sample, file_name="sample.csv", import_mode="skip")
            assert repeat["added"] == 0
            assert repeat["skipped_duplicates"] == 2
    finally:
        await engine.dispose()
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

    print("test_csv_import ok")


if __name__ == "__main__":
    asyncio.run(main())
