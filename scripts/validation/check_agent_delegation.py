#!/usr/bin/env python3
"""Gate: an agent's delegation statement must agree with its tool grant.

Claude Code lets a subagent spawn subagents of its own (up to three layers
below the main conversation) unless the ``Agent`` tool is withheld. An agent
that omits the ``tools`` key inherits ``Agent``. A body line saying "you CANNOT
delegate" is therefore only prose until the frontmatter backs it with a grant
that withholds ``Agent``. Before this gate the two could disagree silently:
seventeen agents said they could not delegate, and fifteen of those inherited
the tool that lets them (issue #5184, ADR-098 Consequences/Negative).

The contract, owned by ``templates/rules/claude-agents.md`` (MUST 9):

- ``DELEGATORS`` names the agents that may delegate. Every other agent is a
  worker.
- The tool grant is the source of truth. A worker's grant withholds ``Agent``:
  either an explicit ``tools`` list without ``Agent``/``Task``, or
  ``disallowedTools: Agent`` when ``tools`` is omitted.
- A worker's body may stay silent about delegation, because the grant answers.
  When a worker does say it cannot delegate, the grant must back the sentence.
- A delegator states no such denial, and its grant includes ``Agent``.
- A delegator declares a bounded-delegation contract under
  ``metadata.delegation`` (budget, responsibility, report schema, acceptance
  owner, retry limit, stop condition, escalation owner), validated by
  ``delegation_contract.py``. A worker declares none: a contract on a worker is
  unauthorized delegation.

Two spellings of the statement exist in the agent bodies: ``**As a subagent,
you CANNOT delegate**`` and ``You cannot delegate.`` The check matches the
phrase ``you cannot delegate`` case-insensitively on purpose, so either
spelling counts. Fenced code blocks are ignored: an example is not a statement.

The scan reads ``src/claude/agents/``, the rendered plugin source. Templates
under ``templates/agents/`` compose their frontmatter from partials, so the
rendered file is the one place the final grant and the final prose sit
together. ``Generated Artifact Staleness`` keeps the render honest.

CLI::

    uv run python scripts/validation/check_agent_delegation.py
    uv run python scripts/validation/check_agent_delegation.py <repo-root>

Exit codes (ADR-035):
    0 - Success (every agent's statement agrees with its grant)
    1 - Logic error (one or more agents disagree, or the registry is stale)
    2 - Config error (invalid repository root, or the tree is missing)
"""

from __future__ import annotations

import re
import sys
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

import delegation_contract as contract_rules
import yaml

AGENT_TREE = Path("src/claude/agents")

# Agents that route work to other agents. Adding a name here is a topology
# decision: update the rule in templates/rules/claude-agents.md in the same PR.
DELEGATORS = frozenset({"orchestrator", "pr-comment-responder"})

_DELEGATION_TOOL = re.compile(r"^(Agent|Task)(\(.*\))?$")
_DENIAL = re.compile(r"\byou\s+cannot\s+delegate\b", re.IGNORECASE)
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


