"""Every commit-tier validator in the applicability table uploads evidence.

ADR-113 decisions 2 and 3, issue #5636. A table row whose job never uploads
reads as a missing result, so the gate would block on a validator that cannot
report. This drift test pins the two together and pins the shape of each call.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.validation.promotion_applicability import load_applicability

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
ACTION_DIR = ROOT / ".github" / "actions" / "upload-validator-evidence"
USES = "./.github/actions/upload-validator-evidence"
EMITTER = ROOT / "scripts" / "validation" / "emit_validator_evidence.py"
SHA_PIN = re.compile(r"@[0-9a-f]{40}$")
MATRIX_REF = "${{ matrix.language }}"


def _calls() -> list[dict[str, Any]]:
    """Return one record per workflow step that calls the upload action."""
    found: list[dict[str, Any]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_id, job in (document.get("jobs") or {}).items():
            steps = job.get("steps") or []
            for index, step in enumerate(steps):
                if step.get("uses") == USES:
                    found.append(
                        {
                            "file": path.name,
                            "job_id": job_id,
                            "job": job,
                            "step": step,
                            "is_last": index == len(steps) - 1,
                        }
                    )
    return found


def _expanded_validators(call: dict[str, Any]) -> list[str]:
    name = str(call["step"]["with"]["validator"])
    if MATRIX_REF not in name:
        return [name]
    legs = call["job"]["strategy"]["matrix"]["include"]
    return [name.replace(MATRIX_REF, leg["language"]) for leg in legs]


def _uploaded() -> dict[str, dict[str, Any]]:
    return {name: call for call in _calls() for name in _expanded_validators(call)}


def test_the_table_has_commit_tier_rows_to_cover() -> None:
    rows = [row for row in load_applicability(ROOT) if row.tier == "commit"]
    assert len(rows) >= 9


# Validators whose jobs live in pytest.yml. A push that changes only that file
# runs the whole suite in the pre-push hook, so its wiring is a separate change.
# The follow-up that wires them empties this set, and the test below fails until
# it does.
AWAITING_WIRING = frozenset({"run_python_tests", "check_whole_tree_count_ratchets_blocking"})


def test_every_commit_tier_validator_has_an_upload_step() -> None:
    wanted = {row.validator for row in load_applicability(ROOT) if row.tier == "commit"}
    assert wanted - set(_uploaded()) == AWAITING_WIRING


def test_a_validator_awaiting_wiring_has_no_upload_step_yet() -> None:
    """Fails the moment a pending validator is wired, so the set cannot go stale."""
    assert AWAITING_WIRING & set(_uploaded()) == set()


def test_no_upload_step_names_a_validator_the_table_lacks() -> None:
    known = {row.validator for row in load_applicability(ROOT)}
    assert set(_uploaded()) - known == set()


def test_each_validator_is_uploaded_from_the_job_the_table_names() -> None:
    uploaded = _uploaded()
    for row in load_applicability(ROOT):
        if row.tier != "commit" or row.validator in AWAITING_WIRING:
            continue
        job_name = str(uploaded[row.validator]["job"]["name"])
        expected = row.job.split("(")[0].strip()
        assert job_name.replace("${{ matrix.language }}", "").split("(")[0].strip() == expected


def test_no_validator_is_uploaded_twice() -> None:
    names = [name for call in _calls() for name in _expanded_validators(call)]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("call", _calls(), ids=lambda c: f"{c['file']}:{c['job_id']}")
def test_the_call_runs_last_and_always_with_the_job_status(call: dict[str, Any]) -> None:
    step = call["step"]
    assert call["is_last"]
    assert step["if"] == "always()"
    assert step["with"]["job-status"] == "${{ job.status }}"


@pytest.mark.parametrize("call", _calls(), ids=lambda c: f"{c['file']}:{c['job_id']}")
def test_the_job_checks_out_the_emitter_before_the_call(call: dict[str, Any]) -> None:
    """The local action resolves only after a checkout holds it and the emitter."""
    steps = call["job"]["steps"]
    before = steps[: steps.index(call["step"])]
    assert any(str(s.get("uses", "")).startswith("actions/checkout@") for s in before)


def _effective_permissions(call: dict[str, Any]) -> dict[str, Any]:
    """Job permissions, or the workflow-level block the job inherits."""
    job = call["job"].get("permissions")
    if job is not None:
        return dict(job)
    document = yaml.safe_load((WORKFLOWS / call["file"]).read_text(encoding="utf-8"))
    return dict(document.get("permissions") or {})


@pytest.mark.parametrize("call", _calls(), ids=lambda c: f"{c['file']}:{c['job_id']}")
def test_the_job_has_no_contents_write_and_no_token_exchange(call: dict[str, Any]) -> None:
    permissions = _effective_permissions(call)
    assert permissions.get("contents", "read") != "write"
    assert "id-token" not in permissions


SKIP_ON_SHORT_CIRCUIT = "steps.should-run.outputs.skip != 'true'"
EXPECTED_RAN = {
    "analyze_actions": "needs.check-paths.outputs.should-run-analysis == 'true'",
    "analyze_python": "needs.check-paths.outputs.should-run-analysis == 'true'",
    "validate_generated_files": SKIP_ON_SHORT_CIRCUIT,
    "validate_path_normalization": SKIP_ON_SHORT_CIRCUIT,
    "validate_pr": SKIP_ON_SHORT_CIRCUIT,
    "validate_pr_title": (
        "github.event_name != 'merge_group' && github.actor != 'dependabot[bot]' "
        "&& github.actor != 'github-actions[bot]' && github.actor != 'renovate[bot]'"
    ),
    "validate_plugin_version_bump": None,
}


def _ran_expression(call: dict[str, Any]) -> str | None:
    value = call["step"]["with"].get("ran")
    if value is None:
        return None
    return str(value).removeprefix("${{ ").removesuffix(" }}")


def test_every_uploaded_validator_has_an_expected_ran_expression() -> None:
    assert set(_uploaded()) == set(EXPECTED_RAN)


@pytest.mark.parametrize("validator", sorted(EXPECTED_RAN))
def test_a_job_that_can_short_circuit_says_so_in_ran(validator: str) -> None:
    """A green job that did no work must read SKIP, so `ran` must follow its own guard."""
    call = _uploaded()[validator]
    assert _ran_expression(call) == EXPECTED_RAN[validator]


def test_the_emitter_checkout_in_a_conditional_job_fetches_only_what_it_needs() -> None:
    for call in _calls():
        for step in call["job"]["steps"]:
            if step.get("name") == "Check out the evidence emitter":
                assert step["if"] == "always() && steps.checkout.outcome != 'success'"
                assert step["with"]["persist-credentials"] is False
                sparse = step["with"]["sparse-checkout"]
                assert "scripts/validation" in sparse
                assert ".github/actions/upload-validator-evidence" in sparse


def _action() -> dict[str, Any]:
    return yaml.safe_load((ACTION_DIR / "action.yml").read_text(encoding="utf-8"))


def test_the_action_pins_every_external_step_to_a_commit_sha() -> None:
    external = [s["uses"] for s in _action()["runs"]["steps"] if "uses" in s]
    assert external
    assert all(SHA_PIN.search(use.split(" ")[0]) for use in external)


def test_the_action_uploads_only_when_the_emitter_wrote_a_file() -> None:
    upload = next(s for s in _action()["runs"]["steps"] if "uses" in s)
    assert upload["if"] == "steps.emit.outputs.emitted == 'true'"
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["name"] == "${{ inputs.validator }}"


def test_action_metadata_holds_no_expression() -> None:
    """Metadata fields are not evaluated; `gh act` rejects an expression in a description."""
    action = _action()
    texts = [action["name"], action["description"]]
    texts += [spec["description"] for spec in action["inputs"].values()]
    assert [text for text in texts if "${{" in text] == []


def test_the_action_keeps_evidence_for_the_adr_015_standard_tier() -> None:
    """ADR-015 allows 1 or 7 days; scripts/ci/adr015_workflow_retention.py scans workflows only."""
    upload = next(s for s in _action()["runs"]["steps"] if "uses" in s)
    assert upload["with"]["retention-days"] == 7


def test_the_action_passes_context_through_env_never_into_the_script() -> None:
    run = next(s for s in _action()["runs"]["steps"] if s.get("id") == "emit")
    assert "${{" not in run["run"]
    assert "${{ inputs.validator }}" == run["env"]["VALIDATOR"]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _third_party(path: Path, seen: set[Path]) -> set[str]:
    if path in seen:
        return set()
    seen.add(path)
    bad: set[str] = set()
    for name in _imports(path):
        if name.startswith("scripts."):
            module = ROOT.joinpath(*name.split("."))
            target = module.with_suffix(".py")
            bad |= _third_party(target if target.exists() else module / "__init__.py", seen)
        elif name.split(".")[0] not in sys.stdlib_module_names:
            bad.add(name)
    return bad


def test_the_emitter_imports_only_the_standard_library_transitively() -> None:
    """ci-scripts.md MUST 18: the jobs call it with bare python3."""
    assert _third_party(EMITTER, set()) == set()
