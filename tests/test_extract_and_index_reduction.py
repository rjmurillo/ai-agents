"""Reduction tests for the context extractor."""

import sys
from pathlib import Path
from textwrap import dedent

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(
    0,
    str(
        Path(__file__).parent.parent
        / ".claude"
        / "skills"
        / "context-optimizer"
        / "scripts"
    ),
)

from extract_and_index import extract_and_index


@pytest.fixture(autouse=True)
def stub_token_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid network dependency from tiktoken in in-process tests."""
    monkeypatch.setattr("extract_and_index.count_tokens", lambda text: len(text.split()))


class TestReductionTargets:
    """Verify 60-80% reduction on realistic documents."""

    LARGE_DOC = dedent("""\
        # Agent System Documentation

        This document describes the complete agent orchestration system.
        The system provides structured task coordination, memory management,
        and quality assurance for AI-powered development workflows.

        ## Agent Catalog

        The following agents are available for task delegation:

        | Agent | Purpose | Model | Priority |
        |-------|---------|-------|----------|
        | orchestrator | Task coordination and routing | opus | P0 |
        | analyst | Research and investigation | sonnet | P1 |
        | architect | Design governance and ADRs | sonnet | P1 |
        | implementer | Production code and tests | sonnet | P1 |
        | qa | Test strategy and verification | sonnet | P1 |
        | security | Threat modeling and scanning | sonnet | P1 |
        | devops | CI/CD pipeline configuration | sonnet | P2 |
        | explainer | Documentation and PRDs | sonnet | P2 |

        ## Workflow Patterns

        Standard feature development follows this sequence:

        1. orchestrator receives the task and classifies complexity
        2. analyst investigates requirements and surfaces unknowns
        3. architect designs the solution with ADR governance
        4. implementer writes production code with tests
        5. qa validates coverage against acceptance criteria
        6. security scans for vulnerabilities

        For quick fixes, use the abbreviated workflow:
        1. implementer writes the fix
        2. qa validates the change

        ## Session Protocol

        Every session must follow the protocol defined in SESSION-PROTOCOL.md.
        The protocol enforces session logging, memory updates, and validation.

        ### Session Start Requirements

        Before any work begins, the agent must:
        - Initialize Serena with the two-call sequence
        - Read HANDOFF.md for project context
        - Create a session log file
        - Search relevant memories

        ### Session End Requirements

        Before claiming completion, the agent must:
        - Complete all MUST items in the session log
        - Update Serena memory with cross-session context
        - Run markdownlint on changed markdown files
        - Commit all changes including the agents directory
        - Run the session validation script

        ## Memory Architecture

        The system uses a four-tier memory architecture:

        | Tier | Storage | Scope | TTL |
        |------|---------|-------|-----|
        | T1 Semantic | Vector store | Cross-session | Permanent |
        | T2 Structural | Serena memories | Project-level | Session |
        | T3 Ephemeral | Context window | Current session | Conversation |
        | T4 External | Documentation files | Repository | Git history |

        Memory retrieval follows a cost-escalation pattern:
        start with the cheapest option and escalate only when needed.

        ## Coding Standards

        All code must follow these standards:

        - Commit format: type(scope): description
        - AI attribution required in Co-Authored-By trailer
        - Exit codes follow ADR-035 standardization
        - GitHub Actions pinned to SHA with version comment
        - 100% test coverage for security paths
        - 80% test coverage for business logic
        - 60% test coverage for documentation tooling

        ## Configuration Reference

        ```yaml
        agents:
          orchestrator:
            model: opus
            max_turns: 50
            timeout: 300
          implementer:
            model: sonnet
            max_turns: 30
            timeout: 180
        ```

        Environment variables:
        - GITHUB_TOKEN: Authentication for GitHub API
        - SERENA_PROJECT: Active project name
        - CLAUDE_MODEL: Override default model selection
    """)

    def test_large_doc_reduction(self, tmp_path):
        detail_dir = tmp_path / "details"
        result = extract_and_index(self.LARGE_DOC, detail_dir, ".details", repo_root=tmp_path)
        assert result.metrics.reduction_percent >= 60, (
            f"Expected >= 60% reduction, got {result.metrics.reduction_percent}%"
        )

    def test_all_sections_extracted(self, tmp_path):
        detail_dir = tmp_path / "details"
        result = extract_and_index(self.LARGE_DOC, detail_dir, ".details", repo_root=tmp_path)
        assert result.metrics.sections_extracted >= 6
