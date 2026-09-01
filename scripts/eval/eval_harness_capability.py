#!/usr/bin/env python3
"""Assemble and validate the per-harness capability matrix (issue #5423).

This is a thin CLI. All logic lives in `_harness_capability`. It loads the
checked-in matrix, optionally augments a harness record with a live runtime
version where that CLI is installed and probe-capable, derives #5422 arm
eligibility, and emits a machine-readable report for #5424 and #5426.

Live probing is read-only and evidence-honest: it fills the exact runtime
version through `_runtime_parity.probe_version` (the existing prober; no second
one is written) and flips nothing else to VERIFIED. A harness that is absent
from PATH, or not probe-capable, keeps its checked-in UNVERIFIED version.

Exit codes follow AGENTS.md: 0 ok, 2 config, 3 external.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from _harness_capability import (
    HarnessCapabilityError,
    HarnessCapabilityRecord,
    apply_version_probe,
    build_report,
    load_matrix,
)
from _runtime_parity import probe_version

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = Path(__file__).parent / "examples" / "harness-capability-matrix.json"
DEFAULT_TIMEOUT = 60.0

# Only harnesses whose isolated profile `_runtime_parity.runtime_env` knows how
# to build are probe-capable through the existing prober. Codex has no in-tree
# runtime support (issue #5423 confirms the gap), so its version stays
# UNVERIFIED rather than being fabricated here.
PROBE_HARNESS: dict[str, str] = {"copilot": "copilot"}

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _probe_bin(harness: str, copilot_bin: str) -> str:
    return copilot_bin if harness == "copilot" else harness


def _augment_versions(
    records: list[HarnessCapabilityRecord],
    *,
    output: Path,
    copilot_bin: str,
    timeout: float,
    runner: Runner,
) -> list[HarnessCapabilityRecord]:
    """Fill live runtime versions where the CLI is installed and probe-capable.

    A probe failure leaves the record at its checked-in UNVERIFIED version.
    UNVERIFIED is the restrictive default here, so continuing on failure never
    upgrades a claim; it only declines to.
    """
    augmented: list[HarnessCapabilityRecord] = []
    for record in records:
        probe_name = PROBE_HARNESS.get(record.harness)
        executable = _probe_bin(record.harness, copilot_bin)
        if probe_name is None or shutil.which(executable) is None:
            augmented.append(record)
            continue
        try:
            version = probe_version(
                executable,
                probe_name,
                output.parent / "version-probes" / record.harness,
                runner,
                timeout,
            )
        except (OSError, RuntimeError, subprocess.SubprocessError):
            augmented.append(record)
            continue
        augmented.append(apply_version_probe(record, version))
    return augmented


def run(
    *,
    matrix_path: Path,
    output: Path,
    copilot_bin: str,
    timeout: float,
    dry_run: bool,
    runner: Runner,
) -> dict[str, object]:
    """Load the matrix, optionally probe versions, and build the report."""
    records = load_matrix(matrix_path)
    if not dry_run:
        records = _augment_versions(
            records,
            output=output,
            copilot_bin=copilot_bin,
            timeout=timeout,
            runner=runner,
        )
    report: dict[str, object] = build_report(records)
    if not dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--copilot-bin", default="copilot")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _default_output() -> Path:
    return REPO_ROOT / "artifacts" / "harness-capability" / "report.json"


def main(argv: Sequence[str] | None = None, *, runner: Runner = subprocess.run) -> int:
    args = _parser().parse_args(argv)
    if not (args.timeout > 0):
        print("Error: --timeout must be greater than zero.", file=sys.stderr)
        return EXIT_CONFIG
    output = (args.output or _default_output()).resolve()
    try:
        report = run(
            matrix_path=args.matrix.resolve(),
            output=output,
            copilot_bin=args.copilot_bin,
            timeout=args.timeout,
            dry_run=args.dry_run,
            runner=runner,
        )
    except HarnessCapabilityError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(json.dumps(report, indent=2))
    if not args.dry_run:
        print(f"Report: {output}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
