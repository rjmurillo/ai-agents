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


# The reads every MCP-mode consumer needs: PR context and threads, issue
# bodies, one check run's output, and CI logs.
_MCP_READS = frozenset(
    {
        "pull_request_read",
        "issue_read",
        "get_check_run",
        "get_job_logs",
    }
)
# pr-review also replies and resolves. pr-autofix does neither: without the
# lease helper it runs read-only, so granting a write there would contradict
# its own Phase 0 rule 3.
_MCP_REVIEW_WRITES = frozenset(
    {
        "add_issue_comment",
        "add_reply_to_pull_request_comment",
        "resolve_review_thread",
        "unresolve_review_thread",
    }
)
# pr-review accepts `all-open` and enumerates the queue in Step 1, which the
# routing table maps to list_pull_requests. pr-autofix must NOT have it: its
# Phase 0 rule 3 forbids sweeping the open queue without a lease, so the grant
# is where that stops being a matter of prose (Copilot review on PR #5509).
_MCP_QUEUE_READ = "list_pull_requests"
# Never granted on either surface. A blanket `github/*` carries all of these,
# which is why ADR-003 names that grant an anti-pattern outright rather than
# only a context cost.
_MCP_FORBIDDEN = frozenset(
    {
        "merge_pull_request",
        "enable_pr_auto_merge",
        "push_files",
        "create_or_update_file",
        "delete_file",
        "update_pull_request",
        "issue_write",
        "create_pull_request",
    }
)


def _granted(path):
    body = path.read_text(encoding="utf-8")
    allowed = next(
        line for line in body.splitlines() if line.startswith("allowed-tools:")
    ).split(":", 1)[1]
    return {t.strip() for t in allowed.split(",")}


