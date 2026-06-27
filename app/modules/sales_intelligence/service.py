from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.ai.providers import get_ai_provider
from app.modules.crm.constants import TaskStatus
from app.modules.crm.models import Company, ContactPoint, DecisionMaker, FollowUpTask, LeadInteraction
from app.modules.crm.service import get_company, humanize_company_status
from app.modules.enrichment.schemas import parse_json_text
from app.modules.enrichment.service import build_enrichment_context_for_company, get_latest_enrichment
from app.modules.insights.schemas import CompanyInsightSnapshotCreate
from app.modules.insights.service import create_company_insight_snapshot, get_latest_company_insight, safe_load_payload
from app.modules.intelligence.service import build_intelligence_context_for_company, get_latest_intelligence
from app.modules.research.service import get_latest_research
from app.modules.sales_intelligence.prompts import build_cold_call_plan_prompt
from app.modules.sales_intelligence.scoring import calculate_material_quality_score
from app.modules.sales_intelligence.schemas import (
    ClosingCriteriaReadiness,
    ClosingCriterionReadiness,
    ColdCallPlan,
    LatestSalesIntelligenceRead,
    ObjectionHandlingItem,
    SalesMaterialScore,
    SopranoQuestionSet,
)


_STATUS_ORDER = {"unknown": 0, "weak": 1, "possible": 2, "strong": 3}
_CRITICALITY_ORDER = {
    "decision_maker": 0,
    "conscious_need": 1,
    "financial_opportunity": 2,
    "here_and_now": 3,
    "trust": 4,
}
_DENTAL_KEYWORDS = (
    "dental",
    "dent",
    "stomat",
    "implant",
    "orthodont",
    "clinic",
    "dentistry",
)
_SALES_INSIGHT_TYPE = "sales_intelligence"
_SALES_INSIGHT_TITLE = "Sales Intelligence / план звонка"
_SALES_INSIGHT_SOURCE = "sales_intelligence"


async def get_company_sales_context(session: AsyncSession, company_id: int) -> dict[str, Any]:
    company = await get_company(session, company_id)
    if not company:
        raise ValueError("Company not found")

    latest_enrichment = await get_latest_enrichment(session, company_id)
    latest_intelligence = await get_latest_intelligence(session, company_id)
    latest_research = await get_latest_research(session, company_id)
    latest_maps_research = await get_latest_company_insight(session, company_id, "maps_research")
    enrichment_context = await build_enrichment_context_for_company(session, company_id)
    intelligence_context = await build_intelligence_context_for_company(session, company_id)

    decision_makers = sorted(
        company.decision_makers,
        key=lambda item: (not item.is_primary, item.created_at or datetime.min),
    )
    contacts = sorted(
        company.contacts,
        key=lambda item: (not item.is_primary, item.created_at or datetime.min),
    )
    recent_interactions = sorted(
        company.interactions,
        key=lambda item: item.created_at or datetime.min,
        reverse=True,
    )[:10]
    open_tasks = sorted(
        [item for item in company.tasks if item.status == TaskStatus.OPEN.value],
        key=lambda item: (item.due_at is None, item.due_at or datetime.max, item.created_at or datetime.min),
    )

    research_job_result = _get_latest_research_job_result(company)
    niche_detected, niche_confidence = _detect_niche(
        company,
        latest_enrichment=latest_enrichment,
        latest_intelligence=latest_intelligence,
        latest_research_job_result=research_job_result,
    )
    scoring_context = _build_scoring_context(
        company,
        decision_makers=decision_makers,
        contacts=contacts,
        latest_enrichment=latest_enrichment,
        latest_intelligence=latest_intelligence,
        latest_research=latest_research,
        latest_maps_research=latest_maps_research,
    )

    return {
        "company_id": company.id,
        "company": _serialize_company(company),
        "contacts": [_serialize_contact(item) for item in contacts],
        "decision_makers": [_serialize_decision_maker(item) for item in decision_makers],
        "latest_enrichment": _model_dump(latest_enrichment),
        "latest_enrichment_context": _model_dump(enrichment_context),
        "latest_intelligence": _model_dump(latest_intelligence),
        "latest_intelligence_context": _model_dump(intelligence_context),
        "latest_research": _model_dump(latest_research),
        "latest_maps_research": safe_load_payload(latest_maps_research) if latest_maps_research else None,
        "latest_research_job_result": research_job_result,
        "recent_interactions": [_serialize_interaction(item) for item in recent_interactions],
        "open_tasks": [_serialize_task(item) for item in open_tasks],
        "scoring_context": scoring_context,
        "website": scoring_context["website"],
        "socials": scoring_context["socials"],
        "maps": scoring_context["maps"],
        "maps_research": scoring_context.get("maps_research"),
        "trust": scoring_context["trust"],
        "contacts_normalized": scoring_context["contacts"],
        "niche_detected": niche_detected,
        "niche_confidence": niche_confidence,
    }


async def calculate_company_material_score(session: AsyncSession, company_id: int) -> SalesMaterialScore:
    company_context = await get_company_sales_context(session, company_id)
    return _calculate_material_score_from_context(company_context)


async def build_closing_criteria_readiness(
    session: AsyncSession,
    company_id: int,
) -> ClosingCriteriaReadiness:
    company_context = await get_company_sales_context(session, company_id)
    material_score = _calculate_material_score_from_context(company_context)
    return _build_closing_criteria_from_context(company_context, material_score)


async def generate_soprano_questions(
    session: AsyncSession,
    company_id: int,
    niche: str | None = None,
) -> SopranoQuestionSet:
    company_context = await get_company_sales_context(session, company_id)
    return _build_soprano_questions_from_context(company_context, niche=niche)


async def generate_cold_call_plan(
    session: AsyncSession,
    company_id: int,
    use_ai: bool = True,
    force_regenerate: bool = False,
    niche: str | None = None,
    persist: bool = True,
) -> ColdCallPlan:
    del force_regenerate

    company_context, material_score, closing_criteria, soprano_questions = await _build_sales_intelligence_components(
        session,
        company_id,
        niche=niche,
    )
    fallback_plan = build_fallback_cold_call_plan(
        company_context,
        material_score,
        closing_criteria,
        soprano_questions,
    )

    if not use_ai or get_settings().ai_provider.lower() == "fallback":
        if persist:
            await _persist_sales_intelligence_snapshot(
                session,
                company_id,
                material_score,
                closing_criteria,
                soprano_questions,
                fallback_plan,
            )
        return fallback_plan

    prompt = build_cold_call_plan_prompt(
        company_context,
        material_score,
        closing_criteria,
        soprano_questions,
    )
    try:
        raw_response = await get_ai_provider().generate(prompt)
    except Exception:
        if persist:
            await _persist_sales_intelligence_snapshot(
                session,
                company_id,
                material_score,
                closing_criteria,
                soprano_questions,
                fallback_plan,
            )
        return fallback_plan

    ai_plan = _parse_ai_cold_call_plan(raw_response, fallback_plan)
    final_plan = ai_plan or fallback_plan
    if persist:
        await _persist_sales_intelligence_snapshot(
            session,
            company_id,
            material_score,
            closing_criteria,
            soprano_questions,
            final_plan,
        )
    return final_plan


