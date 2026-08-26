"""A baseline rewrite must be refused whenever it would drop what the old one holds.

Scan coverage asks whether the tree was fully read. These tests ask the later
question: given that the tree read, is the artifact about to be written a
regression against the artifact it replaces? Four separate ways of lying to git
all reached exit 0 before this guard existed, each dropping entries a previous
baseline recorded:

* ``git add -N`` lists a path as tracked while holding none of its content, so
  a starved root reported one tracked file and passed a per-root check.
* A directory occupying a tracked file path satisfies ``Path.exists()`` while
  both scanners skip it, so the file left the baseline with the root still read.
* An unmerged index lists conflicted paths several times and leaves markers on
  disk, so half-merged content was recorded as the truth.
* ``GIT_INDEX_FILE`` points git at an index built to match a truncated disk, so
  the tree it describes is not the tree that ships.

Enumerating tricks is unbounded. All four converge on one observable, the new
baseline records fewer entries than the old one, so the shrink guard covers the
shapes not yet imagined and the four direct fixes are defense in depth.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validation import check_skill_md_exec_portability as cep
from scripts.validation import check_skill_md_portability as cmp
from scripts.validation.portability_common import (
    refuse_dropped_entries,
    tracked_coverage_by_root,
)

ROOT_NAMES = (".claude/skills", "src/copilot-cli/skills")
SKILLS = ("alpha", "beta", "gamma")

# Counted by both ratchets: the prose line is an upstream-tree reference and the
# fenced line is a bare exec invocation. A fixture neither checker records makes
# every "the baseline did not change" assertion below vacuously true.
SKILL_BODY = (
    "---\nname: {name}\n---\nSee scripts/validation/x.py for detail.\n\n"
    "```bash\npython3 .claude/skills/x/scripts/y.py\n```\n"
)


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        env=env,
    )


def _populate(root: Path) -> None:
    for name in ROOT_NAMES:
        for skill in SKILLS:
            skill_dir = root / name / skill
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(SKILL_BODY.format(name=skill), encoding="utf-8")
    # check_skill_md_portability requires src/copilot-cli/instructions to exist
    # and hold at least one readable file (issue #5214); a clean file (no
    # upstream refs) keeps the "6 recorded files" assumption elsewhere in this
    # module intact, since it contributes 0 to the files dict.
    instructions_dir = root / "src" / "copilot-cli" / "instructions"
    instructions_dir.mkdir(parents=True, exist_ok=True)
    (instructions_dir / "x.instructions.md").write_text(
        "Clean prose with no upstream refs.\n", encoding="utf-8"
    )


def _repo(root: Path) -> None:
    _populate(root)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--allow-empty", "-m", "seed")


def _seed_baseline(root: Path, module: ModuleType) -> tuple[Path, bytes, int]:
    """Write a real baseline from the healthy tree and return it with its size."""
    baseline = root / "baseline.json"
    argv = ["--repo-root", str(root), "--baseline", "baseline.json", "--update-baseline"]
    assert module.main(argv) == 0
    recorded = json.loads(baseline.read_text(encoding="utf-8"))["files"]
    assert recorded, "fixture records nothing, so a dropped entry would be unobservable"
    return baseline, baseline.read_bytes(), len(recorded)


def _update(root: Path, module: ModuleType, *extra: str) -> int:
    return module.main(
        ["--repo-root", str(root), "--baseline", "baseline.json", "--update-baseline", *extra]
    )


class TestIntentToAddIsNotCoverage:
    """``git ls-files`` lists an intent-to-add path while git holds no content for it."""

    @pytest.mark.parametrize("module", [cmp, cep])
    def test_intent_to_add_does_not_make_a_starved_root_look_tracked(
        self, tmp_path: Path, module: ModuleType
    ) -> None:
        _repo(tmp_path)
        baseline, before, count = _seed_baseline(tmp_path, module)
        starved = tmp_path / ROOT_NAMES[1]
        for skill in SKILLS:
            (starved / skill / "SKILL.md").unlink()
        _git(tmp_path, "rm", "-r", "-q", "--cached", "--", ROOT_NAMES[1])
        decoy = starved / "decoy"
        decoy.mkdir(parents=True, exist_ok=True)
        (decoy / "SKILL.md").write_text(SKILL_BODY.format(name="decoy"), encoding="utf-8")
        _git(tmp_path, "add", "-N", "--", f"{ROOT_NAMES[1]}/decoy/SKILL.md")

        assert count > 0
        assert _update(tmp_path, module) == 2
        assert baseline.read_bytes() == before


class TestTypeSubstitution:
    """A directory at a tracked file path exists, and neither scanner can read it."""

    @pytest.mark.parametrize("module", [cmp, cep])
    def test_directory_standing_in_for_a_tracked_file_is_missing_content(
        self, tmp_path: Path, module: ModuleType
    ) -> None:
        _repo(tmp_path)
        baseline, before, _ = _seed_baseline(tmp_path, module)
        # Only one of three, so the root still reads and a coverage check passes.
        victim = tmp_path / ROOT_NAMES[1] / "alpha" / "SKILL.md"
        victim.unlink()
        victim.mkdir()

        assert _update(tmp_path, module) == 2
        assert baseline.read_bytes() == before


class TestUnresolvedConflicts:
    """Half-merged content is neither side's truth, so it is not a baseline."""

    @pytest.mark.parametrize("module", [cmp, cep])
    def test_unmerged_index_refuses_before_recording_conflict_markers(
        self, tmp_path: Path, module: ModuleType
    ) -> None:
        _repo(tmp_path)
        baseline, before, _ = _seed_baseline(tmp_path, module)
        target = tmp_path / ROOT_NAMES[0] / "alpha" / "SKILL.md"
        _git(tmp_path, "checkout", "-q", "-b", "side")
        target.write_text(SKILL_BODY.format(name="side") + "\n```bash\nbash a.sh\n```\n", "utf-8")
        _git(tmp_path, "commit", "-qam", "side")
        _git(tmp_path, "checkout", "-q", "main")
        target.write_text(SKILL_BODY.format(name="main"), encoding="utf-8")
        _git(tmp_path, "commit", "-qam", "main")
        merge = subprocess.run(
            [
                "git",
                "-C",
                str(tmp_path),
                "-c",
                "user.email=t@t",
                "-c",
                "user.name=t",
                "merge",
                "side",
            ],
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
        assert merge.returncode != 0, "fixture failed to produce a conflict"
        unmerged = subprocess.run(
            ["git", "-C", str(tmp_path), "ls-files", "-u"],
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
        assert unmerged.stdout, f"merge failed before producing a conflict: {merge.stderr}"

        assert _update(tmp_path, module) == 2
        assert baseline.read_bytes() == before


class TestIndexEnvironmentIsNotTrusted:
    """An inherited ``GIT_INDEX_FILE`` describes a tree other than the one shipping."""

    @pytest.mark.parametrize("module", [cmp, cep])
    def test_alternate_index_matching_a_truncated_disk_is_ignored(
        self, tmp_path: Path, module: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _repo(tmp_path)
        baseline, before, _ = _seed_baseline(tmp_path, module)
        for skill in ("beta", "gamma"):
            (tmp_path / ROOT_NAMES[1] / skill / "SKILL.md").unlink()
        alternate = tmp_path / ".git" / "alternate-index"
        _git(tmp_path, "add", "-A", env={"GIT_INDEX_FILE": str(alternate), "PATH": "/usr/bin:/bin"})
        monkeypatch.setenv("GIT_INDEX_FILE", str(alternate))

        assert _update(tmp_path, module) == 2
        assert baseline.read_bytes() == before


class TestDroppedEntryGuard:
    """The bounded rule: refuse any rewrite that records less than its predecessor."""

    @pytest.mark.parametrize(
        ("module", "marker"),
        [
            (cmp, "<!-- vendor-portability: test fixture -->"),
            (cep, "<!-- vendor-portability-exec: test fixture -->"),
        ],
    )
    def test_marker_entry_drop_also_needs_the_shrink_to_be_declared(
        self, tmp_path: Path, module: ModuleType, marker: str
    ) -> None:
        _repo(tmp_path)
        target = tmp_path / ROOT_NAMES[1] / "alpha" / "SKILL.md"
        target.write_text(f"{marker}\n{SKILL_BODY.format(name='alpha')}", encoding="utf-8")
        _git(tmp_path, "commit", "-qam", "add marker")
        baseline, before, _ = _seed_baseline(tmp_path, module)
        seeded = json.loads(baseline.read_text(encoding="utf-8"))
        assert seeded["marker_files"], "fixture records no marker entry to protect"

        target.write_text(SKILL_BODY.format(name="alpha"), encoding="utf-8")

        assert _update(tmp_path, module) == 2
        assert baseline.read_bytes() == before

        assert _update(tmp_path, module, "--allow-baseline-shrink") == 0
        after = json.loads(baseline.read_text(encoding="utf-8"))
        assert after["marker_files"] == {}

    @pytest.mark.parametrize("module", [cmp, cep])
    def test_committed_deletion_still_needs_the_shrink_to_be_declared(
        self, tmp_path: Path, module: ModuleType
    ) -> None:
        """Git agrees the tree is whole here, so only the artifact comparison objects."""
        _repo(tmp_path)
        baseline, before, count = _seed_baseline(tmp_path, module)
        for skill in ("beta", "gamma"):
            (tmp_path / ROOT_NAMES[1] / skill / "SKILL.md").unlink()
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-qm", "drop two")

        assert _update(tmp_path, module) == 2
        assert baseline.read_bytes() == before

        assert _update(tmp_path, module, "--allow-baseline-shrink") == 0
        after = json.loads(baseline.read_text(encoding="utf-8"))["files"]
        assert len(after) == count - 2

    @pytest.mark.parametrize("module", [cmp, cep])
    def test_staging_the_deletion_is_no_longer_enough_to_permit_it(
        self, tmp_path: Path, module: ModuleType
    ) -> None:
        """`git add -A` used to relabel an accidental wipe as intentional.

        The root keeps a readable file, so every coverage layer is satisfied and
        git agrees the tree matches its index. Only the artifact comparison is
        left to object, and the removal now has to be named rather than staged.
        """
        _repo(tmp_path)
        baseline, before, _ = _seed_baseline(tmp_path, module)
        for skill in ("beta", "gamma"):
            (tmp_path / ROOT_NAMES[1] / skill / "SKILL.md").unlink()
        _git(tmp_path, "add", "-A")

        assert _update(tmp_path, module) == 2
        assert baseline.read_bytes() == before

    @pytest.mark.parametrize("module", [cmp, cep])
    def test_a_declared_root_leaving_disk_and_index_is_still_refused(
        self, tmp_path: Path, module: ModuleType
    ) -> None:
        """A root absent from disk is never enumerated, so no coverage layer asks."""
        _repo(tmp_path)
        baseline, before, _ = _seed_baseline(tmp_path, module)
        _git(tmp_path, "rm", "-r", "-q", "--cached", "--", ROOT_NAMES[1])
        shutil.rmtree(tmp_path / ROOT_NAMES[1])
        _git(tmp_path, "commit", "-qm", "root leaves the tree")

        assert _update(tmp_path, module) == 2
        assert baseline.read_bytes() == before

    def test_a_first_write_has_no_predecessor_to_regress_against(self) -> None:
        assert refuse_dropped_entries(None, {"files": {"a": 1}}, "skill files", False) is False

    def test_growth_and_recount_are_not_a_drop(self) -> None:
        previous = {"files": {"a": 1, "b": 2}}
        current = {"files": {"a": 9, "b": 2, "c": 1}}
        assert refuse_dropped_entries(previous, current, "u", False) is False

    def test_a_dropped_entry_is_refused_and_named(self, capsys: pytest.CaptureFixture[str]) -> None:
        previous = {"files": {"a": 1, "b": 2}}
        assert refuse_dropped_entries(previous, {"files": {"a": 1}}, "skill files", False) is True
        assert "b" in capsys.readouterr().err

    def test_the_escape_hatch_is_explicit(self) -> None:
        previous = {"files": {"a": 1, "b": 2}}
        assert refuse_dropped_entries(previous, {"files": {"a": 1}}, "skill files", True) is False


class TestCoverageMechanics:
    """Isolate each defense from the shrink guard, which would otherwise mask it.

    Every hostile tree below also shrinks the baseline, so an end-to-end exit
    code cannot say which rule fired. These assert on the coverage numbers, so
    removing one defense changes an answer here even while the write stays
    refused for the other reason.
    """

    def test_intent_to_add_entries_are_not_counted_as_tracked(self, tmp_path: Path) -> None:
        _repo(tmp_path)
        extra = tmp_path / ROOT_NAMES[1] / "decoy"
        extra.mkdir(parents=True)
        (extra / "SKILL.md").write_text(SKILL_BODY.format(name="decoy"), encoding="utf-8")
        _git(tmp_path, "add", "-N", "--", f"{ROOT_NAMES[1]}/decoy/SKILL.md")
        coverage = tracked_coverage_by_root(tmp_path, ROOT_NAMES)
        assert coverage is not None
        assert coverage[ROOT_NAMES[1]] == (len(SKILLS), 0), "intent-to-add inflated the count"

    def test_a_directory_at_a_tracked_path_counts_as_missing(self, tmp_path: Path) -> None:
        _repo(tmp_path)
        victim = tmp_path / ROOT_NAMES[1] / "alpha" / "SKILL.md"
        victim.unlink()
        victim.mkdir()
        coverage = tracked_coverage_by_root(tmp_path, ROOT_NAMES)
        assert coverage is not None
        assert coverage[ROOT_NAMES[1]] == (len(SKILLS), 1)

    def test_an_inherited_index_pointer_does_not_reach_git(self, tmp_path: Path) -> None:
        _repo(tmp_path)
        for skill in ("beta", "gamma"):
            (tmp_path / ROOT_NAMES[1] / skill / "SKILL.md").unlink()
        alternate = tmp_path / ".git" / "alternate-index"
        _git(tmp_path, "add", "-A", env={"GIT_INDEX_FILE": str(alternate), "PATH": "/usr/bin:/bin"})
        import os

        os.environ["GIT_INDEX_FILE"] = str(alternate)
        try:
            coverage = tracked_coverage_by_root(tmp_path, ROOT_NAMES)
        finally:
            del os.environ["GIT_INDEX_FILE"]
        assert coverage is not None
        assert coverage[ROOT_NAMES[1]] == (len(SKILLS), 2), "the alternate index was believed"


class TestHealthyTreeStillWrites:
    """The false-positive control: none of the above may block an honest rewrite."""

    @pytest.mark.parametrize("module", [cmp, cep])
    def test_a_whole_repository_writes_and_exits_zero(
        self, tmp_path: Path, module: ModuleType
    ) -> None:
        _repo(tmp_path)
        baseline, _, count = _seed_baseline(tmp_path, module)
        assert count == len(ROOT_NAMES) * len(SKILLS)
        assert _update(tmp_path, module) == 0
        assert len(json.loads(baseline.read_text(encoding="utf-8"))["files"]) == count
