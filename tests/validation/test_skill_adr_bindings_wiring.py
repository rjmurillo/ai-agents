"""Wiring tests for the skill ADR bindings gate (issue #5665).

The gate's own behavior is covered in `test_check_skill_adr_bindings.py`. This
file proves the two things those tests structurally cannot: that `pre_pr` reaches
the gate at all, and that the adapter converts each exit code into the right
boolean.

`.claude/rules/testing.md` SHOULD 6 is the reason this file exists separately. A
guard can pass every one of its own tests while no consumer is wired to it, and
unit tests on the guard cannot observe that. Evidence cited there: a guard written
for issue #4244 passed nine mutations against its own tests while one of three
consumers never called it, and `check_skill_md_portability.py` shipped without
calling its guard while the guard's unit tests stayed green.

Per SHOULD 6 the consumer is driven twice over the same repository, differing only
in the condition the gate rejects, so a run that fails for an unrelated reason
fails its own control too.

The registration assertion reads the parsed `_SEQUENCE` tuple and compares
callables by identity, never a substring of the module source. `testing.md` MUST 9
is explicit that a substring check passes when the row has been deleted and the
name survives in a comment or a neighbouring key, which is exactly the mistake a
"is the gate wired" test invites.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_skill_adr_bindings import (
    CHECK,
    EXIT_OK,
    EXIT_REGRESSION,
    main,
    validate_skill_adr_bindings,
)


def _git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run git in ``repo`` with every GIT_* variable stripped.

    The gate strips them too, through `count_ratchet.git_environment`. An
    inherited `GIT_DIR`, which `git push` exports into the pre-push hook from a
    linked worktree, would otherwise point both at the wrong index (issue #4914).
    """
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        check=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    )


def _repo_with(tmp_path: Path, *, retired_skills: int) -> Path:
    """A git repo root with one superseded ADR and ``retired_skills`` skills naming it.

    The skills are staged, not merely written: the gate enumerates candidate
    paths from the index, so an unstaged fixture would be counted as zero and
    both cases below would agree for the wrong reason.
    """
    _git(tmp_path, "init", "--quiet")
    adr_dir = tmp_path / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-002-gone.md").write_text(
        "---\nid: ADR-002\nstatus: superseded\n---\n\n# ADR-002\n", encoding="utf-8"
    )
    for index in range(retired_skills):
        skill_dir = tmp_path / "skills" / f"s{index}"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: s\nmetadata:\n  adr: ADR-002\n---\n\n# s\n", encoding="utf-8"
        )
        rel = f"skills/s{index}/SKILL.md"
        _git(tmp_path, "add", "--force", "--", rel)
        assert rel in _git(tmp_path, "ls-files", "--", rel).stdout, f"{rel} unstaged"
    return tmp_path


def _baseline(tmp_path: Path, count: int) -> Path:
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps({"schema_version": "1", "counts": {CHECK: count}}) + "\n",
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------
# Registration: the consumer reaches the gate
# --------------------------------------------------------------------------


def test_gate_is_registered_in_the_pre_pr_sequence() -> None:
    """Compares callables by identity against the parsed sequence, per MUST 9."""
    from pre_pr_sequence import _SEQUENCE

    wired = [gate for gate in _SEQUENCE if "Skill ADR Bindings" in gate.name]
    assert len(wired) == 1, "exactly one row should run this gate"


def test_pre_pr_facade_reexports_the_adapter() -> None:
    """The two sibling ADR gates are re-exported so
    `from scripts.validation.pre_pr import <adapter>` resolves; PR #5209 shows
    what breaks when a newly wired gate skips this line."""
    from pre_pr import validate_skill_adr_bindings as reexported

    assert reexported is validate_skill_adr_bindings


# --------------------------------------------------------------------------
# Propagation: each exit code becomes the right boolean
# --------------------------------------------------------------------------


def test_adapter_is_true_when_at_baseline(tmp_path: Path) -> None:
    """Control for the regression case below: same repo, satisfied ceiling.

    Paired with `test_adapter_is_false_when_above_baseline`, which differs only
    in the violation count. If this control ever fails, the discriminating test
    below proves nothing, which is the trap SHOULD 6 names.
    """
    repo = _repo_with(tmp_path, retired_skills=1)
    assert (
        main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, 1))])
        == EXIT_OK
    )


def test_adapter_is_false_when_above_baseline(tmp_path: Path) -> None:
    """The discriminating half of the pair: only the violation count differs."""
    repo = _repo_with(tmp_path, retired_skills=2)
    assert (
        main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, 1))])
        == EXIT_REGRESSION
    )


def test_adapter_is_false_on_an_unrun_gate(tmp_path: Path) -> None:
    """A gate that could not run must not be scored as a pass. `ci-scripts.md`
    MUST 11 and 12 are the reason: a config fault that returns True is
    indistinguishable from a clean tree."""
    assert validate_skill_adr_bindings(tmp_path / "no-such-repo") is False


def test_the_shipped_baseline_matches_the_tracked_tree() -> None:
    """Pins the committed ceiling against a live measurement, the same invariant
    `test_baseline_ratchet_integrity.py` holds for the other ratchets. A baseline
    that drifts above the tree leaves slack for the next regression to pass in
    silently."""
    import check_skill_adr_bindings as mod

    repo_root = Path(__file__).resolve().parents[2]
    violations = mod.scan(repo_root, repo_root / ".agents" / "architecture")
    assert isinstance(violations, list), (
        f"scan reported a fault, so the count below would measure a string: "
        f"{violations!r}"
    )
    baseline = mod.read_baseline(mod._BASELINE_PATH)
    assert isinstance(baseline, dict), f"shipped baseline is unusable: {baseline}"
    assert baseline[CHECK] == len(violations), (
        f"shipped baseline is {baseline[CHECK]} but the tree has "
        f"{len(violations)}; lower it with --write-baseline"
    )
