from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.ai.providers import get_ai_provider
from app.modules.crm.constants import TaskStatus
from app.modules.crm.models import Company, ContactPoint, DecisionMaker, FollowUpTask, LeadInteraction
from app.modules.crm.service import get_company, humanize_company_status
from app.modules.enrichment.schemas import parse_json_text
from app.modules.enrichment.service import build_enrichment_context_for_company, get_latest_enrichment
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


async def get_company_sales_context(session: AsyncSession, company_id: int) -> dict[str, Any]:
    company = await get_company(session, company_id)
    if not company:
        raise ValueError("Company not found")

    latest_enrichment = await get_latest_enrichment(session, company_id)
    latest_intelligence = await get_latest_intelligence(session, company_id)
    latest_research = await get_latest_research(session, company_id)
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
        "latest_research_job_result": research_job_result,
        "recent_interactions": [_serialize_interaction(item) for item in recent_interactions],
        "open_tasks": [_serialize_task(item) for item in open_tasks],
        "scoring_context": scoring_context,
        "website": scoring_context["website"],
        "socials": scoring_context["socials"],
        "maps": scoring_context["maps"],
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
) -> ColdCallPlan:
    del force_regenerate

    company_context = await get_company_sales_context(session, company_id)
    material_score = _calculate_material_score_from_context(company_context)
    closing_criteria = _build_closing_criteria_from_context(company_context, material_score)
    soprano_questions = _build_soprano_questions_from_context(company_context, niche=niche)
    fallback_plan = build_fallback_cold_call_plan(
        company_context,
        material_score,
        closing_criteria,
        soprano_questions,
    )

    if not use_ai or get_settings().ai_provider.lower() == "fallback":
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
        return fallback_plan

    ai_plan = _parse_ai_cold_call_plan(raw_response, fallback_plan)
    return ai_plan or fallback_plan


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
    first_offer = (
        "Offer a short diagnostic working session to map where enquiries may be slowing down before they become booked patients."
    )
    next_best_action = (
        f"Use the next call to confirm {closing_criteria.next_best_question.lower().rstrip('?')}."
        if closing_criteria.next_best_question
        else "Use the next call to confirm whether a deeper diagnostic conversation is worth scheduling."
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
            "Confirm whether the company may be losing demand between first interest and the booked next step,"
            " then earn permission for a short diagnostic follow-up."
        ),
        opener=(
            f"Hi, am I speaking with the person who looks after growth for {company_name}? "
            "I am calling with one cautious hypothesis from the public side and wanted to sanity-check it with you."
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
            "Open the website, maps listing, and the latest notes before calling.",
            "Confirm whether you reached a decision-maker or a gatekeeper within the first minute.",
            "Ask one closing-criteria question before offering any solution.",
            "Keep every observation framed as a public-side hypothesis, not a certainty.",
            "Leave the call with either a booked follow-up or a clearly stated reason why it is not timely.",
        ],
        risks=_dedupe_preserve_order(
            [
                *material_score.risks[:4],
                *closing_criteria.risks[:4],
                "Public signals can be incomplete, so the manager should validate each hypothesis live on the call.",
            ]
        ),
        do_not_say=[
            "We know exactly where you are losing patients.",
            "Your website is broken.",
            "You definitely need a new contractor.",
            "We can guarantee more revenue.",
            "I already know your budget and internal process.",
        ],
    )


