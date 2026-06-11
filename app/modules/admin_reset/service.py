from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.calls.models import CallRecord
from app.modules.crm.models import Company, ContactPoint, DecisionMaker, FollowUpTask, LeadInteraction
from app.modules.digest.models import DigestSettings
from app.modules.enrichment.models import EnrichmentSnapshot
from app.modules.intelligence.models import IntelligenceSnapshot
from app.modules.proposals.models import ProposalDraft
from app.modules.research_queue.models import ResearchJob


async def reset_database(session: AsyncSession, full_reset: bool = False) -> dict[str, int | bool]:
    settings = get_settings()
    if not settings.allow_db_reset:
        raise PermissionError("ALLOW_DB_RESET is disabled")

    deleted_counts: dict[str, int | bool] = {"full_reset": full_reset}
    ordered_models = [
        ("call_records", CallRecord),
        ("tasks", FollowUpTask),
        ("lead_interactions", LeadInteraction),
        ("contact_points", ContactPoint),
        ("decision_makers", DecisionMaker),
        ("company_insight_snapshots", None),
        ("intelligence_snapshots", IntelligenceSnapshot),
        ("enrichment_snapshots", EnrichmentSnapshot),
        ("research_jobs", ResearchJob),
        ("proposal_drafts", ProposalDraft),
        ("companies", Company),
    ]
    from app.modules.crm.models import CompanyInsightSnapshot

    for key, model in ordered_models:
        actual_model = CompanyInsightSnapshot if model is None else model
        result = await session.execute(delete(actual_model))
        deleted_counts[key] = result.rowcount or 0

    if full_reset:
        digest_result = await session.execute(delete(DigestSettings))
        deleted_counts["digest_settings"] = digest_result.rowcount or 0

    await session.commit()
    return deleted_counts
