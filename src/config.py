from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from model_provider import ProviderConfig, normalize_provider


@dataclass
class LabConfig:
    base_dir: Path
    data_dir: Path
    state_dir: Path
    compact_threshold_tokens: int
    compact_keep_messages: int
    model: ProviderConfig
    judge_model: ProviderConfig
    fact_confidence_threshold: float = 0.75



def load_config(base_dir: Path | None = None) -> LabConfig:
    root = (base_dir or Path(__file__).resolve().parent.parent).resolve()
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
    except ImportError:
        pass
    provider = normalize_provider(os.getenv("LLM_PROVIDER", "openai"))
    key_vars = {
        "openai": "OPENAI_API_KEY", "custom": "CUSTOM_API_KEY",
        "gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
        "ollama": "", "openrouter": "OPENROUTER_API_KEY",
    }

    def make_model(prefix: str, default_provider: str, default_name: str) -> ProviderConfig:
        selected = normalize_provider(os.getenv(f"{prefix}_PROVIDER", default_provider))
        base_url = os.getenv("CUSTOM_BASE_URL") if selected == "custom" else (
            os.getenv("OLLAMA_BASE_URL") if selected == "ollama" else None
        )
        return ProviderConfig(
            provider=selected,
            model_name=os.getenv(f"{prefix}_MODEL", default_name),
            temperature=float(os.getenv(f"{prefix}_TEMPERATURE", "0")),
            api_key=os.getenv(key_vars[selected]) if key_vars[selected] else None,
            base_url=base_url,
        )

    threshold = int(os.getenv("COMPACT_THRESHOLD_TOKENS", "600"))
    keep = int(os.getenv("COMPACT_KEEP_MESSAGES", "4"))
    if threshold <= 0 or keep < 1:
        raise ValueError("Compact threshold must be positive and keep_messages >= 1")
    state = root / "state"
    state.mkdir(parents=True, exist_ok=True)
    main = make_model("LLM", provider, "gpt-4o-mini")
    judge = make_model("JUDGE", provider, main.model_name)
    confidence_threshold = float(os.getenv("FACT_CONFIDENCE_THRESHOLD", "0.75"))
    return LabConfig(root, root / "data", state, threshold, keep, main, judge, confidence_threshold)

