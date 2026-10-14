"""Tests for the ``/build`` documentation-impact record handoff (issue #5398).

``/build`` runs ``doc_accuracy_trigger.py`` once, saves its JSON as the
documentation-impact record, and hands the path to ``/test`` Gate 5. Gate 5
passes the path back through ``--build-record`` so an effect verified at build
time is never dropped and a build-time activation is never silently skipped.
These tests drive the real script, and the round trip feeds the script its own
output instead of a hand-written record.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/test/scripts/doc_accuracy_trigger.py",
    module_name="test_doc_accuracy_build_record_mod",
)

BASE = "origin/main"
CODE_ONLY = ["src/filters.py"]


@pytest.fixture(scope="module")
def classifier():
    return mod.load_classifier()


def _record(tmp_path: Path, payload: object, name: str = "record.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_decision_echoes_the_verified_effects(classifier) -> None:
    result = mod.decide(CODE_ONLY, ["Quantitative-Claim", "quantitative-claim"], BASE, classifier)
    assert result["effects"] == ["quantitative-claim"]


def test_decision_with_no_effects_echoes_an_empty_list(classifier) -> None:
    assert mod.decide(CODE_ONLY, [], BASE, classifier)["effects"] == []


def test_decision_without_a_record_reports_none(classifier) -> None:
    assert mod.decide(CODE_ONLY, [], BASE, classifier)["build_record"] is None


def test_effect_recorded_at_build_time_survives_into_gate5(classifier) -> None:
    """AC: a code-only diff skips alone but activates once the record carries the effect."""
    record = {"decision": "activate", "effects": ["quantitative-claim"], "reason": "r"}
    assert mod.decide(CODE_ONLY, [], BASE, classifier)["decision"] == "skip"
    result = mod.decide(CODE_ONLY, [], BASE, classifier, record)
    assert result["decision"] == "activate"
    assert result["effects"] == ["quantitative-claim"]
    assert result["behavioral_escalation"] == "required"
    assert result["build_record"] == {"decision": "activate", "effects": ["quantitative-claim"]}


def test_build_time_activation_is_never_skipped_by_gate5(classifier) -> None:
    """AC: the build signal is monotone, so Gate 5 cannot skip what build activated."""
    record = {"decision": "activate", "effects": [], "reason": "changed document"}
    result = mod.decide(["tests/test_a.py"], [], BASE, classifier, record)
    assert result["decision"] == "activate"
    assert any(cause.startswith("build record:") for cause in result["activation_causes"])


def test_build_record_that_skipped_adds_no_activation(classifier) -> None:
    record = {"decision": "skip", "effects": [], "reason": "tests only"}
    result = mod.decide(["tests/test_a.py"], [], BASE, classifier, record)
    assert result["decision"] == "skip"
    assert result["build_record"] == {"decision": "skip", "effects": []}


def test_record_effects_merge_with_cli_effects_without_duplicates(classifier) -> None:
    record = {"decision": "activate", "effects": ["public-api"], "reason": "r"}
    result = mod.decide(CODE_ONLY, ["public-api", "cli-surface"], BASE, classifier, record)
    assert result["effects"] == ["public-api", "cli-surface"]


def test_unknown_effect_in_the_record_fails_closed(classifier) -> None:
    record = {"decision": "skip", "effects": ["mystery"], "reason": "r"}
    result = mod.decide(["tests/test_a.py"], [], BASE, classifier, record)
    assert result["decision"] == "activate"
    assert result["unknown_effects"] == ["mystery"]


def test_load_build_record_reads_a_valid_record(tmp_path: Path) -> None:
    path = _record(tmp_path, {"decision": "skip", "effects": [], "reason": "tests only"})
    assert mod.load_build_record(path)["decision"] == "skip"


def test_load_build_record_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot read build record"):
        mod.load_build_record(tmp_path / "absent.json")


def test_load_build_record_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read build record"):
        mod.load_build_record(path)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param([], id="not-an-object"),
        pytest.param({"effects": []}, id="no-decision"),
        pytest.param({"decision": "maybe", "effects": []}, id="unknown-decision"),
        pytest.param({"decision": "skip"}, id="no-effects"),
        pytest.param({"decision": "skip", "effects": "public-api"}, id="effects-not-a-list"),
        pytest.param({"decision": "skip", "effects": [1]}, id="effect-not-a-string"),
    ],
)
def test_load_build_record_rejects_a_malformed_record(tmp_path: Path, payload: object) -> None:
    with pytest.raises(ValueError, match="build record"):
        mod.load_build_record(_record(tmp_path, payload))


def test_main_returns_2_on_an_unreadable_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = mod.main(
        ["--diff-base", BASE, "--changed-path", "README.md", "--build-record", str(tmp_path / "x")]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "doc_accuracy_trigger: cannot read build record" in captured.err


def test_round_trip_build_output_feeds_gate5(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The record is the script's own /build output, not a hand-written shape."""
    build_args = ["--diff-base", BASE, "--changed-path", "src/filters.py"]
    assert mod.main([*build_args, "--effect", "quantitative-claim"]) == 0
    saved = tmp_path / "doc-impact.json"
    saved.write_text(capsys.readouterr().out, encoding="utf-8")

    assert mod.main([*build_args, "--build-record", str(saved)]) == 0
    gate5 = json.loads(capsys.readouterr().out)
    assert gate5["decision"] == "activate"
    assert gate5["effects"] == ["quantitative-claim"]
    assert gate5["build_record"]["decision"] == "activate"


def test_round_trip_build_skip_keeps_gate5_skipping(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_args = ["--diff-base", BASE, "--changed-path", "tests/test_a.py"]
    assert mod.main(build_args) == 0
    saved = tmp_path / "doc-impact.json"
    saved.write_text(capsys.readouterr().out, encoding="utf-8")

    assert mod.main([*build_args, "--build-record", str(saved)]) == 0
    gate5 = json.loads(capsys.readouterr().out)
    assert gate5["decision"] == "skip"
    assert gate5["build_record"] == {"decision": "skip", "effects": []}


def test_negative_control_stale_count_escapes_without_the_record(classifier) -> None:
    """Issue fixture 8 at trigger level: dropping the handoff lets a stale count escape.

    A code-only diff that changes a documented count carries no effect on its
    own, so Gate 5 skips. With the build-time record the same paths activate.
    """
    record = {"decision": "activate", "effects": ["quantitative-claim"], "reason": "count"}
    escaped = mod.decide(CODE_ONLY, [], BASE, classifier)
    caught = mod.decide(CODE_ONLY, [], BASE, classifier, record)
    assert escaped["decision"] == "skip"
    assert caught["decision"] == "activate"
