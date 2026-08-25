# taste-lint: ignore file-size
# Shared portability coverage and escape cases stay on one fixture matrix.
"""Both portability ratchets must refuse a baseline written from a partial scan.

The hazard is shared, so the tests live together rather than split across the
two checkers' own modules. A scan root can exist and still yield nothing to
read: a partial checkout, a sparse clone, a mistargeted repo root. The
offending-file mapping is empty in that case and equally empty for a genuinely
clean tree, so counts alone cannot separate them.

Coverage is per root, never a sum. Both checkers ship two roots, so a total
stays positive while one of them reads nothing. Emptying only
``src/copilot-cli/skills`` on a real checkout drove the markdown baseline from
73 files to 34 and the exec baseline from 170 to 84, both at exit 0. Every
refusal test below therefore populates one root and starves the other, and the
false-positive control populates every root with several files so that it
cannot be mistaken for the partial checkout it has to stay distinct from.
"""

from __future__ import annotations

import json
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
from scripts.validation import portability_common as common
from scripts.validation.portability_common import (
    refuse_uncovered_scan,
    tracked_coverage_by_root,
)

ROOT_NAMES = (".claude/skills", "src/copilot-cli/skills")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _commit_tree(root: Path) -> None:
    """Make the fixture a repository, so coverage is decided the way it is in CI."""
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(
        root, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-q", "--allow-empty", "-m", "seed",
    )


