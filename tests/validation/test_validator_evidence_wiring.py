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


def test_every_commit_tier_validator_has_an_upload_step() -> None:
    wanted = {row.validator for row in load_applicability(ROOT) if row.tier == "commit"}
    assert wanted - set(_uploaded()) == set()


def test_no_upload_step_names_a_validator_the_table_lacks() -> None:
    known = {row.validator for row in load_applicability(ROOT)}
    assert set(_uploaded()) - known == set()


def test_each_validator_is_uploaded_from_the_job_the_table_names() -> None:
    uploaded = _uploaded()
    for row in load_applicability(ROOT):
        if row.tier != "commit":
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


@pytest.mark.parametrize("call", _calls(), ids=lambda c: f"{c['file']}:{c['job_id']}")
def test_the_job_gains_no_write_to_contents_and_no_token_exchange(call: dict[str, Any]) -> None:
    permissions = call["job"].get("permissions") or {}
    assert permissions.get("contents", "read") != "write"
    assert "id-token" not in permissions


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
