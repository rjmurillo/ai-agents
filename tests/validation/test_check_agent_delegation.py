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

The bounded-delegation contract (issue #5184, second half) adds:

- positive: a delegator with a full ``metadata.delegation`` contract passes, at
  the budget and retry ceilings and at their minimums, with ``user`` or an agent
  as owner, and with prose that restates the declared budget.
- negative: a delegator without a contract, with a missing or unknown field, a
  non-mapping contract, an owner that is no agent, or a body cap that disagrees
  with the budget fails. A worker that declares a contract fails, granted or not.
- edge: over-budget fan-out, a zero or boolean budget, a retry above the bound,
  and a malformed report schema (not a list, empty, duplicate, bad name, missing
  required field) fail. A fenced prose cap is not a statement.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_agent_delegation as gate

_STATEMENT = "**As a subagent, you CANNOT delegate**. Return results to orchestrator."


def _agent(frontmatter_extra: str = "", body: str = _STATEMENT) -> str:
    head = f"---\nname: sample\ndescription: A sample agent.\n{frontmatter_extra}---\n"
    return f"{head}\n# Sample\n\n{body}\n"


_VALID_SCHEMA = [
    "artifacts",
    "commands",
    "deltas",
    "residual_risks",
    "confidence",
    "acceptance_status",
    "escalation_status",
]

_VALID_CONTRACT: dict[str, object] = {
    "budget": 15,
    "responsibility": "Routes work to specialists and synthesizes their returns.",
    "report_schema": _VALID_SCHEMA,
    "acceptance_owner": "orchestrator",
    "retry_limit": 1,
    "stop_condition": "Every task item is checked off, or the budget is spent.",
    "escalation_owner": "user",
}


def _with_contract(**overrides: object) -> dict[str, object]:
    return {**_VALID_CONTRACT, **overrides}


def _delegator(
    contract: object = _VALID_CONTRACT,
    extra: str = "",
    body: str = "Routes work.",
) -> str:
    """A registered delegator's file, carrying ``contract`` under metadata.delegation."""
    declared = yaml.safe_dump({"metadata": {"delegation": contract}}, sort_keys=False)
    return _agent(extra + declared, body)


def _tree(tmp_path: Path, agents: dict[str, str], *, with_delegators: bool = True) -> Path:
    tree = tmp_path / "src" / "claude" / "agents"
    tree.mkdir(parents=True)
    files = dict(agents)
    if with_delegators:
        for name in gate.DELEGATORS:
            files.setdefault(name, _delegator())
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
        agents = {"orchestrator": _delegator(extra="tools:\n  - Read\n  - Agent\n")}
        assert _findings(tmp_path, agents) == []

    def test_denial_statement_fails(self, tmp_path: Path) -> None:
        found = _findings(tmp_path, {"orchestrator": _delegator(body=_STATEMENT)})
        assert [name for name, _ in found] == ["orchestrator"]
        assert "says it cannot delegate" in found[0][1]

    def test_withheld_grant_fails(self, tmp_path: Path) -> None:
        agents = {"orchestrator": _delegator(extra="disallowedTools: Agent\n")}
        found = _findings(tmp_path, agents)
        assert [name for name, _ in found] == ["orchestrator"]
        assert "withholds Agent" in found[0][1]

    def test_explicit_list_without_agent_fails(self, tmp_path: Path) -> None:
        agents = {"orchestrator": _delegator(extra="tools: Read, Grep\n")}
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

    def test_real_delegators_declare_a_contract(self) -> None:
        tree = REPO_ROOT / gate.AGENT_TREE
        for name in gate.DELEGATORS:
            facts = gate.read_agent_facts(tree / f"{name}.md")
            assert isinstance(facts.contract, dict), name

    def test_registry_names_real_agents(self) -> None:
        tree = REPO_ROOT / gate.AGENT_TREE
        for name in gate.DELEGATORS:
            assert (tree / f"{name}.md").is_file()


class TestRealTree:
    def test_every_shipped_agent_agrees_with_its_grant(self) -> None:
        assert gate.find_delegation_findings(REPO_ROOT) == []


def _contract_findings(tmp_path: Path, agent: str) -> list[str]:
    found = _findings(tmp_path, {"orchestrator": agent})
    assert {name for name, _ in found} <= {"orchestrator"}
    return [text for _, text in found]


class TestContractPasses:
    def test_full_contract(self, tmp_path: Path) -> None:
        assert _contract_findings(tmp_path, _delegator()) == []

    @pytest.mark.parametrize("budget", [1, 15])
    def test_budget_bounds_are_inclusive(self, tmp_path: Path, budget: int) -> None:
        agent = _delegator(_with_contract(budget=budget))
        assert _contract_findings(tmp_path, agent) == []

    @pytest.mark.parametrize("retries", [0, 1])
    def test_retry_bounds_are_inclusive(self, tmp_path: Path, retries: int) -> None:
        agent = _delegator(_with_contract(retry_limit=retries))
        assert _contract_findings(tmp_path, agent) == []

    @pytest.mark.parametrize("field", ["acceptance_owner", "escalation_owner"])
    @pytest.mark.parametrize("owner", ["user", "pr-comment-responder"])
    def test_owner_is_user_or_an_agent(self, tmp_path: Path, field: str, owner: str) -> None:
        agent = _delegator(_with_contract(**{field: owner}))
        assert _contract_findings(tmp_path, agent) == []

    def test_minimal_report_schema(self, tmp_path: Path) -> None:
        schema = ["artifacts", "acceptance_status", "escalation_status"]
        agent = _delegator(_with_contract(report_schema=schema))
        assert _contract_findings(tmp_path, agent) == []

    def test_prose_cap_matching_the_budget(self, tmp_path: Path) -> None:
        body = "- **Max agent delegations per task**: 15, counted in the task tracker."
        assert _contract_findings(tmp_path, _delegator(body=body)) == []

    def test_fenced_prose_cap_is_not_a_statement(self, tmp_path: Path) -> None:
        body = "Example:\n\n```text\nMax agent delegations per task: 99\n```\n"
        assert _contract_findings(tmp_path, _delegator(body=body)) == []

    def test_worker_without_a_contract_is_unaffected(self, tmp_path: Path) -> None:
        agents = {"worker": _agent("disallowedTools: Agent\n", "Does the work.")}
        assert _findings(tmp_path, agents) == []

    def test_non_mapping_metadata_on_a_worker_is_ignored(self, tmp_path: Path) -> None:
        agents = {"worker": _agent("disallowedTools: Agent\nmetadata: plain\n")}
        assert _findings(tmp_path, agents) == []


class TestContractFails:
    def test_missing_contract(self, tmp_path: Path) -> None:
        found = _contract_findings(tmp_path, _agent(body="Routes work."))
        assert len(found) == 1
        assert "declares no bounded-delegation contract" in found[0]

    def test_null_contract_reports_every_field(self, tmp_path: Path) -> None:
        found = _contract_findings(tmp_path, _delegator(None))
        assert len(found) == len(_VALID_CONTRACT)
        assert all("is missing field" in text for text in found)

    @pytest.mark.parametrize("field", sorted(_VALID_CONTRACT))
    def test_each_missing_field(self, tmp_path: Path, field: str) -> None:
        contract = {key: value for key, value in _VALID_CONTRACT.items() if key != field}
        found = _contract_findings(tmp_path, _delegator(contract))
        assert found == [f"contract is missing field '{field}'"]

    def test_unknown_field(self, tmp_path: Path) -> None:
        found = _contract_findings(tmp_path, _delegator(_with_contract(retry_limt=1)))
        assert found == ["contract has unknown field 'retry_limt'"]

    @pytest.mark.parametrize("contract", ["bounded", ["budget"], 7])
    def test_contract_must_be_a_mapping(self, tmp_path: Path, contract: object) -> None:
        found = _contract_findings(tmp_path, _delegator(contract))
        assert len(found) == 1
        assert "must be a mapping" in found[0]

    def test_grant_withheld_while_contract_is_declared(self, tmp_path: Path) -> None:
        agent = _delegator(extra="tools: Read, Grep\n")
        found = _contract_findings(tmp_path, agent)
        assert len(found) == 1
        assert "withholds Agent" in found[0]

    @pytest.mark.parametrize("owner", ["ghost", "", "   ", 3, None])
    @pytest.mark.parametrize("field", ["acceptance_owner", "escalation_owner"])
    def test_owner_must_be_user_or_a_real_agent(
        self, tmp_path: Path, field: str, owner: object
    ) -> None:
        found = _contract_findings(tmp_path, _delegator(_with_contract(**{field: owner})))
        assert len(found) == 1
        assert f"'{field}'" in found[0]

    @pytest.mark.parametrize("field", ["responsibility", "stop_condition"])
    @pytest.mark.parametrize("value", ["", "  ", 4, None, ["halt"]])
    def test_text_fields_must_be_non_empty_strings(
        self, tmp_path: Path, field: str, value: object
    ) -> None:
        found = _contract_findings(tmp_path, _delegator(_with_contract(**{field: value})))
        assert found == [f"contract field '{field}' must be a non-empty string"]

    def test_prose_cap_disagreeing_with_the_budget(self, tmp_path: Path) -> None:
        body = "- **Max agent delegations per task**: 10, counted in the task tracker."
        found = _contract_findings(tmp_path, _delegator(body=body))
        assert found == ["body states a cap of 10 delegations, but the contract budget is 15"]

    def test_second_conflicting_prose_cap_is_reported(self, tmp_path: Path) -> None:
        body = (
            "- **Max agent delegations per task**: 15, counted in the task tracker.\n"
            "- Max agent delegations per task: 10 for retries.\n"
        )
        found = _contract_findings(tmp_path, _delegator(body=body))
        assert found == ["body states a cap of 10 delegations, but the contract budget is 15"]

    def test_repeated_conflicting_prose_cap_is_reported_once(self, tmp_path: Path) -> None:
        body = "Max agent delegations per task: 10\nMax agent delegations per task: 10\n"
        found = _contract_findings(tmp_path, _delegator(body=body))
        assert found == ["body states a cap of 10 delegations, but the contract budget is 15"]

    def test_repeated_matching_prose_cap_passes(self, tmp_path: Path) -> None:
        body = "Max agent delegations per task: 15\nMax agent delegations per task: 15\n"
        assert _contract_findings(tmp_path, _delegator(body=body)) == []


class TestBoundedFanOutAndRetry:
    @pytest.mark.parametrize("budget", [16, 100, 0, -1])
    def test_budget_outside_the_bound(self, tmp_path: Path, budget: int) -> None:
        found = _contract_findings(tmp_path, _delegator(_with_contract(budget=budget)))
        assert found == [f"contract field 'budget' is {budget}, outside the bound 1 to 15"]

    @pytest.mark.parametrize("budget", [True, "15", 7.5, None, [15]])
    def test_budget_must_be_an_integer(self, tmp_path: Path, budget: object) -> None:
        found = _contract_findings(tmp_path, _delegator(_with_contract(budget=budget)))
        assert len(found) == 1
        assert "'budget' must be an integer" in found[0]

    @pytest.mark.parametrize("retries", [2, 10, -1])
    def test_retry_outside_the_bound(self, tmp_path: Path, retries: int) -> None:
        found = _contract_findings(tmp_path, _delegator(_with_contract(retry_limit=retries)))
        assert found == [f"contract field 'retry_limit' is {retries}, outside the bound 0 to 1"]

    @pytest.mark.parametrize("retries", [False, "1", 0.5, None])
    def test_retry_must_be_an_integer(self, tmp_path: Path, retries: object) -> None:
        found = _contract_findings(tmp_path, _delegator(_with_contract(retry_limit=retries)))
        assert len(found) == 1
        assert "'retry_limit' must be an integer" in found[0]


class TestReportSchema:
    @pytest.mark.parametrize("schema", ["artifacts", None, {"artifacts": 1}, 5])
    def test_schema_must_be_a_list(self, tmp_path: Path, schema: object) -> None:
        found = _contract_findings(tmp_path, _delegator(_with_contract(report_schema=schema)))
        assert found == ["contract field 'report_schema' must be a non-empty list of field names"]

    def test_empty_schema(self, tmp_path: Path) -> None:
        found = _contract_findings(tmp_path, _delegator(_with_contract(report_schema=[])))
        assert "non-empty list" in found[0]

    @pytest.mark.parametrize(
        "name",
        ["Artifacts", "9lives", "two words", "", 4, None, "artifacts\n", "a__b", "a_", "_a"],
    )
    def test_malformed_field_name(self, tmp_path: Path, name: object) -> None:
        schema = [*_VALID_SCHEMA, name]
        found = _contract_findings(tmp_path, _delegator(_with_contract(report_schema=schema)))
        assert len(found) == 1
        assert "malformed names" in found[0]

    def test_duplicate_field_name(self, tmp_path: Path) -> None:
        schema = [*_VALID_SCHEMA, "artifacts"]
        found = _contract_findings(tmp_path, _delegator(_with_contract(report_schema=schema)))
        assert found == ["contract field 'report_schema' repeats a field name"]

    @pytest.mark.parametrize("required", ["artifacts", "acceptance_status", "escalation_status"])
    def test_required_field_missing(self, tmp_path: Path, required: str) -> None:
        schema = [name for name in _VALID_SCHEMA if name != required]
        found = _contract_findings(tmp_path, _delegator(_with_contract(report_schema=schema)))
        assert found == [f"contract field 'report_schema' lacks required field(s): {required}"]


class TestUnauthorizedDelegation:
    def test_worker_with_a_contract_and_no_grant_fails(self, tmp_path: Path) -> None:
        agent = _agent("disallowedTools: Agent\n" + yaml.safe_dump(_metadata()), "Does the work.")
        found = _findings(tmp_path, {"worker": agent})
        assert [name for name, _ in found] == ["worker"]
        assert "only a registered delegator may" in found[0][1]

    def test_worker_with_a_contract_and_a_grant_fails_twice(self, tmp_path: Path) -> None:
        agent = _agent(yaml.safe_dump(_metadata()), "Does the work.")
        found = _findings(tmp_path, {"worker": agent})
        assert [name for name, _ in found] == ["worker", "worker"]
        assert "only a registered delegator may" in found[0][1]
        assert "leaves Agent available" in found[1][1]

    def test_worker_with_a_null_contract_fails(self, tmp_path: Path) -> None:
        agent = _agent("disallowedTools: Agent\nmetadata:\n  delegation:\n", "Does the work.")
        found = _findings(tmp_path, {"worker": agent})
        assert "only a registered delegator may" in found[0][1]


def _metadata() -> dict[str, object]:
    return {"metadata": {"delegation": _VALID_CONTRACT}}


class TestContractEntryPoints:
    def test_dirty_contract_exit_one_and_names_the_field(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _tree(tmp_path, {"orchestrator": _delegator(_with_contract(budget=99))})
        assert gate.main([str(root)]) == 1
        assert "orchestrator: contract field 'budget' is 99" in capsys.readouterr().err

    def test_valid_contract_exit_zero(self, tmp_path: Path) -> None:
        assert gate.main([str(_tree(tmp_path, {}))]) == 0
