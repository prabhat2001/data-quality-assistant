"""Runtime settings. Secrets stay in backend/.env, which is not committed."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _default_database_url() -> str:
    user = os.environ.get("USER") or "postgres"
    return f"postgresql+psycopg2://{user}@localhost:5432/data_quality"


class Settings(BaseSettings):
    database_url: str = _default_database_url()
    seed_demo_data: bool = False

    # gemini (free tier) is the development default. Switch to openai for a paid key.
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    def llm_api_key(self) -> str:
        provider = self.llm_provider.strip().lower()
        if provider == "openai":
            return self.openai_api_key.strip()
        if provider == "groq":
            return self.groq_api_key.strip()
        return self.gemini_api_key.strip()

    def llm_model(self) -> str:
        provider = self.llm_provider.strip().lower()
        if provider == "openai":
            return self.openai_model
        if provider == "groq":
            return self.groq_model
        return self.gemini_model

    def llm_configured(self) -> bool:
        return bool(self.llm_api_key()) and self.llm_provider.strip().lower() in {
            "gemini",
            "groq",
            "openai",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
