#!/usr/bin/env python3
# taste-lint: ignore file-size, validator keeps path grammar and scan policy together.
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
``PLUGIN_ROOTS``, plus the flat source and generated trees in
``EXTRA_SCAN_ROOTS`` (``.claude/commands``, ``templates/agents``, and
``src/copilot-cli/instructions``). These extra directories ship or generate
shipped output, but sit outside plugin-root ``skills/`` sources.
``.claude/commands`` generates Copilot CLI skills under
``src/copilot-cli/skills/`` via ``build/scripts/generate_commands.py``; that
mirror is scanned by the plugin-root pass. ``templates/agents`` generates
Copilot CLI agents under ``src/copilot-cli/agents/`` via
``build/generate_agents.py``; this validator does not scan agent outputs, so
the template source is the only covered surface. ``src/copilot-cli/instructions``
is the generated Copilot instruction mirror of ``.claude/rules/*.md`` via
``build/scripts/generate_rules.py``, which copies each rule body unchanged;
it is scanned directly because it is itself the shipped artifact, not a
source that generates one. See issues #3578 (plugin-root widening), #3646
(commands and templates/agents widening), and #5214 (instructions widening).

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
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.utils.markdown_parser import (
    MarkdownNestingError,
    blank_code_block_lines,
)
from scripts.validation.check_skill_md_drift import (
    _load_drift_baseline,
)
from scripts.validation.check_skill_md_drift import (
    drift_counts_from_failures as _drift_counts_from_failures,
)
from scripts.validation.check_skill_md_drift import (
    marker_path_drift as _drift_marker_path_drift,
)
from scripts.validation.check_skill_md_drift import (
    report_drift_ratchet as _report_drift_ratchet,
)
from scripts.validation.portability_common import (
    build_portability_parser,
    refuse_symlinked_scan_root,
    refuse_unsafe_baseline_write,
    resolve_path_within_root,
    write_baseline_json,
)
from scripts.validation.portability_common import (
    diff_against_baseline as _diff_against_baseline,
)
from scripts.validation.portability_common import (
    load_baseline as _load_baseline,
)
from scripts.validation.portability_common import (
    resolve_checked_baseline as _resolve_checked_baseline,
)
from scripts.validation.portability_common import (
    resolve_root as _common_resolve_root,
)
from scripts.validation.portability_floor import (
    read_previous_sections as _read_previous_sections,
)
from scripts.validation.tracked_paths import GitQueryError

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

# Non-skills directories that also ship to consumers or generate shipped output
# and carry upstream-path prose. ``.claude/commands`` generates Copilot CLI
# skills, whose mirror under ``src/copilot-cli/skills`` is covered by the
# plugin-root scan. ``templates/agents`` generates Copilot CLI agents under
# ``src/copilot-cli/agents``, which this validator deliberately does not scan.
# Scanning these source trees covers the otherwise unscanned source surface and
# avoids double-counting command mirrors. Issue #3646.
#
# ``src/copilot-cli/instructions`` is the generated Copilot instruction mirror
# of ``.claude/rules/*.md`` (``build/scripts/generate_rules.py``, which copies
# each rule body unchanged). It ships inside the ``src/copilot-cli`` plugin
# root but sits outside every root's ``skills/`` tree, so neither the
# plugin-root scan above nor the generator's ``applyTo``-only
# ``_INTERNAL_PATH_PREFIXES`` filter ever reads its prose. Issue #5214 found
# an undeclared upstream-only path shipped this way with no gate covering it.
# ``.github/instructions`` is deliberately excluded: it is the in-repo
# Copilot mirror, not a shipped plugin root (see
# ``.claude/rules/plugin-self-containment.md``), so a repo-only reference
# there is not a defect.
EXTRA_SCAN_ROOTS: tuple[str, ...] = (
    ".claude/commands",
    "templates/agents",
    "src/copilot-cli/instructions",
)

# Extra scan roots whose absence is a broken checkout, not a legitimate minimal
# clone, mirroring the ``REQUIRED_SKILLS_ROOTS`` distinction above.
# ``.claude/commands`` and ``templates/agents`` are sources; a checkout may
# reasonably omit them. ``src/copilot-cli/instructions`` is the shipped
# artifact this validator exists to gate: unlike a source directory, its
# absence means the exact surface issue #5214 found undeclared paths in would
# go unscanned while the run still reports clean, which is the same silent
# fail-open shape as a missing required skills tree.
REQUIRED_EXTRA_ROOTS: frozenset[str] = frozenset({"src/copilot-cli/instructions"})


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


# ---------------------------------------------------------------------------
# Marker path-drift detection (issue #4116)
# ---------------------------------------------------------------------------

def marker_declared_paths(text: str) -> set[str]:
    """Extract upstream paths declared inside the vendor-portability marker."""
    from scripts.validation.check_skill_md_drift import marker_declared_paths as _mdp
    return _mdp(text, _strip_code, _strip_inline_code)


def prose_declared_paths(text: str) -> set[str]:
    """Extract upstream paths from prose with marker and HTML comments removed."""
    from scripts.validation.check_skill_md_drift import prose_declared_paths as _pdp
    return _pdp(text, _strip_code, _strip_inline_code)


def marker_path_drift(text: str, repo_root: Path, rel_path: str) -> list[str]:
    """Delegate to check_skill_md_drift module (issue #4116)."""
    return _drift_marker_path_drift(
        text, repo_root, rel_path, _strip_code, _strip_inline_code
    )


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


def _refuse_markdown_escape(root_resolved: Path, path: Path, label: str) -> None:
    if resolve_path_within_root(root_resolved, path) is not None:
        return
    raise OSError(f"{label} {path} resolves outside the repository root")


def _iter_markdown_files(root: Path, scan_dir: Path) -> list[Path]:
    root_resolved = root.resolve()
    paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(scan_dir, onerror=_reraise_os_error):
        directory = Path(dirpath)
        _refuse_markdown_escape(root_resolved, directory, "Scan directory")
        kept_dirs: list[str] = []
        for name in sorted(dirnames):
            if name == "__pycache__":
                continue
            candidate = directory / name
            _refuse_markdown_escape(root_resolved, candidate, "Scan directory")
            kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for name in sorted(filenames):
            path = directory / name
            _refuse_markdown_escape(root_resolved, path, "Scan entry")
            if path.suffix != MARKDOWN_SUFFIX:
                continue
            if path.is_symlink() and not path.exists():
                raise OSError(f"Broken .md symlink (configuration error): {path}")
            paths.append(path)
    return paths


def scan_skill_markdown(
    skills_dir: Path, repo_root: Path | None = None
) -> MarkdownScan:
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
    dangling target, which would drop it from the scan unnoticed. Descendant
    symlinks that resolve outside the repository are refused before traversal or
    read, because a child escape expands scan scope just like a symlinked root.
    """
    counts: dict[str, int] = {}
    scanned = 0
    base = skills_dir.parent
    root = _common_resolve_root(repo_root, skills_dir, require_repo_marker=False)

    for path in _iter_markdown_files(root, skills_dir):
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

    Roots whose ``skills/`` directory is a symlink pointing outside the
    repository are refused with exit 2 (configuration error). A symlinked root
    scans files git does not track, so coverage checks can be satisfied by
    content that no consumer will receive.
    """
    repo_resolved = root.resolve()
    result = []
    for name in PLUGIN_ROOTS:
        candidate = root / name / "skills"
        if not candidate.is_dir():
            continue
        resolved = candidate.resolve()
        if not resolved.is_relative_to(repo_resolved):
            raise OSError(
                f"Scan root {candidate} resolves to {resolved}, "
                "which is outside the repository root. "
                "A symlinked scan root scans files git does not track. "
                "Remove the symlink or redirect it inside the repository."
            )
        result.append(candidate)
    return result


def extra_scan_dirs(root: Path) -> list[Path]:
    """Return existing directories from ``EXTRA_SCAN_ROOTS``.

    These are flat source trees that ship to consumers or generate shipped
    output, but are not under a plugin root's ``skills/`` subtree.
    ``.claude/commands`` mirrors into ``src/copilot-cli/skills``, which the
    plugin-root scan covers. ``templates/agents`` mirrors into
    ``src/copilot-cli/agents``, which this validator deliberately does not
    scan. Listing the source keeps those template references covered without
    double-counting command mirrors (issue #3646).

    Absent directories are skipped: a checkout that does not have
    ``.claude/commands`` is not broken, it may just be a minimal clone.

    Directories symlinked outside the repository are refused for the same
    reason as plugin roots (see ``skills_dirs``).
    """
    repo_resolved = root.resolve()
    result = []
    for name in EXTRA_SCAN_ROOTS:
        candidate = root / name
        if not candidate.is_dir():
            continue
        resolved = candidate.resolve()
        if not resolved.is_relative_to(repo_resolved):
            raise OSError(
                f"Extra scan dir {candidate} resolves to {resolved}, "
                "which is outside the repository root. "
                "A symlinked scan dir scans files git does not track. "
                "Remove the symlink or redirect it inside the repository."
            )
        result.append(candidate)
    return result


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


def missing_required_extra_roots(root: Path) -> list[str]:
    """Return the required extra scan roots that are absent, in declared order.

    Mirrors ``missing_required_roots`` for ``EXTRA_SCAN_ROOTS`` entries that
    are shipped artifacts rather than optional sources (see
    ``REQUIRED_EXTRA_ROOTS``). Checking this separately from
    ``extra_scan_dirs`` is the point: that function silently skips an absent
    directory so a minimal-clone checkout does not fail on a missing source
    tree, which would also silently skip a required shipped root with no
    signal that anything was missed.
    """
    return [name for name in REQUIRED_EXTRA_ROOTS if not (root / name).is_dir()]


def scan_all(
    root: Path,
    *,
    check_drift: bool = False,
) -> tuple[dict[str, int], dict[str, int], dict[str, int], list[str]]:
    """Scan all skill Markdown files in one traversal.

    Returns (ref_counts, marker_counts, files_by_root, drift_failures). A
    single walk ensures the coverage decision and the baseline contents come
    from the same snapshot, so a concurrent tree mutation cannot produce a short
    baseline that passes the coverage check (issue #4211).

    When check_drift is True, files with a vendor-portability marker are also
    checked for path drift (issue #4116). drift_failures is empty otherwise.

    Raises OSError when a scan root resolves outside the repository root. This
    closes the symlink path-traversal risk: Path.is_dir() returns True through a
    symlink and os.walk follows it, so a symlinked root could read external files
    and count them as repository content (issue #4212).

    Keys in ref_counts and marker_counts are repo-relative posix paths.
    ``marker_counts`` covers plugin roots and extra scan dirs because
    vendor-portability markers in ``.claude/commands`` and
    ``templates/agents`` feed the same exact-count marker baseline. Keys in
    files_by_root are the posix path of the scan root relative to the repo
    root, covering both plugin ``skills/`` dirs and extra scan dirs, so the
    success report can name every root actually examined rather than only
    the ``skills/`` trees (issue #5214 review: a scan root with zero examined
    files must not read the same as a scan root that was never walked).
    """
    ref_counts: dict[str, int] = {}
    marker_counts: dict[str, int] = {}
    files_by_root: dict[str, int] = {}
    drift_failures: list[str] = []

    plugin_dirs = skills_dirs(root)
    extra_dirs = extra_scan_dirs(root)

    def _process_file(text: str, rel_key: str) -> None:
        n_refs = count_file_refs(text)
        if n_refs > 0:
            ref_counts[rel_key] = n_refs
        n_marker = count_marker_suppressed_refs(text)
        if n_marker > 0:
            marker_counts[rel_key] = n_marker
        if check_drift and has_portability_marker(text):
            drift_failures.extend(marker_path_drift(text, root, rel_key))

    for scan_dir in plugin_dirs:
        if refuse_symlinked_scan_root(root, scan_dir):
            raise OSError(f"Scan root {scan_dir} resolves outside the repository root")
        rel_parent = scan_dir.parent.relative_to(root)
        root_key = (rel_parent / scan_dir.name).as_posix()
        paths = _iter_markdown_files(root, scan_dir)
        files_by_root[root_key] = len(paths)
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise OSError(f"Failed to read skill markdown {path}: {exc}") from exc
            rel_key = (rel_parent / path.relative_to(scan_dir.parent)).as_posix()
            _process_file(text, rel_key)

    for extra_dir in extra_dirs:
        if refuse_symlinked_scan_root(root, extra_dir):
            raise OSError(f"Scan root {extra_dir} resolves outside the repository root")
        root_key = extra_dir.relative_to(root).as_posix()
        rel_parent = extra_dir.parent.relative_to(root)
        paths = _iter_markdown_files(root, extra_dir)
        files_by_root[root_key] = len(paths)
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise OSError(f"Failed to read skill markdown {path}: {exc}") from exc
            rel_key = (rel_parent / path.relative_to(extra_dir.parent)).as_posix()
            _process_file(text, rel_key)

    return ref_counts, marker_counts, files_by_root, drift_failures


def scan_plugin_roots(root: Path) -> dict[str, int]:
    """Return {repo_relative_posix_path: ref_count} across every plugin root and extra dirs."""
    ref_counts, _, _, _ = scan_all(root)
    return ref_counts


def scanned_markdown_by_root(root: Path) -> dict[str, int]:
    """Return how many skill ``.md`` files were read under each shipped root.

    A sum cannot answer coverage: one empty root stays invisible in a total
    another root keeps positive, so a partial checkout would write a baseline
    dropping every file the unread root owned.
    """
    _, _, files_by_root, _ = scan_all(root)
    return files_by_root


def scan_marker_suppressions(root: Path) -> dict[str, int]:
    """Return marker-suppressed reference counts across plugin roots and extra scan dirs."""
    _, marker_counts, _, _ = scan_all(root)
    return marker_counts


def _reraise_os_error(error: OSError) -> None:
    raise error


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
    parser = build_portability_parser(__doc__, _DEFAULT_BASELINE_NAME)
    parser.add_argument(
        "--base-ref",
        default=None,
        help=(
            "Git ref to diff the working tree against for the semantic "
            "baseline-conflict guard (issue #4195). When only .md inputs "
            "co-change with the baseline, counts are ratcheted against the "
            "baseline recorded at this ref (issue #4300). Omit to skip the "
            "guard."
        ),
    )
    parser.add_argument(
        "--allow-marker-grow",
        action="store_true",
        default=False,
        help=(
            "Allow the total marker_files suppressed-ref count to increase "
            "during --update-baseline. Required when deliberately adding a new "
            "vendor-portability marker or expanding an existing one (issue #4204)."
        ),
    )
    return parser


# Scanner source files whose edits can change what a stored baseline count
# means, even when no .md file changes. A baseline generated against the old
# scanner semantics is not valid once the scanner itself moves (issue #4195).
_MEASURED_SCANNER_FILES: frozenset[str] = frozenset(
    {
        "scripts/validation/check_skill_md_portability.py",
        "scripts/validation/portability_common.py",
        "scripts/utils/markdown_parser.py",
    }
)


def _is_measured_input(rel_path: str) -> bool:
    """Return whether a repo-relative path feeds this scanner's counts."""
    if rel_path in _MEASURED_SCANNER_FILES:
        return True
    return rel_path.endswith(".md") and any(
        rel_path.startswith(f"{root}/skills/") for root in PLUGIN_ROOTS
    )


def _is_skill_markdown(rel_path: str) -> bool:
    return rel_path.endswith(".md") and any(
        rel_path.startswith(f"{root}/skills/") for root in PLUGIN_ROOTS
    )


def _changed_files_against_base(root: Path, base_ref: str) -> list[str] | None:
    """List files changed or untracked in the working tree relative to ``base_ref``.

    Returns the union of:
    - files in ``git diff --name-only <base_ref>`` (tracked changes)
    - files in ``git ls-files --others --exclude-standard`` (untracked new files)

    A newly created baseline file that has not been ``git add``ed yet is
    untracked; ``git diff`` alone omits it, causing the semantic-conflict guard
    to miss it (issue #4372).

    ``None`` means git could not answer. The caller must fail closed because a
    supplied ``--base-ref`` is the evidence source for the semantic-conflict
    guard; silently skipping it would recreate issue #4195.
    """
    # Three-dot diff (base_ref...HEAD) uses the merge base as the starting
    # point.  Two-dot (base_ref) would compare the working tree directly to
    # base_ref, so if base_ref has advanced past the point where the branch
    # was merged (e.g. main received new commits between the local merge and
    # push), the diff runs in the wrong direction and includes main-side
    # changes as apparent branch changes.  Issue #4474.
    try:
        diff_result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            errors="replace",
            encoding="utf-8",
            check=False,
        )
    except OSError as exc:
        print(f"Could not compare against --base-ref {base_ref}: {exc}", file=sys.stderr)
        return None
    if diff_result.returncode != 0:
        stderr = diff_result.stderr.strip() or "git diff failed"
        print(f"Could not compare against --base-ref {base_ref}: {stderr}", file=sys.stderr)
        return None

    try:
        untracked_result: subprocess.CompletedProcess[str] | None = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            text=True,
            errors="replace",
            encoding="utf-8",
            check=False,
        )
    except OSError:
        untracked_result = None

    diff_files = {line.strip() for line in diff_result.stdout.splitlines() if line.strip()}
    untracked_files: set[str] = set()
    if untracked_result is not None and untracked_result.returncode == 0:
        untracked_files = {
            line.strip()
            for line in untracked_result.stdout.splitlines()
            if line.strip()
        }

    return sorted(diff_files | untracked_files)


def _baseline_matches_scan(
    baseline_path: Path,
    current: dict[str, int],
    marker_current: dict[str, int],
) -> bool:
    """Return True when the baseline on disk reflects the current scan result.

    When it does, the semantic-conflict guard is unnecessary: the baseline was
    regenerated against the exact tree being validated, so there is no stale
    data risk (issue #4300).
    """
    try:
        on_disk_files = _load_baseline(baseline_path)
        on_disk_markers = _load_marker_baseline(baseline_path)
    except (OSError, ValueError):
        return False
    return on_disk_files == current and on_disk_markers == marker_current


def check_semantic_baseline_conflict(
    root: Path,
    base_ref: str,
    baseline_path: Path,
    current: dict[str, int] | None = None,
    marker_current: dict[str, int] | None = None,
) -> list[str] | None:
    """Return measured inputs that changed alongside the baseline (issue #4195).

    A checked-in baseline is only valid against the tree it was generated
    from. If the baseline file differs from ``base_ref`` *and* a file the
    scanner measures (a skill .md, or the scanner code itself) also differs,
    the baseline on disk was regenerated against a tree the merged branch
    will not actually have. Returns an empty list when there is no such
    co-change (including baseline-only changes, which remain allowed).

    A non-empty result is a finding, not yet a verdict.
    ``_semantic_conflict_is_fatal`` decides: scanner changes always fail,
    while .md changes fail only on a real count increase against ``base_ref``.

    Skill-file changes still return a finding here. The fatality check decides
    whether those changes raised undeclared counts above ``base_ref``.
    """
    changed = _changed_files_against_base(root, base_ref)
    if changed is None:
        return None
    if not changed:
        return []
    try:
        baseline_rel = baseline_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return []
    if baseline_rel not in changed:
        return []
    # When the scanner script itself changes (e.g. extending EXTRA_SCAN_ROOTS),
    # the baseline MUST be regenerated to match the new scan scope. That co-change
    # is intentional, not a conflict. Skip the guard in this case. Issue #4195.
    if any(rel in _MEASURED_SCANNER_FILES for rel in changed):
        return []
    return [rel for rel in changed if rel != baseline_rel and _is_measured_input(rel)]


def _counts_section(data: dict[str, Any], key: str) -> dict[str, int]:
    """Return one integer-valued section of a baseline payload."""
    section = data.get(key, {})
    if not isinstance(section, dict):
        raise ValueError(f"Baseline {key!r} must be a JSON object")
    counts: dict[str, int] = {}
    for name, value in section.items():
        try:
            counts[str(name)] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Baseline count for {name!r} is not an integer") from exc
    return counts


def _baseline_payload_at_ref(
    root: Path, base_ref: str, baseline_path: Path
) -> tuple[dict[str, int], dict[str, int]] | None:
    """Return ``(files, marker_files)`` counts recorded in the baseline at ``base_ref``.

    Read through ``git show`` rather than from the working tree, so a branch
    cannot launder a raised count by regenerating its own baseline. ``None``
    means the numbers could not be recovered, which the caller treats as
    fail-closed: with nothing to ratchet against, the guard has not run.
    """
    try:
        rel = baseline_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        print(
            f"Could not read {baseline_path} at {base_ref}: the baseline is "
            f"outside the repository root {root}",
            file=sys.stderr,
        )
        return None
    try:
        proc = subprocess.run(
            ["git", "show", f"{base_ref}:{rel}"],
            cwd=root,
            capture_output=True,
            text=True,
            errors="replace",
            encoding="utf-8",
            check=False,
        )
    except OSError as exc:
        print(f"Could not read {rel} at {base_ref}: {exc}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        detail = proc.stderr.strip() or "git show failed"
        print(f"Could not read {rel} at {base_ref}: {detail}", file=sys.stderr)
        return None
    try:
        data = json.loads(proc.stdout)
        if not isinstance(data, dict):
            raise ValueError("Baseline must be a JSON object")
        return _counts_section(data, "files"), _counts_section(data, "marker_files")
    except ValueError as exc:
        print(f"Could not parse {rel} at {base_ref}: {exc}", file=sys.stderr)
        return None


def _regressions_against_ref_baseline(
    current: dict[str, int],
    ref_files: dict[str, int],
) -> list[str]:
    """Undeclared-ref counts that rose above what ``base_ref`` already allowed.

    Only the ``files`` section is ratcheted. A ``marker_files`` entry is an
    explicit, reviewed declaration, and a branch that adds a new declared file
    has no entry at ``base_ref`` to compare against, so ratcheting markers here
    would reject the sanctioned opt-out flow. Marker drift is still caught
    exactly, against the on-disk baseline, by ``diff_marker_baseline``.
    """
    regressions, _ = _diff_against_baseline(
        current, ref_files, _markdown_regression_message
    )
    return regressions


def _semantic_conflict_is_fatal(
    root: Path,
    base_ref: str,
    baseline_path: Path,
    conflicting_inputs: list[str],
    current: dict[str, int],
) -> bool:
    """Whether a baseline and measured-input co-change must fail the run.

    A scanner-source change is always fatal: the stored numbers were produced
    under different semantics, so no comparison against them means anything.
    A ``.md``-only co-change is fatal only when the branch actually raised a
    count above what ``base_ref`` already allowed, which is the property the
    guard exists to protect. Refusing every such co-change instead made the
    guard unsatisfiable after a main merge, because a merge that brings in
    measured files also requires the baseline to move (issue #4300).
    """
    scanner_changed = [
        rel for rel in conflicting_inputs if rel in _MEASURED_SCANNER_FILES
    ]
    if scanner_changed:
        _report_semantic_conflict(baseline_path, root, conflicting_inputs)
        print(
            "Scanner source changed, so the recorded counts were produced under "
            "different semantics and cannot be compared:"
        )
        for rel in sorted(scanner_changed):
            print(f"  {rel}")
        return True
    ref_counts = _baseline_payload_at_ref(root, base_ref, baseline_path)
    if ref_counts is None:
        _report_semantic_conflict(baseline_path, root, conflicting_inputs)
        return True
    regressions = _regressions_against_ref_baseline(current, ref_counts[0])
    if not regressions:
        return False
    _report_semantic_conflict(baseline_path, root, conflicting_inputs)
    print(f"Counts rose above the baseline recorded at {base_ref}:")
    for line in regressions:
        print(f"  {line}")
    return True


def _report_semantic_conflict(
    baseline_path: Path, root: Path, measured_changed: list[str]
) -> None:
    baseline_rel = baseline_path.resolve().relative_to(root.resolve()).as_posix()
    print(
        f"Semantic baseline conflict (issue #4195): {baseline_rel} changed "
        "alongside measured input(s) below. A baseline is only valid for the "
        "tree it was generated from; regenerate and re-validate together."
    )
    for rel in measured_changed:
        print(f"  changed measured input: {rel}")


def _scan_current_counts(
    root: Path,
    *,
    check_drift: bool = False,
) -> tuple[dict[str, int], dict[str, int], dict[str, int], list[str]] | None:
    """Return current counts, coverage, and drift failures, or None on error."""
    try:
        current, marker_current, scanned_by_root, drift = scan_all(
            root, check_drift=check_drift
        )
    except GitQueryError:
        # An external failure, not a scan result. Exit code 3 per
        # .claude/rules/ci-scripts.md; returning None here would report it as
        # a configuration error and hide that git itself failed.
        raise
    except (OSError, MarkdownNestingError) as exc:
        print(f"Could not scan skills dirs under {root}: {exc}", file=sys.stderr)
        return None
    except Exception as exc:
        print(
            f"Unexpected scan error under {root}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return None
    return current, marker_current, scanned_by_root, drift


def _resolve_root(repo_root: Path | None) -> Path:
    return _common_resolve_root(repo_root, Path(__file__).resolve(), require_repo_marker=False)


def _resolve_baseline_path(root: Path, baseline: Path | None) -> Path | None:
    return _resolve_checked_baseline(root, baseline, _DEFAULT_BASELINE_NAME)


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


def _refuse_marker_files_growth(
    root: Path,
    baseline_path: Path,
    marker_current: dict[str, int],
    *,
    allow_marker_grow: bool,
) -> bool:
    """Refuse when the total marker_files count has grown.

    A marker declares that a file's upstream references are intentional. Once
    a file carries the marker every future reference added to that file inherits
    the exemption automatically. Treating a growth in the total suppressed-ref
    count as a ratchet regression makes that growth visible at review time
    instead of silently absorbed into the next baseline regeneration.

    Pass allow_marker_grow=True (via --allow-marker-grow) to acknowledge a
    deliberate expansion, for example when adding a new marked file.

    Returns True when the write should be refused.
    """
    if allow_marker_grow:
        return False
    previous, problem = _read_previous_sections(root, baseline_path)
    if problem or previous is None:
        # No committed predecessor to compare against; let the write proceed.
        return False
    committed_marker = previous.get("marker_files", {})
    committed_total = sum(committed_marker.values())
    current_total = sum(marker_current.values())
    if current_total > committed_total:
        print(
            f"Refusing --update-baseline: marker_files total grew from "
            f"{committed_total} to {current_total}. "
            "A vendor-portability marker now suppresses more refs than before. "
            "If this is deliberate, pass --allow-marker-grow.",
            file=sys.stderr,
        )
        return True
    return False


def _write_baseline(
    root: Path,
    baseline_path: Path,
    current: dict[str, int],
    marker_current: dict[str, int],
    allow_shrink: bool,
    drift_current: dict[str, int] | None = None,
) -> int:
    total = sum(current.values())
    marker_total = sum(marker_current.values())
    entries = dict(sorted(current.items()))
    marker_entries = dict(sorted(marker_current.items()))
    drift_entries = dict(sorted((drift_current or {}).items()))
    payload: dict[str, Any] = {
        "_comment": (
                "Vendor-portability ratchet baseline for skill Markdown "
                "(issue #2050). The files object counts undeclared "
                "upstream-only path references per Markdown file. The "
                "marker_files object records refs suppressed by "
                "'<!-- vendor-portability: ... -->' markers so stale "
                "declarations do not stay green forever. The drift_files "
                "object records marker path-drift findings per file "
                "(issue #4116). Generated by "
                "check_skill_md_portability.py --update-baseline. Lower "
                "values in files are better; marker_files values must stay exact."
            ),
        "files": entries,
        "marker_files": marker_entries,
    }
    countable: dict[str, dict[str, int]] = {
        "files": entries,
        "marker_files": marker_entries,
    }
    if drift_entries:
        payload["drift_files"] = drift_entries
        countable["drift_files"] = drift_entries
    rc = write_baseline_json(
        root,
        baseline_path,
        payload,
        countable,
        "skill .md files",
        allow_shrink,
    )
    if rc:
        return rc
    drift_total = sum(drift_entries.values())
    print(
        f"Baseline written: {len(current)} files, {total} refs; "
        f"{len(marker_current)} marker files, {marker_total} suppressed refs; "
        f"{len(drift_entries)} drift files, {drift_total} drift findings."
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


def _run_update_baseline(
    args: argparse.Namespace,
    root: Path,
    baseline_path: Path,
    current: dict[str, int],
    marker_current: dict[str, int],
    scanned_by_root: dict[str, int],
    drift_current: dict[str, int] | None = None,
) -> int:
    """Execute the --update-baseline path and return an exit code."""
    if refuse_unsafe_baseline_write(
        root,
        scanned_by_root,
        baseline_path,
        # drift_files must be present or the guard compares the recorded
        # section against a missing one and reports every entry as dropped, so
        # --update-baseline could never succeed once drift was recorded.
        {
            "files": current,
            "marker_files": marker_current,
            "drift_files": drift_current or {},
        },
        "skill .md files",
        args.allow_baseline_shrink,
    ):
        return 2
    if _refuse_marker_files_growth(
        root,
        baseline_path,
        marker_current,
        allow_marker_grow=args.allow_marker_grow,
    ):
        return 2
    return _write_baseline(
        root, baseline_path, current, marker_current,
        args.allow_baseline_shrink, drift_current,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _resolve_root(args.repo_root)
    missing = missing_required_roots(root)
    if missing:
        absent = ", ".join(f"{name}/skills" for name in missing)
        print(f"Required skills dir not found under {root}: {absent}", file=sys.stderr)
        return 2
    missing_extra = missing_required_extra_roots(root)
    if missing_extra:
        absent = ", ".join(missing_extra)
        print(f"Required scan dir not found under {root}: {absent}", file=sys.stderr)
        return 2
    baseline_path = _resolve_baseline_path(root, args.baseline)
    if baseline_path is None:
        return 2

    counts = _scan_current_counts(root, check_drift=True)
    if counts is None:
        return 2
    current, marker_current, scanned_by_root, drift_failures = counts
    scanned = [root / rel for rel in scanned_by_root]
    drift_current = _drift_counts_from_failures(drift_failures)

    if args.update_baseline:
        return _run_update_baseline(
            args, root, baseline_path, current, marker_current,
            scanned_by_root, drift_current,
        )

    if args.base_ref:
        conflicting_inputs = check_semantic_baseline_conflict(
            root, args.base_ref, baseline_path, current, marker_current
        )
        if conflicting_inputs is None:
            return 2
        if conflicting_inputs and _semantic_conflict_is_fatal(
            root,
            args.base_ref,
            baseline_path,
            conflicting_inputs,
            current,
        ):
            return 1

    try:
        baseline = _load_baseline(baseline_path)
        marker_baseline = _load_marker_baseline(baseline_path)
        drift_baseline = _load_drift_baseline(baseline_path)
    except (OSError, ValueError) as exc:
        print(f"Could not read baseline {baseline_path}: {exc}", file=sys.stderr)
        return 2

    regressions, improvements = diff_against_baseline(current, baseline)
    marker_regressions, marker_improvements = diff_marker_baseline(marker_current, marker_baseline)
    regressions.extend(marker_regressions)
    improvements.extend(marker_improvements)

    # Marker path-drift ratchet (issue #4116)
    drift_regressions, drift_improvements = _report_drift_ratchet(
        drift_current, drift_baseline
    )
    regressions.extend(drift_regressions)
    improvements.extend(drift_improvements)

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


def _run(argv: list[str] | None = None) -> int:
    try:
        return main(argv)
    except GitQueryError as exc:
        print(f"External failure: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(_run())
