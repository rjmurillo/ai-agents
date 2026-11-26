#!/usr/bin/env python3
"""Gate: Python copy/paste duplication may not grow.

Runs jscpd (token-based copy/paste detector) over every tracked Python source
the repository authors, using ``.jscpd.json``. Generated mirror trees are
ignored there by name, because each has a canonical source that stays in scope.

Existing duplication is recorded in ``.jscpd-baseline.json`` (jscpd clone
fingerprints with occurrence counts). The gate is a shrink-only ratchet:

  * a clone whose fingerprint is absent from the baseline, or that occurs more
    often than recorded, fails (new duplication);
  * a baseline entry that no longer occurs fails until ``--prune`` removes it,
    so a burn-down is locked in;
  * ``--prune`` can only remove or lower entries. It never adds or raises one.

With ``--base-ref`` the ceiling is the baseline at the fork point of HEAD and
that ref, intersected with the working-tree baseline. A branch that hand-edits
the baseline to cover its own new duplication still fails (same loophole closed
as ``check_nl_structural_debt.py``, issue #6506).

The jscpd runner is the locked npm package's JavaScript entry point under the
repository's ``node_modules``. The environment cannot choose the executable
(CWE-426); tests patch ``resolve_runner``. The checker never downloads tools.

Exit codes (ADR-035):
    0 - Success (no new duplication and no stale baseline entry)
    1 - Logic error (new duplication, or stale baseline entries)
    2 - Config error (bad root, missing or invalid config/baseline, no runner)
    3 - External error (jscpd or git failed, or timed out)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAME = ".jscpd.json"
BASELINE_NAME = ".jscpd-baseline.json"
BASELINE_VERSION = 1
RUN_TIMEOUT_SECONDS = 600
MAX_REPORTED = 40

Fingerprints = dict[str, int]


class GateError(Exception):
    """A failure with the exit code the gate should return."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Delta:
    """Difference between the recorded ceiling and the current scan."""

    grown: Fingerprints
    stale: Fingerprints


