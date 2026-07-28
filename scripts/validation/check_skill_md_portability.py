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

from scripts.validation.portability_common import (
    build_portability_parser,
    write_baseline,
)
from scripts.validation.portability_common import (
    diff_against_baseline as _diff_against_baseline,
)
from scripts.validation.portability_common import (
    load_baseline as _load_baseline,
)
from scripts.validation.portability_common import (
    resolve_baseline_path as _common_resolve_baseline_path,
)
from scripts.validation.portability_common import (
    resolve_root as _common_resolve_root,
)

# Upstream-only runtime path prefixes. Companion to check_skill_portability.py
# which covers script files; this validator covers .md files. The .claude/skills/
# pattern is excluded here: in prose a bare reference to a sibling skill by
# ``.claude/skills/`` resolves through the install root, so it is not an
# upstream-only dependency. ``.agents/``, ``.claude/lib/``,
# ``.claude/review-axes/``, ``templates/agents/``, and ``templates/platforms/``
# have no consumer-side analogue.
#
# ``templates/agents/`` and ``templates/platforms/`` hold the agent sources and
# platform manifests the generators read. Neither ships in the plugin, so a
# consumer following such a reference lands on nothing. Both are matched by
# their second segment rather than a bare ``templates/`` prefix, because bare
# ``templates/`` also names a Flask or Django template directory, a
# file-relative asset directory bundled inside a skill, and a substring of
# unrelated URLs (issue #3459).
#
# Every pattern shares one path-start anchor. A reference counts only when the
# path begins at a real start of context: the start of the document, whitespace
# (which includes a line start), or a Markdown or quoting delimiter. An optional
# single leading separator (``/``, ``\`` or ``./``) is consumed after the anchor
# so a repository-root-relative link such as ``/templates/agents/x.md`` counts,
# because GitHub resolves a leading slash from the repository root.
#
# The anchor is a positive test rather than a negative one. An earlier revision
# used ``(?<![\w.\-/\\])`` and consumed the separator after it, which admitted
# any character outside that set before the separator. That let ``~/templates/``,
# ``C:\templates\``, ``${ROOT}/templates/``, ``%ROOT%\templates\``,
# ``file:///templates/``, ``//templates/`` and a URL fragment ``#/templates/``
# all count, none of which resolve to the repository root. Naming the characters
# that may precede a path is the only way to keep those out while still
# accepting ``[x](/templates/agents/x.md)``.
#
# Inline code is deliberately not stripped before counting (see
# :func:`count_upstream_refs`), so a backtick is a valid anchor character.
# ``../`` stays excluded: it is parent-relative and does not name the repository
# root, so where it lands depends on the referring file's own location.
#
# ``>`` is in the set so a tight blockquote ``>/templates/agents/x.md`` counts,
# matching the spaced ``> /templates/agents/x.md`` that ``\s`` already accepts.
#
# Adding a raw ``:`` or ``=`` to that set is the obvious way to reach the three
# shapes it misses, and it is the wrong way: a raw ``:`` makes the Windows drive
# letters ``C:\templates\`` and ``C:\.agents\`` count, and a raw ``=`` makes the
# URL query parameter ``?next=/.agents/x`` count. Naming the two contexts
# instead reaches all three shapes and admits none of those, so the trade is not
# forced (measured over nine shapes, issue #3489).
_ANCHOR = r"(?:^|(?<=[\s(\[<>\"'`|,;*]))"

# A link reference definition ``[x]:/templates/agents/x.md`` and a ``path:``
# label both put a colon immediately before the path. Requiring the label itself
# to sit at an anchor is what keeps drive letters and URL-embedded colons out:
# in ``C:\templates`` the ``C`` is one character and not the literal ``path`` or
# a bracketed label, and in ``https://x/path:/templates`` the label is preceded
# by ``/``, which is not an anchor character.
#
# Only the tight form, with no gap between the colon and the path, needs this
# anchor. CommonMark allows optional spaces, tabs, and up to one line ending
# between a link label's colon and its destination, but every spaced form is
# already counted without help here: the whitespace is itself an ``_ANCHOR``
# character (``\s`` covers space, tab and newline), so ``[x]: /templates``
# anchors on the space. Widening this to ``[x]:[ \t]*`` would match only strings
# ``_ANCHOR`` already matches, which is dead regex, and it would still admit no
# new hazard because a bare colon in prose (``note:/templates``) has no anchor
# before the label. ``test_label_definition_whitespace_after_colon_still_counts``
# pins the spaced, tabbed and line-broken forms; the negative-control test pins
# that a raw prose colon does not anchor.
_LABEL_ANCHOR = _ANCHOR + r"(?:path|\[[^\]\r\n]+\]):"

