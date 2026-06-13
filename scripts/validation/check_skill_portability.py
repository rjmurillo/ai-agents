#!/usr/bin/env python3
"""Vendor-portability ratchet for skill scripts (issue #2050).

Skill scripts that hard-code upstream-only paths (``.agents/``, ``.claude/lib/``,
``.claude/review-axes/``, ``.claude/skills/``) fail or degrade silently in
vendored plugin installs, where the consumer repo has no such tree and the
plugin lives outside the consumer's working directory. The /review skill's
REQ-008-06 contract (resolve via plugin/skill root, the consumer cwd, or a
documented env var) is the portable pattern; this validator generalizes the
*detection* of violations to all skill scripts.

It is a ratchet, not a hard gate on the existing backlog: every current
reference is grandfathered in a baseline (``skill_portability_baseline.json``),
so the ~30-skill migration can proceed incrementally without blocking unrelated
work. The check FAILS only when a script's reference count exceeds its baseline
(new drift) or a previously-clean script introduces references, and it REPORTS
when counts drop so the baseline can be tightened with ``--update-baseline``.

Scope (v1): scripts (``*.py``, ``*.sh``, ``*.ps1``) under ``.claude/skills/``.
Markdown instruction files carry a prose-vs-runtime ambiguity (a maintainer note
mentioning ``.agents/`` is fine; a runtime instruction to write there is not) and
are a documented follow-up, not part of this ratchet.

EXIT CODES (per .agents/architecture/ADR-035-exit-code-standardization.md):
  Canonical contract:
  | 0 | Success | Operation completed, idempotent skip |
  | 1 | General error / Validation failure | Logic error, assertion failed |
  | 2 | Usage/configuration error | Missing required param, invalid argument, not in git repo |
  | 3 | External service error | GitHub API failure, network error |
  | 4 | Authentication/authorization error | Token expired, permission denied |

This validator uses only the subset below:
  0 - no drift (counts at or below baseline)
  1 - drift detected (a script exceeds its baseline or a new script offends)
  2 - configuration error (skills dir missing, baseline unreadable)
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from pathlib import Path

# Upstream-only runtime path prefixes. A skill script that references these as
# runtime paths assumes the upstream checkout layout and breaks in a vendored
# install. ``.claude/skills/`` is included because a script reaching into a
# sibling skill by that absolute prefix breaks once the plugin root moves.
UPSTREAM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![\\\w.])\.agents(?:[\\/]+|['\"]|$)", re.IGNORECASE),
    re.compile(r"(?<![\\\w.])\.claude[\\/]+lib(?:[\\/]+|['\"]|$)", re.IGNORECASE),
    re.compile(
        r"(?<![\\\w.])\.claude[\\/]+review-axes(?:[\\/]+|['\"]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![\\\w.])\.claude[\\/]+skills(?:[\\/]+|['\"]|$)",
        re.IGNORECASE,
    ),
)
_SPLIT_CLAUDE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(['\"])\.claude\1\s*,\s*(['\"])(?:lib|review-axes|skills)\2",
        re.IGNORECASE,
    ),
    re.compile(
        r"(['\"])\.claude\1(?:\s*\))*\s*/\s*(['\"])(?:lib|review-axes|skills)\2",
        re.IGNORECASE,
    ),
)

SCRIPT_SUFFIXES = (".py", ".sh", ".ps1")

_DEFAULT_BASELINE_NAME = "skill_portability_baseline.json"


def _repo_root(start: Path) -> Path:
    """Walk up from ``start`` to the repo root (the dir containing .claude)."""
    for ancestor in (start, *start.parents):
        if (ancestor / ".claude" / "skills").is_dir():
            return ancestor
    return start


_PYTHON_DOCSTRING_NODES = (
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.FunctionDef,
    ast.Module,
)
_PROSE_KWARGS: frozenset[str] = frozenset(
    {"help", "description", "epilog", "metavar", "usage"}
)


def _python_docstring_spans(text: str) -> set[tuple[int, int, int, int]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()

    spans: set[tuple[int, int, int, int]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, _PYTHON_DOCSTRING_NODES):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if not isinstance(first, ast.Expr):
            continue
        if not isinstance(first.value, ast.Constant) or not isinstance(first.value.value, str):
            continue
        if first.end_lineno is None or first.end_col_offset is None:
            continue
        spans.add((first.lineno, first.col_offset, first.end_lineno, first.end_col_offset))
    return spans


def _python_prose_spans(text: str) -> set[tuple[int, int, int, int]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()

    spans: set[tuple[int, int, int, int]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg not in _PROSE_KWARGS:
                continue
            value = keyword.value
            if value.end_lineno is None or value.end_col_offset is None:
                continue
            spans.add((value.lineno, value.col_offset, value.end_lineno, value.end_col_offset))
    return spans


def _span_contains(
    spans: set[tuple[int, int, int, int]], token: tokenize.TokenInfo
) -> bool:
    start_line, start_col = token.start
    end_line, end_col = token.end
    for span_start_line, span_start_col, span_end_line, span_end_col in spans:
        starts_inside = (start_line, start_col) >= (span_start_line, span_start_col)
        ends_inside = (end_line, end_col) <= (span_end_line, span_end_col)
        if starts_inside and ends_inside:
            return True
    return False


def _strip_hash_comments(text: str) -> str:
    stripped: list[str] = []
    for line in text.splitlines():
        in_single = False
        in_double = False
        escaped = False
        cut_at = len(line)
        for index, char in enumerate(line):
            if escaped:
                escaped = False
                continue
            if char in {"\\", "`"}:
                escaped = True
                continue
            if char == "'" and not in_double:
                in_single = not in_single
                continue
            if char == '"' and not in_single:
                in_double = not in_double
                continue
            if char == "#" and not in_single and not in_double:
                cut_at = index
                break
        stripped.append(line[:cut_at])
    return "\n".join(stripped)


def _runtime_text(text: str, suffix: str) -> str:
    if suffix != ".py":
        return _strip_hash_comments(text)

    ignored_spans = _python_docstring_spans(text) | _python_prose_spans(text)
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        return " ".join(
            token.string
            for token in tokens
            if token.type != tokenize.COMMENT
            and not (token.type == tokenize.STRING and _span_contains(ignored_spans, token))
        )
    except tokenize.TokenError:
        return _strip_hash_comments(text)


def count_upstream_refs(text: str, suffix: str = ".py") -> int:
    """Count upstream-only path references in a single file's text."""
    runtime_text = _runtime_text(text, suffix)
    same_literal_refs = sum(len(pat.findall(runtime_text)) for pat in UPSTREAM_PATTERNS)
    split_component_refs = sum(
        len(pat.findall(runtime_text)) for pat in _SPLIT_CLAUDE_PATTERNS
    )
    return same_literal_refs + split_component_refs


