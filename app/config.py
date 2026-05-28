from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(default="", alias="BOT_TOKEN")
    bot2_api_token: str = Field(default="", alias="BOT2_API_TOKEN")
    database_url: str = Field(default="sqlite+aiosqlite:///./app.db", alias="DATABASE_URL")

    ai_provider: str = Field(default="fallback", alias="AI_PROVIDER")
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="meta-llama/llama-3.1-8b-instruct:free", alias="OPENROUTER_MODEL")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:7b", alias="OLLAMA_MODEL")

    storage_path: Path = Field(default=Path("./storage"), alias="STORAGE_PATH")
    admin_ids: str = Field(default="", alias="ADMIN_IDS")
    legal_provider: str = Field(default="mock", alias="LEGAL_PROVIDER")
    search_provider: str = Field(default="mock", alias="SEARCH_PROVIDER")
    api_fns_key: str = Field(default="", alias="API_FNS_KEY")
    api_fns_base_url: str = Field(default="https://api-fns.ru/api", alias="API_FNS_BASE_URL")
    dadata_token: str = Field(default="", alias="DADATA_TOKEN")
    dadata_secret: str = Field(default="", alias="DADATA_SECRET")
    yandex_search_api_key: str = Field(default="", alias="YANDEX_SEARCH_API_KEY")
    yandex_search_folder_id: str = Field(default="", alias="YANDEX_SEARCH_FOLDER_ID")
    google_search_api_key: str = Field(default="", alias="GOOGLE_SEARCH_API_KEY")
    google_search_engine_id: str = Field(default="", alias="GOOGLE_SEARCH_ENGINE_ID")
    intelligence_request_timeout: int = Field(default=10, alias="INTELLIGENCE_REQUEST_TIMEOUT")
    intelligence_search_limit: int = Field(default=10, alias="INTELLIGENCE_SEARCH_LIMIT")

    @property
    def admin_id_list(self) -> list[int]:
        return [int(item.strip()) for item in self.admin_ids.split(",") if item.strip().isdigit()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
