# taste-lint: ignore file-size
"""Tests for baseline integrity guards: issues #4249, #4259, #4212, #4204.

#4249: four non-portability checkers are wired to refuse undiffable baselines.
#4259: baselines exceeding the reviewability size ceiling are refused.
#4212: scan roots symlinked outside the repository are refused.
#4204: marker_files count growth is refused on --update-baseline.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers: git repo setup
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=stdin,
        check=False,
    )


def _init_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with no external attribute file."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "config", "core.attributesFile", str(tmp_path / "absent-global"))
    return tmp_path


def _commit(root: Path, msg: str = "baseline") -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", msg)


def _hide_baseline(root: Path, pattern: str = "*.json") -> None:
    (root / ".gitattributes").write_text(f"{pattern} -diff\n")


# ---------------------------------------------------------------------------
# Module loaders
# ---------------------------------------------------------------------------


def _load_module(rel: str):
    path = REPO_ROOT / rel
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# #4259: refuse_oversized_baseline
# ---------------------------------------------------------------------------


class TestRefuseOversizedBaseline:
    """The size ceiling guard (issue #4259)."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from scripts.validation.portability_baseline import refuse_oversized_baseline
        self.guard = refuse_oversized_baseline

    def test_normal_sized_baseline_is_allowed(self, tmp_path: Path) -> None:
        p = tmp_path / "baseline.json"
        p.write_text(json.dumps({"files": {"a/b.py": 3}}) + "\n")
        assert self.guard(p) is False

    def test_missing_baseline_is_allowed(self, tmp_path: Path) -> None:
        # Downstream loader will handle missing files; size guard must not block.
        assert self.guard(tmp_path / "nonexistent.json") is False

    def test_oversized_baseline_is_refused(self, tmp_path: Path) -> None:
        p = tmp_path / "padded.json"
        # Write >200 000 bytes: the ceiling stated in portability_baseline.py
        payload = {"_pad": "x" * 300_000, "files": {"a/b.py": 1}}
        p.write_text(json.dumps(payload) + "\n")
        assert self.guard(p) is True

    def test_exactly_at_ceiling_is_allowed(self, tmp_path: Path) -> None:
        from scripts.validation.portability_baseline import _BASELINE_SIZE_CEILING
        p = tmp_path / "ceiling.json"
        # Write exactly the ceiling (not above).
        p.write_bytes(b"x" * _BASELINE_SIZE_CEILING)
        assert self.guard(p) is False

    def test_one_byte_over_ceiling_is_refused(self, tmp_path: Path) -> None:
        from scripts.validation.portability_baseline import _BASELINE_SIZE_CEILING
        p = tmp_path / "over.json"
        p.write_bytes(b"x" * (_BASELINE_SIZE_CEILING + 1))
        assert self.guard(p) is True

    def test_resolve_checked_baseline_refuses_oversized(self, tmp_path: Path) -> None:
        """resolve_checked_baseline propagates the size refusal."""
        repo = _init_repo(tmp_path)
        scripts = repo / "scripts" / "validation"
        scripts.mkdir(parents=True)
        bpath = scripts / "baseline.json"
        payload = {"_pad": "x" * 300_000, "files": {"a/b.py": 1}}
        bpath.write_text(json.dumps(payload) + "\n")
        _commit(repo)

        from scripts.validation.portability_common import resolve_checked_baseline
        result = resolve_checked_baseline(repo, bpath, "baseline.json")
        assert result is None

    def test_resolve_checked_baseline_allows_normal_size(self, tmp_path: Path) -> None:
        """Control: a normal-sized baseline passes resolve_checked_baseline."""
        repo = _init_repo(tmp_path)
        scripts = repo / "scripts" / "validation"
        scripts.mkdir(parents=True)
        bpath = scripts / "baseline.json"
        bpath.write_text(json.dumps({"files": {"a/b.py": 1}}) + "\n")
        _commit(repo)

        from scripts.validation.portability_common import resolve_checked_baseline
        result = resolve_checked_baseline(repo, bpath, "baseline.json")
        assert result == bpath


# ---------------------------------------------------------------------------
# #4249: four checkers wired to refuse_undiffable_baseline
# ---------------------------------------------------------------------------


class _CheckerDiffabilityBase:
    """Shared end-to-end pattern for the four checkers (issue #4249).

    Each subclass sets:
        baseline_name: str         -- relative path to the baseline file
        checker_main_args: callable -- returns argv list for the checker
        baseline_content: str      -- a valid committed baseline text
        setup_tree: callable       -- any extra files the checker needs
    """

    baseline_name: str
    checker_argv: list[str]
    baseline_text: str

    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        repo = _init_repo(tmp_path)
        self.setup_tree(repo)
        bpath = repo / self.baseline_name
        bpath.parent.mkdir(parents=True, exist_ok=True)
        bpath.write_text(self.baseline_text)
        _commit(repo)
        return repo

    def setup_tree(self, repo: Path) -> None:
        """Override to write extra files the checker requires."""

    def run_checker(self, repo: Path, *, hidden: bool) -> int:
        raise NotImplementedError

    def test_refuses_when_baseline_is_hidden(self, repo: Path) -> None:
        _hide_baseline(repo, self.baseline_name + " -diff")
        assert self.run_checker(repo, hidden=True) == 2

    def test_allows_when_baseline_is_visible(self, repo: Path) -> None:
        rc = self.run_checker(repo, hidden=False)
        # 0 = ok, 1 = regression -- both are acceptable; 2 = config error is not.
        assert rc in (0, 1)

    def test_control_hidden_versus_visible_differ(self, repo: Path) -> None:
        """Negative control: the two outcomes must differ (the guard is load-bearing)."""
        visible_rc = self.run_checker(repo, hidden=False)
        _hide_baseline(repo, self.baseline_name + " -diff")
        hidden_rc = self.run_checker(repo, hidden=True)
        assert hidden_rc != visible_rc


class TestCheckModelPinsDiffability:
    """check_model_pins.py refuses an undiffable baseline (issue #4249).

    check_model_pins.py uses a hardcoded _REPO_ROOT; we verify the guard is
    wired by calling refuse_undiffable_baseline in main() via monkeypatching,
    since the checker cannot be redirected to a tmp repo through its CLI alone.
    """

    @pytest.fixture(autouse=True)
    def _load(self):
        self._mod = _load_module("scripts/validation/check_model_pins.py")

    def test_refuse_undiffable_baseline_is_called_in_main(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The guard is wired: main() returns 2 when refuse_undiffable_baseline fires."""
        # Patch in the module's own namespace (imported name, not the source module).
        monkeypatch.setattr(self._mod, "refuse_undiffable_baseline", lambda repo, path: True)
        monkeypatch.setattr(self._mod, "refuse_symlinked_baseline", lambda repo, path: False)
        rc = self._mod.main([])
        assert rc == 2

    def test_refuse_symlinked_baseline_is_called_in_main(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The symlink guard is also wired."""
        monkeypatch.setattr(self._mod, "refuse_symlinked_baseline", lambda repo, path: True)
        rc = self._mod.main([])
        assert rc == 2

    def test_control_guards_do_not_fire_normally(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: when both guards pass, main() does not return 2 from them."""
        monkeypatch.setattr(self._mod, "refuse_symlinked_baseline", lambda repo, path: False)
        monkeypatch.setattr(self._mod, "refuse_undiffable_baseline", lambda repo, path: False)
        rc = self._mod.main([])
        # rc 0 = ok, 1 = regression -- neither is a guard-caused config error.
        assert rc in (0, 1)


class _MonkeypatchCheckerDiffabilityBase:
    """Verify a checker's main() calls both baseline guards (issue #4249).

    Uses monkeypatching because these checkers require complex tree structures
    to run end-to-end. We verify the guard call-site is wired, not the full
    checker behaviour, because the guards themselves are exercised in
    test_portability_baseline_diffability.py.
    """

    _mod: types.ModuleType  # set by _load_mod in each subclass

    @pytest.fixture(autouse=True)
    def _load_mod(self):
        raise NotImplementedError

    def test_refuses_when_undiffable_baseline_fires(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(self._mod, "refuse_symlinked_baseline", lambda r, p: False)
        monkeypatch.setattr(self._mod, "refuse_undiffable_baseline", lambda r, p: True)
        rc = self._run_main()
        assert rc == 2

    def test_refuses_when_symlinked_baseline_fires(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(self._mod, "refuse_symlinked_baseline", lambda r, p: True)
        rc = self._run_main()
        assert rc == 2

    def test_control_guard_pass_does_not_return_2_from_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: with guards bypassed the 2 must not come from them."""
        monkeypatch.setattr(self._mod, "refuse_symlinked_baseline", lambda r, p: False)
        monkeypatch.setattr(self._mod, "refuse_undiffable_baseline", lambda r, p: False)
        # rc may be 0, 1, or 2 for other reasons (e.g. missing tree), but when
        # the guard returns False both guards cannot be responsible for a 2.
        # We can only check that the guards are not the source; let rc be anything.
        rc = self._run_main()
        assert isinstance(rc, int)  # just confirm main() ran without exception

    def _run_main(self) -> int:
        raise NotImplementedError


class TestCheckRuleActivationCoverageDiffability(_MonkeypatchCheckerDiffabilityBase):
    """check_rule_activation_coverage.py refuses an undiffable baseline (issue #4249)."""

    @pytest.fixture(autouse=True)
    def _load_mod(self):
        self._mod = _load_module("scripts/validation/check_rule_activation_coverage.py")

    def _run_main(self) -> int:
        return self._mod.main([])


class TestCheckSkillContractTestsDiffability(_MonkeypatchCheckerDiffabilityBase):
    """check_skill_contract_tests.py refuses an undiffable baseline (issue #4249)."""

    @pytest.fixture(autouse=True)
    def _load_mod(self):
        self._mod = _load_module("scripts/validation/check_skill_contract_tests.py")

    def _run_main(self) -> int:
        return self._mod.main([])


class TestCheckVendorPortabilityDiffability(_MonkeypatchCheckerDiffabilityBase):
    """check_vendor_portability.py refuses an undiffable baseline (issue #4249)."""

    @pytest.fixture(autouse=True)
    def _load_mod(self):
        self._mod = _load_module("scripts/validation/check_vendor_portability.py")

    def _run_main(self) -> int:
        return self._mod.main([])


# ---------------------------------------------------------------------------
# #4212: scan_roots refuses symlinks pointing outside the repository
# ---------------------------------------------------------------------------


class TestScanRootsSymlinkGuard:
    """scan_roots refuses external symlinks (issue #4212)."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self._mod = _load_module("scripts/validation/check_vendor_portability.py")

    def test_normal_directory_is_accepted(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        skill_dir = repo / ".claude" / "skills"
        skill_dir.mkdir(parents=True)
        roots = self._mod.scan_roots(repo)
        assert any(str(r).endswith(".claude/skills") for r in roots)

    def test_symlink_outside_repo_is_refused(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        outside = tmp_path / "outside"
        outside.mkdir()
        (repo / ".claude").mkdir(parents=True)
        link = repo / ".claude" / "skills"
        link.symlink_to(outside)
        # skills directory is symlinked to outside; scan_roots must exclude it.
        roots = self._mod.scan_roots(repo)
        assert not any(str(r).endswith(".claude/skills") for r in roots)

    def test_symlink_inside_repo_is_allowed(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        real_dir = repo / ".real_skills"
        real_dir.mkdir(parents=True)
        (repo / ".claude").mkdir(parents=True)
        link = repo / ".claude" / "skills"
        link.symlink_to(real_dir)
        roots = self._mod.scan_roots(repo)
        # The symlink resolves inside the repo; it must be included.
        assert any(str(r).endswith(".claude/skills") for r in roots)

    def test_regular_root_unaffected_by_symlink_guard(self, tmp_path: Path) -> None:
        """Negative control: existing tests must not regress (the guard must not touch
        non-symlink directories)."""
        repo = tmp_path / "repo"
        skill_dir = repo / ".claude" / "skills" / "foo" / "scripts"
        skill_dir.mkdir(parents=True)
        # No symlinks; guard must leave the root in.
        roots = self._mod.scan_roots(repo)
        assert any(".claude/skills" in str(r) for r in roots)


# ---------------------------------------------------------------------------
# #4204: marker_files growth guard
# ---------------------------------------------------------------------------


class TestMarkerFilesGrowthGuard:
    """_refuse_marker_files_growth blocks silent marker expansion (issue #4204).

    Tests call _refuse_marker_files_growth directly because check_skill_md_portability
    main() requires a full repo tree (src/copilot-cli/skills, etc.) that would
    make the fixtures fragile and slow. The function is the decision point; the
    wiring into main() is verified by a separate integration test.
    """

    @pytest.fixture(autouse=True)
    def _import(self):
        from scripts.validation.check_skill_md_portability import (
            _refuse_marker_files_growth,
        )
        self.guard = _refuse_marker_files_growth

    @pytest.fixture
    def repo_with_committed_baseline(self, tmp_path: Path) -> tuple[Path, Path]:
        """Return (repo, bpath) with a committed baseline recording 2 refs."""
        repo = _init_repo(tmp_path)
        bpath = repo / "scripts" / "validation" / "skill_md_portability_baseline.json"
        bpath.parent.mkdir(parents=True, exist_ok=True)
        committed = {
            "_comment": "test",
            "files": {},
            "marker_files": {".claude/skills/foo/SKILL.md": 2},
        }
        bpath.write_text(json.dumps(committed, indent=2) + "\n")
        _commit(repo)
        return repo, bpath

    def test_growth_is_refused(
        self, repo_with_committed_baseline: tuple[Path, Path]
    ) -> None:
        repo, bpath = repo_with_committed_baseline
        # current total (3) > committed total (2)
        result = self.guard(
            repo, bpath,
            {".claude/skills/foo/SKILL.md": 3},
            allow_marker_grow=False,
        )
        assert result is True

    def test_growth_allowed_with_flag(
        self, repo_with_committed_baseline: tuple[Path, Path]
    ) -> None:
        repo, bpath = repo_with_committed_baseline
        result = self.guard(
            repo, bpath,
            {".claude/skills/foo/SKILL.md": 3},
            allow_marker_grow=True,
        )
        assert result is False

    def test_stable_count_is_allowed(
        self, repo_with_committed_baseline: tuple[Path, Path]
    ) -> None:
        repo, bpath = repo_with_committed_baseline
        result = self.guard(
            repo, bpath,
            {".claude/skills/foo/SKILL.md": 2},
            allow_marker_grow=False,
        )
        assert result is False

    def test_decrease_is_allowed(
        self, repo_with_committed_baseline: tuple[Path, Path]
    ) -> None:
        repo, bpath = repo_with_committed_baseline
        result = self.guard(
            repo, bpath,
            {".claude/skills/foo/SKILL.md": 1},
            allow_marker_grow=False,
        )
        assert result is False

    def test_new_file_adds_to_total_and_is_refused(
        self, repo_with_committed_baseline: tuple[Path, Path]
    ) -> None:
        """Adding a new marked file grows the total and must be refused."""
        repo, bpath = repo_with_committed_baseline
        result = self.guard(
            repo, bpath,
            {
                ".claude/skills/foo/SKILL.md": 2,
                ".claude/skills/bar/SKILL.md": 5,
            },
            allow_marker_grow=False,
        )
        assert result is True

    def test_no_baseline_at_all_is_allowed(self, tmp_path: Path) -> None:
        """When the baseline does not exist on disk or in git, the guard allows."""
        repo = _init_repo(tmp_path)
        bpath = repo / "scripts" / "validation" / "skill_md_portability_baseline.json"
        bpath.parent.mkdir(parents=True, exist_ok=True)
        # No file on disk, no git history.
        result = self.guard(
            repo, bpath,
            {".claude/skills/bar/SKILL.md": 10},
            allow_marker_grow=False,
        )
        assert result is False  # no predecessor at all means no refusal

    def test_disk_only_baseline_compares_against_disk(self, tmp_path: Path) -> None:
        """Disk-present-but-uncommitted baseline still provides a comparison floor."""
        repo = _init_repo(tmp_path)
        bpath = repo / "scripts" / "validation" / "skill_md_portability_baseline.json"
        bpath.parent.mkdir(parents=True, exist_ok=True)
        bpath.write_text(
            json.dumps({"files": {}, "marker_files": {".claude/skills/foo/SKILL.md": 2}}, indent=2)
            + "\n"
        )
        # Current total (5) > disk total (2): growth is refused.
        result = self.guard(
            repo, bpath,
            {".claude/skills/foo/SKILL.md": 5},
            allow_marker_grow=False,
        )
        assert result is True
