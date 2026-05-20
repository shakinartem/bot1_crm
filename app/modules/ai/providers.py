from abc import ABC, abstractmethod

import httpx

from app.config import Settings, get_settings


class AIProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> str:
        raise NotImplementedError


class OpenRouterProvider(AIProvider):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, prompt: str) -> str:
        if not self.settings.openrouter_api_key:
            return await FallbackProvider(self.settings).generate(prompt)
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.openrouter_api_key}"},
                json={
                    "model": self.settings.openrouter_model,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


class OllamaProvider(AIProvider):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/generate",
                json={"model": self.settings.ollama_model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            return response.json().get("response", "")


class FallbackProvider(AIProvider):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, prompt: str) -> str:
        return (
            "AI fallback-режим активен.\n\n"
            "1. Кратко о компании: проверьте сайт, отзывы, географию и специализации.\n"
            "2. Возможные боли: нехватка первичных пациентов, слабая конверсия сайта, мало отзывов, нет системной аналитики заявок.\n"
            "3. Точки роста: SEO/карты, упаковка услуг, скрипты администраторов, ретаргетинг, контроль источников.\n"
            "4. Персональный заход: начать с наблюдения по публичным данным компании.\n"
            "5. ФВ: сколько стоит новый пациент, какой план по выручке, есть ли бюджет на привлечение.\n"
            "6. СОПРАНО: выяснить ситуацию, опыт рекламы, принципы выбора подрядчика, прошлые решения, аналоги, нежелательные сценарии и ограничения.\n"
            "7. Доверие: говорить предметно, без обещаний, через диагностику и кейсовую логику.\n"
            "8. ЛПР: уточнить, кто принимает решение и кто участвует в обсуждении.\n"
            "9. Здесь и сейчас: связать разговор с ближайшей загрузкой врачей и планом месяца.\n"
            "10. Возражения: уже есть подрядчик, нет бюджета, неактуально, пришлите КП.\n"
            "11. Ответы: предложить короткую диагностику, сравнение каналов и один понятный следующий шаг.\n"
            "12. Следующий шаг: назначить консультацию/аудит на конкретное время.\n"
        )


def get_ai_provider() -> AIProvider:
    settings = get_settings()
    providers = {
        "openrouter": OpenRouterProvider,
        "ollama": OllamaProvider,
        "fallback": FallbackProvider,
    }
    return providers.get(settings.ai_provider.lower(), FallbackProvider)(settings)
