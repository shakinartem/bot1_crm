from __future__ import annotations

from pathlib import Path
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.calls.models import CallRecord
from app.modules.crm.models import Company, CompanyInsightSnapshot, ContactPoint, DecisionMaker, FollowUpTask, LeadInteraction, CRMUser
from app.modules.digest.models import DigestSettings
from app.modules.enrichment.models import EnrichmentSnapshot
from app.modules.intelligence.models import IntelligenceSnapshot
from app.modules.legal_discovery.models import LegalDiscoveryCursor
from app.modules.proposals.models import ProposalDraft
from app.modules.research_queue.models import ResearchJob

ResetMode = Literal["crm_only", "all_data"]


async def reset_database(
    session: AsyncSession,
    *,
    mode: ResetMode = "crm_only",
    keep_users: bool = True,
    clear_debug_files: bool | None = None,
) -> dict[str, int | bool | str]:
    settings = get_settings()
    if not settings.allow_db_reset:
        raise PermissionError("ALLOW_DB_RESET is disabled")

    if clear_debug_files is None:
        clear_debug_files = mode == "all_data"

    deleted_counts: dict[str, int | bool | str] = {
        "mode": mode,
        "keep_users": keep_users,
        "clear_debug_files": clear_debug_files,
    }
    ordered_models = [
        ("call_records", CallRecord),
        ("tasks", FollowUpTask),
        ("lead_interactions", LeadInteraction),
        ("contact_points", ContactPoint),
        ("decision_makers", DecisionMaker),
        ("company_insight_snapshots", CompanyInsightSnapshot),
        ("intelligence_snapshots", IntelligenceSnapshot),
        ("enrichment_snapshots", EnrichmentSnapshot),
        ("research_jobs", ResearchJob),
        ("proposal_drafts", ProposalDraft),
        ("legal_discovery_cursors", LegalDiscoveryCursor),
        ("companies", Company),
    ]
    for key, model in ordered_models:
        result = await session.execute(delete(model))
        deleted_counts[key] = result.rowcount or 0

    if mode == "all_data":
        digest_result = await session.execute(delete(DigestSettings))
        deleted_counts["digest_settings"] = digest_result.rowcount or 0
    else:
        deleted_counts["digest_settings"] = 0

    user_count = int(await session.scalar(select(func.count(CRMUser.id))) or 0)
    if not keep_users:
        user_result = await session.execute(delete(CRMUser))
        deleted_counts["crm_users_deleted"] = user_result.rowcount or 0
        deleted_counts["crm_users_kept"] = 0
    else:
        deleted_counts["crm_users_deleted"] = 0
        deleted_counts["crm_users_kept"] = user_count

    deleted_counts["debug_files_deleted"] = 0
    if clear_debug_files:
        deleted_counts["debug_files_deleted"] = _clear_debug_files(settings.storage_path)

    await session.commit()
    return deleted_counts


def _clear_debug_files(storage_path: Path) -> int:
    roots = [
        storage_path / "debug",
        storage_path / "imports",
        storage_path / "exports",
        storage_path / "proposals",
        storage_path / "calls",
        storage_path / "companies",
    ]
    deleted = 0
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.name == ".gitkeep":
                continue
            path.unlink(missing_ok=True)
            deleted += 1
    return deleted
