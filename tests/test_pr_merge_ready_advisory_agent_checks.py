# taste-lint: ignore file-size -- one suite owns the shared git fixtures and check matrix.
"""Advisory agent workflows never block a merge (owner policy, D4/D6/D9).

A non-required check is exempt only when its CheckRun belongs to a listed
workflow file. The list comes from the trusted ref, so a PR cannot exempt its
own failing check (CWE-829). A required check, a status context, and a check
from an unlisted workflow all keep blocking.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tests.test_test_pr_merge_ready import _OPEN_PR, _mod

check_merge_readiness = _mod.check_merge_readiness

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CONFIG_PATH = ".claude/skills/pr-review/pr-review-config.yaml"
LISTED = ".github/workflows/ai-spec-validation.yml"
UNLISTED = ".github/workflows/pytest.yml"
AGENT_CHECK = "Validate Spec Coverage"


def _resource(workflow_file: str, owner: str = "o", repo: str = "r") -> str:
    return f"/{owner}/{repo}/actions/workflows/{Path(workflow_file).name}"


def _pr_with(*rows: dict) -> dict:
    pr_data = json.loads(json.dumps(_OPEN_PR))
    pr = pr_data["repository"]["pullRequest"]
    pr["mergeStateStatus"] = "UNSTABLE"
    rollup = pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
    rollup["contexts"]["nodes"] = list(rows)
    rollup["state"] = "FAILURE"
    return pr_data


def _row(
    name: str,
    conclusion: str | None,
    status: str = "COMPLETED",
    required: bool = False,
    workflow: str | None = LISTED,
    resource: str | None = None,
) -> dict:
    row: dict = {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "isRequired": required,
        "checkSuite": {"workflowRun": None},
    }
    if workflow or resource:
        row["checkSuite"] = {
            "workflowRun": {"workflow": {"resourcePath": resource or _resource(workflow)}}
        }
    return row


def _status_context(name: str, state: str, required: bool = False) -> dict:
    return {"__typename": "StatusContext", "context": name, "state": state, "isRequired": required}


def _readiness(pr_data: dict, listed: set[str], include_non_required: bool = False) -> dict:
    with (
        patch("test_pr_merge_ready.gh_graphql", return_value=pr_data),
        patch(
            "test_pr_merge_ready._load_advisory_agent_workflows",
            return_value=frozenset(listed),
        ),
    ):
        return check_merge_readiness("o", "r", 42, include_non_required=include_non_required)


# ---------------------------------------------------------------------------
# Positive: a check from a listed workflow does not block in any state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("include_non_required", [False, True])
@pytest.mark.parametrize(
    ("status", "conclusion"),
    [
        ("COMPLETED", "FAILURE"),
        ("WAITING", None),
        ("PENDING", None),
        ("QUEUED", None),
        ("IN_PROGRESS", None),
        ("COMPLETED", "CANCELLED"),
        ("COMPLETED", "SKIPPED"),
        ("COMPLETED", "TIMED_OUT"),
    ],
)
def test_listed_workflow_check_never_blocks(
    status: str, conclusion: str | None, include_non_required: bool
) -> None:
    """FAILED is intended to be non-blocking: an agent verdict is advisory."""
    pr_data = _pr_with(_row(AGENT_CHECK, conclusion, status))
    result = _readiness(pr_data, {LISTED}, include_non_required)
    assert result["CanMerge"] is True, result["Reasons"]
    assert result["UndisposedNonRequiredFailures"] == []
    assert result["CIPassing"] is True


# ---------------------------------------------------------------------------
# Negative: everything else keeps its normal verdict
# ---------------------------------------------------------------------------


def test_unlisted_workflow_failure_still_blocks() -> None:
    pr_data = _pr_with(_row("Run Python Tests", "FAILURE", workflow=UNLISTED))
    result = _readiness(pr_data, {LISTED})
    assert result["CanMerge"] is False
    assert result["UndisposedNonRequiredFailures"] == ["Run Python Tests"]


def test_unlisted_workflow_using_a_listed_job_name_still_blocks() -> None:
    """Spoof: the job name matches a listed workflow's job, the workflow does not."""
    pr_data = _pr_with(_row(AGENT_CHECK, "FAILURE", workflow=UNLISTED))
    result = _readiness(pr_data, {LISTED})
    assert result["CanMerge"] is False
    assert result["UndisposedNonRequiredFailures"] == [AGENT_CHECK]


