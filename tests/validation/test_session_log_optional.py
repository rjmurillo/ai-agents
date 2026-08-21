r"""The committed session-log gate is retired; validation stays validate-if-present.

Stage B of retiring the mandatory session-log gate (approved change, Stage A
already landed). Three properties are pinned here:

a. Staging a ``.agents/**`` change no longer *requires* a JSON session log.
   ``check_sessions`` returns 0 and never emits the old mandate string.
b. When a session log IS present, the validation path still shells out to
   ``scripts/validate_session_json.py`` and still fails an invalid log / passes
   a valid one. That capability is the reason the ``session-policy`` pre-commit
   job stays wired (it becomes validate-if-present).
c. The pre-push ``session-json-validation`` job is gone from ``lefthook.yml``,
   while ``extract-session-episodes`` (durable-memory episode extraction) stays.

Canonical contract quoted verbatim (level-1 lookup) from
``scripts/validation/git_hook_policy.py``:

    SESSION_PATH_RE = re.compile(
        r"^\.agents/sessions/\d{4}-\d{2}-\d{2}-session-\d+.*\.json$"
    )

The new ``check_sessions`` no-log branch, quoted verbatim from the same file:

    if not sessions:
        return 0
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import yaml

import scripts.validate_session_json as vsj
from scripts.validation import git_hook_policy as policy
from scripts.validation import pre_pr

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEFTHOOK = PROJECT_ROOT / "lefthook.yml"
SCHEMA_PATH = PROJECT_ROOT / ".agents" / "schemas" / "session-log.schema.json"

# The old mandate the retirement removes. Absence of this string is the
# behavioral pin: a contributor may stage .agents/** with no session log.
_RETIRED_MANDATE = "require a JSON session log"

_SESSION_REL = ".agents/sessions/2026-01-18-session-1.json"

_CANONICAL_CONTRACT_PATHS = (
    ".agents/README.md",
    ".agents/governance/FAILURE-MODES.md",
    ".agents/governance/GOTCHAS.md",
    ".agents/governance/PROJECT-CONSTRAINTS.md",
    ".agents/AGENTS.md",
    ".agents/AGENT-INSTRUCTIONS.md",
    ".claude/agents/critic.md",
    ".claude/agents/implementer.md",
    ".claude/agents/orchestrator.md",
    ".claude/agents/pr-comment-responder.md",
    ".claude/agents/retrospective.md",
    ".claude/rules/universal.md",
    ".claude/commands/build.md",
    ".claude/skills/reflect/references/integration-and-design.md",
    ".claude/skills/research-and-incorporate/references/workflow.md",
    ".claude/skills/ai-agents-change-control/SKILL.md",
    ".claude/skills/ai-agents-docs-of-record/SKILL.md",
    ".claude/skills/memory-gate/SKILL.md",
    ".claude/skills/merge-resolver/SKILL.md",
    ".claude/skills/pr-comment-responder/references/gates.md",
    ".claude/skills/security-scan/references/autonomous-execution-guardrails.md",
    ".github/agents/critic.agent.md",
    ".github/agents/implementer.agent.md",
    ".github/agents/orchestrator.agent.md",
    ".github/agents/pr-comment-responder.agent.md",
    ".github/agents/pr-comment-responder.prompt.md",
    ".github/agents/retrospective.agent.md",
    ".github/copilot-instructions.md",
    "CONTRIBUTING.md",
    "docs/autonomous-pr-monitor.md",
    "docs/search-dont-load.md",
    "docs/skill-reference.md",
    "docs/technical-guardrails.md",
    "src/claude/critic.md",
    "src/claude/implementer.md",
    "src/claude/orchestrator.md",
    "src/claude/pr-comment-responder.md",
    "src/claude/retrospective.md",
    "src/copilot-cli/agents/critic.agent.md",
    "src/copilot-cli/agents/implementer.agent.md",
    "src/copilot-cli/agents/orchestrator.agent.md",
    "src/copilot-cli/agents/pr-comment-responder.agent.md",
    "src/copilot-cli/agents/retrospective.agent.md",
    "src/copilot-cli/skills/build/SKILL.md",
    "src/copilot-cli/skills/reflect/references/integration-and-design.md",
    "src/copilot-cli/skills/research-and-incorporate/references/workflow.md",
    "src/vs-code-agents/critic.agent.md",
    "src/vs-code-agents/implementer.agent.md",
    "src/vs-code-agents/orchestrator.agent.md",
    "src/vs-code-agents/pr-comment-responder.agent.md",
    "src/vs-code-agents/retrospective.agent.md",
    "templates/agents/critic.shared.md",
    "templates/agents/implementer.shared.md",
    "templates/agents/orchestrator.shared.md",
    "templates/agents/pr-comment-responder.shared.md",
    "templates/agents/retrospective.shared.md",
)

_MANDATORY_LOG_PATTERNS = (
    re.compile(r"\bmust\s+(?:create|complete|write)\b.{0,80}\bsession log\b", re.I),
    re.compile(r"\bmandatory\b.{0,40}\bsession log\b", re.I),
    re.compile(r"\bsession log\b.{0,40}\b(?:required|mandatory|blocking)\b", re.I),
    re.compile(r"\bsession log present and complete\b", re.I),
    re.compile(r"\bgate 0:\s*session log creation\b", re.I),
    re.compile(r"\bsession gate\s*\(blocking\)", re.I),
    re.compile(r"\bstarting any new work session\b", re.I),
    re.compile(r"\brun `/session-end` before every commit\b", re.I),
    re.compile(r"\bsession will fail CI validation\b", re.I),
    re.compile(r"\bevery PR starts with malformed session logs\b", re.I),
)

_GENERAL_WORKFLOW_PATHS = (
    ".claude/commands/build.md",
    ".claude/skills/reflect/references/integration-and-design.md",
    ".claude/skills/research-and-incorporate/references/workflow.md",
    "src/copilot-cli/skills/build/SKILL.md",
    "src/copilot-cli/skills/reflect/references/integration-and-design.md",
    "src/copilot-cli/skills/research-and-incorporate/references/workflow.md",
)

_RETIRED_SOLE_SINK_PATTERN = re.compile(
    r"\b(?:capture|document|record|acknowledge)\b.{0,120}\b(?:in|into)\s+(?:the\s+)?session log\b",
    re.I | re.S,
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")


def _stage_file(repo: Path, relative_path: str, content: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", "--", relative_path)


def _valid_session_json() -> str:
    """A schema-valid session log.

    Shape mirrors the ``valid_session_file`` fixture in
    ``tests/test_validate_session_json.py``. ``check_sessions`` runs a first,
    staged add under ``--creation-mode`` (issue #4425), which skips the
    protocol-compliance checks, so the minimal session section suffices to pass.
    """
    return json.dumps(
        {
            "schemaVersion": "1.0",
            "session": {
                "number": 1,
                "date": "2026-01-18",
                "branch": "feat/test",
                "startingCommit": "abcdef1",
                "objective": "Test objective",
            },
            "protocolCompliance": {"sessionStart": {}, "sessionEnd": {}},
            "workLog": [],
            "endingCommit": "a" * 40,
            "nextSteps": [],
        }
    )


def _run_check_sessions_with_real_validator(repo: Path, paths: list[str]) -> tuple[int, bool]:
    """Run ``check_sessions`` and route its validator call to the real validator.

    ``scripts/validate_session_json.py`` resolves session paths against its own
    ``_PROJECT_ROOT`` (the real repo), so a subprocess cannot see a temp-repo
    fixture. This spy replaces only the ``validate_session_json.py`` invocation
    with an in-process ``main()`` call whose ``_PROJECT_ROOT`` points at the temp
    repo; every other ``_run_command`` call (git probes) delegates unchanged.
    The real validation logic and the real schema run, proving the capability is
    preserved. Returns (exit code, whether the validator command was invoked).
    """
    original_run_command = policy._run_command
    invoked = False

    def _spy(command: Any, root: Path, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal invoked
        if not any("validate_session_json.py" in str(part) for part in command):
            return original_run_command(command, root, **kwargs)
        invoked = True
        # command is [python, "scripts/validate_session_json.py", session, mode].
        validator_argv = ["validate_session_json.py", *[str(part) for part in command[2:]]]
        with (
            mock.patch.object(vsj, "_PROJECT_ROOT", repo),
            mock.patch.object(vsj, "SCHEMA_PATH", SCHEMA_PATH),
            mock.patch.object(sys, "argv", validator_argv),
        ):
            return_code = vsj.main()
        return subprocess.CompletedProcess(command, return_code, "", "")

    with mock.patch.object(policy, "_run_command", _spy):
        exit_code = policy.check_sessions(paths, repo)
    return exit_code, invoked


def test_staging_agents_without_a_session_log_is_allowed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(a) A staged ``.agents/**`` change with no session log passes (exit 0)."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _stage_file(repo, ".agents/governance/GOTCHAS.md", "note\n")

    exit_code = policy.check_sessions([".agents/governance/GOTCHAS.md"], repo)

    assert exit_code == 0
    assert _RETIRED_MANDATE not in capsys.readouterr().err


def test_present_valid_session_log_still_passes(tmp_path: Path) -> None:
    """(b) A present, valid session log still runs the validator and returns 0."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _stage_file(repo, _SESSION_REL, _valid_session_json())

    exit_code, invoked = _run_check_sessions_with_real_validator(repo, [_SESSION_REL])

    assert invoked, "the validation path must still call validate_session_json.py"
    assert exit_code == 0


def test_present_invalid_session_log_still_fails(tmp_path: Path) -> None:
    """(b) A present, invalid session log still runs the validator and fails."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _stage_file(repo, _SESSION_REL, "{ not valid json ")

    exit_code, invoked = _run_check_sessions_with_real_validator(repo, [_SESSION_REL])

    assert invoked, "the validation path must still call validate_session_json.py"
    assert exit_code != 0


def _all_job_names(config: dict[str, Any]) -> set[str]:
    """Every job name across every hook, flattening nested groups."""
    names: set[str] = set()

    def _walk(items: list[Any]) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            group = item.get("group")
            if isinstance(group, dict):
                _walk(group.get("jobs", []))
                continue
            name = item.get("name")
            if name is not None:
                names.add(str(name))

    for hook in ("pre-commit", "pre-push", "commit-msg"):
        hook_config = config.get(hook)
        if isinstance(hook_config, dict):
            _walk(hook_config.get("jobs", []))
    return names


def test_lefthook_has_no_session_json_validation_job_but_keeps_episode_extraction() -> None:
    """(c) The pre-push gate is gone; durable-memory extraction is preserved."""
    config = yaml.safe_load(LEFTHOOK.read_text(encoding="utf-8"))
    names = _all_job_names(config)

    assert "session-json-validation" not in names, (
        "the mandatory pre-push session-json-validation gate must be retired"
    )
    assert "extract-session-episodes" in names, (
        "durable-memory episode extraction must be preserved"
    )


@pytest.mark.parametrize("relative_path", _CANONICAL_CONTRACT_PATHS)
def test_canonical_contract_does_not_mandate_session_logs(relative_path: str) -> None:
    """Active canonical guidance cannot restore the retired log prerequisite."""
    text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    for pattern in _MANDATORY_LOG_PATTERNS:
        assert pattern.search(text) is None, (
            f"{relative_path} contains retired mandatory-log wording: "
            f"{pattern.pattern}"
        )


@pytest.mark.parametrize("relative_path", _GENERAL_WORKFLOW_PATHS)
def test_general_workflows_do_not_use_session_logs_as_the_persistence_sink(
    relative_path: str,
) -> None:
    """General workflows persist rationale in durable task artifacts, not logs."""
    text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    assert _RETIRED_SOLE_SINK_PATTERN.search(text) is None, (
        f"{relative_path} still routes durable evidence exclusively to a session log"
    )


def test_pre_pr_session_validation_passes_without_a_branch_log() -> None:
    """The pre-PR session gate passes when the branch changes no JSON log."""
    with (
        mock.patch("checks_tooling._resolve_branch_base_ref", return_value="origin/main"),
        mock.patch("checks_tooling._run_subprocess", return_value=(0, "", "")),
    ):
        assert pre_pr.validate_session_end(PROJECT_ROOT) is True


def test_adr_review_gate_requires_staged_debate_evidence(tmp_path: Path) -> None:
    """ADR governance accepts durable staged evidence, not a working-tree file."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    adr_path = ".agents/architecture/ADR-099-example.md"
    debate_path = ".agents/critique/ADR-099-debate-log.md"
    _stage_file(repo, adr_path, "# ADR-099\n")
    debate = repo / debate_path
    debate.parent.mkdir(parents=True)
    debate.write_text("# ADR Debate Log\n\nADR-099 accepted.\n", encoding="utf-8")

    assert policy.check_adr_review_policy([adr_path], repo) == 1

    _git(repo, "add", "--", debate_path)

    assert policy.check_adr_review_policy([adr_path], repo) == 0


@pytest.mark.parametrize(
    "relative_path",
    (
        ".github/instructions/universal.instructions.md",
        "src/copilot-cli/instructions/universal.instructions.md",
    ),
)
def test_generated_universal_instructions_do_not_mandate_logs(
    relative_path: str,
) -> None:
    """Generated cross-harness instructions never mandate session log creation."""
    text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    assert re.search(r"Session log creation is\s+discontinued", text)
    for pattern in _MANDATORY_LOG_PATTERNS:
        assert pattern.search(text) is None


@pytest.mark.parametrize(
    "relative_path",
    (
        ".agents/SESSION-START-PROMPT.md",
        ".agents/SESSION-END-PROMPT.md",
        ".github/prompts/session-protocol-check.md",
        ".claude/skills/session-log-fixer/scripts/get_validation_errors.py",
        "src/copilot-cli/skills/session-log-fixer/scripts/get_validation_errors.py",
    ),
)
def test_retired_prompt_and_workflow_helpers_remain_absent(relative_path: str) -> None:
    """Deleted workflow surfaces cannot silently return through generation."""
    assert not (PROJECT_ROOT / relative_path).exists()


def test_orphaned_session_command_helper_remains_absent() -> None:
    """Canonical and mirrored hook utilities omit the retired command helper."""
    for relative_path in (
        "scripts/hook_utilities/utilities.py",
        "scripts/hook_utilities/__init__.py",
        ".claude/lib/hook_utilities/utilities.py",
        ".claude/lib/hook_utilities/__init__.py",
        "src/copilot-cli/lib/hook_utilities/utilities.py",
        "src/copilot-cli/lib/hook_utilities/__init__.py",
    ):
        text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "is_session_logged_command" not in text


def test_opt_in_session_logs_retain_validation() -> None:
    """Hand-written opt-in session logs still use the retained validator."""
    assert (PROJECT_ROOT / "scripts" / "validate_session_json.py").is_file()
    assert (
        PROJECT_ROOT / ".agents" / "schemas" / "session-log.schema.json"
    ).is_file()
