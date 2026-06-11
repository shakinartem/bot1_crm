from __future__ import annotations

from app.modules.crm.constants import CompanyStatus
from app.modules.crm.models import Company
from app.modules.lead_fit.schemas import LeadFitScore


GROUP_LABELS = {
    "A_hot_priority": "🔥 Горячие",
    "B_warm_potential": "🟡 Перспективные",
    "C_neutral_database": "⚪ Нейтральные",
    "D_low_priority": "🔻 Низкий приоритет",
    "excluded_do_not_contact": "🚫 Исключённые",
}


def calculate_lead_fit(company: Company) -> LeadFitScore:
    score = 0
    reasons: list[str] = []
    disqualifiers: list[str] = []

    if company.status in {CompanyStatus.DEAL_LOST.value, CompanyStatus.DO_NOT_CONTACT.value}:
        disqualifiers.append("company_status_not_contactable")
    if not company.inn and not company.ogrn:
        disqualifiers.append("missing_legal_identifiers")
    if company.deleted_at is not None:
        disqualifiers.append("deleted_company")

    if company.inn or company.ogrn:
        score += 15
        reasons.append("Есть ИНН/ОГРН")
    if company.phone:
        score += 20
        reasons.append("Есть телефон")
    if company.website:
        score += 20
        reasons.append("Есть сайт")
    if company.city or company.region:
        score += 10
        reasons.append("Есть город/регион")
    if company.address:
        score += 10
        reasons.append("Есть адрес")
    if company.reviews_count:
        score += min(company.reviews_count, 10)
        reasons.append("Есть признаки живого бизнеса")
    if company.maps_url:
        score += 10
        reasons.append("Есть карты/листинг")
    if company.source and "legal_discovery" in company.source:
        score += 5
        reasons.append("Импортирован из discovery")

    if disqualifiers:
        group = "excluded_do_not_contact"
        next_action = "Не брать в активную работу, оставить только для истории и контроля дублей."
        score = min(score, 20)
    elif score >= 70:
        group = "A_hot_priority"
        next_action = "Создать план 7 касаний и подготовить звонок."
    elif score >= 50:
        group = "B_warm_potential"
        next_action = "Взять во вторую волну и проверить digital-слабые места."
    elif score >= 30:
        group = "C_neutral_database"
        next_action = "Оставить в базе и вернуться после приоритетных групп."
    else:
        group = "D_low_priority"
        next_action = "Накопить данные или отложить до следующей волны."

    return LeadFitScore(
        company_id=company.id,
        total_score=max(0, min(100, score)),
        group=group,
        group_label=GROUP_LABELS[group],
        reasons=reasons,
        disqualifiers=disqualifiers,
        recommended_next_action=next_action,
        calculated_at=company.updated_at or company.created_at,
    )