class TestMcpGrantsAreEnumerated:
    """MCP mode is inert without a grant, and unsafe with a blanket one.

    `.agents/architecture/ADR-003-agent-tool-selection-criteria.md:318` reads
    "DO NOT: Use blanket `github/*` allocation" and puts the server at roughly
    59 operations. Both commands consume untrusted PR content, so the grant is
    the operations each one actually uses and nothing that mutates a
    repository.
    """

    @pytest.mark.parametrize("path", [AUTOFIX, REVIEW])
    def test_the_reads_mcp_mode_depends_on_are_granted(self, path):
        granted = _granted(path)
        missing = sorted(
            op for op in _MCP_READS if f"mcp__github__{op}" not in granted
        )
        assert not missing, f"{path.name} cannot call MCP operations it names: {missing}"

    def test_pr_review_is_granted_its_reply_and_resolve_operations(self):
        granted = _granted(REVIEW)
        missing = sorted(
            op for op in _MCP_REVIEW_WRITES if f"mcp__github__{op}" not in granted
        )
        assert not missing, f"pr-review cannot answer or resolve a thread: {missing}"

    def test_pr_review_can_enumerate_the_open_queue(self):
        """`all-open` is a documented argument, so Step 1 needs the operation.

        Without it the command parses `all-open`, cannot list anything, and
        stops before the first review in gh_unusable mode.
        """
        assert f"mcp__github__{_MCP_QUEUE_READ}" in _granted(REVIEW)

    def test_pr_autofix_cannot_enumerate_the_open_queue(self):
        """Rule 3 forbids the sweep, so the grant has to forbid it too."""
        assert f"mcp__github__{_MCP_QUEUE_READ}" not in _granted(AUTOFIX)

    def test_pr_autofix_is_granted_no_write_operation(self):
        """Phase 0 rule 3 makes MCP mode read-only, so the grant must be too.

        Prose saying "do not push" is not a permission boundary. If the grant
        carries the write, a single misread of the rule is enough to take it.
        """
        granted = _granted(AUTOFIX)
        writes = sorted(
            op
            for op in _MCP_REVIEW_WRITES | _MCP_FORBIDDEN
            if f"mcp__github__{op}" in granted
        )
        assert not writes, f"pr-autofix is read-only but grants: {writes}"

    @pytest.mark.parametrize("path", [AUTOFIX, REVIEW])
    def test_no_repository_mutation_is_granted(self, path):
        granted = _granted(path)
        forbidden = sorted(
            op for op in _MCP_FORBIDDEN if f"mcp__github__{op}" in granted
        )
        assert not forbidden, f"{path.name} grants a repository mutation: {forbidden}"

    @pytest.mark.parametrize("path", [AUTOFIX, REVIEW])
    def test_no_github_namespace_wildcard_survives(self, path):
        """The control for every assertion above: `mcp__github__*` satisfies them.

        A wildcard contains each read as a substring only if you match loosely,
        but it also carries every forbidden operation while naming none of
        them, so the forbidden checks pass on it too. Asserting its absence
        directly is what makes those checks mean anything.
        """
        assert "mcp__github__*" not in _granted(path)

    @pytest.mark.parametrize("harness", ["claude_code", "copilot"])
    def test_every_command_in_each_harness_map_names_a_file_that_exists(
        self, harness
    ):
        """A map is only selectable if its targets are real.

        The Copilot map named nine PowerShell files that exist in neither this
        repository nor the standalone plugin. Nothing selected that map while
        the workflow hardcoded `scripts.claude_code`, so the breakage was
        dormant rather than absent, and it became live the moment the prose
        started reading the harness map (Copilot review on PR #5509).
        """
        import re

        import yaml

        config = yaml.safe_load(
            (REPO_ROOT / ".claude" / "commands" / "pr-review-config.yaml").read_text(
                encoding="utf-8"
            )
        )
        missing = []
        for key, command in config["scripts"][harness].items():
            for token in re.findall(r"[^\s\"']+\.(?:py|ps1)", command):
                relative = token.split("}/")[-1].strip("\"'")
                relative = relative.removeprefix(".claude/")
                if not (REPO_ROOT / ".claude" / relative).is_file():
                    missing.append(f"{harness}.{key} -> {relative}")

        assert not missing, f"commands name files that do not exist: {missing}"

    def test_pr_review_may_run_the_copilot_launcher(self):
        """The Copilot check_transport entry shells pwsh, so the grant must allow it.

        The generated Copilot skill copies this grant verbatim, so without a
        scoped pwsh entry a restricted invocation is denied before the blocking
        preflight runs, and the workflow fails for a permission reason that
        looks like a transport reason (Copilot review on PR #5509).
        """
        assert "Bash(pwsh:*)" in _granted(REVIEW)

    @pytest.mark.parametrize("path", [AUTOFIX, REVIEW])
    def test_allowed_tools_carries_no_unscoped_wildcard(self, path):
        """The slash-command validator rejects any wildcard that is not scoped.

        A Copilot-spelled `github/*` here is both invalid to that gate and
        meaningless to Claude. The Copilot surface takes its grant through the
        prompt's own `tools` list instead.
        """
        for tool in _granted(path):
            if "*" in tool:
                assert tool.startswith("Bash("), (
                    f"{path.name} has an unscoped wildcard: {tool}"
                )

    def test_the_copilot_prompt_grants_the_same_operations_its_own_way(self):
        """Same set, Copilot's spelling, and no blanket grant there either."""
        config = yaml.safe_load(PROMPT.read_text(encoding="utf-8").split("---")[1])
        tools = set(config["tools"])

        assert "github/*" not in tools
        expected = {
            f"github/{op}"
            for op in _MCP_READS | _MCP_REVIEW_WRITES | {_MCP_QUEUE_READ}
        }
        assert expected <= tools, f"prompt is missing {sorted(expected - tools)}"
        forbidden = sorted(f"github/{op}" for op in _MCP_FORBIDDEN if f"github/{op}" in tools)
        assert not forbidden, f"prompt grants a repository mutation: {forbidden}"
