"""Regression tests for the retirement-claim verdict guard (Issue #2676).

A skill-overlap follow-up generator emitted a SUBSUMED retirement claim for the
`curating-memories` x `memory-enhancement` pair, which the cited report scored
DISTINCT. That inversion created the bogus issue #2663 and PR #2671. The guard
in scripts/eval/eval-skill-overlap.py validates a claimed verdict word against
the machine-readable report (matrix.json) before the claim is emitted.

The canonical DISTINCT verdict for that pair lives in
evals/reports/overlap-m4-overlap-1949-2026-06-17/matrix.json:
    {"skill_a": "curating-memories", "skill_b": "memory-enhancement",
     "verdict": "DISTINCT", ...}

All tests mock at no boundary: the guard is pure and reads a report payload or
path. No Anthropic API calls are made.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the hyphenated module by path (mirrors tests/test_eval_skill_overlap.py).
# scripts/eval must be on sys.path so the module's `from _anthropic_api import`
# and `from _eval_common import` resolve.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
_path_added = str(_EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(_EVAL_DIR))

try:
    _SPEC = importlib.util.spec_from_file_location(
        "eval_skill_overlap", _EVAL_DIR / "eval-skill-overlap.py"
    )
    assert _SPEC is not None and _SPEC.loader is not None
    eso = importlib.util.module_from_spec(_SPEC)
    sys.modules["eval_skill_overlap"] = eso
    _SPEC.loader.exec_module(eso)
finally:
    if _path_added and str(_EVAL_DIR) in sys.path:
        sys.path.remove(str(_EVAL_DIR))


# ---------------------------------------------------------------------------
# Report fixtures
# ---------------------------------------------------------------------------

# Reproduction of the run m4-overlap-1949-2026-06-17 report. The first pair is
# the DISTINCT case that the bogus generator inverted; the second is a genuine
# SUBSUMED pair used as the negative control.
_M4_REPORT: dict[str, object] = {
    "run_id": "m4-overlap-1949-2026-06-17",
    "model": "claude-sonnet-4-6",
    "pairs": [
        {
            "skill_a": "curating-memories",
            "skill_b": "memory-enhancement",
            "verdict": "DISTINCT",
            "recommendation": (
                "Keep both. curating-memories and memory-enhancement cover "
                "different prompts."
            ),
        },
        {
            "skill_a": "exploring-knowledge-graph",
            "skill_b": "memory",
            "verdict": "SUBSUMED",
            "recommendation": "Prune candidate. memory covers exploring-knowledge-graph.",
        },
    ],
}


def _write_report_dir(tmp_path: Path, payload: dict[str, object]) -> Path:
    """Write payload as matrix.json under a report directory and return the dir."""
    out_dir = tmp_path / "overlap-m4-overlap-1949-2026-06-17"
    out_dir.mkdir(parents=True)
    (out_dir / "matrix.json").write_text(json.dumps(payload), encoding="utf-8")
    return out_dir


# ===========================================================================
# DISTINCT case: the SUBSUMED retirement claim MUST be dropped (Issue #2676)
# ===========================================================================


def test_emit_drops_subsumed_claim_when_report_says_distinct():
    # Arrange: the cited report scored the pair DISTINCT (m4 run).
    stream = io.StringIO()

    # Act: a generator tries to emit a SUBSUMED retirement claim for the pair.
    result = eso.emit_retirement_claim(
        "curating-memories",
        "memory-enhancement",
        "SUBSUMED",
        "Prune candidate. memory-enhancement covers curating-memories.",
        _M4_REPORT,
        stream=stream,
    )

    # Assert: the claim is dropped and the skip is logged with both verdicts.
    assert result is None
    logged = stream.getvalue()
    assert "SKIP retirement claim" in logged
    assert "DISTINCT" in logged


def test_emit_drops_subsumed_claim_for_distinct_pair_from_report_directory(tmp_path):
    # Arrange: cite the report by its on-disk directory, not the in-memory dict.
    report_dir = _write_report_dir(tmp_path, _M4_REPORT)

    # Act
    result = eso.emit_retirement_claim(
        "curating-memories",
        "memory-enhancement",
        "SUBSUMED",
        "Prune candidate.",
        report_dir,
    )

    # Assert
    assert result is None


def test_validate_returns_false_for_distinct_pair():
    # Arrange / Act
    backed = eso.validate_retirement_claim(
        "curating-memories", "memory-enhancement", "SUBSUMED", _M4_REPORT
    )

    # Assert: a DISTINCT report verdict never backs a SUBSUMED claim.
    assert backed is False


def test_validate_returns_false_when_report_is_missing(tmp_path):
    backed = eso.validate_retirement_claim(
        "curating-memories",
        "memory-enhancement",
        "SUBSUMED",
        tmp_path / "missing-report",
    )

    assert backed is False


def test_validate_returns_false_when_pair_is_absent():
    backed = eso.validate_retirement_claim(
        "curating-memories",
        "memory-enhancement",
        "SUBSUMED",
        {"pairs": []},
    )

    assert backed is False


# ===========================================================================
# Negative control: a genuine SUBSUMED pair still emits the retirement claim
# ===========================================================================


def test_emit_keeps_subsumed_claim_when_report_agrees():
    # Arrange: the report scored this pair SUBSUMED.
    recommendation = "Prune candidate. memory covers exploring-knowledge-graph."

    # Act
    result = eso.emit_retirement_claim(
        "exploring-knowledge-graph",
        "memory",
        "SUBSUMED",
        recommendation,
        _M4_REPORT,
    )

    # Assert: a backed retirement claim is emitted unchanged.
    assert result == recommendation


def test_validate_returns_true_when_subsumed_claim_matches_report():
    # Arrange / Act
    backed = eso.validate_retirement_claim(
        "exploring-knowledge-graph", "memory", "SUBSUMED", _M4_REPORT
    )

    # Assert
    assert backed is True


def test_emit_is_order_independent_for_pair_lookup():
    # Arrange: cite the SUBSUMED pair in the reversed (b, a) order.
    # Act
    result = eso.emit_retirement_claim(
        "memory",
        "exploring-knowledge-graph",
        "SUBSUMED",
        "Prune candidate.",
        _M4_REPORT,
    )

    # Assert: the verdict lookup ignores pair order.
    assert result == "Prune candidate."


# ===========================================================================
# Verdict-word classification (positive + negative + edge)
# ===========================================================================


def test_is_retirement_verdict_true_for_subsumed_and_overlap():
    assert eso.is_retirement_verdict("SUBSUMED") is True
    assert eso.is_retirement_verdict("OVERLAP") is True


def test_is_retirement_verdict_false_for_distinct():
    assert eso.is_retirement_verdict("DISTINCT") is False


def test_is_retirement_verdict_false_for_unknown_word():
    # Edge: an unrecognized verdict word never authorizes retirement.
    assert eso.is_retirement_verdict("MAYBE") is False
    assert eso.is_retirement_verdict("") is False


def test_emit_drops_non_retirement_verdict_even_when_report_agrees():
    # Edge: DISTINCT is the report verdict AND the claimed verdict, but DISTINCT
    # is not a retirement verdict, so no retirement claim is emitted.
    result = eso.emit_retirement_claim(
        "curating-memories",
        "memory-enhancement",
        "DISTINCT",
        "Keep both.",
        _M4_REPORT,
        stream=io.StringIO(),
    )
    assert result is None


# ===========================================================================
# report_verdict_for_pair / load_report_verdicts (lookup + error paths)
# ===========================================================================


def test_report_verdict_for_pair_returns_report_word():
    verdict = eso.report_verdict_for_pair(
        _M4_REPORT, "curating-memories", "memory-enhancement"
    )
    assert verdict == "DISTINCT"


def test_report_verdict_for_pair_raises_when_pair_absent():
    # Negative: a pair the report never scored cannot back any claim.
    with pytest.raises(eso.ReportVerdictError):
        eso.report_verdict_for_pair(_M4_REPORT, "skill-x", "skill-y")


def test_load_report_verdicts_maps_each_pair():
    verdicts = eso.load_report_verdicts(_M4_REPORT)
    assert verdicts[frozenset({"curating-memories", "memory-enhancement"})] == "DISTINCT"
    assert verdicts[frozenset({"exploring-knowledge-graph", "memory"})] == "SUBSUMED"


def test_load_report_verdicts_treats_explicit_null_pairs_as_empty():
    assert eso.load_report_verdicts({"pairs": None}) == {}


def test_load_report_verdicts_raises_when_pairs_is_not_a_list():
    with pytest.raises(eso.ReportVerdictError):
        eso.load_report_verdicts({"pairs": {}})


def test_load_report_verdicts_raises_on_malformed_pair():
    # Negative: a pair entry missing the verdict field is malformed input.
    bad = {"pairs": [{"skill_a": "a", "skill_b": "b"}]}
    with pytest.raises(eso.ReportVerdictError):
        eso.load_report_verdicts(bad)


# ===========================================================================
# _coerce_report_payload (boundary: dict, file, dir, bad input)
# ===========================================================================


def test_coerce_reads_matrix_json_from_directory(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(eso, "REPO_ROOT", tmp_path)
    report_dir = _write_report_dir(tmp_path, _M4_REPORT)
    payload = eso._coerce_report_payload(report_dir)
    assert payload["run_id"] == "m4-overlap-1949-2026-06-17"


def test_coerce_reads_matrix_json_from_file_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(eso, "REPO_ROOT", tmp_path)
    report_dir = _write_report_dir(tmp_path, _M4_REPORT)
    payload = eso._coerce_report_payload(report_dir / "matrix.json")
    assert payload["pairs"][0]["verdict"] == "DISTINCT"


def test_coerce_raises_when_report_file_missing(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(eso, "REPO_ROOT", tmp_path)
    with pytest.raises(eso.ReportVerdictError):
        eso._coerce_report_payload(tmp_path / "overlap-missing")


def test_coerce_raises_when_report_path_escapes_repo(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(eso, "REPO_ROOT", repo_root)
    report = tmp_path / "matrix.json"
    report.write_text(json.dumps(_M4_REPORT), encoding="utf-8")

    with pytest.raises(eso.ReportVerdictError):
        eso._coerce_report_payload(report)


def test_coerce_raises_on_non_json_report(tmp_path):
    out_dir = tmp_path / "overlap-bad"
    out_dir.mkdir()
    (out_dir / "matrix.json").write_text("not json", encoding="utf-8")
    with pytest.raises(eso.ReportVerdictError):
        eso._coerce_report_payload(out_dir)


def test_coerce_raises_on_unsupported_reference_type():
    # Edge: an int is neither a payload dict nor a path.
    with pytest.raises(eso.ReportVerdictError):
        eso._coerce_report_payload(42)
