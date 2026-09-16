"""Parsing lefthook's own summary block (REQ-027 T1).

Split from test_gate_latency.py so each test module mirrors one source
module, which is also what the code-qualities cohesion gate asks for.
Every fixture here is real captured output from this repository's hooks
or from a negative control, never invented.
"""

from __future__ import annotations

from scripts.metrics import lefthook_summary as ls
from tests.metrics.gate_latency_helpers import (
    NEGATIVE_CONTROL_STDOUT,
    REAL_CAPTURED_STDOUT,
    UNVERIFIED_SYNONYM_MARKER_STDOUT,
)

# --- lefthook_summary.py: parser (positive, negative, edge) -----------------


def test_positive_real_captured_output_yields_one_pass_sample() -> None:
    samples, reported = ls.parse_summary(REAL_CAPTURED_STDOUT)
    assert reported == 0.20
    assert len(samples) == 1
    sample = samples[0]
    assert sample.name == "security-suppressions-staged"
    assert sample.seconds == 0.20
    assert sample.status == "pass"
    assert sample.marker == "✓"
    assert sample.depth == 0


def test_positive_real_negative_control_yields_one_pass_and_one_fail() -> None:
    """Real capture from a disposable throwaway repo (never committed here)."""
    samples, reported = ls.parse_summary(NEGATIVE_CONTROL_STDOUT)
    assert reported == 0.01
    assert [(s.name, s.status, s.marker) for s in samples] == [
        ("good-job", "pass", "✓"),
        ("bad-job", "fail", "✗"),
    ]


def test_edge_documented_synonym_marker_not_observed_here_still_classifies() -> None:
    """U+2714 U+FE0F is a documented synonym, not a capture from this environment."""
    samples, _reported = ls.parse_summary(UNVERIFIED_SYNONYM_MARKER_STDOUT)
    assert samples == [
        ls.JobSample(name="some-other-job", seconds=0.05, status="pass", marker="✔️", depth=0)
    ]


def test_negative_absent_summary_yields_zero_samples_and_does_not_raise() -> None:
    samples, reported = ls.parse_summary("no summary here at all\njust noise\n")
    assert samples == []
    assert reported is None


def test_negative_malformed_summary_line_yields_zero_samples() -> None:
    samples, reported = ls.parse_summary("summary: this is not the expected shape\n")
    assert samples == []
    assert reported is None


def test_edge_nested_group_parses_all_rows_with_correct_depths() -> None:
    stdout = (
        "summary: (done in 0.50 seconds)\n"
        "✔️ group-name (0.50 seconds)\n"
        "  ✔️ member-one (0.20 seconds)\n"
        "  ✖️ member-two (0.30 seconds)\n"
    )
    samples, reported = ls.parse_summary(stdout)
    assert reported == 0.50
    assert [(s.name, s.depth, s.status) for s in samples] == [
        ("group-name", 0, "pass"),
        ("member-one", 2, "pass"),
        ("member-two", 2, "fail"),
    ]


def test_edge_marker_classification_covers_pass_fail_and_unknown() -> None:
    # Verified this session (real lefthook 2.1.12 captures):
    assert ls.classify_marker("✓") == "pass"  # bare check mark
    assert ls.classify_marker("✗") == "fail"  # bare ballot X
    # Documented synonyms, not observed in this environment:
    assert ls.classify_marker("✔️") == "pass"
    assert ls.classify_marker("✔") == "pass"
    assert ls.classify_marker("✅") == "pass"
    assert ls.classify_marker("✖️") == "fail"
    assert ls.classify_marker("✖") == "fail"
    assert ls.classify_marker("✘") == "fail"
    assert ls.classify_marker("❌") == "fail"
    assert ls.classify_marker("?") == "unknown"
    assert ls.classify_marker("") == "unknown"


def test_edge_trailing_non_job_line_after_summary_stops_parsing() -> None:
    stdout = (
        "summary: (done in 0.10 seconds)\n"
        "✔️ only-job (0.10 seconds)\n"
        "some trailing prose that is not a job line\n"
        "✔️ never-reached (9.99 seconds)\n"
    )
    samples, _reported = ls.parse_summary(stdout)
    assert [s.name for s in samples] == ["only-job"]


