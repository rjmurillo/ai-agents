from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATHS = (
    PROJECT_ROOT / "templates/agents/implementer.shared.md",
    PROJECT_ROOT / "src/claude/implementer.md",
    PROJECT_ROOT / ".claude/agents/implementer.md",
    PROJECT_ROOT / ".github/agents/implementer.agent.md",
    PROJECT_ROOT / "src/copilot-cli/agents/implementer.agent.md",
    PROJECT_ROOT / "src/vs-code-agents/implementer.agent.md",
)


def _prompt_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_consumer_owned_agents_directory_skips_scaffold_gates() -> None:
    for path in PROMPT_PATHS:
        text = _prompt_text(path)

        assert (
            "If `.agents/` is missing, or `.agents/` exists but "
            "`.agents/AGENT-INSTRUCTIONS.md` is missing"
        ) in text, path
        assert "consumer-owned `.agents/` directory without that file" in text, path


def test_ai_agents_scaffold_still_blocks_incomplete_required_docs() -> None:
    """HANDOFF.md is retired (issue #5168); AGENTS.md is still required.

    A complete-but-partial toolkit scaffold (AGENT-INSTRUCTIONS.md present,
    root AGENTS.md missing) still hard-stops instead of failing open.
    """
    for path in PROMPT_PATHS:
        text = _prompt_text(path)

        assert (
            "If `.agents/AGENT-INSTRUCTIONS.md` exists but the root `AGENTS.md` "
            "is missing: stop and report `[BLOCKED] Missing root agent instructions`"
        ) in text, path


def test_implementer_prompt_no_longer_keys_on_directory_presence() -> None:
    forbidden = (
        "If `.agents/` exists but `.agents/HANDOFF.md` is missing",
        "If `.agents/` exists but `.agents/AGENT-INSTRUCTIONS.md` is missing",
    )
    for path in PROMPT_PATHS:
        text = _prompt_text(path)

        for phrase in forbidden:
            assert phrase not in text, path


def test_implementer_prompt_drops_the_handoff_blocking_gate() -> None:
    """Deleting HANDOFF.md must not resurrect the retired gate (issue #5168).

    templates/agents/implementer.shared.md used to hard-block every session
    with `[BLOCKED] No prior session context available` when
    `.agents/HANDOFF.md` was missing. HANDOFF.md is now permanently retired
    (per-issue handoffs and ADR-014 carry continuity instead), so that block
    would fire on every future run. Commit e89d30097 removed it; this guards
    against reintroduction.
    """
    for path in PROMPT_PATHS:
        text = _prompt_text(path)

        assert (
            "If `.agents/AGENT-INSTRUCTIONS.md` exists but `.agents/HANDOFF.md` "
            "is missing"
        ) not in text, path
        assert "[BLOCKED] No prior session context available" not in text, path
