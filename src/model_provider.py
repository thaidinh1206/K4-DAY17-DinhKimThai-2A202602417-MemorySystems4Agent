from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderConfig:
    provider: str
    model_name: str
    temperature: float = 0.0
    api_key: str | None = None
    base_url: str | None = None


def normalize_provider(value: str) -> str:
    name = value.strip().lower().replace("-", "_")
    name = {"anthorpic": "anthropic", "google": "gemini", "google_genai": "gemini"}.get(name, name)
    if name not in {"openai", "custom", "gemini", "anthropic", "ollama", "openrouter"}:
        raise ValueError(f"Unsupported provider: {value}")
    return name


def build_chat_model(config: ProviderConfig):
    """Build a live model lazily; offline agents never import provider packages."""
    provider = normalize_provider(config.provider)
    common = {"model": config.model_name, "temperature": config.temperature}
    if provider in {"openai", "custom"}:
        from langchain_openai import ChatOpenAI

        if provider == "custom" and not config.base_url:
            raise ValueError("CUSTOM_BASE_URL is required for the custom provider")
        return ChatOpenAI(**common, api_key=config.api_key or "unused", base_url=config.base_url)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(**common, google_api_key=config.api_key)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(**common, api_key=config.api_key)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(**common, base_url=config.base_url)
    from langchain_openrouter import ChatOpenRouter

    return ChatOpenRouter(**common, api_key=config.api_key)
