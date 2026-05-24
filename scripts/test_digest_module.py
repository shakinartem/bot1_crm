import asyncio
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import Base
from app.modules.crm.constants import CompanyStatus, InteractionResult, InteractionType, LeadPriority, TaskStatus
from app.modules.crm.models import Company, FollowUpTask, LeadInteraction
from app.modules.digest.service import get_hot_leads, get_stale_leads
from app.modules.digest.settings import (
    get_due_digest_settings,
    get_or_create_digest_settings,
    mark_digest_sent,
    update_digest_settings,
)


class DigestModuleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_hot_leads_prioritize_overdue_then_high_priority_then_status(self) -> None:
        now = datetime.now()

        async with self.session_factory() as session:
            top = Company(name="Top Dental", status=CompanyStatus.PROPOSAL_SENT.value, priority=LeadPriority.HIGH.value)
            middle = Company(name="Middle Dental", status=CompanyStatus.INTERESTED.value, priority=LeadPriority.HIGH.value)
            low = Company(name="Low Dental", status=CompanyStatus.INTERESTED.value, priority=LeadPriority.MEDIUM.value)
            session.add_all([top, middle, low])
            await session.flush()

            session.add_all(
                [
                    FollowUpTask(
                        company_id=top.id,
                        title="Send proposal",
                        due_at=now - timedelta(hours=2),
                        due_date=now - timedelta(hours=2),
                        status=TaskStatus.OPEN.value,
                        priority=LeadPriority.HIGH.value,
                    ),
                    LeadInteraction(
                        company_id=top.id,
                        type=InteractionType.CALL.value,
                        result=InteractionResult.PROPOSAL_REQUESTED.value,
                        created_at=now - timedelta(hours=1),
                    ),
                    LeadInteraction(
                        company_id=middle.id,
                        type=InteractionType.CALL.value,
                        result=InteractionResult.INTERESTED.value,
                        created_at=now - timedelta(hours=3),
                    ),
                    LeadInteraction(
                        company_id=low.id,
                        type=InteractionType.CALL.value,
                        result=InteractionResult.INTERESTED.value,
                        created_at=now - timedelta(minutes=30),
                    ),
                ]
            )
            await session.commit()

            leads = await get_hot_leads(session)

        self.assertEqual([lead.company_name for lead in leads[:3]], ["Top Dental", "Middle Dental", "Low Dental"])
        self.assertIn("просроч", leads[0].reason.lower())

    async def test_stale_leads_exclude_closed_statuses_and_include_no_touch_companies(self) -> None:
        now = datetime.now()

        async with self.session_factory() as session:
            stale = Company(name="Stale Clinic", status=CompanyStatus.INTERESTED.value, city="Saratov")
            no_touch = Company(
                name="No Touch Clinic",
                status=CompanyStatus.NEW.value,
                city="Moscow",
                created_at=now - timedelta(days=10),
            )
            closed = Company(
                name="Closed Clinic",
                status=CompanyStatus.DEAL_WON.value,
                created_at=now - timedelta(days=20),
            )
            session.add_all([stale, no_touch, closed])
            await session.flush()

            session.add(
                LeadInteraction(
                    company_id=stale.id,
                    type=InteractionType.CALL.value,
                    result=InteractionResult.INTERESTED.value,
                    created_at=now - timedelta(days=9),
                )
            )
            await session.commit()

            leads = await get_stale_leads(session, days_without_interaction=7)

        names = [lead.company_name for lead in leads]
        self.assertIn("Stale Clinic", names)
        self.assertIn("No Touch Clinic", names)
        self.assertNotIn("Closed Clinic", names)

    async def test_digest_settings_persist_and_scheduler_selection_uses_last_sent_at(self) -> None:
        now = datetime(2026, 5, 24, 9, 0)

        async with self.session_factory() as session:
            created = await get_or_create_digest_settings(session, telegram_user_id=101, default_enabled=True)
            self.assertTrue(created.enabled)

            updated = await update_digest_settings(
                session,
                telegram_user_id=101,
                send_time="09:00",
                stale_days=11,
                weekdays=(6,),
            )
            self.assertEqual(updated.stale_days, 11)

            due = await get_due_digest_settings(session, now=now, admin_user_ids=[101])
            self.assertEqual([item.telegram_user_id for item in due], [101])

            await mark_digest_sent(session, updated, sent_at=now)
            due_again = await get_due_digest_settings(session, now=now, admin_user_ids=[101])

        self.assertEqual(due_again, [])


if __name__ == "__main__":
    unittest.main()
