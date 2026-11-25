"""Contract for the `/ship` and `/push-pr` split: `/push-pr` is the only PR creator.

`/ship` used to inline Azure DevOps PR creation (`az repos pr create`) and ran
`/validate-pr-description` before `/push-pr`, when no body file existed yet. Both
overlapped with `/push-pr`, which already validates title and body. These tests pin the
split in both rendered copies (Claude and Copilot):

- `/push-pr` owns the ADO branch and the clean-tree contract. It grants no `az`
  entry, so each ADO create prompts the user.
- `/ship` step 3 calls `/push-pr` for both hosts and creates nothing itself.
- `/ship` still discharges the ADO deferred pipeline with `pullRequestId` from `/push-pr`.

Inverse failure modes pinned: any `az` or `Bash(*)` grant on `/push-pr`, an ADO create
with no description check or no `@`-fallback check, and a ship step 4 that no longer
reads the PR id from `/push-pr`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.commands.test_ship_first_pr_ordering import (
    COMMAND_MIRROR_PATH,
    COMMAND_PATH,
    REPO_ROOT,
    numbered_item,
    numbered_items,
    section,
)

PUSH_PR_PATH = REPO_ROOT / ".claude" / "skills" / "push-pr" / "SKILL.md"
PUSH_PR_MIRROR_PATH = REPO_ROOT / "src" / "copilot-cli" / "skills" / "push-pr" / "SKILL.md"
VALIDATOR_GRANT = "Bash(python3:-I */pr/validate_pr_description.py*)"
_ALLOWED_TOOLS_RE = re.compile(r"^allowed-tools: (?P<value>.*)$", re.MULTILINE)
_GRANT_RE = re.compile(r"Bash\((?:[^()]|\([^()]*\))*\)|[A-Za-z]+\([^)]*\)|[A-Za-z]+")


def grants_of(text: str) -> list[str]:
    """Return the entries of the `allowed-tools` frontmatter line."""
    match = _ALLOWED_TOOLS_RE.search(text)
    assert match, "no allowed-tools line in frontmatter"
    return _GRANT_RE.findall(match.group("value"))


@pytest.fixture(params=[COMMAND_PATH, COMMAND_MIRROR_PATH], ids=["claude", "copilot"])
def ship_text(request: pytest.FixtureRequest) -> str:
    return Path(request.param).read_text(encoding="utf-8")


@pytest.fixture(params=[PUSH_PR_PATH, PUSH_PR_MIRROR_PATH], ids=["claude", "copilot"])
def push_pr_text(request: pytest.FixtureRequest) -> str:
    return Path(request.param).read_text(encoding="utf-8")


class TestPushPrOwnsAdoCreation:
    def test_ado_branch_runs_az_repos_pr_create(self, push_pr_text: str) -> None:
        ado = section(push_pr_text, "Azure DevOps PR Creation")
        assert "`host=ado`" in ado
        assert "az repos pr create --output json" in ado
        assert "--description '@<body-file-path-from-step-3>'" in ado, (
            "quote it: PowerShell splats @name"
        )
        assert "--title" in ado

    def test_ado_branch_reports_pull_request_id(self, push_pr_text: str) -> None:
        ado = section(push_pr_text, "Azure DevOps PR Creation")
        output = section(push_pr_text, "Output")
        assert "pullRequestId" in ado
        assert "pullRequestId=<id>" in output
        assert "url=" in output

    def test_ado_failure_stops_with_az_stderr(self, push_pr_text: str) -> None:
        ado = section(push_pr_text, "Azure DevOps PR Creation")
        assert "no PR was created" in ado
        assert "`az` stderr" in ado

    def test_host_detection_matches_ship(self, push_pr_text: str, ship_text: str) -> None:
        """Both skills classify the origin URL with the same case arms and error exit."""
        detection = section(push_pr_text, "Host Detection")
        ship_detection = section(ship_text, "Mode Detection")
        for fragment in (
            "*dev.azure.com*|*visualstudio.com*) host=ado ;;",
            "*) host=github ;;",
            "git remote get-url origin",
            "exit 2",
        ):
            assert fragment in detection
            assert fragment in ship_detection

    def test_ado_steps_push_before_create(self, push_pr_text: str) -> None:
        items = numbered_items(section(push_pr_text, "Process"))
        pushes = [i for i, item in enumerate(items) if item.startswith("6. Push the branch")]
        creates = [i for i, item in enumerate(items) if "Azure DevOps PR Creation" in item]
        assert pushes
        assert creates
        assert min(pushes) < min(creates)

    def test_clean_tree_contract_is_stated_once(self, push_pr_text: str) -> None:
        contract = section(push_pr_text, "Commit Contract")
        assert "MUST NOT create a commit" in contract
        assert "Co-Authored-By" in contract
        assert push_pr_text.count("MUST NOT create a commit") == 1

    def test_ado_validates_description_before_create(self, push_pr_text: str) -> None:
        ado = section(push_pr_text, "Azure DevOps PR Creation")
        check = ado.find("validate_pr_description.py")
        create = ado.find("az repos pr create --output json")
        assert check != -1
        assert check < create
        command = next(
            ln
            for ln in ado.splitlines()
            if "exec python3" in ln and "validate_pr_description.py" in ln
        )
        assert "--fail-on-violation" not in command, "warnings must stay advisory, as on GitHub"
        assert VALIDATOR_GRANT in grants_of(push_pr_text)

    def test_ado_forbids_extra_az_flags(self, push_pr_text: str) -> None:
        ado = section(push_pr_text, "Azure DevOps PR Creation")
        assert "MUST NOT add any other flag" in ado
        for flag in ("--auto-complete", "--bypass-policy", "--org", "--project", "--source-branch"):
            assert f"`{flag}`" in ado

    def test_ado_binds_body_path_and_bans_other_at_arguments(self, push_pr_text: str) -> None:
        ado = section(push_pr_text, "Azure DevOps PR Creation")
        assert "No other argument may" in ado
        assert "passed steps 4 and 5" in " ".join(ado.split())

    def test_ado_detects_silent_at_fallback(self, push_pr_text: str) -> None:
        ado = section(push_pr_text, "Azure DevOps PR Creation")
        assert "`description` field" in ado
        assert "If it starts with `@`" in " ".join(ado.split())
        assert "Do not abandon or edit it without their answer" in ado

    def test_ado_warnings_are_advisory(self, push_pr_text: str) -> None:
        ado = " ".join(section(push_pr_text, "Azure DevOps PR Creation").split())
        assert "are advisory" in ado
        assert "`AB#`" in ado
        assert "a bad title still exits 0" in ado
        assert "prints an `Errors` section" in ado

    def test_ado_requires_manual_dash_check(self, push_pr_text: str) -> None:
        ado = " ".join(section(push_pr_text, "Azure DevOps PR Creation").split())
        assert "has no dash check" in ado
        assert "U+2014" in ado and "U+2013" in ado

    def test_ado_title_cannot_start_with_at(self, push_pr_text: str) -> None:
        ado = " ".join(section(push_pr_text, "Azure DevOps PR Creation").split())
        assert "NOT start with `@`" in ado

    def test_ado_target_branch_aligns_diff_base(self, push_pr_text: str) -> None:
        ado = " ".join(section(push_pr_text, "Azure DevOps PR Creation").split())
        assert "`--base origin/<branch>`" in ado

    def test_ado_windows_uses_fallback_body_file(self, push_pr_text: str) -> None:
        ado = " ".join(section(push_pr_text, "Azure DevOps PR Creation").split())
        assert "`pr-body-windows.md`, the scratch file" in ado
        assert "Skip its step 7 item" in ado

    def test_identity_hardened_forms_unchanged(self, push_pr_text: str) -> None:
        grants = grants_of(push_pr_text)
        assert "Bash(python3:-I */pr/new_pr.py*)" in grants
        assert "Bash(uv run --frozen python -I scripts/validation/pr_description.py*)" in grants


class TestPushPrGrantIsNotBroadened:
    def test_no_az_grant_at_all(self, push_pr_text: str) -> None:
        """A prefix grant would auto-approve `--bypass-policy` and `@<path>` uploads."""
        az = [g for g in grants_of(push_pr_text) if re.search(r"\baz\b", g)]
        assert az == []

    def test_no_remote_url_grant(self, push_pr_text: str) -> None:
        """Its stdout can print origin credentials, so each lookup must prompt."""
        assert not [g for g in grants_of(push_pr_text) if "remote get-url" in g]

    def test_az_detector_sees_a_scoped_az_grant(self) -> None:
        """Negative control: the `az` detector fires on the grant this file bans."""
        grants = grants_of("allowed-tools: Bash(git add:*), Bash(az repos pr create:*)\n")
        assert [g for g in grants if re.search(r"\baz\b", g)] == ["Bash(az repos pr create:*)"]

    def test_no_wildcard_bash_grant(self, push_pr_text: str) -> None:
        grants = grants_of(push_pr_text)
        assert "Bash(*)" not in grants
        assert "Bash" not in grants
        assert "Bash(az:*)" not in grants

    def test_grant_parser_detects_a_broadened_grant(self) -> None:
        """Negative control: the parser sees `Bash(*)` and `az:*` when they are present."""
        text = "allowed-tools: Bash(git add:*), Bash(*), Bash(az:*)\n"
        grants = grants_of(text)
        assert "Bash(*)" in grants
        assert "Bash(az:*)" in grants


class TestShipCreatesNothing:
    def test_step_3_calls_push_pr_for_both_hosts(self, ship_text: str) -> None:
        step = numbered_item(section(ship_text, "Process"), "If no blocking check failed")
        owner = next(ln for ln in step.splitlines() if "`mode=owner`" in ln)
        assert "both hosts" in owner
        assert "/push-pr" in owner
        assert "`host=github`" in owner
        assert "`host=ado`" in owner

    def test_ship_no_longer_validates_pr_description(self, ship_text: str) -> None:
        assert "/validate-pr-description" not in ship_text

    def test_ship_no_longer_creates_a_pr(self, ship_text: str) -> None:
        assert "az repos pr create" not in ship_text

    def test_ship_no_longer_restates_commit_rule(self, ship_text: str) -> None:
        assert "Commit messages MUST follow" not in ship_text
        assert "Co-Authored-By" not in ship_text

    def test_ship_references_clean_tree_contract(self, ship_text: str) -> None:
        check = numbered_item(section(ship_text, "Pre-flight Checks"), "**Reviewed on this SHA**")
        assert "`/push-pr` must only push the existing marker commit" in check
        assert "clean-tree contract" in check

    def test_ship_failure_names_an_existing_ado_pr(self, ship_text: str) -> None:
        """The `@` fallback FAIL arrives after a PR exists, so ship must not say none was made."""
        step = numbered_item(section(ship_text, "Process"), "If no blocking check failed")
        owner = next(ln for ln in step.splitlines() if "`mode=owner`" in ln)
        assert "no PR was created" not in owner
        assert "that PR exists" in owner

    def test_ship_keeps_pipeline_policy_scripts(self, ship_text: str) -> None:
        """Inverse guard: pipeline checks stay in ship when PR creation moves out."""
        assert "az repos pr policy list" in ship_text
        assert "references/ado-policy-wait.md" in ship_text


class TestAdoDischargeUsesPushPrOutput:
    def test_discharge_reads_pull_request_id_from_push_pr(self, ship_text: str) -> None:
        discharge = numbered_item(section(ship_text, "Process"), "Discharge a deferred")
        ado = discharge.split("For `host=ado`", 1)[1]
        assert "`pullRequestId`" in ado
        assert "`/push-pr` output" in ado
        assert "`pr_id`" in ado
        assert "references/ado-policy-wait.md" in ado
        assert "DEFERRED->FAIL" in ado

    def test_step_3_names_pull_request_id_capture(self, ship_text: str) -> None:
        step = numbered_item(section(ship_text, "Process"), "If no blocking check failed")
        assert "`pullRequestId`" in step
        assert "`pr_id`" in step

    def test_contributor_mode_still_creates_nothing(self, ship_text: str) -> None:
        step = numbered_item(section(ship_text, "Process"), "If no blocking check failed")
        contributor = next(ln for ln in step.splitlines() if "`mode=contributor`" in ln)
        assert "do NOT create a PR" in contributor
        assert "/push-pr" not in contributor
