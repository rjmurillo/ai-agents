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

Scope: ``*.md`` under the ``skills/`` tree of every plugin root listed in
``PLUGIN_ROOTS``. Scanning only ``.claude/skills`` left thirty nine references
unratcheted in ``src/copilot-cli/skills``, which is generated from
``.claude/commands`` and so was covered by neither path. See issue #3578.

Exit codes:
  0 - no drift (counts at or below baseline), or --update-baseline wrote the file
  1 - drift detected (a file exceeds its baseline or a new file offends)
  2 - configuration error (skills dir missing, baseline unreadable)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.utils.markdown_parser import (
    MarkdownNestingError,
    blank_code_block_lines,
)
from scripts.validation.portability_common import build_portability_parser
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
# ``.claude/review-axes/``, ``build/``, ``templates/agents/``, and
# ``templates/platforms/`` have no consumer-side analogue.
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

# A directory reference ends where the directory name stops. The terminator
# accepts either a continuation into a subpath or any boundary that is not part
# of the name.
#
# ``[\\/]+`` keeps a reference that runs on into a subpath or filename and
# consumes the separators, so ``/templates/agents/x.md`` counts and an adjacent
# reference is not double counted.
#
# ``(?![\w-])`` is the word-boundary case the older class missed. A bare mention
# such as ``templates/agents for generation`` ends at a space, and
# ``[state](/.agents)`` ends at ``)``; both are boundaries, neither a separator
# nor one of the few punctuation marks the old class named. The negative
# lookahead admits every non-identifier boundary at once (space, tab, newline,
# end of string, closing parenthesis, comma, semicolon, exclamation mark,
# backtick, quotes, question mark, hash and the rest) while still rejecting a
# longer directory name:
# ``templates/agentsx``, ``templates/agents-v2`` and ``templates/agents2``
# continue with a word character or a hyphen and do not match. This subsumes the
# old ``['\"?#]`` and ``$`` alternatives, which were all non-identifier
# boundaries already, and it also rejects a hyphenated continuation
# (``agents-v2``) that a bare ``\b`` alternative would still accept, because a
# hyphen is a non-word character and therefore a ``\b`` transition.
#
# ``(?!\.[\w])`` rejects a file-extension dot. Without it, the case-insensitive
# match makes the real file ``templates/AGENTS.md`` count as the
# ``templates/agents`` directory, because ``.`` is a boundary and ``AGENTS``
# folds to ``agents`` (measured: 25 such false positives across the repo, all
# references to ``templates/AGENTS.md``). A sentence-ending period is still a
# boundary, because ``templates/agents.`` puts a non-word character after the
# dot; only ``name.ext`` is excluded (issue #3482).
_TERMINATOR = r"(?:[\\/]+|(?![\w-])(?!\.[\w]))"

UPSTREAM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(_BOUNDARY + r"\.agents" + _TERMINATOR, re.IGNORECASE),
    re.compile(_BOUNDARY + r"\.claude[\\/]+lib" + _TERMINATOR, re.IGNORECASE),
    re.compile(
        _BOUNDARY + r"\.claude[\\/]+review-axes" + _TERMINATOR,
        re.IGNORECASE,
    ),
    # `build/` exists only in the upstream checkout. Match the root directory
    # only, with the same separator requirement as scripts/, so prose words
    # such as "build" do not count.
    re.compile(_BOUNDARY + r"build[\\/]", re.IGNORECASE),
    re.compile(
        _BOUNDARY + r"templates[\\/]+agents" + _TERMINATOR,
        re.IGNORECASE,
    ),
    re.compile(
        _BOUNDARY + r"templates[\\/]+platforms" + _TERMINATOR,
        re.IGNORECASE,
    ),
    # `scripts/` exists only in the upstream checkout (issue #4013). Neither
    # plugin root ships the scripts/ tree, so a skill prose instruction that
    # tells the agent to open or run `scripts/x.py` will silently fail in every
    # consumer install. Require the path-separator to avoid matching the plain
    # English word "scripts" in surrounding prose.
    re.compile(_BOUNDARY + r"scripts[\\/]", re.IGNORECASE),
)

