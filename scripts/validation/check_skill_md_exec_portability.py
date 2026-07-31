#!/usr/bin/env python3
"""Exec-path vendor-portability ratchet for skill instruction files (issue #2838).

Companion to ``check_skill_md_portability.py``. That validator counts *prose*
references to upstream-only trees (``.agents/``, ``.claude/lib/``,
``.claude/review-axes/``) after stripping fenced code, and it deliberately
excludes ``.claude/skills/`` because a bare prose cross-link to a sibling skill
resolves through the install root. This validator is the INVERSE: it looks for
*executable* invocations of ``.claude/skills/...`` scripts, which the prose
guard erases when it strips code fences.

Why a separate check (issue #2837 is the instance, #2838 the systemic gap):
  In a vendored plugin install the skill tree is rooted at the harness plugin
  root, not at ``./.claude``. A command written as

      python3 .claude/skills/github/scripts/pr/test_pr_merge_ready.py --pull-request 1

  hard-codes the upstream layout. Under Claude Code it happens to work because
  the checkout root IS ``.claude``; under GitHub Copilot CLI (or any consumer
  repo that vendored the plugin) ``./.claude/skills/...`` does not exist and the
  command fails. The portable form resolves the root through a harness env var
  with a source-tree fallback, e.g.::

      SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr"
      python3 "$SCRIPTS_DIR/test_pr_merge_ready.py" --pull-request 1

  This mirrors the form other skills already ship
  (``.claude/skills/github/SKILL.md``,
  ``.claude/skills/pr-comment-responder/SKILL.md``,
  ``.claude/commands/push-pr.md``).

What it counts:
  Executable invocations of a bare ``.claude/skills/...`` script inside skill
  instruction Markdown. The scan covers ``SKILL.md``, ``references/**/*.md``,
  and ``scripts/README-*.md`` under each skill root. An invocation is either
  (a) a shell interpreter token
  (``python``, ``python3``, ``bash``, ``sh``), optionally followed by short
  options (``python3 -u ...``), then a bare ``.claude/skills/<path>`` ending in
  ``.py`` or ``.sh``, or (b) a direct ``./``-prefixed executable
  (``./.claude/skills/x/y.sh``). The lead-in must be a standalone token
  (start of line, whitespace, backtick, or a shell operator such as ``|`` or
  ``&&`` precedes it) so that ``bash`` does not match the ``sh`` inside another
  word. Shell line continuations (a trailing backslash before a newline) are
  joined before matching so a split invocation is still counted. Path references
  that route through a resolved variable
  (``"$SCRIPTS_DIR/..."`` or ``"${CLAUDE_PLUGIN_ROOT:-.claude}/..."``) do NOT
  match: the literal substring is ``.claude}/skills`` (a ``}`` breaks the
  ``.claude/skills`` sequence) and there is no interpreter-then-bare-path shape.
  Prose cross-links (``see .claude/skills/x/SKILL.md``) do NOT match: no
  execution lead-in and the target is not a ``.py``/``.sh`` script.

Machine-readable opt-out (mirrors the prose guard's escape hatch, but distinct):
  A skill that genuinely must invoke a bare upstream path can DECLARE it with
  the HTML comment marker

      <!-- vendor-portability-exec: <free text> -->

  A file containing the marker is suppressed (count 0). The marker is
  DELIBERATELY distinct from the prose guard's ``vendor-portability`` marker:
  a file that declared a prose ``.agents/`` dependency for the sibling guard
  did not thereby consent to exempting its executable ``.claude/skills/...``
  invocations, which are a different, independently-migratable concern. The
  marker is a reviewable act; a silent bare invocation is not.

Baseline ratchet:
  Every current offender is grandfathered in
  ``skill_md_exec_portability_baseline.json``. The check FAILS only when a
  file's count rises above its baseline (new drift) or a previously-clean file
  introduces an invocation. It REPORTS when counts drop so the baseline can be
  tightened with ``--update-baseline``. This is the same incremental-migration
  philosophy as the sibling script/markdown guards: block regressions now,
  migrate the grandfathered offenders skill-by-skill over time.

Scope: ``SKILL.md``, ``references/**/*.md``, and ``scripts/README-*.md`` under
``.claude/skills/`` and ``src/copilot-cli/skills/`` (both shipped trees).
Roots that do not exist are skipped.

Exit codes (ADR-035):
  0 - no drift (counts at or below baseline), or --update-baseline wrote the file
  1 - drift detected (a file exceeds its baseline or a new file offends)
  2 - configuration error (no scan roots, baseline unreadable)
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

# Shipped skill trees to scan. Both carry SKILL.md files that agents execute:
# .claude/skills is the canonical tree; src/copilot-cli/skills holds the
# generated twins plus copilot-cli-native skills (e.g. pr-autofix).
SCAN_ROOTS: tuple[tuple[str, ...], ...] = (
    (".claude", "skills"),
    ("src", "copilot-cli", "skills"),
)

# Executable invocation of a bare .claude/skills or scripts/ path.
# Two lead-ins: (1) interpreter token (python/python3/bash/sh) with optional
# short options, (2) direct ./ executable. Negative lookbehind keeps the
# lead-in standalone so "sh" inside "bash" does not match. Line continuations
# are normalized before matching (#2838). scripts/ added in #4013.
# CAUTION: the ./ branch covers `./scripts/` forms independently of the
# interpreter branch; do not merge them or drop `scripts/` from either.
# Both mutations are pinned by TestDotSlashScriptsExecDetection (#4029).
EXEC_PATTERN = re.compile(
    r"(?<![\w.])(?:(?:python3?|bash|sh)\s+(?:-\S+\s+)*|\./)"
    r"[\"']?(?:\.claude/skills/|scripts/)\S+\.(?:py|sh)(?!\.\w)[\"']?"
)

# Skill-relative script invocations: ``python3 scripts/foo.py`` (issue #3916).
_SKILL_REL_SCRIPT_PAT = re.compile(
    r"(?<![\w.])(?:python3?|bash|sh)\s+(?:-\S+\s+)*"
    r"[\"']?([a-zA-Z0-9_][a-zA-Z0-9_./-]*/[a-zA-Z0-9_./-]*\.(?:py|sh))[\"']?(?!\.\w)"
)

# Shell line-continuation: collapse backslash-newline to a space (#2838).
_CONTINUATION_PATTERN = re.compile(r"\\\r?\n[ \t]*")

# Escape hatch: ``<!-- vendor-portability-exec: <reason> -->`` suppresses a
# file. Distinct from the prose guard's marker (issue #2838).
_MARKER_PATTERN = re.compile(
    r"<!--\s*vendor-portability-exec\s*:.*?-->",
    re.IGNORECASE | re.DOTALL,
)

_DEFAULT_BASELINE_NAME = "skill_md_exec_portability_baseline.json"

SKILL_FILE_NAME = "SKILL.md"
SCAN_FILE_PATTERNS: tuple[str, ...] = (
    SKILL_FILE_NAME,
    "references/**/*.md",
    "scripts/README-*.md",
)


def _repo_root(start: Path) -> Path:
    """Walk up from ``start`` to the repo root (the dir containing .claude/skills)."""
    base = start if start.is_dir() else start.parent
    for ancestor in (base, *base.parents):
        if (ancestor / ".claude" / "skills").is_dir():
            return ancestor
    return base


def has_portability_marker(text: str) -> bool:
    """Return True if the file self-declares an intentional bare invocation."""
    return _MARKER_PATTERN.search(text) is not None


def find_skill_relative_scripts(text: str) -> list[str]:
    """Return skill-relative script paths; empty when portability-exec marker present (#3916)."""
    if has_portability_marker(text):
        return []
    joined = _CONTINUATION_PATTERN.sub(" ", text)
    return _SKILL_REL_SCRIPT_PAT.findall(joined)


def _scan_skill_for_dangling(
    paths: list[Path],
    skill_root: Path,
    repo_root: Path,
    seen: set[tuple[str, str]],
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for path in paths:
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise OSError(f"Failed to read {path}: {exc}") from exc
        rel = path.relative_to(repo_root).as_posix()
        for script_path in find_skill_relative_scripts(text):
            if (skill_root / script_path).is_file() or (repo_root / script_path).is_file():
                continue
            key = (rel, script_path)
            if key not in seen:
                seen.add(key)
                result.append(key)
    return result


def scan_dangling_skill_relative_scripts(repo_root: Path) -> list[tuple[str, str]]:
    """Return ``[(file_rel_path, script_path)]`` for unresolvable script refs (#3916)."""
    seen: set[tuple[str, str]] = set()
    dangling: list[tuple[str, str]] = []
    for parts in SCAN_ROOTS:
        root = repo_root.joinpath(*parts)
        if not root.is_dir():
            continue
        valid = (
            p
            for p in root.iterdir()
            if p.is_dir() and "__pycache__" not in p.parts and (p / SKILL_FILE_NAME).is_file()
        )
        for skill_root in sorted(valid):
            paths = sorted(
                set(itertools.chain.from_iterable(skill_root.glob(p) for p in SCAN_FILE_PATTERNS))
            )
            dangling.extend(_scan_skill_for_dangling(paths, skill_root, repo_root, seen))
    return dangling


def count_exec_invocations(text: str) -> int:
    """Count bare ``.claude/skills`` executable invocations in a SKILL.md."""
    joined = _CONTINUATION_PATTERN.sub(" ", text)
    return len(EXEC_PATTERN.findall(joined))


def count_file_invocations(text: str) -> int:
    """Marker-aware per-file count: 0 when self-declared, else the count."""
    if has_portability_marker(text):
        return 0
    return count_exec_invocations(text)


def _iter_skill_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for skill_root in sorted(p for p in root.iterdir() if p.is_dir()):
        if "__pycache__" in skill_root.parts:
            continue
        if not (skill_root / SKILL_FILE_NAME).is_file():
            continue
        for pattern in SCAN_FILE_PATTERNS:
            paths.extend(
                p
                for p in sorted(skill_root.glob(pattern))
                if p.is_file() and "__pycache__" not in p.parts
            )
    return sorted(dict.fromkeys(paths))


def scan_skill_execs(repo_root: Path) -> dict[str, int]:
    """Return {relative_posix_path: count} for skill Markdown with >0 invocations.

    Paths are relative to the repo root and POSIX-normalized for cross-OS
    stability. Files that self-declare via the marker contribute 0 and are
    omitted. Scan roots that do not exist are skipped.
    """
    counts: dict[str, int] = {}
    for parts in SCAN_ROOTS:
        root = repo_root.joinpath(*parts)
        if not root.is_dir():
            continue
        for path in _iter_skill_files(root):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise OSError(f"Failed to read skill file {path}: {exc}") from exc
            n = count_file_invocations(text)
            if n > 0:
                counts[path.relative_to(repo_root).as_posix()] = n
    return counts


def _load_baseline(path: Path) -> dict[str, int]:
    if not path.is_file():
        raise FileNotFoundError(f"Baseline file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Baseline must be a JSON object")
    files = data["files"] if "files" in data else data
    if not isinstance(files, dict):
        raise ValueError("Baseline 'files' must be a JSON object")

    baseline: dict[str, int] = {}
    for key, value in files.items():
        if value is None:
            raise ValueError(f"Baseline count for {key!r} is null")
        try:
            baseline[str(key)] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Baseline count for {key!r} is not an integer") from exc
    return baseline


def diff_against_baseline(
    current: dict[str, int], baseline: dict[str, int]
) -> tuple[list[str], list[str]]:
    """Return (regressions, improvements) comparing current to baseline."""
    regressions: list[str] = []
    for rel, n in sorted(current.items()):
        allowed = baseline.get(rel, 0)
        if n > allowed:
            regressions.append(
                f"{rel}: {n} bare '.claude/skills/...' or 'scripts/...' invocation(s) "
                f"(baseline {allowed}). For a '.claude/skills/...' invocation, resolve "
                "the script root via a plugin-root env var "
                'with a source fallback, e.g. SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:'
                '-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/..." then invoke '
                "\"$SCRIPTS_DIR/script.py\". A 'scripts/...' invocation has no such "
                "resolved form: that tree is upstream-only and ships in neither "
                "plugin root, so drop the invocation instead. Either kind may be "
                "declared as an intentional dependency "
                "with '<!-- vendor-portability-exec: ... -->' (issue #2838, #4013)."
            )
    improvements: list[str] = []
    for rel, allowed in sorted(baseline.items()):
        n = current.get(rel, 0)
        if n < allowed:
            improvements.append(f"{rel}: {n} invocations (baseline {allowed})")
    return regressions, improvements


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: walk up for .claude/skills).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help=f"Baseline JSON (default: scripts/validation/{_DEFAULT_BASELINE_NAME}).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the baseline to the current state and exit 0.",
    )
    parser.add_argument(
        "--output-format",
        choices=("human", "json"),
        default="human",
    )
    return parser


