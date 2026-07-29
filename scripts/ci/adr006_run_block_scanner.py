#!/usr/bin/env python3
"""ADR-006 run-block scanner: an objective, re-runnable burn-down metric (#3084).

ADR-006 forbids business logic in workflow YAML ``run:`` blocks; the work is
tracked by #2967. That burn-down count ("93 genuine violations") came from a
one-off manual audit and could not be re-run or CI-tracked. This scanner makes
it reproducible: it flags ``run:`` block scalars over a code-line threshold that
also contain logic (conditionals, loops, parsing pipes, computed variables, or
output assembly), the same high-signal heuristic the manual audit used.

It is a METRIC by default (exit 0, prints the count + list). Pass ``--max N`` to
turn it into a ratchet gate that exits 1 when the violation count exceeds N, so
the burn-down cannot silently regress.

Exit codes (AGENTS.md): 0 ok, 1 over --max, 2 config error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_OVER_MAX = 1
EXIT_CONFIG = 2

_DEFAULT_THRESHOLD = 10
_SCAN_GLOBS = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".github/actions/*/action.yml",
)

# A run: key, optionally preceded by a YAML list dash, introducing a block
# scalar (| or >). Inline one-line commands (no block scalar) are single
# commands, not logic blocks, and are skipped.
_RUN_KEY = re.compile(r"^(?P<indent>\s*)(?:-\s+)?run:\s*(?P<scalar>[|>][+-]?\d*)\s*$")

# High-signal logic markers, matching the manual-audit criteria: conditionals,
# loops, parsing pipes, computed variables, and output assembly.
_LOGIC = re.compile(
    r"""(?xm)
    \bif\b | \belif\b | \bfor\b | \bwhile\b | \bcase\b |     # conditionals / loops
    ^\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*= |              # variable assignment
    \$\( |                                                    # command substitution
    \|\s*(?:jq|grep|sed|awk|python3?|cut|tr|head|tail|xargs)\b |  # parsing pipes
    >>?\s*"?\$?\{?\s*GITHUB_(?:OUTPUT|ENV|STEP_SUMMARY)       # output assembly
    """,
)

# A line whose command is a pure output builtin. Its quoted operands are
# message text, not shell source.
_STATIC_OUTPUT_CMD = re.compile(r"^\s*(?:echo|printf)\b")

# One quoted operand, honouring backslash escapes so an escaped quote does not
# end the match early.
_QUOTED_OPERAND = re.compile(r"""(?P<q>["'])(?P<text>(?:\\.|(?!(?P=q)).)*)(?P=q)""")

# Anything that makes a quoted operand evaluate rather than print: command
# substitution, parameter expansion, a bare variable, a special parameter
# (``$?``, ``$$``, ``$@``, ``$1``, and friends), or an unescaped backtick.
# Special parameters matter because blanking an operand that evaluates at
# runtime would undercount logic and make the metric less conservative.
_EXPANSION = re.compile(r"\$[({A-Za-z_?$@*#!0-9-]|(?<!\\)`")


def _blank_static_operands(line: str) -> str:
    """Blank every quoted operand on ``line`` that cannot evaluate."""

    def _blank(match: re.Match[str]) -> str:
        if _EXPANSION.search(match.group("text")):
            return match.group(0)
        return match.group("q") * 2

    return _QUOTED_OPERAND.sub(_blank, line)


def _strip_static_output(line: str) -> str:
    """Blank the message text of an ``echo``/``printf`` operand.

    ``_LOGIC`` matches shell keywords by word boundary, so English prose in a
    remediation message trips it: ``echo "Use forward slashes (/) for
    cross-platform compatibility"`` matches ``\\bfor\\b`` and the whole block is
    reported as business logic in YAML. Six live blocks were flagged this way
    on the words "for" and "if" alone, and the scanner's own contract
    (``test_large_pure_output_block_is_not_flagged``) says a pure output block
    is not a violation. The existing comment-stripping in ``scan_text`` is the
    same idea applied to ``#`` lines.

    Only operands that cannot evaluate are blanked. An operand carrying
    ``$(``, ``${``, ``$VAR``, or an unescaped backtick is left intact, so
    ``echo "$(gh pr list)"`` still reads as logic. Everything outside the
    quotes survives untouched, so a redirect to ``$GITHUB_STEP_SUMMARY``, a
    pipe into ``jq``, and a trailing ``if`` all still match.
    """
    if not _STATIC_OUTPUT_CMD.match(line):
        return line

    return _blank_static_operands(line)


def _strip_static_output_body(lines: Sequence[str]) -> list[str]:
    """Apply :func:`_strip_static_output` across a body, following continuations.

    A message list can span lines: ``printf '%s\\n' \\`` followed by bare
    quoted operands. Those continuation lines carry no command of their own, so
    a per-line check on the leading command never strips them and prose there
    still trips ``_LOGIC``. ``validate-adr-number-uniqueness.yml`` is flagged
    on exactly that shape.

    Continuation state is carried only from an ``echo``/``printf`` command, so
    an operand of any other command is left alone, and it ends at the first
    line without a trailing backslash.
    """
    stripped: list[str] = []
    continuing = False
    for line in lines:
        starts = bool(_STATIC_OUTPUT_CMD.match(line))
        stripped.append(_blank_static_operands(line) if starts or continuing else line)
        continuing = (starts or continuing) and line.rstrip().endswith("\\")
    return stripped


@dataclass(frozen=True, slots=True)
class RunBlock:
    """One ``run:`` block scalar found in a file."""

    line: int  # 1-based line of the run: key
    code_lines: int  # non-blank, non-comment body lines
    has_logic: bool
    body: str


def _body_lines(lines: Sequence[str], start: int, key_indent: int) -> tuple[list[str], int]:
    """Collect the block-scalar body after ``start`` (0-based key index).

    A body line belongs to the block when it is blank or indented deeper than the
    ``run:`` key. Returns (body_lines, next_index).
    """
    body: list[str] = []
    j = start + 1
    while j < len(lines):
        raw = lines[j]
        if raw.strip() == "":
            body.append(raw)
            j += 1
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent > key_indent:
            body.append(raw)
            j += 1
        else:
            break
    return body, j


def _count_code_lines(body: Iterable[str]) -> int:
    """Non-blank body lines that are not pure comments."""
    count = 0
    for raw in body:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        count += 1
    return count


def scan_text(text: str) -> list[RunBlock]:
    """Return every ``run:`` block scalar in ``text`` with its metrics."""
    lines = text.splitlines()
    blocks: list[RunBlock] = []
    i = 0
    while i < len(lines):
        match = _RUN_KEY.match(lines[i])
        if match is None:
            i += 1
            continue
        key_indent = len(match.group("indent"))
        body, nxt = _body_lines(lines, i, key_indent)
        body_text = "\n".join(body)
        # Filter out comments and blank lines before logic detection to avoid
        # false positives from keywords appearing only in comment text, and
        # blank the message text of pure output commands for the same reason
        # (prose in a remediation `echo` is not shell logic).
        code_only_text = "\n".join(
            _strip_static_output_body(
                [line for line in body if line.strip() and not line.strip().startswith("#")]
            )
        )
        blocks.append(
            RunBlock(
                line=i + 1,
                code_lines=_count_code_lines(body),
                has_logic=bool(_LOGIC.search(code_only_text)),
                body=body_text,
            )
        )
        i = nxt
    return blocks


def is_violation(block: RunBlock, threshold: int) -> bool:
    """A block violates ADR-006 when it is large AND carries logic."""
    return block.code_lines > threshold and block.has_logic


def _iter_targets(root: Path) -> list[Path]:
    targets: list[Path] = []
    for pattern in _SCAN_GLOBS:
        targets.extend(sorted(root.glob(pattern)))
    return targets


def scan_repo(root: Path, threshold: int) -> list[dict[str, object]]:
    """Scan the repo's workflow/action files, returning violation records."""
    found: list[tuple[str, RunBlock]] = []
    for path in _iter_targets(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root).as_posix()
        for block in scan_text(text):
            if is_violation(block, threshold):
                found.append((rel, block))
    found.sort(key=lambda rb: (-rb[1].code_lines, rb[0], rb[1].line))
    return [
        {"file": rel, "line": block.line, "code_lines": block.code_lines}
        for rel, block in found
    ]


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ADR-006 run-block burn-down scanner (#3084).")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repo root.")
    parser.add_argument(
        "--threshold", type=int, default=_DEFAULT_THRESHOLD,
        help=f"Min body code lines to count as a violation (default {_DEFAULT_THRESHOLD}).",
    )
    parser.add_argument(
        "--max", type=int, default=None, dest="max_allowed",
        help="Gate mode: exit 1 when the violation count exceeds MAX.",
    )
    parser.add_argument("--format", choices=("json", "human"), default="human")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: root not found: {root}", file=sys.stderr)
        return EXIT_CONFIG
    if args.threshold < 0:
        print("error: --threshold must be >= 0", file=sys.stderr)
        return EXIT_CONFIG

    violations = scan_repo(root, args.threshold)
    count = len(violations)

    if args.format == "json":
        payload = {"threshold": args.threshold, "count": count, "violations": violations}
        print(json.dumps(payload, indent=2))
    else:
        print(f"ADR-006 run-block violations (> {args.threshold} code lines + logic): {count}")
        for v in violations:
            print(f"  {v['file']}:{v['line']}  ({v['code_lines']} code lines)")

    if args.max_allowed is not None and count > args.max_allowed:
        print(
            f"ADR-006 scanner: {count} violations exceeds --max {args.max_allowed}.",
            file=sys.stderr,
        )
        return EXIT_OVER_MAX
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
