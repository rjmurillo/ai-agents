#!/usr/bin/env python3
"""Markdown vendor-portability ratchet for skill instruction files (issue #2050).

Companion to ``check_skill_portability.py``. That validator scopes to skill
*scripts* (``*.py``, ``*.sh``, ``*.ps1``) and explicitly defers Markdown:

    "Markdown instruction files carry a prose-vs-runtime ambiguity (a maintainer
    note mentioning ``.agents/`` is fine; a runtime instruction to write there is
    not) and are a documented follow-up, not part of this ratchet."

This validator is that follow-up. Issue #2050's worst offenders are SKILL.md and
reference ``.md`` files (34 hits in ``memory/references/troubleshooting.md``, 25
in ``session/SKILL.md``, ...). In a vendored plugin install the consumer repo has
no ``.agents/``, ``.claude/lib/``, or ``.claude/review-axes/`` tree, so an
instruction telling the agent to write to ``.agents/analysis/foo.md`` silently
degrades. This check generalizes the /review REQ-008-06 contract (resolve via
plugin/skill root, the consumer cwd, or a documented env var) to skill prose.

What it counts:
  Upstream-only runtime path references (``.agents/``, ``.claude/lib/``,
  ``.claude/review-axes/``) in a skill ``.md`` file, after stripping:
    * fenced code blocks (``` and ~~~): example commands, not runtime instructions
    * inline code spans (`...`): illustrative paths, not directives
  ``.claude/skills/`` is NOT counted: it is the install-root-relative convention
  the ``paths.py`` helper resolves, mirroring the script ratchet's exclusion.

Machine-readable opt-out (the issue's acceptance criterion):
  A skill that genuinely depends on an upstream path can DECLARE it instead of
  hiding it. A file containing the HTML comment marker

      <!-- vendor-portability: <free text> -->

  is treated as having self-declared its path dependencies; all of its
  references are suppressed (count 0). This satisfies the acceptance criterion
  "declares explicitly in a machine-readable section of SKILL.md which paths it
  depends on" without forcing a migration the maintainer has consciously
  deferred. The marker is a deliberate, reviewable act; silent prose is not.

Baseline ratchet:
  Every current offender is grandfathered in ``skill_md_portability_baseline.json``.
  The check FAILS only when a file's count rises above its baseline (new drift)
  or a previously-clean file introduces references. It REPORTS when counts drop
  so the baseline can be tightened with ``--update-baseline``.

Scope: ``*.md`` under ``.claude/skills/``.

Exit codes:
  0 - no drift (counts at or below baseline), or --update-baseline wrote the file
  1 - drift detected (a file exceeds its baseline or a new file offends)
  2 - configuration error (skills dir missing, baseline unreadable)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Upstream-only runtime path prefixes. Companion to check_skill_portability.py
# which covers script files; this validator covers .md files. The .claude/skills/
# pattern is excluded here: in prose a bare reference to a sibling skill by
# ``.claude/skills/`` resolves through the install root, so it is not an
# upstream-only dependency. ``.agents/``, ``.claude/lib/``, and
# ``.claude/review-axes/`` have no consumer-side analogue.
UPSTREAM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![\\\w.])\.agents(?:[\\/]+|['\"]|$)", re.IGNORECASE),
    re.compile(r"(?<![\\\w.])\.claude[\\/]+lib(?:[\\/]+|['\"]|$)", re.IGNORECASE),
    re.compile(
        r"(?<![\\\w.])\.claude[\\/]+review-axes(?:[\\/]+|['\"]|$)",
        re.IGNORECASE,
    ),
)

# A skill self-declares its upstream path dependencies with this HTML comment.
# When present, the file's references are suppressed (the acceptance-criterion
# escape hatch). Free text after the colon documents which paths and why.
_MARKER_PATTERN = re.compile(
    r"<!--\s*vendor-portability\s*:.*?-->",
    re.IGNORECASE | re.DOTALL,
)

# Regex to detect a fenced code block opening line (CommonMark: 0-3 spaces indent allowed).
_FENCE_OPEN_PATTERN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")

# Inline code spans: `...`. Illustrative, not a directive.
_INLINE_CODE_PATTERN = re.compile(r"`[^`\n]*`")

_DEFAULT_BASELINE_NAME = "skill_md_portability_baseline.json"

MARKDOWN_SUFFIX = ".md"


def _repo_root(start: Path) -> Path:
    """Walk up from ``start`` to the repo root (the dir containing .claude/skills)."""
    base = start if start.is_dir() else start.parent
    for ancestor in (base, *base.parents):
        if (ancestor / ".claude" / "skills").is_dir():
            return ancestor
    return base


def has_portability_marker(text: str) -> bool:
    """Return True if the file self-declares its upstream path dependencies.

    Strips fenced and inline code first so that a marker inside a code example
    is not treated as the real opt-out declaration.
    """
    return _MARKER_PATTERN.search(_strip_code(text)) is not None


def _strip_code(text: str) -> str:
    """Remove fenced code blocks and inline code spans, leaving prose.

    Uses line-by-line processing to correctly handle nested fence examples
    (e.g., a code block that itself contains triple-backtick lines).
    A closing fence must use the same character and be at least as long
    as the opening fence, per CommonMark spec.
    """
    lines = text.split("\n")
    result_lines: list[str] = []
    fence_char: str | None = None
    fence_len = 0

    for line in lines:
        if fence_char is None:
            match = _FENCE_OPEN_PATTERN.match(line)
            if match:
                fence_char = match.group(1)[0]
                fence_len = len(match.group(1))
                result_lines.append("")
            else:
                result_lines.append(line)
        else:
            close_pattern = re.compile(
                r"^[ \t]{0,3}" + re.escape(fence_char) + r"{" + str(fence_len) + r",}\s*$"
            )
            if close_pattern.match(line):
                fence_char = None
                fence_len = 0
                result_lines.append("")
            else:
                result_lines.append("")

    without_fences = "\n".join(result_lines)
    return _INLINE_CODE_PATTERN.sub(" ", without_fences)


def count_upstream_refs(text: str) -> int:
    """Count upstream-only path references in Markdown prose.

    Strips fenced and inline code first so example commands do not count, then
    matches the upstream path prefixes. Does NOT honor the opt-out marker; use
    :func:`count_file_refs` for the marker-aware per-file count.
    """
    prose = _strip_code(text)
    return sum(len(pat.findall(prose)) for pat in UPSTREAM_PATTERNS)


def count_file_refs(text: str) -> int:
    """Marker-aware per-file count: 0 when the file self-declares, else the count.

    The opt-out marker is only recognized in prose (not inside code blocks).
    """
    if has_portability_marker(text):
        return 0
    prose = _strip_code(text)
    return sum(len(pat.findall(prose)) for pat in UPSTREAM_PATTERNS)


def scan_skill_markdown(skills_dir: Path) -> dict[str, int]:
    """Return {relative_posix_path: count} for skill ``.md`` files with >0 refs.

    Paths are relative to the skills dir's parent, so they begin with
    ``skills/`` and stay POSIX-normalized for cross-OS stability. Files that
    self-declare via the marker contribute 0 and are omitted.
    """
    counts: dict[str, int] = {}
    base = skills_dir.parent
    for path in sorted(skills_dir.rglob("*")):
        if not path.is_file() or path.suffix != MARKDOWN_SUFFIX:
            continue
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise OSError(f"Failed to read skill markdown {path}: {exc}") from exc
        n = count_file_refs(text)
        if n > 0:
            counts[path.relative_to(base).as_posix()] = n
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
    """Return (regressions, improvements) comparing current to baseline.

    A regression is a file whose count rose above its baseline, or a file with
    references that is absent from the baseline. An improvement is a file whose
    count dropped (including to zero / removed).
    """
    regressions: list[str] = []
    for rel, n in sorted(current.items()):
        allowed = baseline.get(rel, 0)
        if n > allowed:
            regressions.append(
                f"{rel}: {n} upstream-path refs in prose (baseline {allowed}). "
                "Resolve via plugin/skill root or consumer cwd, or declare the "
                "dependency with an HTML comment marker "
                "'<!-- vendor-portability: ... -->' (issue #2050)."
            )
    improvements: list[str] = []
    for rel, allowed in sorted(baseline.items()):
        n = current.get(rel, 0)
        if n < allowed:
            improvements.append(f"{rel}: {n} refs (baseline {allowed})")
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
        return repo_root.resolve()
    return _repo_root(Path(__file__).resolve())


def _resolve_baseline_path(root: Path, baseline: Path | None) -> Path:
    if baseline is None:
        return root / "scripts" / "validation" / _DEFAULT_BASELINE_NAME
    resolved = (
        baseline.expanduser().resolve()
        if baseline.is_absolute()
        else (root / baseline).expanduser().resolve()
    )
    if not resolved.is_relative_to(root.resolve()):
        return Path("")
    return resolved


def _write_baseline(baseline_path: Path, current: dict[str, int]) -> int:
    total = sum(current.values())
    baseline_path.write_text(
        json.dumps(
            {
                "_comment": (
                    "Vendor-portability ratchet baseline for skill Markdown "
                    "(issue #2050). Counts of upstream-only path references per "
                    ".md file (fenced/inline code stripped; files with a "
                    "'<!-- vendor-portability: ... -->' marker excluded). "
                    "Generated by check_skill_md_portability.py --update-baseline. "
                    "Lower is better; review count increases before committing."
                ),
                "files": dict(sorted(current.items())),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Baseline written: {len(current)} files, {total} refs.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _resolve_root(args.repo_root)
    skills_dir = root / ".claude" / "skills"
    if not skills_dir.is_dir():
        print(f"Skills dir not found: {skills_dir}", file=sys.stderr)
        return 2
    baseline_path = _resolve_baseline_path(root, args.baseline)
    if baseline_path == Path(""):
        print(
            f"--baseline path is outside the repository root, rejecting: {args.baseline}",
            file=sys.stderr,
        )
        return 2

    try:
        current = scan_skill_markdown(skills_dir)
    except OSError as exc:
        print(f"Could not scan skills dir {skills_dir}: {exc}", file=sys.stderr)
        return 2

    if args.update_baseline:
        return _write_baseline(baseline_path, current)

    try:
        baseline = _load_baseline(baseline_path)
    except (OSError, ValueError) as exc:
        print(f"Could not read baseline {baseline_path}: {exc}", file=sys.stderr)
        return 2

    regressions, improvements = diff_against_baseline(current, baseline)

    if args.output_format == "json":
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
    else:
        if improvements:
            print("Portability improved (tighten the baseline with --update-baseline):")
            for line in improvements:
                print(f"  [IMPROVED] {line}")
        if regressions:
            print("Markdown vendor-portability drift detected (issue #2050):")
            for line in regressions:
                print(f"  [DRIFT] {line}")
        else:
            print(
                f"No Markdown vendor-portability drift. "
                f"{sum(current.values())} grandfathered refs across "
                f"{len(current)} files (baseline {sum(baseline.values())})."
            )

    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
