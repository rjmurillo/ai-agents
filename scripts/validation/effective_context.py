#!/usr/bin/env python3
# ruff: noqa: E402
"""Report which instruction files a harness loads for one target path.

Issue #4880: no command reported path-local effective context. A maintainer
ran ``wc -c`` on candidate files and guessed which ones a harness actually
loads; the issue that motivated this module names that guess as wrong, and
``.github/AGENTS.md`` regrew from 5,008 to 24,932 bytes with no gate noticing
(see SPEC-4880-path-local-effective-context.md, Q5). This module resolves,
per harness, the set of files a target path actually loads, tagged by layer
(root, nested, scoped, user), and ratchets the nested ("path-local") layer for
five frozen targets so that growth is visible in CI.

Exit codes follow ADR-035:
    0 - Success (report printed, or --ci found every ceiling within budget,
        or --observe found no mismatch)
    1 - Logic error (--ci ceiling breach, or --observe mismatch)
    2 - Configuration error (missing --target/--harness, target escapes the
        repository, invalid --rev, or --observe combined with --rev or with
        --harness claude)
    3 - External error (the `copilot` binary is absent, or `copilot
        instruction list --json` timed out)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_PACKAGE_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
if _VALIDATION_PACKAGE_SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))  # pragma: no cover - already on path under pytest

from scripts.validation.effective_context_resolvers import (
    EffectiveContextResult,
    InvalidRevError,
    Repo,
    TargetOutsideRepoError,
    copilot_static_paths_unfiltered,
    resolve_base_directory,
    resolve_effective_context,
)
from scripts.validation.instruction_budget_globs import UnsupportedApplyToError

# Frozen targets from SPEC-4880-path-local-effective-context.md, "Frozen
# targets" table. Each exercises a different depth and a different nested
# file combination (workflow under two directories, script under two, agent
# template under three for Claude's src/ split).
FROZEN_TARGETS: tuple[str, ...] = (
    ".github/workflows/pr-validation.yml",
    "scripts/validation/pre_pr.py",
    "build/scripts/build_all.py",
    "templates/agents/analyst.shared.md",
    "src/claude/agents/analyst.md",
)

HARNESSES: tuple[str, ...] = ("claude", "copilot")

# These are LOCAL, NON-REGRESSION ceilings measured at the accepted state on
# the commit where SPEC-4880 seeded them (this module's own first commit,
# `git log -1 --format=%H -- scripts/validation/effective_context.py`).
# Anthropic and GitHub publish no 25 KB, 200-line, or 50-line hard limit for
# CLAUDE.md or AGENTS.md; no vendor size limit is implied by any value below.
# Lower a ceiling when the nested corpus shrinks; never raise one without
# recording why in the same change.
CEILING_LABEL: str = (
    "These are local, non-regression ceilings measured at the accepted "
    "state on the commit where they were set. No vendor (Anthropic, "
    "GitHub) publishes a size limit for CLAUDE.md or AGENTS.md; no vendor "
    "limit is implied by any ceiling value."
)

CEILINGS_BYTES: dict[tuple[str, str], int] = {
    (".github/workflows/pr-validation.yml", "claude"): 5_190,
    (".github/workflows/pr-validation.yml", "copilot"): 5_190,
    ("scripts/validation/pre_pr.py", "claude"): 4_141,
    ("scripts/validation/pre_pr.py", "copilot"): 4_141,
    ("build/scripts/build_all.py", "claude"): 5_807,
    ("build/scripts/build_all.py", "copilot"): 5_807,
    ("templates/agents/analyst.shared.md", "claude"): 5_923,
    ("templates/agents/analyst.shared.md", "copilot"): 5_923,
    # Claude loads only `src/AGENTS.md` and `src/CLAUDE.md`: `src/claude/`
    # has no `CLAUDE.md`, so Claude Code's own loading model (imports only
    # follow from a `CLAUDE.md`) never reaches `src/claude/AGENTS.md`.
    # Copilot's directory-chain rule needs no import, reads AGENTS.md/CLAUDE.md
    # directly per directory, and so also counts `src/claude/AGENTS.md`. This
    # asymmetry is why SPEC-4880 picked this target: it exercises the one
    # place the two harnesses' nested layers genuinely diverge.
    ("src/claude/agents/analyst.md", "claude"): 3_183,
    ("src/claude/agents/analyst.md", "copilot"): 6_376,
}


class CopilotUnavailableError(RuntimeError):
    """`copilot` is not on PATH, or `instruction list --json` timed out."""


def _resolve_for_harnesses(
    repo_root: Path,
    target: str,
    harness: str,
    *,
    rev: str | None,
    include_user: bool,
) -> list[EffectiveContextResult]:
    """Resolve one or both harnesses for ``target``, per ``--harness``."""
    selected = HARNESSES if harness == "both" else (harness,)
    return [
        resolve_effective_context(repo_root, target, one, rev=rev, include_user=include_user)
        for one in selected
    ]


def _normalize_source_path(repo_root: Path, raw: str) -> str:
    """Fold a `copilot instruction list` sourcePath to a repo-relative POSIX path.

    Handles an absolute path under the repository root; a path already
    relative is returned with backslashes folded to forward slashes and any
    leading `./` stripped. `--observe`'s live run (T4/T9) is the only way to
    confirm the real shape `sourcePath` takes; this normalizer is written
    defensively for both an absolute and an already-relative form because no
    live sample was available before this module's first commit.
    """
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return candidate.as_posix()
    return raw.replace("\\", "/").removeprefix("./")


def run_copilot_observe(
    repo_root: Path, target_directory: str, static_paths: set[str]
) -> tuple[bool, list[str], list[str]]:
    """Compare Copilot CLI's live listing with the static set (REQ-3).

    Runs `copilot instruction list --json` with cwd set to the target's
    directory (repo root when the target is at the root). Compares every
    non-user `sourcePath` against `static_paths`, which the caller builds
    from `copilot_static_paths_unfiltered` (every repository instructions
    file, before the `applyTo` filter, per REQ-3's own wording: "Copilot
    lists every instruction file; applyTo is applied at edit time").

    Raises `CopilotUnavailableError` when the binary is absent or the call
    times out (ADR-035 exit code 3).
    """
    cwd = repo_root / target_directory if target_directory else repo_root
    try:
        result = subprocess.run(
            ["copilot", "instruction", "list", "--json"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        msg = "the `copilot` binary is not on PATH"
        raise CopilotUnavailableError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = "`copilot instruction list --json` timed out after 60s"
        raise CopilotUnavailableError(msg) from exc
    if result.returncode != 0:
        msg = f"`copilot instruction list --json` exited {result.returncode}: {result.stderr}"
        raise CopilotUnavailableError(msg)
    entries = json.loads(result.stdout)
    observed = {
        _normalize_source_path(repo_root, entry["sourcePath"])
        for entry in entries
        if entry.get("location") != "user" and entry.get("sourcePath")
    }
    missing = sorted(static_paths - observed)
    extra = sorted(observed - static_paths)
    return (not missing and not extra), missing, extra


def _to_json(results: list[EffectiveContextResult]) -> list[dict[str, object]]:
    return [
        {
            "target": r.target,
            "harness": r.harness,
            "files": [dataclasses.asdict(f) for f in r.files],
            "problems": [dataclasses.asdict(p) for p in r.problems],
            "totals": {
                "repo_total_bytes": r.repo_total_bytes,
                "path_local_bytes": r.path_local_bytes,
                "user_total_bytes": r.user_total_bytes,
            },
        }
        for r in results
    ]


def _format_table(results: list[EffectiveContextResult]) -> str:
    lines: list[str] = []
    for r in results:
        lines.append(f"== {r.harness} :: {r.target} ==")
        lines.append(f"{'layer':<8} {'bytes':>8}  path (reason)")
        for f in sorted(r.files, key=lambda item: (item.layer, item.path)):
            lines.append(f"{f.layer:<8} {f.size_bytes:>8}  {f.path} ({f.reason})")
        for p in r.problems:
            lines.append(f"PROBLEM  {p.kind:<13}  {p.location} -> {p.target}")
        lines.append(
            f"totals: repo={r.repo_total_bytes} path_local={r.path_local_bytes} "
            f"user={r.user_total_bytes}"
        )
        lines.append("")
    return "\n".join(lines).rstrip()


def check_ceilings(
    repo_root: Path, ceilings: dict[tuple[str, str], int]
) -> tuple[bool, list[str], list[str]]:
    """Resolve every (target, harness) in ``ceilings`` and report breaches.

    Returns ``(ok, report_lines, failure_lines)``. Split from ``_run_ci`` so a
    test can exercise the ratchet logic against a synthetic fixture tree and
    a small ``ceilings`` dict, instead of only against the real repository and
    :data:`CEILINGS_BYTES` (REQ-6's "a synthetic growth fixture fails").
    """
    report: list[str] = []
    failures: list[str] = []
    for (target, harness), ceiling in ceilings.items():
        result = resolve_effective_context(repo_root, target, harness)
        used = result.path_local_bytes
        status = "PASS" if used <= ceiling else "FAIL"
        report.append(
            f"{status} {harness:<8} {target:<45} path_local={used:>7} ceiling={ceiling:>7}"
        )
        if used > ceiling:
            failures.append(
                f"{harness} {target}: path-local bytes {used} exceed ceiling {ceiling}. "
                "Run `uv run python -m scripts.validation.effective_context "
                f"--target {target} --harness {harness}` to see the inventory."
            )
    return not failures, report, failures


def _run_ci(repo_root: Path) -> int:
    """Check all ten frozen (target, harness) ceilings (REQ-6)."""
    try:
        ok, report, failures = check_ceilings(repo_root, CEILINGS_BYTES)
    except UnsupportedApplyToError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    for line in report:
        print(line)
    print()
    if not ok:
        print("FAIL: path-local effective-context ratchet breached.")
        for line in failures:
            print(line)
        return 1
    print("PASS: every path-local effective-context ceiling holds.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report path-local effective instruction context per target path.",
    )
    parser.add_argument("--target", help="Repository-relative target path.")
    parser.add_argument(
        "--harness", choices=("claude", "copilot", "both"), help="Which harness to resolve."
    )
    parser.add_argument("--rev", default=None, help="Read every file at this git ref.")
    parser.add_argument(
        "--observe",
        action="store_true",
        help="Compare the static Copilot set with a live `copilot instruction list --json`.",
    )
    parser.add_argument(
        "--include-user", action="store_true", help="Also report the per-developer user layer."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON records.")
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Check all ten frozen (target, harness) ceilings; ignores --target/--harness.",
    )
    return parser


def main(argv: list[str] | None = None, *, repo_root: Path | None = None) -> int:
    """CLI entry point. ``repo_root`` defaults to this repository (test hook)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = repo_root or _PROJECT_ROOT

    if args.ci:
        return _run_ci(repo_root)

    if not args.target or not args.harness:
        parser.error("--target and --harness are required unless --ci is set")
    if args.observe and args.rev:
        parser.error("--observe cannot be combined with --rev")
    if args.observe and args.harness == "claude":
        parser.error("--observe requires --harness copilot or both")

    try:
        results = _resolve_for_harnesses(
            repo_root, args.target, args.harness, rev=args.rev, include_user=args.include_user
        )
    except TargetOutsideRepoError as exc:
        print(f"Error: target escapes the repository: {exc}", file=sys.stderr)
        return 2
    except InvalidRevError as exc:
        print(f"Error: --rev does not resolve to a commit: {exc}", file=sys.stderr)
        return 2
    except UnsupportedApplyToError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    observe_ok = True
    observe_missing: list[str] = []
    observe_extra: list[str] = []
    if args.observe:
        static_repo = Repo(repo_root, None)
        base_dir = resolve_base_directory(static_repo, args.target)
        static_paths = copilot_static_paths_unfiltered(static_repo, base_dir)
        try:
            observe_ok, observe_missing, observe_extra = run_copilot_observe(
                repo_root, base_dir, static_paths
            )
        except CopilotUnavailableError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 3

    if args.json:
        payload = _to_json(results)
        if args.observe:
            payload_observe: dict[str, object] = {
                "match": observe_ok,
                "missing": observe_missing,
                "extra": observe_extra,
            }
            print(json.dumps({"results": payload, "observe": payload_observe}, indent=2))
        else:
            print(json.dumps(payload, indent=2))
    else:
        print(_format_table(results))
        if args.observe:
            print()
            print("Copilot --observe: " + ("MATCH" if observe_ok else "MISMATCH"))
            if observe_missing:
                print(f"missing (static but not observed): {observe_missing}")
            if observe_extra:
                print(f"extra (observed but not static): {observe_extra}")

    if args.observe and not observe_ok:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via `main()` directly in tests
    raise SystemExit(main())
