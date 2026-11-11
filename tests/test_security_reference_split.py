"""Static guards for the security agent reference split.

The security body moved three blocks into ``security-scan`` skill references
(the CWE catalog, the impact analysis template, and the PIV CI check commands)
and now loads the three older sidecars from the same directory. These tests pin,
for every surface:

1. ``Reference Loading`` exists once, names every reference with a load
   condition, and carries the unresolved-path rule for a harness with no skill
   tree (VS Code).
2. Each stub heading names its reference, and each reference exists.
3. The agent-tree copies of the old sidecars are gone, so one copy remains.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / "src" / "claude" / "skills" / "security-scan" / "references"
LOADING_HEADING = "## Reference Loading"
PATH_FORM = (
    "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/security-scan/references/"
)
UNRESOLVED_RULE = "apply the rules in this file and state that the reference was unavailable"

SECURITY_PATHS = (
    Path("templates/agents/security.shared.md"),
    Path("src/claude/agents/security.md"),
    Path(".claude/agents/security.md"),
    Path(".github/agents/security.agent.md"),
    Path("src/copilot-cli/agents/security.agent.md"),
    Path("src/vs-code-agents/security.agent.md"),
)

# reference -> (load condition phrase in Reference Loading, text a stub keeps nearby)
REFERENCES = {
    "security-cwe-catalog.md": (
        "you scan for CWEs",
        "#### CWE-699 Categories and High-Priority CWEs",
    ),
    "security-impact-analysis.md": ("requests impact analysis", "#### Impact Analysis Deliverable"),
    "security-piv-ci-checks.md": ("write the CI check request", "You cannot run them."),
    "powershell-security-checklist.md": ("touches PowerShell", "### PowerShell Security Review"),
    "dependency-risk-scoring.md": ("adds a package", "## Dependency Risk Scoring"),
    "threat-model-template.md": ("write a threat model", "## Threat Model Format"),
}

RETIRED_COPIES = (
    "src/claude/security/references",
    ".github/agents/security/references",
)


def _text(path: Path) -> str:
    return " ".join((REPO_ROOT / path).read_text(encoding="utf-8").split())


def _loading_section(path: Path) -> str:
    text = _text(path)
    assert text.count(LOADING_HEADING) == 1, f"{path} must carry {LOADING_HEADING!r} once"
    rest = text[text.index(LOADING_HEADING) + len(LOADING_HEADING) :]
    boundary = rest.find(" ## ")
    return rest if boundary == -1 else rest[:boundary]


@pytest.mark.parametrize("path", SECURITY_PATHS, ids=str)
def test_reference_loading_names_every_reference_with_a_condition(path: Path) -> None:
    section = _loading_section(path)

    assert PATH_FORM in section, f"{path} Reference Loading lacks the plugin-root path form"
    for name, (condition, _) in REFERENCES.items():
        assert name in section, f"{path} Reference Loading does not list {name}"
        assert condition in section, f"{path} has no load condition {condition!r} for {name}"


@pytest.mark.parametrize("path", SECURITY_PATHS, ids=str)
def test_harness_without_a_skill_tree_has_a_fallback_rule(path: Path) -> None:
    assert UNRESOLVED_RULE in _loading_section(path), f"{path} has no unresolved-path rule"


@pytest.mark.parametrize("name", sorted(REFERENCES))
def test_reference_exists_in_the_security_scan_skill(name: str) -> None:
    ref = REFERENCE_DIR / name

    assert ref.is_file(), f"missing reference {ref}"
    assert len(ref.read_text(encoding="utf-8").split()) > 40, f"{name} is a stub"


@pytest.mark.parametrize("path", SECURITY_PATHS, ids=str)
def test_moved_blocks_keep_a_stub_that_names_the_reference(path: Path) -> None:
    text = _text(path)

    for name in (
        "security-cwe-catalog.md",
        "security-impact-analysis.md",
        "security-piv-ci-checks.md",
    ):
        anchor = REFERENCES[name][1]
        assert anchor in text, f"{path} lost {anchor!r}"
        assert name in text[text.index(anchor) :], f"{path} stub near {anchor!r} never names {name}"


def _stub_after(text: str, heading: str) -> str:
    """Return the flattened text from ``heading`` to the next Markdown heading."""
    start = text.index(heading) + len(heading)
    following = re.search(r" #{2,6} ", text[start:])
    return text[start : start + following.start()] if following else text[start:]


@pytest.mark.parametrize("path", SECURITY_PATHS, ids=str)
def test_cwe_stub_keeps_the_high_priority_cwe_numbers(path: Path) -> None:
    """The stub works alone on a harness with no skill tree."""
    stub = _stub_after(_text(path), "#### CWE-699 Categories and High-Priority CWEs")

    for token in (
        "(CWE-22, 23, 36, 73, 77, 78, 89, 91, 94, 95, 99)",
        "(CWE-287, 798, 640, 384, 613)",
        "(CWE-285, 863, 269, 284)",
        "(CWE-306, 862, 426, 502)",
    ):
        assert token in stub, f"{path} CWE stub lost {token}"


@pytest.mark.parametrize("path", SECURITY_PATHS, ids=str)
def test_cwe_stub_keeps_every_agentic_id_with_its_cwe(path: Path) -> None:
    """The BLOCKED trigger names ASI boundary violations, so the ids need definitions inline."""
    stub = _stub_after(_text(path), "#### CWE-699 Categories and High-Priority CWEs")

    for token in (
        "ASI01 Agent Goal Hijack (CWE-94)",
        "ASI02 Tool Misuse (CWE-22)",
        "ASI03 Identity Abuse (CWE-522)",
        "ASI04 Supply Chain (CWE-426)",
        "ASI05 Code Execution (CWE-94)",
        "ASI06 Memory Poisoning (CWE-502)",
        "ASI07 Inter-Agent Communication",
        "ASI08 Cascading Failures (CWE-703)",
        "ASI09 Trust Exploitation (CWE-346)",
        "ASI10 Rogue Agents (CWE-284)",
    ):
        assert token in stub, f"{path} CWE stub lost {token}"


@pytest.mark.parametrize("path", SECURITY_PATHS, ids=str)
def test_impact_analysis_stub_names_every_section_without_the_reference(path: Path) -> None:
    stub = _stub_after(_text(path), "#### Impact Analysis Deliverable")

    assert "If it is unavailable, write a document titled" in stub, path
    for section in (
        "Impacts Identified",
        "Attack Surface Analysis",
        "Required Security Controls",
        "Blast Radius Assessment",
        "Dependency Security",
        "Estimated Effort",
    ):
        assert section in stub, f"{path} impact stub lost {section}"


@pytest.mark.parametrize("path", SECURITY_PATHS, ids=str)
def test_piv_fallback_names_the_three_checks_and_the_ci_environment(path: Path) -> None:
    """With no reference loaded the request still names exact checks, not "the block"."""
    text = _text(path)
    start = text.index("CI Environment Security Testing (request, do not run)")
    section = text[start : text.index("4. **PIV Report Template**", start)]

    assert "run the checks and return their output" in section, path
    assert "`CI=true` and `GITHUB_ACTIONS=true`" in section, path
    for step in (
        "(1) hook-manager configuration validation",
        "(2) staged-diff scan for hardcoded secrets",
        "(3) scan for hardcoded environment-variable assignments",
    ):
        assert step in section, f"{path} PIV fallback lost {step}"
    assert "the block" not in section and "that block" not in section, path


# One or two lines per moved reference that a trim would silently lose.
LOAD_BEARING_LINES = {
    "security-cwe-catalog.md": (
        "- CWE-22: Path Traversal - Improper limitation of pathname to restricted directory",
        "- ASI03/CWE-522: Identity Abuse - Credentials exposed in agent context",
    ),
    "security-impact-analysis.md": (
        "## Blast Radius Assessment",
        "**Worst Case Impact**: [Description of maximum damage if breach occurs]",
    ),
    "security-piv-ci-checks.md": (
        "$env:CI = 'true'",
        "uv run --frozen lefthook validate",
    ),
}


@pytest.mark.parametrize("name", sorted(LOAD_BEARING_LINES))
def test_moved_reference_keeps_its_load_bearing_lines(name: str) -> None:
    text = (REFERENCE_DIR / name).read_text(encoding="utf-8")

    for line in LOAD_BEARING_LINES[name]:
        assert line in text, f"{name} lost {line!r}"


@pytest.mark.parametrize("relative", RETIRED_COPIES)
def test_one_copy_of_the_security_sidecars_remains(relative: str) -> None:
    """The agent-tree copies are retired; the security-scan skill owns the files."""
    assert not (REPO_ROOT / relative).exists(), f"{relative} is a second copy of the sidecars"


def test_negative_control_unrelated_file_has_no_reference_loading() -> None:
    assert LOADING_HEADING not in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
