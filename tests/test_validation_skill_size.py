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
    StagedDiscoveryError,
    check_skill_size,
    get_staged_skill_files,
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
            "---\nname: test\nsize-exception: true\n---\n" + "line\n" * SKILL_SIZE_LIMIT
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
        skill.write_text("---\nname: test\n---\n" + ("x" * 200 + "\n") * 70, encoding="utf-8")

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
        skill.write_text("---\nname: test\n---\n" + ("x" * 600 + "\n") * 50, encoding="utf-8")

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
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n" + "line\n" * 600)

        exit_code = main(["--path", str(tmp_path), "--ci"])
        assert exit_code == 1

    def test_oversized_passes_locally(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        skill_dir = tmp_path / "big-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n" + "line\n" * 600)

        exit_code = main(["--path", str(tmp_path)])
        assert exit_code == 0

    def test_custom_limit(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n" + "line\n" * 150)

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
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n" + "x" * 500, encoding="utf-8")

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
    reads the staged index object (``git ls-files -s`` + ``git cat-file blob``),
    never the working tree.
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
        skill = self._write_skill(tmp_path, b"---\nname: big\nsize-exception: true\n---\n" + big)
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

    def test_git_cat_file_failure_fails_closed_in_main(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # If reading the staged blob fails for any reason, main must fail closed
        # (exit 2, unconditionally) and never silently pass the file.
        self._init_repo(tmp_path)
        self._write_skill(tmp_path, b"---\nname: big\n---\nsmall")
        self._stage_all(tmp_path)

        def _boom(path: Path) -> bytes:
            msg = f"{path.as_posix()}: simulated git cat-file failure"
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

    def test_staged_gitlink_skill_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Round-3 finding: a gitlink/submodule entry (mode 160000) stores a commit
        # id as its "blob", not the file bytes, so measuring it under-counts. The
        # mode whitelist (100644/100755) must reject it. Staged via cacheinfo so
        # the test needs no real submodule and is OS-independent.
        self._init_repo(tmp_path)
        # A gitlink cacheinfo needs a non-null commit id; git rejects the all-zero
        # SHA. Reuse a real commit id from an initial commit in this repo.
        (tmp_path / "seed.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "seed.txt"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-qm", "seed"], cwd=tmp_path, check=True, capture_output=True
        )
        commit_sha = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, check=True
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
                f"160000,{commit_sha},.claude/skills/big/SKILL.md",
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        monkeypatch.chdir(tmp_path)
        assert main(["--staged-only", "--ci"]) == 2

    def test_typechange_to_symlink_is_discovered_and_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Round-3 finding: replacing a committed regular SKILL.md with a symlink is
        # a typechange (git status ``T``). ``--diff-filter=ACMR`` excluded ``T``, so
        # discovery skipped it and the gate passed (exit 0) while an oversized-target
        # symlink was commit-ready. ``--diff-filter=ACMRT`` must discover it, and the
        # mode whitelist must then reject it (exit 2).
        self._init_repo(tmp_path)
        skill = self._write_skill(tmp_path, b"---\nname: big\n---\nsmall real body")
        self._stage_all(tmp_path)
        subprocess.run(
            ["git", "commit", "-qm", "add skill"], cwd=tmp_path, check=True, capture_output=True
        )
        # Replace the regular file with a symlink blob at the same path (typechange).
        sha = (
            subprocess.run(
                ["git", "hash-object", "-w", "--stdin"],
                input=b"../../../some/large/target",
                cwd=tmp_path,
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .strip()
        )
        skill.unlink()
        subprocess.run(
            [
                "git",
                "update-index",
                "--cacheinfo",
                f"120000,{sha},.claude/skills/big/SKILL.md",
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        monkeypatch.chdir(tmp_path)
        assert main(["--staged-only", "--ci"]) == 2

    def test_non_ascii_staged_path_is_discovered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Round-3 finding: with default ``core.quotePath``, a non-ASCII path like
        # ``café`` is emitted octal-escaped and double-quoted by a newline-split
        # ``git diff --name-only``, so an anchored match missed it and the oversized
        # blob dodged the gate. ``-z`` emits raw NUL-separated paths, so discovery
        # sees it and the gate fails on the oversized staged blob.
        self._init_repo(tmp_path)
        skill = tmp_path / ".claude" / "skills" / "café" / "SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_bytes(b"---\nname: cafe\n---\n" + b"x" * (SKILL_BYTE_LIMIT + 64))
        self._stage_all(tmp_path)

        monkeypatch.chdir(tmp_path)
        discovered = get_staged_skill_files()
        assert any("caf" in p.as_posix() for p in discovered)
        assert main(["--staged-only", "--ci"]) == 1

    def test_discovery_failure_fails_closed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Round-3 finding: a failed ``git diff`` (nonzero/timeout/git missing) must
        # not become an empty successful run (exit 0). It raises StagedDiscoveryError,
        # which main routes to exit 2 (fail closed), unconditionally (no --ci).
        def _boom() -> list[Path]:
            raise StagedDiscoveryError("simulated git diff failure")

        monkeypatch.setattr(_skill_size_mod, "get_staged_skill_files", _boom)
        monkeypatch.chdir(tmp_path)
        assert main(["--staged-only"]) == 2

    def test_pathspec_glob_dir_name_measures_own_blob(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Finding 1 (pathspec glob collision): a skill dir whose name holds a glob
        # metacharacter (``x?``) was passed to ``git ls-files -- <path>`` as a
        # pathspec, so it glob-matched a smaller sibling (``x0``). ``git ls-files``
        # emits ``x0`` first (it sorts before ``x?``), so a first-match read
        # measured the small decoy and the oversized body slipped (under-count,
        # exit 0). ``:(literal)`` plus a returned-pathname check must bind the read
        # to the exact path. Staged via cacheinfo so the ``?`` path is
        # OS-independent (Windows cannot create it on disk, but the index never
        # touches the filesystem).
        self._init_repo(tmp_path)
        big = (
            subprocess.run(
                ["git", "hash-object", "-w", "--stdin"],
                input=b"---\nname: xq\n---\n" + b"x" * (SKILL_BYTE_LIMIT + 64),
                cwd=tmp_path,
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .strip()
        )
        small = (
            subprocess.run(
                ["git", "hash-object", "-w", "--stdin"],
                input=b"small",
                cwd=tmp_path,
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .strip()
        )
        for cacheinfo in (
            f"100644,{big},.claude/skills/x?/SKILL.md",
            f"100644,{small},.claude/skills/x0/SKILL.md",
        ):
            subprocess.run(
                ["git", "update-index", "--add", "--cacheinfo", cacheinfo],
                cwd=tmp_path,
                check=True,
                capture_output=True,
            )

        monkeypatch.chdir(tmp_path)
        # The read binds to x?'s own oversized blob, not the small x0 decoy that
        # the glob pathspec would have matched first.
        measured = read_staged_blob_bytes(Path(".claude/skills/x?/SKILL.md"))
        assert len(measured) > SKILL_BYTE_LIMIT
        assert main(["--staged-only", "--ci"]) == 1

    def test_replace_ref_does_not_swap_measured_blob(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Finding 2 (replace-refs): ``git cat-file blob <oid>`` honors
        # ``refs/replace/`` by default, so a replace ref pointing the oversized
        # index blob at a tiny substitute would make the gate measure the small
        # bytes (under-count, exit 0). ``--no-replace-objects`` must read the true
        # indexed object (exit 1).
        self._init_repo(tmp_path)
        self._write_skill(tmp_path, b"---\nname: big\n---\n" + b"x" * (SKILL_BYTE_LIMIT + 64))
        self._stage_all(tmp_path)
        big_oid = (
            subprocess.run(
                ["git", "rev-parse", ":.claude/skills/big/SKILL.md"],
                cwd=tmp_path,
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .strip()
        )
        small_oid = (
            subprocess.run(
                ["git", "hash-object", "-w", "--stdin"],
                input=b"tiny",
                cwd=tmp_path,
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .strip()
        )
        subprocess.run(
            ["git", "update-ref", f"refs/replace/{big_oid}", small_oid],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        monkeypatch.chdir(tmp_path)
        # Setup proof: a default cat-file honors the replacement (reads "tiny"),
        # so the substitution is genuinely active in this repo.
        swapped = subprocess.run(
            ["git", "cat-file", "blob", big_oid],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        ).stdout
        assert swapped == b"tiny"
        # The gate reads with --no-replace-objects, so it measures the real blob.
        measured = read_staged_blob_bytes(Path(".claude/skills/big/SKILL.md"))
        assert len(measured) > SKILL_BYTE_LIMIT
        assert main(["--staged-only", "--ci"]) == 1

    def test_sparse_index_tree_replace_does_not_swap_measured_blob(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Finding (round-3 review, sparse-index tree replacement): a full index
        # prints the recorded oid from ``ls-files -s`` verbatim, but a sparse
        # index expands the sparse-directory tree entry that holds the path, and
        # that expansion honors ``refs/replace/``. A replacement TREE mapping the
        # skill path to a tiny decoy blob makes the oid resolution return the
        # decoy; the cat-file (already --no-replace-objects) then reads the
        # decoy's small bytes -> under-count (exit 0). ``ls-files`` must also run
        # with --no-replace-objects. Reproduced on git 2.43.
        self._init_repo(tmp_path)
        # Harden the environment so an inherited replace-disabling setting
        # cannot make the setup guard below skip on a capable git build and
        # silently mask a regression. Three inheritance channels can force
        # replace refs off and each outranks or bypasses repo-local config:
        #   - GIT_NO_REPLACE_OBJECTS (env): disables replace outright.
        #   - core.useReplaceRefs=false in global/system config: repo-local
        #     core.useReplaceRefs=true (set below) overrides it.
        #   - command-scope config injection via GIT_CONFIG_PARAMETERS or the
        #     GIT_CONFIG_COUNT/KEY_*/VALUE_* trio: these are applied at -c
        #     precedence and would override the repo-local setting, so drop
        #     them. Clearing GIT_CONFIG_COUNT neutralizes the indexed trio.
        monkeypatch.delenv("GIT_NO_REPLACE_OBJECTS", raising=False)
        monkeypatch.delenv("GIT_CONFIG_PARAMETERS", raising=False)
        monkeypatch.delenv("GIT_CONFIG_COUNT", raising=False)
        subprocess.run(
            ["git", "config", "core.useReplaceRefs", "true"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        (tmp_path / "keep").mkdir()
        (tmp_path / "keep" / "a.txt").write_bytes(b"keep\n")
        self._write_skill(tmp_path, b"---\nname: big\n---\n" + b"x" * (SKILL_BYTE_LIMIT + 64))
        self._stage_all(tmp_path)
        subprocess.run(
            ["git", "commit", "-qm", "base"], cwd=tmp_path, check=True, capture_output=True
        )
        skill_rel = ".claude/skills/big/SKILL.md"

        def _git(*args: str, _input: bytes | None = None) -> str:
            return (
                subprocess.run(
                    ["git", *args],
                    cwd=tmp_path,
                    input=_input,
                    capture_output=True,
                    check=True,
                )
                .stdout.decode()
                .strip()
            )

        big_oid = _git("rev-parse", f":{skill_rel}")
        small_oid = _git("hash-object", "-w", "--stdin", _input=b"tiny")
        orig_subtree = _git("rev-parse", "HEAD^{tree}:.claude/skills/big")
        new_subtree = _git("mktree", _input=f"100644 blob {small_oid}\tSKILL.md\n".encode())
        _git("replace", orig_subtree, new_subtree)
        _git("sparse-checkout", "init", "--cone", "--sparse-index")
        _git("sparse-checkout", "set", "keep")
        # Prove the sparse-index setup actually produced a sparse-directory
        # entry (mode 040000): the .claude tree is outside the "keep" cone, so
        # it must collapse to a tree entry the gate has to expand. A git build
        # that does not produce one cannot stage this attack; skip there.
        staged = _git("ls-files", "--sparse", "--stage")
        if not any(line.startswith("040000") for line in staged.splitlines()):
            pytest.skip("git build did not produce a sparse-directory index entry")

        monkeypatch.chdir(tmp_path)
        # Setup proof (replace refs forced on above): a replace-honoring
        # ls-files expands the sparse tree through the replacement, resolving
        # the path to the decoy oid. With the environment sanitized, reaching
        # the skip below means a genuine git-build limitation, not inherited
        # configuration.
        default_listed = subprocess.run(
            ["git", "ls-files", "-s", "-z", "--", f":(literal){skill_rel}"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        ).stdout
        default_oid = default_listed.split()[1].decode() if default_listed.strip() else ""
        if default_oid != small_oid:
            pytest.skip("git build does not resolve sparse tree entries through replace refs")
        assert big_oid != small_oid
        # The gate reads with --no-replace-objects on ls-files too, so it
        # resolves the real indexed blob and measures the oversized bytes.
        measured = read_staged_blob_bytes(Path(skill_rel))
        assert len(measured) > SKILL_BYTE_LIMIT
    def test_replace_ref_head_does_not_hide_staged_skill_from_discovery(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Discovery-side replace-refs (PR #3462 round-2 review): ``git diff
        # --cached`` honors ``refs/replace/`` by default. A replacement HEAD
        # whose tree already contains the oversized staged skill makes the diff
        # report no change for that path, dropping it from discovery while the
        # real commit still writes the index (including the oversized file).
        # Discovery must run with ``--no-replace-objects`` so it diffs the real
        # HEAD and still finds the file (exit 1).
        self._init_repo(tmp_path)
        # Real HEAD C0: a seed commit that does NOT contain the skill.
        (tmp_path / "README.md").write_bytes(b"seed\n")
        subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-qm", "seed"], cwd=tmp_path, check=True, capture_output=True
        )
        head = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=tmp_path,
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .strip()
        )
        # Stage the oversized skill: the index now differs from the real HEAD.
        self._write_skill(tmp_path, b"---\nname: big\n---\n" + b"x" * (SKILL_BYTE_LIMIT + 64))
        self._stage_all(tmp_path)
        # Doctored HEAD C0': a commit whose tree equals the current index, so it
        # already carries the oversized skill.
        index_tree = (
            subprocess.run(["git", "write-tree"], cwd=tmp_path, capture_output=True, check=True)
            .stdout.decode()
            .strip()
        )
        doctored = (
            subprocess.run(
                ["git", "commit-tree", index_tree, "-m", "doctored"],
                cwd=tmp_path,
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .strip()
        )
        subprocess.run(
            ["git", "update-ref", f"refs/replace/{head}", doctored],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        monkeypatch.chdir(tmp_path)
        # Setup proof: a default diff --cached honors the replacement, so a
        # replace-honoring discovery would not list the oversized skill.
        default_listed = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMRT"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        ).stdout
        assert b".claude/skills/big/SKILL.md" not in default_listed
        # The gate discovers with --no-replace-objects, so it diffs the real HEAD
        # and still finds the oversized file.
        discovered = {p.as_posix() for p in get_staged_skill_files()}
        assert ".claude/skills/big/SKILL.md" in discovered
        assert main(["--staged-only", "--ci"]) == 1

    def test_newline_in_staged_path_is_discovered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Finding 3 (newline path): a newline is a legal git path byte that ``-z``
        # keeps inside one NUL record. The prior ``^...$`` match (no DOTALL) let
        # ``.*`` stop at the newline, so a newline-bearing skill path failed the
        # match, dropped from discovery, and under-counted (exit 0). The
        # DOTALL/\Z pattern must still discover it. Driven through a stubbed
        # ``git diff`` so the newline path needs no filesystem staging (a newline
        # path is unstageable on some platforms).
        payload = b".claude/skills/ev\nil/SKILL.md\x00.claude/skills/ok/SKILL.md\x00"
        completed = subprocess.CompletedProcess(
            args=["git", "diff"], returncode=0, stdout=payload, stderr=b""
        )
        monkeypatch.setattr(_skill_size_mod.subprocess, "run", lambda *a, **k: completed)
        discovered = {p.as_posix() for p in get_staged_skill_files()}
        assert ".claude/skills/ev\nil/SKILL.md" in discovered
        assert ".claude/skills/ok/SKILL.md" in discovered

    def test_staged_mirror_tree_skill_is_discovered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Finding 4 (mirror-tree scope): the lefthook ``**/SKILL.md`` glob stages
        # both the canonical Claude tree and the generated Copilot mirror, but
        # discovery matched only ``.claude/skills``. An oversized staged mirror
        # SKILL.md was silently dropped (exit 0). The pattern must also cover
        # ``src/copilot-cli/skills``.
        self._init_repo(tmp_path)
        mirror = tmp_path / "src" / "copilot-cli" / "skills" / "big" / "SKILL.md"
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_bytes(b"---\nname: big\n---\n" + b"x" * (SKILL_BYTE_LIMIT + 64))
        self._stage_all(tmp_path)

        monkeypatch.chdir(tmp_path)
        discovered = {p.as_posix() for p in get_staged_skill_files()}
        assert "src/copilot-cli/skills/big/SKILL.md" in discovered
        assert main(["--staged-only", "--ci"]) == 1