def scan_skill_scripts(skills_dir: Path) -> dict[str, int]:
    """Return {relative_posix_path: count} for skill scripts with >0 refs.

    Paths are relative to the skills dir's parent (so they read
    ``skills/<name>/scripts/<file>``), POSIX-normalized for cross-OS stability.
    """
    counts: dict[str, int] = {}
    base = skills_dir.parent
    for path in sorted(skills_dir.rglob("*")):
        if not path.is_file() or path.suffix not in SCRIPT_SUFFIXES:
            continue
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise OSError(f"Failed to read skill script {path}: {exc}") from exc
        n = count_upstream_refs(text, path.suffix)
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
                f"{rel}: {n} upstream-path refs (baseline {allowed}). "
                "Resolve via plugin/skill root or consumer cwd, not a hard-coded "
                "upstream path (issue #2050)."
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
    if baseline.is_absolute():
        return baseline
    return root / baseline


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _resolve_root(args.repo_root)
    skills_dir = root / ".claude" / "skills"
    if not skills_dir.is_dir():
        print(f"Skills dir not found: {skills_dir}", file=sys.stderr)
        return 2
    baseline_path = _resolve_baseline_path(root, args.baseline)

    try:
        current = scan_skill_scripts(skills_dir)
    except OSError as exc:
        print(f"Could not scan skills dir {skills_dir}: {exc}", file=sys.stderr)
        return 2

    if args.update_baseline:
        total = sum(current.values())
        baseline_path.write_text(
            json.dumps(
                {
                    "_comment": (
                        "Vendor-portability ratchet baseline for skill scripts "
                        "(issue #2050). Counts of upstream-only path references "
                        "per script. Generated by check_skill_portability.py "
                        "--update-baseline. Lower is better; never raise a count."
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
            print("Vendor-portability drift detected (issue #2050):")
            for line in regressions:
                print(f"  [DRIFT] {line}")
        else:
            print(
                f"No vendor-portability drift. "
                f"{sum(current.values())} grandfathered refs across "
                f"{len(current)} scripts (baseline {sum(baseline.values())})."
            )

    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
