#!/usr/bin/env python3
"""Aggregate session protocol validation verdicts across all validated files.

Input env vars (used as defaults for CLI args):
    GITHUB_OUTPUT      - Path to GitHub Actions output file
    GITHUB_WORKSPACE   - Workspace root (for package imports)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from glob import glob
from pathlib import Path

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.ai_review_common import write_log, write_output  # noqa: E402

_VALID_VERDICTS = frozenset(
    {
        "PASS",
        "COMPLIANT",
        "SKIPPED",
        "WARN",
        "CRITICAL_FAIL",
        "REJECTED",
        "NON_COMPLIANT",
    }
)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Aggregate session protocol validation verdicts across all validated files.",
    )
    parser.add_argument(
        "--results-dir",
        default="validation-results",
        help="Directory containing verdict and must-failures files",
    )
    parser.add_argument(
        "--expected-results",
        type=int,
        default=int(os.environ.get("EXPECTED_RESULTS", "0")),
        help="Expected number of session verdict artifacts",
    )
    parser.add_argument(
        "--expected-artifacts",
        default=os.environ.get("EXPECTED_ARTIFACTS", "{}"),
        help="JSON object mapping expected artifact stems to session paths",
    )
    return parser


def _load_expected_artifacts(
    raw: str,
    expected_results: int,
) -> dict[str, str] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict) or len(value) != expected_results:
        return None
    if not all(
        isinstance(stem, str)
        and stem
        and isinstance(session, str)
        and session
        for stem, session in value.items()
    ):
        return None
    return value


def _aggregate_verdicts(
    verdict_files: list[str],
    overall_verdict: str,
    expected_artifacts: dict[str, str],
) -> str:
    for verdict_file in verdict_files:
        filename = os.path.basename(verdict_file)
        stem = filename[: -len("-verdict.txt")]
        with open(verdict_file, encoding="utf-8") as f:
            verdict = f.read().strip()

        write_log(f"Found verdict: {verdict} from {filename}")
        if verdict not in _VALID_VERDICTS:
            write_log(f"ERROR: Invalid verdict {verdict!r} in {filename}")
            print(
                f"::error::Invalid session verdict {verdict!r} in {filename}",
                file=sys.stderr,
            )
            overall_verdict = "CRITICAL_FAIL"
            continue
        if verdict == "SKIPPED" and Path(expected_artifacts.get(stem, "")).exists():
            write_log(f"ERROR: SKIPPED verdict targets an existing file: {filename}")
            print(
                f"::error::SKIPPED session verdict targets an existing file: {filename}",
                file=sys.stderr,
            )
            overall_verdict = "CRITICAL_FAIL"
            continue

        if verdict in ("CRITICAL_FAIL", "REJECTED", "NON_COMPLIANT"):
            overall_verdict = "CRITICAL_FAIL"
        elif verdict == "WARN" and overall_verdict == "PASS":
            overall_verdict = "WARN"

    return overall_verdict


def _count_must_failures(must_files: list[str]) -> tuple[int, bool]:
    total_must_failures = 0
    invalid = False
    for must_file in must_files:
        filename = os.path.basename(must_file)
        with open(must_file, encoding="utf-8") as f:
            content = f.read().strip()

        if not re.fullmatch(r"\d+", content):
            write_log(f"ERROR: Invalid MUST-failure count {content!r} in {filename}")
            print(
                f"::error::Invalid MUST-failure count {content!r} in {filename}",
                file=sys.stderr,
            )
            invalid = True
            continue
        total_must_failures += int(content)

    return total_must_failures, invalid


def _artifact_stems(paths: list[str], suffix: str) -> set[str]:
    return {
        os.path.basename(path)[: -len(suffix)]
        for path in paths
        if path.endswith(suffix)
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results_dir = os.path.abspath(args.results_dir)
    overall_verdict = "PASS"
    total_must_failures = 0
    expected_artifacts = _load_expected_artifacts(
        args.expected_artifacts,
        args.expected_results,
    )

    verdict_files = sorted(glob(f"{results_dir}/*-verdict.txt"))

    if args.expected_results < 1 or expected_artifacts is None:
        write_log("ERROR: Expected result count is missing or invalid")
        print("::error::Expected session artifacts are missing or invalid", file=sys.stderr)
        overall_verdict = "CRITICAL_FAIL"
    elif len(verdict_files) != args.expected_results:
        write_log(
            "ERROR: Session verdict artifact count mismatch: "
            f"expected {args.expected_results}, found {len(verdict_files)}"
        )
        print(
            "::error::Session verdict artifact count mismatch: "
            f"expected {args.expected_results}, found {len(verdict_files)}",
            file=sys.stderr,
        )
        overall_verdict = "CRITICAL_FAIL"

    overall_verdict = _aggregate_verdicts(
        verdict_files,
        overall_verdict,
        expected_artifacts or {},
    )

    must_files = sorted(glob(f"{results_dir}/*-must-failures.txt"))
    if args.expected_results > 0 and len(must_files) != args.expected_results:
        write_log(
            "ERROR: MUST-failure artifact count mismatch: "
            f"expected {args.expected_results}, found {len(must_files)}"
        )
        print(
            "::error::MUST-failure artifact count mismatch: "
            f"expected {args.expected_results}, found {len(must_files)}",
            file=sys.stderr,
        )
        overall_verdict = "CRITICAL_FAIL"
    verdict_stems = _artifact_stems(verdict_files, "-verdict.txt")
    must_stems = _artifact_stems(must_files, "-must-failures.txt")
    expected_stems = set(expected_artifacts or {})
    if verdict_stems != must_stems or verdict_stems != expected_stems:
        write_log("ERROR: Session verdict and MUST-failure artifacts do not pair")
        print(
            "::error::Session verdict and MUST-failure artifacts do not pair",
            file=sys.stderr,
        )
        overall_verdict = "CRITICAL_FAIL"

    total_must_failures, invalid_must_count = _count_must_failures(must_files)
    if invalid_must_count:
        overall_verdict = "CRITICAL_FAIL"

    if total_must_failures > 0:
        overall_verdict = "CRITICAL_FAIL"

    write_output("final_verdict", overall_verdict)
    write_output("must_failures", str(total_must_failures))

    write_log(f"Final verdict: {overall_verdict} (MUST failures: {total_must_failures})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
