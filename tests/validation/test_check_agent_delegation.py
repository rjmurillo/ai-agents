"""Guards for the agent delegation gate (issue #5184).

The gate exists because a body line saying "you CANNOT delegate" is prose until
the frontmatter withholds the ``Agent`` tool. Claude Code lets a subagent spawn
subagents unless ``Agent`` is withheld, and an omitted ``tools`` key inherits it.

Coverage:

- positive: a worker with ``disallowedTools: Agent`` passes with or without a
  statement, as does a worker with an explicit ``tools`` list lacking
  ``Agent``. A registered delegator with an inherited or explicit grant passes.
  Both statement spellings pass. The real repository tree passes.
- negative: a worker that inherits ``Agent``, with or without a statement, a
  worker whose explicit list names ``Agent`` or ``Task``, a delegator that
  states a denial, and a delegator whose grant withholds ``Agent`` each fail.
- edge: a statement inside a code fence is not a statement; ``Agent(type)`` and
  ``Task`` spellings count as the tool; comma-string and list forms parse;
  ``disallowedTools`` wins over ``tools``; an empty ``tools`` key inherits; a
  stale registry entry, unreadable frontmatter, a missing tree, and an empty
  tree fail rather than pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_agent_delegation as gate

_STATEMENT = "**As a subagent, you CANNOT delegate**. Return results to orchestrator."


def _agent(frontmatter_extra: str = "", body: str = _STATEMENT) -> str:
    head = f"---\nname: sample\ndescription: A sample agent.\n{frontmatter_extra}---\n"
    return f"{head}\n# Sample\n\n{body}\n"


def _tree(tmp_path: Path, agents: dict[str, str], *, with_delegators: bool = True) -> Path:
    tree = tmp_path / "src" / "claude" / "agents"
    tree.mkdir(parents=True)
    files = dict(agents)
    if with_delegators:
        for name in gate.DELEGATORS:
            files.setdefault(name, _agent(body="Routes work."))
    for name, text in files.items():
        (tree / f"{name}.md").write_text(text, encoding="utf-8")
    return tmp_path


def _findings(tmp_path: Path, agents: dict[str, str]) -> list[tuple[str, str]]:
    return gate.find_delegation_findings(_tree(tmp_path, agents))


class TestWorkersPass:
    def test_disallowed_agent_with_statement(self, tmp_path: Path) -> None:
        agents = {"worker": _agent("disallowedTools: Agent\n")}
        assert _findings(tmp_path, agents) == []

    def test_disallowed_agent_silent_body(self, tmp_path: Path) -> None:
        agents = {"worker": _agent("disallowedTools: Agent\n", "Does the work.")}
        assert _findings(tmp_path, agents) == []

    def test_explicit_tools_silent_body(self, tmp_path: Path) -> None:
        agents = {"worker": _agent("tools: Read, Grep\n", "Does the work.")}
        assert _findings(tmp_path, agents) == []

    def test_explicit_tools_without_agent(self, tmp_path: Path) -> None:
        agents = {"worker": _agent("tools:\n  - Read\n  - Grep\n")}
        assert _findings(tmp_path, agents) == []

    def test_comma_string_tools_without_agent(self, tmp_path: Path) -> None:
        agents = {"worker": _agent("tools: Read, Grep, Glob\n")}
        assert _findings(tmp_path, agents) == []

    def test_second_spelling_is_accepted(self, tmp_path: Path) -> None:
        body = "You cannot delegate. Return to orchestrator."
        agents = {"worker": _agent("disallowedTools: Agent\n", body)}
        assert _findings(tmp_path, agents) == []

    def test_statement_with_trailing_words_is_accepted(self, tmp_path: Path) -> None:
        body = "**As a subagent, you CANNOT delegate to other agents**. Return a report."
        agents = {"worker": _agent("disallowedTools: Agent\n", body)}
        assert _findings(tmp_path, agents) == []

    def test_disallowed_list_form(self, tmp_path: Path) -> None:
        agents = {"worker": _agent("disallowedTools:\n  - Bash\n  - Agent\n")}
        assert _findings(tmp_path, agents) == []

    def test_disallowed_wins_over_tools(self, tmp_path: Path) -> None:
        agents = {"worker": _agent("tools: Read, Agent\ndisallowedTools: Agent\n")}
        assert _findings(tmp_path, agents) == []


class TestWorkersFail:
    def test_inherited_agent_with_statement(self, tmp_path: Path) -> None:
        found = _findings(tmp_path, {"worker": _agent()})
        assert [name for name, _ in found] == ["worker"]
        assert "says it cannot delegate, but its grant leaves Agent" in found[0][1]

    def test_inherited_agent_without_statement(self, tmp_path: Path) -> None:
        found = _findings(tmp_path, {"worker": _agent(body="Does the work.")})
        assert [name for name, _ in found] == ["worker"]
        assert "worker's grant leaves Agent available" in found[0][1]

    @pytest.mark.parametrize("tool", ["Agent", "Task", "Agent(analyst)", "Task(analyst)"])
    def test_explicit_list_names_delegation_tool(self, tmp_path: Path, tool: str) -> None:
        agents = {"worker": _agent(f"tools:\n  - Read\n  - {tool}\n")}
        found = _findings(tmp_path, agents)
        assert [name for name, _ in found] == ["worker"]
        assert "leaves Agent available" in found[0][1]

    def test_empty_tools_key_inherits(self, tmp_path: Path) -> None:
        found = _findings(tmp_path, {"worker": _agent("tools:\n")})
        assert "leaves Agent available" in found[0][1]

    def test_disallowing_another_tool_does_not_withhold_agent(self, tmp_path: Path) -> None:
        found = _findings(tmp_path, {"worker": _agent("disallowedTools: Bash\n")})
        assert "leaves Agent available" in found[0][1]

    def test_statement_only_inside_a_fence_is_not_a_statement(self, tmp_path: Path) -> None:
        body = "Example:\n\n```text\nYou cannot delegate.\n```\n"
        found = _findings(tmp_path, {"worker": _agent(body=body)})
        assert "worker's grant leaves Agent available" in found[0][1]

    def test_long_fence_is_not_closed_by_a_short_one(self, tmp_path: Path) -> None:
        body = "````text\n```\nYou cannot delegate.\n````\n"
        found = _findings(tmp_path, {"worker": _agent(body=body)})
        assert "worker's grant leaves Agent available" in found[0][1]

    def test_statement_after_a_closed_fence_counts(self, tmp_path: Path) -> None:
        body = "```text\nexample\n```\n\n" + _STATEMENT
        found = _findings(tmp_path, {"worker": _agent(body=body)})
        assert "says it cannot delegate, but its grant leaves Agent" in found[0][1]


class TestDelegators:
    def test_inherited_grant_passes(self, tmp_path: Path) -> None:
        assert _findings(tmp_path, {}) == []

    def test_explicit_grant_passes(self, tmp_path: Path) -> None:
        agents = {"orchestrator": _agent("tools:\n  - Read\n  - Agent\n", "Routes work.")}
        assert _findings(tmp_path, agents) == []

    def test_denial_statement_fails(self, tmp_path: Path) -> None:
        found = _findings(tmp_path, {"orchestrator": _agent()})
        assert [name for name, _ in found] == ["orchestrator"]
        assert "says it cannot delegate" in found[0][1]

    def test_withheld_grant_fails(self, tmp_path: Path) -> None:
        agents = {"orchestrator": _agent("disallowedTools: Agent\n", "Routes work.")}
        found = _findings(tmp_path, agents)
        assert [name for name, _ in found] == ["orchestrator"]
        assert "withholds Agent" in found[0][1]

    def test_explicit_list_without_agent_fails(self, tmp_path: Path) -> None:
        agents = {"orchestrator": _agent("tools: Read, Grep\n", "Routes work.")}
        found = _findings(tmp_path, agents)
        assert "withholds Agent" in found[0][1]

    def test_stale_registry_entry_fails(self, tmp_path: Path) -> None:
        agents = {"worker": _agent("disallowedTools: Agent\n")}
        root = _tree(tmp_path, agents, with_delegators=False)
        found = gate.find_delegation_findings(root)
        assert {name for name, _ in found} == set(gate.DELEGATORS)
        assert all("no such agent file" in text for _, text in found)


class TestMalformedInput:
    def test_missing_frontmatter(self, tmp_path: Path) -> None:
        found = _findings(tmp_path, {"worker": "# No frontmatter\n"})
        assert "no YAML frontmatter block" in found[0][1]

    def test_unterminated_frontmatter(self, tmp_path: Path) -> None:
        found = _findings(tmp_path, {"worker": "---\nname: x\n"})
        assert "no YAML frontmatter block" in found[0][1]

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        found = _findings(tmp_path, {"worker": "---\nname: [unclosed\n---\nbody\n"})
        assert "not valid YAML" in found[0][1]

    def test_frontmatter_not_a_mapping(self, tmp_path: Path) -> None:
        found = _findings(tmp_path, {"worker": "---\n- a\n- b\n---\nbody\n"})
        assert "not a mapping" in found[0][1]

    def test_unexpected_tools_type_is_ignored(self) -> None:
        assert gate.grants_agent_tool({"tools": 7}) is False
        assert gate.grants_agent_tool({"disallowedTools": 7}) is True


class TestTreeErrors:
    def test_missing_tree_is_config_error(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            gate.find_delegation_findings(tmp_path)
        assert gate.main([str(tmp_path)]) == 2

    def test_empty_tree_fails(self, tmp_path: Path) -> None:
        (tmp_path / "src" / "claude" / "agents").mkdir(parents=True)
        with pytest.raises(FileNotFoundError):
            gate.find_delegation_findings(tmp_path)
        assert gate.validate_agent_delegation(tmp_path) is False

    def test_invalid_root_is_config_error(self, tmp_path: Path) -> None:
        assert gate.main([str(tmp_path / "absent")]) == 2


class TestEntryPoints:
    def test_clean_tree_exit_zero(self, tmp_path: Path) -> None:
        root = _tree(tmp_path, {"worker": _agent("disallowedTools: Agent\n")})
        assert gate.main([str(root)]) == 0

    def test_dirty_tree_exit_one_and_names_the_agent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _tree(tmp_path, {"worker": _agent(body="Does the work.")})
        assert gate.main([str(root)]) == 1
        err = capsys.readouterr().err
        assert "worker: worker's grant leaves Agent available" in err
        assert "#5184" in err

    def test_cli_default_root_is_the_repository(self) -> None:
        assert gate.main([]) == 0

    def test_registry_names_real_agents(self) -> None:
        tree = REPO_ROOT / gate.AGENT_TREE
        for name in gate.DELEGATORS:
            assert (tree / f"{name}.md").is_file()


class TestRealTree:
    def test_every_shipped_agent_agrees_with_its_grant(self) -> None:
        assert gate.find_delegation_findings(REPO_ROOT) == []