def test_a_name_shared_with_an_unlisted_workflow_is_not_exempt() -> None:
    pr_data = _pr_with(
        _row(AGENT_CHECK, "FAILURE", workflow=LISTED),
        _row(AGENT_CHECK, "FAILURE", workflow=UNLISTED),
    )
    result = _readiness(pr_data, {LISTED})
    assert result["CanMerge"] is False


def test_status_context_with_a_listed_job_name_still_blocks() -> None:
    pr_data = _pr_with(_status_context(AGENT_CHECK, "FAILURE"))
    result = _readiness(pr_data, {LISTED})
    assert result["CanMerge"] is False
    assert result["UndisposedNonRequiredFailures"] == [AGENT_CHECK]


def test_a_status_context_cannot_ride_beside_a_listed_check_row() -> None:
    pr_data = _pr_with(
        _row(AGENT_CHECK, "FAILURE", workflow=LISTED),
        _status_context(AGENT_CHECK, "FAILURE"),
    )
    result = _readiness(pr_data, {LISTED})
    assert result["CanMerge"] is False


def test_check_run_without_a_workflow_run_still_blocks() -> None:
    pr_data = _pr_with(_row(AGENT_CHECK, "FAILURE", workflow=None))
    result = _readiness(pr_data, {LISTED})
    assert result["CanMerge"] is False


@pytest.mark.parametrize(
    "resource",
    [
        "/other/repo/actions/workflows/ai-spec-validation.yml",
        "/o/r/actions/workflows/sub/ai-spec-validation.yml",
        "/o/r/actions/workflows/",
        "/o/r/ai-spec-validation.yml",
    ],
)
def test_a_resource_path_from_another_repo_or_shape_is_not_exempt(resource: str) -> None:
    pr_data = _pr_with(_row(AGENT_CHECK, "FAILURE", workflow=None, resource=resource))
    result = _readiness(pr_data, {LISTED})
    assert result["CanMerge"] is False


def test_unlisted_pending_still_blocks_when_non_required_count() -> None:
    pr_data = _pr_with(_row("Run Python Tests", None, "IN_PROGRESS", workflow=UNLISTED))
    result = _readiness(pr_data, {LISTED}, include_non_required=True)
    assert result["CanMerge"] is False


def test_a_listed_check_does_not_hide_an_unlisted_failure_beside_it() -> None:
    pr_data = _pr_with(
        _row(AGENT_CHECK, "FAILURE"),
        _row("Run Python Tests", "FAILURE", workflow=UNLISTED),
    )
    result = _readiness(pr_data, {LISTED})
    assert result["CanMerge"] is False
    assert result["UndisposedNonRequiredFailures"] == ["Run Python Tests"]


def test_empty_list_exempts_nothing() -> None:
    pr_data = _pr_with(_row(AGENT_CHECK, "FAILURE"))
    assert _readiness(pr_data, set())["CanMerge"] is False


# ---------------------------------------------------------------------------
# Edge: listed but required still blocks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("status", "conclusion"), [("COMPLETED", "FAILURE"), ("WAITING", None)])
def test_listed_but_required_check_still_blocks(status: str, conclusion: str | None) -> None:
    pr_data = _pr_with(_row(AGENT_CHECK, conclusion, status, required=True))
    result = _readiness(pr_data, {LISTED})
    assert result["CanMerge"] is False
    assert any(AGENT_CHECK in reason for reason in result["Reasons"])


# ---------------------------------------------------------------------------
# Edge: the list is read from the trusted ref, never the branch
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, timeout=30)


def _config(paths: list[str]) -> str:
    entries = "".join(
        f'  - path: "{path}"\n    reason: "test"\n    owner: "rjmurillo"\n' for path in paths
    )
    return f"scripts: {{}}\nadvisory_agent_workflows:\n{entries}\ntransport_preflight: {{}}\n"


