"""Tests for scripts/eval/eval-skill-overlap.py (Issue #1932).

The module under test has a hyphenated filename, so it is loaded by path and
registered in sys.modules. All tests mock at the API boundary (the injected
respond/judge callables or the _anthropic_api functions) and make ZERO real
Anthropic API calls.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the hyphenated module by path. scripts/eval must be on sys.path so the
# module's `from _anthropic_api import ...` and `from _eval_common import ...`
# resolve.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

_SPEC = importlib.util.spec_from_file_location(
    "eval_skill_overlap", _EVAL_DIR / "eval-skill-overlap.py"
)
assert _SPEC is not None and _SPEC.loader is not None
eso = importlib.util.module_from_spec(_SPEC)
sys.modules["eval_skill_overlap"] = eso
_SPEC.loader.exec_module(eso)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


def _make_skill_dir(root: Path, name: str, body: str = "skill body") -> Path:
    """Create a minimal skill directory with a SKILL.md."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"# {name}\n\n{body}\n", encoding="utf-8")
    return skill_dir


# ===========================================================================
# classify_overlap (positive: each verdict)
# ===========================================================================


def test_classify_returns_distinct_when_neither_skill_covers_the_other():
    # Arrange: each skill helps on its own prompts; cross help is near zero.
    a_on_a = eso.DirectionScores(baseline=2.0, own=4.0, other=2.1)
    b_on_b = eso.DirectionScores(baseline=2.0, own=4.0, other=2.0)

    # Act
    verdict = eso.classify_overlap(a_on_a, b_on_b)

    # Assert
    assert verdict == "DISTINCT"


def test_classify_returns_overlap_when_both_cover_each_other():
    # Arrange: symmetric cross-prompt parity; each skill helps the other set
    # about as much as the owner does.
    a_on_a = eso.DirectionScores(baseline=2.0, own=4.0, other=3.8)
    b_on_b = eso.DirectionScores(baseline=2.0, own=4.0, other=3.9)

    # Act
    verdict = eso.classify_overlap(a_on_a, b_on_b)

    # Assert
    assert verdict == "OVERLAP"


def test_classify_returns_subsumed_when_only_one_direction_covers():
    # Arrange: B covers A's prompts, A does not cover B's prompts.
    a_on_a = eso.DirectionScores(baseline=2.0, own=4.0, other=3.9)
    b_on_b = eso.DirectionScores(baseline=2.0, own=4.0, other=2.1)

    # Act
    verdict = eso.classify_overlap(a_on_a, b_on_b)

    # Assert
    assert verdict == "SUBSUMED"


def test_classify_subsumed_when_other_skill_beats_owner():
    # Arrange: B helps A's prompts MORE than A helps them, A helps B's none.
    # _covers must hold when other_delta exceeds own_delta.
    a_on_a = eso.DirectionScores(baseline=2.0, own=3.0, other=4.5)
    b_on_b = eso.DirectionScores(baseline=2.0, own=4.0, other=2.0)

    # Act
    verdict = eso.classify_overlap(a_on_a, b_on_b)

    # Assert
    assert verdict == "SUBSUMED"


# ===========================================================================
# DirectionScores deltas (edge)
# ===========================================================================


def test_direction_scores_zero_delta_when_skill_does_not_beat_baseline():
    # Arrange: own equals baseline.
    scores = eso.DirectionScores(baseline=3.0, own=3.0, other=3.0)

    # Act / Assert
    assert scores.own_delta == 0.0
    assert scores.other_delta == 0.0


def test_classify_distinct_when_all_scores_identical():
    # Arrange: zero deltas everywhere (no skill helps at all).
    flat = eso.DirectionScores(baseline=3.0, own=3.0, other=3.0)

    # Act
    verdict = eso.classify_overlap(flat, flat)

    # Assert: no coverage anywhere, so DISTINCT (keep both, neither earns).
    assert verdict == "DISTINCT"


# ===========================================================================
# recommend_action (positive: table-driven mapping)
# ===========================================================================


@pytest.mark.parametrize(
    "verdict,needle",
    [
        ("DISTINCT", "Keep both"),
        ("OVERLAP", "Fold candidate"),
        ("SUBSUMED", "Prune candidate"),
    ],
)
def test_recommend_action_maps_each_verdict(verdict, needle):
    # Act
    text = eso.recommend_action(verdict, "alpha", "beta")

    # Assert
    assert needle in text
    assert "alpha" in text and "beta" in text


# ===========================================================================
# estimate_cost (positive + edge)
# ===========================================================================


