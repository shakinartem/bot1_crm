from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import async_session_factory  # noqa: E402
from app.modules.crm.models import Company  # noqa: E402
from app.modules.research_queue.service import create_research_jobs_for_companies, run_research_batch  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run queued website research for CRM companies")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--source", type=str, default=None)
    parser.add_argument("--only-without-website", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    async with async_session_factory() as session:
        stmt = select(Company.id).order_by(Company.created_at.desc()).limit(args.limit)
        if args.source:
            stmt = stmt.where(Company.source == args.source)
        if args.only_without_website:
            stmt = stmt.where(Company.website.is_(None))
        result = await session.execute(stmt)
        company_ids = [item[0] for item in result.all()]
        if args.dry_run:
            print(f"dry-run companies: {len(company_ids)}")
            for company_id in company_ids[:10]:
                print(company_id)
            return
        jobs = await create_research_jobs_for_companies(session, company_ids)
        print(f"created jobs: {len(jobs)}")

    completed = await run_research_batch(async_session_factory, concurrency=args.concurrency, limit=args.limit)
    print(f"completed jobs: {len(completed)}")


if __name__ == "__main__":
    asyncio.run(main())
