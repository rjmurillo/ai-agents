#!/usr/bin/env python3
"""Gate: every ``.md`` file under ``.claude/agents/`` must be an agent definition.

The Claude Code plugin loader scans ``.claude/agents/`` recursively and
registers every Markdown file it finds as a dispatchable subagent. A file with
no YAML frontmatter still registers; the loader synthesizes a description
("Agent from project-toolkit plugin") and moves on. There is no frontmatter to
fail on, so nothing errors, and an orchestrator picking a delegation target off
the agent listing can dispatch to a reference document whose whole system prompt
is prose with no role, no tools contract, and no output format. The run returns
plausible text and the orchestrator accepts it.

Five such files shipped for months (issue #5493): ``AGENTS.md``, ``CLAUDE.md``,
and three documents under ``security/references/``. Issue #4813 named the same
five a quarter earlier and responded by narrowing this repository's own
validator globs (``check_agent_skill_discriminator.py`` grew
``_NON_AGENT_NAMES`` and a ``/references/`` skip). That taught our CI to look
away. It did nothing to the loader, which is a separate consumer reading the
same directory, so all five kept shipping to every session. This gate is the
one that closes the loop: it fails the build rather than exempting the file.

Membership is decided by content, not by filename. ``is_agent_definition`` in
``build/scripts/validate_agent_matrix_refs.py`` is the repository's canonical
predicate (frontmatter block with a non-empty string ``description:`` key) and
is imported here rather than restated, so a change to what counts as an agent
cannot drift between the roster and this gate.

The scan walks the filesystem rather than ``git ls-files`` on purpose. The
loader reads the filesystem, so an untracked or ignored stub is just as
dispatchable as a committed one. A finding on an untracked file is a true
positive.

There is no allowlist. The tree holds 31 files and all 31 are agent
definitions, so the gate holds at zero. Adding an exemption here would repeat
the #4813 mistake in a new file.

CLI::

    uv run python scripts/validation/check_agent_tree_frontmatter.py
    uv run python scripts/validation/check_agent_tree_frontmatter.py <repo-root>

Exit codes (ADR-035):
    0 - Success (every scanned file is an agent definition)
    1 - Logic error (one or more files carry no agent frontmatter)
    2 - Config error (invalid repository root, or the tree is missing)
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path

# The one tree the Claude Code plugin loader scans recursively for agents.
# The other agent trees use an ``.agent.md`` suffix, so a bare ``.md`` sibling
# in them is never loaded; ``validate_copilot_agent_frontmatter.py`` covers
# those. Keep this a single entry until a second recursive tree exists.
AGENT_TREE = Path(".claude/agents")

_PREDICATE_SOURCE = Path("build/scripts/validate_agent_matrix_refs.py")


def _load_predicate(repo_root: Path) -> Callable[[Path, list[str] | None], bool]:
    """Return ``is_agent_definition`` from the canonical matrix validator.

    Loaded by path rather than imported by name: ``build/scripts`` is not a
    package on ``sys.path`` when ``pre_pr.py`` runs, and copying the predicate
    would let the roster and this gate disagree about what an agent is.
    """
    path = repo_root / _PREDICATE_SOURCE
    spec = importlib.util.spec_from_file_location("_agent_matrix_refs_for_gate", path)
    if spec is None or spec.loader is None:
        msg = f"cannot load agent predicate from {path}"
        raise FileNotFoundError(msg)
    module = importlib.util.module_from_spec(spec)
    # Register before executing. ``@dataclass`` resolves annotations through
    # ``sys.modules[cls.__module__]``, so a module executed while absent from
    # that table raises AttributeError on the first dataclass it defines.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    predicate: Callable[[Path, list[str] | None], bool] = module.is_agent_definition
    return predicate


def find_non_agent_files(repo_root: Path) -> list[tuple[Path, str]]:
    """Return ``(relative path, reason)`` for each scanned file that is not an agent.

    Raises ``FileNotFoundError`` when the tree or the predicate is absent. A
    silently empty scan is a passing scan that proves nothing, so absence is a
    configuration error rather than a pass.
    """
    tree = repo_root / AGENT_TREE
    if not tree.is_dir():
        msg = f"agent tree not found: {tree}"
        raise FileNotFoundError(msg)

    is_agent_definition = _load_predicate(repo_root)
    scanned = sorted(tree.rglob("*.md"))
    if not scanned:
        msg = f"agent tree yields no Markdown files: {tree}"
        raise FileNotFoundError(msg)

    findings: list[tuple[Path, str]] = []
    for path in scanned:
        reasons: list[str] = []
        if is_agent_definition(path, reasons):
            continue
        reason = reasons[0] if reasons else "no YAML frontmatter with a description key"
        findings.append((path.relative_to(repo_root), reason))
    return findings


def validate_agent_tree_frontmatter(repo_root: Path) -> bool:
    """Return True when every ``.md`` under the agent tree is an agent definition.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr.py``.
    """
    try:
        findings = find_non_agent_files(repo_root)
    except FileNotFoundError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return False

    if not findings:
        return True

    print(
        f"[FAIL] {len(findings)} file(s) under {AGENT_TREE.as_posix()}/ carry no agent "
        "frontmatter. The Claude Code plugin loader registers each one as a "
        "dispatchable subagent with a synthesized description, so an orchestrator "
        "can misroute work to a document with no role and no output contract:",
        file=sys.stderr,
    )
    for rel, reason in findings:
        print(f"  {rel.as_posix()}  ({reason})", file=sys.stderr)
    print(
        "\nFix: move the file out of the agent tree (a skill's references/ "
        "directory is the usual home) or delete it. Do not add an exemption; "
        "the loader does not read exemptions. Refs issue #5493.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    if not (repo_root / _PREDICATE_SOURCE).is_file():
        print(f"[FAIL] Missing agent predicate: {repo_root / _PREDICATE_SOURCE}", file=sys.stderr)
        return 2
    if not (repo_root / AGENT_TREE).is_dir():
        print(f"[FAIL] Missing agent tree: {repo_root / AGENT_TREE}", file=sys.stderr)
        return 2
    return 0 if validate_agent_tree_frontmatter(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
