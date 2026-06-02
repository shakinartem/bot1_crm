from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.modules.sales_intelligence.schemas import SalesMaterialScore

_WEIGHTS = {
    "website": 0.25,
    "conversion": 0.20,
    "trust": 0.20,
    "contact": 0.15,
    "socials": 0.10,
    "maps": 0.10,
}

_REQUIRED_TOP_LEVEL_SECTIONS = ("website", "socials", "maps", "trust", "contacts")


def _clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))


def _grade(value: int) -> str:
    if value <= 24:
        return "weak"
    if value <= 44:
        return "basic"
    if value <= 64:
        return "normal"
    if value <= 84:
        return "strong"
    return "excellent"


def _weighted_total(component_scores: dict[str, int]) -> int:
    total = sum(_clamp_score(component_scores[name]) * weight for name, weight in _WEIGHTS.items())
    return _clamp_score(round(total))


def _hypothesis(text: str) -> str:
    return f"По доступным сигналам можно предположить, что {text}."


def _check(text: str) -> str:
    return f"Стоит проверить, {text}."


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
        return any(_has_value(item) for item in value)
    return bool(value)


def _ratio_score(*signals: bool) -> int:
    if not signals:
        return 0
    matched = sum(1 for signal in signals if signal)
    return _clamp_score(round((matched / len(signals)) * 100))


def _score_website(company_context: Mapping[str, Any]) -> int:
    website = _as_dict(company_context.get("website"))
    return _ratio_score(
        _has_value(website.get("url")),
        bool(website.get("reachable")),
        (_safe_float(website.get("confidence")) or 0) >= 0.75,
        bool(website.get("has_phone")),
        bool(website.get("has_email")) or bool(website.get("has_form")),
        bool(website.get("has_messenger")),
        bool(website.get("has_cta")) or bool(website.get("has_online_booking")),
        bool(website.get("has_services")),
        bool(website.get("has_team")),
        bool(website.get("has_reviews")) or bool(website.get("has_privacy_policy")),
    )


def _score_socials(company_context: Mapping[str, Any]) -> int:
    socials = _as_dict(company_context.get("socials"))
    return _ratio_score(
        _has_value(socials.get("links")) or _has_value(socials.get("platforms")),
        _has_value(socials.get("platforms")),
        bool(socials.get("active")),
        bool(socials.get("has_trust_content")),
    )


def _score_maps(company_context: Mapping[str, Any]) -> int:
    maps = _as_dict(company_context.get("maps"))
    return _ratio_score(
        bool(maps.get("has_listing")),
        _has_value(maps.get("platforms")),
        bool(maps.get("has_reviews")) or bool(maps.get("rating")),
        bool(maps.get("contact_consistency")),
        bool(maps.get("has_photos")),
        bool(maps.get("has_description")) or bool(maps.get("has_services")),
    )


def _score_trust(company_context: Mapping[str, Any]) -> int:
    website = _as_dict(company_context.get("website"))
    trust = _as_dict(company_context.get("trust"))
    contacts = _as_dict(company_context.get("contacts"))
    socials = _as_dict(company_context.get("socials"))
    return _ratio_score(
        bool(trust.get("has_decision_maker")),
        bool(trust.get("has_legal_identifiers")),
        bool(website.get("reachable")),
        _has_value(contacts.get("address")),
        bool(trust.get("has_reviews")) or bool(website.get("has_reviews")),
        bool(trust.get("has_team")) or bool(website.get("has_team")),
        bool(trust.get("has_licenses")),
        _has_value(contacts.get("phones")) and (_has_value(contacts.get("emails")) or _has_value(socials.get("links"))),
    )


def _score_conversion(company_context: Mapping[str, Any]) -> int:
    website = _as_dict(company_context.get("website"))
    return _ratio_score(
        bool(website.get("has_cta")),
        bool(website.get("has_online_booking")),
        bool(website.get("has_form")),
        bool(website.get("has_messenger")),
        bool(website.get("has_phone")),
        bool(website.get("has_services")),
        bool(website.get("has_prices")) or bool(website.get("has_consultation_offer")),
    )


def _score_contacts(company_context: Mapping[str, Any]) -> int:
    contacts = _as_dict(company_context.get("contacts"))
    website = _as_dict(company_context.get("website"))
    socials = _as_dict(company_context.get("socials"))
    maps = _as_dict(company_context.get("maps"))
    return _ratio_score(
        _has_value(contacts.get("phones")) or bool(website.get("has_phone")),
        _has_value(contacts.get("emails")) or bool(website.get("has_email")) or bool(website.get("has_form")),
        _has_value(website.get("url")),
        _has_value(contacts.get("messengers")) or bool(website.get("has_messenger")),
        _has_value(contacts.get("address")),
        _has_value(socials.get("links")) or _has_value(socials.get("platforms")),
        bool(maps.get("has_listing")),
    )