def _init_origin(tmp_path: Path) -> tuple[Path, Path]:
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True, capture_output=True)
    _git(work, "config", "user.email", "t@example.invalid")
    _git(work, "config", "user.name", "t")
    target = work / CONFIG_PATH
    target.parent.mkdir(parents=True)
    target.write_text(_config([LISTED]), encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "base")
    _git(work, "push", "-q", "origin", "HEAD:main")
    _git(work, "fetch", "-q", "origin", "main")
    return bare, work


@pytest.fixture
def origin_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    return _init_origin(tmp_path)


@pytest.fixture
def clone(origin_and_clone: tuple[Path, Path]) -> Path:
    return origin_and_clone[1]


def test_loader_reads_the_trusted_ref(clone: Path) -> None:
    assert _mod._load_advisory_agent_workflows(cwd=str(clone)) == {LISTED}


def test_branch_edited_list_is_ignored(clone: Path) -> None:
    (clone / CONFIG_PATH).write_text(_config([LISTED, UNLISTED]), encoding="utf-8")
    _git(clone, "commit", "-qam", "branch edits the list")
    assert _mod._load_advisory_agent_workflows(cwd=str(clone)) == {LISTED}


def test_uncommitted_edit_is_ignored(clone: Path) -> None:
    (clone / CONFIG_PATH).write_text(_config([UNLISTED]), encoding="utf-8")
    assert _mod._load_advisory_agent_workflows(cwd=str(clone)) == {LISTED}


