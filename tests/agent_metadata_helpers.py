"""Shared helpers for the tier-to-role migration guards (issue #5130).

Split out of `test_agent_role_metadata_migration.py` when that module crossed
the 500-line taste ceiling. Copilot flagged the violation on PR #5177 while the
description still claimed lint was clean; the file is split by concern rather
than suppressed, which is how the same ceiling was handled earlier in this PR
when `test_openclaw_bridge.py` crossed it.

The tree roster and the predicate for what counts as an agent definition are
imported from `build/scripts/validate_agent_matrix_refs.py` rather than
restated. An earlier revision hardcoded both, which Cursor Bugbot flagged as a
one-directional config set: a seventh tree, or a renamed one, went unchecked.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_matrix_validator():
    """Load the canonical agent-tree roster and agent-definition predicate."""
    path = _REPO_ROOT / "build" / "scripts" / "validate_agent_matrix_refs.py"
    spec = importlib.util.spec_from_file_location("validate_agent_matrix_refs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_vamr = _load_matrix_validator()

# (tree path, filename suffix) for each configured tree, from the canonical
# constant. Suffix matters: `.claude/agents` uses a bare `.md`, so it admits
# sibling docs like `AGENTS.md` that are not agent definitions.
# `as_posix()`, not `str()`: on Windows `str(Path)` yields backslashes while
# discovery below records parents with `as_posix()`, so the two sets would
# never intersect and every real tree would read as unconfigured.
_AGENT_TREES = tuple(tree.as_posix() for tree, _ in _vamr.AGENT_TREES)

# Must stay in sync with _KNOWN_ROLES in scripts/openclaw_bridge.py,
# scripts/validation/validate_copilot_agent_frontmatter.py, and
# build/generate_agent_catalog.py.
_KNOWN_ROLES = frozenset({"strategic", "coordinator", "executor", "support"})

# The pre-migration vocabulary. Discovery keys on these *values*, not on the key
# names, because both keys are overloaded here: skills use `metadata.tier: 3`
# for skill tier, Serena memories use `tier:` for memory tier, and
# `.claude/skills/review/references/*.md` use `role: analyst` for a review axis.
# A key-name check drags all three in as false positives.
_LEGACY_TIERS = frozenset({"expert", "manager", "builder", "integration"})

# Frozen measurement artifacts for issue #1738. They deliberately retain
# `metadata.tier` because rewriting them would alter a recorded measurement.
# Listed per file, not per directory, so adding one is a deliberate edit here
# rather than silent inheritance of a directory-wide exemption.
_EXEMPT_FILES = frozenset(
    {
        ".agents/prototypes/agents/implementer.compressed.md",
        ".agents/prototypes/agents/orchestrator.compressed.md",
        ".agents/prototypes/agents/security.compressed.md",
        ".agents/analysis/instruction-specificity-prototype-security-compressed.md",
    }
)

# `role:` is not exclusive to agents. The review skill's reference files use it
# for a review axis (`role: agent-safety`), in both the Claude and Copilot
# trees, and those values are strings just like agent roles, so no type check
# separates them. Named here rather than discriminated by value, because value
# matching is exactly the bug this list exists to avoid reintroducing.
#
# Getting this list wrong fails loudly rather than silently: an unlisted
# non-agent directory shows up as a spurious unconfigured tree, which is a
# noisy test, not a missed one.
_NON_AGENT_ROLE_DIRS = frozenset(
    {
        ".claude/skills/review/references",
        "src/copilot-cli/skills/review/references",
    }
)

_FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n")

# Matches a `tier:` key inside a frontmatter block at any indent. Used for the
# textual sweep that does not depend on the block parsing as YAML.
_RAW_TIER_RE = re.compile(r"^[ \t]*tier:[ \t]*(\S.*)$", re.M)


def _agent_files() -> list[Path]:
    """Every file in a configured tree that carries that tree's suffix."""
    files: list[Path] = []
    for tree, suffix in _vamr.AGENT_TREES:
        root = _REPO_ROOT / tree
        if root.is_dir():
            files.extend(sorted(root.glob(f"*{suffix}")))
    return files


def _agent_definitions() -> list[Path]:
    """Agent files the repo's own predicate accepts as definitions.

    Excludes siblings like `AGENTS.md` and `claude-instructions.template.md`
    that share a tree's bare `.md` suffix but ship no agent frontmatter.
    """
    return [path for path in _agent_files() if _vamr.is_agent_definition(path)]