# An unquoted HTML attribute ``<img src=/templates/agents/x.md>`` puts an equals
# sign immediately before the path. Requiring an open tag and a real attribute
# name is what keeps ``?next=/.agents/x`` out: a URL query parameter has no
# enclosing tag. The quoted form needs no rule here because ``"`` and ``'`` are
# already anchor characters.
_ATTR_ANCHOR = r"<[A-Za-z][^<>\r\n]*?\s(?:src|href|action)="

_BOUNDARY = rf"(?:{_ANCHOR}|{_LABEL_ANCHOR}|{_ATTR_ANCHOR})" + r"(?:\.[\\/]|[\\/])?"

# Bare-ref terminator: a reference is counted when the path segment ends at a
# word boundary (\b), a separator, a quoting delimiter, or end-of-line. The
# lookahead avoids consuming the delimiter so overlapping contexts are not
# missed. Without the \b alternative, references like ``.agents`` at the end of
# a sentence (followed by period, comma, or whitespace) go uncounted (issue
# #3482).
_UPSTREAM_REF_TERMINATOR = r"(?=\b|[\\/]+|['\"?#]|$)"

UPSTREAM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(_BOUNDARY + r"\.agents" + _UPSTREAM_REF_TERMINATOR, re.IGNORECASE),
    re.compile(_BOUNDARY + r"\.claude[\\/]+lib" + _UPSTREAM_REF_TERMINATOR, re.IGNORECASE),
    re.compile(
        _BOUNDARY + r"\.claude[\\/]+review-axes" + _UPSTREAM_REF_TERMINATOR,
        re.IGNORECASE,
    ),
    re.compile(
        _BOUNDARY + r"templates[\\/]+agents" + _UPSTREAM_REF_TERMINATOR,
        re.IGNORECASE,
    ),
    re.compile(
        _BOUNDARY + r"templates[\\/]+platforms" + _UPSTREAM_REF_TERMINATOR,
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

# One blockquote marker: optional leading indent on the first, then ``>`` and an
# optional single space that belongs to the marker rather than the content.
_QUOTE_MARKER_PATTERN = re.compile(r"^[ \t]{0,3}>[ \t]?")


def _quote_depth(line: str) -> int:
    """Count the blockquote markers a line opens with."""
    depth = 0
    rest = line
    while True:
        match = _QUOTE_MARKER_PATTERN.match(rest)
        if match is None:
            return depth
        depth += 1
        rest = rest[match.end() :]


def _strip_quote_markers(line: str, depth: int) -> str:
    """Remove exactly ``depth`` blockquote markers from the front of a line.

    Stripping exactly the opening depth, rather than every marker, is what lets
    a deeper marker be recognised as content instead of a closing fence.
    """
    rest = line
    for _ in range(depth):
        match = _QUOTE_MARKER_PATTERN.match(rest)
        if match is None:
            break
        rest = rest[match.end() :]
    return rest

_DEFAULT_BASELINE_NAME = "skill_md_portability_baseline.json"

MARKDOWN_SUFFIX = ".md"


def has_portability_marker(text: str) -> bool:
    """Return True if the file self-declares its upstream path dependencies.

    Strips fenced code and inline code first so that a marker inside a code
    example is not treated as the real opt-out declaration.
    """
    return _MARKER_PATTERN.search(_strip_inline_code(_strip_code(text))) is not None


def _strip_code(text: str) -> str:
    """Remove fenced code blocks, leaving prose and inline code spans.

    Uses line-by-line processing to correctly handle nested fence examples
    (e.g., a code block that itself contains triple-backtick lines).
    A closing fence must use the same character and be at least as long
    as the opening fence, per CommonMark spec.

    A fence that opens inside a blockquote is stripped too, and only such a
    fence accepts a blockquoted closing line. Requiring the close to match the
    open's context keeps a bare ``>``-prefixed line inside a top-level fence
    from closing it early.

    A blockquoted fence also ends when its blockquote ends, because a fenced
    code block has no lazy continuation. The line that ends the blockquote is
    then re-read at top level, so a bare ``\u0060\u0060\u0060`` there opens a new
    top-level fence rather than being treated as prose.

    The opening blockquote depth is recorded, not merely the fact of being
    quoted. Depth matters in both directions: a fence opened at depth 1 must not
    be closed by a marker at depth 2, and a fence opened at depth 2 must end when
    the document drops to depth 1, because that line has left the block the fence
    opened in.
    """
    lines = text.split("\n")
    result_lines: list[str] = []
    fence_char: str | None = None
    fence_len = 0
    fence_depth = 0

    for line in lines:
        if fence_char is not None and fence_depth > 0 and _quote_depth(line) < fence_depth:
            fence_char = None
            fence_len = 0
            fence_depth = 0

        if fence_char is None:
            match = _FENCE_OPEN_PATTERN.match(line)
            depth = 0
            if match is None:
                depth = _quote_depth(line)
                if depth:
                    match = _FENCE_OPEN_PATTERN.match(_strip_quote_markers(line, depth))
                    if match is None:
                        depth = 0
            if match:
                fence_char = match.group(1)[0]
                fence_len = len(match.group(1))
                fence_depth = depth
                result_lines.append("")
            else:
                result_lines.append(line)
        else:
            close_pattern = re.compile(
                r"^[ \t]{0,3}" + re.escape(fence_char) + r"{" + str(fence_len) + r",}\s*$"
            )
            candidate = _strip_quote_markers(line, fence_depth) if fence_depth else line
            if close_pattern.match(candidate):
                fence_char = None
                fence_len = 0
                fence_depth = 0
                result_lines.append("")
            else:
                result_lines.append("")

    return "\n".join(result_lines)


def _strip_inline_code(text: str) -> str:
    """Remove inline code spans while preserving surrounding prose."""
    return re.sub(r"`[^`\n]*`", " ", text)


def count_upstream_refs(text: str) -> int:
    """Count upstream-only path references in Markdown prose.

    Strips fenced code first so example commands do not count, then matches the
    upstream path prefixes. Inline code spans still count because SKILL.md
    runtime directives and path dependencies are commonly written in backticks.
    Does NOT honor the opt-out marker; use
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


def _markdown_regression_message(rel: str, count: int, allowed: int) -> str:
    return (
        f"{rel}: {count} upstream-path refs in prose (baseline {allowed}). "
        "Resolve via plugin/skill root or consumer cwd, or declare the "
        "dependency with an HTML comment marker "
        "'<!-- vendor-portability: ... -->' (issue #2050)."
    )


def diff_against_baseline(
    current: dict[str, int], baseline: dict[str, int]
) -> tuple[list[str], list[str]]:
    """Return (regressions, improvements) comparing current to baseline.

    A regression is a file whose count rose above its baseline, or a file with
    references that is absent from the baseline. An improvement is a file whose
    count dropped (including to zero / removed).
    """
    return _diff_against_baseline(current, baseline, _markdown_regression_message)


def build_parser() -> argparse.ArgumentParser:
    return build_portability_parser(__doc__, _DEFAULT_BASELINE_NAME)


def _resolve_root(repo_root: Path | None) -> Path:
    return _common_resolve_root(repo_root, Path(__file__).resolve(), require_repo_marker=False)


def _resolve_baseline_path(root: Path, baseline: Path | None) -> Path:
    return _common_resolve_baseline_path(
        root, baseline, _DEFAULT_BASELINE_NAME, reject_outside_root=True
    )


def _write_baseline(baseline_path: Path, current: dict[str, int]) -> int:
    return write_baseline(
        baseline_path,
        current,
        (
            "Vendor-portability ratchet baseline for skill Markdown "
            "(issue #2050). Counts of upstream-only path references per "
            ".md file (fenced code stripped; inline paths counted; files with a "
            "'<!-- vendor-portability: ... -->' marker excluded). "
            "Generated by check_skill_md_portability.py --update-baseline. "
            "Lower is better; review count increases before committing."
        ),
        "refs",
    )


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
