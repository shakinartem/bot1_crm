from __future__ import annotations

from app.modules.analytics.schemas import LeadScoreRead
from app.modules.crm.constants import CompanyStatus


STATUS_SCORE_MAP = {
    CompanyStatus.NEW.value: 0,
    CompanyStatus.RESEARCH_NEEDED.value: 5,
    CompanyStatus.PREPARED.value: 10,
    CompanyStatus.CALL_PLANNED.value: 15,
    CompanyStatus.CALLED.value: 15,
    CompanyStatus.NO_ANSWER.value: 5,
    CompanyStatus.INTERESTED.value: 35,
    CompanyStatus.CONSULTATION_PLANNED.value: 45,
    CompanyStatus.PROPOSAL_SENT.value: 55,
}

PRIORITY_SCORE_MAP = {
    "high": 15,
    "medium": 5,
    "low": 0,
}

INTERACTION_SCORE_MAP = {
    "interested": 20,
    "callback_requested": 15,
    "consultation_booked": 25,
    "proposal_requested": 25,
    "rejected": -25,
    "no_answer": -5,
}

PROPOSAL_READY_STATUSES = {
    CompanyStatus.INTERESTED.value,
    CompanyStatus.CONSULTATION_PLANNED.value,
    CompanyStatus.PROPOSAL_SENT.value,
}


def calculate_lead_score(company_context: dict) -> LeadScoreRead:
    status = company_context["status"]
    priority = company_context["priority"]
    score = 0
    reasons: list[str] = []
    risks: list[str] = []

    if status == CompanyStatus.DEAL_WON.value:
        return _finalize(
            company_context,
            100,
            reasons=["сделка уже выиграна"],
            risks=[],
            next_best_action="Открыть карточку и запланировать следующий шаг",
        )

    if status in {CompanyStatus.DEAL_LOST.value, CompanyStatus.DO_NOT_CONTACT.value}:
        return _finalize(
            company_context,
            0,
            reasons=["лид исключён из активной работы"],
            risks=["повторный контакт не рекомендуется"],
            next_best_action="Не трогать",
        )

    if company_context["has_website"]:
        score += 10
        reasons.append("есть сайт")
    else:
        risks.append("нет сайта")

    if company_context["has_phone"]:
        score += 10
        reasons.append("есть телефон")
    else:
        risks.append("нет телефона")

    if company_context["has_decision_maker"]:
        score += 10
        reasons.append("есть ЛПР")
    else:
        risks.append("нет ЛПР")

    if company_context["has_city"]:
        score += 10
        reasons.append("указан город")
    else:
        risks.append("не указан город")

    if company_context["has_notes_or_history"]:
        score += 10
        reasons.append("есть заметки или история касаний")
    else:
        risks.append("мало контекста по лиду")

    status_points = STATUS_SCORE_MAP.get(status, 0)
    if status_points:
        score += status_points
        reasons.append(f"статус {status}")

    priority_points = PRIORITY_SCORE_MAP.get(priority, 0)
    if priority_points:
        score += priority_points
        reasons.append(f"priority {priority}")

    last_result = company_context["last_interaction_result"]
    interaction_points = INTERACTION_SCORE_MAP.get(last_result, 0)
    if interaction_points:
        score += interaction_points
        reasons.append(f"последнее касание {last_result}")

    if company_context["has_task_today"]:
        score += 10
        reasons.append("есть задача на сегодня")

    if company_context["has_overdue_task"] and status in {
        CompanyStatus.INTERESTED.value,
        CompanyStatus.CONSULTATION_PLANNED.value,
        CompanyStatus.PROPOSAL_SENT.value,
    }:
        score += 15
        reasons.append("просроченная задача по тёплому лиду")

    if company_context["days_without_interaction"] is not None:
        days = company_context["days_without_interaction"]
        if days > 30:
            score -= 20
            risks.append("нет касаний больше 30 дней")
        elif days > 14:
            score -= 10
            risks.append("нет касаний больше 14 дней")
        elif days <= 3:
            score += 10
            reasons.append("касание было в последние 3 дня")

    if status in {CompanyStatus.INTERESTED.value, CompanyStatus.PROPOSAL_SENT.value} and not company_context["has_open_task"]:
        score -= 10
        risks.append("нет активной follow-up задачи")

    next_best_action = _next_best_action(company_context)
    return _finalize(company_context, score, reasons, risks, next_best_action)


def _grade(score: int) -> str:
    if score <= 24:
        return "cold"
    if score <= 49:
        return "warm"
    if score <= 74:
        return "hot"
    return "priority"


def _next_best_action(company_context: dict) -> str:
    status = company_context["status"]
    if status in {CompanyStatus.DO_NOT_CONTACT.value, CompanyStatus.DEAL_LOST.value}:
        return "Не трогать"
    if status == CompanyStatus.NO_ANSWER.value:
        return "Перезвонить в другое время"
    if status == CompanyStatus.INTERESTED.value and not company_context["has_open_task"]:
        return "Поставить follow-up"
    if status == CompanyStatus.CONSULTATION_PLANNED.value:
        return "Подготовить консультационный пакет"
    if status == CompanyStatus.PROPOSAL_SENT.value:
        return "Дожать КП / уточнить решение"
    if status == CompanyStatus.NEW.value and status != CompanyStatus.PREPARED.value:
        return "Подготовить к звонку через AI"
    if (company_context["days_without_interaction"] or 0) > 14:
        return "Вернуться с мягким касанием"
    if not company_context["has_phone"] or not company_context["has_website"] or not company_context["has_decision_maker"]:
        return "Ресёрч и обогащение карточки"
    return "Открыть карточку и запланировать следующий шаг"


def _finalize(
    company_context: dict,
    raw_score: int,
    reasons: list[str],
    risks: list[str],
    next_best_action: str,
) -> LeadScoreRead:
    score = max(0, min(100, raw_score))
    grade = _grade(score)
    can_prepare_proposal = score >= 75 and company_context["status"] in PROPOSAL_READY_STATUSES
    proposal_recommendation = "Можно подготовить КП / договорный пакет" if can_prepare_proposal else None

    unique_reasons = _unique(reasons)
    unique_risks = _unique(risks)
    if not unique_reasons:
        unique_reasons = ["нужно собрать больше данных по лиду"]

    return LeadScoreRead(
        company_id=company_context["company_id"],
        company_name=company_context["company_name"],
        city=company_context["city"],
        source=company_context["source"],
        status=company_context["status"],
        priority=company_context["priority"],
        score=score,
        grade=grade,
        reasons=unique_reasons,
        risks=unique_risks,
        next_best_action=next_best_action,
        has_open_task=company_context["has_open_task"],
        has_overdue_task=company_context["has_overdue_task"],
        last_interaction_result=company_context["last_interaction_result"],
        can_prepare_proposal=can_prepare_proposal,
        proposal_recommendation=proposal_recommendation,
    )


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
