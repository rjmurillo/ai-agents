"""Review fixes: attributed tag blocks, control overflow in strata, undated turn count.

Synthetic data only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from replies_helpers import (
    CONTROL_REPLY,
    assistant_text,
    plant_control,
    prepare_args,
    prepare_ok,
    replies_corpus,
    replies_prepare,
    run_cli,
    simple_session,
    user,
    write_session,
)


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "projects" / "proj-a"


@pytest.mark.parametrize(
    ("text", "left"),
    [
        ('<pasted_content id="1">synthetic blob</pasted_content>', ""),
        ('<pasted_content id="1" name="x">synthetic blob</pasted_content> typed', " typed"),
        ("<pasted_content>synthetic blob</pasted_content>", ""),
        ("<system-reminder>synthetic note</system-reminder>", ""),
        ("<system-reminder>synthetic note</system-reminder>kept", "kept"),
    ],
)
def test_tag_block_strips_plain_and_attributed_blocks(text: str, left: str) -> None:
    assert replies_corpus.TAG_BLOCK.sub("", text) == left


def test_tag_block_leaves_a_mismatched_or_prefixed_tag_name_alone() -> None:
    text = '<pasted_contentx id="1">synthetic</pasted_contentx>'
    assert replies_corpus.TAG_BLOCK.sub("", text) == text


def test_attributed_paste_before_typed_words_is_a_typed_followup(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pasted = '<pasted_content id="1">synthetic pasted log line</pasted_content> now fix it'
    recs = [user("synthetic prompt wording sigma for paste test", 1), assistant_text("one", 2)]
    recs += [user(pasted, 3), assistant_text("two", 4)]
    write_session(store, "main-a", recs)
    plant_control(store)
    run_dir = tmp_path / "run"
    payload, _ = prepare_ok(capsys, store, run_dir)
    assert "relay" not in payload["machine"]
    assert payload["turns"]["typed_followup"] == 1


def test_a_paste_only_turn_is_skipped_not_a_followup(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pasted = '<pasted_content id="1">synthetic pasted log line</pasted_content>'
    recs = [user("synthetic prompt wording tau for paste test", 1), assistant_text("one", 2)]
    recs += [user(pasted, 3), assistant_text("two", 4)]
    write_session(store, "main-a", recs)
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    assert payload["machine"] == {"empty": 1}
    assert payload["turns"].get("typed_followup", 0) == 0


def test_marker_hits_over_the_cap_stay_in_the_strata(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hits = replies_prepare.MAX_CONTROLS + 5
    for number in range(hits):
        prompt = f"synthetic unique hit prompt {number} omega"
        write_session(store, f"hit{number}", simple_session(prompt, [CONTROL_REPLY], 10 + number))
    for number in range(4):
        prompt = f"synthetic unique plain prompt {number} psi"
        reply = f"Plain finished statement {number}."
        write_session(store, f"plain{number}", simple_session(prompt, [reply], 200 + number))
    code, payload, _ = run_cli(capsys, prepare_args(store, tmp_path / "run"))
    assert code == 0, payload
    eligible = sum(kind["total"] for kind in payload["replies"]["by_kind"].values())
    population = sum(stratum["population"] for stratum in payload["strata"])
    assert payload["replies"]["marker_hits"] == hits
    assert payload["controls_sampled"] == replies_prepare.MAX_CONTROLS
    assert eligible == hits + 4
    assert population == eligible - replies_prepare.MAX_CONTROLS
    assert payload["controls_sampled"] + population == eligible
    manifest = json.loads((tmp_path / "run" / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["control_ids"]) == replies_prepare.MAX_CONTROLS


def test_undated_turns_are_reported_beside_parse_errors(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    undated: dict[str, Any] = user("synthetic undated typed turn", 3)
    undated["timestamp"] = None
    recs = [user("synthetic prompt wording upsilon for dating test", 1), assistant_text("one", 2)]
    recs += [undated, assistant_text("two", 4)]
    write_session(store, "main-a", recs)
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    assert payload["population"]["undated_turns"] == 1
    assert payload["population"]["parse_errors"] == 0


def test_undated_turns_default_to_zero(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(store, "main-a", simple_session("synthetic dated prompt wording phi", ["ok"], 1))
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    assert payload["population"]["undated_turns"] == 0