def test_estimate_cost_counts_calls_across_both_prompt_sets():
    # Arrange: 2 prompts for A, 2 for B => 4 prompts * 6 calls = 24.
    pairs = [("a", "b")]
    prompts = {
        "a": [{"prompt": "p1", "expected": "e1"}, {"prompt": "p2", "expected": "e2"}],
        "b": [{"prompt": "p3", "expected": "e3"}, {"prompt": "p4", "expected": "e4"}],
    }

    # Act
    cost = eso.estimate_cost(pairs, prompts)

    # Assert
    assert cost.api_calls == 24
    assert cost.est_tokens == 24 * eso.EST_TOKENS_PER_CALL
    assert cost.usd_estimate > 0
    assert "USD" in cost.render()


def test_estimate_cost_zero_for_empty_prompt_sets():
    # Arrange: a pair whose skills have no prompts (degenerate edge).
    pairs = [("a", "b")]

    # Act
    cost = eso.estimate_cost(pairs, {})

    # Assert
    assert cost.api_calls == 0
    assert cost.est_tokens == 0


# ===========================================================================
# load_pairs_file (positive)
# ===========================================================================


def _valid_pairs_payload() -> dict:
    return {
        "pairs": [["a", "b"]],
        "prompts": {
            "a": [{"prompt": "pa", "expected": "ea"}],
            "b": [{"prompt": "pb", "expected": "eb"}],
        },
    }


def test_load_pairs_file_parses_valid_cluster_json(tmp_path):
    # Arrange
    f = tmp_path / "cluster.json"
    f.write_text(json.dumps(_valid_pairs_payload()), encoding="utf-8")

    # Act
    config = eso.load_pairs_file(str(f))

    # Assert
    assert config.pairs == [("a", "b")]
    assert "a" in config.prompts and "b" in config.prompts


# ===========================================================================
# load_pairs_file (negative: each maps to a config error / exit 2)
# ===========================================================================


def test_load_pairs_file_raises_on_missing_file(tmp_path):
    # Act / Assert
    with pytest.raises(eso.PairsFileError, match="not found"):
        eso.load_pairs_file(str(tmp_path / "nope.json"))


def test_load_pairs_file_raises_on_malformed_json(tmp_path):
    # Arrange
    f = tmp_path / "bad.json"
    f.write_text("{not valid json", encoding="utf-8")

    # Act / Assert
    with pytest.raises(eso.PairsFileError, match="not valid JSON"):
        eso.load_pairs_file(str(f))


def test_load_pairs_file_raises_when_pairs_missing(tmp_path):
    # Arrange
    f = tmp_path / "c.json"
    payload = {"prompts": {"a": [{"prompt": "p", "expected": "e"}]}}
    f.write_text(json.dumps(payload), encoding="utf-8")

    # Act / Assert
    with pytest.raises(eso.PairsFileError, match="non-empty list"):
        eso.load_pairs_file(str(f))


def test_load_pairs_file_raises_on_wrong_pair_arity(tmp_path):
    # Arrange: a triple instead of a pair.
    payload = _valid_pairs_payload()
    payload["pairs"] = [["a", "b", "c"]]
    f = tmp_path / "c.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    # Act / Assert
    with pytest.raises(eso.PairsFileError, match="two"):
        eso.load_pairs_file(str(f))


def test_load_pairs_file_raises_when_prompt_missing_expected(tmp_path):
    # Arrange: a prompt entry without an 'expected' key.
    payload = _valid_pairs_payload()
    payload["prompts"]["a"] = [{"prompt": "pa"}]
    f = tmp_path / "c.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    # Act / Assert
    with pytest.raises(eso.PairsFileError, match="expected"):
        eso.load_pairs_file(str(f))


def test_load_pairs_file_raises_when_pair_has_no_prompts(tmp_path):
    # Arrange: pair references skill 'b' but prompts only define 'a'.
    payload = {
        "pairs": [["a", "b"]],
        "prompts": {"a": [{"prompt": "pa", "expected": "ea"}]},
    }
    f = tmp_path / "c.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    # Act / Assert
    with pytest.raises(eso.PairsFileError, match="no prompts provided for skill 'b'"):
        eso.load_pairs_file(str(f))


# ===========================================================================
# require_skill_dir (negative: missing skill -> logic error / exit 1)
# ===========================================================================


def test_require_skill_dir_raises_for_deleted_skill(tmp_path):
    # Arrange: an empty skills root; the named skill does not exist.
    # This is the deleted-skill case from the Issue #1932 Phase 1 pairs.

    # Act / Assert
    with pytest.raises(eso.MissingSkillError, match="not found"):
        eso.require_skill_dir("doc-coverage", skills_dir=tmp_path)


