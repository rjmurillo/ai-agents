"""Every count ratchet's merge-tree declaration, pinned against the registry.

``count_ratchet.run`` waives the baseline-above-base comparison for a branch
that never moved the number, on the grounds that
``scripts/ci/merge_tree_ratchet_check.py`` measures the merged result instead.
That trade is only sound for a ratchet the merge-tree gate actually evaluates,
and the gate evaluates exactly
``scripts/ci/merge_tree_ratchet_registry.py::RATCHETS``.

Nothing structural connects a ratchet module's ``MERGE_TREE_BACKED`` literal to
that tuple, so this module is the connection. Issue #5065's first cut waived the
comparison unconditionally and turned off the only stale-branch guard the
subprocess-encoding ratchet had.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.ci import (
    cli_exit_contract_ratchet,
    count_ratchet,
    memory_index_count_ratchet,
    ruff_count_ratchet,
    subprocess_encoding_count_ratchet,
    taste_count_ratchet,
    type_ignore_count_ratchet,
)
from scripts.ci.merge_tree_ratchet_registry import RATCHETS
from tests.ci.count_ratchet_git_harness import FakeCounter, commit_all, init_repo

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_DIR = REPO_ROOT / "scripts" / "ci"

# Every module under scripts/ci that owns a *_baseline.txt and drives
# count_ratchet.run. Kept as an explicit tuple so a module dropped from the
# import list fails the inventory test below rather than vanishing silently.
RATCHET_MODULES = (
    cli_exit_contract_ratchet,
    memory_index_count_ratchet,
    ruff_count_ratchet,
    subprocess_encoding_count_ratchet,
    taste_count_ratchet,
    type_ignore_count_ratchet,
)


def _registered_baseline_names() -> set[str]:
    return {Path(ratchet.baseline_path).name for ratchet in RATCHETS}


def test_every_ci_baseline_file_has_exactly_one_ratchet_module() -> None:
    """The inventory is total: no baseline without a module, no module without one.

    A new ratchet that ships its baseline but is missed here would leave the
    declaration test below blind to it, which is the shape that let the
    subprocess-encoding ratchet sit outside the registry unnoticed.
    """
    on_disk = {path.name for path in CI_DIR.glob("*_baseline.txt")}
    declared = {module._BASELINE_PATH.name for module in RATCHET_MODULES}

    assert on_disk == declared, (
        f"scripts/ci baseline files and ratchet modules disagree: "
        f"only on disk {sorted(on_disk - declared)}, "
        f"only in modules {sorted(declared - on_disk)}"
    )


def test_every_registry_baseline_belongs_to_a_known_module() -> None:
    """The registry may not name a baseline no module in the inventory owns."""
    declared = {module._BASELINE_PATH.name for module in RATCHET_MODULES}

    assert _registered_baseline_names() <= declared, (
        f"merge_tree_ratchet_registry names baselines no ratchet module owns: "
        f"{sorted(_registered_baseline_names() - declared)}"
    )


@pytest.mark.parametrize(
    "module", RATCHET_MODULES, ids=lambda module: module.__name__.rsplit(".", 1)[-1]
)
def test_merge_tree_backed_matches_registry_membership(module) -> None:
    """A ratchet may claim the waiver only if the merge-tree gate covers it."""
    registered = module._BASELINE_PATH.name in _registered_baseline_names()

    assert module.MERGE_TREE_BACKED is registered, (
        f"{module.__name__} declares MERGE_TREE_BACKED="
        f"{module.MERGE_TREE_BACKED} but its baseline "
        f"{module._BASELINE_PATH.name} is "
        f"{'in' if registered else 'absent from'} "
        f"merge_tree_ratchet_registry.py::RATCHETS. Either register the "
        f"baseline or flip the declaration; the waiver in "
        f"count_ratchet._base_ref_verdict is only sound for a registered one."
    )


@pytest.mark.parametrize(
    "module", RATCHET_MODULES, ids=lambda module: module.__name__.rsplit(".", 1)[-1]
)
def test_main_forwards_merge_tree_backing_declaration(module, monkeypatch) -> None:
    """Each ratchet CLI must pass its declaration to the shared runner."""
    forwarded: dict[str, object] = {}

    def capture_run(_args, **kwargs) -> int:
        forwarded.update(kwargs)
        return count_ratchet.EXIT_OK

    monkeypatch.setattr(module, "run", capture_run)

    assert module.main([]) == count_ratchet.EXIT_OK
    assert forwarded["merge_tree_backed"] is module.MERGE_TREE_BACKED


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True)


def _stale_branch_with_four_violations(tmp_path: Path) -> tuple[Path, Path]:
    """A repo reproducing the hole: fork 4, main 0, tree measures 4.

    Mirrors the shipped shape at a size a test can carry: on 2026-08-27
    ``scripts/ci/subprocess_encoding_count_baseline.txt`` recorded 238 against a
    tracked tree of 236, inside ``MAX_BASELINE_SLACK``. A branch cut before main
    trues that up can add violations up to the stale ceiling and land above the
    current one.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    baseline = repo / "subprocess_encoding_count_baseline.txt"
    baseline.write_text("4\n", encoding="utf-8")
    (repo / "clean.py").write_text("import subprocess\n", encoding="utf-8")
    commit_all(repo, "main: baseline=4")

    _git(repo, "checkout", "-q", "-b", "truing-up")
    baseline.write_text("0\n", encoding="utf-8")
    commit_all(repo, "main: lower baseline to 0")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--ff-only", "truing-up")

    _git(repo, "checkout", "-q", "-b", "stale", "main~1")
    # The checker flags a literal UTF-8 decode with capture and no errors=;
    # a bare text=True with no capture is not a violation, so it cannot stand
    # in here. Probed against find_all_violations before this test was written.
    call = 'subprocess.run(["cmd{index}"], encoding="utf-8", capture_output=True)\n'
    (repo / "added.py").write_text(
        "import subprocess\n\n\n"
        + "".join(call.format(index=index) for index in range(4)),
        encoding="utf-8",
    )
    commit_all(repo, "stale: four utf-8 captures with no errors=")
    return repo, baseline


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_the_unbacked_ratchet_blocks_a_stale_branch_with_slack(tmp_path, capsys) -> None:
    """Drives the real unbacked CLI, not the taste label, and must not exit 0.

    The branch never edited the baseline, so the fork-point read reports
    ``unchanged`` and the waiver would fire. It must not: nothing else measures
    the merged result for this ratchet, so the four added violations would land
    above main's trued-up ceiling and redden every later push on main.
    """
    repo, baseline = _stale_branch_with_four_violations(tmp_path)
    assert subprocess_encoding_count_ratchet.current_count(repo) == 4

    rc = subprocess_encoding_count_ratchet.main(
        [
            "--repo-root",
            str(repo),
            "--baseline",
            str(baseline),
            "--base-ref",
            "main",
        ]
    )

    assert rc != count_ratchet.EXIT_OK
    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "BEHIND BASE" in err
    assert "NOT registered" in err


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_the_same_topology_passes_for_a_backed_ratchet(tmp_path, capsys) -> None:
    """Discrimination probe: the declaration alone flips the verdict.

    Same repository, same numbers, same fork point. Only ``merge_tree_backed``
    differs, so a test that passed for an unrelated reason would fail here too.
    """
    repo, baseline = _stale_branch_with_four_violations(tmp_path)
    args = count_ratchet.build_parser("ratchet", baseline).parse_args(
        ["--repo-root", str(repo), "--baseline", str(baseline), "--base-ref", "main"]
    )

    rc = count_ratchet.run(
        args,
        label="ratchet",
        counter=FakeCounter(4),
        scan_error="scan failed",
        regression_advice="fix them.",
        merge_tree_backed=True,
    )

    assert rc == count_ratchet.EXIT_OK
    assert "BEHIND BASE (not blocking)" in capsys.readouterr().out
