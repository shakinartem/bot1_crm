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
            "AI fallback-режим активен: внешний провайдер не настроен или недоступен.\n\n"
            "1. Краткое резюме клиники: проверьте сайт, отзывы, географию, специализации и публичные контакты.\n"
            "2. Возможные боли: нехватка первичных пациентов, слабая конверсия сайта, мало отзывов, нет понятной аналитики заявок.\n"
            "3. Что проверить перед звонком: сайт, карты, соцсети, отзывы, рекламные посадочные страницы, актуальность телефонов.\n"
            "4. Скрипт первого звонка: коротко представиться, объяснить повод, задать 2-3 диагностических вопроса, предложить аудит.\n"
            "5. Персонализированные заходы: отзывы, загрузка врачей, продвижение услуг, заявки с карт, качество сайта.\n"
            "6. Возражения: есть подрядчик, нет бюджета, неактуально, пришлите КП, нет времени.\n"
            "7. Ответы: предложить не продажу, а короткую диагностику и сравнение точек роста.\n"
            "8. Первый шаг: назначить 20-минутную консультацию или экспресс-аудит.\n"
            "9. Сообщение после звонка: отправить краткое резюме договоренности и 2-3 пункта аудита.\n"
            "10. Следующее действие: зафиксировать результат звонка и создать задачу на следующий контакт.\n"
        )


def get_ai_provider() -> AIProvider:
    settings = get_settings()
    providers = {
        "openrouter": OpenRouterProvider,
        "ollama": OllamaProvider,
        "fallback": FallbackProvider,
    }
    return providers.get(settings.ai_provider.lower(), FallbackProvider)(settings)
