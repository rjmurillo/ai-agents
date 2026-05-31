"""Tests for scripts/eval/variance-control.py (issue #1877).

Covers the pure variance metrics, verdict extraction, and the rep-orchestration
loop with a fake adapter. No live API calls.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

_SCRIPT = _EVAL_DIR / "variance-control.py"
_spec = importlib.util.spec_from_file_location("variance_control", _SCRIPT)
assert _spec is not None and _spec.loader is not None
vc = importlib.util.module_from_spec(_spec)
sys.modules["variance_control"] = vc
_spec.loader.exec_module(vc)


# ---------------------------------------------------------------------------
# Verdict extraction
# ---------------------------------------------------------------------------


class TestExtractVerdict:
    def test_leading_identify(self):
        assert vc.extract_verdict("IDENTIFY the spoofing threat") == "IDENTIFY"

    def test_leading_escalate(self):
        assert vc.extract_verdict("ESCALATE: needs a human") == "ESCALATE"

    def test_empty_is_none(self):
        assert vc.extract_verdict("") is None

    def test_no_token_is_none(self):
        assert vc.extract_verdict("There is no verdict word at the start.") is None


# ---------------------------------------------------------------------------
# Levenshtein
# ---------------------------------------------------------------------------


class TestLevenshtein:
    def test_identical_is_zero(self):
        assert vc.levenshtein("abc", "abc") == 0

    def test_classic_kitten_sitting(self):
        assert vc.levenshtein("kitten", "sitting") == 3

    def test_empty_left(self):
        assert vc.levenshtein("", "abc") == 3

    def test_normalized_identical_is_zero(self):
        assert vc.normalized_levenshtein("abc", "abc") == 0.0

    def test_normalized_both_empty_is_zero(self):
        assert vc.normalized_levenshtein("", "") == 0.0

    def test_normalized_in_unit_interval(self):
        d = vc.normalized_levenshtein("abcd", "abxy")
        assert 0.0 < d <= 1.0


# ---------------------------------------------------------------------------
# Response-text variance
# ---------------------------------------------------------------------------


class TestResponseTextVariance:
    def test_all_identical(self):
        out = vc.response_text_variance(["same", "same", "same"])
        assert out["all_identical"] is True
        assert out["unique_count"] == 1
        assert out["max_consecutive_distance"] == 0.0

    def test_varied(self):
        out = vc.response_text_variance(["alpha", "beta", "gamma"])
        assert out["all_identical"] is False
        assert out["unique_count"] == 3
        assert out["mean_consecutive_distance"] > 0.0

    def test_single_response_has_no_consecutive_distance(self):
        out = vc.response_text_variance(["solo"])
        assert out["mean_consecutive_distance"] == 0.0
        assert out["all_identical"] is True


# ---------------------------------------------------------------------------
# Verdict distribution
# ---------------------------------------------------------------------------


class TestVerdictDistribution:
    def test_stable(self):
        out = vc.verdict_distribution(["IDENTIFY", "IDENTIFY", "IDENTIFY"])
        assert out["stable"] is True
        assert out["distinct_count"] == 1
        assert out["modal_verdict"] == "IDENTIFY"
        assert out["modal_count"] == 3

    def test_varied(self):
        out = vc.verdict_distribution(["IDENTIFY", "ESCALATE", "ESCALATE"])
        assert out["stable"] is False
        assert out["distinct_count"] == 2
        assert out["modal_verdict"] == "ESCALATE"
        assert out["modal_count"] == 2

    def test_none_counted_as_token(self):
        out = vc.verdict_distribution(["IDENTIFY", None])
        assert out["distribution"]["<none>"] == 1
        assert out["distinct_count"] == 2


# ---------------------------------------------------------------------------
# Pass-rate variance
# ---------------------------------------------------------------------------


class TestPassRateVariance:
    def test_all_pass(self):
        out = vc.pass_rate_variance(["IDENTIFY", "IDENTIFY"], "IDENTIFY")
        assert out["pass_rate"] == 1.0
        assert out["all_pass"] is True
        assert out["any_fail"] is False
        assert out["pass_variance"] == 0.0

    def test_mixed(self):
        out = vc.pass_rate_variance(["IDENTIFY", "ESCALATE"], "IDENTIFY")
        assert out["pass_count"] == 1
        assert out["pass_rate"] == 0.5
        assert out["any_fail"] is True
        assert out["pass_variance"] > 0.0

    def test_case_insensitive_match(self):
        out = vc.pass_rate_variance(["identify"], "IDENTIFY")
        assert out["pass_count"] == 1


# ---------------------------------------------------------------------------
# Finding classification (the issue's three branches)
# ---------------------------------------------------------------------------


class TestClassifyFinding:
    def test_bit_identical(self):
        text = vc.response_text_variance(["x", "x"])
        verdict = vc.verdict_distribution(["IDENTIFY", "IDENTIFY"])
        assert vc.classify_finding(text, verdict).startswith("responses-bit-identical")

    def test_text_varies_verdict_stable(self):
        text = vc.response_text_variance(["a long answer", "a longer answer"])
        verdict = vc.verdict_distribution(["IDENTIFY", "IDENTIFY"])
        assert vc.classify_finding(text, verdict).startswith("text-varies-verdict-stable")

    def test_verdicts_vary(self):
        text = vc.response_text_variance(["a", "b"])
        verdict = vc.verdict_distribution(["IDENTIFY", "ESCALATE"])
        assert vc.classify_finding(text, verdict).startswith("verdicts-vary")


# ---------------------------------------------------------------------------
# Orchestration with a fake adapter
# ---------------------------------------------------------------------------


@dataclass
class _FakeResult:
    raw_response: str
    outcome: str = "success"
    latency_ms: float = 1.0
    error_category: str | None = None


class _FakeAdapter:
    """Returns preset responses in order; records each call's kwargs."""

    def __init__(self, responses: list[_FakeResult]):
        self._responses = responses
        self.calls: list[dict] = []

    def call_model(
        self, prompt, model_id, fixture_id, variant, run_index, *, system, max_retries=3,
    ):
        self.calls.append({
            "fixture_id": fixture_id, "variant": variant,
            "run_index": run_index, "model_id": model_id,
        })
        return self._responses[run_index - 1]