def test_require_skill_dir_rejects_path_traversal(tmp_path):
    # Arrange / Act / Assert: a name with a slash must not escape the root.
    with pytest.raises(eso.MissingSkillError):
        eso.require_skill_dir("../secrets", skills_dir=tmp_path)


def test_require_skill_dir_returns_dir_when_present(tmp_path):
    # Arrange
    _make_skill_dir(tmp_path, "real-skill")

    # Act
    resolved = eso.require_skill_dir("real-skill", skills_dir=tmp_path)

    # Assert
    assert resolved.name == "real-skill"


# ===========================================================================
# evaluate_pair (positive + API error path) with mocked respond/judge
# ===========================================================================


def test_evaluate_pair_classifies_distinct_with_mocked_scoring(tmp_path):
    # Arrange: two real skill dirs; judge returns high score only when the
    # owning skill's context is present, near-baseline otherwise.
    _make_skill_dir(tmp_path, "alpha", body="ALPHA")
    _make_skill_dir(tmp_path, "beta", body="BETA")
    prompts = {
        "alpha": [{"prompt": "qa", "expected": "ea"}],
        "beta": [{"prompt": "qb", "expected": "eb"}],
    }

    def respond(prompt: str, system_context: str) -> str:
        if "ALPHA" in system_context and prompt == "qa":
            return "alpha-good"
        if "BETA" in system_context and prompt == "qb":
            return "beta-good"
        return "weak"

    def judge(prompt: str, response: str, expected: str) -> float:
        return 5.0 if response.endswith("-good") else 2.0

    # Act
    result = eso.evaluate_pair(
        "alpha", "beta", prompts, respond=respond, judge=judge, skills_dir=tmp_path
    )

    # Assert: each skill helps only on its own prompt, neither covers the other.
    assert result.verdict == "DISTINCT"
    assert result.a_on_a.own == 5.0
    assert result.a_on_a.other == 2.0
    assert result.api_calls == 12  # 2 prompts * 6 calls


def test_evaluate_pair_classifies_overlap_when_both_contexts_help_both(tmp_path):
    # Arrange: any non-empty skill context yields a high score on any prompt.
    _make_skill_dir(tmp_path, "alpha")
    _make_skill_dir(tmp_path, "beta")
    prompts = {
        "alpha": [{"prompt": "qa", "expected": "ea"}],
        "beta": [{"prompt": "qb", "expected": "eb"}],
    }

    def respond(prompt: str, system_context: str) -> str:
        return "enhanced" if system_context else "baseline"

    def judge(prompt: str, response: str, expected: str) -> float:
        return 5.0 if response == "enhanced" else 2.0

    # Act
    result = eso.evaluate_pair(
        "alpha", "beta", prompts, respond=respond, judge=judge, skills_dir=tmp_path
    )

    # Assert
    assert result.verdict == "OVERLAP"


def test_evaluate_pair_propagates_missing_skill(tmp_path):
    # Arrange: only 'alpha' exists; 'beta' was deleted.
    _make_skill_dir(tmp_path, "alpha")
    prompts = {
        "alpha": [{"prompt": "qa", "expected": "ea"}],
        "beta": [{"prompt": "qb", "expected": "eb"}],
    }

    def respond(prompt: str, system_context: str) -> str:
        return "x"

    def judge(prompt: str, response: str, expected: str) -> float:
        return 3.0

    # Act / Assert
    with pytest.raises(eso.MissingSkillError):
        eso.evaluate_pair(
            "alpha", "beta", prompts, respond=respond, judge=judge, skills_dir=tmp_path
        )


def test_evaluate_pair_single_prompt_edge(tmp_path):
    # Arrange: prompt sets of length 1 each (edge: minimal input).
    _make_skill_dir(tmp_path, "alpha")
    _make_skill_dir(tmp_path, "beta")
    prompts = {
        "alpha": [{"prompt": "qa", "expected": "ea"}],
        "beta": [{"prompt": "qb", "expected": "eb"}],
    }

    def respond(prompt: str, system_context: str) -> str:
        return "r"

    def judge(prompt: str, response: str, expected: str) -> float:
        return 3.0  # identical scores everywhere

    # Act
    result = eso.evaluate_pair(
        "alpha", "beta", prompts, respond=respond, judge=judge, skills_dir=tmp_path
    )

    # Assert: identical scores -> zero deltas -> DISTINCT.
    assert result.verdict == "DISTINCT"
    assert result.a_on_a.own_delta == 0.0