class TestRefuseUncoveredScanHelper:
    """The shared decision, tested directly rather than only through callers."""

    def test_every_root_read_permits(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        for name in ROOT_NAMES:
            (tmp_path / name).mkdir(parents=True)
            (tmp_path / name / "SKILL.md").write_text("x\n", encoding="utf-8")
        _commit_tree(tmp_path)
        counts = dict.fromkeys(ROOT_NAMES, 3)
        assert refuse_uncovered_scan(tmp_path, counts, "skill files") is False
        assert capsys.readouterr().err == ""

    def test_one_unread_root_among_several_refuses(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """A sum would stay positive here. Coverage is what has to fail."""
        assert refuse_uncovered_scan(tmp_path, {"a": 84, "b": 0}, "skill files") is True
        assert "read 0 skill files under: b" in capsys.readouterr().err

    def test_all_roots_unread_refuses(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        assert refuse_uncovered_scan(tmp_path, {"a": 0, "b": 0}, "skill files") is True
        assert "none" in capsys.readouterr().err

    def test_no_roots_at_all_refuses(self, tmp_path: Path) -> None:
        """An empty mapping means nothing was enumerated, which is not coverage."""
        assert refuse_uncovered_scan(tmp_path, {}, "skill files") is True

    def test_refusal_names_the_roots_that_were_read(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Naming both sides is what tells an operator it was partial, not empty."""
        refuse_uncovered_scan(tmp_path, {"kept": 12, "lost": 0}, "skill .md files")
        err = capsys.readouterr().err
        assert "under: lost" in err
        assert "kept (12)" in err


class TestMarkdownCheckerCoverage:
    def _roots(self, root: Path, populated: tuple[str, ...] = ()) -> None:
        """Create every required root, then seed only the named ones."""
        for name in sorted(cmp.REQUIRED_SKILLS_ROOTS):
            skills = root / name / "skills"
            skills.mkdir(parents=True, exist_ok=True)
            if name not in populated:
                continue
            for slug in ("alpha", "beta"):
                (skills / slug).mkdir()
                (skills / slug / "SKILL.md").write_text("Nothing upstream.\n", encoding="utf-8")
        # REQUIRED_EXTRA_ROOTS (issue #5214): always create and populate, since
        # it is orthogonal to the skills-root "populated" matrix these tests
        # exercise and every case here needs main() to get past the required
        # root check.
        instructions = root / "src" / "copilot-cli" / "instructions"
        instructions.mkdir(parents=True, exist_ok=True)
        (instructions / "x.instructions.md").write_text("Nothing upstream.\n", encoding="utf-8")
        _commit_tree(root)

    def _run(self, root: Path, baseline: Path) -> int:
        return cmp.main(
            ["--repo-root", str(root), "--baseline", str(baseline), "--update-baseline"]
        )

    def test_refuses_when_every_root_is_empty(self, tmp_path: Path) -> None:
        self._roots(tmp_path)
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_refuses_when_only_the_claude_root_is_populated(self, tmp_path: Path) -> None:
        """The reported failure: one root full, one empty, previously exit 0."""
        self._roots(tmp_path, populated=(".claude",))
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_refuses_when_only_the_copilot_root_is_populated(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=("src/copilot-cli",))
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_partial_scan_leaves_a_populated_baseline_untouched(self, tmp_path: Path) -> None:
        """The wipe this guards against: shrinking a real baseline, not creating one."""
        self._roots(tmp_path, populated=(".claude",))
        baseline = tmp_path / "baseline.json"
        original = json.dumps({"files": {"a/SKILL.md": 3}, "marker_files": {"b/SKILL.md": 1}})
        baseline.write_text(original, encoding="utf-8")
        assert self._run(tmp_path, baseline) == 2
        assert baseline.read_text(encoding="utf-8") == original

    def test_refuses_when_roots_hold_only_non_markdown(self, tmp_path: Path) -> None:
        self._roots(tmp_path)
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "run.py").write_text("x = 1\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_writes_when_every_root_is_populated(self, tmp_path: Path) -> None:
        """The false-positive control. Multi-root by design, so a partial checkout
        cannot satisfy it and the guard cannot degrade into a blanket refusal."""
        self._roots(tmp_path, populated=tuple(sorted(cmp.REQUIRED_SKILLS_ROOTS)))
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 0
        assert json.loads(baseline.read_text(encoding="utf-8"))["files"] == {}

    def test_coverage_counts_files_read_not_offenders(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=tuple(sorted(cmp.REQUIRED_SKILLS_ROOTS)))
        assert cmp.scan_plugin_roots(tmp_path) == {}
        assert cmp.scanned_markdown_by_root(tmp_path) == {
            ".claude/skills": 2,
            "src/copilot-cli/skills": 2,
            "src/copilot-cli/instructions": 1,
        }

    def test_coverage_reports_a_starved_root_as_zero(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=(".claude",))
        assert cmp.scanned_markdown_by_root(tmp_path) == {
            ".claude/skills": 2,
            "src/copilot-cli/skills": 0,
            "src/copilot-cli/instructions": 1,
        }


class TestExecCheckerCoverage:
    def _roots(self, root: Path, populated: tuple[str, ...] = ()) -> None:
        for parts in cep.SCAN_ROOTS:
            skills = root.joinpath(*parts)
            skills.mkdir(parents=True, exist_ok=True)
            if "/".join(parts) not in populated:
                continue
            for slug in ("alpha", "beta"):
                (skills / slug).mkdir()
                (skills / slug / "SKILL.md").write_text("No bare invocations.\n", encoding="utf-8")
        _commit_tree(root)

    def _run(self, root: Path, baseline: Path) -> int:
        return cep.main(
            ["--repo-root", str(root), "--baseline", str(baseline), "--update-baseline"]
        )

    def test_refuses_when_every_root_is_empty(self, tmp_path: Path) -> None:
        self._roots(tmp_path)
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_refuses_when_only_the_claude_root_is_populated(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=(".claude/skills",))
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_refuses_when_the_copilot_root_is_absent_entirely(self, tmp_path: Path) -> None:
        """A sparse checkout omits the directory rather than emptying it."""
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text("ok\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_partial_scan_leaves_a_populated_baseline_untouched(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=(".claude/skills",))
        baseline = tmp_path / "baseline.json"
        original = json.dumps({"files": {"keep/SKILL.md": 9}, "marker_files": {}})
        baseline.write_text(original, encoding="utf-8")
        assert self._run(tmp_path, baseline) == 2
        assert baseline.read_text(encoding="utf-8") == original

    def test_refuses_when_skill_dir_lacks_a_skill_file(self, tmp_path: Path) -> None:
        """A directory without SKILL.md yields no readable files."""
        self._roots(tmp_path)
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "notes.md").write_text(
            "python3 scripts/x.py\n", encoding="utf-8"
        )
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_writes_when_every_root_is_populated(self, tmp_path: Path) -> None:
        """The false-positive control, built multi-root so it stays distinct."""
        self._roots(tmp_path, populated=tuple("/".join(p) for p in cep.SCAN_ROOTS))
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 0
        assert json.loads(baseline.read_text(encoding="utf-8"))["files"] == {}

    def test_coverage_counts_files_read_not_offenders(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=tuple("/".join(p) for p in cep.SCAN_ROOTS))
        assert cep.scan_skill_execs(tmp_path) == {}
        assert cep.scanned_files_by_root(tmp_path) == {
            ".claude/skills": 2,
            "src/copilot-cli/skills": 2,
        }

    def test_coverage_reports_an_absent_root_as_zero(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=(".claude/skills",))
        assert cep.scanned_files_by_root(tmp_path)["src/copilot-cli/skills"] == 0


class TestDescendantSymlinkEscapes:
    """Descendant escapes must fail closed before scan results are trusted."""

    @staticmethod
    def _seed_scan_roots(root: Path) -> None:
        for name in ROOT_NAMES:
            skill_dir = root / name / "alpha"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text("Clean prose.\n", encoding="utf-8")

    @staticmethod
    def _baseline(root: Path) -> tuple[Path, bytes]:
        baseline = root / "baseline.json"
        baseline.write_text(
            json.dumps({"files": {"keep/SKILL.md": 4}, "marker_files": {}}),
            encoding="utf-8",
        )
        return baseline, baseline.read_bytes()

    @staticmethod
    def _outside_path(root: Path, name: str) -> Path:
        return root.parent / f"{root.name}-{name}"

    @staticmethod
    def _escape_text(module: ModuleType) -> str:
        if module is cmp:
            return "Writes .agents/analysis/escape.md.\n"
        return "python3 .claude/skills/alpha/scripts/escape.py\n"

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Symlinks require privileges on Windows",
    )
    @pytest.mark.parametrize("module", [cmp, cep])
    @pytest.mark.parametrize("root_name", ROOT_NAMES)
    def test_checkers_refuse_descendant_file_symlink_escape(
        self, tmp_path: Path, module: ModuleType, root_name: str
    ) -> None:
        self._seed_scan_roots(tmp_path)
        outside = self._outside_path(tmp_path, "outside-file.md")
        outside.write_text(self._escape_text(module), encoding="utf-8")
        refs = tmp_path / root_name / "alpha" / "references"
        refs.mkdir()
        (refs / "escape.md").symlink_to(outside)
        baseline, before = self._baseline(tmp_path)

        rc = module.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])

        assert rc == 2
        assert baseline.read_bytes() == before

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Symlinks require privileges on Windows",
    )
    @pytest.mark.parametrize("module", [cmp, cep])
    @pytest.mark.parametrize("root_name", ROOT_NAMES)
    def test_checkers_refuse_descendant_directory_symlink_escape(
        self, tmp_path: Path, module: ModuleType, root_name: str
    ) -> None:
        self._seed_scan_roots(tmp_path)
        outside = self._outside_path(tmp_path, "outside-dir")
        outside.mkdir()
        (outside / "guide.md").write_text(self._escape_text(module), encoding="utf-8")
        skill_dir = tmp_path / root_name / "alpha"
        (skill_dir / "references").symlink_to(outside, target_is_directory=True)
        baseline, before = self._baseline(tmp_path)

        rc = module.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])

        assert rc == 2
        assert baseline.read_bytes() == before

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Symlinks require privileges on Windows",
    )
    @pytest.mark.parametrize("root_name", ROOT_NAMES)
    def test_exec_checker_refuses_descendant_scripts_directory_symlink_escape(
        self, tmp_path: Path, root_name: str
    ) -> None:
        self._seed_scan_roots(tmp_path)
        outside = self._outside_path(tmp_path, "outside-scripts-dir")
        skill_dir = tmp_path / root_name / "alpha"
        (skill_dir / "scripts").symlink_to(outside, target_is_directory=True)
        baseline, before = self._baseline(tmp_path)

        rc = cep.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])

        assert rc == 2
        assert baseline.read_bytes() == before

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Symlinks require privileges on Windows",
    )
    @pytest.mark.parametrize("module", [cmp, cep])
    @pytest.mark.parametrize("root_name", ROOT_NAMES)
    def test_update_baseline_treats_tracked_escape_as_missing(
        self, tmp_path: Path, module: ModuleType, root_name: str
    ) -> None:
        self._seed_scan_roots(tmp_path)
        outside = self._outside_path(tmp_path, "outside-notes.txt")
        outside.write_text("external\n", encoding="utf-8")
        (tmp_path / root_name / "alpha" / "notes.txt").symlink_to(outside)
        _commit_tree(tmp_path)
        coverage = tracked_coverage_by_root(tmp_path, ROOT_NAMES)
        assert coverage is not None
        assert coverage[root_name][1] == 1
        baseline, before = self._baseline(tmp_path)

        rc = module.main(
            [
                "--repo-root",
                str(tmp_path),
                "--baseline",
                "baseline.json",
                "--update-baseline",
            ]
        )

        assert rc == 2
        assert baseline.read_bytes() == before


class TestWorktreeGapCoverage:
    """Presence is not coverage, and an empty index is not proof of a full tree.

    A per-root non-zero rule accepts a checkout holding a single file in each
    root, which writes a baseline that drops every other file. Git already knows
    what the tree should contain, so the index is the ground truth rather than
    expected counts persisted in the baseline, which would drift. Zero tracked
    files is the trap: an untracked root, a tree that is not a repository, and a
    mistargeted root all report zero missing, so completeness git cannot confirm
    is refused rather than permitted.
    """

    def _repo(self, root: Path, skills: tuple[str, ...] = ("alpha", "beta", "gamma")) -> None:
        self._populate(root, skills)
        _commit_tree(root)

    def _populate(self, root: Path, skills: tuple[str, ...] = ("alpha", "beta", "gamma")) -> None:
        for name in ROOT_NAMES:
            for skill in skills:
                skill_dir = root / name / skill
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text(
                    f"---\nname: {skill}\n---\nSee `.claude/skills/x/y.py`.\n", encoding="utf-8"
                )

    def test_coverage_is_unknowable_outside_a_git_repo(self, tmp_path: Path) -> None:
        assert tracked_coverage_by_root(tmp_path, ROOT_NAMES) is None

    def test_complete_worktree_reports_every_file_tracked_and_present(self, tmp_path: Path) -> None:
        self._repo(tmp_path)
        assert tracked_coverage_by_root(tmp_path, ROOT_NAMES) == dict.fromkeys(ROOT_NAMES, (3, 0))

    def test_coverage_counts_tracked_files_absent_from_disk(self, tmp_path: Path) -> None:
        self._repo(tmp_path)
        (tmp_path / ROOT_NAMES[1] / "beta" / "SKILL.md").unlink()
        coverage = tracked_coverage_by_root(tmp_path, ROOT_NAMES)
        assert coverage == {ROOT_NAMES[0]: (3, 0), ROOT_NAMES[1]: (3, 1)}

    def test_untracked_root_reports_nothing_tracked(self, tmp_path: Path) -> None:
        self._repo(tmp_path)
        extra = tmp_path / ROOT_NAMES[1] / "delta"
        extra.mkdir(parents=True)
        (extra / "SKILL.md").write_text("x\n", encoding="utf-8")
        assert tracked_coverage_by_root(tmp_path, ["nowhere"]) == {"nowhere": (0, 0)}

    def test_complete_worktree_permits_the_write(self, tmp_path: Path) -> None:
        self._repo(tmp_path)
        assert refuse_uncovered_scan(tmp_path, dict.fromkeys(ROOT_NAMES, 3), "skill files") is False

    def test_missing_tracked_files_refuse_even_when_every_root_read(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        self._repo(tmp_path)
        for skill in ("beta", "gamma"):
            (tmp_path / ROOT_NAMES[1] / skill / "SKILL.md").unlink()
        assert refuse_uncovered_scan(tmp_path, dict.fromkeys(ROOT_NAMES, 1), "skill files") is True
        err = capsys.readouterr().err
        assert "incomplete checkout" in err
        assert f"{ROOT_NAMES[1]} (2 missing)" in err

    def test_untracked_files_refuse_rather_than_read_as_complete(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        self._populate(tmp_path)
        _git(tmp_path, "init", "-q", "-b", "main")
        assert refuse_uncovered_scan(tmp_path, dict.fromkeys(ROOT_NAMES, 3), "skill files") is True
        err = capsys.readouterr().err
        assert "git does not track" in err
        assert ROOT_NAMES[0] in err and ROOT_NAMES[1] in err

    def test_a_tree_that_is_not_a_repository_refuses(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        self._populate(tmp_path)
        assert refuse_uncovered_scan(tmp_path, dict.fromkeys(ROOT_NAMES, 3), "skill files") is True
        assert "git cannot vouch for" in capsys.readouterr().err

    def test_a_failed_conflict_probe_refuses(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        self._repo(tmp_path)
        real_git_lines = common._git_lines

        def fail_conflict_probe(root: Path, args: list[str]) -> list[str] | None:
            if args[:3] == ["ls-files", "-u", "-z"]:
                return None
            return real_git_lines(root, args)

        monkeypatch.setattr(common, "_git_lines", fail_conflict_probe)

        assert refuse_uncovered_scan(tmp_path, dict.fromkeys(ROOT_NAMES, 3), "skill files") is True
        assert "could not inspect unresolved conflicts" in capsys.readouterr().err

    def test_a_missing_git_executable_refuses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._repo(tmp_path)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise OSError("git not found")

        monkeypatch.setattr(subprocess, "run", _boom)
        assert tracked_coverage_by_root(tmp_path, ROOT_NAMES) is None

    def test_staged_deletions_are_accepted_as_intentional(self, tmp_path: Path) -> None:
        self._repo(tmp_path)
        (tmp_path / ROOT_NAMES[1] / "beta" / "SKILL.md").unlink()
        _git(tmp_path, "add", "-A")
        assert refuse_uncovered_scan(tmp_path, dict.fromkeys(ROOT_NAMES, 2), "skill files") is False

    @pytest.mark.parametrize("module", [cmp, cep])
    def test_checkers_refuse_a_sparse_worktree_and_leave_the_baseline(
        self, tmp_path: Path, module: ModuleType
    ) -> None:
        self._repo(tmp_path)
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {"keep/SKILL.md": 4}}), encoding="utf-8")
        before = baseline.read_bytes()
        for skill in ("beta", "gamma"):
            (tmp_path / ROOT_NAMES[1] / skill / "SKILL.md").unlink()
        argv = ["--repo-root", str(tmp_path), "--baseline", "baseline.json", "--update-baseline"]
        assert module.main(argv) == 2
        assert baseline.read_bytes() == before

    @pytest.mark.parametrize("module", [cmp, cep])
    def test_checkers_refuse_a_tree_that_is_not_a_repository(
        self, tmp_path: Path, module: ModuleType
    ) -> None:
        """Exit 2 rather than crash: git being unanswerable is a refusal, not an error."""
        self._populate(tmp_path)
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {"keep/SKILL.md": 4}}), encoding="utf-8")
        before = baseline.read_bytes()
        argv = ["--repo-root", str(tmp_path), "--baseline", "baseline.json", "--update-baseline"]
        assert module.main(argv) == 2
        assert baseline.read_bytes() == before

    @pytest.mark.parametrize("module", [cmp, cep])
    def test_checkers_refuse_a_root_git_does_not_track_and_leave_the_baseline(
        self, tmp_path: Path, module: ModuleType
    ) -> None:
        """One tracked root beside one untracked root: the shape found in the wild."""
        self._populate(tmp_path)
        _git(tmp_path, "init", "-q", "-b", "main")
        _git(tmp_path, "add", "--", ROOT_NAMES[0])
        _git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "partial")
        assert tracked_coverage_by_root(tmp_path, ROOT_NAMES) == {
            ROOT_NAMES[0]: (3, 0),
            ROOT_NAMES[1]: (0, 0),
        }
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {"keep/SKILL.md": 4}}), encoding="utf-8")
        before = baseline.read_bytes()
        argv = ["--repo-root", str(tmp_path), "--baseline", "baseline.json", "--update-baseline"]
        assert module.main(argv) == 2
        assert baseline.read_bytes() == before
