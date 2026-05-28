from __future__ import annotations

from app.modules.legal_discovery.schemas import LegalDiscoveredCompany


def _build_mock_company(
    index: int,
    *,
    legal_name: str,
    short_name: str,
    status: str = "active",
    confidence: str = "high",
    city: str = "Саратов",
    region: str = "Саратовская область",
    okved: str = "86.23",
    okved_name: str = "Стоматологическая практика",
    warnings: list[str] | None = None,
    address_suffix: str | None = None,
    inn: str | None = None,
    ogrn: str | None = None,
) -> LegalDiscoveredCompany:
    resolved_inn = inn or f"6453{index:06d}"
    resolved_ogrn = ogrn or f"1026403{index:06d}"
    address_tail = address_suffix or f"ул. Тестовая, д. {index}"
    return LegalDiscoveredCompany(
        provider="mock",
        inn=resolved_inn,
        ogrn=resolved_ogrn,
        kpp=f"6453{index:05d}"[:9],
        legal_name=legal_name,
        short_name=short_name,
        address=f"г. {city}, {address_tail}",
        city=city,
        region=region,
        status=status,
        okved=okved,
        okved_name=okved_name,
        raw_payload={"index": index, "mock": True},
        confidence=confidence,
        warnings=warnings or [],
    )


MOCK_COMPANIES: list[LegalDiscoveredCompany] = [
    _build_mock_company(1, legal_name='ООО "ДЕНТАЛ БРАВО"', short_name="Дентал Браво"),
    _build_mock_company(2, legal_name='ООО "СМАЙЛ КЛИНИК"', short_name="Смайл Клиник"),
    _build_mock_company(3, legal_name='ООО "АЛЬФА ДЕНТ"', short_name="Альфа Дент"),
    _build_mock_company(4, legal_name='ООО "ОРТО СМАЙЛ"', short_name="Орто Смайл"),
    _build_mock_company(5, legal_name='ООО "ДЕТСКАЯ УЛЫБКА"', short_name="Детская Улыбка"),
    _build_mock_company(6, legal_name='ООО "ИМПЛАНТ ЭКСПЕРТ"', short_name="Имплант Эксперт"),
    _build_mock_company(7, legal_name='ООО "КЛИНИКА БЕЛЫЙ ЗУБ"', short_name="Белый Зуб"),
    _build_mock_company(8, legal_name='ООО "ЗУБНОЙ СТАНДАРТ"', short_name="Зубной Стандарт"),
    _build_mock_company(9, legal_name='ООО "ПЕРВАЯ СТОМАТОЛОГИЯ"', short_name="Первая Стоматология"),
    _build_mock_company(10, legal_name='ООО "ЭСТЕТИК ДЕНТ"', short_name="Эстетик Дент"),
    _build_mock_company(11, legal_name='ООО "ДОКТОР УЛЫБКА"', short_name="Доктор Улыбка"),
    _build_mock_company(12, legal_name='ООО "ЗУБНАЯ ЛИНИЯ"', short_name="Зубная Линия"),
    _build_mock_company(13, legal_name='ООО "ДЕНТАЛ БРАВО"', short_name="Дентал Браво Повтор", inn="6453000001", ogrn="1026403000001"),
    _build_mock_company(14, legal_name='ООО "ГОРОДСКАЯ СТОМАТОЛОГИЯ"', short_name="Городская Стоматология", status="inactive", confidence="medium"),
    _build_mock_company(15, legal_name='ООО "ФОРМУЛА УЛЫБКИ"', short_name="Формула Улыбки"),
    _build_mock_company(16, legal_name='ООО "ПЛОМБА+"', short_name="Пломба+", warnings=["Нет short digital footprint"], confidence="medium"),
    _build_mock_company(17, legal_name='ООО "32 КАРАТА"', short_name="32 Карата"),
    _build_mock_company(18, legal_name='ООО "МЕДИКАЛ ДЕНТ"', short_name="Медикал Дент", okved="86.21", okved_name="Общая врачебная практика", confidence="medium"),
    _build_mock_company(19, legal_name='ООО "КОМФОРТ ДЕНТ"', short_name="Комфорт Дент", status="inactive", confidence="low"),
    _build_mock_company(20, legal_name='ООО "ДЕНТ СИТИ"', short_name="Дент Сити"),
    _build_mock_company(21, legal_name='ООО "САРТОМ"', short_name="Сартом", warnings=["Неполный адрес"], address_suffix="пр. Кирова"),
    _build_mock_company(22, legal_name='ООО "АКАДЕМИЯ УЛЫБКИ"', short_name="Академия Улыбки"),
    _build_mock_company(23, legal_name='ООО "БРАВО ДЕНТ"', short_name="Браво Дент", city="Энгельс"),
    _build_mock_company(24, legal_name='ООО "ПРОФИ ДЕНТ"', short_name="Профи Дент"),
    _build_mock_company(25, legal_name='ООО "СТОМАТОЛОГИЯ НА МОСКОВСКОЙ"', short_name="На Московской"),
    _build_mock_company(26, legal_name='ООО "МЕДСЕРВИС"', short_name="Медсервис", okved="86.90", okved_name="Прочая медицинская деятельность", confidence="low", warnings=["Ниша подтверждена неявно"]),
    _build_mock_company(27, legal_name='ООО "УЛЫБКА ПЛЮС"', short_name="Улыбка Плюс"),
    _build_mock_company(28, legal_name='ООО "ЭЛАЙНЕР ЦЕНТР"', short_name="Элайнер Центр"),
    _build_mock_company(29, legal_name='ООО "СКАН ДЕНТ"', short_name="Скан Дент"),
    _build_mock_company(30, legal_name='ООО "ЛИНИЯ ДОВЕРИЯ"', short_name="Линия Доверия", confidence="low", warnings=["Слабое совпадение по нише"]),
]


class MockLegalDiscoveryProvider:
    code = "mock"
    title = "Mock / Dev"
    enabled = True

    async def search_companies(
        self,
        query: str,
        city: str | None = None,
        region: str | None = None,
        limit: int = 50,
    ) -> list[LegalDiscoveredCompany]:
        normalized_query = query.lower().strip()
        normalized_city = (city or "").lower().strip()
        items = MOCK_COMPANIES
        if normalized_query:
            items = [
                company
                for company in items
                if normalized_query in company.legal_name.lower()
                or normalized_query in (company.short_name or "").lower()
                or normalized_query in (company.okved_name or "").lower()
                or normalized_query == "стоматология"
            ]
        if normalized_city:
            items = [company for company in items if (company.city or "").lower() == normalized_city]
        if region:
            items = [company for company in items if (company.region or "").lower() == region.lower().strip()]
        return items[:limit]