class TestRunReps:
    def test_records_one_per_rep_with_verdicts(self):
        adapter = _FakeAdapter([
            _FakeResult("IDENTIFY a"),
            _FakeResult("ESCALATE b"),
            _FakeResult("IDENTIFY c"),
        ])
        records = vc.run_reps(
            adapter, system="sys", user="usr",
            fixture_id="F002", reps=3, model_id="m",
        )
        assert len(records) == 3
        assert [r.verdict for r in records] == ["IDENTIFY", "ESCALATE", "IDENTIFY"]
        assert [c["run_index"] for c in adapter.calls] == [1, 2, 3]
        assert all(c["variant"] == "agent" for c in adapter.calls)

    def test_error_rep_has_empty_response_and_no_verdict(self):
        adapter = _FakeAdapter([
            _FakeResult("IDENTIFY a"),
            _FakeResult("", outcome="error", error_category="timeout"),
        ])
        records = vc.run_reps(
            adapter, system="s", user="u", fixture_id="F002", reps=2, model_id="m",
        )
        assert records[1].response == ""
        assert records[1].verdict is None
        assert records[1].error_category == "timeout"


class TestSummarizeVariance:
    def test_excludes_error_reps_from_metrics(self):
        records = [
            vc.RepRecord(1, "success", "IDENTIFY x", "IDENTIFY", 1.0, None),
            vc.RepRecord(2, "success", "IDENTIFY y", "IDENTIFY", 1.0, None),
            vc.RepRecord(3, "error", "", None, 1.0, "timeout"),
        ]
        summary = vc.summarize_variance(records, "IDENTIFY")
        assert summary["reps_total"] == 3
        assert summary["reps_answered"] == 2
        assert summary["reps_error"] == 1
        assert summary["verdict_variance"]["stable"] is True
        assert summary["pass_rate_variance"]["pass_count"] == 2

    def test_report_md_has_sections(self):
        records = [
            vc.RepRecord(1, "success", "IDENTIFY x", "IDENTIFY", 1.0, None),
            vc.RepRecord(2, "success", "ESCALATE y", "ESCALATE", 1.0, None),
        ]
        summary = vc.summarize_variance(records, "IDENTIFY")
        md = vc.build_report_md(
            run_id="rid", fixture_id="F002", agent="security",
            model_id="m", summary=summary,
        )
        assert "# Variance Control Report: F002 / security" in md
        assert "## Verdict variance" in md
        assert "## Pass-rate variance" in md
        assert "## Response-text variance" in md


# ---------------------------------------------------------------------------
# Fixture + CLI plumbing
# ---------------------------------------------------------------------------


class TestFixtureAndCli:
    def test_loads_f002_expected_verdict(self):
        fixture = vc._load_fixture("F002")
        assert vc._expected_verdict(fixture) == "IDENTIFY"

    def test_dry_run_issues_no_api_calls(self, capsys):
        rc = vc.main(["--fixture", "F002", "--agent", "security", "--reps", "5", "--dry-run"])
        assert rc == 0
        assert "PLAN:" in capsys.readouterr().out

    def test_reps_below_two_rejected(self):
        rc = vc.main(["--reps", "1", "--dry-run"])
        assert rc == 2

    def test_bad_run_id_rejected(self):
        with pytest.raises(SystemExit):
            vc.build_parser().parse_args(["--run-id", "../../etc/passwd"])
