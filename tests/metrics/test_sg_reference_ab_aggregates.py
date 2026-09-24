"""Tests for aggregation in scripts/metrics/sg_reference_ab.py (#5856, REQ-8):
Aggregate/build_aggregates/write_output, including the valid_run_count /
infra-failure-exclusion behavior Task 2 added.

Split out of ``tests/metrics/test_sg_reference_ab.py`` under the taste-lints
file-size gate.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.metrics import sg_reference_ab as ab
from tests.metrics.sg_reference_ab_helpers import SCHEMA

# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _run(
    *,
    fixture: str = "f",
    mode: str = "inline",
    findings: list[tuple[str, str, str]] | None = None,
    failure: str | None = None,
    failure_detail: str | None = None,
    infra_failure: bool = False,
    total_input_tokens: int = 100,
    latency_s: float = 1.0,
    seeded_detected: bool = False,
    preexisting_flagged: bool = False,
) -> ab.RunResult:
    return ab.RunResult(
        fixture=fixture,
        mode=mode,
        run_index=0,
        prompt_bytes=1,
        usage_input_tokens=total_input_tokens,
        usage_cache_creation_tokens=0,
        usage_cache_read_tokens=0,
        usage_output_tokens=0,
        total_input_tokens=total_input_tokens,
        turns=1,
        latency_s=latency_s,
        failure=failure,
        failure_detail=failure_detail,
        infra_failure=infra_failure,
        findings=findings or [],
        read_diff_artifact_called=False,
        seeded_detected=seeded_detected,
        preexisting_flagged=preexisting_flagged,
    )


def test_median_empty_is_none() -> None:
    assert ab._median([]) is None
    assert ab._median([2.0, 4.0]) == 3.0


def test_aggregate_mode_counts_failures_and_flags() -> None:
    rows = [
        _run(total_input_tokens=100, latency_s=1.0, failure=None, seeded_detected=True),
        _run(total_input_tokens=200, latency_s=3.0, failure="timeout", preexisting_flagged=True),
    ]

    agg = ab._aggregate_mode(rows)

    assert agg.run_count == 2
    assert agg.valid_run_count == 2  # "timeout" is not an infra failure
    assert agg.median_input_tokens == 150
    assert agg.median_latency_s == 2.0
    assert agg.failure_count == 1
    assert agg.seeded_detected_count == 1
    assert agg.preexisting_flagged_count == 1


def test_aggregate_mode_excludes_infra_failures_from_valid_statistics() -> None:
    """REQ-8 support (#5856): an infra (billing/auth) failure carries no
    signal about inline-vs-referenced prompt behavior, so it must not drag
    down the median tokens/latency or the seeded/preexisting counts, even
    though it still counts toward run_count and failure_count.
    """
    rows = [
        _run(total_input_tokens=100, latency_s=1.0, seeded_detected=True),
        _run(
            total_input_tokens=999_999,
            latency_s=999.0,
            failure="http_400:invalid_request_error",
            failure_detail="Your credit balance is too low.",
            infra_failure=True,
            seeded_detected=True,
        ),
    ]

    agg = ab._aggregate_mode(rows)

    assert agg.run_count == 2
    assert agg.valid_run_count == 1
    assert agg.median_input_tokens == 100
    assert agg.median_latency_s == 1.0
    assert agg.failure_count == 1
    assert agg.seeded_detected_count == 1  # only the valid row's True counted


def test_jaccard_identical_sets_is_one() -> None:
    a = {("f.py", "CWE-78", "high")}
    assert ab._jaccard(a, set(a)) == 1.0


def test_jaccard_disjoint_sets_is_zero() -> None:
    a = {("f.py", "CWE-78", "high")}
    b = {("g.py", "CWE-89", "medium")}
    assert ab._jaccard(a, b) == 0.0


def test_jaccard_both_empty_is_none() -> None:
    assert ab._jaccard(set(), set()) is None


def test_finding_set_excludes_infra_failure_rows() -> None:
    rows = [
        _run(findings=[("a.py", "CWE-78", "high")]),
        _run(findings=[("b.py", "CWE-89", "medium")], infra_failure=True),
    ]

    assert ab._finding_set(rows) == {("a.py", "CWE-78", "high")}


def test_build_aggregates_groups_by_fixture_and_mode() -> None:
    rows = [
        _run(fixture="f1", mode="inline", findings=[("a.py", "CWE-78", "high")]),
        _run(fixture="f1", mode="referenced", findings=[("a.py", "CWE-78", "high")]),
        _run(fixture="f2", mode="inline", findings=[]),
    ]

    aggregates = ab.build_aggregates(rows)

    assert set(aggregates) == {"f1", "f2"}
    assert aggregates["f1"]["jaccard"] == 1.0
    assert aggregates["f2"]["jaccard"] is None  # no "referenced" rows for f2
    assert aggregates["f1"]["inline"]["run_count"] == 1
    assert aggregates["f1"]["inline"]["valid_run_count"] == 1


def test_write_output_produces_valid_json_with_expected_keys(tmp_path: Path) -> None:
    contract = ab.PluginContract(
        system="s",
        findings_schema=SCHEMA,
        review_api_sha256="a" * 64,
        llm_sha256="b" * 64,
        plugin_version="1.0",
    )
    rows = [_run()]
    output_path = tmp_path / "out" / "result.json"

    ab.write_output(output_path, contract, "model-x", 1, rows)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["provenance"]["plugin_version"] == "1.0"
    assert payload["provenance"]["review_api_sha256"] == "a" * 64
    assert payload["provenance"]["model"] == "model-x"
    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["failure_detail"] is None
    assert payload["runs"][0]["infra_failure"] is False
    assert "f" in payload["aggregates"]


