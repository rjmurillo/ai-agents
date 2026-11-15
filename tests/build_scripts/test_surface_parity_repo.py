"""The live repository must satisfy its own surface parity manifest (issue #5637).

``test_check_surface_parity.py`` proves the checker on synthetic trees. These
tests hold the real ``templates/platforms/surface-parity.yaml`` to the real
tree, and guard the manifest against silent weakening.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import build_all  # noqa: E402
import check_surface_parity as csp  # noqa: E402
import surface_manifest as sm  # noqa: E402

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
STALENESS_WORKFLOW = WORKFLOWS / "validate-generated-agents.yml"
DRIFT_WORKFLOW = WORKFLOWS / "agent-drift-detection.yml"
GENERATE_VALIDATE = "build/generate_agents.py --validate"
BUILD_ALL_CHECK = "build/scripts/build_all.py --check"

# Hand-maintained copies no generator writes. Losing either row would let a stale
# runtime copy ship while every generator-owned check stays green.
HAND_MAINTAINED = {
    "lib-copilot-modules",
    "lib-claude-dispatch-copies",
}
# Deleting this row leaves its files under the independent parent row
# `lib-claude-plugin`, which accepts any file, so the gate cannot go red. The
# row's presence is pinned by `test_hand_maintained_surfaces_are_declared`.
ROW_DELETION_CANNOT_GO_RED = {"lib-claude-dispatch-copies"}


@pytest.fixture(scope="module")
def manifest() -> sm.Manifest:
    loaded = sm.load_manifest(REPO_ROOT)
    assert loaded is not None, f"{sm.MANIFEST_REL} is missing"
    return loaded


@pytest.fixture(scope="module")
def files() -> list[str]:
    return sm.list_files(REPO_ROOT)


@pytest.fixture(scope="module")
def rooted_files(manifest: sm.Manifest, files: list[str]) -> list[str]:
    """Files under a manifest root, the only ones ``check_classification`` reads.

    This repeats the root guard at the top of ``check_classification`` in
    build/scripts/check_surface_parity.py. Deleting a surface row leaves
    ``roots`` unchanged, so one filter serves every weakened manifest.
    """
    return [f for f in files if any(sm.rel_to(f, root) is not None for root in manifest.roots)]


def any_finding(manifest: sm.Manifest, files: list[str], rooted_files: list[str]) -> bool:
    """True when a ``run_checks`` check other than import closure reports a finding.

    Each deletion case needs only one finding. The classification scan over the
    real tree is the costliest check here, so it runs last, and the first
    non-empty check ends the call. This keeps the parametrized cases inside the
    slow-test budget in pyproject.toml.
    """
    checks = (
        lambda: csp.check_declarations(REPO_ROOT, manifest),
        lambda: csp.check_inventory(REPO_ROOT, manifest, build_all.OWNED_PREFIXES),
        lambda: csp.check_hand_maintained(REPO_ROOT, manifest, files),
        lambda: csp.check_classification(manifest, rooted_files),
    )
    return any(check() for check in checks)


def test_every_shipped_surface_holds(capsys: pytest.CaptureFixture[str]) -> None:
    """``build_all.py --check`` runs the manifest gate, and the real tree passes it.

    One call covers both claims: with no stale paths, the exit is 0 exactly when
    ``run_checks`` finds nothing. The import-closure scan inside it costs several
    seconds, so a second test of the same gate would double that cost.
    """
    rc = build_all._surface_parity_exit(REPO_ROOT, [])

    assert rc == 0, capsys.readouterr().err


# `mirrored` went unused when the security sidecar copies were retired. The
# lib/paths.py byte copies into the Codex, Cursor, and Muse trees (issue #7221)
# use it again, so the live manifest must use every relation in the vocabulary.
def test_manifest_distinguishes_every_live_relation(manifest: sm.Manifest) -> None:
    assert {s.relation for s in manifest.surfaces} == sm.RELATIONS


def test_hand_maintained_surfaces_are_declared(manifest: sm.Manifest) -> None:
    hand = {s.id for s in manifest.surfaces if s.hand_maintained}
    assert HAND_MAINTAINED <= hand


def test_every_independent_surface_states_why(manifest: sm.Manifest) -> None:
    bare = [s.id for s in manifest.surfaces if s.relation == "independent" and not s.reason]
    assert bare == []


def test_every_checked_surface_names_its_validation_owner(manifest: sm.Manifest) -> None:
    unowned = [s.id for s in manifest.surfaces if s.relation != "independent" and not s.owner]
    assert unowned == []


def non_independent_ids() -> list[str]:
    loaded = sm.load_manifest(REPO_ROOT)
    assert loaded is not None
    return [s.id for s in loaded.surfaces if s.relation != "independent"]


@pytest.mark.parametrize(
    "surface_id", [i for i in non_independent_ids() if i not in ROW_DELETION_CANNOT_GO_RED]
)
def test_deleting_a_surface_row_fails_the_gate(
    manifest: sm.Manifest, files: list[str], rooted_files: list[str], surface_id: str
) -> None:
    """A weakened manifest must go red, not quiet."""
    weakened = dataclasses.replace(
        manifest, surfaces=tuple(s for s in manifest.surfaces if s.id != surface_id)
    )
    assert any_finding(weakened, files, rooted_files)


def test_editing_a_hand_maintained_copy_fails_with_the_file_named(
    manifest: sm.Manifest, files: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    target = "src/copilot-cli/lib/shim_loader.py"
    original = (REPO_ROOT / target).read_bytes()
    real_read = Path.read_bytes

    def read(self: Path) -> bytes:
        return original + b"# drift\n" if self == REPO_ROOT / target else real_read(self)

    monkeypatch.setattr(Path, "read_bytes", read)
    found = csp.check_hand_maintained(REPO_ROOT, manifest, files)
    assert [(f.kind, f.path) for f in found] == [("STALE", target)]


def test_manifest_is_not_a_platform_config() -> None:
    assert build_all._is_platform_config(REPO_ROOT / sm.MANIFEST_REL) is False


def codeowner_patterns() -> list[str]:
    lines = (REPO_ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8").splitlines()
    return [ln.split()[0] for ln in lines if ln.strip() and not ln.startswith("#")]


@pytest.mark.parametrize(
    "protected",
    [
        sm.MANIFEST_REL,
        "build/scripts/check_surface_parity.py",
        "build/scripts/surface_manifest.py",
        "build/scripts/build_all.py",
        "tests/build_scripts/test_check_surface_parity.py",
        "tests/build_scripts/test_check_surface_parity_inventory.py",
        "tests/build_scripts/test_surface_parity_repo.py",
    ],
)
def test_code_owners_protect_the_manifest_and_its_gate(protected: str) -> None:
    """A CODEOWNERS pattern must cover each file that can weaken the gate."""
    covered = any(re.fullmatch(_glob(pattern), "/" + protected) for pattern in codeowner_patterns())
    assert covered, f"no CODEOWNERS entry covers {protected}"


def _glob(pattern: str) -> str:
    """Translate the CODEOWNERS subset this repo uses: anchored paths, dir/ and ** prefixes."""
    body = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return body + ".*" if pattern.endswith("/") else body


def load_workflow(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def step_commands(workflow: dict[str, Any]) -> list[str]:
    return [
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]


def test_ci_runs_the_manifest_gate_through_build_all() -> None:
    commands = step_commands(load_workflow(STALENESS_WORKFLOW))
    assert any(BUILD_ALL_CHECK in c for c in commands)


def test_agent_drift_detection_keeps_its_own_purpose() -> None:
    """The standalone validate stays where the failure diff and job summary live."""
    commands = step_commands(load_workflow(DRIFT_WORKFLOW))
    assert any(GENERATE_VALIDATE in c for c in commands)
    text = DRIFT_WORKFLOW.read_text(encoding="utf-8")
    assert "show_drift_failure.py" in text
    assert "write_drift_job_summary.py" in text


def test_staleness_workflow_does_not_repeat_the_agent_validate() -> None:
    """build_all.py --check already runs generate_agents; the standalone step is a duplicate."""
    commands = step_commands(load_workflow(STALENESS_WORKFLOW))
    assert not any(GENERATE_VALIDATE in c for c in commands)


def test_a_real_file_under_a_binplaced_surface_with_no_authority_is_extra(
    manifest: sm.Manifest, files: list[str]
) -> None:
    """Negative control: a repo-only instruction not claimed by its own row fails."""
    stray = ".github/instructions/not-shipped.instructions.md"
    found = csp.check_hand_maintained(REPO_ROOT, manifest, [*files, stray])
    assert [(f.kind, f.path) for f in found] == [("EXTRA", stray)]
