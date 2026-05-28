from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.modules.analytics.service import build_company_lead_score
from app.modules.ai.service import generate_daily_recommendation
from app.modules.crm.constants import CompanyStatus, InteractionResult, InteractionType, LeadPriority, TaskStatus
from app.modules.crm.models import Company, FollowUpTask, LeadInteraction
from app.modules.crm.service import format_datetime, humanize_interaction_result
from app.modules.digest.schemas import ActivitySummary, DailyDigestRead, LeadDigestItem, TaskDigestItem, WeeklySummaryRead
from app.modules.digest.settings import DEFAULT_STALE_DAYS, get_or_create_digest_settings


HOT_STATUSES = {
    CompanyStatus.INTERESTED.value,
    CompanyStatus.CONSULTATION_PLANNED.value,
    CompanyStatus.PROPOSAL_SENT.value,
}
HOT_RESULTS = {
    InteractionResult.INTERESTED.value,
    InteractionResult.CALLBACK_REQUESTED.value,
    InteractionResult.CONSULTATION_BOOKED.value,
    InteractionResult.PROPOSAL_REQUESTED.value,
}
STALE_EXCLUDED_STATUSES = {
    CompanyStatus.DEAL_WON.value,
    CompanyStatus.DEAL_LOST.value,
    CompanyStatus.DO_NOT_CONTACT.value,
}


async def get_overdue_tasks(
    session: AsyncSession,
    limit: int = 20,
) -> list[TaskDigestItem]:
    now = datetime.now()
    result = await session.execute(
        select(FollowUpTask)
        .options(selectinload(FollowUpTask.company))
        .where(
            FollowUpTask.status == TaskStatus.OPEN.value,
            FollowUpTask.due_at.is_not(None),
            FollowUpTask.due_at < now,
        )
        .order_by(FollowUpTask.due_at.asc(), FollowUpTask.created_at.asc())
        .limit(limit)
    )
    return [_task_digest_item(task) for task in result.scalars().all()]


async def get_today_tasks(
    session: AsyncSession,
    limit: int = 20,
) -> list[TaskDigestItem]:
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    result = await session.execute(
        select(FollowUpTask)
        .options(selectinload(FollowUpTask.company))
        .where(
            FollowUpTask.status == TaskStatus.OPEN.value,
            FollowUpTask.due_at.is_not(None),
            FollowUpTask.due_at >= start,
            FollowUpTask.due_at < end,
        )
    )
    tasks = list(result.scalars().all())
    tasks.sort(
        key=lambda task: (
            0 if task.priority == LeadPriority.HIGH.value else 1,
            task.due_at or datetime.max,
        )
    )
    return [_task_digest_item(task) for task in tasks[:limit]]


async def get_hot_leads(
    session: AsyncSession,
    limit: int = 20,
) -> list[LeadDigestItem]:
    companies = await _load_digest_companies(session)
    scored: list[tuple[tuple, LeadDigestItem]] = []

    for company in companies:
        lead_score = build_company_lead_score(company)
        last_interaction = _last_interaction(company)
        next_task = _next_open_task(company)
        overdue_task = _has_overdue_task(company)
        due_today = _has_due_today_task(company)
        high_priority = company.priority == LeadPriority.HIGH.value
        hot_by_status = company.status in HOT_STATUSES
        hot_by_result = bool(last_interaction and last_interaction.result in HOT_RESULTS)

        reasons: list[str] = []
        if hot_by_status:
            reasons.append(f"статус={company.status}")
        if high_priority:
            reasons.append("priority=high")
        if overdue_task:
            reasons.append("есть просроченная задача")
        elif due_today:
            reasons.append("есть задача на сегодня")
        if hot_by_result and last_interaction:
            reasons.append(f"последний результат={last_interaction.result}")

        if not reasons:
            continue

        status_weight = {
            CompanyStatus.PROPOSAL_SENT.value: 3,
            CompanyStatus.CONSULTATION_PLANNED.value: 2,
            CompanyStatus.INTERESTED.value: 1,
        }.get(company.status, 0)
        freshness = _timestamp_value(last_interaction.created_at if last_interaction else None)

        scored.append(
            (
                (
                    0 if overdue_task else 1,
                    0 if high_priority else 1,
                    -lead_score.score,
                    -status_weight,
                    -freshness,
                    0 if last_interaction else 1,
                ),
                _lead_digest_item(
                    company,
                    reason=", ".join(reasons),
                    next_task=next_task,
                    last_interaction=last_interaction,
                    score=lead_score.score,
                    grade=lead_score.grade,
                    proposal_recommendation=lead_score.proposal_recommendation,
                ),
            )
        )

    scored.sort(key=lambda item: item[0])
    return [item for _, item in scored[:limit]]


