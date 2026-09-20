#!/usr/bin/env python3
"""Assemble and validate the per-harness capability matrix (issue #5423).

This is a thin CLI. It loads the checked-in matrix, fills a live runtime
version where that CLI is installed, optionally executes shell-free behavioral
probe commands from a JSON plan, derives #5422 arm eligibility, and emits a
machine-readable report for #5424 and #5426.

Version and behavioral probing are read-only and evidence-honest. A behavioral
result can upgrade only the capability named by its plan entry, and only after
the runtime version is confirmed. A harness that is absent from PATH, or not
probe-capable, keeps its checked-in UNVERIFIED state.

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

from _capability_probes import (
    BehavioralProbe,
    build_override_plan,
    load_behavioral_probes,
    probe_concurrency,
    probe_override,
    probe_subagent_support,
)
from _harness_capability import (
    Capability,
    EvidenceKind,
    HarnessCapabilityError,
    HarnessCapabilityRecord,
    apply_behavioral_probe,
    apply_version_probe,
    build_report,
    load_matrix,
    write_report,
)
from _runtime_harness import probe_version

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = Path(__file__).parent / "examples" / "harness-capability-matrix.json"
DEFAULT_TIMEOUT = 60.0

# Only harnesses whose isolated profile `_runtime_parity.runtime_env` knows how
# to build are probe-capable through the existing prober. `_runtime_parity`
# now has a codex branch (profile root, isolated env, version-probe argv), so
# codex is wired in alongside copilot. Neither harness's *behavioral*
# capabilities (model/effort override, subagent support, and so on) are
# probed anywhere in this module: only the version string can move off
# UNVERIFIED here, and only when the CLI is actually on PATH.
PROBE_HARNESS: dict[str, str] = {"copilot": "copilot", "codex": "codex"}

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


def _run_behavioral_probe(
    probe: BehavioralProbe,
    *,
    runner: Runner,
    timeout: float,
) -> Capability:
    if probe.capability in ("model_override", "effort_override"):
        if probe.parent_value is None or probe.child_value is None:
            raise HarnessCapabilityError(
                f"{probe.harness}.{probe.capability} is missing override values"
            )
        plan = build_override_plan(
            capability=probe.capability,
            harness=probe.harness,
            parent_value=probe.parent_value,
            candidates=(probe.child_value,),
        )
        return probe_override(plan, probe.command, runner=runner, timeout=timeout)
    if probe.capability == "subagent_support":
        return probe_subagent_support(probe.command, runner=runner, timeout=timeout)
    if probe.requested is None:
        raise HarnessCapabilityError(
            f"{probe.harness}.{probe.capability} is missing requested concurrency"
        )
    return probe_concurrency(
        probe.command,
        requested=probe.requested,
        runner=runner,
        timeout=timeout,
    )


def _augment_behavioral(
    records: list[HarnessCapabilityRecord],
    *,
    plan_path: Path,
    timeout: float,
    runner: Runner,
) -> list[HarnessCapabilityRecord]:
    """Apply live behavioral evidence to the matching records."""
    by_harness = {record.harness: record for record in records}
    for probe in load_behavioral_probes(plan_path):
        if probe.harness not in by_harness:
            raise HarnessCapabilityError(
                f"behavioral probe targets unknown harness: {probe.harness}"
            )
        record = by_harness[probe.harness]
        if record.version_evidence is not EvidenceKind.BACKEND or not record.version:
            continue
        result = _run_behavioral_probe(probe, runner=runner, timeout=timeout)
        by_harness[probe.harness] = apply_behavioral_probe(
            record,
            probe.capability,
            result,
            reported_value=probe.child_value,
        )
    return [by_harness[record.harness] for record in records]


def run(
    *,
    matrix_path: Path,
    output: Path,
    copilot_bin: str,
    timeout: float,
    dry_run: bool,
    runner: Runner,
    behavioral_probes: Path | None = None,
) -> dict[str, object]:
    """Load the matrix, probe versions, and optionally run behavioral probes."""
    records = load_matrix(matrix_path)
    if not dry_run:
        records = _augment_versions(
            records,
            output=output,
            copilot_bin=copilot_bin,
            timeout=timeout,
            runner=runner,
        )
        if behavioral_probes is not None:
            records = _augment_behavioral(
                records,
                plan_path=behavioral_probes,
                timeout=timeout,
                runner=runner,
            )
    report: dict[str, object] = build_report(records)
    if not dry_run:
        write_report(output, report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--copilot-bin", default="copilot")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--behavioral-probes",
        type=Path,
        help="JSON plan of live behavioral probe commands",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _default_output() -> Path:
    return REPO_ROOT / "artifacts" / "harness-capability" / "report.json"


def main(argv: Sequence[str] | None = None, *, runner: Runner = subprocess.run) -> int:
    args = _parser().parse_args(argv)
    if not (args.timeout > 0):
        print("Error: --timeout must be greater than zero.", file=sys.stderr)
        return EXIT_CONFIG
    # Path.resolve() touches the filesystem, so it fails the same ways the run
    # does. A relative path resolves through os.getcwd(), which raises
    # FileNotFoundError once the working directory has been removed. Resolving
    # outside this block let that escape as a traceback instead of the exit
    # contract below.
    try:
        output = (args.output or _default_output()).resolve()
        behavioral_probes = args.behavioral_probes.resolve() if args.behavioral_probes else None
        report = run(
            matrix_path=args.matrix.resolve(),
            output=output,
            copilot_bin=args.copilot_bin,
            timeout=args.timeout,
            dry_run=args.dry_run,
            runner=runner,
            behavioral_probes=behavioral_probes,
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
