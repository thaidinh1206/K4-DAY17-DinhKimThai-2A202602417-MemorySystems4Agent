from __future__ import annotations

from pathlib import Path

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config
from memory_store import (
    CompactMemoryManager, UserProfileStore, extract_profile_updates, extract_structured_facts,
)



def make_config(tmp_path: Path):
    config = load_config(tmp_path)
    config.compact_threshold_tokens = 100
    config.compact_keep_messages = 2
    return config


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    store = UserProfileStore(tmp_path / "profiles")
    assert store.file_size("dungct") == 0
    assert store.read_text("dungct").startswith("# User profile")
    store.write_text("dungct", "# User profile\n- location: Đà Nẵng\n")
    assert store.edit_text("dungct", "Đà Nẵng", "Huế")
    assert store.facts("dungct")["location"] == "Huế"
    store.upsert_fact("dungct", "location", "Đà Nẵng")
    assert store.facts("dungct")["location"] == "Đà Nẵng"
    assert store.file_size("dungct") > 0
    assert not store.edit_text("dungct", "missing", "x")


def test_compact_trigger(tmp_path: Path) -> None:
    memory = CompactMemoryManager(100, 2)
    for _ in range(5):
        memory.append("thread", "user", "Một đoạn tin dài về AI và Python. " * 10)
    assert memory.compaction_count("thread") > 0
    assert len(memory.context("thread")["messages"]) == 2
    assert memory.context("thread")["summary"]


def test_cross_session_recall(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)
    for agent in (baseline, advanced):
        agent.reply("u", "old", "Mình tên là DũngCT. Mình ở Đà Nẵng.")
    question = "Mình tên gì và hiện ở đâu?"
    assert "DũngCT" in baseline.reply("u", "old", question)["answer"]
    assert "DũngCT" not in baseline.reply("u", "new", question)["answer"]
    answer = advanced.reply("u", "new", question)["answer"]
    assert "DũngCT" in answer and "Đà Nẵng" in answer
    advanced.reply("u", "old", "Mình đính chính: giờ mình đang ở Huế chứ không còn ở Đà Nẵng.")
    assert advanced.profile_store.facts("u")["location"] == "Huế"
    assert "Huế" in advanced.reply("u", "another", "Hiện tại mình ở đâu?")["answer"]
    assert extract_profile_updates("Hà Nội chỉ là nơi mình đi họp, không phải nơi ở hiện tại.") == {}
    assert extract_profile_updates("Tên mình là gì?") == {}
    advanced.reply("u", "another", "Tên mình là gì?")
    assert advanced.profile_store.facts("u")["name"] == "DũngCT"


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)
    for i in range(16):
        message = f"Đây là tin số {i} về hệ thống AI. " + "Mình đang xem xét trade-off và vận hành. " * 25
        baseline.reply("u", "long", message)
        advanced.reply("u", "long", message)
    assert advanced.compaction_count("long") > 0
    assert advanced.prompt_token_usage("long") < baseline.prompt_token_usage("long")


def test_confidence_guardrail_rejects_questions_and_jokes(tmp_path: Path) -> None:
    # 1. Questions should have low confidence (< 0.5) and not update profile
    question_msg = "Có phải mình đang ở Hà Nội không?"
    facts_q = extract_structured_facts(question_msg)
    if "location" in facts_q:
        assert facts_q["location"].confidence < 0.5
    assert extract_profile_updates(question_msg) == {}

    # 2. Jokes and hypothetical statements should be rejected, while legitimate facts in same turn are kept
    joke_turn = (
        "Có lúc mình đùa với đồng nghiệp rằng hay là chuyển sang product manager cho đỡ phải ngồi canh pipeline, "
        "nhưng đó chỉ là câu đùa. Nghề nghiệp hiện tại vẫn là MLOps engineer."
    )
    facts_j = extract_structured_facts(joke_turn)
    assert facts_j["profession"].value == "MLOps engineer"
    assert facts_j["profession"].confidence >= 0.75
    updates = extract_profile_updates(joke_turn)
    assert updates.get("profession") == "MLOps engineer"
    assert "product manager" not in updates.values()

    # 3. Temporary trips and negated locations should not overwrite home location
    trip_msg = "Hà Nội chỉ là nơi mình vừa bay ra họp hai ngày với đối tác chứ không phải nơi ở hiện tại."
    assert extract_profile_updates(trip_msg) == {}


def test_conflict_handling_and_audit_history(tmp_path: Path) -> None:
    store = UserProfileStore(tmp_path / "profiles")
    user = "dungct_audit"

    # Add initial fact
    store.upsert_fact(user, "location", "Đà Nẵng", confidence=0.92, reason="Initial assertion")
    assert store.facts(user)["location"] == "Đà Nẵng"
    assert len(store.conflict_history(user)) == 0

    # User corrects location to Huế (Conflict!)
    corrected = store.upsert_fact(
        user, "location", "Huế", confidence=0.98, reason="Explicit correction: chuyển từ Đà Nẵng sang Huế"
    )
    assert corrected is True
    assert store.facts(user)["location"] == "Huế"

    # Verify conflict history was properly audited
    conflicts = store.conflict_history(user)
    assert len(conflicts) == 1
    assert conflicts[0]["key"] == "location"
    assert conflicts[0]["old_value"] == "Đà Nẵng"
    assert conflicts[0]["new_value"] == "Huế"
    assert conflicts[0]["confidence"] == 0.98

    # Verify User.md does NOT contain obsolete 'Đà Nẵng' location
    markdown_content = store.read_text(user)
    assert "- location: Huế" in markdown_content
    assert "- location: Đà Nẵng" not in markdown_content

