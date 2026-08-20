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


def _load_module(path: Path):
    """Import a repository module by path, for cross-consumer contract checks."""
    spec = importlib.util.spec_from_file_location(f"_probe_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

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

    Distinctive-suffix files are kept even when the predicate rejects them, so a
    malformed agent fails the role check instead of dropping out of the corpus.
    Copilot found the fail-open on PR #5177: `is_agent_definition` needs
    parseable frontmatter with a description, so an agent whose YAML breaks was
    excluded before the known-role test could report it, and the raw legacy-tier
    sweep only looks for retired *values* and would not see a bad `role`. Only
    `.agent.md` and `.shared.md` qualify, because the two trees using a bare
    `.md` also hold genuine non-agent siblings that have no frontmatter at all.
    """
    return [
        path
        for path in _agent_files()
        if _vamr.is_agent_definition(path)
        or path.name.endswith(_AGENT_FILE_SUFFIXES)
    ]


def _canonical_roles_by_agent() -> dict[str, str]:
    """Declared role per agent name in the shared template tree.

    The template is the canonical source: it is what `build/generate_agents.py`
    renders the platform copies from, so a copy disagreeing with it is drift.
    """
    canonical: dict[str, str] = {}
    template_root = _REPO_ROOT / "templates" / "agents"
    for path in sorted(template_root.glob("*.shared.md")):
        front = _frontmatter(path)
        if front is None:
            continue
        role = _declared_role(front)
        if isinstance(role, str):
            canonical[path.name.removesuffix(".shared.md")] = role.strip()
    return canonical


def _agent_name(path: Path) -> str:
    """Agent name from a filename, with every tree's suffix stripped."""
    name = path.name
    for suffix in (".shared.md", ".agent.md", ".md"):
        if name.endswith(suffix):
            return name.removesuffix(suffix)
    return name


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
        isinstance(scope.get("role"), str) or isinstance(scope.get("tier"), str)
        for scope in scopes
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