# ===========================================================================
# Judge parsing (edge)
# ===========================================================================


def test_parse_judge_score_extracts_from_code_fence():
    # Arrange
    raw = '```json\n{"score": 4}\n```'

    # Act / Assert
    assert eso._parse_judge_score(raw) == 4.0


def test_parse_judge_score_returns_zero_on_garbage():
    # Act / Assert
    assert eso._parse_judge_score("not json at all") == 0.0


# ===========================================================================
# Report writers (positive)
# ===========================================================================


def _sample_result(verdict: str = "OVERLAP"):
    return eso.PairResult(
        skill_a="alpha",
        skill_b="beta",
        a_on_a=eso.DirectionScores(baseline=2.0, own=4.0, other=3.8),
        b_on_b=eso.DirectionScores(baseline=2.0, own=4.0, other=3.9),
        verdict=verdict,
        recommendation=eso.recommend_action(verdict, "alpha", "beta"),
        api_calls=12,
    )


def test_build_matrix_includes_pair_and_deltas():
    # Act
    matrix = eso.build_matrix([_sample_result()], model="m", run_id="rid")

    # Assert
    assert matrix["run_id"] == "rid"
    assert matrix["model"] == "m"
    assert matrix["pairs"][0]["verdict"] == "OVERLAP"
    assert matrix["pairs"][0]["a_on_a"]["own_delta"] == 2.0


def test_build_report_md_renders_prune_fold_table():
    # Act
    md = eso.build_report_md([_sample_result()], model="m", run_id="rid")

    # Assert
    assert "Prune / Fold Table" in md
    assert "| alpha | beta | OVERLAP |" in md
    assert "Per-Pair Detail" in md


def test_write_reports_produces_matrix_and_report(tmp_path):
    # Act
    out_dir = eso.write_reports(
        [_sample_result()], model="m", run_id="rid", reports_dir=tmp_path
    )

    # Assert
    assert (out_dir / "matrix.json").is_file()
    assert (out_dir / "REPORT.md").is_file()
    parsed = json.loads((out_dir / "matrix.json").read_text(encoding="utf-8"))
    assert parsed["pairs"][0]["skill_a"] == "alpha"


def test_write_reports_is_idempotent_on_same_run_id(tmp_path):
    # Arrange: write once.
    eso.write_reports([_sample_result("DISTINCT")], model="m", run_id="rid", reports_dir=tmp_path)

    # Act: write again with the same run id but a different verdict.
    out_dir = eso.write_reports(
        [_sample_result("OVERLAP")], model="m", run_id="rid", reports_dir=tmp_path
    )

    # Assert: the second write wins; no duplicate directory.
    parsed = json.loads((out_dir / "matrix.json").read_text(encoding="utf-8"))
    assert parsed["pairs"][0]["verdict"] == "OVERLAP"
    overlap_dirs = list(tmp_path.glob("overlap-*"))
    assert len(overlap_dirs) == 1


# ===========================================================================
# CLI run() exit codes (ADR-035) with mocked boundaries
# ===========================================================================


def _write_valid_cluster(tmp_path: Path) -> Path:
    f = tmp_path / "cluster.json"
    f.write_text(json.dumps(_valid_pairs_payload()), encoding="utf-8")
    return f


def test_run_dry_run_exits_ok_without_api_calls(tmp_path, monkeypatch, capsys):
    # Arrange: guard against any real API key load during dry run.
    def _boom():
        raise AssertionError("dry run must not load the API key")

    monkeypatch.setattr(eso, "_load_api_key", _boom)
    cluster = _write_valid_cluster(tmp_path)
    args = eso.build_parser().parse_args(["--pairs", str(cluster), "--dry-run"])

    # Act
    code = eso.run(args)

    # Assert
    assert code == eso.EXIT_OK
    assert "Cost estimate" in capsys.readouterr().err


def test_run_returns_config_exit_on_bad_pairs_file(tmp_path):
    # Arrange
    f = tmp_path / "bad.json"
    f.write_text("not json", encoding="utf-8")
    args = eso.build_parser().parse_args(["--pairs", str(f), "--dry-run"])

    # Act
    code = eso.run(args)

    # Assert
    assert code == eso.EXIT_CONFIG


