from __future__ import annotations

from app.modules.intelligence.providers.base import LegalLookupProvider
from app.modules.intelligence.schemas import LegalCompany


class MockLegalProvider(LegalLookupProvider):
    code = "mock"
    title = "Mock legal provider"
    enabled = True

    async def find_by_inn(self, inn: str) -> LegalCompany | None:
        cleaned = "".join(ch for ch in inn if ch.isdigit())
        if not cleaned:
            return None
        if cleaned == "7701234567":
            return self._dental_bravo()
        return LegalCompany(
            provider=self.code,
            inn=cleaned,
            ogrn="1027700000000",
            legal_name=f"ООО {cleaned}",
            short_name=cleaned,
            address="Россия",
            city="Саратов",
            region="Саратовская область",
            status="active",
            okved="86.23",
            raw_payload={"mock": True},
            confidence=0.75,
        )

    async def search_by_name(
        self,
        name: str,
        city: str | None = None,
        region: str | None = None,
        limit: int = 10,
    ) -> list[LegalCompany]:
        haystack = f"{name} {city or ''} {region or ''}".lower()
        if "дентал браво" in haystack:
            return [self._dental_bravo()]
        if "дентал" in haystack:
            return [
                self._dental_bravo(),
                LegalCompany(
                    provider=self.code,
                    inn="7707654321",
                    ogrn="1027700000011",
                    legal_name='ООО "ДЕНТАЛ БРАВО ПЛЮС"',
                    short_name="Дентал Браво Плюс",
                    address="г. Саратов, ул. Волжская, 10",
                    city="Саратов",
                    region="Саратовская область",
                    status="active",
                    okved="86.23",
                    raw_payload={"mock": True},
                    confidence=0.58,
                ),
            ][:limit]
        return []

    def _dental_bravo(self) -> LegalCompany:
        return LegalCompany(
            provider=self.code,
            inn="7701234567",
            ogrn="1027700000001",
            kpp="770101001",
            legal_name='ООО "ДЕНТАЛ БРАВО"',
            short_name="Дентал Браво",
            address="г. Саратов, ул. Радищева, 15",
            city="Саратов",
            region="Саратовская область",
            status="active",
            okved="86.23",
            raw_payload={"mock": True},
            confidence=0.92,
        )