def _resolve_root(repo_root: Path | None) -> Path:
    if repo_root:
        return repo_root.expanduser().resolve()
    return _repo_root(Path(__file__).resolve())


def _resolve_baseline_path(root: Path, baseline: Path | None) -> Path | None:
    if baseline is None:
        return root / "scripts" / "validation" / _DEFAULT_BASELINE_NAME
    resolved = baseline.expanduser()
    if not resolved.is_absolute():
        resolved = root / resolved
    resolved = resolved.resolve()
    if not resolved.is_relative_to(root.resolve()):
        return None
    return resolved


def _write_baseline(baseline_path: Path, current: dict[str, int]) -> int:
    total = sum(current.values())
    baseline_path.write_text(
        json.dumps(
            {
                "_comment": (
                    "Exec-path vendor-portability ratchet baseline for skill "
                    "Markdown files (issues #2838, #4013). Counts of bare "
                    "'.claude/skills/...' or 'scripts/...' executable "
                    "invocations per file "
                    "under SKILL.md, references/**/*.md, and scripts/README-*.md "
                    "(files with a '<!-- vendor-portability-exec: ... -->' marker "
                    "excluded). Generated by "
                    "check_skill_md_exec_portability.py --update-baseline. "
                    "Lower is better; migrate '.claude/skills/...' offenders to "
                    "the "
                    "'${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}' "
                    "resolved form and tighten this baseline. The 'scripts/' "
                    "tree is upstream-only and has no resolved form: drop the "
                    "invocation or declare it with a "
                    "'<!-- vendor-portability-exec: ... -->' marker."
                ),
                "files": dict(sorted(current.items())),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Baseline written: {len(current)} files, {total} invocations.")
    return 0


def _has_scan_root(root: Path) -> bool:
    return any(root.joinpath(*parts).is_dir() for parts in SCAN_ROOTS)


def _print_report(
    output_format: str,
    regressions: list[str],
    improvements: list[str],
    dangling: list[tuple[str, str]],
    current: dict[str, int],
    baseline: dict[str, int],
) -> None:
    if output_format == "json":
        print(
            json.dumps(
                {
                    "regressions": regressions,
                    "improvements": improvements,
                    "current_total": sum(current.values()),
                    "baseline_total": sum(baseline.values()),
                },
                indent=2,
            )
        )
        return

    if improvements:
        print("Portability improved (tighten the baseline with --update-baseline):")
        for line in improvements:
            print(f"  [IMPROVED] {line}")
    if regressions:
        print("Skill exec-path vendor-portability drift detected (issue #2838, #4013):")
        for line in regressions:
            print(f"  [DRIFT] {line}")
    if dangling:
        print(
            "Skill-relative scripts resolving nowhere (#3916).\n"
            "Suppress with '<!-- vendor-portability-exec: ... -->' if intentional:"
        )
        for rel_file, script in dangling:
            print(f"  [DANGLING] {rel_file}: {script!r}")
        return
    print(
        f"No skill exec-path vendor-portability drift. "
        f"{sum(current.values())} grandfathered invocations across "
        f"{len(current)} files (baseline {sum(baseline.values())})."
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _resolve_root(args.repo_root)

    if not _has_scan_root(root):
        print(
            f"No skill scan roots found under {root} "
            f"({', '.join('/'.join(p) for p in SCAN_ROOTS)}).",
            file=sys.stderr,
        )
        return 2

    baseline_path = _resolve_baseline_path(root, args.baseline)
    if baseline_path is None:
        print(
            f"--baseline path is outside the repository root, rejecting: {args.baseline}",
            file=sys.stderr,
        )
        return 2

    try:
        current = scan_skill_execs(root)
    except OSError as exc:
        print(f"Could not scan skill files under {root}: {exc}", file=sys.stderr)
        return 2

    if args.update_baseline:
        return _write_baseline(baseline_path, current)

    try:
        baseline = _load_baseline(baseline_path)
    except (OSError, ValueError) as exc:
        print(f"Could not read baseline {baseline_path}: {exc}", file=sys.stderr)
        return 2

    regressions, improvements = diff_against_baseline(current, baseline)
    _print_report(args.output_format, regressions, improvements, current, baseline)

    try:
        dangling = scan_dangling_skill_relative_scripts(root)
    except OSError as exc:
        print(f"Could not scan skill files under {root}: {exc}", file=sys.stderr)
        dangling = []

    _print_report(args.output_format, regressions, improvements, dangling, current, baseline)

    return 1 if (regressions or dangling) else 0


if __name__ == "__main__":
    sys.exit(main())