def build_fallback_cold_call_plan(
    company_context: dict[str, Any],
    material_score: SalesMaterialScore,
    closing_criteria: ClosingCriteriaReadiness,
    soprano_questions: SopranoQuestionSet,
) -> ColdCallPlan:
    company = company_context["company"]
    company_name = company["name"]
    niche_detected = soprano_questions.niche_detected
    observations = _build_digital_observations(company_context, material_score)
    likely_pains = _build_likely_pains(material_score, closing_criteria)
    personalization_points = _build_personalization_points(company_context, material_score)
    first_offer = "Предложить короткую диагностическую сессию, чтобы понять, где заявки замедляются до записи."
    next_best_action = (
        f"На следующем касании подтвердить: {closing_criteria.next_best_question.lower().rstrip('?')}."
        if closing_criteria.next_best_question
        else "На следующем касании подтвердить, есть ли смысл выходить на более глубокую диагностику."
    )
    short_script = _build_short_script(
        company_name=company_name,
        reason_for_call=_reason_for_call(material_score, observations),
        next_question=closing_criteria.next_best_question,
        first_offer=first_offer,
    )
    detailed_script = _build_detailed_script(
        company_name=company_name,
        observations=observations,
        closing_criteria=closing_criteria,
        first_offer=first_offer,
        soprano_questions=soprano_questions,
    )
    return ColdCallPlan(
        company_id=int(company["id"]),
        company_name=company_name,
        niche=soprano_questions.niche,
        niche_detected=niche_detected,
        niche_confidence=soprano_questions.niche_confidence,
        generation_mode="fallback",
        confidence=_plan_confidence(material_score, closing_criteria),
        created_at=datetime.utcnow(),
        call_goal=(
            "Понять, теряет ли компания спрос между первым интересом и следующим целевым шагом,"
            " а затем мягко вывести разговор к короткой диагностике."
        ),
        opener=(
            f"Добрый день. Подскажите, пожалуйста, я говорю с человеком, который отвечает за рост и привлечение в {company_name}? "
            "Звоню с аккуратной гипотезой по публичной digital-стороне и хотел бы быстро сверить её с вами."
        ),
        reason_for_call=_reason_for_call(material_score, observations),
        personalization_points=personalization_points,
        digital_observations=observations,
        likely_pains=likely_pains,
        closing_criteria=closing_criteria,
        soprano_questions=soprano_questions,
        objection_preparation=_build_objection_preparation(),
        first_offer=first_offer,
        next_best_action=next_best_action,
        call_script_short=short_script,
        call_script_detailed=detailed_script,
        copyable_short_script=short_script,
        manager_checklist=[
            "Перед звонком откройте сайт, карточки на картах и последние заметки по компании.",
            "В первую минуту уточните, вышли ли вы на ЛПР или пока общаетесь через фильтр.",
            "До любого оффера задайте хотя бы один вопрос из 5 критериев сделки.",
            "Все наблюдения формулируйте как гипотезу по публичной стороне, а не как установленный факт.",
            "Завершайте звонок либо договорённостью о следующем шаге, либо понятной причиной, почему сейчас не время.",
        ],
        risks=_dedupe_preserve_order(
            [
                *material_score.risks[:4],
                *closing_criteria.risks[:4],
                "Публичные сигналы могут быть неполными, поэтому каждую гипотезу нужно проверять прямо в разговоре.",
            ]
        ),
        do_not_say=[
            "Мы точно знаем, где вы теряете пациентов.",
            "У вас сломан сайт.",
            "Вам срочно нужен новый подрядчик.",
            "Мы гарантируем рост выручки.",
            "Я уже понимаю ваш бюджет и внутренний процесс.",
        ],
    )


async def get_latest_sales_intelligence(
    session: AsyncSession,
    company_id: int,
) -> LatestSalesIntelligenceRead:
    snapshot = await get_latest_company_insight(session, company_id, _SALES_INSIGHT_TYPE)
    latest = _build_latest_sales_intelligence_from_snapshot(snapshot)
    if latest is not None:
        return latest
    return await _build_latest_sales_intelligence_on_demand(session, company_id)


async def _build_latest_sales_intelligence_on_demand(
    session: AsyncSession,
    company_id: int,
    *,
    niche: str | None = None,
) -> LatestSalesIntelligenceRead:
    _, material_score, closing_criteria, soprano_questions = await _build_sales_intelligence_components(
        session,
        company_id,
        niche=niche,
    )
    return LatestSalesIntelligenceRead(
        material_score=material_score,
        closing_criteria=closing_criteria,
        soprano_questions=soprano_questions,
        cold_call_plan=None,
        saved_at=None,
    )


async def _build_sales_intelligence_components(
    session: AsyncSession,
    company_id: int,
    *,
    niche: str | None,
) -> tuple[dict[str, Any], SalesMaterialScore, ClosingCriteriaReadiness, SopranoQuestionSet]:
    company_context = await get_company_sales_context(session, company_id)
    material_score = _calculate_material_score_from_context(company_context)
    closing_criteria = _build_closing_criteria_from_context(company_context, material_score)
    soprano_questions = _build_soprano_questions_from_context(company_context, niche=niche)
    return company_context, material_score, closing_criteria, soprano_questions


def _build_latest_sales_intelligence_from_snapshot(snapshot: Any) -> LatestSalesIntelligenceRead | None:
    payload = safe_load_payload(snapshot)
    if payload is None:
        return None

    try:
        material_score = SalesMaterialScore.model_validate(payload.get("material_score") or {})
        closing_criteria = ClosingCriteriaReadiness.model_validate(payload.get("closing_criteria") or {})
        soprano_questions = SopranoQuestionSet.model_validate(payload.get("soprano_questions") or {})
    except ValidationError:
        return None

    cold_call_plan_payload = payload.get("cold_call_plan")
    cold_call_plan: ColdCallPlan | None = None
    if cold_call_plan_payload is not None:
        try:
            cold_call_plan = ColdCallPlan.model_validate(cold_call_plan_payload)
        except ValidationError:
            return None

    saved_at = _parse_snapshot_saved_at(payload.get("saved_at"), fallback=snapshot.created_at)
    return LatestSalesIntelligenceRead(
        material_score=material_score,
        closing_criteria=closing_criteria,
        soprano_questions=soprano_questions,
        cold_call_plan=cold_call_plan,
        saved_at=saved_at,
    )


