"""Guards for the agent-tree frontmatter gate (issue #5493).

The gate exists because a frontmatter-less Markdown file under
``.claude/agents/`` still registers with the Claude Code plugin loader as a
dispatchable subagent. Five did, for a quarter, while our own validators were
narrowed to skip them.

Coverage:

- positive: a tree of well-formed agent definitions passes, and the real
  repository tree passes.
- negative: a bare stub, a file whose frontmatter carries no ``description``,
  a file whose ``description`` is blank, and a file nested in a subdirectory
  each fail; the nested case is the one a non-recursive glob misses.
- edge: a missing tree, an empty tree, and a missing predicate are config
  errors rather than passes, because a silently empty scan proves nothing.
  Also: the gate carries no allowlist, which is the whole point of it.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_agent_tree_frontmatter as gate

_AGENT = """---
name: sample
description: A sample agent used by the tests.
model: sonnet
---

# Sample

Body.
"""


def _repo(tmp_path: Path) -> Path:
    """Build a minimal repo root: the agent tree plus the real predicate source."""
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    predicate = tmp_path / gate._PREDICATE_SOURCE
    predicate.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / gate._PREDICATE_SOURCE, predicate)
    return tmp_path


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / ".claude" / "agents" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- positive ------------------------------------------------------------


def test_tree_of_agent_definitions_passes(tmp_path):
    repo = _repo(tmp_path)
    _write(repo, "alpha.md", _AGENT)
    _write(repo, "beta.md", _AGENT)

    assert gate.find_non_agent_files(repo) == []
    assert gate.validate_agent_tree_frontmatter(repo) is True
    assert gate.main([str(repo)]) == 0


def test_real_repository_tree_passes():
    """The gate holds at zero on this head. Without this the suite is vacuous."""
    assert gate.find_non_agent_files(REPO_ROOT) == []


def test_real_repository_tree_is_not_empty():
    """Negative control for the guard above: an empty scan would pass falsely."""
    scanned = sorted((REPO_ROOT / gate.AGENT_TREE).rglob("*.md"))
    assert len(scanned) > 20


# --- negative ------------------------------------------------------------


def test_frontmatter_less_stub_fails(tmp_path):
    repo = _repo(tmp_path)
    _write(repo, "alpha.md", _AGENT)
    _write(repo, "CLAUDE.md", "<claude-mem-context>\n*No recent activity*\n</claude-mem-context>\n")

    findings = gate.find_non_agent_files(repo)
    assert [rel.as_posix() for rel, _ in findings] == [".claude/agents/CLAUDE.md"]
    assert gate.validate_agent_tree_frontmatter(repo) is False
    assert gate.main([str(repo)]) == 1


def test_frontmatter_without_description_fails(tmp_path):
    repo = _repo(tmp_path)
    _write(repo, "alpha.md", "---\nname: alpha\nmodel: sonnet\n---\n\nBody.\n")

    findings = gate.find_non_agent_files(repo)
    assert [rel.as_posix() for rel, _ in findings] == [".claude/agents/alpha.md"]


def test_blank_description_fails(tmp_path):
    repo = _repo(tmp_path)
    _write(repo, "alpha.md", "---\nname: alpha\ndescription: '   '\n---\n\nBody.\n")

    findings = gate.find_non_agent_files(repo)
    assert [rel.as_posix() for rel, _ in findings] == [".claude/agents/alpha.md"]


def test_nested_reference_document_fails(tmp_path):
    """The #5493 shape: a references/ subdirectory a flat glob never sees."""
    repo = _repo(tmp_path)
    _write(repo, "alpha.md", _AGENT)
    _write(repo, "security/references/threat-model-template.md", "# Threat Model\n\nProse.\n")

    findings = gate.find_non_agent_files(repo)
    assert [rel.as_posix() for rel, _ in findings] == [
        ".claude/agents/security/references/threat-model-template.md"
    ]


def test_every_non_agent_file_is_reported(tmp_path):
    """Reporting only the first finding would hide four of the five #5493 files."""
    repo = _repo(tmp_path)
    _write(repo, "alpha.md", _AGENT)
    for rel in ("AGENTS.md", "CLAUDE.md", "security/references/a.md"):
        _write(repo, rel, "Prose with no frontmatter.\n")

    findings = gate.find_non_agent_files(repo)
    assert [rel.as_posix() for rel, _ in findings] == [
        ".claude/agents/AGENTS.md",
        ".claude/agents/CLAUDE.md",
        ".claude/agents/security/references/a.md",
    ]


# --- edge ----------------------------------------------------------------


def test_missing_tree_is_a_config_error(tmp_path):
    repo = _repo(tmp_path)
    shutil.rmtree(repo / ".claude" / "agents")

    with pytest.raises(FileNotFoundError):
        gate.find_non_agent_files(repo)
    assert gate.validate_agent_tree_frontmatter(repo) is False
    assert gate.main([str(repo)]) == 2


def test_empty_tree_does_not_pass_silently(tmp_path):
    """A scan that finds nothing is a passing scan that proves nothing."""
    repo = _repo(tmp_path)

    with pytest.raises(FileNotFoundError):
        gate.find_non_agent_files(repo)
    assert gate.validate_agent_tree_frontmatter(repo) is False


def test_missing_predicate_is_a_config_error(tmp_path):
    repo = _repo(tmp_path)
    _write(repo, "alpha.md", _AGENT)
    (repo / gate._PREDICATE_SOURCE).unlink()

    assert gate.main([str(repo)]) == 2


def test_invalid_repo_root_is_a_config_error(tmp_path):
    assert gate.main([str(tmp_path / "does-not-exist")]) == 2


def test_non_markdown_files_are_ignored(tmp_path):
    repo = _repo(tmp_path)
    _write(repo, "alpha.md", _AGENT)
    (repo / ".claude" / "agents" / "notes.txt").write_text("not markdown", encoding="utf-8")

    assert gate.find_non_agent_files(repo) == []


def test_gate_has_no_allowlist():
    """#4813 answered these files with exemptions. This gate must not repeat it."""
    source = (REPO_ROOT / "scripts" / "validation" / "check_agent_tree_frontmatter.py").read_text(
        encoding="utf-8"
    )
    for token in ("ALLOW", "EXEMPT", "_SKIP_FILES", "frozenset("):
        assert token not in source, f"gate grew an exemption mechanism: {token}"
