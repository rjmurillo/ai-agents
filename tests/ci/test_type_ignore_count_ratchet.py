"""Tests for the type-ignore count ratchet (issue #4039)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import count_ratchet
from scripts.ci import type_ignore_count_ratchet as ratchet

REPO_ROOT = Path(__file__).resolve().parents[2]


def _fake_git(files: tuple[str, ...] = ("pkg/mod.py",), git_rc: int = 0):
    """subprocess.run stub that returns a tracked-file list from git ls-files."""

    def _run(cmd, **kwargs):
        stdout = "\0".join(files) + ("\0" if files else "")
        return subprocess.CompletedProcess(cmd, git_rc, stdout=stdout, stderr="")

    return _run


# --- unit tests for current_count -----------------------------------------


class TestCurrentCount:
    def test_counts_type_ignore_in_single_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        py = tmp_path / "mod.py"
        py.write_text(
            "x: int = 'hi'  # type: ignore[assignment]\ny = 1\nz: str = 2  # type: ignore\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(subprocess, "run", _fake_git((str(py),)))
        assert ratchet.current_count(tmp_path) == 2

    def test_counts_across_multiple_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("x = y  # type: ignore[name-defined]\n", encoding="utf-8")
        b.write_text("a = b  # type: ignore\n", encoding="utf-8")
        monkeypatch.setattr(subprocess, "run", _fake_git((str(a), str(b))))
        assert ratchet.current_count(tmp_path) == 2

    def test_reads_relative_git_paths_from_repo_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        py = package_dir / "mod.py"
        py.write_text("x: int = 'hi'  # type: ignore[assignment]\n", encoding="utf-8")
        monkeypatch.setattr(subprocess, "run", _fake_git(("pkg/mod.py",)))
        assert ratchet.current_count(tmp_path) == 1

    def test_returns_zero_when_no_type_ignores(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        py = tmp_path / "clean.py"
        py.write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(subprocess, "run", _fake_git((str(py),)))
        assert ratchet.current_count(tmp_path) == 0

    def test_returns_zero_for_empty_file_list(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_git(()))
        assert ratchet.current_count(tmp_path) == 0

    def test_returns_none_when_git_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_git(git_rc=128))
        assert ratchet.current_count(tmp_path) is None

    def test_returns_none_when_file_unreadable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_git(("/nonexistent/path.py",)))
        assert ratchet.current_count(tmp_path) is None

    def test_ignores_partial_matches(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        py = tmp_path / "mod.py"
        py.write_text(
            "# noqa: type-ignore-something\n"  # inline test string, not a mypy annotation
            "# type-ignore\n"  # hyphen before "ignore", not a mypy annotation
            "x: int = 'hi'  # type: ignore\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(subprocess, "run", _fake_git((str(py),)))
        assert ratchet.current_count(tmp_path) == 1


class TestSelfReferentialExclusion:
    """Negative controls proving _SELF_REFERENTIAL_FILES exclusion is load-bearing.

    Each test simulates a self-referential file that contains the target pattern
    in a string literal (the same way the real ratchet and its tests do), and
    verifies the file is excluded from the count (issue #4039).
    """

    def test_ratchet_impl_file_is_excluded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Occurrences in the ratchet implementation file must NOT be counted."""
        rel = "scripts/ci/type_ignore_count_ratchet.py"
        ratchet_path = tmp_path / rel
        ratchet_path.parent.mkdir(parents=True)
        ratchet_path.write_text(
            '"""Count ``# type: ignore`` in files."""\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(subprocess, "run", _fake_git((rel,)))
        monkeypatch.setattr(ratchet, "_SELF_REFERENTIAL_FILES", frozenset([rel]))

        assert ratchet.current_count(tmp_path) == 0

    def test_exclusion_is_load_bearing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the self-referential path were NOT excluded, the count would be > 0.

        This is the isolating negative control: removing the exclusion makes the
        count rise. With the exclusion in place the count is 0.
        """
        target = tmp_path / "self_ref.py"
        target.write_text(
            '"""Match ``# type: ignore`` in this docstring."""\n',
            encoding="utf-8",
        )
        rel = str(target)

        # Without exclusion: count = 1
        monkeypatch.setattr(subprocess, "run", _fake_git((rel,)))
        monkeypatch.setattr(ratchet, "_SELF_REFERENTIAL_FILES", frozenset())
        assert ratchet.current_count(tmp_path) == 1

        # With exclusion: count = 0
        monkeypatch.setattr(ratchet, "_SELF_REFERENTIAL_FILES", frozenset([rel]))
        assert ratchet.current_count(tmp_path) == 0

    def test_non_excluded_files_are_still_counted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exclusion must not suppress real suppressions in other files."""
        real_file = tmp_path / "real_code.py"
        real_file.write_text("x: int = 1  # type: ignore[assignment]\n", encoding="utf-8")
        rel = str(real_file)
        monkeypatch.setattr(subprocess, "run", _fake_git((rel,)))
        monkeypatch.setattr(ratchet, "_SELF_REFERENTIAL_FILES", frozenset(["other/path.py"]))
        assert ratchet.current_count(tmp_path) == 1


class TestGeneratedLibMirrorExclusion:
    """ADR-109 B5: a mirrored lib package's suppressions count once, at source.

    `.claude/lib/`, `src/claude/lib/`, and `src/copilot-cli/lib/` each carry a
    byte-for-byte (modulo import rewrite) copy of
    `scripts/{hook_utilities,github_core,ai_review_common}/`. Counting the
    same suppression once per generated copy would make every new mirror
    inflate the ratchet for content that already counted at its canonical
    source (issue #4039's rationale, applied to duplicates instead of
    self-description).
    """

    @pytest.mark.parametrize(
        "rel",
        [
            ".claude/lib/github_core/bot_config.py",
            "src/claude/lib/github_core/bot_config.py",
            "src/copilot-cli/lib/hook_utilities/guards.py",
        ],
    )
    def test_mirror_package_files_are_excluded(self, rel: str) -> None:
        assert ratchet._is_generated_lib_mirror(rel) is True

    def test_canonical_source_is_not_excluded(self) -> None:
        assert ratchet._is_generated_lib_mirror("scripts/github_core/bot_config.py") is False

    def test_hand_maintained_lib_file_is_not_excluded(self) -> None:
        """Only the three mirrored package dirs are excluded, not the whole tree."""
        assert ratchet._is_generated_lib_mirror(".claude/lib/paths.py") is False

    def test_exclusion_is_load_bearing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        canonical = tmp_path / "scripts" / "github_core" / "bot_config.py"
        canonical.parent.mkdir(parents=True)
        canonical.write_text("x = None  # type: ignore[assignment]\n", encoding="utf-8")
        mirrors = [
            tmp_path / ".claude" / "lib" / "github_core" / "bot_config.py",
            tmp_path / "src" / "claude" / "lib" / "github_core" / "bot_config.py",
            tmp_path / "src" / "copilot-cli" / "lib" / "github_core" / "bot_config.py",
        ]
        for mirror in mirrors:
            mirror.parent.mkdir(parents=True)
            mirror.write_text("x = None  # type: ignore[assignment]\n", encoding="utf-8")

        rels = (
            "scripts/github_core/bot_config.py",
            ".claude/lib/github_core/bot_config.py",
            "src/claude/lib/github_core/bot_config.py",
            "src/copilot-cli/lib/github_core/bot_config.py",
        )
        monkeypatch.setattr(subprocess, "run", _fake_git(rels))

        assert ratchet.current_count(tmp_path) == 1


class TestGeneratedSkillMirrorExclusion:
    """ADR-109 B3 follow-up: a mirrored skill support file counts once, at source.

    .claude/skills/<name>/ is the canonical, hand-maintained source for every
    non-SKILL.md file; src/claude/skills/ and src/copilot-cli/skills/ each
    carry a byte-for-byte copy (generate_skills.py). Same rationale as the lib
    mirror exclusion above, applied to skills.
    """

    @pytest.mark.parametrize(
        ("rel", "expected"),
        [
            ("src/claude/skills/review/scripts/run.py", ".claude/skills/review/scripts/run.py"),
            (
                "src/copilot-cli/skills/review/scripts/run.py",
                ".claude/skills/review/scripts/run.py",
            ),
            (".claude/skills/review/scripts/run.py", None),
            ("scripts/authored/run.py", None),
        ],
    )
    def test_skill_mirror_canonical_source_mapping(self, rel: str, expected: str | None) -> None:
        assert ratchet._skill_mirror_canonical_source(rel) == expected

    def test_exclusion_is_load_bearing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        canonical = tmp_path / ".claude" / "skills" / "review" / "scripts" / "run.py"
        canonical.parent.mkdir(parents=True)
        canonical.write_text("x = None  # type: ignore[assignment]\n", encoding="utf-8")
        mirrors = [
            tmp_path / "src" / "claude" / "skills" / "review" / "scripts" / "run.py",
            tmp_path / "src" / "copilot-cli" / "skills" / "review" / "scripts" / "run.py",
        ]
        for mirror in mirrors:
            mirror.parent.mkdir(parents=True)
            mirror.write_text("x = None  # type: ignore[assignment]\n", encoding="utf-8")

        rels = (
            ".claude/skills/review/scripts/run.py",
            "src/claude/skills/review/scripts/run.py",
            "src/copilot-cli/skills/review/scripts/run.py",
        )
        monkeypatch.setattr(subprocess, "run", _fake_git(rels))

        assert ratchet.current_count(tmp_path) == 1

    def test_mirror_with_no_canonical_source_still_counts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A mirror-shaped path with nothing at .claude/skills/ is authored work."""
        orphan = tmp_path / "src" / "claude" / "skills" / "new" / "scripts" / "run.py"
        orphan.parent.mkdir(parents=True)
        orphan.write_text("x = None  # type: ignore[assignment]\n", encoding="utf-8")
        rels = ("src/claude/skills/new/scripts/run.py",)
        monkeypatch.setattr(subprocess, "run", _fake_git(rels))

        assert ratchet.current_count(tmp_path) == 1


class TestConstants:
    def test_py_globs_targets_python_files(self) -> None:
        """_PY_GLOBS must target .py files; mutation to another extension must be detected."""
        assert ratchet._PY_GLOBS == ("*.py",)

    def test_script_marker_names_a_tracked_file(self) -> None:
        """The bootstrap marker must point at this ratchet's own file."""
        assert (REPO_ROOT / ratchet._SCRIPT).is_file()


# --- integration tests for main() -----------------------------------------


class TestMain:
    def test_config_error_without_base_ref(self, capsys: pytest.CaptureFixture) -> None:
        assert ratchet.main([]) == count_ratchet.EXIT_CONFIG
        captured = capsys.readouterr()
        assert "--base-ref" in captured.err + captured.out

    def test_external_error_when_scan_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ratchet, "current_count", lambda _: None)
        assert ratchet.main(["--base-ref", "HEAD"]) == count_ratchet.EXIT_EXTERNAL

    def test_wires_this_ratchet_into_the_base_derived_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict = {}

        def _run(args, **kwargs):
            seen.update(kwargs)
            return 0

        monkeypatch.setattr(ratchet, "run", _run)
        assert ratchet.main(["--base-ref", "origin/main"]) == 0
        assert seen["label"] == "type-ignore count ratchet"
        assert seen["introduced_by"] == ratchet._SCRIPT
        assert seen["counter"] is ratchet.current_count

    def test_end_to_end_against_head_passes_on_the_real_repo(self) -> None:
        rc = ratchet.main(["--base-ref", "HEAD", "--repo-root", str(REPO_ROOT)])
        assert rc == count_ratchet.EXIT_OK