@dataclass(frozen=True)
class AgentFacts:
    """What one agent file says about delegation, in prose and in its grant."""

    states_denial: bool
    grants_agent: bool
    contract: object = None
    prose_budgets: tuple[int, ...] = ()


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    """Return ``(frontmatter, body)`` or None when no frontmatter block exists."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])
    return None


def _strip_fences(body: str) -> str:
    """Drop fenced code blocks so an example never counts as a statement."""
    kept: list[str] = []
    opener = ""
    for line in body.splitlines():
        match = _FENCE.match(line)
        if opener:
            if match and match.group(1)[0] == opener[0] and len(match.group(1)) >= len(opener):
                opener = ""
            continue
        if match:
            opener = match.group(1)
            continue
        kept.append(line)
    return "\n".join(kept)


def _tool_names(value: object) -> list[str]:
    """Normalize a ``tools``/``disallowedTools`` value to a list of names."""
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value]
    return []


def _has_delegation_tool(value: object) -> bool:
    return any(_DELEGATION_TOOL.match(name) for name in _tool_names(value))


def grants_agent_tool(frontmatter: dict[str, object]) -> bool:
    """Return True when the frontmatter leaves the ``Agent`` tool available.

    ``disallowedTools`` is applied first, then ``tools`` resolves against what
    remains. An omitted (or empty-valued) ``tools`` key inherits everything not
    denied, which includes ``Agent``.
    """
    if _has_delegation_tool(frontmatter.get("disallowedTools")):
        return False
    tools = frontmatter.get("tools")
    if tools is None:
        return True
    return _has_delegation_tool(tools)


def _declared_contract(frontmatter: dict[str, object]) -> object:
    """Return ``metadata.delegation``: None when absent, ``{}`` when declared empty."""
    metadata = frontmatter.get("metadata")
    if not isinstance(metadata, dict) or contract_rules.CONTRACT_KEY not in metadata:
        return None
    declared = metadata[contract_rules.CONTRACT_KEY]
    return {} if declared is None else declared


def read_agent_facts(path: Path) -> AgentFacts:
    """Parse one agent file. Raises ``ValueError`` when it cannot be read as an agent."""
    parts = _split_frontmatter(path.read_text(encoding="utf-8"))
    if parts is None:
        raise ValueError("no YAML frontmatter block")
    try:
        loaded = yaml.safe_load(parts[0])
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("frontmatter is not a mapping")
    prose = _strip_fences(parts[1])
    return AgentFacts(
        states_denial=bool(_DENIAL.search(prose)),
        grants_agent=grants_agent_tool(loaded),
        contract=_declared_contract(loaded),
        prose_budgets=contract_rules.prose_budgets(prose),
    )


def check_agent(name: str, facts: AgentFacts, agents: Collection[str] = ()) -> list[str]:
    """Return the findings for one agent, empty when prose, grant, and contract agree.

    ``agents`` holds the agent names a contract owner may reference.
    """
    if name in DELEGATORS:
        return _check_delegator(facts, agents)
    return _check_worker(facts)


def _check_delegator(facts: AgentFacts, agents: Collection[str]) -> list[str]:
    findings: list[str] = []
    if facts.states_denial:
        findings.append(
            "registered delegator, but its body says it cannot delegate "
            "(remove the statement, or drop the agent from DELEGATORS)"
        )
    if not facts.grants_agent:
        findings.append(
            "registered delegator, but its grant withholds Agent "
            "(add Agent to an explicit tools list, or remove the disallowedTools entry)"
        )
    findings.extend(contract_rules.check_contract(facts.contract, agents, facts.prose_budgets))
    return findings


def _check_worker(facts: AgentFacts) -> list[str]:
    findings: list[str] = []
    if facts.contract is not None:
        findings.append(
            "worker declares a bounded-delegation contract, which only a registered "
            "delegator may (remove metadata.delegation, or add the agent to DELEGATORS)"
        )
    findings.extend(_check_worker_grant(facts))
    return findings


def _check_worker_grant(facts: AgentFacts) -> list[str]:
    if not facts.grants_agent:
        return []
    fix = "add 'disallowedTools: Agent', or list tools without Agent/Task"
    if facts.states_denial:
        return [f"body says it cannot delegate, but its grant leaves Agent available ({fix})"]
    return [f"worker's grant leaves Agent available ({fix})"]


def find_delegation_findings(repo_root: Path) -> list[tuple[str, str]]:
    """Return ``(agent, finding)`` pairs across the tree.

    Raises ``FileNotFoundError`` when the tree is absent or empty: a silently
    empty scan is a passing scan that proves nothing.
    """
    tree = repo_root / AGENT_TREE
    if not tree.is_dir():
        raise FileNotFoundError(f"agent tree not found: {tree}")
    files = sorted(tree.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"agent tree yields no Markdown files: {tree}")

    findings: list[tuple[str, str]] = []
    seen = {path.stem for path in files}
    for path in files:
        try:
            facts = read_agent_facts(path)
        except ValueError as exc:
            findings.append((path.stem, f"cannot read delegation facts: {exc}"))
            continue
        findings.extend((path.stem, text) for text in check_agent(path.stem, facts, seen))
    findings.extend(
        (name, "listed in DELEGATORS but no such agent file exists")
        for name in sorted(DELEGATORS - seen)
    )
    return findings


def validate_agent_delegation(repo_root: Path) -> bool:
    """Return True when every agent's delegation statement agrees with its grant.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr.py``.
    """
    try:
        findings = find_delegation_findings(repo_root)
    except FileNotFoundError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return False

    if not findings:
        return True

    print(
        f"[FAIL] {len(findings)} delegation finding(s) under {AGENT_TREE.as_posix()}/. "
        "Claude Code lets a subagent spawn subagents unless Agent is withheld, so "
        "a statement with no matching grant is prose nothing enforces:",
        file=sys.stderr,
    )
    for name, text in findings:
        print(f"  {name}: {text}", file=sys.stderr)
    print(
        "\nFix the template under templates/agents/, then run "
        "'uv run python build/scripts/build_all.py'. Contract: MUST 9 in "
        "templates/rules/claude-agents.md. Refs issue #5184.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    if not (repo_root / AGENT_TREE).is_dir():
        print(f"[FAIL] Missing agent tree: {repo_root / AGENT_TREE}", file=sys.stderr)
        return 2
    return 0 if validate_agent_delegation(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
