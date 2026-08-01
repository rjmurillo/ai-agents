"""Regression guards for knowledge-surface contradictions fixed in issues #4155, #4169, #4175.

Each test pins a previously broken or contradictory claim so the same wording
cannot re-enter an always-on surface unnoticed.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_AGENTS_MD = REPO_ROOT / "AGENTS.md"
_CLAUDE_AGENTS_RULE = REPO_ROOT / ".claude" / "rules" / "claude-agents.md"
_TEMPLATES_RULE = REPO_ROOT / ".claude" / "rules" / "templates.md"


# ---------------------------------------------------------------------------
# Issue #4155: detect_agent_drift.py compares src/claude vs src/vs-code-agents,
# NOT vs templates. templates.md MUST NOT list src/claude/ as generated.
# ---------------------------------------------------------------------------


def test_templates_rule_does_not_list_src_claude_as_generated() -> None:
    """templates.md MUST NOT cite src/claude/ as a generated tree to avoid editing.

    src/claude/ is hand-maintained (claude-agents.md MUST-1 says "Edit Claude
    agents directly"). Listing it as a file that must not be edited because it
    is generated contradicts that rule and deadlocks any agent that loads both.
    """
    text = _TEMPLATES_RULE.read_text(encoding="utf-8")
    must_not_start = text.index("## MUST NOT")
    must_not_section = text[must_not_start:]
    # The specific phrase that caused the deadlock was listing src/claude/ as a
    # generated file in the prohibition, e.g.:
    # "MUST NOT edit generated files directly (`src/claude/`..."
    assert "generated files directly (`src/claude/" not in must_not_section, (
        "templates.md MUST NOT section prohibits editing src/claude/ as a generated "
        "file. src/claude/ is hand-maintained; this contradicts claude-agents.md "
        "MUST-1 ('Edit Claude agents directly'). Remove it and list the actual "
        "generated trees: src/copilot-cli/agents/ and src/vs-code-agents/."
    )


def test_templates_rule_references_actual_generated_trees() -> None:
    """templates.md MUST reference the trees the generator actually writes.

    The generator writes src/copilot-cli/agents/ and src/vs-code-agents/.
    Those must appear in the MUST-2 commit instruction.
    """
    text = _TEMPLATES_RULE.read_text(encoding="utf-8")
    assert "src/copilot-cli/" in text, (
        "templates.md should reference src/copilot-cli/ as a generated destination."
    )
    assert "src/vs-code-agents/" in text, (
        "templates.md should reference src/vs-code-agents/ as a generated destination."
    )


def test_claude_agents_rule_does_not_claim_drift_detector_compares_templates() -> None:
    """claude-agents.md must not say detect_agent_drift.py compares vs templates.

    The detector compares src/claude/ against src/vs-code-agents/, not against
    templates/agents/*.shared.md. Saying 'diverges from the shared body' implies
    a direct template comparison that never happens.
    """
    text = _CLAUDE_AGENTS_RULE.read_text(encoding="utf-8")
    # These phrases would mean "compares against the template"
    bad_phrases = [
        "diverges from the shared body",
        "stays in sync with the shared template body",
        "diverge from that shared body",
    ]
    for phrase in bad_phrases:
        assert phrase not in text, (
            f"claude-agents.md contains '{phrase}', implying detect_agent_drift.py "
            "compares src/claude/ against the shared template. It actually compares "
            "against VS Code copies (src/vs-code-agents/). Correct the description."
        )


def test_claude_agents_and_templates_rules_agree_src_claude_is_hand_maintained() -> None:
    """The two rules must not contradict each other on whether src/claude/ is generated.

    claude-agents.md says edit src/claude/ directly (MUST-1).
    templates.md must not prohibit that edit by listing src/claude/ as generated.
    If both load simultaneously (they do: both have applyTo matching src/claude/**)
    an agent holding both rules is deadlocked.
    """
    claude_agents_text = _CLAUDE_AGENTS_RULE.read_text(encoding="utf-8")
    templates_text = _TEMPLATES_RULE.read_text(encoding="utf-8")

    # claude-agents.md must still say src/claude/ is hand-maintained
    assert "hand-maintained" in claude_agents_text, (
        "claude-agents.md must state that src/claude/ is hand-maintained."
    )
    assert "NOT generated" in claude_agents_text, (
        "claude-agents.md must state that src/claude/ is NOT generated."
    )

    # templates.md MUST NOT section must not prohibit editing src/claude/ as generated
    must_not_start = templates_text.index("## MUST NOT")
    must_not_section = templates_text[must_not_start:]
    assert "generated files directly (`src/claude/" not in must_not_section, (
        "templates.md MUST NOT section contradicts claude-agents.md by listing "
        "src/claude/ as a generated file that must not be edited directly."
    )


# ---------------------------------------------------------------------------
# Issue #4169: AGENTS.md Never list must say "New bash scripts", not "Use bash".
# An unqualified "Use bash" contradicts claude-model-patches.md which lists
# allowed bash patterns including git, gh, and package managers.
# ---------------------------------------------------------------------------


def test_agents_md_never_list_does_not_flatly_prohibit_use_bash() -> None:
    """AGENTS.md Never list must not say bare 'Use bash'.

    'Use bash' without a qualifier contradicts claude-model-patches.md which
    explicitly lists allowed bash patterns (git, gh, package managers, etc.).
    An agent holding both rules cannot tell which to follow; the correct
    wording is 'New bash scripts' to match all three detailed rules which
    scope the prohibition to authoring script files.
    """
    text = _AGENTS_MD.read_text(encoding="utf-8")
    never_start = text.index("**Never**:")
    never_line = text[never_start : text.index("\n", never_start)]
    assert "Use bash" not in never_line, (
        "AGENTS.md Never list contains 'Use bash' without qualifier. This contradicts "
        "claude-model-patches.md which enumerates allowed bash patterns (git, gh, "
        "package managers). Change to 'New bash scripts' to match the detailed rules."
    )


# ---------------------------------------------------------------------------
# Issue #4175: AGENTS.md Always list must not say "Bump plugin manifest".
# ADR-092 removed the version field from all plugin manifests; any bump
# now fails the validate_plugin_version_bump.py gate.
# ---------------------------------------------------------------------------


def test_agents_md_always_list_does_not_say_bump_plugin_manifest() -> None:
    """AGENTS.md Always list must not say 'Bump plugin manifest'.

    ADR-092 removed the version field from all plugin manifests. Following
    'Bump plugin manifest' now fails the validate_plugin_version_bump.py gate
    with exit 1. The correct entry is 'No manifest version (ADR-092)' or
    equivalent that reflects the current policy.
    """
    text = _AGENTS_MD.read_text(encoding="utf-8")
    always_start = text.index("**Always**:")
    always_line = text[always_start : text.index("\n", always_start)]
    assert "Bump plugin manifest" not in always_line, (
        "AGENTS.md Always list contains 'Bump plugin manifest'. ADR-092 removed the "
        "version field; bumping now fails the gate. Replace with guidance that "
        "reflects the current no-version policy."
    )
