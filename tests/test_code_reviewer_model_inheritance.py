"""code-reviewer inherits the host model on Copilot hosts (issue #6638).

Copilot CLI refused `claude-haiku-4.5` on a host that did not offer it, so the
reviewer never started when the caller omitted `model`. The Copilot CLI and
VS Code projections now carry no `model:` key and inherit the host default.
The Claude projection keeps its `haiku` alias, which Claude Code resolves
itself. This module pins both halves in the committed trees.

CI has no Copilot CLI host, so these checks read the generated output. The live
run is recorded on the pull request.

The last section guards every generated Copilot-side agent, not only
code-reviewer. `scripts/validation/check_model_pins.py` skips the generated
mirrors, and the generator turns `model_tier: haiku` into a versioned id, so a
new haiku-tier template would bring the bug back unseen.
"""

from __future__ import annotations

import json
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


# Repo-wide guard: no generated Copilot-side agent pins a model without evidence.
GENERATED_COPILOT_AGENT_GLOBS = (
    "src/copilot-cli/agents/*.agent.md",
    "src/vs-code-agents/*.agent.md",
    ".github/agents/*.agent.md",
)
PIN_MANIFEST = REPO_ROOT / ".agents" / "governance" / "model-pin-evidence.json"


def _generated_copilot_agents() -> list[Path]:
    found: list[Path] = []
    for pattern in GENERATED_COPILOT_AGENT_GLOBS:
        found.extend(sorted(REPO_ROOT.glob(pattern)))
    return found


def _kept_pin_agent_names(manifest: Path) -> set[str]:
    """Agent names that a KEEP_PIN manifest entry justifies."""
    data = json.loads(manifest.read_text(encoding="utf-8"))
    names: set[str] = set()
    for entry in data.get("pins", []):
        if entry.get("decision") == "KEEP_PIN":
            # Unit paths look like templates/agents/<name>.shared.md.
            names.add(Path(str(entry["unit"])).name.split(".")[0])
    return names


def _assert_pin_is_backed(path: Path, kept: set[str]) -> None:
    if "model" not in _frontmatter(path):
        return
    name = path.name.split(".")[0]
    assert name in kept, (
        f"{path} pins a model with no KEEP_PIN entry in the model-pin-evidence "
        "manifest. A host without that model rejects the agent."
    )


def test_generated_copilot_agents_are_discovered() -> None:
    """Guard against a vacuous pass if the trees move."""
    paths = _generated_copilot_agents()
    assert len(paths) >= 30
    relative = {p.relative_to(REPO_ROOT).as_posix() for p in paths}
    for pattern in GENERATED_COPILOT_AGENT_GLOBS:
        prefix = pattern.split("*")[0]
        assert any(r.startswith(prefix) for r in relative), f"no agents found under {prefix}"


@pytest.mark.parametrize(
    "path",
    _generated_copilot_agents(),
    ids=lambda p: p.relative_to(REPO_ROOT).as_posix(),
)
def test_generated_copilot_agent_pins_no_unbacked_model(path: Path) -> None:
    _assert_pin_is_backed(path, _kept_pin_agent_names(PIN_MANIFEST))


def test_unbacked_pin_in_generated_agent_is_rejected(tmp_path: Path) -> None:
    """Negative control: a haiku-tier template rendered to a versioned id fails."""
    agent = tmp_path / "new-agent.agent.md"
    agent.write_text("---\ndescription: x\nmodel: claude-haiku-4.5\n---\nbody\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="no KEEP_PIN entry"):
        _assert_pin_is_backed(agent, set())


def test_manifest_backed_pin_in_generated_agent_is_accepted(tmp_path: Path) -> None:
    """Positive: a KEEP_PIN entry for the agent justifies its pin."""
    manifest = tmp_path / "model-pin-evidence.json"
    manifest.write_text(
        json.dumps(
            {
                "pins": [
                    {"unit": "templates/agents/new-agent.shared.md", "decision": "KEEP_PIN"},
                    {"unit": "templates/agents/other.shared.md", "decision": "DROP_PIN"},
                ]
            }
        ),
        encoding="utf-8",
    )
    agent = tmp_path / "new-agent.agent.md"
    agent.write_text("---\ndescription: x\nmodel: claude-haiku-4.5\n---\nbody\n", encoding="utf-8")
    kept = _kept_pin_agent_names(manifest)

    assert kept == {"new-agent"}
    _assert_pin_is_backed(agent, kept)


def test_non_keep_pin_manifest_entry_does_not_back_a_pin(tmp_path: Path) -> None:
    """Edge: only KEEP_PIN decisions count."""
    manifest = tmp_path / "model-pin-evidence.json"
    manifest.write_text(
        json.dumps({"pins": [{"unit": "templates/agents/x.shared.md", "decision": "DROP_PIN"}]}),
        encoding="utf-8",
    )

    assert _kept_pin_agent_names(manifest) == set()


def test_empty_manifest_backs_nothing(tmp_path: Path) -> None:
    """Edge: the committed steady state, an empty pins list."""
    manifest = tmp_path / "model-pin-evidence.json"
    manifest.write_text(json.dumps({"pins": []}), encoding="utf-8")

    assert _kept_pin_agent_names(manifest) == set()
