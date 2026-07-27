"""Tests for scripts.validation.skill_size module.

Validates SKILL.md files against size limits per Issue #676.
Covers size checking, exception handling, CLI modes, and edge cases.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import skill_size as _skill_size_mod
from scripts.validation.skill_size import (
    SKILL_BYTE_LIMIT,
    SKILL_BYTE_TARGET,
    SKILL_BYTE_WARNING,
    SKILL_SIZE_LIMIT,
    SKILL_SIZE_WARNING,
    StagedBlobError,
    check_skill_size,
    has_size_exception,
    main,
    read_staged_blob_bytes,
)

# ---------------------------------------------------------------------------
# has_size_exception
# ---------------------------------------------------------------------------


class TestHasSizeException:
    """Tests for size exception detection in frontmatter."""

    def test_exception_declared(self) -> None:
        content = "---\nname: big-skill\nsize-exception: true\n---\nBody"
        assert has_size_exception(content) is True

    def test_no_exception(self) -> None:
        content = "---\nname: small-skill\n---\nBody"
        assert has_size_exception(content) is False

    def test_exception_false(self) -> None:
        content = "---\nname: skill\nsize-exception: false\n---\nBody"
        assert has_size_exception(content) is False

    def test_no_frontmatter(self) -> None:
        content = "No frontmatter here"
        assert has_size_exception(content) is False

    def test_unclosed_frontmatter(self) -> None:
        content = "---\nname: skill\nsize-exception: true\nNo closing delimiter"
        assert has_size_exception(content) is False


# ---------------------------------------------------------------------------
# check_skill_size
# ---------------------------------------------------------------------------


class TestCheckSkillSize:
    """Tests for individual file size checking."""

    def test_small_file_passes(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: test\n---\n" + "line\n" * 50)

        result = check_skill_size(skill)

        assert result.passed is True
        assert result.warning is False
        assert result.line_count == 53

    def test_warning_threshold(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: test\n---\n" + "line\n" * SKILL_SIZE_WARNING)

        result = check_skill_size(skill)

        assert result.passed is True
        assert result.warning is True

    def test_exceeds_limit(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: test\n---\n" + "line\n" * SKILL_SIZE_LIMIT)

        result = check_skill_size(skill)

        assert result.passed is False
        assert len(result.errors) == 1
        assert "exceeds" in result.errors[0]
        assert "progressive disclosure" in result.errors[0]

    def test_exceeds_limit_with_exception(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\nname: test\nsize-exception: true\n---\n"
            + "line\n" * SKILL_SIZE_LIMIT
        )

        result = check_skill_size(skill)

        assert result.passed is True
        assert result.warning is True
        assert result.has_exception is True

    def test_empty_file_passes(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("")

        result = check_skill_size(skill)

        assert result.passed is True
        assert result.line_count == 0

    def test_exactly_at_limit(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        lines = SKILL_SIZE_LIMIT - 3  # 3 lines for frontmatter
        skill.write_text("---\nname: test\n---\n" + "line\n" * lines)

        result = check_skill_size(skill)

        assert result.passed is True


# ---------------------------------------------------------------------------
# check_skill_size: byte dimension (Issue #3421)
# ---------------------------------------------------------------------------


class TestCheckSkillSizeBytes:
    """Tests for the byte-size dimension, independent of the line dimension."""

    def test_byte_thresholds_are_ordered(self) -> None:
        # The ratchet invariant: warn < documented target <= enforced ceiling.
        assert SKILL_BYTE_WARNING < SKILL_BYTE_TARGET
        assert SKILL_BYTE_TARGET <= SKILL_BYTE_LIMIT

    def test_small_file_no_byte_warning(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: test\n---\nSmall body", encoding="utf-8")

        result = check_skill_size(skill)

        assert result.passed is True
        assert result.warning is False
        assert result.byte_count == len(skill.read_bytes())

    def test_byte_warning_threshold(self, tmp_path: Path) -> None:
        # Over the 12 KiB soft ceiling but under the enforced limit and under
        # the 500-line limit: warns on bytes alone.
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\nname: test\n---\n" + ("x" * 200 + "\n") * 70, encoding="utf-8"
        )

        result = check_skill_size(skill)

        assert result.byte_count > SKILL_BYTE_WARNING
        assert result.byte_count <= SKILL_BYTE_LIMIT
        assert result.line_count <= SKILL_SIZE_LIMIT
        assert result.passed is True
        assert result.warning is True

    def test_exceeds_byte_limit_under_line_limit(self, tmp_path: Path) -> None:
        # The case the line check misses: a table-heavy body sits well under
        # 500 lines yet blows the byte ceiling. It must FAIL on bytes.
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\nname: test\n---\n" + ("x" * 600 + "\n") * 50, encoding="utf-8"
        )

        result = check_skill_size(skill)

        assert result.line_count <= SKILL_SIZE_LIMIT
        assert result.byte_count > SKILL_BYTE_LIMIT
        assert result.passed is False
        assert len(result.errors) == 1
        assert "bytes" in result.errors[0]
        assert "progressive disclosure" in result.errors[0]

    def test_exceeds_byte_limit_with_exception(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\nname: test\nsize-exception: true\n---\n" + ("x" * 600 + "\n") * 50,
            encoding="utf-8",
        )

        result = check_skill_size(skill)

        assert result.passed is True
        assert result.warning is True
        assert result.has_exception is True

    def test_byte_count_is_raw_bytes_not_chars(self, tmp_path: Path) -> None:
        # Multi-byte UTF-8 must count as raw bytes (matching `wc -c`), not code
        # points, so the measure cannot be dodged with wide characters. Write raw
        # bytes (not write_text) so the on-disk size is identical on Windows and
        # POSIX: write_text translates LF to CRLF on Windows and would inflate the
        # count, failing this test spuriously. The embedded CRLF also proves the
        # counter preserves bytes verbatim rather than normalizing newlines.
        skill = tmp_path / "SKILL.md"
        payload = b"---\r\nname: test\r\n---\r\n" + "\u00e9".encode("utf-8") * 100
        skill.write_bytes(payload)

        result = check_skill_size(skill)

        assert result.byte_count == len(payload)
        # 100 two-byte 'é' plus the prefix: more raw bytes than decoded code points.
        assert result.byte_count > len(payload.decode("utf-8"))

    def test_custom_byte_limit_triggers_failure(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: test\n---\n" + "x" * 500, encoding="utf-8")

        result = check_skill_size(skill, byte_limit=100, byte_warn=50)

        assert result.passed is False
        assert any("bytes" in e for e in result.errors)

    def test_byte_limit_boundary_is_inclusive(self, tmp_path: Path) -> None:
        # Pin ``>`` (not ``>=``): a body of EXACTLY the limit passes; one byte
        # over fails. Guards the ratchet against an off-by-one that would red a
        # file sitting on the boundary or pass one just past it.
        at_limit = tmp_path / "at.md"
        at_limit.write_bytes(b"x" * SKILL_BYTE_LIMIT)
        result_at = check_skill_size(at_limit)
        assert result_at.byte_count == SKILL_BYTE_LIMIT
        assert result_at.passed is True

        over = tmp_path / "over.md"
        over.write_bytes(b"x" * (SKILL_BYTE_LIMIT + 1))
        result_over = check_skill_size(over)
        assert result_over.byte_count == SKILL_BYTE_LIMIT + 1
        assert result_over.passed is False

    def test_real_corpus_within_byte_ratchet(self) -> None:
        # Main must stay green: every shipped SKILL.md is within the seeded
        # ratchet. If a new skill lands oversized, or the ratchet is lowered
        # below the current largest body, this fails, exactly when a human must
        # decide to decompose the skill or re-seed the constant. Mirrors the
        # instruction-budget anchor test. Reads raw bytes directly so it pins the
        # byte dimension without coupling to the line check.
        repo_root = Path(__file__).resolve().parents[1]
        skills = sorted((repo_root / ".claude" / "skills").rglob("SKILL.md"))
        assert skills, "expected shipped skills under .claude/skills"
        oversized = [
            (str(skill), len(skill.read_bytes()))
            for skill in skills
            if len(skill.read_bytes()) > SKILL_BYTE_LIMIT
        ]
        assert not oversized, (
            f"ratchet seed too low: these bodies exceed "
            f"SKILL_BYTE_LIMIT={SKILL_BYTE_LIMIT}: {oversized}"
        )

    def test_no_files_returns_zero(self, tmp_path: Path) -> None:
        exit_code = main(["--path", str(tmp_path)])
        assert exit_code == 0

    def test_valid_files_pass(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nSmall skill")

        exit_code = main(["--path", str(tmp_path)])
        assert exit_code == 0

    def test_oversized_fails_in_ci(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "big-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\n---\n" + "line\n" * 600
        )

        exit_code = main(["--path", str(tmp_path), "--ci"])
        assert exit_code == 1

    def test_oversized_passes_locally(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.delenv("CI", raising=False)
        skill_dir = tmp_path / "big-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\n---\n" + "line\n" * 600
        )

        exit_code = main(["--path", str(tmp_path)])
        assert exit_code == 0

    def test_custom_limit(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\n---\n" + "line\n" * 150
        )

        exit_code = main(["--path", str(tmp_path), "--ci", "--limit", "100"])
        assert exit_code == 1

    def test_exception_bypasses_failure(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\nsize-exception: true\n---\n" + "line\n" * 600
        )

        exit_code = main(["--path", str(tmp_path), "--ci"])
        assert exit_code == 0

    def test_custom_byte_limit_fails_in_ci(self, tmp_path: Path) -> None:
        # A body that is fine on lines but over a tightened byte limit fails CI.
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\n---\n" + "x" * 500, encoding="utf-8"
        )

        exit_code = main(
            ["--path", str(tmp_path), "--ci", "--byte-limit", "100", "--byte-warn", "50"]
        )
        assert exit_code == 1

    def test_byte_exception_bypasses_failure_in_ci(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\nsize-exception: true\n---\n" + "x" * 500,
            encoding="utf-8",
        )

        exit_code = main(
            ["--path", str(tmp_path), "--ci", "--byte-limit", "100", "--byte-warn", "50"]
        )
        assert exit_code == 0


class TestStagedBlobValidation:
    """Staged mode judges the indexed blob, not the working tree (#3421 review).

    A pre-commit gate that measured the working tree could be fooled: stage an
    oversized body, then shrink or add an exception in the worktree without
    staging, and the oversized blob would still get committed. These tests build
    a real repo and drive ``main(["--staged-only", "--ci"])`` to prove the gate
    reads ``git show :<path>``.
    """

    @staticmethod
    def _init_repo(repo: Path) -> None:
        for args in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "test@example.com"],
            ["git", "config", "user.name", "Test"],
        ):
            subprocess.run(args, cwd=repo, check=True, capture_output=True)

    @staticmethod
    def _write_skill(repo: Path, payload: bytes) -> Path:
        skill = repo / ".claude" / "skills" / "big" / "SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_bytes(payload)
        return skill

    @staticmethod
    def _stage_all(repo: Path) -> None:
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)

    def test_oversized_staged_blob_fails_despite_small_worktree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Stage an oversized body, then shrink the worktree WITHOUT staging. The
        # gate must fail on the staged (committed) blob, not the small worktree.
        self._init_repo(tmp_path)
        skill = self._write_skill(
            tmp_path, b"---\nname: big\n---\n" + b"x" * (SKILL_BYTE_LIMIT + 64)
        )
        self._stage_all(tmp_path)
        skill.write_bytes(b"---\nname: big\n---\nsmall")  # unstaged shrink

        monkeypatch.chdir(tmp_path)
        assert main(["--staged-only", "--ci"]) == 1

    def test_unstaged_growth_does_not_fail_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Stage a small body, then grow the worktree oversized WITHOUT staging.
        # The gate must pass: only the staged blob (small) is committed.
        self._init_repo(tmp_path)
        skill = self._write_skill(tmp_path, b"---\nname: big\n---\nsmall")
        self._stage_all(tmp_path)
        skill.write_bytes(b"---\nname: big\n---\n" + b"x" * (SKILL_BYTE_LIMIT + 64))

        monkeypatch.chdir(tmp_path)
        assert main(["--staged-only", "--ci"]) == 0

    def test_unstaged_exception_does_not_bypass_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The reviewer's exact concern: an oversized body is staged WITHOUT an
        # exception; the worktree adds `size-exception: true` unstaged. The gate
        # must still FAIL, because the staged blob carries no exception.
        self._init_repo(tmp_path)
        big = b"x" * (SKILL_BYTE_LIMIT + 64)
        skill = self._write_skill(tmp_path, b"---\nname: big\n---\n" + big)
        self._stage_all(tmp_path)
        skill.write_bytes(b"---\nname: big\nsize-exception: true\n---\n" + big)

        monkeypatch.chdir(tmp_path)
        assert main(["--staged-only", "--ci"]) == 1

    def test_staged_exception_is_honored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A staged oversized body WITH an exception downgrades to a warning
        # (exit 0), even though the worktree removes the exception unstaged.
        # Proves exception parsing reads the staged blob too.
        self._init_repo(tmp_path)
        big = b"x" * (SKILL_BYTE_LIMIT + 64)
        skill = self._write_skill(
            tmp_path, b"---\nname: big\nsize-exception: true\n---\n" + big
        )
        self._stage_all(tmp_path)
        skill.write_bytes(b"---\nname: big\n---\n" + big)  # exception removed, unstaged

        monkeypatch.chdir(tmp_path)
        assert main(["--staged-only", "--ci"]) == 0

    def test_staged_deletion_of_oversized_add_fails_closed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Finding A (fail-open): stage an oversized ADD, then delete the worktree
        # file WITHOUT staging the deletion. The index still carries the oversized
        # blob, so it is commit-ready. The old discovery filtered by
        # ``path.exists()`` and dropped it -> gate found nothing -> exit 0. The
        # gate must instead measure the staged blob and FAIL.
        import os

        self._init_repo(tmp_path)
        skill = self._write_skill(
            tmp_path, b"---\nname: big\n---\n" + b"x" * (SKILL_BYTE_LIMIT + 64)
        )
        self._stage_all(tmp_path)
        os.remove(skill)  # worktree gone; staged ADD remains commit-ready

        monkeypatch.chdir(tmp_path)
        assert main(["--staged-only", "--ci"]) == 1

    def test_read_staged_blob_bytes_raises_when_not_staged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A path with no index entry cannot be measured; fail closed rather than
        # return None (which the old code let fall back to the working tree).
        self._init_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(StagedBlobError):
            read_staged_blob_bytes(Path(".claude/skills/ghost/SKILL.md"))

    def test_git_show_failure_fails_closed_in_main(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # If reading the staged blob fails for any reason, main must fail closed
        # (exit 2, unconditionally) and never silently pass the file.
        self._init_repo(tmp_path)
        self._write_skill(tmp_path, b"---\nname: big\n---\nsmall")
        self._stage_all(tmp_path)

        def _boom(path: Path) -> bytes:
            msg = f"{path.as_posix()}: simulated git show failure"
            raise StagedBlobError(msg)

        monkeypatch.setattr(_skill_size_mod, "read_staged_blob_bytes", _boom)
        monkeypatch.chdir(tmp_path)
        # Not --ci: fail-closed on an uncertifiable blob is unconditional.
        assert main(["--staged-only"]) == 2

    def test_staged_symlink_skill_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Finding B (symlink): git stores a symlink's target text as its blob, so
        # a staged SKILL.md symlink to a 30 KiB file measures only the short link
        # text and would slip past the ceiling. Staged via update-index cacheinfo
        # (mode 120000) so the test is OS-independent (no real filesystem symlink,
        # works on Windows CI). The gate must reject it (fail closed, exit 2).
        self._init_repo(tmp_path)
        sha = (
            subprocess.run(
                ["git", "hash-object", "-w", "--stdin"],
                input=b"../../../some/large/target/file",
                cwd=tmp_path,
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .strip()
        )
        subprocess.run(
            [
                "git",
                "update-index",
                "--add",
                "--cacheinfo",
                f"120000,{sha},.claude/skills/big/SKILL.md",
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        monkeypatch.chdir(tmp_path)
        assert main(["--staged-only", "--ci"]) == 2
