"""Review fixes: attributed tag blocks, control overflow in strata, undated turn count.

Synthetic data only.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from replies_helpers import (
    CONTROL_REPLY,
    CONTROL_TOKEN,
    assistant_text,
    evidence_rows,
    plant_control,
    prepare_args,
    prepare_ok,
    replies_corpus,
    replies_prepare,
    replies_sample,
    replies_tally,
    run_cli,
    simple_session,
    user,
    write_child,
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


def test_a_paste_only_turn_ends_the_reply_before_it(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pasted = '<pasted_content id="1">synthetic pasted log line</pasted_content>'
    recs = [user("synthetic prompt wording tau for paste test", 1), assistant_text("one", 2)]
    recs += [user(pasted, 3), assistant_text("two", 4)]
    write_session(store, "main-a", recs)
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    assert "empty" not in payload["machine"]
    assert payload["turns"]["typed_followup"] == 1
    # Both replies in the session plus the planted control reply.
    assert sum(kind["total"] for kind in payload["replies"]["by_kind"].values()) == 3


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


JUDGE_DOC = Path(replies_corpus.__file__).parent.parent / "references" / "reply-friction-judge.md"
LABELS_SCHEMA = "reply-friction/labels/v1"


def make_tally_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    store = tmp_path / "projects" / "proj-a"
    plant_control(store)
    write_session(store, "main-a", simple_session("synthetic prompt wording kappa", ["Done."], 10))
    run_dir = tmp_path / "run"
    prepare_ok(capsys, store, run_dir)
    return run_dir


def tally_cli(
    capsys: pytest.CaptureFixture[str], run_dir: Path, labels: Path
) -> tuple[int, dict[str, Any]]:
    code, payload, _ = run_cli(
        capsys, ["tally", "--run-dir", str(run_dir), "--labels", str(labels)]
    )
    return code, payload


def rewrite_evidence(run_dir: Path, extra_line: str) -> None:
    """Append a row and rewrite the manifest hash so load_run reaches the row check."""
    evidence = run_dir / replies_sample.EVIDENCE_NAME
    blob = evidence.read_bytes() + extra_line.encode("utf-8") + b"\n"
    evidence.write_bytes(blob)
    manifest_path = run_dir / replies_sample.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence_sha256"] = hashlib.sha256(blob).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def stratum(population: int, sampled: int, friction: int) -> dict[str, Any]:
    cell = {"n": sampled, "unclear": 0, "friction": friction}
    return {"population": population, "cell": cell}


def test_census_stratum_does_not_void_the_interval() -> None:
    ordinary = [stratum(100, 4, 1), stratum(80, 5, 2)]
    census = stratum(1, 1, 1)
    without = replies_tally._interval(ordinary, 0.3, 180)
    assert without is not None
    assert replies_tally._interval([*ordinary, census], 0.3, 180) == without


def test_unresolved_small_sample_still_voids_the_interval() -> None:
    assert replies_tally._interval([stratum(100, 4, 1), stratum(50, 1, 0)], 0.3, 150) is None


def test_deeply_nested_labels_are_a_config_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = make_tally_run(tmp_path, capsys)
    labels = tmp_path / "deep.json"
    labels.write_text("[" * 100_000, encoding="utf-8")
    assert labels.stat().st_size < replies_tally.MAX_LABEL_BYTES
    code, payload = tally_cli(capsys, run_dir, labels)
    assert (code, payload) == (2, {"error": "config", "message": "labels_not_json"})


@pytest.mark.parametrize("line", ["[]", "5", '{"id": 7}', '{"reply": "no id"}'])
def test_evidence_row_without_a_string_id_is_unreadable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], line: str
) -> None:
    run_dir = make_tally_run(tmp_path, capsys)
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"schema": LABELS_SCHEMA, "labels": []}), encoding="utf-8")
    rewrite_evidence(run_dir, line)
    code, payload = tally_cli(capsys, run_dir, labels)
    assert (code, payload) == (2, {"error": "config", "message": "run_dir_unreadable"})


def test_manifest_sample_count_mismatch_is_a_config_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = make_tally_run(tmp_path, capsys)
    manifest_path = run_dir / replies_sample.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["strata"][0]["sampled"] += 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    labels: list[dict[str, Any]] = []
    for row in evidence_rows(run_dir):
        if CONTROL_TOKEN in row["reply"]:
            labels.append(
                {
                    "id": row["id"],
                    "label": "friction",
                    "category": "offer_tail",
                    "quote_source": "reply",
                    "quote": "Want me to",
                }
            )
        else:
            labels.append({"id": row["id"], "label": "none"})
    path = tmp_path / "labels.json"
    path.write_text(json.dumps({"schema": LABELS_SCHEMA, "labels": labels}), encoding="utf-8")
    code, payload = tally_cli(capsys, run_dir, path)
    assert (code, payload) == (2, {"error": "config", "message": "manifest_sample_mismatch"})


def test_judge_category_table_matches_the_tally_categories() -> None:
    lines = JUDGE_DOC.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("| `category` |"))
    names: list[str] = []
    for line in lines[start + 2 :]:
        match = re.match(r"\| `([a-z_]+)` \|", line)
        if not match:
            break
        names.append(match.group(1))
    assert len(names) == len(set(names))
    assert set(names) == set(replies_tally.CATEGORIES)


@pytest.mark.parametrize("bad", ["t" * 41, "bad type"])
def test_unbounded_agent_type_and_entrypoint_never_reach_stdout(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], bad: str
) -> None:
    assert replies_corpus.AGENT_TYPE.fullmatch(bad) is None
    recs = [user("synthetic prompt wording lambda", 1, entrypoint=bad), assistant_text("ok", 2)]
    write_session(store, "main-a", recs)
    child = [user("synthetic child brief wording", 20, isSidechain=True), assistant_text("hi", 21)]
    write_child(store, "main-a", "agent-one", child, meta=bad)
    plant_control(store)
    payload, out = prepare_ok(capsys, store, tmp_path / "run")
    assert bad not in out
    assert payload["population"]["entrypoints"].get("unknown", 0) >= 1
    assert payload["subagent_meta"] == {"unnamed": 1}
