#!/usr/bin/env python3
"""Select Stage-2 review axes from verified changed paths and diff effects.

``/review`` runs a Stage-1 ``spec-compliance`` gate, then a set of Stage-2
axes.  Running all of them on every change costs review latency and adds
low-signal findings, so this script decides which axes a change actually
needs.  It is a pure function of its arguments: the same paths and effects
always produce the same selection, so the routing is testable instead of
being re-derived by a model on each run.

Two axis families stay in separate output fields, because they load
differently and conflating them misloads a caller-pinned local axis.
**Canonical axes** are discovered from ``references/*.md`` and dispatched with
``Task(subagent_type="{stem}")`` using ``references/{stem}.md`` as the system
prompt.  **Local-only skill axes** (see ``LOCAL_AXES``) are sibling skills
invoked with ``Skill(skill="{name}")``; none has a ``references/{name}.md``
file, so a local axis in the canonical list resolves to a path that does not
exist.  ``spec-compliance`` is the Stage-1 gate: it always runs, is never
reported here, and is excluded from the canonical candidate set.

Selection is additive: one change can match several risk categories and
every matched category contributes its axes.

Fail-closed rule: when a changed path matches no known risk category, when the
path list is empty or holds nothing but blanks, when a declared diff effect is
not in the known vocabulary, or when a demanded axis has no
``references/{stem}.md`` prompt to load, every candidate axis is selected.  An
unclassified change gets the full review, never an empty one, and an incomplete
prompt set widens the review instead of narrowing it.  A demanded axis with no
prompt is reported in ``unresolved_axes`` so it never vanishes from both
``canonical_selected`` and ``skipped``.

EXIT CODES (ADR-035):
    0 - A selection was emitted on stdout as JSON.
    2 - Config error: an unknown pinned axis name, or the references
        directory could not be resolved.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path, PurePosixPath

# The Stage-1 gate. Runs unconditionally; never a Stage-2 candidate.
STAGE1_AXIS = "spec-compliance"

# One general review always runs (issue #4981 acceptance criterion 2).
ALWAYS_ON_CANONICAL = ("analyst",)

# Sibling skills invoked with Skill(skill=...), not references/{stem}.md.
LOCAL_AXES = ("code-qualities-assessment", "doc-accuracy", "golden-principles", "taste-lints")

# Every suffix either local scanner reads, plus the ones only the canonical
# code-quality subagent covers (.rs, .rb). A suffix missing here never matches
# executable-code, so the row cannot contribute code-quality or either scanner,
# and a file that another row already classified is silently reviewed by less
# than it should be: scripts/setup.bash matched toolkit-governance alone and
# skipped taste-lints, which reads .bash, and an .mjs or .cjs hook matched
# agent-artifacts alone and skipped code-qualities-assessment, which reads both.
_CODE_SUFFIXES = frozenset(
    {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".cs",
        ".ps1", ".psm1", ".sh", ".bash", ".go", ".rs", ".rb", ".java",
    }
)

_DEPENDENCY_MANIFESTS = frozenset(
    {
        "pyproject.toml", "uv.lock", "poetry.lock", "package.json", "package-lock.json",
        "pnpm-lock.yaml", "yarn.lock", "go.mod", "go.sum", "cargo.toml", "cargo.lock",
        "gemfile", "gemfile.lock", "directory.packages.props", "packages.lock.json",
    }
)

# Whole path words, never bare substrings: "auth" inside "docs/authors.md" and
# "token" inside "src/tokenizer.py" both selected the security axis before.
_SECURITY_WORDS = frozenset(
    {
        "auth", "authn", "authz", "oauth", "secret", "secrets", "credential", "credentials",
        "password", "passwords", "token", "tokens", "permission", "permissions",
        "authentication", "authorization", "security",
    }
)

# Genuinely prefix-shaped: every real spelling starts with these ("sanitize",
# "sanitizer", "sanitization"; "cryptography", "cryptographic").
_SECURITY_WORD_PREFIXES = ("sanitiz", "crypto")

# Directory-shaped and filename-shaped CI markers. The bare token "release"
# used to match "docs/release-notes.md"; a deploy or release surface is a
# directory or a workflow filename, so match those shapes instead.
_CI_PATH_TOKENS = (".github/workflows/", ".github/actions/")
_CI_DIRECTORIES = frozenset({"deploy", "release"})
_CI_FILENAMES = frozenset(
    {
        "dockerfile", "lefthook.yml", "lefthook.yaml", "release.yml", "release.yaml",
        "deploy.yml", "deploy.yaml",
    }
)
_CI_FILENAME_PREFIXES = ("dockerfile.", "docker-compose", "deploy.")
_CI_FILENAME_SUFFIXES = (".tf", ".tfvars")

# Word boundary inside one path segment: any run of non-alphanumeric bytes.
_WORD_SPLIT = re.compile(r"[^a-z0-9]+")

# Every set below is matched as a whole path segment, whole basename, or whole
# name segment, for the reason _SECURITY_WORDS is whole words. Bare substrings
# over-fired and under-fired at once, and the under-fire is the expensive half:
# the path still classifies as something else, so fail_closed stays false and
# the missing axis reads as a deliberate skip. resources/axis-selection.md,
# "Risk categories", carries the measured cases behind each set.
_TYPE_API_STEMS = frozenset({"types", "api", "models", "schema", "protocols", "interfaces"})
_TYPE_API_DIRECTORIES = frozenset({"schemas", "interfaces"})
_TYPE_API_SUFFIXES = (".d.ts", ".proto")
_TEST_NAME_PREFIXES = ("test_", "test.")
_TEST_NAME_INFIXES = (".test.", ".tests.", ".spec.", "_test.", "_tests.", "_spec.")
_TEST_DIRECTORIES = frozenset({"tests", "fixtures"})
# pytest loads these by exact filename regardless of a test_/_test spelling.
_TEST_EXACT_FILENAMES = frozenset({"conftest.py"})
_AGENT_ARTIFACT_DIRECTORIES = frozenset({"skills", "agents", "hooks", "prompts", "commands"})
_AGENT_ARTIFACT_FILENAMES = frozenset({"skill.md"})
# The four file-type domains golden-principles actually checks, mirroring
# scan_principles._is_applicable and the markers in scan_principles_core.py:84-86.
# GP-001 covers .sh/.bash anywhere, GP-003 SKILL.md under .claude/skills/,
# GP-004 .md under .claude/agents/ except CLAUDE.md, and GP-005/GP-006
# .yml/.yaml under .github/workflows/. Selecting on any broader notion of
# "toolkit artifact" buys a scan with zero applicable rules; selecting on any
# narrower one drops a real violation, which is what happened to
# scripts/install.sh.
_GP_SCRIPT_SUFFIXES = (".sh", ".bash")
_GP_WORKFLOW_SUFFIXES = (".yml", ".yaml")
_GP_SKILL_FILENAME = "skill.md"
_GP_AGENT_EXCLUDED_FILENAME = "claude.md"
# These markers match segments of a caller-supplied changed-file path, they do
# not resolve anything on disk, so the vendor-portability ratchet's concern
# does not apply. The root is a named constant so the pair is never spelled as
# an adjacent ".claude", "skills" literal, which that ratchet reads as a
# hard-coded upstream path (issue #2050).
_TOOLKIT_ROOT_SEGMENT = ".claude"
_GP_SKILLS_MARKER = (_TOOLKIT_ROOT_SEGMENT, "skills")
_GP_AGENTS_MARKER = (_TOOLKIT_ROOT_SEGMENT, "agents")
_GP_WORKFLOWS_MARKER = (".github", "workflows")
_DECISION_DIRECTORIES = frozenset({"architecture", "decisions"})
_ROADMAP_DIRECTORIES = frozenset({"roadmap", "planning", "specs"})


def _norm(path: str) -> str:
    """Normalize a changed path for matching: posix separators, lowercase."""
    return path.replace("\\", "/").strip().lower()


def _segments(path: str) -> list[str]:
    """Return the non-empty path segments of a normalized path."""
    return [segment for segment in path.split("/") if segment]


def _words(path: str) -> set[str]:
    """Split a normalized path into alphanumeric words.

    ``src/auth/session.py`` yields ``{src, auth, session, py}``; the word set
    is what security matching tests, so ``docs/authors.md`` (``authors``) and
    ``src/tokenizer.py`` (``tokenizer``) no longer match ``auth``/``token``.
    """
    return {word for segment in _segments(path) for word in _WORD_SPLIT.split(segment) if word}


def _is_test_path(path: str) -> bool:
    # [:-1] drops the filename, so a file named "fixtures" is not a directory
    # of them, and a repo-root "tests/" or "fixtures/" directory still counts.
    segments = _segments(path)
    if _TEST_DIRECTORIES & set(segments[:-1]):
        return True
    name = segments[-1] if segments else ""
    if name in _TEST_EXACT_FILENAMES:
        return True
    if name.startswith(_TEST_NAME_PREFIXES):
        return True
    return any(infix in name for infix in _TEST_NAME_INFIXES)


def _is_security_path(path: str) -> bool:
    if path.rsplit("/", 1)[-1].startswith(".env") or ".env." in path:
        return True
    words = _words(path)
    if words & _SECURITY_WORDS:
        return True
    return any(word.startswith(_SECURITY_WORD_PREFIXES) for word in words)


def _is_dependency_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name in _DEPENDENCY_MANIFESTS or name.endswith(".csproj"):
        return True
    return name.startswith("requirements") and name.endswith(".txt")


def _is_ci_deploy_path(path: str) -> bool:
    # startswith (not substring): trailing / ensures segment alignment.
    if any(path.startswith(token) for token in _CI_PATH_TOKENS):
        return True
    name = path.rsplit("/", 1)[-1]
    if name in _CI_FILENAMES or name.startswith(_CI_FILENAME_PREFIXES):
        return True
    if name.endswith(_CI_FILENAME_SUFFIXES):
        return True
    return bool(_CI_DIRECTORIES & set(_segments(path)[:-1]))


def _is_type_or_api_path(path: str) -> bool:
    segments = _segments(path)
    if _TYPE_API_DIRECTORIES & set(segments[:-1]):
        return True
    name = segments[-1] if segments else ""
    if name.endswith(_TYPE_API_SUFFIXES):
        return True
    stem, dot, suffix = name.rpartition(".")
    return bool(dot) and stem in _TYPE_API_STEMS and f".{suffix}" in _CODE_SUFFIXES


def _is_agent_artifact_path(path: str) -> bool:
    # [:-1] drops the filename, so a file named "skills" is not a directory of
    # them (same convention as _is_ci_deploy_path above).
    segments = _segments(path)
    if segments and segments[-1] in _AGENT_ARTIFACT_FILENAMES:
        return True
    return bool(_AGENT_ARTIFACT_DIRECTORIES & set(segments[:-1]))


def _has_contiguous_segments(segments: list[str], marker: tuple[str, ...]) -> bool:
    """Return True when marker appears as contiguous path segments."""
    width = len(marker)
    return any(
        tuple(segments[index : index + width]) == marker
        for index in range(len(segments) - width + 1)
    )


def _is_toolkit_artifact_path(path: str) -> bool:
    """Classify a path as toolkit governance, mirroring the GP scanner's domain.

    Canonical source: `.claude/skills/golden-principles/scripts/scan_principles.py`,
    function `_is_applicable`. Its contract, quoted verbatim:

        suffix = Path(filepath).suffix
        name = Path(filepath).name

        if suffix in (".sh", ".bash"):
            return True
        if name == "SKILL.md" and _has_path_parts(filepath, _SKILLS_PATH_PARTS):
            return True
        if suffix == ".md" and _has_path_parts(filepath, _AGENTS_PATH_PARTS) and name != "CLAUDE.md":
            return True
        if suffix in (".yml", ".yaml") and _has_path_parts(filepath, _WORKFLOWS_PATH_PARTS):
            return True
        return False

    The markers it tests are `.claude/skills/`, `.claude/agents/`, and
    `.github/workflows/` (`_SKILLS_PATH_MARKER`, `_AGENTS_PATH_MARKER`,
    `_WORKFLOWS_PATH_MARKER` in `scan_principles_core.py`), matched as
    contiguous path components.

    Stricter/looser/different than canonical
    ---------------------------------------
    Different in case handling, and only there. `classify_paths` lowercases
    every path through `_norm` before any predicate sees it, so this function
    compares lowercased literals while the canonical compares `"SKILL.md"` and
    `"CLAUDE.md"` as written. Consequences in both directions:

    - Looser: `.CLAUDE/SKILLS/review/SKILL.MD` classifies here and would not be
      applicable to the scanner.
    - Stricter: `.claude/agents/Claude.md` is excluded here (it folds to the
      excluded name) and would be applicable to the scanner.

    The fold is deliberate and stays: this predicate feeds category reporting
    and the eight canonical-axis rows, which have no scanner behind them and
    should match case-insensitively. Axis routing does not rely on it. The
    local `golden-principles` axis is gated separately by
    `_golden_principles_reads`, which mirrors the canonical casing exactly, so
    the looser direction above cannot select an axis the scanner would skip.
    """
    if path.endswith(_GP_SCRIPT_SUFFIXES):
        return True
    segments = _segments(path)
    if not segments:
        return False
    name = segments[-1]
    if name == _GP_SKILL_FILENAME and _has_contiguous_segments(segments, _GP_SKILLS_MARKER):
        return True
    if (
        name.endswith(".md")
        and name != _GP_AGENT_EXCLUDED_FILENAME
        and _has_contiguous_segments(segments, _GP_AGENTS_MARKER)
    ):
        return True
    return name.endswith(_GP_WORKFLOW_SUFFIXES) and _has_contiguous_segments(
        segments, _GP_WORKFLOWS_MARKER
    )


def _is_decision_doc_path(path: str) -> bool:
    segments = _segments(path)
    if segments and segments[-1].startswith("adr-"):
        return True
    return bool(_DECISION_DIRECTORIES & set(segments[:-1]))


def _is_roadmap_doc_path(path: str) -> bool:
    return bool(_ROADMAP_DIRECTORIES & set(_segments(path)[:-1]))


def _is_docs_path(path: str) -> bool:
    """Match what doc-accuracy actually inventories: Markdown.

    Its DOC_GLOBS is ["docs/**/*.md", "**/*.md"], so .mdx, .rst, and .txt are
    never read. Claiming them here selected the axis for a file it would not
    open, and the resulting empty scan gated PASS. Leaving them out drops them
    through to unclassified, which fails the run closed onto the full axis set
    rather than handing a text change to nobody.
    """
    return path.endswith(".md")


def _is_code_path(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in _CODE_SUFFIXES)


# Every local axis is one scanner, and a scanner reads only the files its own
# source accepts. Routing an axis at a change whose files that scanner skips
# gives a run over zero files, which adapt_local_axis_verdict reports as
# UNKNOWN, so the axis can never reach PASS and the review cannot finish. The
# predicates below mirror each scanner's acceptance test, casing included,
# against the path as git reports it rather than the lowercased form the
# category predicates match.

# Canonical source: .claude/skills/code-qualities-assessment/scripts/assess.py,
# dict `_LANGUAGE_BY_SUFFIX`, read through `_LANGUAGE_BY_SUFFIX.get(
# file_path.suffix.lower())`. The `.lower()` is why this mirror folds case.
# Divergence: none. Absent on purpose because the canonical map has no entry
# for them: .ps1, .psm1, .sh, .rs, .rb. Parity is asserted against the dict
# itself in tests/skills/review/test_select_axes_scanner_capability.py.
_ASSESS_SUFFIXES = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".cs", ".java", ".go"}
)
# Canonical source: .claude/skills/taste-lints/scripts/taste_lints.py, set
# `SCANNABLE_EXTENSIONS`, read through `Path(filepath).suffix in
# SCANNABLE_EXTENSIONS`. No case folding there, so this mirror does not fold
# either. Divergence: none. The canonical set has no entry for TypeScript,
# JavaScript, C#, Go, Rust, Ruby, or Java. Parity is asserted against the set
# itself in tests/skills/review/test_select_axes_scanner_capability.py.
_TASTE_LINT_SUFFIXES = frozenset(
    {".py", ".ps1", ".psm1", ".sh", ".bash", ".yml", ".yaml", ".md", ".json"}
)
# Canonical source: .claude/skills/doc-accuracy/scripts/doc_accuracy.py,
# `DOC_GLOBS = ["docs/**/*.md", "**/*.md"]`, quoted verbatim. Markdown only,
# and fnmatch applies those globs case-sensitively, so .mdx, .rst, and .txt are
# never inventoried. Divergence: none. The literal is asserted unchanged in
# tests/skills/review/test_select_axes_scanner_capability.py, so widening the
# canonical list reds that test instead of silently drifting from this one.
_DOC_ACCURACY_SUFFIXES = frozenset({".md"})
# Same file, `EXCLUDE_DIRS`, quoted verbatim. The inventory walk skips any path
# under one of these, so a Markdown file inside one is never read even though
# its suffix matches. This repository tracks `build/AGENTS.md`, which is
# exactly that case.
_DOC_ACCURACY_EXCLUDED_DIRS = frozenset(
    {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        "target", "dist", "build", "bin", "obj", ".doc-accuracy",
    }
)
# scan_principles._is_applicable compares these two names literally. The
# classifier above matches them lowercased; this mirror keeps the real casing.
_GP_SCANNER_SKILL_FILENAME = "SKILL.md"
_GP_SCANNER_EXCLUDED_FILENAME = "CLAUDE.md"


def _posix(path: str) -> str:
    """Normalize separators without folding case, unlike ``_norm``."""
    return path.replace("\\", "/").strip()


def _suffix(path: str) -> str:
    return PurePosixPath(path).suffix


def _assess_reads(path: str) -> bool:
    """Return True when assess.py would score *path*.

    Mirrors `_LANGUAGE_BY_SUFFIX` in
    `.claude/skills/code-qualities-assessment/scripts/assess.py`; see the
    constant above for the quoted contract and the divergence note.
    """
    return _suffix(path).lower() in _ASSESS_SUFFIXES


def _taste_lints_reads(path: str) -> bool:
    """Return True when taste_lints.py would scan *path*.

    Mirrors `SCANNABLE_EXTENSIONS` in
    `.claude/skills/taste-lints/scripts/taste_lints.py`; see the constant above
    for the quoted contract and the divergence note.
    """
    return _suffix(path) in _TASTE_LINT_SUFFIXES


def _doc_accuracy_reads(path: str) -> bool:
    """Return True when doc_accuracy.py would inventory *path*.

    Mirrors `DOC_GLOBS` and `EXCLUDE_DIRS` in
    `.claude/skills/doc-accuracy/scripts/doc_accuracy.py`; see the constants
    above for the quoted contracts and the divergence notes. The suffix alone
    is not enough: the inventory walk prunes excluded directories first, so a
    tracked file like `build/AGENTS.md` matches the glob and is still never
    read.
    """
    if _suffix(path) not in _DOC_ACCURACY_SUFFIXES:
        return False
    return not (_DOC_ACCURACY_EXCLUDED_DIRS & set(_segments(path)[:-1]))


def _golden_principles_reads(path: str) -> bool:
    """Return True when the GP scanner would treat *path* as applicable.

    Canonical source: `.claude/skills/golden-principles/scripts/scan_principles.py`,
    function `_is_applicable`, quoted verbatim in `_is_toolkit_artifact_path`
    above. Markers come from `scan_principles_core.py`: `.claude/skills/`,
    `.claude/agents/`, `.github/workflows/`, matched as contiguous components
    by `_has_path_parts`.

    Stricter/looser/different than canonical
    ---------------------------------------
    No behavioral divergence. This is the case-preserving mirror, so it is fed
    the path as git reports it rather than the lowercased form the classifier
    uses. `tests/skills/review/test_select_axes_scanner_capability.py`
    asserts parity against the canonical function itself across a path table
    that includes the case variants, so drift in either reds that test rather
    than living in this comment.
    """
    segments = _segments(_posix(path))
    if not segments:
        return False
    name = segments[-1]
    if name.endswith(_GP_SCRIPT_SUFFIXES):
        return True
    if name == _GP_SCANNER_SKILL_FILENAME and _has_contiguous_segments(
        segments, _GP_SKILLS_MARKER
    ):
        return True
    if (
        name.endswith(".md")
        and name != _GP_SCANNER_EXCLUDED_FILENAME
        and _has_contiguous_segments(segments, _GP_AGENTS_MARKER)
    ):
        return True
    return name.endswith(_GP_WORKFLOW_SUFFIXES) and _has_contiguous_segments(
        segments, _GP_WORKFLOWS_MARKER
    )


_LOCAL_SCANNER_READS: dict[str, Callable[[str], bool]] = {
    "code-qualities-assessment": _assess_reads,
    "doc-accuracy": _doc_accuracy_reads,
    "golden-principles": _golden_principles_reads,
    "taste-lints": _taste_lints_reads,
}


def routed_local_paths(paths: Sequence[str]) -> dict[str, list[str]]:
    """Map each local axis to the changed paths whose category routed it."""
    routed: dict[str, list[str]] = {}
    for raw in paths:
        normalized = _norm(raw)
        if not normalized:
            continue
        for _category, predicate, _canonical, local_axes in _RISK_TABLE:
            if predicate(normalized):
                for axis in local_axes:
                    routed.setdefault(axis, []).append(raw)
    return routed


def scannable_local_axes(paths: Sequence[str]) -> set[str]:
    """Local axes whose scanner reads a path that actually routed them.

    Asking whether the scanner reads any changed path is not enough. With
    `README.md` and `src/main.rs`, only the Rust file routes taste-lints, and
    only the README is readable by it, so a whole-list question keeps the axis
    and it reports PASS over a file that never selected it while skipping the
    one that did. `_EFFECT_TABLE` routes no local axis, so paths are the only
    source of a local selection; a contract test holds that.
    """
    return {
        axis
        for axis, axis_paths in routed_local_paths(paths).items()
        if any(_LOCAL_SCANNER_READS[axis](_posix(path)) for path in axis_paths)
    }


# Ordered risk table. Each row is (category, predicate, canonical axes, local
# axes). Every row whose predicate matches contributes its axes, so a single
# path can select several axes and several paths accumulate.
_RISK_TABLE: tuple[tuple[str, Callable[[str], bool], tuple[str, ...], tuple[str, ...]], ...] = (
    ("tests-or-fixtures", _is_test_path, ("qa",), ()),
    ("auth-secrets-execution", _is_security_path, ("security",), ()),
    ("dependencies", _is_dependency_path, ("security", "devops"), ()),
    ("ci-deploy-artifacts", _is_ci_deploy_path, ("devops", "security"), ()),
    ("types-or-public-api", _is_type_or_api_path, ("architect",), ()),
    ("agent-artifacts", _is_agent_artifact_path, ("agent-safety",), ()),
    ("decision-records", _is_decision_doc_path, ("decision-rigor",), ()),
    ("roadmap-or-spec-docs", _is_roadmap_doc_path, ("roadmap",), ()),
    ("docs-and-instructions", _is_docs_path, (), ("doc-accuracy",)),
    ("executable-code", _is_code_path, ("code-quality",), ("code-qualities-assessment", "taste-lints")),
    ("toolkit-governance", _is_toolkit_artifact_path, (), ("golden-principles",)),
)
# The 12 diff effects the caller verified in the diff body, which no path glob
# can see. An effect outside this vocabulary fails closed. The execution,
# untrusted-input, artifact, and rollback rows of issue #4981 live here rather
# than in _RISK_TABLE: they name what a diff does, not what a path is called,
# and matching them as path words measured as pure noise. Counts in
# resources/axis-selection.md, "Diff-effect mapping".
_EFFECT_TABLE: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "command-execution": (("security",), ()),
    "untrusted-input": (("security",), ()),
    "artifact-or-rollback": (("devops", "security"), ()),
    "error-handling": (("reliability", "qa"), ()),
    "type-change": (("architect",), ()),
    "public-api": (("architect",), ()),
    "integration-point": (("reliability",), ()),
    "new-code-path": (("observability",), ()),
    "dependency-change": (("security", "devops"), ()),
    "agent-behavior": (("agent-safety",), ()),
    "decision-record": (("decision-rigor",), ()),
    "comments-or-docstrings": (("code-quality",), ()),
}

_SKIP_REASON = "skipped - no changed path or diff effect matched this axis"
_UNREADABLE_REASON = "skipped - no changed file this axis's scanner reads"
_FAIL_CLOSED_REASON = "selected - fail-closed: change could not be classified"
_UNRESOLVED_REASON = "selected - fail-closed: a demanded axis has no prompt to load"
_DEEP_REASON = "selected - deep review requested"
_ALWAYS_ON_REASON = "selected - always-on"
_PINNED_REASON = "selected - caller-pinned always-on"


def _blanket_reason(
    deep: bool,
    unclassified: Sequence[str],
    unknown_effects: Sequence[str],
    usable_paths: Sequence[str],
) -> str:
    """Return the reason recorded on every axis when the whole set runs."""
    if deep:
        return _DEEP_REASON
    if unclassified or unknown_effects or not usable_paths:
        return _FAIL_CLOSED_REASON
    return _UNRESOLVED_REASON


def discover_canonical_axes(references_dir: Path) -> list[str]:
    """Return the Stage-2 canonical axis stems found in *references_dir*.

    The directory is the source of truth: adding ``references/{stem}.md``
    enrolls an axis with no edit here. ``spec-compliance`` is the Stage-1
    gate and is excluded.
    """
    stems = sorted(p.stem for p in references_dir.glob("*.md"))
    return [stem for stem in stems if stem != STAGE1_AXIS]


def unreviewable_paths(paths: Sequence[str]) -> list[str]:
    """Paths whose every contributed axis is a local axis no scanner reads.

    Narrowing a local axis to what its scanner can read is safe only while some
    other axis still covers the path. `executable-code` also contributes the
    canonical `code-quality` subagent, so dropping both scanners for a Rust file
    still leaves it reviewed. `docs-and-instructions` and `toolkit-governance`
    contribute local axes alone, so dropping theirs leaves nobody: a tracked
    `build/AGENTS.md` or a `README.MD` would be classified, skipped by every
    axis that claimed it, and the run could still finish PASS with no
    documentation evidence at all. Those paths are reported so the caller fails
    the run closed instead.
    """
    stranded: list[str] = []
    for raw in paths:
        normalized = _norm(raw)
        if not normalized:
            continue
        # Per path, not per run: a sibling that doc-accuracy can read does not
        # make this one readable, and asking globally let a stranded path hide
        # behind a covered one in the same diff.
        posix = _posix(raw)
        covered = any(
            predicate(normalized)
            and (
                bool(canonical_axes)
                or any(_LOCAL_SCANNER_READS[axis](posix) for axis in local_axes)
            )
            for _category, predicate, canonical_axes, local_axes in _RISK_TABLE
        )
        if not covered:
            stranded.append(raw)
    return stranded


def classify_paths(paths: Sequence[str]) -> tuple[list[str], list[str]]:
    """Split *paths* into matched risk categories and unclassified paths."""
    categories: list[str] = []
    unclassified: list[str] = []
    for raw in paths:
        normalized = _norm(raw)
        if not normalized:
            continue
        matched = False
        for category, predicate, _canonical, _local in _RISK_TABLE:
            if predicate(normalized):
                matched = True
                if category not in categories:
                    categories.append(category)
        if not matched:
            unclassified.append(raw)
    return categories, unclassified


def _contributions(
    categories: Iterable[str], effects: Sequence[str]
) -> tuple[dict[str, list[str]], dict[str, list[str]], list[str]]:
    """Map each axis to the categories and effects that selected it."""
    canonical: dict[str, list[str]] = {}
    local: dict[str, list[str]] = {}
    unknown: list[str] = []

    def record(bucket: dict[str, list[str]], axes: Iterable[str], source: str) -> None:
        for axis in axes:
            bucket.setdefault(axis, []).append(source)

    wanted = set(categories)
    for category, _predicate, canonical_axes, local_axes in _RISK_TABLE:
        if category in wanted:
            record(canonical, canonical_axes, category)
            record(local, local_axes, category)

    for effect in effects:
        entry = _EFFECT_TABLE.get(_norm(effect))
        if entry is None:
            unknown.append(effect)
            continue
        record(canonical, entry[0], f"effect:{_norm(effect)}")
        record(local, entry[1], f"effect:{_norm(effect)}")

    return canonical, local, unknown


def select_axes(
    changed_paths: Sequence[str],
    canonical_candidates: Sequence[str],
    effects: Sequence[str] = (),
    pinned: Sequence[str] = (),
    deep: bool = False,
) -> dict[str, object]:
    """Return the axis selection for one change.

    ``canonical_candidates`` is the discovered Stage-2 set. ``pinned`` may
    name either a canonical or a local axis; each is routed to its own
    family so a pinned local axis is never loaded as a canonical prompt.
    """
    # classify_paths drops an empty-after-trimming entry rather than calling it
    # unclassified, so judging emptiness on the raw list let ["", "   "] reach
    # the risk branch with nothing matched and narrow to analyst alone.
    usable_paths = [raw for raw in changed_paths if _norm(raw)]
    categories, unclassified = classify_paths(changed_paths)
    # A path every claiming axis then skips is reviewed by nobody, which is the
    # unclassified case wearing a category. Fold it in so the run fails closed.
    unclassified = unclassified + [
        raw for raw in unreviewable_paths(usable_paths) if raw not in unclassified
    ]
    canonical_sources, local_sources, unknown_effects = _contributions(categories, effects)

    # A demanded canonical axis with no references/{stem}.md prompt cannot be
    # dispatched. Report it rather than dropping it from both output lists.
    demanded = set(canonical_sources) | set(ALWAYS_ON_CANONICAL)
    unresolved_axes = sorted(demanded - set(canonical_candidates))

    fail_closed = bool(unclassified or unknown_effects or unresolved_axes) or not usable_paths
    reasons: dict[str, str] = {}
    skip_overrides: dict[str, str] = {}

    if deep or fail_closed:
        blanket = _blanket_reason(deep, unclassified, unknown_effects, usable_paths)
        canonical_selected = set(canonical_candidates)
        local_selected = set(LOCAL_AXES)
        for axis in canonical_selected | local_selected:
            reasons[axis] = blanket
        for axis in unresolved_axes:
            reasons[axis] = _UNRESOLVED_REASON
    else:
        # unresolved_axes is empty on this branch (a demanded axis with no
        # prompt fails closed above), so every demanded axis is a candidate.
        canonical_selected = set(canonical_sources)
        # A routed local axis still needs a file its own scanner reads. The
        # risk rows are coarser than the scanners behind them: executable-code
        # covers .rs and .rb that neither scanner scores, and
        # docs-and-instructions covers .mdx, .rst, and .txt that doc-accuracy
        # never inventories. Selecting those anyway yields a scan over zero
        # files, which reports UNKNOWN, and an UNKNOWN axis blocks a PASS just
        # as a skipped one does without saying why. Skipping names the reason.
        # Deep and fail-closed runs skip this narrowing on purpose: both are
        # explicit "run everything" modes, and fail-closed has no trustworthy
        # path list to narrow by.
        routed_local = set(local_sources) & set(LOCAL_AXES)
        local_selected = routed_local & scannable_local_axes(usable_paths)
        unreadable_local = routed_local - local_selected
        for axis in canonical_selected:
            reasons[axis] = "selected - " + ", ".join(canonical_sources[axis])
        for axis in local_selected:
            reasons[axis] = "selected - " + ", ".join(local_sources[axis])
        skip_overrides.update(dict.fromkeys(unreadable_local, _UNREADABLE_REASON))
        for axis in ALWAYS_ON_CANONICAL:
            canonical_selected.add(axis)
            reasons[axis] = _ALWAYS_ON_REASON

    for axis in pinned:
        if axis in LOCAL_AXES:
            local_selected.add(axis)
        else:
            canonical_selected.add(axis)
        reasons[axis] = _PINNED_REASON

    skipped = {
        axis: skip_overrides.get(axis, _SKIP_REASON)
        for axis in list(canonical_candidates) + list(LOCAL_AXES)
        if axis not in canonical_selected and axis not in local_selected
    }

    return {
        "mode": "deep" if deep else "risk",
        "stage1_axis": STAGE1_AXIS,
        "fail_closed": fail_closed and not deep,
        "matched_categories": categories,
        "unclassified_paths": unclassified,
        "unknown_effects": unknown_effects,
        "unresolved_axes": unresolved_axes,
        "canonical_selected": sorted(canonical_selected),
        "local_selected": sorted(local_selected),
        "selection_reasons": dict(sorted(reasons.items())),
        "skipped": dict(sorted(skipped.items())),
    }


def _default_references_dir() -> Path:
    """Resolve ``references/`` next to this script, in either layout.

    The script ships inside the skill directory, so its own location anchors
    the lookup in both the source project and a vendored plugin install.
    """
    return Path(__file__).resolve().parent.parent / "references"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--changed-path", action="append", default=[], metavar="PATH",
        help="A path from the verified three-dot diff. Repeatable.",
    )
    parser.add_argument(
        "--effect", action="append", default=[], metavar="NAME",
        help=(
            "A diff effect verified in the diff body. Known values: "
            + ", ".join(sorted(_EFFECT_TABLE))
            + ". An unknown value fails closed."
        ),
    )
    parser.add_argument(
        "--pin", action="append", default=[], metavar="AXIS",
        help="A caller-pinned always-on axis, canonical or local. Repeatable.",
    )
    parser.add_argument(
        "--deep", action="store_true",
        help="Deep review: select every candidate axis regardless of risk.",
    )
    parser.add_argument(
        "--references-dir", type=Path, default=None,
        help="Directory holding the canonical axis prompts (references/*.md).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    references_dir = args.references_dir or _default_references_dir()
    if not references_dir.is_dir():
        print(
            f"select_axes: references directory not found: {references_dir}",
            file=sys.stderr,
        )
        return 2

    candidates = discover_canonical_axes(references_dir)
    if not candidates:
        print(
            f"select_axes: no canonical axis prompts in {references_dir}",
            file=sys.stderr,
        )
        return 2

    known = set(candidates) | set(LOCAL_AXES)
    unknown_pins = [axis for axis in args.pin if axis not in known]
    if unknown_pins:
        print(
            "select_axes: unknown pinned axis: " + ", ".join(sorted(unknown_pins)),
            file=sys.stderr,
        )
        return 2

    result = select_axes(
        changed_paths=args.changed_path,
        canonical_candidates=candidates,
        effects=args.effect,
        pinned=args.pin,
        deep=args.deep,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
