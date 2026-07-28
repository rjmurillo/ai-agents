"""Regression test for the Context Budget Management section in agent prompts.

Issue #1728 names a context-pressure pattern: an agent's output quality degrades
silently as its context window fills. PR #2167 introduced the ``## Context Budget
Management`` section to the implementer agent as a tracer, and a later slice
extended it to the orchestrator.

The original section asked the agent to detect that pressure by watching its own
output for "pressure signals" and to checkpoint or hand off when one fired. That
mitigation is unsound: the context window size is not exposed to the model, so
any claim about how much remains is fabricated, and a rule keyed to a fabricated
self-report is trivially weaponized into a session escape. The wiki concept note
that motivated the section places enforcement in the harness (PreCompact and the
session log), not in the model's self-assessment.

The section now keeps the durable half (commit and record as you go, degrade with
evidence) and replaces the self-assessed trigger with objective criteria the
repository already uses for ``[NEEDS_DECOMPOSITION]``. ``REQUIRED_PHRASES`` pins
what must survive; ``FORBIDDEN_PHRASES`` pins what must not come back.

The section must appear in every platform copy of each participating agent so the
guidance reaches the agent regardless of which install a consumer uses. This test
pins that contract so a future template edit cannot silently drop the section from
one copy and leave the parity group inconsistent.

If a new agent adopts the section, add it to ``BUDGET_AGENTS``. The canonical
source is ``templates/agents/<name>.shared.md``; the other copies are generated
(copilot-cli, vs-code) or hand-maintained for install parity (.claude, .github,
src/claude).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Agents that carry the Context Budget Management section. Add new adopters here.
BUDGET_AGENTS = (
    "implementer",
    "orchestrator",
)

SECTION_HEADING = "## Context Budget Management"

# Phrases that must appear in the section body. These pin the load-bearing parts
# of the pattern: state that context is unobservable, checkpoint on an objective
# cadence, degrade explicitly, and name the harness-side hook that backstops it.
REQUIRED_PHRASES = (
    "Your context window is finite",
    "You cannot observe your own context usage.",
    "fabricated",
    "Checkpoint protocol",
    "Degrade, do not fail silently.",
    "PreCompact",
)

# Phrases that must NOT reappear. Each one asks the agent to act on a self-report
# about its own context, which it cannot make truthfully. Keyed rules like these
# are the weaponization path: the agent fabricates the trigger, then banks the
# stop or the handoff the rule authorizes.
FORBIDDEN_PHRASES = (
    "pressure signal",
    "you are near the limit",
    "budget is nearly spent",
    "within budget",
)

# The six install/source copies of a shared agent. Mirrors the SHARED_AGENT
# parity group in build/scripts/validate_install_parity.py.
PLATFORM_PATHS = (
    ("templates/agents", "{name}.shared.md"),
    (".claude/agents", "{name}.md"),
    (".github/agents", "{name}.agent.md"),
    ("src/claude", "{name}.md"),
    ("src/copilot-cli/agents", "{name}.agent.md"),
    ("src/vs-code-agents", "{name}.agent.md"),
)


def _agent_files() -> list[Path]:
    paths: list[Path] = []
    for subdir, pattern in PLATFORM_PATHS:
        for name in BUDGET_AGENTS:
            paths.append(REPO_ROOT / subdir / pattern.format(name=name))
    return paths


def _context_budget_section(path: Path) -> str:
    assert path.exists(), f"Expected agent prompt at {path}"
    text = path.read_text(encoding="utf-8")
    start = text.find(SECTION_HEADING)
    assert start != -1, (
        f"{path.relative_to(REPO_ROOT)} is missing the {SECTION_HEADING!r} heading."
    )
    rest = text[start + len(SECTION_HEADING):]
    next_heading = rest.find("\n## ")
    return rest if next_heading == -1 else rest[:next_heading]


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_agent_carries_context_budget_section(path: Path) -> None:
    """Each participating agent copy carries the section heading exactly once.

    Exactly one occurrence guards against both a missing section (regression that
    drops the guidance) and a duplicated section (a botched merge that pastes it
    twice).
    """
    assert path.exists(), f"Expected agent prompt at {path}"
    text = path.read_text(encoding="utf-8")
    count = text.count(SECTION_HEADING)
    assert count == 1, (
        f"{path.relative_to(REPO_ROOT)} must contain exactly one "
        f"{SECTION_HEADING!r} heading. Found {count}. Re-add or deduplicate the "
        "section so the context-pressure guidance stays consistent across the "
        "parity group."
    )


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_section_carries_required_phrases(path: Path) -> None:
    """The section body pins the load-bearing parts of the pattern.

    A heading with an empty or reworded body would pass the count check but lose
    the guidance. Assert the load-bearing phrases survive.
    """
    body = _context_budget_section(path)
    for phrase in REQUIRED_PHRASES:
        assert phrase in body, (
            f"{path.relative_to(REPO_ROOT)} is missing required phrase "
            f"{phrase!r} from the Context Budget Management section. The section "
            "must state that context usage is unobservable, give an objective "
            "checkpoint protocol, and carry the degrade-with-evidence rule."
        )


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_section_rejects_self_reported_context_triggers(path: Path) -> None:
    """The section must not key any instruction to a self-reported context state.

    Negative case for the required-phrase test above. The model cannot observe its
    remaining context, so a rule that fires on "you are near the limit" fires on a
    fabricated premise, and the stop or handoff it authorizes is free to take. The
    checkpoint cadence and the decomposition criteria must stay objective.
    """
    body = _context_budget_section(path).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in body, (
            f"{path.relative_to(REPO_ROOT)} Context Budget Management section "
            f"contains {phrase!r}, which keys behaviour to a self-reported "
            "context state the model cannot observe. Trigger the checkpoint on an "
            "objective cadence and [NEEDS_DECOMPOSITION] on the countable "
            "criteria (XL complexity, more than five files) instead."
        )


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_section_has_no_em_or_en_dash(path: Path) -> None:
    """The section body uses no em or en dash, per .claude/rules/universal.md.

    Bot reviewers flag every dash. Pinning the carve-out here catches a regression
    in the section we own without forcing a fix on pre-existing dashes elsewhere
    in the hand-maintained .github copy.
    """
    body = _context_budget_section(path)
    for bad, name in (("\u2014", "em dash (U+2014)"), ("\u2013", "en dash (U+2013)")):
        assert bad not in body, (
            f"{path.relative_to(REPO_ROOT)} Context Budget Management section "
            f"contains a {name}. Use commas, periods, colons, or hyphens instead "
            "(.claude/rules/universal.md MUST-5)."
        )


def test_orchestrator_section_is_routing_scoped_not_code_scoped() -> None:
    """The orchestrator section is adapted to routing, not copied from implementer.

    The orchestrator does not write code, so the implementer's code-specific
    pressure signals (stubs, TODO bodies) do not apply. This edge test confirms
    the adaptation: the orchestrator section names synthesis and delegation, and
    does not carry the implementer's code-stub phrasing. Guards against a future
    edit that lazily pastes the implementer text into the orchestrator.
    """
    body = _context_budget_section(REPO_ROOT / "templates/agents/orchestrator.shared.md")
    assert "synthesis" in body.lower(), (
        "Orchestrator Context Budget section must name synthesis (its domain). "
        "It appears to have been copied from the implementer without adaptation."
    )
    assert "re-delegate" in body.lower(), (
        "Orchestrator Context Budget section must name re-delegation as the "
        "duplicate-work defect it guards against. It appears to have been copied "
        "from the implementer."
    )
    assert "placeholder bodies" not in body, (
        "Orchestrator Context Budget section carries the implementer's "
        "code-stub phrasing ('placeholder bodies'). The orchestrator does not "
        "write code; adapt the pressure signals to routing and synthesis."
    )