def _frontmatter_block(path: Path) -> str | None:
    """The raw text between the frontmatter fences, unparsed."""
    match = _FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def _frontmatter(path: Path) -> dict | None:
    block = _frontmatter_block(path)
    if block is None:
        return None
    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _declared_role(front: dict) -> object | None:
    """The role a file declares, top-level shape taking precedence over nested.

    Mirrors `_read_declared_role` in scripts/openclaw_bridge.py.
    """
    if front.get("role") is not None:
        return front["role"]
    nested = front.get("metadata")
    if isinstance(nested, dict):
        return nested.get("role")
    return None


def _declares_agent_metadata(front: dict) -> bool:
    """True when frontmatter carries an agent role or tier key, whatever its value.

    Deliberately value-independent. An earlier version matched only the four
    known roles and the four legacy tiers, which made discovery depend on the
    very field the other guards validate: a brand new tree whose first agent
    said `role: strategc` was not recognized as an agent tree at all, so the
    converse guard passed and the known-role guard never looked there, because
    it only scans configured trees. Raised by Copilot on PR #5177, and
    reproduced before fixing: a tracked `src/new-agents/foo.agent.md` with that
    typo passed both guards.

    Type still discriminates, because `tier` is overloaded. Skills use
    `metadata.tier: 3` and Serena memories use `tier: 2`, both integers, while
    an agent tier was always a string.
    """
    scopes = [front]
    nested = front.get("metadata")
    if isinstance(nested, dict):
        scopes.append(nested)
    return any(
        isinstance(scope.get("role"), str) or isinstance(scope.get("tier"), str) for scope in scopes
    )