def _parse_snapshot_saved_at(value: Any, *, fallback: datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return fallback
    return fallback


async def _persist_sales_intelligence_snapshot(
    session: AsyncSession,
    company_id: int,
    material_score: SalesMaterialScore,
    closing_criteria: ClosingCriteriaReadiness,
    soprano_questions: SopranoQuestionSet,
    cold_call_plan: ColdCallPlan,
) -> None:
    saved_at = datetime.utcnow()
    summary = (
        f"Оценка материалов: {material_score.total_score}/100 ({material_score.grade}). "
        f"Первый оффер: {cold_call_plan.first_offer}. "
        f"Режим: {cold_call_plan.generation_mode}."
    )
    payload = {
        "material_score": material_score.model_dump(mode="json"),
        "closing_criteria": closing_criteria.model_dump(mode="json"),
        "soprano_questions": soprano_questions.model_dump(mode="json"),
        "cold_call_plan": cold_call_plan.model_dump(mode="json"),
        "saved_at": saved_at.isoformat(),
    }
    try:
        await create_company_insight_snapshot(
            session,
            CompanyInsightSnapshotCreate(
                company_id=company_id,
                insight_type=_SALES_INSIGHT_TYPE,
                title=_SALES_INSIGHT_TITLE,
                status="success",
                payload=payload,
                summary=summary,
                source=_SALES_INSIGHT_SOURCE,
                version="v1",
            ),
        )
        await _save_sales_intelligence_note(session, company_id, summary)
    except Exception:
        await session.rollback()
        return None


async def _save_sales_intelligence_note(
    session: AsyncSession,
    company_id: int,
    summary: str,
) -> None:
    note_text = f"План звонка сохранён. {summary}"
    latest_note = await session.scalar(
        select(LeadInteraction)
        .where(
            LeadInteraction.company_id == company_id,
            LeadInteraction.type == "note",
            LeadInteraction.created_by == _SALES_INSIGHT_SOURCE,
        )
        .order_by(LeadInteraction.created_at.desc(), LeadInteraction.id.desc())
        .limit(1)
    )
    if latest_note and (latest_note.summary or "").strip() == note_text:
        return

    session.add(
        LeadInteraction(
            company_id=company_id,
            type="note",
            summary=note_text,
            created_by=_SALES_INSIGHT_SOURCE,
        )
    )
    try:
        await session.commit()
    except Exception:
        await session.rollback()


def _calculate_material_score_from_context(company_context: dict[str, Any]) -> SalesMaterialScore:
    return calculate_material_quality_score(dict(company_context["scoring_context"]))


def _build_closing_criteria_from_context(
    company_context: dict[str, Any],
    material_score: SalesMaterialScore,
) -> ClosingCriteriaReadiness:
    company = company_context["company"]
    text_haystack = _build_text_haystack(company_context)
    website = company_context["scoring_context"]["website"]
    trust_signals = company_context["scoring_context"]["trust"]
    decision_makers = company_context["decision_makers"]
    recent_interactions = company_context["recent_interactions"]
    open_tasks = company_context["open_tasks"]

    financial_evidence: list[str] = []
    financial_questions: list[str] = []
    financial_score = 10
    if company_context.get("niche_detected") in {"dentistry", "medical"}:
        financial_score += 20
        financial_evidence.append(
            "Компания работает в сервисной нише, где даже умеренный рост конверсии может заметно влиять на выручку."
        )
    if material_score.total_score >= 55:
        financial_score += 20
        financial_evidence.append(
            "Публичная digital-упаковка уже достаточно развита, чтобы разговор о росте выглядел предметным."
        )
    if company.get("priority") == "high":
        financial_score += 15
        financial_evidence.append(
            "Лид уже отмечен как приоритетный внутри CRM, значит разговор о коммерческом эффекте уместен."
        )
    if "budget" in text_haystack or "marketing weekly" in text_haystack:
        financial_score += 20
        financial_evidence.append(
            "По заметкам видно, что внутри уже обсуждаются маркетинг, загрузка или коммерческий результат."
        )
    financial_questions.extend(
        [
            "Если конверсия в новых пациентов немного вырастет, что это даст бизнесу за месяц?",
            "Какие услуги для вас наиболее коммерчески важны, когда загрузка проседает?",
        ]
    )
    financial_opportunity = _criterion_from_score(financial_score, financial_evidence, financial_questions)

    need_evidence: list[str] = []
    need_questions: list[str] = []
    need_score = 5
    if any(marker in text_haystack for marker in ("loses demand", "losing demand", "uneven", "inquiry", "lead")):
        need_score += 35
        need_evidence.append(
            "В заметках уже есть сигналы, что спрос может теряться или проседать после первого обращения."
        )
    if material_score.conversion_score < 60:
        need_score += 20
        need_evidence.append(
            "Путь к записи на публичной стороне выглядит недособранным, значит потребность может быть реальной, а не формальной."
        )
    if open_tasks:
        need_score += 15
        need_evidence.append(
            "У команды уже стоит открытая задача на follow-up, значит часть потребности, вероятно, уже признана."
        )
    if recent_interactions:
        need_score += 10
        need_evidence.append(
            "Недавние касания показывают, что аккаунт ещё живой и гипотезу можно аккуратно проверять в диалоге."
        )
    need_questions.extend(
        [
            "Где сейчас сильнее всего замедляется путь до нового пациента: трафик, первый контакт или запись?",
            "Что уже подтолкнуло вас смотреть в эту сторону именно сейчас, если такой повод есть?",
        ]
    )
    conscious_need = _criterion_from_score(need_score, need_evidence, need_questions)

    trust_evidence: list[str] = []
    trust_questions: list[str] = []
    trust_score = 5
    if material_score.trust_score >= 70:
        trust_score += 35
        trust_evidence.append(
            "На публичной стороне уже видны несколько сигналов доверия, поэтому заход через консультацию выглядит естественнее."
        )
    if recent_interactions:
        trust_score += 15
        trust_evidence.append(
            "С компанией уже был хотя бы один контакт, а значит первый барьер сопротивления ниже."
        )
    if trust_signals.get("has_decision_maker"):
        trust_score += 10
        trust_evidence.append(
            "В CRM уже есть ЛПР, поэтому разговор о доверии можно вести не вслепую."
        )
    if company.get("rating") and company.get("rating") >= 4:
        trust_score += 10
        trust_evidence.append(
            "Хороший публичный рейтинг позволяет говорить не о спасении, а об усилении уже достойной репутации."
        )
    trust_questions.extend(
        [
            "Когда вы оцениваете внешнюю помощь, какие доказательства или процесс делают её для вас достаточно надёжной?",
            "Пробовали ли вы уже усиливать это направление с кем-то ещё, и чего тогда не хватило?",
        ]
    )
    trust = _criterion_from_score(trust_score, trust_evidence, trust_questions)

    dm_evidence: list[str] = []
    dm_questions: list[str] = []
    dm_score = 0
    if decision_makers:
        dm_score += 45
        dm_evidence.append(
            "В карточке уже указан конкретный ЛПР."
        )
        primary_dm = next((item for item in decision_makers if item.get("is_primary")), decision_makers[0])
        if primary_dm.get("role"):
            dm_score += 20
            dm_evidence.append(
                f"Основной контакт отмечен как {primary_dm['role']}, а значит влияние на решение может быть прямым."
            )
        if primary_dm.get("phone") or primary_dm.get("email") or primary_dm.get("telegram"):
            dm_score += 10
            dm_evidence.append(
                "Есть хотя бы один прямой канал до вероятного ЛПР."
            )
    if "owner" in text_haystack or "director" in text_haystack:
        dm_score += 10
        dm_evidence.append(
            "В заметках видно, что в разговор может быть уже вовлечён собственник или руководитель."
        )
    dm_questions.extend(
        [
            "Кто обычно принимает решение, стоит ли вообще что-то менять в digital-воронке?",
            "Если гипотеза окажется релевантной, кто ещё должен посмотреть результаты диагностики вместе с вами?",
        ]
    )
    decision_maker = _criterion_from_score(dm_score, dm_evidence, dm_questions)

    timing_evidence: list[str] = []
    timing_questions: list[str] = []
    timing_score = 5
    if company.get("status") in {"interested", "consultation_planned", "proposal_sent"}:
        timing_score += 30
        timing_evidence.append(
            "Текущий статус в CRM показывает, что разговор уже достаточно тёплый для следующего шага."
        )
    if recent_interactions:
        timing_score += 15
        timing_evidence.append(
            "Недавняя активность подтверждает, что лид не завис без движения."
        )
    if open_tasks:
        timing_score += 15
        timing_evidence.append(
            "Есть открытая follow-up задача, значит у команды уже есть повод продолжать разговор сейчас."
        )
    if website.get("has_online_booking") or website.get("has_cta"):
        timing_score += 10
        timing_evidence.append(
            "На сайте есть запись или CTA, значит компания уже думает о заявках и тема конверсии своевременна."
        )
    timing_questions.extend(
        [
            "Почему в эту тему имеет смысл смотреть сейчас, а не переносить на потом?",
            "Есть ли сейчас сезонность, кампания или вопрос загрузки, который делает это более срочным?",
        ]
    )
    here_and_now = _criterion_from_score(timing_score, timing_evidence, timing_questions)

    criteria_map = {
        "financial_opportunity": financial_opportunity,
        "conscious_need": conscious_need,
        "trust": trust,
        "decision_maker": decision_maker,
        "here_and_now": here_and_now,
    }
    weakest_name, weakest_criterion = min(
        criteria_map.items(),
        key=lambda item: (
            item[1].score,
            _CRITICALITY_ORDER[item[0]],
            _STATUS_ORDER[item[1].status],
        ),
    )
    summary = _build_closing_summary(criteria_map)
    risks = _build_closing_risks(criteria_map)
    next_best_question = weakest_criterion.questions[0] if weakest_criterion.questions else _default_question_for_criterion(
        weakest_name
    )
    return ClosingCriteriaReadiness(
        financial_opportunity=financial_opportunity,
        conscious_need=conscious_need,
        trust=trust,
        decision_maker=decision_maker,
        here_and_now=here_and_now,
        summary=summary,
        risks=risks,
        next_best_question=next_best_question,
    )


def _build_soprano_questions_from_context(
    company_context: dict[str, Any],
    niche: str | None = None,
) -> SopranoQuestionSet:
    company = company_context["company"]
    niche_detected = niche or company_context.get("niche_detected")
    niche_confidence = company_context.get("niche_confidence")
    niche_label = niche_detected or "общей сервисной ниши"
    return SopranoQuestionSet(
        company_id=int(company["id"]),
        niche=niche,
        niche_detected=niche_detected,
        niche_confidence=niche_confidence,
        intro=(
            "Держите спокойный консультационный тон и двигайтесь от текущей реальности к желаемому результату. "
            f"Вопросы должны быть уместны для ниши {niche_label}, но без предположений, которые ещё не подтверждены."
        ),
        situation=_soprano_situation_questions(niche_detected),
        experience=_soprano_experience_questions(niche_detected),
        principles=_soprano_principles_questions(),
        solutions=_soprano_solution_questions(),
        analogies=_soprano_analogy_questions(niche_detected),
        undesired=_soprano_undesired_questions(),
        limitations=_soprano_limitation_questions(),
        recommended_order=[
            "situation",
            "experience",
            "principles",
            "solutions",
            "analogies",
            "undesired",
            "limitations",
        ],
    )


def _build_scoring_context(
    company: Company,
    *,
    decision_makers: list[DecisionMaker],
    contacts: list[ContactPoint],
    latest_enrichment: BaseModel | None,
    latest_intelligence: BaseModel | None,
    latest_research: BaseModel | None,
    latest_maps_research: BaseModel | None,
) -> dict[str, Any]:
    all_phones = _dedupe_preserve_order(
        [company.phone, *_pluck(contacts, "value", contact_type="phone"), *_model_list(latest_intelligence, "parsed_contacts", "phones"), *_model_list(latest_enrichment, "detected_contacts", "phones")]
    )
    all_emails = _dedupe_preserve_order(
        [
            *_pluck(contacts, "value", contact_type="email"),
            *_model_list(latest_intelligence, "parsed_contacts", "emails"),
            *_model_list(latest_enrichment, "detected_contacts", "emails"),
        ]
    )
    messenger_links = _dedupe_preserve_order(
        [
            company.telegram_url,
            *_pluck(contacts, "value", contact_type="telegram"),
            *_pluck(contacts, "value", contact_type="whatsapp"),
            *_model_list(latest_intelligence, "parsed_contacts", "telegram_links"),
            *_model_list(latest_intelligence, "parsed_contacts", "whatsapp_links"),
            *_model_list(latest_enrichment, "detected_contacts", "telegram_links"),
            *_model_list(latest_enrichment, "detected_contacts", "whatsapp_links"),
        ]
    )
    social_links = _dedupe_preserve_order(
        [
            company.vk_url,
            company.instagram_url,
            company.telegram_url,
            *_model_list(latest_intelligence, "parsed_socials", "vk_links"),
            *_model_list(latest_intelligence, "parsed_socials", "instagram_links"),
            *_model_list(latest_intelligence, "parsed_socials", "telegram_links"),
            *_model_list(latest_intelligence, "parsed_socials", "whatsapp_links"),
            *_flatten_mapping_values(_model_dump_field(latest_enrichment, "detected_socials")),
        ]
    )
    social_platforms = _dedupe_preserve_order(
        [
            *([ "vk" ] if any("vk.com" in item for item in social_links) else []),
            *([ "instagram" ] if any("instagram" in item for item in social_links) else []),
            *([ "telegram" ] if any("t.me" in item for item in social_links) else []),
            *([ "whatsapp" ] if any("wa.me" in item for item in social_links) else []),
            *_mapping_keys_with_values(_model_dump_field(latest_enrichment, "detected_socials")),
        ]
    )
    map_links = _dedupe_preserve_order(
        [
            company.maps_url,
            *_model_list(latest_intelligence, "parsed_socials", "yandex_maps_links"),
            *_model_list(latest_intelligence, "parsed_socials", "two_gis_links"),
            *_flatten_mapping_values(_model_dump_field(latest_enrichment, "detected_maps")),
            _model_dump_field(latest_maps_research, "yandex_maps_url"),
            _model_dump_field(latest_maps_research, "selected_url"),
        ]
    )
    map_platforms = _dedupe_preserve_order(
        [
            *([ "yandex_maps" ] if any("yandex" in item for item in map_links) else []),
            *([ "2gis" ] if any("2gis" in item for item in map_links) else []),
            *_mapping_keys_with_values(_model_dump_field(latest_enrichment, "detected_maps")),
        ]
    )
    intelligence_signals = _model_dump_field(latest_intelligence, "parsed_signals")
    enrichment_signals = _model_dump_field(latest_enrichment, "signals")
    maps_research = _model_dump(latest_maps_research) if latest_maps_research else None
    title_text = " ".join(
        item
        for item in [
            _model_dump_field(latest_enrichment, "page_title"),
            _model_dump_field(latest_enrichment, "meta_description"),
            _model_dump_field(latest_enrichment, "raw_text_excerpt"),
        ]
        if isinstance(item, str) and item.strip()
    ).lower()

    website_confidence = _normalize_confidence(
        _model_dump_field(latest_intelligence, "website_confidence")
    )
    website = {
        "url": _first_non_empty(
            _model_dump_field(latest_intelligence, "website_url"),
            _model_dump_field(latest_enrichment, "website_url"),
            company.website,
        ),
        "reachable": _model_dump_field(latest_enrichment, "status") in {"success", "partial"}
        or _model_dump_field(latest_intelligence, "status") in {"success", "partial"},
        "confidence": website_confidence,
        "has_phone": bool(all_phones),
        "has_email": bool(all_emails),
        "has_form": _signal_value(intelligence_signals, "has_callback_form")
        or _signal_value(enrichment_signals, "has_callback_form"),
        "has_messenger": bool(messenger_links)
        or _signal_value(intelligence_signals, "has_messenger_links")
        or _signal_value(enrichment_signals, "has_messenger_links"),
        "has_cta": _signal_value(intelligence_signals, "has_online_booking")
        or _signal_value(enrichment_signals, "has_online_booking")
        or _signal_value(intelligence_signals, "has_callback_form")
        or _signal_value(enrichment_signals, "has_callback_form"),
        "has_online_booking": _signal_value(intelligence_signals, "has_online_booking")
        or _signal_value(enrichment_signals, "has_online_booking"),
        "has_services": _signal_value(intelligence_signals, "has_prices")
        or _signal_value(enrichment_signals, "has_prices")
        or "implant" in title_text
        or "orthodont" in title_text,
        "has_team": _signal_value(intelligence_signals, "has_doctors_page")
        or _signal_value(enrichment_signals, "has_doctors_page"),
        "has_reviews": _signal_value(intelligence_signals, "has_reviews_section")
        or _signal_value(enrichment_signals, "has_reviews_section")
        or bool(company.reviews_count),
        "has_privacy_policy": _signal_value(intelligence_signals, "has_privacy_policy")
        or _signal_value(enrichment_signals, "has_privacy_policy"),
        "has_prices": _signal_value(intelligence_signals, "has_prices")
        or _signal_value(enrichment_signals, "has_prices"),
        "has_consultation_offer": "consult" in title_text or "diagnostic" in title_text,
    }
    return {
        "company_id": company.id,
        "website": website,
        "socials": {
            "links": social_links,
            "platforms": social_platforms,
            "active": len(social_links) >= 2,
            "has_trust_content": website["has_reviews"] or website["has_team"],
        },
        "maps": {
            "has_listing": bool(map_links),
            "platforms": map_platforms,
            "has_reviews": bool(company.reviews_count),
            "rating": company.rating,
            "contact_consistency": bool(all_phones) and bool(company.address or _model_list(latest_intelligence, "parsed_contacts", "addresses")),
            "has_photos": bool(company.reviews_count and company.reviews_count >= 20),
            "has_description": bool(_model_dump_field(latest_enrichment, "meta_description")),
            "has_services": website["has_services"],
            "research_status": _model_dump_field(latest_maps_research, "status"),
            "research_score": _model_dump_field(latest_maps_research, "total_score"),
        },
        "maps_research": maps_research,
        "trust": {
            "has_decision_maker": bool(decision_makers),
            "has_legal_identifiers": bool(company.inn or company.ogrn or company.legal_name),
            "has_reviews": website["has_reviews"],
            "has_team": website["has_team"],
            "has_licenses": "license" in title_text or "licence" in title_text,
        },
        "contacts": {
            "phones": all_phones,
            "emails": all_emails,
            "messengers": messenger_links,
            "address": _first_non_empty(
                company.address,
                *_model_list(latest_intelligence, "parsed_contacts", "addresses"),
            ),
        },
    }


def _serialize_company(company: Company) -> dict[str, Any]:
    return {
        "id": company.id,
        "name": company.name,
        "legal_name": company.legal_name,
        "inn": company.inn,
        "ogrn": company.ogrn,
        "city": company.city,
        "region": company.region,
        "address": company.address,
        "phone": company.phone,
        "website": company.website,
        "maps_url": company.maps_url,
        "vk_url": company.vk_url,
        "instagram_url": company.instagram_url,
        "telegram_url": company.telegram_url,
        "rating": company.rating,
        "reviews_count": company.reviews_count,
        "source": company.source,
        "status": company.status,
        "status_label": humanize_company_status(company.status),
        "priority": company.priority,
        "notes": company.notes,
    }


def _serialize_contact(contact: ContactPoint) -> dict[str, Any]:
    return {
        "id": contact.id,
        "type": contact.type,
        "value": contact.value,
        "label": contact.label,
        "is_primary": contact.is_primary,
        "notes": contact.notes,
        "created_at": contact.created_at.isoformat() if contact.created_at else None,
    }


def _serialize_decision_maker(item: DecisionMaker) -> dict[str, Any]:
    return {
        "id": item.id,
        "full_name": item.full_name,
        "role": item.role,
        "phone": item.phone,
        "email": item.email,
        "telegram": item.telegram,
        "source": item.source,
        "is_primary": item.is_primary,
        "notes": item.notes,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_interaction(item: LeadInteraction) -> dict[str, Any]:
    return {
        "id": item.id,
        "type": item.type,
        "result": item.result,
        "summary": item.summary,
        "next_action": item.next_action,
        "next_step": item.next_step,
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_task(item: FollowUpTask) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "status": item.status,
        "priority": item.priority,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _detect_niche(
    company: Company,
    *,
    latest_enrichment: BaseModel | None,
    latest_intelligence: BaseModel | None,
    latest_research_job_result: dict[str, Any] | list[Any] | None,
) -> tuple[str | None, float | None]:
    haystack_parts = [
        company.name or "",
        company.legal_name or "",
        company.notes or "",
        _model_dump_field(latest_enrichment, "page_title") or "",
        _model_dump_field(latest_enrichment, "meta_description") or "",
        _model_dump_field(latest_enrichment, "raw_text_excerpt") or "",
        " ".join(_model_dump_field(latest_enrichment, "hypotheses") or []),
        " ".join(_model_dump_field(latest_intelligence, "hypotheses") or []),
        json.dumps(latest_research_job_result, ensure_ascii=False) if latest_research_job_result else "",
    ]
    haystack = " ".join(str(item).lower() for item in haystack_parts if item)
    if any(keyword in haystack for keyword in _DENTAL_KEYWORDS):
        return "dentistry", 0.88
    if any(keyword in haystack for keyword in ("medical", "clinic", "patient", "doctor")):
        return "medical", 0.66
    if any(keyword in haystack for keyword in ("beauty", "salon", "cosmet")):
        return "beauty", 0.62
    if any(keyword in haystack for keyword in ("school", "course", "academy", "education")):
        return "education", 0.58
    return None, None


def _get_latest_research_job_result(company: Company) -> dict[str, Any] | list[Any] | None:
    if not company.research_jobs:
        return None
    latest_job = max(
        company.research_jobs,
        key=lambda item: (item.created_at or datetime.min, item.id or 0),
    )
    return parse_json_text(latest_job.result_json, None)


def _model_dump(value: BaseModel | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return value.model_dump(mode="json")


def _model_dump_field(value: BaseModel | None, field_name: str) -> Any:
    if value is None:
        return None
    return getattr(value, field_name, None)


def _model_list(value: BaseModel | None, field_name: str, nested_field: str) -> list[str]:
    nested = _model_dump_field(value, field_name)
    if nested is None:
        return []
    raw = getattr(nested, nested_field, None)
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _pluck(items: list[ContactPoint], field_name: str, *, contact_type: str) -> list[str]:
    values: list[str] = []
    for item in items:
        if item.type != contact_type:
            continue
        raw = getattr(item, field_name, None)
        if not raw:
            continue
        text = str(raw).strip()
        if text:
            values.append(text)
    return values


def _flatten_mapping_values(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    flattened: list[str] = []
    for items in value.values():
        if isinstance(items, list):
            flattened.extend(str(item).strip() for item in items if str(item).strip())
    return flattened


def _mapping_keys_with_values(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    return [str(key) for key, items in value.items() if isinstance(items, list) and items]


def _normalize_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric > 1:
        return round(numeric / 100, 2)
    return round(numeric, 2)


def _signal_value(payload: Any, key: str) -> bool:
    if isinstance(payload, dict):
        return bool(payload.get(key))
    return False


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _dedupe_preserve_order(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _build_text_haystack(company_context: dict[str, Any]) -> str:
    chunks = [
        company_context["company"].get("notes") or "",
        " ".join(item.get("summary") or "" for item in company_context.get("recent_interactions", [])),
        " ".join(item.get("next_action") or "" for item in company_context.get("recent_interactions", [])),
        " ".join(item.get("description") or "" for item in company_context.get("open_tasks", [])),
        " ".join(_model_dump_field_from_context(company_context, "latest_enrichment", "hypotheses")),
        " ".join(_model_dump_field_from_context(company_context, "latest_intelligence", "hypotheses")),
        json.dumps(company_context.get("latest_research_job_result"), ensure_ascii=False)
        if company_context.get("latest_research_job_result")
        else "",
    ]
    return " ".join(chunk.lower() for chunk in chunks if isinstance(chunk, str))


def _model_dump_field_from_context(company_context: dict[str, Any], key: str, field_name: str) -> list[str]:
    payload = company_context.get(key)
    if not isinstance(payload, dict):
        return []
    value = payload.get(field_name)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _criterion_from_score(
    score: int,
    evidence: list[str],
    questions: list[str],
) -> ClosingCriterionReadiness:
    score = max(0, min(100, int(score)))
    if score < 15 and not evidence:
        status = "unknown"
    elif score < 45:
        status = "weak"
    elif score < 75:
        status = "possible"
    else:
        status = "strong"
    return ClosingCriterionReadiness(
        score=score,
        status=status,
        evidence=_dedupe_preserve_order(evidence)[:3],
        questions=_dedupe_preserve_order(questions)[:3],
    )


def _build_closing_summary(criteria_map: dict[str, ClosingCriterionReadiness]) -> str:
    label_map = {
        "financial_opportunity": "финансовой возможности",
        "conscious_need": "осознанной потребности",
        "trust": "доверия",
        "decision_maker": "ЛПР",
        "here_and_now": "критерия «здесь и сейчас»",
    }
    stronger = [label_map[name] for name, item in criteria_map.items() if item.status == "strong"]
    weaker = [label_map[name] for name, item in criteria_map.items() if item.status in {"unknown", "weak"}]
    if stronger and weaker:
        return (
            f"Сигналы сильнее всего выглядят в зоне {', '.join(stronger[:2])}, "
            f"но в следующем разговоре важно отдельно подтвердить {', '.join(weaker[:2])}, прежде чем ускорять сделку."
        )
    if stronger:
        return (
            f"Несколько критериев уже поддерживают разговор, особенно в части {', '.join(stronger[:2])}, "
            "но менеджеру всё равно важно подтвердить это вживую."
        )
    return (
        "Данных пока недостаточно, поэтому звонок лучше вести как discovery-разговор и сначала подтвердить базовые вводные."
    )


def _build_closing_risks(criteria_map: dict[str, ClosingCriterionReadiness]) -> list[str]:
    label_map = {
        "financial_opportunity": "финансовой возможности",
        "conscious_need": "осознанной потребности",
        "trust": "доверия",
        "decision_maker": "ЛПР",
        "here_and_now": "срочности",
    }
    risks: list[str] = []
    for name, criterion in criteria_map.items():
        if criterion.status in {"unknown", "weak"}:
            risks.append(f"В разговоре пока не хватает уверенного подтверждения по части {label_map[name]}, поэтому этот блок нужно исследовать напрямую.")
    return risks[:5]


def _default_question_for_criterion(name: str) -> str:
    mapping = {
        "financial_opportunity": "Если здесь получится улучшение, как это коммерчески отразится на вас?",
        "conscious_need": "Что делает эту тему достойной обсуждения именно сейчас?",
        "trust": "Что вам нужно увидеть от внешнего подрядчика, чтобы продолжить разговор?",
        "decision_maker": "Кто ещё должен согласовать следующий шаг, если тема подтвердится?",
        "here_and_now": "Почему это имеет смысл разбирать сейчас, а не позже?",
    }
    return mapping[name]


def _soprano_situation_questions(niche: str | None) -> list[str]:
    if niche == "dentistry":
        return [
            "Как сейчас новый пациент проходит путь от первого обращения до подтверждённой записи?",
            "Через какие каналы чаще всего приходят первичные обращения по стоматологии?",
            "Как сейчас в этот путь встроены онлайн-запись и передача обращения администратору?",
        ]
    return [
        "Как сейчас новый лид проходит путь от первого обращения до следующего целевого шага?",
        "Какие каналы сейчас приносят вам самые релевантные входящие обращения?",
        "Как выглядит первый контакт с вашей стороны глазами клиента?",
    ]


def _soprano_experience_questions(niche: str | None) -> list[str]:
    if niche == "dentistry":
        return [
            "Когда спрос высокий, на каком этапе путь пациента идёт гладко, а где начинает проседать?",
            "Что вы уже пробовали, чтобы улучшить запись или сократить потери после обращения?",
            "На каких услугах сильнее всего проявляются узкие места в конверсии?",
        ]
    return [
        "Когда спрос в порядке, какая часть пути работает у вас лучше всего?",
        "Что вы уже пробовали, чтобы усилить конверсию или follow-up?",
        "Какая часть воронки сильнее всего плавает от месяца к месяцу?",
    ]


def _soprano_principles_questions() -> list[str]:
    return [
        "Что для вас важнее всего в росте: скорость, предсказуемость, контроль или что-то ещё?",
        "Что в клиентском опыте должно остаться неизменным, даже если поток обращений вырастет?",
        "По каким признакам вы обычно понимаете, что маркетинговое или конверсионное изменение стоит продолжать?",
    ]


def _soprano_solution_questions() -> list[str]:
    return [
        "Если бы эту задачу удалось решить достаточно хорошо, что вы хотели бы увидеть в первую очередь?",
        "Какой первый шаг был бы для вас полезным, но не выглядел бы слишком большим обязательством?",
        "Кто из команды должен быть вовлечён, если вы решите протестировать улучшения?",
    ]


def _soprano_analogy_questions(niche: str | None) -> list[str]:
    if niche == "dentistry":
        return [
            "Есть ли клиника, чья подача и путь до записи вам действительно нравятся?",
            "Если бы путь пациента работал так же надёжно, как ваш лучший клинический процесс, что было бы иначе?",
        ]
    return [
        "Есть ли компания или конкурент, чья подача и первый контакт вам нравятся?",
        "Если бы этот участок воронки работал так же надёжно, как ваш самый сильный внутренний процесс, что было бы иначе?",
    ]


def _soprano_undesired_questions() -> list[str]:
    return [
        "Каких действий в маркетинге вы точно не хотите, потому что они дают шум без качества?",
        "Что сделало бы разговор с внешним агентством для вас преждевременным или бесполезным?",
        "По каким признакам вы бы поняли, что изменение идёт не туда?",
    ]


def _soprano_limitation_questions() -> list[str]:
    return [
        "Какие ограничения нам важно учитывать: сроки, согласования, команда, системы?",
        "Где у команды обычно заканчивается ресурс, когда спрос растёт?",
        "Что помешает действовать, даже если мы вместе увидим понятную возможность?",
    ]


def _build_digital_observations(
    company_context: dict[str, Any],
    material_score: SalesMaterialScore,
) -> list[str]:
    company = company_context["company"]
    website = company_context["scoring_context"]["website"]
    maps = company_context["scoring_context"]["maps"]
    observations: list[str] = []
    if website.get("url"):
        observations.append("У компании есть публичный сайт, на который можно опереться в разговоре.")
    if website.get("has_online_booking"):
        observations.append("На сайте, похоже, есть онлайн-запись, а значит команда уже ценит digital-путь до обращения.")
    if website.get("has_reviews"):
        observations.append("На публичной стороне видны отзывы, и это уже поддерживает базовое доверие.")
    if maps.get("has_listing"):
        observations.append("У компании есть карточки на картах, значит локальный спрос уже может быть заметным.")
    if company.get("reviews_count"):
        observations.append(
            f"На публичной стороне видно около {company['reviews_count']} отзывов, что может говорить о заметном объёме первичного спроса."
        )
    if material_score.conversion_score < 60:
        observations.append("Даже при наличии цифровых активов следующий шаг для клиента может быть недостаточно явным.")
    return observations[:5]


def _build_likely_pains(
    material_score: SalesMaterialScore,
    closing_criteria: ClosingCriteriaReadiness,
) -> list[str]:
    pains: list[str] = []
    if material_score.conversion_score < 60:
        pains.append("Компания может терять часть обращений между первым визитом и следующим целевым действием.")
    if material_score.socials_score < 50:
        pains.append("Соцдоказательства и прогрев пока могут недостаточно стабильно усиливать доверие.")
    if material_score.trust_score < 70:
        pains.append("Часть сигналов доверия пока может не дотягивать до уверенного решения клиента.")
    if closing_criteria.decision_maker.status in {"unknown", "weak"}:
        pains.append("Путь к решению пока не до конца ясен, а это тормозит даже хороший разговор.")
    if closing_criteria.here_and_now.status in {"unknown", "weak"}:
        pains.append("Даже если возможность реальна, срочность действий пока может быть не сформулирована.")
    return pains[:5]


def _build_personalization_points(
    company_context: dict[str, Any],
    material_score: SalesMaterialScore,
) -> list[str]:
    company = company_context["company"]
    decision_makers = company_context["decision_makers"]
    points: list[str] = []
    if decision_makers:
        primary_dm = next((item for item in decision_makers if item.get("is_primary")), decision_makers[0])
        role_text = primary_dm.get("role") or "ответственный за рост"
        points.append(f"В CRM уже есть ЛПР: {primary_dm['full_name']} ({role_text}).")
    if company.get("rating"):
        points.append(
            f"Публичный рейтинг около {company['rating']}, поэтому разговор можно строить вокруг усиления уже существующего доверия."
        )
    if company.get("website"):
        points.append("Сайт даёт достаточно контекста, чтобы звонок звучал как подготовленная диагностика, а не слепой pitch.")
    if material_score.total_score >= 55:
        points.append("Digital-след уже достаточно развит, поэтому точечные улучшения воронки могут быть важнее полного переделывания.")
    if company_context.get("recent_interactions"):
        points.append("Недавняя активность в CRM позволяет опираться на живой контекст, а не начинать разговор с нуля.")
    return points[:5]


def _reason_for_call(material_score: SalesMaterialScore, observations: list[str]) -> str:
    if material_score.conversion_score < 60:
        return (
            "По публичной стороне видно, что digital-активность уже есть, но между первым интересом и следующим шагом может оставаться трение."
        )
    if observations:
        return (
            "По публичной стороне компания выглядит достаточно активной, чтобы предметно обсудить, где рост ещё может упираться в ограничения."
        )
    return (
        "Цель звонка — аккуратно проверить гипотезу, что на пути от первого интереса до реальной возможности есть устранимые потери."
    )


def _build_objection_preparation() -> list[ObjectionHandlingItem]:
    return [
        ObjectionHandlingItem(
            objection="Мы уже работаем с кем-то.",
            response_principle="Не спорить с текущим подрядчиком, а позиционировать разговор как второй взгляд на точки потери воронки.",
            suggested_response="Понимаю. Я не исхожу из того, что у вас что-то сломано. Иногда короткая внешняя диагностика просто помогает подтвердить, что текущая система уже достаточна, или найти одно узкое место, которое действительно стоит поправить.",
        ),
        ObjectionHandlingItem(
            objection="Сначала пришлите что-нибудь сообщением.",
            response_principle="Согласиться, но оставить маленький уточняющий вопрос, чтобы follow-up был релевантным.",
            suggested_response="Конечно. Прежде чем отправлять общий материал, можно я уточню один момент по тому, как у вас сейчас обрабатываются обращения, чтобы сообщение было действительно полезным?",
        ),
        ObjectionHandlingItem(
            objection="Сейчас нет времени.",
            response_principle="Признать вопрос тайминга и предложить более лёгкий следующий шаг.",
            suggested_response="Понимаю. Если на полноценный разговор сейчас нет окна, был бы полезен короткий диагностический summary, чтобы позже спокойно решить, стоит ли возвращаться к теме?",
        ),
    ]


def _plan_confidence(
    material_score: SalesMaterialScore,
    closing_criteria: ClosingCriteriaReadiness,
) -> str:
    strong_count = sum(
        1
        for item in [
            closing_criteria.financial_opportunity,
            closing_criteria.conscious_need,
            closing_criteria.trust,
            closing_criteria.decision_maker,
            closing_criteria.here_and_now,
        ]
        if item.status == "strong"
    )
    if material_score.total_score >= 70 and strong_count >= 3:
        return "high"
    if material_score.total_score >= 45 or strong_count >= 2:
        return "medium"
    return "low"


def _build_short_script(
    *,
    company_name: str,
    reason_for_call: str,
    next_question: str,
    first_offer: str,
) -> str:
    return (
        f"Добрый день. Звоню по компании {company_name}. "
        f"По публичной стороне вижу такую гипотезу: {reason_for_call.lower()} "
        f"Можно задам один короткий вопрос: {next_question} "
        f"Если это откликается, следующим шагом предложил бы {first_offer.lower()}"
    )


def _build_detailed_script(
    *,
    company_name: str,
    observations: list[str],
    closing_criteria: ClosingCriteriaReadiness,
    first_offer: str,
    soprano_questions: SopranoQuestionSet,
) -> str:
    observation_line = observations[0] if observations else "Есть несколько публичных сигналов, которые стоит спокойно проверить вместе."
    soprano_question = (
        soprano_questions.situation[0]
        if soprano_questions.situation
        else closing_criteria.next_best_question
    )
    return "\n".join(
        [
            f"1. Мягкий вход: упомянуть {company_name} и сказать, что звоните с аккуратной гипотезой по публичной стороне.",
            f"2. Наблюдение: {observation_line}",
            f"3. Discovery-вопрос: {soprano_question}",
            f"4. Приоритетный вопрос по сделке: {closing_criteria.next_best_question}",
            f"5. Если проблема подтверждается, предложить следующий шаг: {first_offer}",
            "6. Если собеседник сомневается, предложить короткий диагностический summary вместо давления на встречу.",
        ]
    )


def _parse_ai_cold_call_plan(raw_response: str | None, fallback_plan: ColdCallPlan) -> ColdCallPlan | None:
    payload = _extract_json_payload(raw_response)
    if not isinstance(payload, dict):
        return None

    payload.setdefault("company_id", fallback_plan.company_id)
    payload.setdefault("company_name", fallback_plan.company_name)
    payload.setdefault("niche", fallback_plan.niche)
    payload.setdefault("niche_detected", fallback_plan.niche_detected)
    payload.setdefault("niche_confidence", fallback_plan.niche_confidence)
    payload["generation_mode"] = "ai"
    payload.setdefault("created_at", datetime.utcnow().isoformat())
    payload.setdefault("closing_criteria", fallback_plan.closing_criteria.model_dump(mode="json"))
    payload.setdefault("soprano_questions", fallback_plan.soprano_questions.model_dump(mode="json"))
    payload.setdefault("objection_preparation", [item.model_dump(mode="json") for item in fallback_plan.objection_preparation])
    payload.setdefault("manager_checklist", fallback_plan.manager_checklist)
    payload.setdefault("do_not_say", fallback_plan.do_not_say)
    payload.setdefault("risks", fallback_plan.risks)

    try:
        return ColdCallPlan.model_validate(payload)
    except ValidationError:
        return None


def _extract_json_payload(raw_response: str | None) -> dict[str, Any] | None:
    if not raw_response or not raw_response.strip():
        return None
    raw_text = raw_response.strip()
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()
    candidates = [raw_text]
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw_text[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


__all__ = [
    "build_closing_criteria_readiness",
    "build_fallback_cold_call_plan",
    "calculate_company_material_score",
    "generate_cold_call_plan",
    "generate_soprano_questions",
    "get_company_sales_context",
    "get_latest_sales_intelligence",
]
