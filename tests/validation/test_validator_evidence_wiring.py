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
    """The call from each validator's main job. A skip job's call is in ``_skip_calls``."""
    skip_jobs = {r.path_filter.skip_job for r in load_applicability(ROOT) if r.path_filter}
    return {
        name: call
        for call in _calls()
        if call["job"].get("name") not in skip_jobs
        for name in _expanded_validators(call)
    }


def _skip_calls() -> dict[str, dict[str, Any]]:
    skip_jobs = {r.path_filter.skip_job for r in load_applicability(ROOT) if r.path_filter}
    return {
        name: call
        for call in _calls()
        if call["job"].get("name") in skip_jobs
        for name in _expanded_validators(call)
    }


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


def test_no_validator_is_uploaded_twice_except_by_its_declared_skip_job() -> None:
    names = [name for call in _calls() for name in _expanded_validators(call)]
    declared = {
        r.validator for r in load_applicability(ROOT) if r.path_filter and r.path_filter.skip_job
    }
    repeated = {name for name in names if names.count(name) > 1}
    assert repeated == declared
    assert all(names.count(name) == 2 for name in repeated)


def test_a_skip_job_records_the_skip_and_names_the_job_the_table_declares() -> None:
    rows = {
        r.validator: r for r in load_applicability(ROOT) if r.path_filter and r.path_filter.skip_job
    }
    assert rows
    calls = _skip_calls()
    assert set(calls) == set(rows)
    for name, row in rows.items():
        assert row.path_filter is not None
        assert calls[name]["job"]["name"] == row.path_filter.skip_job
        assert calls[name]["step"]["with"]["ran"] == "false"


@pytest.mark.parametrize("call", _calls(), ids=lambda c: f"{c['file']}:{c['job_id']}")
def test_the_call_runs_last_and_always_with_the_job_status(call: dict[str, Any]) -> None:
    step = call["step"]
    assert call["is_last"] or step["with"].get("kind") == "build"
    expected = "always()"
    if step["with"].get("kind") == "build":
        expected = "always() && steps.digest.outputs.digest != ''"
    assert step["if"] == expected
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
    "run_python_tests": None,
    "check_whole_tree_count_ratchets_blocking": None,
    "npm_package_metadata": None,
    "npm_pack_size": None,
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
                earlier = call["job"]["steps"][: call["job"]["steps"].index(step)]
                has_checkout_id = any(e.get("id") == "checkout" for e in earlier)
                expected = (
                    "always() && steps.checkout.outcome != 'success'"
                    if has_checkout_id
                    else "always()"
                )
                assert step["if"] == expected
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


def test_only_a_build_call_may_name_a_commit_other_than_the_run_commit() -> None:
    run = next(s for s in _action()["runs"]["steps"] if s.get("id") == "emit")
    assert (
        run["env"]["REVISION"] == "${{ (inputs.kind == 'build' && inputs.revision) || github.sha }}"
    )


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


def _module_file(name: str) -> Path:
    module = ROOT.joinpath(*name.split("."))
    return (
        module.with_suffix(".py") if module.with_suffix(".py").exists() else module / "__init__.py"
    )


def _closure(path: Path, seen: set[Path]) -> set[Path]:
    """Every repository file the emitter loads: its imports and each package marker above them.

    Importing ``scripts.validation.evidence`` runs ``scripts/__init__.py`` and
    ``scripts/validation/__init__.py`` first, and the second one imports
    ``scripts.validation.models``, so those are part of the closure too.
    """
    if path in seen:
        return seen
    seen.add(path)
    modules = [name for name in _imports(path) if name.startswith("scripts.")]
    for name in modules:
        parts = name.split(".")
        for depth in range(1, len(parts) + 1):
            _closure(_module_file(".".join(parts[:depth])), seen)
    return seen


def _sparse_checkout(call: dict[str, Any]) -> tuple[list[str], bool] | None:
    """The sparse checkout in force at the call, or None when the last checkout is full.

    Each checkout step replaces the workspace, so the last one before the call
    decides which files exist.
    """
    steps = call["job"]["steps"]
    current: tuple[list[str], bool] | None = None
    for step in steps[: steps.index(call["step"])]:
        if not str(step.get("uses", "")).startswith("actions/checkout@"):
            continue
        options = step.get("with") or {}
        text = options.get("sparse-checkout")
        if not text:
            current = None
            continue
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        current = (lines, options.get("sparse-checkout-cone-mode", True) is not False)
    return current


def _is_checked_out(name: str, patterns: list[str], cone: bool) -> bool:
    """Whether a sparse checkout includes ``name``.

    A pattern names a file or a directory. Cone mode also includes the files
    that sit directly in each parent directory of a listed directory, which is
    why ``scripts/__init__.py`` arrives with ``scripts/validation``.
    """
    for pattern in patterns:
        directory = pattern.rstrip("/")
        if name == pattern or name.startswith(directory + "/"):
            return True
        parent = name.rpartition("/")[0]
        if cone and directory.startswith(parent + "/"):
            return True
    return False


def test_a_sparse_checkout_ahead_of_a_call_carries_the_emitter_and_its_imports() -> None:
    """Some jobs check out only a few files, so the emitter must be in that list."""
    needed = {path.relative_to(ROOT).as_posix() for path in _closure(EMITTER, set())}
    needed |= {".github/actions/upload-validator-evidence/action.yml"}
    for call in _calls():
        sparse = _sparse_checkout(call)
        if sparse is None:
            continue
        for name in needed:
            assert _is_checked_out(name, *sparse), f"{call['file']}:{call['job_id']} omits {name}"


def test_the_closure_includes_the_package_marker_imports() -> None:
    names = {path.relative_to(ROOT).as_posix() for path in _closure(EMITTER, set())}
    assert {
        "scripts/__init__.py",
        "scripts/validation/__init__.py",
        "scripts/validation/models.py",
    } <= names


def test_a_later_full_checkout_replaces_an_earlier_sparse_one() -> None:
    sparse = {"uses": "actions/checkout@x", "with": {"sparse-checkout": "a"}}
    full = {"uses": "actions/checkout@x"}
    call = {"job": {"steps": [sparse, full, {"id": "call"}]}, "step": {"id": "call"}}
    assert _sparse_checkout(call) is None
    call = {"job": {"steps": [full, sparse, {"id": "call"}]}, "step": {"id": "call"}}
    assert _sparse_checkout(call) == (["a"], True)


def test_a_sparse_checkout_check_notices_a_missing_file() -> None:
    patterns = ["scripts/validation/evidence.py"]
    assert not _is_checked_out("scripts/validation/promotion_evidence.py", patterns, cone=False)
    assert _is_checked_out("scripts/validation/evidence.py", patterns, cone=False)
    assert _is_checked_out("scripts/__init__.py", ["scripts/validation"], cone=True)
    assert not _is_checked_out("scripts/__init__.py", ["scripts/validation"], cone=False)


def test_the_emitter_imports_only_the_standard_library_transitively() -> None:
    """ci-scripts.md MUST 18: the jobs call it with bare python3."""
    assert _third_party(EMITTER, set()) == set()
