"""code-reviewer inherits the host model on Copilot hosts (issue #6638).

Copilot CLI refused `claude-haiku-4.5` on a host that did not offer it, so the
reviewer never started when the caller omitted `model`. The Copilot CLI and
VS Code projections now carry no `model:` key and inherit the host default.
The Claude projection keeps its `haiku` alias, which Claude Code resolves
itself. This module pins both halves in the committed trees.

A live run on a host without haiku is not possible in CI, so these checks
read the generated output instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COPILOT_SIDE_FILES = (
    REPO_ROOT / "src" / "copilot-cli" / "agents" / "code-reviewer.agent.md",
    REPO_ROOT / "src" / "vs-code-agents" / "code-reviewer.agent.md",
    REPO_ROOT / ".github" / "agents" / "code-reviewer.agent.md",
)
CLAUDE_FILES = (
    REPO_ROOT / "src" / "claude" / "agents" / "code-reviewer.md",
    REPO_ROOT / ".claude" / "agents" / "code-reviewer.md",
)
COPILOT_TEMPLATES = (
    REPO_ROOT / "templates" / "agents" / "code-reviewer.copilot.md.tmpl",
    REPO_ROOT / "templates" / "agents" / "code-reviewer.shared.md",
)


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    _, block, _ = text.split("---\n", 2)
    loaded = yaml.safe_load(block)
    assert isinstance(loaded, dict), f"{path} frontmatter is not a mapping"
    return loaded


def _assert_no_model(path: Path) -> None:
    assert "model" not in _frontmatter(path), (
        f"{path} pins a model, so a host without it rejects the reviewer."
    )


@pytest.mark.parametrize("path", COPILOT_SIDE_FILES, ids=lambda p: p.parent.parent.name)
def test_copilot_side_code_reviewer_sets_no_model(path: Path) -> None:
    _assert_no_model(path)


@pytest.mark.parametrize("path", COPILOT_TEMPLATES, ids=lambda p: p.name)
def test_copilot_side_template_sets_no_model_tier(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert not [line for line in lines if line.startswith("model_tier:")]


@pytest.mark.parametrize("path", CLAUDE_FILES, ids=lambda p: p.parent.parent.name)
def test_claude_code_reviewer_keeps_haiku_alias(path: Path) -> None:
    assert _frontmatter(path).get("model") == "haiku"


def test_versioned_haiku_id_is_absent_from_copilot_side_files() -> None:
    for path in COPILOT_SIDE_FILES:
        text = path.read_text(encoding="utf-8")
        assert "claude-haiku-4.5" not in text
        assert "Claude Haiku 4.5" not in text


def test_pinned_model_is_detected(tmp_path: Path) -> None:
    """Negative control: a reviewer that pins a model fails the check."""
    agent = tmp_path / "code-reviewer.agent.md"
    agent.write_text("---\ndescription: x\nmodel: claude-haiku-4.5\n---\nbody\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="pins a model"):
        _assert_no_model(agent)


def test_unpinned_model_passes_check(tmp_path: Path) -> None:
    """Edge: frontmatter with no model key passes."""
    agent = tmp_path / "code-reviewer.agent.md"
    agent.write_text("---\ndescription: x\n---\nbody\n", encoding="utf-8")

    _assert_no_model(agent)