def parse_baseline(text: str, source: str) -> Fingerprints:
    """Parse jscpd baseline JSON, rejecting any shape the gate cannot trust."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GateError(f"{source}: invalid JSON: {exc}", 2) from exc
    prints = data.get("fingerprints") if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("version") != BASELINE_VERSION:
        raise GateError(f"{source}: expected an object with version {BASELINE_VERSION}", 2)
    if not isinstance(prints, dict) or not all(
        isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v > 0
        for k, v in prints.items()
    ):
        raise GateError(f"{source}: 'fingerprints' must map strings to positive integers", 2)
    return dict(prints)


def render_baseline(prints: Fingerprints) -> str:
    return (
        json.dumps(
            {"version": BASELINE_VERSION, "fingerprints": dict(sorted(prints.items()))}, indent=2
        )
        + "\n"
    )


def compute_ceiling(working: Fingerprints, base: Fingerprints | None) -> Fingerprints:
    """Intersect the working baseline with the base-ref baseline (lowest wins)."""
    if base is None:
        return dict(working)
    return {fp: min(count, base[fp]) for fp, count in working.items() if fp in base}


def diff_against_ceiling(ceiling: Fingerprints, current: Fingerprints) -> Delta:
    grown = {fp: n for fp, n in current.items() if n > ceiling.get(fp, 0)}
    stale = {fp: n for fp, n in ceiling.items() if current.get(fp, 0) < n}
    return Delta(grown=grown, stale=stale)


def pruned(working: Fingerprints, current: Fingerprints) -> Fingerprints:
    """Baseline after a burn-down: never adds a key or raises a count."""
    return {fp: min(n, current[fp]) for fp, n in working.items() if fp in current}


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}


def resolve_runner(root: Path) -> list[str]:
    """Return the repo-local jscpd command; nothing outside ``root`` is consulted."""
    local = root / "node_modules" / "jscpd" / "run-jscpd.js"
    if local.is_file():
        return ["node", str(local)]
    raise GateError("no locked jscpd runner: run 'npm ci --ignore-scripts' first", 2)


def _run(cmd: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RUN_TIMEOUT_SECONDS,
            env={**_clean_env(), "JSCPD_NO_TIPS": "1", "NO_COLOR": "1"},
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GateError(f"cannot run {cmd[0]}: {exc}", 3) from exc


def scan(root: Path, runner: list[str], ceiling: Fingerprints) -> tuple[Fingerprints, int]:
    """Scan once and return current fingerprints, using a scratch baseline file."""
    with tempfile.TemporaryDirectory(prefix="jscpd-gate-") as tmp:
        scratch = Path(tmp) / "baseline.json"
        scratch.write_text(render_baseline(ceiling), encoding="utf-8")
        result = _run(
            [
                *runner,
                "-c",
                CONFIG_NAME,
                "-r",
                "json",
                "-o",
                tmp,
                "-s",
                "--fail-on-empty",
                "--baseline",
                str(scratch),
                "--update-baseline",
            ],
            root,
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip().splitlines()[-5:]
            raise GateError(f"jscpd exited {result.returncode}: {' | '.join(tail)}", 3)
        try:
            report = json.loads((Path(tmp) / "jscpd-report.json").read_text(encoding="utf-8"))
            sources = report["statistics"]["total"]["sources"]
            if type(sources) is not int or sources <= 0:
                raise ValueError("source count must be a positive integer")
            fingerprints = parse_baseline(scratch.read_text(encoding="utf-8"), "jscpd scan output")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise GateError(f"invalid jscpd scan output: {exc}", 3) from exc
        return fingerprints, sources


def _clone_location(side: object) -> str:
    if not isinstance(side, dict):
        raise ValueError("clone location must be an object")
    name, start, end = (side.get(key) for key in ("name", "start", "end"))
    if not isinstance(name, str) or not name.strip():
        raise ValueError("clone location name must be a nonempty string")
    if type(start) is not int or type(end) is not int:
        raise ValueError("clone location bounds must be integers")
    if start <= 0 or end < start:
        raise ValueError("clone location bounds must be positive and ordered")
    return f"{name}:{start}-{end}"


def _clone_row(clone: object) -> str:
    if not isinstance(clone, dict) or type(clone.get("isNew")) is not bool:
        raise ValueError("clone must be an object with a boolean isNew")
    lines = clone.get("lines")
    if type(lines) is not int or lines <= 0:
        raise ValueError("clone lines must be a positive integer")
    first, second = (_clone_location(clone.get(key)) for key in ("firstFile", "secondFile"))
    return f"  {first} <-> {second} ({lines} lines)" if clone["isNew"] else ""


def _clone_report(text: str) -> str:
    report = json.loads(text)
    clones = report.get("duplicates") if isinstance(report, dict) else None
    if not isinstance(clones, list):
        raise ValueError("clone report must contain a duplicates array")
    rows = [row for clone in clones if (row := _clone_row(clone))]
    return "\n".join(["New or grown clones:", *rows[:MAX_REPORTED]]) if rows else ""


def show_new_clones(root: Path, runner: list[str], ceiling: Fingerprints) -> str:
    """List only clones jscpd marks new against the gate's effective ceiling."""
    with tempfile.TemporaryDirectory(prefix="jscpd-gate-") as tmp:
        baseline = Path(tmp) / "baseline.json"
        baseline.write_text(render_baseline(ceiling), encoding="utf-8")
        result = _run(
            [
                *runner,
                "-c",
                CONFIG_NAME,
                "-r",
                "json",
                "-o",
                tmp,
                "-s",
                "--baseline",
                str(baseline),
            ],
            root,
        )
        report = Path(tmp) / "jscpd-report.json"
        if result.returncode != 0:
            raise GateError(f"jscpd diagnostics rerun exited {result.returncode}", 3)
        if not report.is_file():
            raise GateError("jscpd diagnostics rerun wrote no report", 3)
        return _clone_report(report.read_text(encoding="utf-8"))


def _print_new_clones(root: Path, runner: list[str], ceiling: Fingerprints) -> None:
    try:
        details = show_new_clones(root, runner, ceiling)
        if details:
            print(details)
    except (GateError, OSError, ValueError) as exc:
        # Diagnostics cannot replace the already-established duplication failure.
        print(f"WARNING: clone diagnostics unavailable: {exc}", file=sys.stderr)


