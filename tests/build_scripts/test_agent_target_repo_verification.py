"""QA and security derive verification commands from the target repository (#6988).

The agents are prompts, so the contract is the prompt text plus the evidence a
consumer repository offers. Consumer roots live in tmp_path, outside the plugin
root, and are never written by the agents.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS = REPO_ROOT / "templates" / "agents"
FIXTURES = REPO_ROOT / "tests" / "build_scripts" / "fixtures" / "agent_templates_b1" / "expected"

QA_SURFACES = [
    AGENTS / "qa.shared.md",
    AGENTS / "qa.claude.md.tmpl",
    AGENTS / "partials" / "qa-insufficient-test-evidence.mustache",
    FIXTURES / "claude" / "qa.md",
    FIXTURES / "copilot_source" / "qa.md",
    REPO_ROOT / "src" / "claude" / "agents" / "qa.md",
    REPO_ROOT / "src" / "copilot-cli" / "agents" / "qa.agent.md",
    REPO_ROOT / "src" / "vs-code-agents" / "qa.agent.md",
    REPO_ROOT / "src" / "cursor" / "agents" / "qa.md",
]
SECURITY_SURFACES = [
    AGENTS / "security.shared.md",
    AGENTS / "partials" / "security-mandatory-routing-for-security-relevant.mustache",
    FIXTURES / "claude" / "security.md",
    FIXTURES / "copilot_source" / "security.md",
    REPO_ROOT / "src" / "claude" / "agents" / "security.md",
    REPO_ROOT / "src" / "copilot-cli" / "agents" / "security.agent.md",
    REPO_ROOT / "src" / "vs-code-agents" / "security.agent.md",
]
ALL = QA_SURFACES + SECURITY_SURFACES

# Commands that belong to one repository, not to every consumer.
FOREIGN_COMMANDS = (
    "Qwiq.sln",
    'dotnet test --filter "Category=Security"',
    "dotnet reportgenerator",
)

# Sources the prompt tells the agent to read, in order, and the unresolved result.
SOURCE_MARKERS = (
    "documented command",
    "manifest or task runner",
    "CI configuration",
    "existing local validation skill",
    "`autoplan`",
)
UNRESOLVED_MARKER = "UNRESOLVED EVIDENCE:"
NEVER_MARKER = "never invent"


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT))


def _flat(p: Path) -> str:
    return re.sub(r"\s+", " ", p.read_text(encoding="utf-8"))


def _missing(path: Path, markers: tuple[str, ...]) -> list[str]:
    text = _flat(path).lower()
    return [m for m in markers if m.lower() not in text]


@pytest.fixture
def python_consumer(tmp_path: Path) -> Path:
    root = tmp_path / "py-consumer"
    root.mkdir()
    (root / "README.md").write_text("Run tests: `uv run pytest -q`\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    return root


@pytest.fixture
def dotnet_consumer(tmp_path: Path) -> Path:
    root = tmp_path / "dotnet-consumer"
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "Contoso.sln").write_text("", encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "run: dotnet test Contoso.sln --filter Category=Unit\n", encoding="utf-8"
    )
    return root


@pytest.fixture
def bare_consumer(tmp_path: Path) -> Path:
    root = tmp_path / "bare-consumer"
    root.mkdir()
    return root


def _consumer_evidence(root: Path) -> list[Path]:
    names = ("README.md", "pyproject.toml", "package.json", "Makefile", "AGENTS.md", "CLAUDE.md")
    found = [root / n for n in names if (root / n).is_file()]
    found += list(root.glob("*.sln")) + list(root.glob(".github/workflows/*.yml"))
    return found


def test_consumer_roots_are_outside_plugin_root(
    python_consumer: Path, dotnet_consumer: Path, bare_consumer: Path
) -> None:
    for root in (python_consumer, dotnet_consumer, bare_consumer):
        assert REPO_ROOT not in root.resolve().parents


@pytest.mark.parametrize("path", ALL, ids=_rel)
def test_no_surface_hardcodes_another_repositorys_commands(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    present = [c for c in FOREIGN_COMMANDS if c in text]
    assert not present, f"{_rel(path)} hardcodes {present}"


@pytest.mark.parametrize("path", QA_SURFACES[:1] + QA_SURFACES[3:], ids=_rel)
def test_qa_names_sources_and_unresolved_result(path: Path) -> None:
    missing = _missing(path, (*SOURCE_MARKERS, UNRESOLVED_MARKER, NEVER_MARKER))
    assert not missing, f"{_rel(path)} missing {missing}"


def test_claude_qa_test_commands_defers_to_resolved_commands() -> None:
    text = _flat(AGENTS / "qa.claude.md.tmpl")
    assert "Use the commands resolved in the Validation Protocol" in text
    assert "UNRESOLVED EVIDENCE:" in text


@pytest.mark.parametrize("path", SECURITY_SURFACES, ids=_rel)
def test_security_requests_repo_command_and_stays_request_only(path: Path) -> None:
    missing = _missing(path, (*SOURCE_MARKERS, UNRESOLVED_MARKER, NEVER_MARKER))
    assert not missing, f"{_rel(path)} missing {missing}"
    text = _flat(path)
    assert "You cannot run them." in text, f"{_rel(path)} lost the request-only contract"
    assert "Ask the caller to run it" in text
    assert "Never invent a command, skip an item silently, or report it as passed" in text
    assert "a found hook or secrets command never satisfies the security test" in text
    assert "<security test|hook|secrets>" in text


def test_security_tool_grant_gained_no_shell() -> None:
    """The fix is prose only: the parsed Claude security tool list stays shell-free."""
    text = (REPO_ROOT / "src" / "claude" / "agents" / "security.md").read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---", 2)[1])
    tools = frontmatter["tools"]
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",")]
    assert tools, "security agent lost its tools list"
    assert "Bash" not in tools, f"security agent gained a shell: {tools}"


@pytest.mark.parametrize(
    ("agent", "listed"),
    [("qa", QA_SURFACES), ("security", SECURITY_SURFACES)],
)
def test_every_rendered_agent_copy_is_pinned(agent: str, listed: list[Path]) -> None:
    """Converse of the surface lists: a new platform copy cannot dodge the checks."""
    src = REPO_ROOT / "src"
    on_disk = {
        p.resolve()
        for pattern in (f"*/agents/{agent}.md", f"*/agents/{agent}.agent.md")
        for p in src.glob(pattern)
    }
    unpinned = sorted(_rel(p) for p in on_disk - {p.resolve() for p in listed})
    assert not unpinned, f"{agent} copies missing from the surface list: {unpinned}"


def test_python_consumer_offers_documented_command(python_consumer: Path) -> None:
    evidence = _consumer_evidence(python_consumer)
    assert any("uv run pytest" in p.read_text(encoding="utf-8") for p in evidence)
    assert not list(python_consumer.glob("*.sln"))


def test_dotnet_consumer_offers_its_own_solution_and_category(dotnet_consumer: Path) -> None:
    ci = (dotnet_consumer / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Contoso.sln" in ci and "Category=Unit" in ci
    for path in QA_SURFACES + SECURITY_SURFACES:
        assert "Contoso.sln" not in path.read_text(encoding="utf-8")


def test_bare_consumer_has_no_evidence_so_prompt_requires_unresolved(bare_consumer: Path) -> None:
    """Negative control: no source exists, so the only honest result is unresolved."""
    assert _consumer_evidence(bare_consumer) == []
    for path in (AGENTS / "qa.shared.md", FIXTURES / "claude" / "security.md"):
        assert UNRESOLVED_MARKER in path.read_text(encoding="utf-8")
