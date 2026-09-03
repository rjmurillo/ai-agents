"""The transport preflight must stay wired ahead of the first GitHub call.

The preflight script has its own unit tests, but they all still pass if the
command stops calling it, or calls it after triage. Prose is not a gate, so
these tests pin the wiring itself (Copilot review on PR #5509).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOFIX = REPO_ROOT / ".claude" / "commands" / "pr-autofix.md"
REVIEW = REPO_ROOT / ".claude" / "commands" / "pr-review.md"
CONFIG = REPO_ROOT / ".claude" / "commands" / "pr-review-config.yaml"
PROMPT = REPO_ROOT / ".github" / "prompts" / "pr-review.prompt.md"
COPILOT_AUTOFIX = REPO_ROOT / "src" / "copilot-cli" / "skills" / "pr-autofix" / "SKILL.md"
COPILOT_REVIEW = REPO_ROOT / "src" / "copilot-cli" / "skills" / "pr-review" / "SKILL.md"


class TestAutofixPhaseZero:
    def test_phase_0_exists_and_is_blocking(self):
        body = AUTOFIX.read_text(encoding="utf-8")
        assert "Phase 0: Transport preflight (BLOCKING, runs once)" in body

    def test_phase_0_precedes_phase_1(self):
        """Ordering is the whole point: after triage is too late."""
        body = AUTOFIX.read_text(encoding="utf-8")
        assert body.index("### Phase 0") < body.index("### Phase 1")

    def test_phase_0_invokes_the_preflight_script(self):
        body = AUTOFIX.read_text(encoding="utf-8")
        assert "check_github_transport.py" in body

    def test_the_generated_skill_carries_the_same_gate(self):
        body = COPILOT_AUTOFIX.read_text(encoding="utf-8")
        assert "Phase 0: Transport preflight (BLOCKING, runs once)" in body
        assert body.index("### Phase 0") < body.index("### Phase 1")


class TestReviewPreflightWiring:
    def test_config_declares_a_blocking_preflight(self):
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        preflight = config["transport_preflight"]
        assert preflight["blocking"] is True
        assert preflight["command_key"] == "check_transport"

    @pytest.mark.parametrize("harness", ["claude_code", "copilot"])
    def test_command_key_resolves_in_every_harness_map(self, harness):
        """A key that resolves in one map and not the other cannot dispatch."""
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        key = config["transport_preflight"]["command_key"]
        assert key in config["scripts"][harness], (
            f"{key} missing from scripts.{harness}; Step 0 cannot dispatch there"
        )

    def test_the_preflight_command_is_plugin_root_anchored(self):
        """A bare .claude path does not exist in a standalone install."""
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        for harness in ("claude_code", "copilot"):
            command = config["scripts"][harness]["check_transport"]
            assert "PLUGIN_ROOT" in command, f"{harness} command is not anchored"

    def test_verdicts_cover_both_transport_outcomes(self):
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        verdicts = {v["transport"] for v in config["transport_preflight"]["verdicts"]}
        assert verdicts == {"gh", "gh_unusable"}

    @pytest.mark.parametrize("path", [REVIEW, PROMPT, COPILOT_REVIEW])
    def test_every_consumer_runs_the_preflight_before_step_1(self, path):
        body = path.read_text(encoding="utf-8")
        assert "transport_preflight" in body, f"{path.name} never runs the preflight"
        assert body.index("transport_preflight") < body.index(
            "Step 1: Parse and Validate PRs"
        ), f"{path.name} reaches Step 1 before deciding transport"


class TestMcpNamespaceIsGranted:
    """MCP mode is inert if the command cannot call the operations it names."""

    @pytest.mark.parametrize("path", [AUTOFIX, REVIEW])
    def test_commands_grant_the_mcp_namespace(self, path):
        body = path.read_text(encoding="utf-8")
        allowed = next(
            line for line in body.splitlines() if line.startswith("allowed-tools:")
        )
        assert "mcp__github__*" in allowed, f"{path.name} cannot call MCP operations"

    @pytest.mark.parametrize("path", [AUTOFIX, REVIEW])
    def test_allowed_tools_carries_no_unscoped_wildcard(self, path):
        """The slash-command validator rejects any wildcard that is not scoped.

        A Copilot-spelled `github/*` here is both invalid to that gate and
        meaningless to Claude. The Copilot surface takes its grant through the
        prompt's own `tools` list instead.
        """
        body = path.read_text(encoding="utf-8")
        allowed = next(
            line for line in body.splitlines() if line.startswith("allowed-tools:")
        ).split(":", 1)[1]
        for tool in (t.strip() for t in allowed.split(",")):
            if "*" in tool:
                assert tool.startswith("mcp__") or tool.startswith("Bash("), (
                    f"{path.name} has an unscoped wildcard: {tool}"
                )

    def test_the_copilot_prompt_grants_its_own_namespace(self):
        config = yaml.safe_load(PROMPT.read_text(encoding="utf-8").split("---")[1])
        assert "github/*" in config["tools"]
