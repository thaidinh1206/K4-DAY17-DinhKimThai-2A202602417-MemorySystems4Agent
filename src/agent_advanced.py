from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import LabConfig, load_config
from memory_store import (
    CompactMemoryManager, ExtractedFact, UserProfileStore, answer_from_facts, estimate_tokens,
    extract_profile_updates, extract_structured_facts,
)


@dataclass
class AgentContext:
    user_id: str
    memory_path: str


class AdvancedAgent:
    """Persistent profile plus bounded per-thread context."""

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.confidence_threshold = getattr(self.config, "fact_confidence_threshold", 0.75)
        self.profile_store = UserProfileStore(self.config.state_dir / "profiles")
        self.compact_memory = CompactMemoryManager(
            threshold_tokens=self.config.compact_threshold_tokens,
            keep_messages=self.config.compact_keep_messages,
        )
        self.thread_tokens: dict[str, int] = {}
        self.thread_prompt_tokens: dict[str, int] = {}
        self.langchain_agent = None

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        return self._reply_offline(user_id, thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        return self.thread_tokens.get(thread_id, 0)

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.thread_prompt_tokens.get(thread_id, 0)

    def memory_file_size(self, user_id: str) -> int:
        return self.profile_store.file_size(user_id)

    def compaction_count(self, thread_id: str) -> int:
        return self.compact_memory.compaction_count(thread_id)

    def _reply_offline(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        structured_facts = extract_structured_facts(message)
        for key, fact in structured_facts.items():
            if fact.confidence >= self.confidence_threshold:
                self.profile_store.upsert_fact(
                    user_id, key, fact.value, confidence=fact.confidence, reason=fact.reason
                )
        self.compact_memory.append(thread_id, "user", message)
        prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        answer = self._offline_response(user_id, thread_id, message)
        self.compact_memory.append(thread_id, "assistant", answer)
        self.thread_prompt_tokens[thread_id] = self.thread_prompt_tokens.get(thread_id, 0) + prompt_tokens
        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + estimate_tokens(answer)
        return {"answer": answer, "response": answer, "tokens": estimate_tokens(answer)}


    def _estimate_prompt_context_tokens(self, user_id: str, thread_id: str) -> int:
        context = self.compact_memory.context(thread_id)
        return (
            estimate_tokens(self.profile_store.read_text(user_id))
            + estimate_tokens(str(context["summary"]))
            + sum(estimate_tokens(m["content"]) for m in context["messages"])
        )

    def _offline_response(self, user_id: str, thread_id: str, message: str) -> str:
        return answer_from_facts(message, self.profile_store.facts(user_id))

    def _maybe_build_langchain_agent(self):
        return None