def test_absent_ref_fails_closed_and_warns(clone: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = _mod._load_advisory_agent_workflows(trust_anchor_ref="origin/absent", cwd=str(clone))
    assert result == frozenset()
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "cannot read" in err
    assert "origin/absent" in err


def test_shallow_clone_without_the_ref_fails_closed_and_warns(
    origin_and_clone: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bare, work = origin_and_clone
    _git(work, "checkout", "-q", "-b", "feature")
    (work / "note.txt").write_text("x\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "feature")
    _git(work, "push", "-q", "origin", "feature")
    shallow = tmp_path / "shallow"
    subprocess.run(
        [
            "git",
            "clone",
            "-q",
            "--depth",
            "1",
            "--single-branch",
            "--branch",
            "feature",
            bare.resolve().as_uri(),
            str(shallow),
        ],
        check=True,
        capture_output=True,
    )
    result = _mod._load_advisory_agent_workflows(cwd=str(shallow))
    assert result == frozenset()
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "shallow clone" in err


def test_unparseable_list_fails_closed_and_warns(
    clone: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (clone / CONFIG_PATH).write_text(
        'advisory_agent_workflows:\n  - path: "x.yml"\n    owner: "o"\n', encoding="utf-8"
    )
    _git(clone, "commit", "-qam", "list without a reason")
    _git(clone, "push", "-q", "origin", "HEAD:main")
    _git(clone, "fetch", "-q", "origin", "main")
    assert _mod._load_advisory_agent_workflows(cwd=str(clone)) == frozenset()
    err = capsys.readouterr().err
    assert "parse error" in err


def test_not_a_repository_fails_closed_and_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _mod._load_advisory_agent_workflows(cwd=str(tmp_path)) == frozenset()
    assert "WARNING" in capsys.readouterr().err


def test_end_to_end_branch_edit_does_not_exempt_a_failing_check(clone: Path) -> None:
    (clone / CONFIG_PATH).write_text(_config([LISTED, UNLISTED]), encoding="utf-8")
    _git(clone, "commit", "-qam", "branch edits the list")
    trusted = _mod._load_advisory_agent_workflows(cwd=str(clone))
    pr_data = _pr_with(_row("Run Python Tests", "FAILURE", workflow=UNLISTED))
    assert _readiness(pr_data, set(trusted))["CanMerge"] is False


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parser_reads_quoted_entries_and_stops_at_the_next_key() -> None:
    text = (
        "other: 1\nadvisory_agent_workflows:\n"
        '  - path: ".github/workflows/a.yml"\n    reason: "r"\n    owner: "o"\n'
        "  # comment\n"
        "  - path: '.github/workflows/b.yml'\n    reason: r # note\n    owner: o\n"
        "next_key: 2\n"
    )
    assert _mod._parse_advisory_agent_workflows(text) == {
        ".github/workflows/a.yml",
        ".github/workflows/b.yml",
    }


@pytest.mark.parametrize(
    "text",
    [
        "scripts: {}\n",
        'advisory_agent_workflows:\n  - path: "a.yml"\n    owner: "o"\n',
        'advisory_agent_workflows:\n  - path: "a.yml"\n    reason: "r"\n',
        'advisory_agent_workflows:\n    reason: "r"\n',
        'advisory_agent_workflows:\n  - reason: "r"\n',
        "advisory_agent_workflows:\n  - garbage\n",
    ],
)
def test_parser_rejects_malformed_lists(text: str) -> None:
    with pytest.raises(ValueError):
        _mod._parse_advisory_agent_workflows(text)


# ---------------------------------------------------------------------------
# Shipped contract and drift
# ---------------------------------------------------------------------------


def _workflow_docs() -> dict[str, dict]:
    return {
        f".github/workflows/{path.name}": yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(WORKFLOWS.glob("*.yml"))
    }


def _triggers(doc: dict) -> set[str]:
    on = doc.get(True) if True in doc else doc.get("on")
    return set(on) if isinstance(on, dict) else {on} if isinstance(on, str) else set(on or [])


# Per-provider approval environments. Each holds one provider's secrets and
# requires a reviewer. agent-approval holds no secrets and no workflow uses it.
PROVIDER_ENVIRONMENTS = frozenset({"agent-claude", "agent-codex", "agent-droid", "agent-copilot"})
RETIRED_ENVIRONMENT = "agent-approval"
# The nightly smoke picks its environment from the matrix leg, one per CLI.
MATRIX_ENVIRONMENT = "agent-${{ matrix.cli }}"
# Stored secret each provider's model calls read, derived from the workflows.
PROVIDER_SECRETS = {
    "claude": ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"),
    "codex": ("OPENAI_API_KEY",),
    "droid": ("FACTORY_API_KEY",),
    "copilot": ("COPILOT_GITHUB_TOKEN",),
}
# Every gated job and the provider environment it must declare. Jobs that read
# no provider secret in YAML (the Copilot synthesis scripts, claude.yml's
# action) are pinned here by name.
EXPECTED_JOB_ENVIRONMENTS = {
    ("ai-metrics-analysis.yml", "analyze-metrics"): "agent-copilot",
    ("ai-spec-validation.yml", "validate-spec"): "agent-claude",
    ("artifact-insight-scanner.yml", "scan-artifacts"): "agent-copilot",
    ("claude.yml", "claude-response"): "agent-claude",
    ("copilot-context-synthesis.yml", "synthesize-single"): "agent-copilot",
    ("copilot-context-synthesis.yml", "sweep-missed"): "agent-copilot",
    ("nightly-cli-smoke.yml", "smoke"): MATRIX_ENVIRONMENT,
    ("post-pr-retrospective.yml", "retrospective"): "agent-claude",
    ("pr-maintenance.yml", "process-prs"): "agent-copilot",
    ("skill-overlap-eval.yml", "run-eval"): "agent-claude",
    ("slash-command-quality.yml", "validate-slash-commands"): "agent-claude",
    ("software-engineering-library-activation.yml", "activation-gate"): "agent-claude",
}


def _is_gated(job: dict) -> bool:
    environment = job.get("environment")
    return environment in PROVIDER_ENVIRONMENTS or environment == MATRIX_ENVIRONMENT


def _gated_jobs(doc: dict) -> list[str]:
    return [k for k, j in (doc.get("jobs") or {}).items() if _is_gated(j)]


def _provider_of_secret(text: str) -> set[str]:
    return {
        provider
        for provider, names in PROVIDER_SECRETS.items()
        if any(f"secrets.{name}" in text for name in names)
    }


def _shipped_entries() -> list[dict]:
    return yaml.safe_load((REPO_ROOT / CONFIG_PATH).read_text(encoding="utf-8"))[
        "advisory_agent_workflows"
    ]


def test_shipped_list_parses_to_the_yaml_paths() -> None:
    text = (REPO_ROOT / CONFIG_PATH).read_text(encoding="utf-8")
    assert _mod._parse_advisory_agent_workflows(text) == {e["path"] for e in _shipped_entries()}


def test_every_entry_carries_a_reason_and_the_owner() -> None:
    for entry in _shipped_entries():
        assert entry["reason"].strip()
        assert entry["owner"] == "rjmurillo"


def test_every_listed_path_exists_and_gates_its_model_jobs() -> None:
    docs = _workflow_docs()
    for entry in _shipped_entries():
        assert entry["path"] in docs, entry["path"]
        assert _gated_jobs(docs[entry["path"]]), f"{entry['path']} has no provider-gated job"


def test_every_listed_workflow_triggers_on_pull_request() -> None:
    docs = _workflow_docs()
    for entry in _shipped_entries():
        assert "pull_request" in _triggers(docs[entry["path"]]), entry["path"]


def test_every_pull_request_workflow_with_a_provider_gated_job_is_listed() -> None:
    """Drift: a new agent job on a pull_request workflow must join the list."""
    listed = {e["path"] for e in _shipped_entries()}
    expected = {
        path
        for path, doc in _workflow_docs().items()
        if "pull_request" in _triggers(doc)
        and _gated_jobs(doc)
        and path != ".github/workflows/claude.yml"
    }
    assert listed == expected


def test_claude_workflow_is_gated_by_agent_claude_and_not_listed_as_advisory() -> None:
    doc = _workflow_docs()[".github/workflows/claude.yml"]
    assert _gated_jobs(doc) == ["claude-response"]
    listed = {e["path"] for e in _shipped_entries()}
    assert ".github/workflows/claude.yml" not in listed


def test_no_workflow_uses_the_retired_agent_approval_environment() -> None:
    offenders = [
        path.name
        for path in sorted(WORKFLOWS.glob("*.yml"))
        if RETIRED_ENVIRONMENT in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
    for doc in _workflow_docs().values():
        for job in (doc.get("jobs") or {}).values():
            assert job.get("environment") != RETIRED_ENVIRONMENT


def test_each_gated_job_declares_the_environment_matching_its_provider() -> None:
    docs = _workflow_docs()
    actual = {
        (Path(path).name, job_id): job["environment"]
        for path, doc in docs.items()
        for job_id, job in (doc.get("jobs") or {}).items()
        if _is_gated(job)
    }
    assert actual == EXPECTED_JOB_ENVIRONMENTS


def test_jobs_reading_a_provider_secret_declare_that_provider_environment() -> None:
    """Drift: a job that reads a provider secret must sit in that provider's environment."""
    checked = 0
    for path, doc in _workflow_docs().items():
        for job_id, job in (doc.get("jobs") or {}).items():
            providers = _provider_of_secret(yaml.safe_dump(job))
            if not providers or job.get("environment") == MATRIX_ENVIRONMENT:
                # The matrix job reads one secret per leg; test_nightly_cli_smoke_security.py
                # pins each leg's credential.
                continue
            checked += 1
            expected = {f"agent-{p}" for p in providers}
            environment = job.get("environment")
            assert environment in expected | {MATRIX_ENVIRONMENT}, (
                f"{path}:{job_id} reads {sorted(providers)} secrets but declares {environment!r}"
            )
            assert len(providers) == 1, f"{path}:{job_id} mixes provider secrets"
    assert checked >= 8


@pytest.mark.parametrize(
    ("environment", "providers", "ok"),
    [
        ("agent-claude", {"claude"}, True),
        ("agent-copilot", {"claude"}, False),
        ("agent-approval", {"copilot"}, False),
        (None, {"claude"}, False),
    ],
)
def test_the_provider_environment_rule_rejects_a_mismatch(
    environment: str | None, providers: set[str], ok: bool
) -> None:
    """Negative: the matching rule used above fails closed on a wrong or missing environment."""
    expected = {f"agent-{p}" for p in providers}
    assert (environment in expected) is ok


def test_the_matrix_environment_resolves_to_provider_environments_only() -> None:
    doc = _workflow_docs()[".github/workflows/nightly-cli-smoke.yml"]
    smoke = doc["jobs"]["smoke"]
    clis = smoke["strategy"]["matrix"]["cli"]
    assert {f"agent-{cli}" for cli in clis} <= PROVIDER_ENVIRONMENTS
