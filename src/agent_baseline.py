from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import answer_from_facts, estimate_tokens, extract_profile_updates


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Full thread history in memory, with no cross-thread persistence."""

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}
        self.langchain_agent = None

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        return self._reply_offline(thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        return self.sessions.get(thread_id, SessionState()).token_usage

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.sessions.get(thread_id, SessionState()).prompt_tokens_processed

    def compaction_count(self, thread_id: str) -> int:
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        session = self.sessions.setdefault(thread_id, SessionState())
        session.messages.append({"role": "user", "content": message})
        facts: dict[str, str] = {}
        for entry in session.messages:
            if entry["role"] == "user":
                facts.update(extract_profile_updates(entry["content"]))
        answer = answer_from_facts(message, facts)
        session.prompt_tokens_processed += sum(estimate_tokens(m["content"]) for m in session.messages)
        session.token_usage += estimate_tokens(answer)
        session.messages.append({"role": "assistant", "content": answer})
        return {"answer": answer, "response": answer, "tokens": estimate_tokens(answer)}

    def _maybe_build_langchain_agent(self):
        return None
