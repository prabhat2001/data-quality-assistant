"""Model settings loaded from backend/.env. OpenAI is the project default."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LlmSettings:
    llm_provider: str
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-luna"

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


def current_llm_settings() -> LlmSettings:
    from django.conf import settings

    return LlmSettings(
        llm_provider=settings.LLM_PROVIDER,
        gemini_api_key=settings.GEMINI_API_KEY,
        gemini_model=settings.GEMINI_MODEL,
        groq_api_key=settings.GROQ_API_KEY,
        groq_model=settings.GROQ_MODEL,
        openai_api_key=settings.OPENAI_API_KEY,
        openai_model=settings.OPENAI_MODEL,
    )