async def get_latest_sales_intelligence(
    session: AsyncSession,
    company_id: int,
) -> LatestSalesIntelligenceRead:
    company_context = await get_company_sales_context(session, company_id)
    material_score = _calculate_material_score_from_context(company_context)
    closing_criteria = _build_closing_criteria_from_context(company_context, material_score)
    soprano_questions = _build_soprano_questions_from_context(company_context, niche=None)
    return LatestSalesIntelligenceRead(
        material_score=material_score,
        closing_criteria=closing_criteria,
        soprano_questions=soprano_questions,
        cold_call_plan=None,
        saved_at=None,
    )


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
            "The company appears to operate in a service category where even modest conversion gains could matter commercially."
        )
    if material_score.total_score >= 55:
        financial_score += 20
        financial_evidence.append(
            "The public footprint looks substantial enough that a structured growth conversation may be commercially relevant."
        )
    if company.get("priority") == "high":
        financial_score += 15
        financial_evidence.append(
            "The lead is already marked high priority internally, which may justify a revenue-focused conversation."
        )
    if "budget" in text_haystack or "marketing weekly" in text_haystack:
        financial_score += 20
        financial_evidence.append(
            "Notes suggest commercial performance or marketing spend may already be discussed internally."
        )
    financial_questions.extend(
        [
            "If new-patient conversion improved even slightly, what would that be worth to the business over a month?",
            "Which services matter most commercially when your schedule is not full enough?",
        ]
    )
    financial_opportunity = _criterion_from_score(financial_score, financial_evidence, financial_questions)

    need_evidence: list[str] = []
    need_questions: list[str] = []
    need_score = 5
    if any(marker in text_haystack for marker in ("loses demand", "losing demand", "uneven", "inquiry", "lead")):
        need_score += 35
        need_evidence.append(
            "Existing notes already hint that demand may become uneven or leak after the first enquiry."
        )
    if material_score.conversion_score < 60:
        need_score += 20
        need_evidence.append(
            "The public conversion path still looks incomplete enough that there may be a real underlying growth need."
        )
    if open_tasks:
        need_score += 15
        need_evidence.append(
            "There is already an open follow-up task around a diagnostic conversation, which suggests some need may have been recognized."
        )
    if recent_interactions:
        need_score += 10
        need_evidence.append(
            "Recent conversations suggest the account is active enough to test whether the need is explicit yet."
        )
    need_questions.extend(
        [
            "Where do you feel new-patient demand slows down most today: traffic, first contact, or booked appointment?",
            "What has already prompted you to look at this area now, if anything?",
        ]
    )
    conscious_need = _criterion_from_score(need_score, need_evidence, need_questions)

    trust_evidence: list[str] = []
    trust_questions: list[str] = []
    trust_score = 5
    if material_score.trust_score >= 70:
        trust_score += 35
        trust_evidence.append(
            "The public presence already shows several trust markers, which may make a consultative conversation easier."
        )
    if recent_interactions:
        trust_score += 15
        trust_evidence.append(
            "Someone at the company has already engaged at least once, which may lower initial resistance."
        )
    if trust_signals.get("has_decision_maker"):
        trust_score += 10
        trust_evidence.append(
            "A named decision-maker is available, which can make trust-building more direct."
        )
    if company.get("rating") and company.get("rating") >= 4:
        trust_score += 10
        trust_evidence.append(
            "A solid public rating may help anchor the conversation around protecting an already credible brand."
        )
    trust_questions.extend(
        [
            "When you evaluate outside help, what proof or process usually makes it credible enough to continue the conversation?",
            "Have you already tried to improve this area with someone else, and what felt missing?",
        ]
    )
    trust = _criterion_from_score(trust_score, trust_evidence, trust_questions)

    dm_evidence: list[str] = []
    dm_questions: list[str] = []
    dm_score = 0
    if decision_makers:
        dm_score += 45
        dm_evidence.append(
            "A named decision-maker is already attached to the company record."
        )
        primary_dm = next((item for item in decision_makers if item.get("is_primary")), decision_makers[0])
        if primary_dm.get("role"):
            dm_score += 20
            dm_evidence.append(
                f"The primary contact is marked as {primary_dm['role']}, which may indicate real decision influence."
            )
        if primary_dm.get("phone") or primary_dm.get("email") or primary_dm.get("telegram"):
            dm_score += 10
            dm_evidence.append(
                "There is at least one direct path to the likely decision-maker."
            )
    if "owner" in text_haystack or "director" in text_haystack:
        dm_score += 10
        dm_evidence.append(
            "Interaction notes suggest ownership or senior leadership may already be involved."
        )
    dm_questions.extend(
        [
            "Who usually decides whether a digital growth issue is important enough to act on?",
            "If this does look relevant, who would want to see the diagnostic findings with you?",
        ]
    )
    decision_maker = _criterion_from_score(dm_score, dm_evidence, dm_questions)

    timing_evidence: list[str] = []
    timing_questions: list[str] = []
    timing_score = 5
    if company.get("status") in {"interested", "consultation_planned", "proposal_sent"}:
        timing_score += 30
        timing_evidence.append(
            "The current CRM status suggests the conversation may already be warm enough for a timely next step."
        )
    if recent_interactions:
        timing_score += 15
        timing_evidence.append(
            "Recent activity means the account is not dormant."
        )
    if open_tasks:
        timing_score += 15
        timing_evidence.append(
            "There is an open follow-up task, so the team already has a reason to continue the conversation now."
        )
    if website.get("has_online_booking") or website.get("has_cta"):
        timing_score += 10
        timing_evidence.append(
            "The company appears to care about enquiries now, which makes a conversion discussion more timely."
        )
    timing_questions.extend(
        [
            "Why is this worth looking at now rather than in a later quarter?",
            "Is there any campaign, seasonality, or capacity issue making this more urgent right now?",
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
    niche_label = niche_detected or "generic services"
    return SopranoQuestionSet(
        company_id=int(company["id"]),
        niche=niche,
        niche_detected=niche_detected,
        niche_confidence=niche_confidence,
        intro=(
            "Use a calm consultative tone and move from current reality to desired outcomes. "
            f"Keep the questions relevant to {niche_label} without assuming facts that have not been confirmed."
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
        },
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
    stronger = [name.replace("_", " ") for name, item in criteria_map.items() if item.status == "strong"]
    weaker = [name.replace("_", " ") for name, item in criteria_map.items() if item.status in {"unknown", "weak"}]
    if stronger and weaker:
        return (
            f"Signals look relatively stronger around {', '.join(stronger[:2])}, "
            f"but the next conversation should still confirm {', '.join(weaker[:2])} before moving too quickly."
        )
    if stronger:
        return (
            f"Several signals already support the conversation, especially around {', '.join(stronger[:2])}, "
            "though the manager should still validate them live."
        )
    return (
        "The available evidence is still partial, so the manager should treat this as a discovery-first call and confirm the basics before pitching."
    )


def _build_closing_risks(criteria_map: dict[str, ClosingCriterionReadiness]) -> list[str]:
    risks: list[str] = []
    for name, criterion in criteria_map.items():
        if criterion.status in {"unknown", "weak"}:
            label = name.replace("_", " ")
            risks.append(
                f"The call still lacks strong confirmation around {label}, so that area should be explored directly."
            )
    return risks[:5]


def _default_question_for_criterion(name: str) -> str:
    mapping = {
        "financial_opportunity": "If this area improved, what would the commercial impact likely look like for you?",
        "conscious_need": "What is making this issue worth discussing now, if anything?",
        "trust": "What would you need to see from an outside partner before continuing the conversation?",
        "decision_maker": "Who would need to agree before this could move forward?",
        "here_and_now": "Why is this worth looking at now rather than later?",
    }
    return mapping[name]


def _soprano_situation_questions(niche: str | None) -> list[str]:
    if niche == "dentistry":
        return [
            "How does a new patient usually move from first enquiry to a confirmed appointment today?",
            "Which channels currently bring the most first-time dental enquiries?",
            "Where do online booking and receptionist handoff fit into that flow right now?",
        ]
    return [
        "How does a new prospect usually move from first enquiry to a booked next step today?",
        "Which channels bring the most relevant inbound opportunities right now?",
        "What does the first-contact workflow look like from the customer side?",
    ]


def _soprano_experience_questions(niche: str | None) -> list[str]:
    if niche == "dentistry":
        return [
            "When demand is strong, where does the patient journey feel smooth, and where does it start to strain?",
            "What have you already tried to improve bookings or reduce drop-off?",
            "Which services tend to expose the biggest conversion bottlenecks?",
        ]
    return [
        "When demand is healthy, what part of the journey works best today?",
        "What have you already tried to improve conversion or follow-up?",
        "Which part of the funnel feels most inconsistent from month to month?",
    ]


def _soprano_principles_questions() -> list[str]:
    return [
        "When you evaluate growth work, what principles matter most: speed, predictability, control, or something else?",
        "What has to stay true about your customer experience even if you improve volume?",
        "How do you usually decide whether a marketing or conversion change is worth continuing?",
    ]


def _soprano_solution_questions() -> list[str]:
    return [
        "If this issue were solved well enough, what would you want to see change first?",
        "What kind of first step would feel useful without becoming a large commitment too early?",
        "Which team members would need a practical role if you decided to test improvements here?",
    ]


def _soprano_analogy_questions(niche: str | None) -> list[str]:
    if niche == "dentistry":
        return [
            "Have you seen another clinic handle first-contact conversion in a way you respect?",
            "If your patient journey felt as reliable as your best clinical process, what would be different?",
        ]
    return [
        "Have you seen another business handle first-contact conversion in a way that impressed you?",
        "If this part of the funnel worked as reliably as your strongest internal process, what would be different?",
    ]


def _soprano_undesired_questions() -> list[str]:
    return [
        "What kind of growth effort would you want to avoid because it creates noise without quality?",
        "What would make an outside agency conversation feel unhelpful or premature?",
        "Which outcomes would tell you a change is heading in the wrong direction?",
    ]


def _soprano_limitation_questions() -> list[str]:
    return [
        "What constraints should we know about: time, approvals, staffing, or systems?",
        "Where does the team usually run out of capacity when demand rises?",
        "What would make it hard to act even if we agreed there was a clear opportunity?",
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
        observations.append("The company appears to maintain a public website that can anchor the conversation.")
    if website.get("has_online_booking"):
        observations.append("Online booking appears to be available, which suggests the team already values a digital conversion path.")
    if website.get("has_reviews"):
        observations.append("Reviews seem visible on the public side, which may already support baseline trust.")
    if maps.get("has_listing"):
        observations.append("A maps listing appears to exist, so local-intent demand may already be present.")
    if company.get("reviews_count"):
        observations.append(
            f"The public profile shows roughly {company['reviews_count']} reviews, which may indicate meaningful discovery volume."
        )
    if material_score.conversion_score < 60:
        observations.append("Even with visible assets, the next step may still be less explicit than it could be.")
    return observations[:5]


def _build_likely_pains(
    material_score: SalesMaterialScore,
    closing_criteria: ClosingCriteriaReadiness,
) -> list[str]:
    pains: list[str] = []
    if material_score.conversion_score < 60:
        pains.append("The business may still be losing some enquiries between first visit and booked next step.")
    if material_score.socials_score < 50:
        pains.append("Social proof and ongoing nurture may not be reinforcing trust consistently enough yet.")
    if material_score.trust_score < 70:
        pains.append("Some trust signals may still need to work harder before a prospect feels ready to commit.")
    if closing_criteria.decision_maker.status in {"unknown", "weak"}:
        pains.append("The buying path may still be unclear, which can slow good conversations down.")
    if closing_criteria.here_and_now.status in {"unknown", "weak"}:
        pains.append("The urgency to act may not be explicit yet, even if the opportunity is real.")
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
        role_text = primary_dm.get("role") or "the growth lead"
        points.append(f"A named decision-maker is present in CRM: {primary_dm['full_name']} ({role_text}).")
    if company.get("rating"):
        points.append(
            f"The public rating looks to be about {company['rating']}, so the discussion can focus on protecting existing trust while improving conversion."
        )
    if company.get("website"):
        points.append("The public website gives enough context to frame the call as an informed diagnostic rather than a blind pitch.")
    if material_score.total_score >= 55:
        points.append("The footprint looks developed enough that small funnel fixes could matter more than rebuilding everything.")
    if company_context.get("recent_interactions"):
        points.append("Recent CRM activity means the call can reference live internal context instead of starting from zero.")
    return points[:5]


def _reason_for_call(material_score: SalesMaterialScore, observations: list[str]) -> str:
    if material_score.conversion_score < 60:
        return (
            "From the public side, the company already appears to have real digital activity, but there may still be friction between first interest and the booked next step."
        )
    if observations:
        return (
            "From the public side, the company appears to have enough digital activity to justify a quick diagnostic conversation about where growth could still be constrained."
        )
    return (
        "The call is to test a cautious hypothesis that the company may have a few avoidable leaks in the path from first interest to real opportunity."
    )


def _build_objection_preparation() -> list[ObjectionHandlingItem]:
    return [
        ObjectionHandlingItem(
            objection="We already work with someone.",
            response_principle="Do not attack the incumbent; position the conversation as a second set of eyes on conversion friction.",
            suggested_response="That makes sense. I am not assuming anything is broken. Sometimes a short outside diagnostic just helps confirm whether the current setup is already doing enough or whether there is one bottleneck worth fixing.",
        ),
        ObjectionHandlingItem(
            objection="Send something by message first.",
            response_principle="Agree, but keep the ask small and specific so the follow-up has context.",
            suggested_response="Happy to. Before I send anything broad, could I confirm one thing about how enquiries are handled now, so the note is actually relevant to your team?",
        ),
        ObjectionHandlingItem(
            objection="We do not have time right now.",
            response_principle="Acknowledge the timing issue and offer a lower-friction next step.",
            suggested_response="Understood. If a full conversation is not timely, would a short diagnostic summary be more useful so you can decide later whether it is worth revisiting?",
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
        f"Hi, I am calling about {company_name}. "
        f"From the public side, {reason_for_call.lower()} "
        f"Could I ask one quick question: {next_question} "
        f"If that is relevant, I would suggest {first_offer.lower()}"
    )


def _build_detailed_script(
    *,
    company_name: str,
    observations: list[str],
    closing_criteria: ClosingCriteriaReadiness,
    first_offer: str,
    soprano_questions: SopranoQuestionSet,
) -> str:
    observation_line = observations[0] if observations else "There may be a few public-side signals worth validating together."
    soprano_question = (
        soprano_questions.situation[0]
        if soprano_questions.situation
        else closing_criteria.next_best_question
    )
    return "\n".join(
        [
            f"1. Open gently: mention {company_name} and state that you are calling with a cautious public-side hypothesis.",
            f"2. Observation: {observation_line}",
            f"3. Discovery question: {soprano_question}",
            f"4. Priority closing question: {closing_criteria.next_best_question}",
            f"5. If the issue sounds real, offer this next step: {first_offer}",
            "6. If the prospect is unsure, suggest sending a short diagnostic summary instead of forcing a meeting.",
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