# A skill self-declares its upstream path dependencies with this HTML comment.
# When present, the file's references are suppressed (the acceptance-criterion
# escape hatch). Free text after the colon documents which paths and why.
_MARKER_PATTERN = re.compile(
    r"<!--\s*vendor-portability\s*:.*?-->",
    re.IGNORECASE | re.DOTALL,
)

_DEFAULT_BASELINE_NAME = "skill_md_portability_baseline.json"

MARKDOWN_SUFFIX = ".md"

# Plugin roots whose ``skills/`` tree ships to a consumer. Order fixes the scan
# order so a regenerated baseline stays diff-stable. ``src/claude`` is listed
# even though it has no skills tree today, because the cost of naming it is one
# line and the cost of omitting it is a silently unratcheted root the day one
# appears.
PLUGIN_ROOTS: tuple[str, ...] = (".claude", "src/claude", "src/copilot-cli")

# Roots whose skills tree must exist. A missing tree here is a broken checkout
# or a moved directory, not a legitimate absence, and scanning around it would
# reintroduce exactly the blind spot issue #3578 closed: the run reports clean
# while a whole shipped root goes unread. `src/claude` is deliberately absent
# from this set because it ships agents and rules and has no skills tree today.
REQUIRED_SKILLS_ROOTS: frozenset[str] = frozenset({".claude", "src/copilot-cli"})


def has_portability_marker(text: str) -> bool:
    """Return True if the file self-declares its upstream path dependencies.

    Strips fenced code and inline code first so that a marker inside a code
    example is not treated as the real opt-out declaration.
    """
    return _MARKER_PATTERN.search(_strip_inline_code(_strip_code(text))) is not None


def _strip_code(text: str) -> str:
    """Remove fenced and indented code blocks, leaving prose and inline code.

    Delegates to the shared CommonMark parser via
    :func:`blank_code_block_lines`, so fence termination, blockquote depth, and
    list-relative indentation are resolved by the reference implementation
    instead of a hand-rolled line scanner. Every code line, including fence
    markers, becomes empty, so line numbers are preserved for downstream
    matching.

    Indented code blocks are now stripped too. The previous line-based scanner
    saw only fenced blocks, so a path inside an indented example counted as a
    runtime reference; CommonMark classifies that indented block as code and it
    no longer counts (issue #3499).

    Inline code spans are kept; :func:`_strip_inline_code` removes those.
    A parser failure propagates rather than returning clean prose, so an
    unparseable file cannot slip past the gate.
    """
    return blank_code_block_lines(text)


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


def count_marker_suppressed_refs(text: str) -> int:
    """Count refs hidden by a ``vendor-portability`` marker.

    A marked file used to suppress every finding without leaving any checkable
    value behind. This count becomes a second baseline: if a declaration stays
    behind while the referenced prose moves away, the marker count changes and
    the guard fails until the declaration or baseline is updated.
    """
    if not has_portability_marker(text):
        return 0
    text_without_markers = _MARKER_PATTERN.sub("", text)
    return count_upstream_refs(text_without_markers)


class MarkdownScan(NamedTuple):
    """Result of scanning the skill tree for upstream path references.

    ``counts`` maps each offending file (refs > 0) to its count. ``scanned`` is
    every ``.md`` file actually read. Reporting ``scanned`` separately keeps a
    zero-file scan (empty tree, unreadable dir, mistargeted root) from looking
    identical to a healthy scan that simply found no offenders: both leave
    ``counts`` empty, but only a real scan leaves ``scanned`` positive.
    """

    counts: dict[str, int]
    scanned: int