def base_ref_baseline(root: Path, ref: str) -> Fingerprints | None:
    """Return the baseline at the fork point, or None if the file did not exist there."""
    git = ["git", "-C", str(root)]
    merge_base = _run([*git, "merge-base", "HEAD", ref], root)
    if merge_base.returncode != 0:
        raise GateError(f"git cannot name a fork point with {ref!r}", 3)
    commit = merge_base.stdout.strip()
    exists = _run([*git, "cat-file", "-e", f"{commit}:{BASELINE_NAME}"], root)
    if exists.returncode != 0:
        return None
    shown = _run([*git, "show", f"{commit}:{BASELINE_NAME}"], root)
    if shown.returncode != 0:
        raise GateError(f"git cannot read {BASELINE_NAME} at {commit[:12]}", 3)
    return parse_baseline(shown.stdout, f"{BASELINE_NAME} at {ref}")


def _fail_lines(delta: Delta) -> list[str]:
    lines: list[str] = []
    if delta.grown:
        lines.append(
            f"FAIL: {len(delta.grown)} duplicated block(s) are new or occur more often "
            "than the baseline allows."
        )
        lines.append(
            "Extract the shared code into one function or module. Do not add a baseline entry."
        )
    if delta.stale:
        lines.append(
            f"FAIL: {len(delta.stale)} baseline entr(ies) no longer occur (duplication was "
            "removed or edited)."
        )
        lines.append(f"Lock in the burn-down: {Path(sys.argv[0]).name} --prune")
    return lines


def initialize_baseline(root: Path, runner: list[str], baseline_path: Path) -> int:
    """Bootstrap the baseline once, refusing to overwrite an existing file."""
    if baseline_path.exists():
        raise GateError(f"{BASELINE_NAME} already exists; --init only bootstraps", 2)
    current, sources = scan(root, runner, {})
    baseline_path.write_text(render_baseline(current), encoding="utf-8")
    print(
        f"Wrote {BASELINE_NAME}: {len(current)} existing duplicated block(s) "
        f"recorded across {sources} Python files."
    )
    return 0


def run_gate(root: Path, args: argparse.Namespace) -> int:
    if not (root / CONFIG_NAME).is_file():
        raise GateError(f"{CONFIG_NAME} not found under {root}", 2)
    baseline_path = root / BASELINE_NAME
    runner = resolve_runner(root)

    if args.init:
        return initialize_baseline(root, runner, baseline_path)

    if not baseline_path.is_file():
        raise GateError(f"{BASELINE_NAME} not found; bootstrap with --init", 2)
    working = parse_baseline(baseline_path.read_text(encoding="utf-8"), BASELINE_NAME)
    base = base_ref_baseline(root, args.base_ref) if args.base_ref else None
    ceiling = compute_ceiling(working, base)

    current, sources = scan(root, runner, ceiling)
    print(f"Examined {sources} Python files.")
    delta = diff_against_ceiling(ceiling, current)
    inflated = sum(1 for fp, n in working.items() if n > ceiling.get(fp, 0))

    if args.prune:
        if delta.grown:
            print("\n".join(_fail_lines(Delta(delta.grown, {}))))
            print("Refusing --prune: the baseline may only shrink.")
            return 1
        new_baseline = pruned(working, current)
        baseline_path.write_text(render_baseline(new_baseline), encoding="utf-8")
        removed = len(working) - len(new_baseline)
        print(f"Pruned {removed} stale entr(ies); {len(new_baseline)} remain.")
        return 0

    if delta.grown:
        _print_new_clones(root, runner, ceiling)
    if inflated:
        print(
            f"FAIL: {inflated} baseline entr(ies) are absent from or higher than the "
            f"fork-point baseline at {args.base_ref}. The baseline may not grow."
        )
    lines = _fail_lines(delta)
    if lines or inflated:
        print("\n".join(lines))
        return 1
    print(f"OK: no new Python duplication ({len(current)} existing block(s) in baseline).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo_root", nargs="?", default=None)
    parser.add_argument("--base-ref", help="Cap the baseline at the fork point with this ref.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prune", action="store_true", help="Remove stale entries (shrink-only).")
    mode.add_argument("--init", action="store_true", help="Create the baseline if missing.")
    args = parser.parse_args(argv)
    root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[2]
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 2
    try:
        return run_gate(root.resolve(), args)
    except GateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