def _tracked_markdown() -> list[str]:
    """Every markdown path git tracks, as repo-relative posix strings.

    Deliberately not `rglob`. This suite runs under xdist alongside tests that
    materialize git worktrees and scratch repositories, and a raw filesystem
    walk races them: a sibling test's temporary checkout carries the six real
    agent trees under a path this file has never heard of, and the converse
    guard below reports them as unconfigured. That failure is scheduling
    dependent, so it passes locally and fails in CI, which is how it was found
    (PR #5177, the `bulk-nested` partition).

    Asking git removes the race. It answers about committed and staged content
    only, which is the exact scope this guard is about: a seventh agent tree
    someone added to the repository, not a directory that existed for 200ms
    inside another test.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=True,
        encoding=None,
    )
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


# Suffixes distinctive enough to identify an agent file without reading its
# role. Measured across every tracked markdown file: `.agent.md` and
# `.shared.md` occur only inside configured agent trees, so they carry no false
# positives. The two trees that use a bare `.md` are not listed, because that
# suffix also matches hundreds of ordinary documents.
_AGENT_FILE_SUFFIXES = (".agent.md", ".shared.md")


def _looks_like_an_agent_file(name: str, path: Path, front: dict | None) -> bool:
    """Two independent signals, so neither alone has to be complete.

    The frontmatter signal catches a role or tier of any value. The suffix
    signal catches a file that declares no role at all, which the frontmatter
    signal cannot see and which Copilot found uncovered on PR #5177: the
    negative control there promised "absent or misspelled" and only exercised
    misspelled.

    The suffix is checked first and without parsing. Copilot found the previous
    order wrong on PR #5177: both signals sat behind a successful YAML parse, so
    a tracked `src/new-agents/foo.agent.md` with invalid frontmatter fell out of
    discovery entirely and every migration guard stayed green. A malformed agent
    is exactly the file most likely to be carrying something wrong.

    Residual, stated rather than papered over: a new tree that uses a bare
    `.md` suffix *and* omits `role` entirely is still invisible here. Closing
    that would mean treating every markdown file with a `description` as an
    agent, which pulls in skills, prompts, and analysis documents. The two
    signals below cover every naming convention the repository actually uses
    for agents.
    """
    if name.endswith(_AGENT_FILE_SUFFIXES):
        return True
    return front is not None and _declares_agent_metadata(front)


def _discover_agent_trees() -> set[str]:
    """Every tracked directory holding agent files, found by search, not config."""
    found: set[str] = set()
    for name in _tracked_markdown():
        if name in _EXEMPT_FILES:
            continue
        path = _REPO_ROOT / name
        if not path.is_file():
            continue
        if _looks_like_an_agent_file(name, path, _frontmatter(path)):
            found.add(PurePosixPath(name).parent.as_posix())
    return found


# The canonical tree, from the same constant the matrix validator resolves
# against. Quoted from build/scripts/validate_agent_matrix_refs.py:137:
#   CANONICAL_TREE = Path("templates/agents")
_CANONICAL_TREE = _vamr.CANONICAL_TREE.as_posix()

# Suffix-matching sibling documents that are deliberately not agent
# definitions. They are the only files in a configured tree allowed to fail the
# fail-closed corpus guard in `test_agent_tree_discovery.py`. Listed per file,
# not per directory, for the same reason as `_EXEMPT_FILES`: adding one is then
# a deliberate edit rather than silent inheritance.
#
# Quoted from the same predicate's docstring in
# build/scripts/validate_agent_matrix_refs.py, which measured the same four:
# "Re-measured across all six trees on 2026-08-20: 190 files carry a configured
# tree's suffix, the rule keeps all 186 agent definitions, and it excludes
# exactly four suffix-matching sibling documents: ``.claude/agents/AGENTS.md``,
# ``.claude/agents/CLAUDE.md``, ``src/claude/AGENTS.md``, and
# ``src/claude/claude-instructions.template.md``."
#
# The quotation and its source are updated together on purpose. The previous
# pair both said 175, true when written and false by this PR, and a quotation
# that drifts from its source is the failure `canonical-source-mirror` names.
# Cited by symbol rather than by line range for the same reason: those line
# numbers moved in this very change.
_NON_AGENT_SIBLINGS = frozenset(
    {
        ".claude/agents/AGENTS.md",
        ".claude/agents/CLAUDE.md",
        "src/claude/AGENTS.md",
        "src/claude/claude-instructions.template.md",
    }
)


def _why_not_an_agent_definition(path: Path) -> str:
    """Empty when the repo's own predicate accepts `path`, else why it does not.

    `is_agent_definition` fills `reasons` only for the two failures it can
    describe, a duplicated frontmatter key and a `description` that is present
    but unusable. Absent, unterminated, and unparseable blocks return None
    silently, so the fallback names all of them rather than reporting an empty
    string that reads as no finding.
    """
    reasons: list[str] = []
    if _vamr.is_agent_definition(path, reasons):
        return ""
    return "; ".join(reasons) or (
        "frontmatter is absent, unterminated, unparseable, or carries no non-empty `description`"
    )


def _roles_by_agent_name() -> dict[str, dict[str, object]]:
    """Agent name -> tree -> declared role, across every configured tree.

    The name is the filename with that tree's own suffix stripped, which is how
    `validate_agent_matrix_refs` resolves a citation: the trees do not agree on
    one suffix, so `orchestrator.shared.md`, `orchestrator.md`, and
    `orchestrator.agent.md` are all the agent `orchestrator`.

    Files the corpus predicate rejects are skipped here and caught by the
    fail-closed guard instead. So is the narrower case of the two parsers
    disagreeing, which `test_every_agent_definition_declares_a_known_role`
    reports.
    """
    roles: dict[str, dict[str, object]] = {}
    for tree, suffix in _vamr.AGENT_TREES:
        for path in sorted((_REPO_ROOT / tree).glob(f"*{suffix}")):
            if not _vamr.is_agent_definition(path):
                continue
            front = _frontmatter(path)
            if front is None:
                continue
            roles.setdefault(path.name[: -len(suffix)], {})[tree.as_posix()] = _declared_role(front)
    return roles


def _cross_tree_role_disagreements(roles: Mapping[str, Mapping[str, object]]) -> list[str]:
    """Names whose copies declare more than one role, with the canonical value.

    The expected value is the template's when the template carries the agent,
    since `templates/agents` is the canonical tree every other copy is
    generated or hand-mirrored from. When it does not, the first tree in sorted
    order stands in, so a pair of non-template copies is still compared rather
    than dropped.

    A tree-specific agent, which Copilot asked to be handled explicitly, needs
    no special case and deliberately does not get one: the single tree is its
    own source, the comparison excludes the source, and nothing is left to
    disagree. Guarding on `len(by_tree) < 2` would state that in a branch no
    input can make observable. What must not happen is the naive spelling,
    `by_tree.get(_CANONICAL_TREE)`, which reads a template-less agent as
    expecting `None` and reports every tree-specific agent as divergent.
    `test_cross_tree_role_comparison_verdicts` pins that case.

    Compared with `!=` rather than through a set, because a role is whatever
    the frontmatter said. A list or a dict there is a defect the known-role
    guard reports, and it must not crash this one on the way past. Sorting is
    by tree name for the same reason: role values are not ordered.
    """
    offenders: list[str] = []
    for name in sorted(roles):
        by_tree = roles[name]
        source = _CANONICAL_TREE if _CANONICAL_TREE in by_tree else sorted(by_tree)[0]
        expected = by_tree[source]
        divergent = [
            (tree, by_tree[tree])
            for tree in sorted(by_tree)
            if tree != source and by_tree[tree] != expected
        ]
        if divergent:
            offenders.append(
                f"{name}: {source} declares {expected!r}, but "
                + ", ".join(f"{tree} declares {role!r}" for tree, role in divergent)
            )
    return offenders
