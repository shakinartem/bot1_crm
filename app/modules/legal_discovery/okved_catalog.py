from __future__ import annotations

import re

from app.modules.legal_discovery.schemas import PopularOkvedItem


POPULAR_OKVED_ITEMS: list[PopularOkvedItem] = [
    PopularOkvedItem(code="86.23", normalized_code="862300", title="Стоматологическая практика", keywords=["стоматология", "стоматологическая клиника", "зубная клиника"]),
    PopularOkvedItem(code="56.10", normalized_code="561000", title="Рестораны и услуги по доставке продуктов питания", keywords=["ресторан", "кафе", "доставка еды"]),
    PopularOkvedItem(code="69.10", normalized_code="691000", title="Деятельность в области права", keywords=["юрист", "юридические услуги", "адвокат"]),
    PopularOkvedItem(code="68.31", normalized_code="683100", title="Деятельность агентств недвижимости за вознаграждение", keywords=["недвижимость", "риелтор", "агентство недвижимости"]),
    PopularOkvedItem(code="45.20", normalized_code="452000", title="Техническое обслуживание и ремонт автотранспортных средств", keywords=["автосервис", "сто", "ремонт авто"]),
    PopularOkvedItem(code="96.02", normalized_code="960200", title="Предоставление услуг парикмахерскими и салонами красоты", keywords=["салон красоты", "парикмахерская", "маникюр"]),
    PopularOkvedItem(code="93.13", normalized_code="931300", title="Деятельность фитнес-центров", keywords=["фитнес", "спортзал", "тренажерный зал"]),
    PopularOkvedItem(code="73.11", normalized_code="731100", title="Деятельность рекламных агентств", keywords=["маркетинг", "реклама", "digital агентство"]),
    PopularOkvedItem(code="62.01", normalized_code="620100", title="Разработка компьютерного программного обеспечения", keywords=["разработка по", "it", "разработка сайтов"]),
    PopularOkvedItem(code="85.41", normalized_code="854100", title="Образование дополнительное детей и взрослых", keywords=["образовательный центр", "курсы", "школа"]),
]


def list_popular_okved() -> list[PopularOkvedItem]:
    return POPULAR_OKVED_ITEMS


def normalize_okved_code(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D+", "", value)
    if not digits:
        return None
    if len(digits) == 4:
        return f"{digits}00"
    if len(digits) >= 6:
        return digits[:6]
    return digits.ljust(6, "0")


def resolve_okved_by_query(query: str | None) -> PopularOkvedItem | None:
    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return None
    direct_code = normalize_okved_code(normalized_query)
    if direct_code:
        return next((item for item in POPULAR_OKVED_ITEMS if item.normalized_code == direct_code), None)
    for item in POPULAR_OKVED_ITEMS:
        if any(keyword in normalized_query for keyword in item.keywords):
            return item
    return None