def scan_skill_markdown(skills_dir: Path) -> MarkdownScan:
    """Return offending counts and the scanned-file total for skill ``.md`` files.

    Paths in ``counts`` are relative to the skills dir's parent, so they begin
    with ``skills/`` and stay POSIX-normalized for cross-OS stability. Files
    that self-declare via the marker contribute 0 to ``counts`` but still count
    as scanned.

    Traversal errors surface rather than being swallowed. ``Path.rglob`` hides a
    permission error on a subdirectory and walks on, so a partial scan reports
    as clean; ``os.walk`` with a re-raising ``onerror`` refuses instead. A
    broken ``.md`` symlink is a configuration error, not a file to skip
    silently, because ``Path.is_file`` follows the link and returns False for a
    dangling target, which would drop it from the scan unnoticed.
    """
    counts: dict[str, int] = {}
    scanned = 0
    base = skills_dir.parent

    def _reraise(error: OSError) -> None:
        raise error

    for dirpath, dirnames, filenames in os.walk(skills_dir, onerror=_reraise):
        dirnames[:] = sorted(name for name in dirnames if name != "__pycache__")
        directory = Path(dirpath)
        for name in sorted(filenames):
            path = directory / name
            if path.suffix != MARKDOWN_SUFFIX:
                continue
            if path.is_symlink() and not path.exists():
                raise OSError(f"Broken .md symlink (configuration error): {path}")
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise OSError(f"Failed to read skill markdown {path}: {exc}") from exc
            scanned += 1
            n = count_file_refs(text)
            if n > 0:
                counts[path.relative_to(base).as_posix()] = n
    return MarkdownScan(counts, scanned)


def skills_dirs(root: Path) -> list[Path]:
    """Return the existing ``skills/`` directory of every plugin root.

    A plugin root is a directory that ships to a consumer, so its ``skills/``
    tree reaches the same reader whichever root it came from. Scanning only one
    of them left thirty nine references unratcheted in ``src/copilot-cli``,
    which is generated from ``.claude/commands`` and therefore never passed
    under the ``.claude/skills`` scan either. See issue #3578.

    Absent roots are skipped rather than reported. ``src/claude`` ships agents
    and rules but has no skills tree, and a root that grows one later is picked
    up without touching this list.
    """
    return [root / name / "skills" for name in PLUGIN_ROOTS if (root / name / "skills").is_dir()]


def missing_required_roots(root: Path) -> list[str]:
    """Return the required roots whose skills tree is absent, in declared order.

    Checking this separately from ``skills_dirs`` is the point: a scan that
    silently drops a root still finds files, still compares cleanly against the
    baseline, and still exits 0. Only an explicit expectation of which roots
    must be present turns that into a failure.
    """
    return [
        name
        for name in PLUGIN_ROOTS
        if name in REQUIRED_SKILLS_ROOTS and not (root / name / "skills").is_dir()
    ]


def scan_plugin_roots(root: Path) -> dict[str, int]:
    """Return {repo_relative_posix_path: count} across every plugin root.

    Keys are relative to the repository root rather than to the skills dir's
    parent. Both roots hold a ``skills/spec/SKILL.md``, so the parent-relative
    key that a single-root scan could use collides the moment a second root is
    read, and one root's count would silently overwrite the other's.
    """
    counts: dict[str, int] = {}
    for skills_dir in skills_dirs(root):
        for rel, n in scan_skill_markdown(skills_dir).counts.items():
            counts[(skills_dir.parent.relative_to(root) / rel).as_posix()] = n
    return counts


