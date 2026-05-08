#!/usr/bin/env python3
"""Run the guard maturity report end-to-end.

Thin wrapper around the two build/scripts:

1. ``aggregate_guard_intercepts.py``
2. ``classify_guard_maturity.py``

Output is a human-readable table printed to stdout, plus the raw JSON
report on stderr (so a caller can capture it with ``2>``).

The wrapper keeps logic out of the SKILL.md prose (the skill should
describe what to do; the script should do it). All tier and fitness
math lives in the classifier; this file is presentation only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Subprocess-safety note (CWE-78, semgrep
# python.lang.security.audit.dangerous-subprocess-use-tainted-env-args):
# Path resolution intentionally does NOT consult environment variables.
# Earlier revisions read ``CLAUDE_PLUGIN_ROOT`` and ``GITHUB_WORKSPACE``,
# but those values flow into ``AGGREGATE`` / ``CLASSIFY`` and from there
# into ``subprocess.run`` argv, which semgrep flags as a tainted-env-args
# command-injection sink even with list-form ``run`` (no shell). We
# resolve via ``__file__``-relative walk-up only; the resulting path is
# not user-controlled. We additionally call ``Path.resolve(strict=True)``
# at exec time so a non-existent or symlink-relocated script raises
# before reaching ``subprocess.run``.

_SCRIPT_NAMES = (
    "aggregate_guard_intercepts.py",
    "classify_guard_maturity.py",
)


def _resolve_repo_root() -> Path:
    """Locate the repo root from ``__file__`` only — no env-var input.

    The same source file lives at two different depths:
    - canonical: ``.claude/skills/guard-maturity/scripts/run_report.py`` →
      ``parents[4]`` is the repo root.
    - copilot-cli mirror: ``src/copilot-cli/skills/guard-maturity/scripts/
      run_report.py`` → ``parents[4]`` is ``<repo>/src``, NOT the repo
      root. A naive ``parents[4]`` makes ``AGGREGATE`` / ``CLASSIFY`` point
      at ``<repo>/src/build/scripts/...`` which does not exist.

    Walk up from ``__file__`` looking for ``AGENTS.md`` (in-repo
    canonical) or ``.git`` (any local clone). Fall back to
    ``parents[4]`` (preserves prior behavior for the canonical layout
    when no marker is found).
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "AGENTS.md").is_file() or (parent / ".git").is_dir():
            return parent
    return here.parents[4]


def _validated_script_path(name: str) -> Path:
    """Return the resolved path of a known build script, or raise.

    Semgrep-recognized hardening: the file name MUST be one of the two
    known constants in ``_SCRIPT_NAMES``; ``Path.resolve(strict=True)``
    asserts the file exists at the moment of exec; the parent directory
    chain MUST end ``.../build/scripts/<name>``. A symlink, a missing
    file, or a relocated layout raises before ``subprocess.run`` is
    called, so the argv contents are constrained to a closed set.
    """
    if name not in _SCRIPT_NAMES:
        raise SystemExit(f"refusing to exec unknown build script: {name!r}")
    path = (REPO_ROOT / "build" / "scripts" / name).resolve(strict=True)
    if path.parent.name != "scripts" or path.parent.parent.name != "build":
        raise SystemExit(f"refusing to exec script outside build/scripts: {path}")
    if path.name != name:
        raise SystemExit(f"resolved name mismatch: {path.name} != {name}")
    return path


REPO_ROOT = _resolve_repo_root()

# Severity sort: Harmful first (act now), then Inert (prune), then the
# happy tiers. Within a tier, sort by intercepts descending so the
# loudest guards float to the top.
TIER_ORDER = {
    "Harmful": 0,
    "Inert": 1,
    "Budding": 2,
    "Growing": 3,
    "Mature": 4,
    "Proficient": 5,
}


def _parse_subprocess_json(stdout: str, child_label: str) -> dict:
    """Parse JSON from a child subprocess's stdout with a controlled error.

    A successful (returncode 0) child whose stdout is empty or non-JSON is
    a contract violation. Raise SystemExit(3) (external error per ADR-035)
    rather than letting json.JSONDecodeError dump a traceback.
    """
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(
            f"error: {child_label} returned non-JSON stdout "
            f"({len(stdout)} bytes): {exc}\n"
        )
        raise SystemExit(3) from exc


def _run_aggregate(known_guards: list[str], source: str | None) -> dict:
    aggregate = _validated_script_path("aggregate_guard_intercepts.py")
    cmd = [sys.executable, str(aggregate)]
    for g in known_guards:
        cmd.extend(["--guard", g])
    if source:
        cmd.extend(["--source", source])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return _parse_subprocess_json(proc.stdout, "aggregate_guard_intercepts.py")


def _run_classify(summary: dict, treat_unseen_as_inert: bool) -> dict:
    classify = _validated_script_path("classify_guard_maturity.py")
    cmd = [sys.executable, str(classify)]
    if treat_unseen_as_inert:
        cmd.append("--treat-unseen-as-inert")
    proc = subprocess.run(
        cmd,
        input=json.dumps(summary),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return _parse_subprocess_json(proc.stdout, "classify_guard_maturity.py")


def _format_table(report: dict) -> str:
    rows = sorted(
        report.values(),
        key=lambda r: (TIER_ORDER.get(r["tier"], 99), -r["intercepts"], r["guard"]),
    )
    if not rows:
        return "(no guards in report)\n"
    header = f"{'tier':<11} {'guard':<22} {'intercepts':>10} {'fitness':>7} {'age_days':>9}"
    lines = [header, "-" * len(header)]
    for r in rows:
        age = r.get("days_since_first_event")
        age_s = f"{age:.1f}" if isinstance(age, (int, float)) else "n/a"
        lines.append(
            f"{r['tier']:<11} {r['guard']:<22} {r['intercepts']:>10} "
            f"{r['fitness']:>+7.2f} {age_s:>9}"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the guard maturity report (aggregate + classify).",
    )
    parser.add_argument(
        "--guard",
        action="append",
        default=None,
        help=("Guard name to include even with zero events. Repeatable. "
              "Defaults cover M2-M5."),
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Override telemetry source path (file or directory).",
    )
    parser.add_argument(
        "--treat-unseen-as-inert",
        action="store_true",
        help="Mark guards with no events as Inert instead of Budding.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSON instead of the human-readable table.",
    )
    args = parser.parse_args(argv)

    if args.guard is None:
        args.guard = [
            "markdown-lint",
            "manifest-count",
            "pr-description",
            "session-log",
        ]

    summary = _run_aggregate(args.guard, args.source)
    report = _run_classify(summary, args.treat_unseen_as_inert)

    if args.json:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(_format_table(report))
        # Stash the raw JSON on stderr so callers can capture both.
        json.dump(report, sys.stderr, indent=2, sort_keys=True)
        sys.stderr.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