def _build_reasons(scores: Mapping[str, int]) -> list[str]:
    reasons: list[str] = []
    if scores["website"] >= 60:
        reasons.append(_hypothesis("сайт уже закрывает несколько базовых задач упаковки и первого доверия"))
    if scores["maps"] >= 50:
        reasons.append(_hypothesis("карты уже могут поддерживать локальный спрос и обнаружение компании"))
    if scores["trust"] >= 50:
        reasons.append(_hypothesis("у компании уже видны отдельные сигналы доверия на публичной стороне"))
    if scores["contact"] >= 60:
        reasons.append(_hypothesis("клиенту, вероятно, доступно хотя бы одно понятное контактное окно"))
    return reasons


def _build_risks(company_context: Mapping[str, Any], scores: Mapping[str, int]) -> list[str]:
    website = _as_dict(company_context.get("website"))
    socials = _as_dict(company_context.get("socials"))
    risks: list[str] = []
    if scores["socials"] < 50:
        risks.append(_check("соцсети неактивны, редки или пока слабо усиливают доверие"))
    if scores["conversion"] < 60:
        risks.append(_check("следующий шаг для посетителя сайта пока недостаточно очевиден"))
    if not (bool(website.get("has_cta")) or bool(website.get("has_online_booking"))):
        risks.append(_check("на сайте нет заметного CTA или понятного шага к записи"))
    if not bool(socials.get("active")):
        risks.append(_check("соцпрофили обновляются недостаточно регулярно, чтобы поддерживать доверие"))
    return risks


def _build_opportunities(company_context: Mapping[str, Any], scores: Mapping[str, int]) -> list[str]:
    website = _as_dict(company_context.get("website"))
    maps = _as_dict(company_context.get("maps"))
    opportunities: list[str] = []
    if scores["website"] < 80:
        opportunities.append(_hypothesis("более ясная структура сайта может усилить первое впечатление и понимание оффера"))
    if scores["trust"] < 75:
        opportunities.append(_hypothesis("дополнительные доказательства и кейсы могут заметно усилить доверие"))
    if not bool(maps.get("has_photos")):
        opportunities.append(_hypothesis("более полное оформление карточек на картах может повысить локальное доверие"))
    if not bool(website.get("has_messenger")):
        opportunities.append(_hypothesis("добавление мессенджера может снизить трение при первом обращении"))
    return opportunities


def _build_next_improvements(company_context: Mapping[str, Any]) -> list[str]:
    website = _as_dict(company_context.get("website"))
    socials = _as_dict(company_context.get("socials"))
    maps = _as_dict(company_context.get("maps"))
    improvements: list[str] = []
    if not (bool(website.get("has_cta")) or bool(website.get("has_online_booking"))):
        improvements.append(_check("следующим улучшением сайта стоит сделать ясный CTA или путь к записи"))
    if not bool(website.get("has_reviews")):
        improvements.append(_check("на сайт стоит добавить видимые отзывы, кейсы или другие proof-блоки"))
    if not bool(socials.get("active")):
        improvements.append(_check("регулярный ритм публикаций в соцсетях может поддержать доверие"))
    if not bool(maps.get("has_photos")):
        improvements.append(_check("карточкам на картах не хватает фото или более полного контента"))
    return improvements


def _missing_sections(company_context: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    for section_name in _REQUIRED_TOP_LEVEL_SECTIONS:
        if not isinstance(company_context.get(section_name), Mapping):
            missing.append(section_name)
    return missing


def _context_cautions(company_context: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    cautions: list[str] = []
    improvements: list[str] = []
    missing_sections = _missing_sections(company_context)
    if missing_sections:
        joined = ", ".join(missing_sections)
        cautions.append(_check(f"в нормализованном контексте пока отсутствуют обязательные разделы: {joined}"))
        for section_name in missing_sections:
            improvements.append(_check(f"перед использованием скоринга стоит заполнить раздел '{section_name}'"))

    website = _as_dict(company_context.get("website"))
    confidence_value = website.get("confidence")
    if confidence_value is not None and _safe_float(confidence_value) is None:
        cautions.append(_check("поле confidence сайта не удалось разобрать и оно считается недоступным"))
    return cautions, improvements


def calculate_material_quality_score(company_context: dict[str, Any]) -> SalesMaterialScore:
    website_score = _score_website(company_context)
    socials_score = _score_socials(company_context)
    maps_score = _score_maps(company_context)
    trust_score = _score_trust(company_context)
    conversion_score = _score_conversion(company_context)
    contact_score = _score_contacts(company_context)
    component_scores = {
        "website": website_score,
        "socials": socials_score,
        "maps": maps_score,
        "trust": trust_score,
        "conversion": conversion_score,
        "contact": contact_score,
    }
    total_score = _weighted_total(component_scores)
    context_risks, context_improvements = _context_cautions(company_context)
    return SalesMaterialScore(
        company_id=int(company_context.get("company_id") or 0),
        total_score=total_score,
        grade=_grade(total_score),
        website_score=website_score,
        socials_score=socials_score,
        maps_score=maps_score,
        trust_score=trust_score,
        conversion_score=conversion_score,
        contact_score=contact_score,
        reasons=_build_reasons(component_scores),
        risks=[*context_risks, *_build_risks(company_context, component_scores)],
        opportunities=_build_opportunities(company_context, component_scores),
        next_improvements=[*context_improvements, *_build_next_improvements(company_context)],
    )


__all__ = ["calculate_material_quality_score"]