async def get_stale_leads(
    session: AsyncSession,
    days_without_interaction: int = 7,
    limit: int = 20,
) -> list[LeadDigestItem]:
    companies = await _load_digest_companies(session)
    now = datetime.now()
    items: list[LeadDigestItem] = []

    for company in companies:
        if company.status in STALE_EXCLUDED_STATUSES:
            continue

        last_interaction = _last_interaction(company)
        next_task = _next_open_task(company)
        anchor = last_interaction.created_at if last_interaction else company.created_at
        days = max((now.date() - anchor.date()).days, 0)
        if days < days_without_interaction:
            continue

        items.append(
            _lead_digest_item(
                company,
                reason=f"{days} дней без касаний" if days else "нет касаний",
                next_task=next_task,
                last_interaction=last_interaction,
                days_without_interaction=days,
            )
        )

    items.sort(key=lambda item: (-(item.days_without_interaction or 0), item.company_name))
    return items[:limit]


async def get_yesterday_activity(session: AsyncSession) -> ActivitySummary:
    now = datetime.now()
    start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return await _build_activity_summary(session, start, end)


async def get_week_activity(session: AsyncSession) -> ActivitySummary:
    end = datetime.now()
    start = end - timedelta(days=7)
    return await _build_activity_summary(session, start, end)


async def build_daily_digest(session: AsyncSession, manager_id: int | None = None) -> DailyDigestRead:
    overdue = await get_overdue_tasks(session)
    today = await get_today_tasks(session)
    hot = await get_hot_leads(session)
    top_scored = await get_top_scored_leads(session, limit=3)

    stale_days = DEFAULT_STALE_DAYS
    if manager_id is not None:
        default_enabled = manager_id in set(get_settings().admin_id_list)
        settings = await get_or_create_digest_settings(
            session,
            manager_id,
            default_enabled=default_enabled,
        )
        stale_days = settings.stale_days

    stale = await get_stale_leads(session, days_without_interaction=stale_days)
    yesterday = await get_yesterday_activity(session)
    recommendation = await recommend_daily_focus(
        {
            "overdue_tasks": len(overdue),
            "today_tasks": len(today),
            "hot_leads": len(hot),
            "stale_leads": len(stale),
            "yesterday_interactions": yesterday.interactions_total,
            "yesterday_interested": yesterday.interested_count,
            "yesterday_consultations": yesterday.consultations_count,
            "yesterday_proposals": yesterday.proposals_count,
            "yesterday_rejections": yesterday.deals_lost_count,
        }
    )

    return DailyDigestRead(
        date=datetime.now().strftime("%d.%m.%Y"),
        overdue_tasks=overdue,
        today_tasks=today,
        hot_leads=hot,
        top_scored_leads=top_scored,
        stale_leads=stale,
        yesterday_activity=yesterday,
        recommendation=recommendation,
    )


async def build_weekly_summary(session: AsyncSession, manager_id: int | None = None) -> WeeklySummaryRead:
    end = datetime.now()
    start = end - timedelta(days=7)
    activity = await _build_activity_summary(session, start, end)
    recommendation = _rule_based_weekly_recommendation(activity)
    return WeeklySummaryRead(
        date_from=start.strftime("%d.%m.%Y"),
        date_to=end.strftime("%d.%m.%Y"),
        activity=activity,
        recommendation=recommendation,
    )


async def get_top_scored_leads(
    session: AsyncSession,
    limit: int = 3,
) -> list[LeadDigestItem]:
    companies = await _load_digest_companies(session)
    items: list[tuple[int, LeadDigestItem]] = []
    for company in companies:
        score = build_company_lead_score(company)
        if score.score <= 0:
            continue
        items.append(
            (
                score.score,
                _lead_digest_item(
                    company,
                    reason=score.next_best_action,
                    next_task=_next_open_task(company),
                    last_interaction=_last_interaction(company),
                    score=score.score,
                    grade=score.grade,
                    proposal_recommendation=score.proposal_recommendation,
                ),
            )
        )
    items.sort(key=lambda item: (-item[0], item[1].company_name.lower()))
    return [item for _, item in items[:limit]]


async def recommend_daily_focus(digest: dict) -> str:
    ai_text = await generate_daily_recommendation(digest)
    if ai_text:
        return ai_text.strip()

    actions: list[str] = []
    if digest.get("overdue_tasks", 0):
        actions.append("1. Сначала закрыть просроченные задачи.")
    if digest.get("hot_leads", 0):
        actions.append("2. Затем обработать interested / consultation_planned / proposal_sent.")
    if digest.get("stale_leads", 0):
        actions.append("3. Потом вернуться к компаниям без касаний больше 7 дней.")
    if not actions:
        actions.append("1. Начни с задач на сегодня и обнови статусы после касаний.")
    return "\n".join(actions)


