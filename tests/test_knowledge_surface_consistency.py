"""Regression guards for issues #4155, #4169, and #4175."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_AGENTS_MD = REPO_ROOT / "AGENTS.md"
_CLAUDE_AGENTS_RULE = REPO_ROOT / ".claude" / "rules" / "claude-agents.md"
_TEMPLATES_RULE = REPO_ROOT / ".claude" / "rules" / "templates.md"
_CLAUDE_AGENTS_MIRRORS = (
    REPO_ROOT / ".github" / "instructions" / "claude-agents.instructions.md",
    REPO_ROOT / "src" / "copilot-cli" / "instructions" / "claude-agents.instructions.md",
)
_TEMPLATES_MIRRORS = (
    REPO_ROOT / ".github" / "instructions" / "templates.instructions.md",
    REPO_ROOT / "src" / "copilot-cli" / "instructions" / "templates.instructions.md",
)
_PLUGIN_VERSION_RULE_SURFACES = (
    REPO_ROOT / ".claude" / "rules" / "plugin-version-bump.md",
    REPO_ROOT / ".github" / "instructions" / "plugin-version-bump.instructions.md",
    REPO_ROOT
    / "src"
    / "copilot-cli"
    / "instructions"
    / "plugin-version-bump.instructions.md",
)
_KNOWLEDGE_PERSISTENCE_SURFACES = (
    REPO_ROOT / ".claude" / "rules" / "knowledge-persistence.md",
    REPO_ROOT / ".github" / "instructions" / "knowledge-persistence.instructions.md",
    REPO_ROOT
    / "src"
    / "copilot-cli"
    / "instructions"
    / "knowledge-persistence.instructions.md",
)
_ARCHITECTURE_SKILL_SURFACES = (
    REPO_ROOT / ".claude" / "skills" / "ai-agents-architecture-contract" / "SKILL.md",
    REPO_ROOT
    / "src"
    / "copilot-cli"
    / "skills"
    / "ai-agents-architecture-contract"
    / "SKILL.md",
)
_DRIFT_MEMORIES = (
    REPO_ROOT / ".serena" / "memories" / "agents-two-pipeline-mirror-recipe.md",
    REPO_ROOT
    / ".serena"
    / "memories"
    / "architecture"
    / "architecture-agent-mirror-two-pipeline.md",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    marker = f"\n{heading}\n"
    start = text.index(marker) + 1
    end = text.find("\n## ", start + len(heading))
    return text[start:] if end == -1 else text[start:end]


def _numbered_rule(section: str, number: int) -> str:
    prefix = f"{number}. "
    lines = section.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(prefix))
    item = [lines[start]]
    after_blank = False
    for line in lines[start + 1 :]:
        if re.match(r"\d+\. ", line) or line.startswith("## "):
            break
        if after_blank and line and not line.startswith((" ", "\t")):
            break
        item.append(line)
        after_blank = not line
    return "\n".join(item).rstrip()


def _boundary_entries(text: str, boundary: str) -> list[str]:
    prefix = f"**{boundary}**:"
    start = text.index(prefix)
    line = text[start : text.index("\n", start)]
    return line.removeprefix(prefix).split("|")


def _normalized(path: Path) -> str:
    return " ".join(_read(path).split())


def test_template_rules_name_only_generated_agent_trees() -> None:
    for path in (_TEMPLATES_RULE, *_TEMPLATES_MIRRORS):
        text = _read(path)
        must_2 = _numbered_rule(_section(text, "## MUST"), 2)
        should_2 = _numbered_rule(_section(text, "## SHOULD"), 2)
        generated_clause = re.search(
            r"Regenerated files under (.+?) MUST be committed", must_2, re.DOTALL
        )
        assert generated_clause is not None
        must_paths = set(re.findall(r"`([^`]+/)`", generated_clause.group(1)))

        expected = {"src/copilot-cli/agents/", "src/vs-code-agents/"}
        assert must_paths == expected
        assert should_2 == (
            "2. **Preview per platform**. SHOULD inspect the generated output for both "
            "target platforms (`src/copilot-cli/agents/<agent>.agent.md` and "
            "`src/vs-code-agents/<agent>.agent.md`) to confirm the change renders "
            "correctly."
        )


def test_templates_rule_uses_portable_claude_agents_reference() -> None:
    for path in (_TEMPLATES_RULE, *_TEMPLATES_MIRRORS):
        must_not_1 = _numbered_rule(_section(_read(path), "## MUST NOT"), 1)
        assert ".claude/rules/claude-agents.md" not in must_not_1
        assert "claude-agents rule" in must_not_1


def test_claude_agents_rule_states_drift_detector_inputs() -> None:
    for path in (_CLAUDE_AGENTS_RULE, *_CLAUDE_AGENTS_MIRRORS):
        detector_section = _section(
            _read(path), "## What the drift detector does and does not catch"
        )

        assert "It compares two pairs, and `templates/` is in neither:" in detector_section
        assert _numbered_rule(detector_section, 1) == (
            "1. `src/claude/*.md` against `src/vs-code-agents/*.agent.md`"
        )
        assert _numbered_rule(detector_section, 2) == (
            "2. `.claude/agents/*.md` against `.github/agents/*.agent.md`"
        )


def test_other_detector_guidance_surfaces_state_actual_inputs() -> None:
    expected_first_pair = "`src/claude` against `src/vs-code-agents`"
    expected_pairs = (
        "`src/claude` against `src/vs-code-agents`, and `.claude/agents` against "
        "`.github/agents`"
    )

    for path in (*_TEMPLATES_MIRRORS, _TEMPLATES_RULE):
        text = _normalized(path)
        assert "does NOT compare templates against anything" in text
        assert expected_pairs in text

    for path in _ARCHITECTURE_SKILL_SURFACES:
        text = _normalized(path)
        assert "NOT against templates" in text
        assert expected_pairs in text

    recipe_text = _normalized(_DRIFT_MEMORIES[0])
    assert "never reads a template body" in recipe_text
    assert expected_first_pair in recipe_text

    architecture_text = _normalized(_DRIFT_MEMORIES[1])
    assert "never reads a template body" in architecture_text
    assert expected_pairs in architecture_text

    obsolete_claims = (
        "compares agents against templates",
        "diverges from the shared body",
        "diverges from the template",
        "stays in sync with the shared template body",
    )
    detector_surfaces = (
        _CLAUDE_AGENTS_RULE,
        *_CLAUDE_AGENTS_MIRRORS,
        _TEMPLATES_RULE,
        *_TEMPLATES_MIRRORS,
        *_ARCHITECTURE_SKILL_SURFACES,
        *_DRIFT_MEMORIES,
    )
    for path in detector_surfaces:
        text = _normalized(path).casefold()
        assert all(claim not in text for claim in obsolete_claims)


def test_rules_agree_src_claude_is_hand_maintained() -> None:
    expected_contract = (
        "`src/claude/*.md` are hand-maintained Claude agent prompts with unique "
        "Claude-specific content (`name`/`model` frontmatter). They are NOT generated."
    )
    for path in (_CLAUDE_AGENTS_RULE, *_CLAUDE_AGENTS_MIRRORS):
        text = _read(path)
        assert expected_contract in text

    for path in (_TEMPLATES_RULE, *_TEMPLATES_MIRRORS):
        must_not = _section(_read(path), "## MUST NOT")
        assert "generated files directly (`src/claude/" not in must_not
        assert (
            "`src/claude/`, `.claude/agents/`, or `.github/agents/`, "
            "which are hand-maintained"
        ) in must_not


def test_agents_never_scopes_bash_rule_to_new_scripts() -> None:
    entries = _boundary_entries(_read(_AGENTS_MD), "Never")

    assert "New bash scripts" in entries
    assert "Use bash" not in entries


def test_agents_always_requires_no_manifest_version_policy() -> None:
    entries = _boundary_entries(_read(_AGENTS_MD), "Always")

    assert "No manifest version (ADR-092)" in entries
    assert "Bump plugin manifest" not in entries


def test_plugin_version_rules_forbid_manifest_bumps() -> None:
    for path in _PLUGIN_VERSION_RULE_SURFACES:
        text = _read(path)
        assert "# Plugin Manifests Carry No Version" in text
        assert "must never add one back" in text
        assert "Nothing. Do not touch the manifests" in text


def test_knowledge_persistence_does_not_require_manifest_bumps() -> None:
    for path in _KNOWLEDGE_PERSISTENCE_SURFACES:
        assert "manifest bump" not in _read(path).casefold()


def test_readme_and_installation_agree_on_vscode_agent_path() -> None:
    """Regression guard for issue #4942.

    README and docs/installation.md must agree that VS Code agents
    are installed at .github/agents/, not src/vs-code-agents/.
    """
    readme = _read(REPO_ROOT / "README.md")
    installation = _read(REPO_ROOT / "docs" / "installation.md")

    # README platform table: VS Code row should point to .github/agents/
    vscode_row = re.search(
        r"\|\s*\*\*VS Code.*?\|\s*`([^`]+)`\s*\|", readme
    )
    assert vscode_row is not None, "VS Code row missing from README platform table"
    readme_path = vscode_row.group(1)

    # installation.md platform table: VS Code row
    install_vscode_row = re.search(
        r"\|\s*VS Code\s*\|\s*`([^`]+)`\s*\|", installation
    )
    assert install_vscode_row is not None
    install_path = install_vscode_row.group(1)

    assert readme_path == install_path, (
        f"README says {readme_path!r} but installation.md says {install_path!r}"
    )
    assert readme_path == ".github/agents/", (
        f"VS Code agent path should be .github/agents/, got {readme_path!r}"
    )
