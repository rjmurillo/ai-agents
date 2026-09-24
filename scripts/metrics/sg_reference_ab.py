"""Live A/B measurement: inline vs referenced security-guidance diff prompt (#5856).

Evaluation harness only. Not wired to any hook. Runs the plugin's real
investigate system prompt and findings schema (loaded from the installed
``security-guidance`` plugin via importlib, read only) through a minimal tool
loop against the Anthropic Messages API, once with the diff inlined
(:func:`scripts.metrics.sg_diff_reference.build_inline_prompt`) and once with
the diff replaced by a content-addressed artifact reference
(:func:`scripts.metrics.sg_diff_producer.produce_prompt`, mode
``"referenced"``), so prompt size, token usage, latency, and finding parity
can be compared per REQ-8.

This module owns orchestration (running every fixture x mode x repeat
combination), aggregation, and the CLI. It is split, under the taste-lints
file-size gate, from three sibling modules this module imports:
``sg_reference_ab_fixtures`` (the four seeded git repositories reviewed),
``sg_reference_ab_api`` (credentials, the plugin contract, the Messages API
transport, and failure classification), and ``sg_reference_ab_toolloop``
(the tool-confined filesystem handlers and the per-turn investigate loop
built on that transport).

Stricter/looser/different than canonical
-----------------------------------------

This harness runs only ``review_api.AGENTIC_INVESTIGATE_SYSTEM`` (stage 1,
investigate) with a single ``report_findings`` tool call ending the loop. It
does not run the plugin's stage 2 self-refute/adjudication pass
(``llm.py:agentic_review``'s ``filter_mode="self_refute"`` branch), and it
does not apply ``tag_diff_anchor`` or severity filtering. This is narrower by
design (REQ-8 measures prompt/token/latency/finding-set parity between inline
and referenced diffs, not overall review precision) and is a non-goal per the
spec ("No change to security heuristics or review failure handling").
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.metrics import sg_diff_producer as sgdp
from scripts.metrics import sg_diff_reference as sgd
from scripts.metrics.sg_reference_ab_api import (
    PluginContract,
    PluginContractError,
    default_model,
    load_api_key,
    load_plugin_contract,
)
from scripts.metrics.sg_reference_ab_fixtures import Fixture, build_fixtures
from scripts.metrics.sg_reference_ab_toolloop import run_investigate_loop

DEFAULT_PLUGIN_DIR = (
    Path.home()
    / ".claude"
    / "plugins"
    / "cache"
    / "claude-plugins-official"
    / "security-guidance"
    / "2.0.8"
    / "hooks"
)

_ALL_FIXTURE_NAMES = ("f_repeat", "f_paths", "f_trunc", "f_mismatch")

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3


# ---------------------------------------------------------------------------
# Per-run orchestration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RunResult:
    fixture: str
    mode: str
    run_index: int
    prompt_bytes: int
    usage_input_tokens: int
    usage_cache_creation_tokens: int
    usage_cache_read_tokens: int
    usage_output_tokens: int
    total_input_tokens: int
    turns: int
    latency_s: float
    failure: str | None
    failure_detail: str | None
    infra_failure: bool
    findings: list[tuple[str, str, str]]
    read_diff_artifact_called: bool
    seeded_detected: bool
    preexisting_flagged: bool


def _classify_findings(
    findings: Sequence[dict[str, Any]], seeded_path: str, preexisting_path: str
) -> tuple[bool, bool]:
    flagged_paths = {str(f.get("filePath", "")) for f in findings if isinstance(f, dict)}
    return seeded_path in flagged_paths, preexisting_path in flagged_paths


def run_fixture_mode(
    *,
    fixture: Fixture,
    mode: str,
    run_index: int,
    api_key: str,
    model: str,
    system: str,
    findings_schema: dict[str, Any],
    store_dir: Path,
) -> RunResult:
    start = time.monotonic()
    prompt, outcome = sgdp.produce_prompt(
        mode,
        store_dir,
        fixture.repo_id,
        fixture.head,
        fixture.touched_paths,
        fixture.diff_files,
        fixture.context_note,
        per_file_bytes=fixture.per_file_bytes,
        total_bytes=fixture.total_bytes,
    )
    inline_diff_text, _dropped = sgd.capped_diff_text(
        fixture.diff_files, per_file_bytes=fixture.per_file_bytes, total_bytes=fixture.total_bytes
    )
    loop = run_investigate_loop(
        api_key=api_key,
        model=model,
        system=system,
        prompt=prompt,
        fixture_dir=fixture.fixture_dir,
        store_dir=store_dir,
        ref=outcome.ref,
        expected_repo_id=fixture.repo_id,
        expected_head=fixture.head,
        inline_diff_text=inline_diff_text,
        findings_schema=findings_schema,
    )
    latency_s = time.monotonic() - start
    seeded_detected, preexisting_flagged = _classify_findings(
        loop.findings, fixture.seeded_path, fixture.preexisting_path
    )
    findings_sorted = sorted(
        (str(f.get("filePath", "")), str(f.get("category", "")), str(f.get("severity", "")))
        for f in loop.findings
        if isinstance(f, dict)
    )
    return RunResult(
        fixture=fixture.name,
        mode=mode,
        run_index=run_index,
        prompt_bytes=len(prompt.encode("utf-8")),
        usage_input_tokens=loop.usage.input_tokens,
        usage_cache_creation_tokens=loop.usage.cache_creation_tokens,
        usage_cache_read_tokens=loop.usage.cache_read_tokens,
        usage_output_tokens=loop.usage.output_tokens,
        total_input_tokens=loop.usage.total_input_tokens,
        turns=loop.turns,
        latency_s=latency_s,
        failure=loop.failure,
        failure_detail=loop.failure_detail,
        infra_failure=loop.infra_failure,
        findings=findings_sorted,
        read_diff_artifact_called=loop.read_diff_artifact_called,
        seeded_detected=seeded_detected,
        preexisting_flagged=preexisting_flagged,
    )


def run_all(
    fixtures: Sequence[Fixture],
    runs: int,
    api_key: str,
    model: str,
    contract: PluginContract,
    store_dir: Path,
) -> list[RunResult]:
    rows: list[RunResult] = []
    for fixture in fixtures:
        for mode in ("inline", "referenced"):
            for run_index in range(runs):
                rows.append(
                    run_fixture_mode(
                        fixture=fixture,
                        mode=mode,
                        run_index=run_index,
                        api_key=api_key,
                        model=model,
                        system=contract.system,
                        findings_schema=contract.findings_schema,
                        store_dir=store_dir,
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# Aggregation and output
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Aggregate:
    fixture: str
    mode: str
    run_count: int
    valid_run_count: int
    median_input_tokens: float | None
    median_latency_s: float | None
    failure_count: int
    seeded_detected_count: int
    preexisting_flagged_count: int


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _aggregate_mode(rows: Sequence[RunResult]) -> Aggregate:
    """One fixture/mode's summary statistics.

    ``run_count`` covers every row, including infrastructure failures
    (billing/auth; see ``sg_reference_ab_api.FailureClassification``), so a
    reader can see how many runs were attempted. ``valid_run_count`` and
    every statistic derived from ``valid_rows`` below exclude infra
    failures: an auth or billing failure carries no signal about
    inline-vs-referenced prompt behavior, and folding it into the median
    token/latency figures or the seeded/preexisting counts would silently
    understate them. ``failure_count`` is deliberately NOT narrowed the same
    way; it counts every failure (infra or not) as a diagnostic total.
    """
    valid_rows = [r for r in rows if not r.infra_failure]
    return Aggregate(
        fixture=rows[0].fixture,
        mode=rows[0].mode,
        run_count=len(rows),
        valid_run_count=len(valid_rows),
        median_input_tokens=_median([r.total_input_tokens for r in valid_rows]),
        median_latency_s=_median([r.latency_s for r in valid_rows]),
        failure_count=sum(1 for r in rows if r.failure is not None),
        seeded_detected_count=sum(1 for r in valid_rows if r.seeded_detected),
        preexisting_flagged_count=sum(1 for r in valid_rows if r.preexisting_flagged),
    )


def _finding_set(rows: Sequence[RunResult]) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for row in rows:
        if row.infra_failure:
            continue
        out.update(row.findings)
    return out


def _jaccard(a: set[tuple[str, str, str]], b: set[tuple[str, str, str]]) -> float | None:
    union = a | b
    if not union:
        return None
    return len(a & b) / len(union)


def build_aggregates(rows: Sequence[RunResult]) -> dict[str, dict[str, Any]]:
    by_fixture: dict[str, dict[str, list[RunResult]]] = {}
    for row in rows:
        by_fixture.setdefault(row.fixture, {}).setdefault(row.mode, []).append(row)

    result: dict[str, dict[str, Any]] = {}
    for fixture_name, modes in by_fixture.items():
        entry: dict[str, Any] = {
            mode: dataclasses.asdict(_aggregate_mode(mode_rows))
            for mode, mode_rows in modes.items()
        }
        # _finding_set already excludes infra-failure rows (REQ-8: jaccard
        # measures finding-set parity, which an auth/billing failure cannot
        # speak to).
        entry["jaccard"] = _jaccard(
            _finding_set(modes.get("inline", [])), _finding_set(modes.get("referenced", []))
        )
        result[fixture_name] = entry
    return result


def write_output(
    output_path: Path,
    contract: PluginContract,
    model: str,
    runs: int,
    rows: Sequence[RunResult],
) -> None:
    payload = {
        "provenance": {
            "plugin_version": contract.plugin_version,
            "review_api_sha256": contract.review_api_sha256,
            "llm_sha256": contract.llm_sha256,
            "model": model,
            "runs_per_fixture_mode": runs,
        },
        "runs": [dataclasses.asdict(r) for r in rows],
        "aggregates": build_aggregates(rows),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live A/B measurement: inline vs referenced security-guidance diff prompt."
    )
    parser.add_argument("--runs", type=int, required=True)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plugin-dir", type=Path, default=DEFAULT_PLUGIN_DIR)
    parser.add_argument("--fixtures", type=str, default=None)
    return parser.parse_args(argv)


def _selected_fixture_names(raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return _ALL_FIXTURE_NAMES
    names = tuple(n.strip() for n in raw.split(",") if n.strip())
    unknown = [n for n in names if n not in _ALL_FIXTURE_NAMES]
    if unknown or not names:
        print(
            f"sg_reference_ab: unknown fixture(s) {unknown or '(empty)'}; "
            f"choose from {_ALL_FIXTURE_NAMES}",
            file=sys.stderr,
        )
        return None
    return names


_ResolvedConfig = tuple[str, PluginContract, str, tuple[str, ...]]


def _resolve_config(args: argparse.Namespace, repo_root: Path) -> _ResolvedConfig | int:
    """Validate CLI inputs; returns (api_key, contract, model, fixture_names) or an exit code."""
    if args.runs < 1:
        print("sg_reference_ab: --runs must be >= 1", file=sys.stderr)
        return EXIT_CONFIG
    api_key = load_api_key(repo_root)
    if not api_key:
        print("sg_reference_ab: ANTHROPIC_API_KEY not set and not found in .env", file=sys.stderr)
        return EXIT_CONFIG
    try:
        contract = load_plugin_contract(args.plugin_dir)
    except PluginContractError as exc:
        print(f"sg_reference_ab: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    fixture_names = _selected_fixture_names(args.fixtures)
    if fixture_names is None:
        return EXIT_CONFIG
    model = args.model or default_model()
    return api_key, contract, model, fixture_names


def _report_total_failure(rows: Sequence[RunResult]) -> None:
    """Print why every run failed. Distinguishes an infrastructure outage
    (billing/auth; every run never reached a real review) from an ordinary
    review failure, so a billing failure like the one that motivated
    ``sg_reference_ab_api.FailureClassification`` is never reported as an
    undifferentiated "every run failed".
    """
    if all(row.infra_failure for row in rows):
        detail = next((row.failure_detail for row in rows if row.failure_detail), None)
        suffix = f": {detail}" if detail else ""
        print(
            "sg_reference_ab: every run failed due to an infrastructure error "
            f"(billing/auth){suffix}",
            file=sys.stderr,
        )
        return
    print("sg_reference_ab: every run failed", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = Path(__file__).resolve().parents[2]

    resolved = _resolve_config(args, repo_root)
    if isinstance(resolved, int):
        return resolved
    api_key, contract, model, fixture_names = resolved

    with tempfile.TemporaryDirectory(prefix="sg-ab-") as tmp:
        tmp_root = Path(tmp)
        try:
            fixtures = build_fixtures(tmp_root, fixture_names)
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"sg_reference_ab: failed building fixtures: {exc}", file=sys.stderr)
            return EXIT_CONFIG
        rows = run_all(fixtures, args.runs, api_key, model, contract, tmp_root / "store")
        write_output(args.output, contract, model, args.runs, rows)

    if rows and all(row.failure is not None for row in rows):
        _report_total_failure(rows)
        return EXIT_EXTERNAL
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - standard CLI entrypoint guard
    sys.exit(main())