async def _build_activity_summary(
    session: AsyncSession,
    start: datetime,
    end: datetime,
) -> ActivitySummary:
    interaction_result = await session.execute(
        select(LeadInteraction).where(
            LeadInteraction.created_at >= start,
            LeadInteraction.created_at < end,
        )
    )
    interactions = list(interaction_result.scalars().all())

    task_result = await session.execute(
        select(FollowUpTask).where(
            FollowUpTask.completed_at.is_not(None),
            FollowUpTask.completed_at >= start,
            FollowUpTask.completed_at < end,
        )
    )
    completed_tasks = list(task_result.scalars().all())

    company_result = await session.execute(
        select(Company).where(
            Company.created_at >= start,
            Company.created_at < end,
        )
    )
    new_companies = list(company_result.scalars().all())

    return ActivitySummary(
        interactions_total=len(interactions),
        calls_total=sum(1 for item in interactions if item.type == InteractionType.CALL.value),
        messages_total=sum(1 for item in interactions if item.type == InteractionType.MESSAGE.value),
        emails_total=sum(1 for item in interactions if item.type == InteractionType.EMAIL.value),
        interested_count=sum(1 for item in interactions if item.result == InteractionResult.INTERESTED.value),
        consultations_count=sum(1 for item in interactions if item.result == InteractionResult.CONSULTATION_BOOKED.value),
        proposals_count=sum(
            1
            for item in interactions
            if item.result == InteractionResult.PROPOSAL_REQUESTED.value or item.type == InteractionType.PROPOSAL.value
        ),
        deals_won_count=sum(1 for item in interactions if item.result == InteractionResult.DEAL_WON.value),
        deals_lost_count=sum(
            1
            for item in interactions
            if item.result in {InteractionResult.DEAL_LOST.value, InteractionResult.REJECTED.value}
        ),
        tasks_done_count=len(completed_tasks),
        new_companies_count=len(new_companies),
        overdue_tasks_count=await session.scalar(
            select(func.count(FollowUpTask.id)).where(
                FollowUpTask.status == TaskStatus.OPEN.value,
                FollowUpTask.due_at.is_not(None),
                FollowUpTask.due_at < datetime.now(),
            )
        )
        or 0,
    )


async def _load_digest_companies(session: AsyncSession) -> list[Company]:
    result = await session.execute(
        select(Company)
        .options(
            selectinload(Company.decision_makers),
            selectinload(Company.contacts),
            selectinload(Company.interactions),
            selectinload(Company.tasks),
            selectinload(Company.enrichment_snapshots),
            selectinload(Company.intelligence_snapshots),
        )
        .order_by(Company.created_at.desc())
    )
    return list(result.scalars().unique().all())


def _task_digest_item(task: FollowUpTask) -> TaskDigestItem:
    return TaskDigestItem(
        task_id=task.id,
        company_id=task.company_id,
        company_name=task.company.name if task.company else f"Компания #{task.company_id}",
        title=task.title,
        due_at=format_datetime(task.due_at) if task.due_at else None,
        priority=task.priority,
        company_status=task.company.status if task.company else CompanyStatus.NEW.value,
    )


def _lead_digest_item(
    company: Company,
    *,
    reason: str,
    next_task: FollowUpTask | None,
    last_interaction: LeadInteraction | None,
    days_without_interaction: int | None = None,
    score: int | None = None,
    grade: str | None = None,
    proposal_recommendation: str | None = None,
) -> LeadDigestItem:
    return LeadDigestItem(
        company_id=company.id,
        company_name=company.name,
        city=company.city,
        status=company.status,
        priority=company.priority,
        score=score,
        grade=grade,
        last_interaction_at=format_datetime(last_interaction.created_at) if last_interaction else None,
        last_interaction_result=(
            humanize_interaction_result(last_interaction.result) if last_interaction and last_interaction.result else None
        ),
        next_task_due_at=format_datetime(next_task.due_at) if next_task and next_task.due_at else None,
        next_task_title=next_task.title if next_task else None,
        reason=reason,
        days_without_interaction=days_without_interaction,
        proposal_recommendation=proposal_recommendation,
    )


def _last_interaction(company: Company) -> LeadInteraction | None:
    if not company.interactions:
        return None
    return sorted(company.interactions, key=lambda item: item.created_at or datetime.min, reverse=True)[0]


def _next_open_task(company: Company) -> FollowUpTask | None:
    tasks = [task for task in company.tasks if task.status == TaskStatus.OPEN.value]
    if not tasks:
        return None
    return sorted(tasks, key=lambda item: (item.due_at is None, item.due_at or datetime.max))[0]


def _has_overdue_task(company: Company) -> bool:
    now = datetime.now()
    return any(
        task.status == TaskStatus.OPEN.value and task.due_at and task.due_at < now
        for task in company.tasks
    )


def _has_due_today_task(company: Company) -> bool:
    today = datetime.now().date()
    return any(
        task.status == TaskStatus.OPEN.value and task.due_at and task.due_at.date() == today
        for task in company.tasks
    )


def _timestamp_value(value: datetime | None) -> float:
    if value is None:
        return float("-inf")
    return value.timestamp()


def _rule_based_weekly_recommendation(activity: ActivitySummary) -> str:
    suggestions = [
        "1. Дожать proposal_sent и consultation_planned.",
        "2. Вернуться к interested без активных задач.",
        "3. Закрыть просроченные follow-up и stale leads.",
    ]
    if activity.proposals_count == 0:
        suggestions[0] = "1. Увеличить число КП и follow-up после интереса."
    if activity.interested_count == 0:
        suggestions[1] = "2. Пересобрать первичные касания и скрипт первого контакта."
    return "\n".join(suggestions)