def scan_marker_suppressions(root: Path) -> dict[str, int]:
    """Return marker-suppressed reference counts across every plugin root."""
    counts: dict[str, int] = {}
    for skills_dir in skills_dirs(root):
        base = skills_dir.parent
        for path in sorted(skills_dir.rglob(f"*{MARKDOWN_SUFFIX}")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise OSError(f"Failed to read skill markdown {path}: {exc}") from exc
            n = count_marker_suppressed_refs(text)
            if n > 0:
                rel = skills_dir.parent.relative_to(root) / path.relative_to(base)
                counts[rel.as_posix()] = n
    return counts


def _markdown_regression_message(rel: str, count: int, allowed: int) -> str:
    return (
        f"{rel}: {count} upstream-path refs in prose (baseline {allowed}). "
        "Resolve a '.claude/...' ref via plugin/skill root or consumer cwd. "
        "A 'scripts/' ref has no resolved form (that tree is upstream-only and "
        "ships in neither plugin root), so drop it instead. Either kind may be "
        "declared with an HTML comment marker "
        "'<!-- vendor-portability: ... -->' (issues #2050, #4013)."
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


def _load_marker_baseline(path: Path) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Baseline must be a JSON object")
    marker_files = data.get("marker_files", {})
    if not isinstance(marker_files, dict):
        raise ValueError("Baseline 'marker_files' must be a JSON object")
    baseline: dict[str, int] = {}
    for key, value in marker_files.items():
        try:
            baseline[str(key)] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Marker baseline count for {key!r} is not an integer") from exc
    return baseline


def diff_marker_baseline(
    current: dict[str, int], baseline: dict[str, int]
) -> tuple[list[str], list[str]]:
    """Return exact-count marker drift.

    Marker counts are not an ordinary debt ratchet. A lower count can mean the
    declaration is stale after prose moved away, so both increases and decreases
    are regressions.
    """
    regressions: list[str] = []
    for rel in sorted(set(current) | set(baseline)):
        count = current.get(rel, 0)
        allowed = baseline.get(rel, 0)
        if count != allowed:
            regressions.append(
                f"{rel}: vendor-portability marker suppresses {count} refs "
                f"(baseline {allowed}). Update the marker or regenerate the marker baseline."
            )
    return regressions, []


def _write_baseline(
    baseline_path: Path, current: dict[str, int], marker_current: dict[str, int]
) -> int:
    total = sum(current.values())
    marker_total = sum(marker_current.values())
    baseline_path.write_text(
        json.dumps(
            {
                "_comment": (
                    "Vendor-portability ratchet baseline for skill Markdown "
                    "(issue #2050). files counts undeclared upstream-only path "
                    "references per .md file. marker_files records the refs "
                    "suppressed by '<!-- vendor-portability: ... -->' markers "
                    "so stale declarations do not stay green forever. Generated "
                    "by check_skill_md_portability.py --update-baseline. Lower "
                    "files counts are better; marker_files counts must stay exact."
                ),
                "files": dict(sorted(current.items())),
                "marker_files": dict(sorted(marker_current.items())),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Baseline written: {len(current)} files, {total} refs; "
        f"{len(marker_current)} marker files, {marker_total} suppressed refs."
    )
    return 0


def _report(
    *,
    regressions: list[str],
    improvements: list[str],
    current: dict[str, int],
    baseline: dict[str, int],
    scanned: list[Path],
    root: Path,
    output_format: str,
) -> None:
    """Print the scan outcome. Presentation only, no exit decision.

    Split out of ``main`` so that argument handling and orchestration read as
    one thing and formatting as another. ``main`` carried both and sat above
    the complexity ceiling before this seam existed.
    """
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
        print("Markdown vendor-portability drift detected (issue #2050):")
        for line in regressions:
            print(f"  [DRIFT] {line}")
        return
    roots = ", ".join(d.relative_to(root).as_posix() for d in scanned)
    print(
        f"No Markdown vendor-portability drift. "
        f"{sum(current.values())} grandfathered refs across "
        f"{len(current)} files (baseline {sum(baseline.values())}). "
        f"Scanned {roots}."
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _resolve_root(args.repo_root)
    scanned = skills_dirs(root)
    missing = missing_required_roots(root)
    if missing:
        absent = ", ".join(f"{name}/skills" for name in missing)
        print(f"Required skills dir not found under {root}: {absent}", file=sys.stderr)
        return 2
    baseline_path = _resolve_baseline_path(root, args.baseline)
    if baseline_path == Path(""):
        print(
            f"--baseline path is outside the repository root, rejecting: {args.baseline}",
            file=sys.stderr,
        )
        return 2

    try:
        current = scan_plugin_roots(root)
        marker_current = scan_marker_suppressions(root)
    except (OSError, MarkdownNestingError) as exc:
        print(f"Could not scan skills dirs under {root}: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"Unexpected scan error under {root}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    if args.update_baseline:
        return _write_baseline(baseline_path, current, marker_current)

    try:
        baseline = _load_baseline(baseline_path)
        marker_baseline = _load_marker_baseline(baseline_path)
    except (OSError, ValueError) as exc:
        print(f"Could not read baseline {baseline_path}: {exc}", file=sys.stderr)
        return 2

    regressions, improvements = diff_against_baseline(current, baseline)
    marker_regressions, marker_improvements = diff_marker_baseline(
        marker_current, marker_baseline
    )
    regressions.extend(marker_regressions)
    improvements.extend(marker_improvements)
    _report(
        regressions=regressions,
        improvements=improvements,
        current=current,
        baseline=baseline,
        scanned=scanned,
        root=root,
        output_format=args.output_format,
    )
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