def test_run_returns_logic_exit_when_skill_dir_missing(tmp_path, monkeypatch):
    # Arrange: valid cluster, but skills resolve against an empty dir, so the
    # pair references skills that do not exist -> logic error (exit 1).
    cluster = _write_valid_cluster(tmp_path)
    empty_skills = tmp_path / "skills_root"
    empty_skills.mkdir()
    monkeypatch.setattr(eso, "SKILLS_DIR", empty_skills)
    monkeypatch.setattr(eso, "_load_api_key", lambda: "fake-key")
    monkeypatch.setattr(eso, "make_response_fn", lambda key, model: (lambda p, c: "r"))
    monkeypatch.setattr(eso, "make_judge_fn", lambda key, model: (lambda p, r, e: 3.0))
    args = eso.build_parser().parse_args(["--pairs", str(cluster)])

    # Act
    code = eso.run(args)

    # Assert
    assert code == eso.EXIT_LOGIC


def test_run_returns_external_exit_on_api_failure(tmp_path, monkeypatch):
    # Arrange: real skill dirs so resolution passes, but the response fn raises
    # a RuntimeError mimicking an Anthropic API failure.
    skills_root = tmp_path / "skills_root"
    skills_root.mkdir()
    _make_skill_dir(skills_root, "a")
    _make_skill_dir(skills_root, "b")
    cluster = _write_valid_cluster(tmp_path)

    def _failing_respond(prompt: str, context: str) -> str:
        raise RuntimeError("Anthropic API returned HTTP 503")

    monkeypatch.setattr(eso, "SKILLS_DIR", skills_root)
    monkeypatch.setattr(eso, "_load_api_key", lambda: "fake-key")
    monkeypatch.setattr(eso, "make_response_fn", lambda key, model: _failing_respond)
    monkeypatch.setattr(eso, "make_judge_fn", lambda key, model: (lambda p, r, e: 3.0))
    args = eso.build_parser().parse_args(["--pairs", str(cluster)])

    # Act
    code = eso.run(args)

    # Assert
    assert code == eso.EXIT_EXTERNAL


def test_run_returns_external_exit_when_api_key_missing(tmp_path, monkeypatch):
    # Arrange: live run, but the key load fails.
    cluster = _write_valid_cluster(tmp_path)

    def _no_key():
        raise RuntimeError("ANTHROPIC_API_KEY not found")

    monkeypatch.setattr(eso, "_load_api_key", _no_key)
    args = eso.build_parser().parse_args(["--pairs", str(cluster)])

    # Act
    code = eso.run(args)

    # Assert
    assert code == eso.EXIT_EXTERNAL


def test_run_full_live_path_writes_report(tmp_path, monkeypatch):
    # Arrange: full happy path with all boundaries mocked; verifies the report
    # lands and the run id is honored. Zero real API calls.
    skills_root = tmp_path / "skills_root"
    skills_root.mkdir()
    _make_skill_dir(skills_root, "a")
    _make_skill_dir(skills_root, "b")
    reports_root = tmp_path / "reports"
    cluster = _write_valid_cluster(tmp_path)

    def respond(prompt, context):
        return "enhanced" if context else "base"

    def judge(prompt, response, expected):
        return 5.0 if response == "enhanced" else 2.0

    monkeypatch.setattr(eso, "SKILLS_DIR", skills_root)
    monkeypatch.setattr(eso, "REPORTS_DIR", reports_root)
    monkeypatch.setattr(eso, "_load_api_key", lambda: "fake-key")
    monkeypatch.setattr(eso, "make_response_fn", lambda key, model: respond)
    monkeypatch.setattr(eso, "make_judge_fn", lambda key, model: judge)
    monkeypatch.setattr(eso.time, "sleep", lambda _s: None)
    args = eso.build_parser().parse_args(["--pairs", str(cluster), "--run-id", "testrun"])

    # Act
    code = eso.run(args)

    # Assert
    assert code == eso.EXIT_OK
    assert (reports_root / "overlap-testrun" / "matrix.json").is_file()


# ===========================================================================
# main() argv wiring (positive)
# ===========================================================================


def test_main_dry_run_returns_zero(tmp_path, monkeypatch):
    # Arrange: dry run must never load the API key.
    def _no_key():
        raise AssertionError("no key in dry run")

    monkeypatch.setattr(eso, "_load_api_key", _no_key)
    cluster = _write_valid_cluster(tmp_path)

    # Act
    code = eso.main(["--pairs", str(cluster), "--dry-run"])

    # Assert
    assert code == eso.EXIT_OK


def test_main_requires_pairs_argument():
    # Act / Assert: argparse exits with code 2 when --pairs is omitted.
    with pytest.raises(SystemExit) as excinfo:
        eso.main([])
    assert excinfo.value.code == 2
