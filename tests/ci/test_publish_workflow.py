"""publish.yml: build once, gate, verify the digest, then publish.

ADR-113 decisions 1, 4, and 5 and Resolved Questions 2 and 3, issue #5636. A
parsed-YAML test pins the controls that make the dispatch route the only live
route and keep every write permission and every candidate-code step out of the
jobs that hold secrets or decide the verdict.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PUBLISH = ROOT / ".github" / "workflows" / "publish.yml"
SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    document = yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _jobs(workflow: dict[str, Any]) -> dict[str, Any]:
    return workflow["jobs"]


def _steps(workflow: dict[str, Any], job: str) -> list[dict[str, Any]]:
    return _jobs(workflow)[job]["steps"]


def _names(workflow: dict[str, Any], job: str) -> list[str | None]:
    return [step.get("name") for step in _steps(workflow, job)]


def _normalized(text: str) -> str:
    return " ".join(str(text).split())


def test_triggers_are_a_tag_push_and_a_dispatch_only(workflow: dict[str, Any]) -> None:
    triggers = next(value for key, value in workflow.items() if key in ("on", True))
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"] == {"tags": ["v*"]}
    assert set(triggers["workflow_dispatch"]["inputs"]) == {
        "dry-run",
        "candidate-sha",
        "release-tag",
    }
    assert triggers["workflow_dispatch"]["inputs"]["dry-run"]["default"] == "true"


def test_the_jobs_run_in_the_documented_order(workflow: dict[str, Any]) -> None:
    jobs = _jobs(workflow)
    assert set(jobs) == {"resolve", "build", "gate", "publish", "attach"}
    assert "needs" not in jobs["resolve"]
    assert jobs["build"]["needs"] == "resolve"
    assert jobs["gate"]["needs"] == ["resolve", "build"]
    assert jobs["publish"]["needs"] == ["resolve", "build", "gate"]
    assert jobs["attach"]["needs"] == ["resolve", "gate", "publish"]


def test_the_default_permissions_are_empty(workflow: dict[str, Any]) -> None:
    assert workflow["permissions"] == {}


def test_only_the_gate_call_holds_a_write_permission_and_publish_holds_the_token_exchange(
    workflow: dict[str, Any],
) -> None:
    jobs = _jobs(workflow)
    writers = {
        name
        for name, job in jobs.items()
        if any(level == "write" for level in job.get("permissions", {}).values())
    }
    assert writers == {"gate", "publish", "attach"}
    assert jobs["gate"]["permissions"] == {"contents": "write", "actions": "read", "checks": "read"}
    assert jobs["attach"]["permissions"] == {"contents": "write"}
    assert jobs["publish"]["permissions"] == {"contents": "read", "id-token": "write"}
    for name in ("resolve", "build"):
        assert jobs[name]["permissions"] == {"contents": "read"}


def test_the_gate_is_the_reusable_workflow_and_takes_the_build_outputs(
    workflow: dict[str, Any],
) -> None:
    gate = _jobs(workflow)["gate"]
    assert gate["uses"] == "./.github/workflows/promotion-gate.yml"
    assert "steps" not in gate
    assert gate["with"] == {
        "candidate-sha": "${{ needs.resolve.outputs.candidate_sha }}",
        "candidate-digest": "${{ needs.build.outputs.digest }}",
        "release-tag": "${{ needs.resolve.outputs.release_tag }}",
        "mode": "${{ needs.resolve.outputs.mode }}",
        "build-run-id": "${{ github.run_id }}",
        "attach-manifest": False,
    }


def test_publish_runs_only_for_a_good_dry_run_or_a_promoted_gate(workflow: dict[str, Any]) -> None:
    condition = _normalized(_jobs(workflow)["publish"]["if"])
    assert condition == (
        "${{ !cancelled() && ((needs.resolve.outputs.dry_run == 'true' && "
        "needs.build.result == 'success') || (needs.gate.result == 'success' && "
        "needs.gate.outputs.promoted == 'true')) }}"
    )


def test_the_digest_is_verified_before_either_publish_step(workflow: dict[str, Any]) -> None:
    names = _names(workflow, "publish")
    verify = names.index("Verify the tarball digest")
    assert verify < names.index("Publish (dry-run)")
    assert verify < names.index("Publish")
    step = _steps(workflow, "publish")[verify]
    command = _normalized(step["run"])
    assert "tarball_digest.py verify" in command
    assert '--expected "$BOUND_DIGEST"' in command
    assert step["env"]["BOUND_DIGEST"] == "${{ needs.build.outputs.digest }}"


def test_publish_publishes_the_verified_file_not_a_rebuild(workflow: dict[str, Any]) -> None:
    steps = {s.get("name"): s for s in _steps(workflow, "publish")}
    for name in ("Publish (dry-run)", "Publish"):
        assert steps[name]["env"]["TARBALL"] == "${{ steps.verify.outputs.file }}"
        assert 'npm publish "$TARBALL"' in steps[name]["run"]
    assert "--dry-run" in steps["Publish (dry-run)"]["run"]
    assert "--dry-run" not in steps["Publish"]["run"]
    assert not any("npm ci" in str(s.get("run", "")) for s in _steps(workflow, "publish"))


def test_publish_downloads_the_artifact_the_build_uploaded(workflow: dict[str, Any]) -> None:
    upload = next(s for s in _steps(workflow, "build") if s.get("name") == "Upload the tarball")
    download = next(
        s
        for s in _steps(workflow, "publish")
        if s.get("name") == "Download the tarball the gate bound"
    )
    assert upload["with"]["name"] == download["with"]["name"] == "npm-tarball"


def test_the_tarball_is_packed_once_and_hashed_before_it_is_uploaded(
    workflow: dict[str, Any],
) -> None:
    names = _names(workflow, "build")
    assert names.count("Pack the tarball once") == 1
    assert names.index("Pack the tarball once") < names.index("Hash the tarball")
    assert names.index("Hash the tarball") < names.index("Upload the tarball")
    all_runs = " ".join(str(s.get("run", "")) for job in ("resolve", "build", "publish")
                        for s in _steps(workflow, job))  # fmt: skip
    assert all_runs.count("npm pack") == 1


def test_build_evidence_names_the_candidate_and_the_digest_for_both_table_rows(
    workflow: dict[str, Any],
) -> None:
    calls = [
        s
        for s in _steps(workflow, "build")
        if s.get("uses") == "./.github/actions/upload-validator-evidence"
    ]
    assert [c["with"]["validator"] for c in calls] == ["npm_package_metadata", "npm_pack_size"]
    for call in calls:
        assert call["if"] == "always() && steps.digest.outputs.digest != ''"
        assert call["with"]["kind"] == "build"
        assert call["with"]["revision"] == "${{ needs.resolve.outputs.candidate_sha }}"
        assert call["with"]["digest"] == "${{ steps.digest.outputs.digest }}"
        assert call["with"]["job-status"] == "${{ job.status }}"


def test_the_build_job_is_named_for_the_table_rows(workflow: dict[str, Any]) -> None:
    from scripts.validation.promotion_applicability import load_applicability

    build_rows = [r for r in load_applicability(ROOT) if r.tier == "build"]
    assert {r.validator for r in build_rows} == {"npm_package_metadata", "npm_pack_size"}
    for row in build_rows:
        assert row.workflow == ".github/workflows/publish.yml"
        assert row.job == _jobs(workflow)["build"]["name"]


def test_tooling_comes_from_the_default_branch_and_the_candidate_is_only_built(
    workflow: dict[str, Any],
) -> None:
    for job in ("build", "publish"):
        checkouts = [
            s
            for s in _steps(workflow, job)
            if str(s.get("uses", "")).startswith("actions/checkout@")
        ]
        assert len(checkouts) == 2
        tooling, candidate = checkouts
        assert "ref" not in tooling.get("with", {})
        assert candidate["with"]["ref"] == "${{ needs.resolve.outputs.candidate_sha }}"
        assert candidate["with"]["path"] == "candidate"
        assert all(c["with"]["persist-credentials"] is False for c in checkouts)
    for step in _steps(workflow, "build"):
        run = str(step.get("run", ""))
        if "scripts/" in run:
            assert "candidate/scripts" not in run


def test_candidate_package_commands_run_only_in_the_candidate_directory(
    workflow: dict[str, Any],
) -> None:
    for step in _steps(workflow, "build"):
        if re.search(r"\bnpm (ci|run|pack)\b", str(step.get("run", ""))):
            assert step["working-directory"] == "${{ env.PACKAGE_DIR }}"
    assert workflow["env"]["PACKAGE_DIR"] == "candidate/packages/ai-agents-cli"


def test_the_route_is_decided_first_from_env_only(workflow: dict[str, Any]) -> None:
    step = next(s for s in _steps(workflow, "resolve") if s.get("id") == "route")
    command = _normalized(step["run"])
    assert "resolve_publish_route.py route" in command
    assert "${{" not in step["run"]
    assert step["env"]["EVENT_NAME"] == "${{ github.event_name }}"
    assert step["env"]["REF"] == "${{ github.ref }}"


def test_nothing_reaches_the_shell_through_an_expression(workflow: dict[str, Any]) -> None:
    for name, job in _jobs(workflow).items():
        for step in job.get("steps", []):
            assert "${{" not in str(step.get("run", "")), (name, step.get("name"))


def test_the_manifest_is_attached_only_after_a_successful_real_publish(
    workflow: dict[str, Any],
) -> None:
    attach = _jobs(workflow)["attach"]
    assert _normalized(attach["if"]) == (
        "${{ !cancelled() && needs.publish.result == 'success' "
        "&& needs.resolve.outputs.dry_run == 'false' "
        "&& needs.resolve.outputs.release_tag != '' "
        "&& needs.gate.outputs.release_eligible == 'true' }}"
    )
    uses = [str(s.get("uses", "")) for s in attach["steps"]]
    assert not any(u.startswith("actions/checkout") for u in uses)
    runs = [str(s["run"]) for s in attach["steps"] if "run" in s]
    assert len(runs) == 1
    assert "gh release upload" in runs[0]
    assert "gh release create" not in runs[0]
    assert "scripts/" not in runs[0]


def test_the_secret_is_read_only_by_the_publish_steps(workflow: dict[str, Any]) -> None:
    text = PUBLISH.read_text(encoding="utf-8")
    assert text.count("secrets.NPM_TOKEN") == 2
    for step in _steps(workflow, "publish"):
        if "secrets.NPM_TOKEN" in str(step.get("env", {})):
            assert str(step["name"]).startswith("Publish")


def test_no_job_triggers_on_a_pull_request_or_checks_out_a_head_ref() -> None:
    text = PUBLISH.read_text(encoding="utf-8")
    for forbidden in ("pull_request_target", "github.head_ref", "github.event.pull_request"):
        assert forbidden not in text


def test_every_external_action_is_pinned_to_a_full_commit_sha(workflow: dict[str, Any]) -> None:
    for name, job in _jobs(workflow).items():
        for step in job.get("steps", []):
            uses = str(step.get("uses", ""))
            if uses and not uses.startswith("./"):
                assert SHA_PIN.match(uses), (name, uses)


def test_the_tag_route_is_refused_by_the_first_job_and_nothing_downstream_runs_without_it(
    workflow: dict[str, Any],
) -> None:
    jobs = _jobs(workflow)
    for name in ("build", "gate", "publish", "attach"):
        needs = jobs[name]["needs"]
        assert "resolve" in (needs if isinstance(needs, list) else [needs])
    assert jobs["resolve"]["outputs"]["candidate_sha"] == "${{ steps.route.outputs.candidate_sha }}"
