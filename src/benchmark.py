from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of conversations in {path}")
    return data


def recall_points(answer: str, expected: list[str]) -> float:
    if not expected:
        return 1.0
    normalized = answer.casefold()
    return sum(item.casefold() in normalized for item in expected) / len(expected)


def heuristic_quality(answer: str, expected: list[str]) -> float:
    if not answer.strip() or "chưa có thông tin" in answer.casefold():
        return 0.0
    return round(0.8 * recall_points(answer, expected) + 0.2 * (len(answer) <= 500), 3)


def run_agent_benchmark(agent_name: str, agent, conversations: list[dict[str, Any]], config) -> BenchmarkRow:
    before = sum(agent.memory_file_size(user) for user in {c["user_id"] for c in conversations}) if isinstance(agent, AdvancedAgent) else 0
    thread_ids: list[str] = []
    scores: list[float] = []
    qualities: list[float] = []
    for conversation in conversations:
        user_id = conversation["user_id"]
        thread_id = f"{conversation['id']}-main"
        thread_ids.append(thread_id)
        for turn in conversation["turns"]:
            agent.reply(user_id, thread_id, turn)
        for index, question in enumerate(conversation["recall_questions"]):
            recall_thread = f"{conversation['id']}-recall-{index}"
            thread_ids.append(recall_thread)
            answer = agent.reply(user_id, recall_thread, question["question"])["answer"]
            scores.append(recall_points(answer, question["expected_contains"]))
            qualities.append(heuristic_quality(answer, question["expected_contains"]))
    after = sum(agent.memory_file_size(user) for user in {c["user_id"] for c in conversations}) if isinstance(agent, AdvancedAgent) else 0
    return BenchmarkRow(
        agent_name,
        sum(agent.token_usage(thread) for thread in thread_ids),
        sum(agent.prompt_token_usage(thread) for thread in thread_ids),
        sum(scores) / len(scores) if scores else 0.0,
        sum(qualities) / len(qualities) if qualities else 0.0,
        after - before,
        sum(agent.compaction_count(thread) for thread in thread_ids),
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    header = "| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |"
    divider = "|---|---:|---:|---:|---:|---:|---:|"
    lines = [header, divider]
    for row in rows:
        lines.append(
            f"| {row.agent_name} | {row.agent_tokens_only} | {row.prompt_tokens_processed} | "
            f"{row.recall_score:.1%} | {row.response_quality:.1%} | "
            f"{row.memory_growth_bytes} | {row.compactions} |"
        )
    return "\n".join(lines)


def main() -> None:
    config = load_config(Path(__file__).resolve().parent.parent)
    for title, filename in (
        ("Standard Benchmark", "conversations.json"),
        ("Long-Context Stress Benchmark", "advanced_long_context.json"),
    ):
        conversations = load_conversations(config.data_dir / filename)
        rows = []
        # Reset dataset users before each run so previous benchmark runs cannot leak facts.
        for name, agent_class in (("Baseline", BaselineAgent), ("Advanced", AdvancedAgent)):
            run_config = replace(config, state_dir=config.state_dir / f"benchmark_{Path(filename).stem}_{name.lower()}")
            agent = agent_class(run_config, force_offline=True)
            if isinstance(agent, AdvancedAgent):
                for user in {c["user_id"] for c in conversations}:
                    agent.profile_store.write_text(user, "# User profile\n")
            rows.append(run_agent_benchmark(name, agent, conversations, run_config))
        print(f"## {title}\n{format_rows(rows)}\n")


if __name__ == "__main__":
    main()
