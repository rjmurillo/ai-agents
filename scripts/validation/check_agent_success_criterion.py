#!/usr/bin/env python3
"""Gate: every agent declares an explicit success criterion (ADR-065 Decision 2).

ADR-065 says the orchestrator is a router with a retry policy, not a
supervisor. A router can only retry on a signal it can read, so each agent
names that signal in a top-level ``success_criterion`` frontmatter key, the
location ADR-065's schema gives. Before this gate, no agent declared one
(issue #7639). The field is declarative today: no code reads it yet. The
orchestrator prompt reads it, and ADR-065 step 6 (retry code) is its future
code consumer.

The rules for one criterion live in ``success_criterion.py``. This gate adds
the cross-agent rule: two agents may not share a rationale, because a copied
rationale explains neither agent.

The scan reads ``src/claude/agents/``, the rendered plugin source, for the
same reason ``check_agent_delegation.py`` does: templates compose their
frontmatter from partials, so the rendered file is the one place the final
frontmatter sits. ``.claude/agents/`` links into that tree (ADR-119), and
``Generated Artifact Staleness`` keeps the render honest.

The field lives only in the Claude templates (``templates/agents/*.claude.md.tmpl``).
The Copilot and VS Code trees, and the Cursor and Codex trees that keep only
``name`` and ``description``, do not carry it. A criterion nested under
``metadata`` is reported, so the key cannot sit where nothing looks for it.

CLI::

    uv run python scripts/validation/check_agent_success_criterion.py
    uv run python scripts/validation/check_agent_success_criterion.py <repo-root>

Exit codes (ADR-035):
    0 - Success (every agent declares a valid, distinct criterion)
    1 - Logic error (one or more agents miss or break the contract)
    2 - Config error (invalid repository root, or the tree is missing)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_gate_cli
import success_criterion as rules

AGENT_TREE = Path("src/claude/agents")


def read_frontmatter(path: Path) -> dict[str, object]:
    """Return one agent's frontmatter mapping.

    Raises ``ValueError`` when the file cannot be read as an agent.
    """
    text = path.read_text(encoding="utf-8")
    # Strict: a repeated key inside success_criterion would let a valid second
    # value hide an invalid first one.
    return agent_gate_cli.read_agent_text(text, allow_duplicate_keys=False).frontmatter


def read_criterion(path: Path) -> object:
    """Return the top-level ``success_criterion`` for one agent, or None when absent."""
    return read_frontmatter(path).get(rules.CRITERION_KEY)


def _nested_criterion(frontmatter: dict[str, object]) -> bool:
    metadata = frontmatter.get("metadata")
    return isinstance(metadata, dict) and rules.CRITERION_KEY in metadata


def find_criterion_findings(repo_root: Path) -> list[tuple[str, str]]:
    """Return ``(agent, finding)`` pairs across the tree.

    Raises ``FileNotFoundError`` when the tree is absent or empty: a silently
    empty scan is a passing scan that proves nothing.
    """
    files = agent_gate_cli.agent_markdown_files(repo_root, AGENT_TREE)

    findings: list[tuple[str, str]] = []
    rationales: dict[str, str] = {}
    for path in files:
        try:
            frontmatter = read_frontmatter(path)
        except ValueError as exc:
            findings.append((path.stem, f"cannot read success criterion: {exc}"))
            continue
        if _nested_criterion(frontmatter):
            findings.append(
                (path.stem, "success_criterion is nested under metadata; move it to the top level")
            )
        criterion = frontmatter.get(rules.CRITERION_KEY)
        findings.extend((path.stem, text) for text in rules.check_criterion(criterion))
        if isinstance(criterion, dict) and isinstance(criterion.get("rationale"), str):
            rationales[path.stem] = criterion["rationale"]
    for name, others in sorted(rules.duplicate_rationales(rationales).items()):
        findings.append(
            (name, f"'rationale' is copied from {', '.join(others)}; write one for this agent")
        )
    return sorted(findings)


def validate_agent_success_criterion(repo_root: Path) -> bool:
    """Return True when every agent declares a valid, distinct success criterion.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr.py``.
    """
    try:
        findings = find_criterion_findings(repo_root)
    except FileNotFoundError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return False
    if not findings:
        return True
    print(
        f"[FAIL] {len(findings)} success-criterion finding(s) under "
        f"{AGENT_TREE.as_posix()}/. A router can only retry on a signal the agent "
        "declares (ADR-065 Decision 2):",
        file=sys.stderr,
    )
    for name, text in findings:
        print(f"  {name}: {text}", file=sys.stderr)
    print(
        "\nFix the Claude template under templates/agents/, then run "
        "'uv run python build/scripts/build_all.py'. Contract: the Success "
        "Criterion section of templates/rules/claude-agents.md. Refs issue #7639.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    return agent_gate_cli.run_repo_gate(argv, validate_agent_success_criterion, AGENT_TREE)


if __name__ == "__main__":
    raise SystemExit(main())
