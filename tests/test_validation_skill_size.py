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
    RATIONALE_MIN_CHARS,
    RATIONALE_SEARCH_LINES,
    SKILL_BYTE_LIMIT,
    SKILL_BYTE_TARGET,
    SKILL_BYTE_WARNING,
    SKILL_SIZE_LIMIT,
    SKILL_SIZE_WARNING,
    StagedBlobError,
    StagedDiscoveryError,
    check_skill_size,
    get_staged_skill_files,
    has_exception_rationale,
    has_size_exception,
    main,
    read_staged_blob_bytes,
)

_FIXTURE_REASON = (
    "size-exception rationale for this fixture. The gate demands a stated reason "
    "beside a declared escape hatch, so a fixture that exercises the exception "
    "path must carry one too or it tests a shape the repository forbids."
)
_FIXTURE_COMMENT = f"<!--\n{_FIXTURE_REASON}\n-->\n"

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
            + _FIXTURE_COMMENT
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
            "---\nname: test\nsize-exception: true\n---\n"
            + _FIXTURE_COMMENT
            + ("x" * 600 + "\n") * 50,
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
        #
        # Both trees, not just .claude/skills (issue #4015): the generated
        # Copilot mirror ships skills too, and measuring one tree while claiming
        # the corpus is the reporting bug this test would otherwise repeat.
        # Bodies with a declared size-exception are skipped because the
        # validator downgrades them to a warning by design;
        # src/copilot-cli/skills/spec/SKILL.md is the live case at 69,383 bytes.
        repo_root = Path(__file__).resolve().parents[1]
        skills = sorted(
            skill
            for prefix in _skill_size_mod._SKILL_TREE_PREFIXES
            for skill in (repo_root / prefix).rglob("SKILL.md")
        )
        assert skills, "expected shipped skills under the skill trees"
        oversized = [
            (str(skill), len(raw))
            for skill in skills
            for raw in [skill.read_bytes()]
            if len(raw) > SKILL_BYTE_LIMIT
            and not has_size_exception(raw.decode("utf-8", errors="replace"))
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
            "---\nname: test\nsize-exception: true\n---\n" + _FIXTURE_COMMENT + "line\n" * 600
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
            "---\nname: test\nsize-exception: true\n---\n" + _FIXTURE_COMMENT + "x" * 500,
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
        skill.write_bytes(
            b"---\nname: big\nsize-exception: true\n---\n" + _FIXTURE_COMMENT.encode() + big
        )

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
            tmp_path,
            b"---\nname: big\nsize-exception: true\n---\n" + _FIXTURE_COMMENT.encode() + big,
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
        # Make this test's git environment hermetic so no inherited
        # configuration can disable replace refs (or redirect the repo, object
        # store, index, or config this guard depends on) and turn the setup
        # guard's skip into a silent mask over a real regression. git honors
        # refs/replace/ unless replace is disabled, and replace resolution can
        # be subverted through many channels that each outrank or bypass the
        # repo-local write below. Rather than enumerate them by hand (a
        # whack-a-mole that across review rounds missed GIT_NO_REPLACE_OBJECTS,
        # then command-scope -c injection, then GIT_CONFIG, then
        # GIT_TEMPLATE_DIR, then GIT_DIR/GIT_WORK_TREE), clear git's own
        # authoritative list of local-scope env vars, reported by
        # ``git rev-parse --local-env-vars``. That set covers
        # GIT_NO_REPLACE_OBJECTS, GIT_REPLACE_REF_BASE, GIT_CONFIG,
        # GIT_CONFIG_PARAMETERS, GIT_CONFIG_COUNT, GIT_DIR, GIT_WORK_TREE,
        # GIT_OBJECT_DIRECTORY, GIT_ALTERNATE_OBJECT_DIRECTORIES,
        # GIT_INDEX_FILE, GIT_COMMON_DIR, GIT_GRAFT_FILE, and every other var
        # git uses to resolve THIS repository. On top of that: the indexed
        # GIT_CONFIG_KEY_*/VALUE_* trio is neutralized because clearing
        # GIT_CONFIG_COUNT (in the list) makes git read zero injected pairs;
        # GIT_CONFIG_NOSYSTEM=1 disables system config outright;
        # GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM redirect at a nonexistent file
        # (git reads a missing config as empty); and GIT_TEMPLATE_DIR points at
        # an empty dir so no template [include] seeds
        # core.useReplaceRefs=false. git then falls back to its default of
        # replace ENABLED and the repo-local write reinforces it. Sanitize
        # before _init_repo so its identity writes and any template expansion
        # land in a clean repo-local .git/config. This closes the whole class,
        # bounded by git's own enumeration: a residual channel would have to be
        # a var git does not report as local (a git bug, not a test gap).
        _rev_parse_result = subprocess.run(
            ["git", "rev-parse", "--local-env-vars"],
            capture_output=True,
            text=True,
        )
        if _rev_parse_result.returncode != 0:
            pytest.skip("git build does not support --local-env-vars")
        _local_env_vars = _rev_parse_result.stdout.split()
        for _var in _local_env_vars:
            monkeypatch.delenv(_var, raising=False)
        _neutral_cfg = tmp_path / "hermetic-absent.gitconfig"
        _empty_template = tmp_path / "hermetic-empty-template"
        _empty_template.mkdir()
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(_neutral_cfg))
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(_neutral_cfg))
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        monkeypatch.setenv("GIT_TEMPLATE_DIR", str(_empty_template))
        self._init_repo(tmp_path)
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
        try:
            _git("sparse-checkout", "init", "--cone", "--sparse-index")
            _git("sparse-checkout", "set", "keep")
        except subprocess.CalledProcessError:
            pytest.skip("git build does not support sparse-checkout --sparse-index")
        # Prove the sparse-index setup actually produced a sparse-directory
        # entry (mode 040000): the .claude tree is outside the "keep" cone, so
        # it must collapse to a tree entry the gate has to expand. A git build
        # that does not produce one cannot stage this attack; skip there.
        try:
            staged = _git("ls-files", "--sparse", "--stage")
        except subprocess.CalledProcessError:
            pytest.skip("git build does not support ls-files --sparse")
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


# ---------------------------------------------------------------------------
# has_exception_rationale (Issue #3632)
# ---------------------------------------------------------------------------

_LONG_REASON = (
    "size-exception rationale. The 500-line ceiling in skill_size.py wants this "
    "body split into references/, but the overage predates this change and the "
    "split alters runtime behavior for every caller, so it needs its own tests "
    "rather than riding along here. Issue #3632 retires the key."
)


def _oversized(lines: int = SKILL_SIZE_LIMIT + 10) -> str:
    return "\n".join(f"line {n}" for n in range(lines))


def _doc(frontmatter: str, head: str = "", body: str | None = None) -> str:
    return f"---\n{frontmatter}\n---\n{head}\n{body if body is not None else _oversized()}"


class TestHasExceptionRationale:
    """Rationale detection for a declared size-exception."""

    def test_long_comment_in_head_qualifies(self) -> None:
        assert has_exception_rationale(f"<!--\n{_LONG_REASON}\n-->\nbody") is True

    def test_absent_comment_does_not_qualify(self) -> None:
        assert has_exception_rationale("---\nsize-exception: true\n---\nbody") is False

    def test_token_comment_is_too_short(self) -> None:
        assert has_exception_rationale("<!-- size-exception -->\nbody") is False

    def test_long_comment_without_the_keyword_does_not_qualify(self) -> None:
        unrelated = _LONG_REASON.replace("size-exception", "generation note")
        assert has_exception_rationale(f"<!--\n{unrelated}\n-->\nbody") is False

    def test_comment_opening_past_the_window_does_not_qualify(self) -> None:
        filler = "\n".join("x" for _ in range(RATIONALE_SEARCH_LINES + 5))
        assert has_exception_rationale(f"{filler}\n<!--\n{_LONG_REASON}\n-->") is False

    def test_comment_opening_inside_the_window_may_close_outside_it(self) -> None:
        padding = "\n".join(f"{_LONG_REASON} continued." for _ in range(60))
        content = f"<!--\n{_LONG_REASON}\n{padding}\n-->"
        assert content.count("\n") > RATIONALE_SEARCH_LINES
        assert has_exception_rationale(content) is True

    def test_empty_content_does_not_qualify(self) -> None:
        assert has_exception_rationale("") is False

    def test_keyword_match_is_case_insensitive(self) -> None:
        shouted = _LONG_REASON.replace("size-exception", "SIZE-EXCEPTION")
        assert has_exception_rationale(f"<!--\n{shouted}\n-->") is True

    def test_body_at_the_length_floor_qualifies(self) -> None:
        reason = "size-exception " + "j" * (RATIONALE_MIN_CHARS - len("size-exception "))
        assert len(reason) == RATIONALE_MIN_CHARS
        assert has_exception_rationale(f"<!--{reason}-->") is True

    def test_body_one_char_below_the_floor_does_not_qualify(self) -> None:
        reason = "size-exception " + "j" * (RATIONALE_MIN_CHARS - len("size-exception ") - 1)
        assert len(reason) == RATIONALE_MIN_CHARS - 1
        assert has_exception_rationale(f"<!--{reason}-->") is False


class TestExceptionRequiresRationale:
    """check_skill_size refuses an undocumented escape hatch."""

    def test_oversized_exception_without_rationale_fails(self, tmp_path: Path) -> None:
        target = tmp_path / "SKILL.md"
        target.write_text(_doc("name: big\nsize-exception: true"), encoding="utf-8")
        result = check_skill_size(target)
        assert result.passed is False
        assert any("no rationale" in e for e in result.errors)

    def test_oversized_exception_with_rationale_passes(self, tmp_path: Path) -> None:
        target = tmp_path / "SKILL.md"
        target.write_text(
            _doc("name: big\nsize-exception: true", head=f"<!--\n{_LONG_REASON}\n-->"),
            encoding="utf-8",
        )
        result = check_skill_size(target)
        assert result.passed is True
        assert result.warning is True

    def test_within_limits_exception_without_rationale_still_passes(self, tmp_path: Path) -> None:
        """A declared-but-unused exception is dead config, not a blocking defect."""
        target = tmp_path / "SKILL.md"
        target.write_text(_doc("name: small\nsize-exception: true", body="tiny"), encoding="utf-8")
        result = check_skill_size(target)
        assert result.passed is True

    def test_oversized_without_exception_reports_only_the_size_error(self, tmp_path: Path) -> None:
        target = tmp_path / "SKILL.md"
        target.write_text(_doc("name: big"), encoding="utf-8")
        result = check_skill_size(target)
        assert result.passed is False
        assert not any("no rationale" in e for e in result.errors)

    def test_byte_overage_alone_also_requires_a_rationale(self, tmp_path: Path) -> None:
        """The byte ceiling is an independent dimension and must gate the same way."""
        fat = "w" * (SKILL_BYTE_LIMIT + 100)
        target = tmp_path / "SKILL.md"
        target.write_text(_doc("name: fat\nsize-exception: true", body=fat), encoding="utf-8")
        assert len(fat.splitlines()) < SKILL_SIZE_LIMIT
        result = check_skill_size(target)
        assert result.passed is False
        assert any("no rationale" in e for e in result.errors)

    def test_shipped_spec_forms_carry_a_rationale(self) -> None:
        """The two files that hold the only live exceptions must stay documented."""
        root = Path(__file__).resolve().parents[1]
        for relative in (
            ".claude/commands/spec.md",
            "src/copilot-cli/skills/spec/SKILL.md",
        ):
            content = (root / relative).read_text(encoding="utf-8")
            assert has_size_exception(content), relative
            assert has_exception_rationale(content), relative


class TestDefaultScanCorpus:
    """The full scan measures every tree the staged scan matches (issue #4015).

    Before this, `--path` defaulted to `.claude/skills` and a full audit opened
    98 of 209 SKILL.md bodies, then printed "All skill files within size
    limits", a sentence about a corpus it had never read. The staged branch was
    already correct, so the gate never under-counted; the audit path did.

    These tests build a fake project root and point the module's `_PROJECT_ROOT`
    at it, so discovery runs against a controlled two-tree corpus with no git,
    no network, and no dependence on the live repository's contents.
    """

    @staticmethod
    def _write_skill(root: Path, prefix: str, name: str, body: str) -> Path:
        target = root / prefix / name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return target

    @staticmethod
    def _small() -> str:
        return "---\nname: test\n---\nSmall skill\n"

    @staticmethod
    def _oversized() -> str:
        return "---\nname: test\n---\n" + "line\n" * 600

    def _fake_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.delenv("SKILL_PATH", raising=False)
        monkeypatch.setattr(_skill_size_mod, "_PROJECT_ROOT", tmp_path)
        return tmp_path

    def test_default_scan_covers_both_trees(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = self._fake_root(tmp_path, monkeypatch)
        self._write_skill(root, ".claude/skills", "alpha", self._small())
        self._write_skill(root, "src/copilot-cli/skills", "beta", self._small())

        exit_code = main([])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Found 2 SKILL.md file(s)" in out
        assert "  Total:    2" in out

    def test_oversized_body_in_mirror_tree_only_fails_ci(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The regression guard. Against the single-tree default this returned 0
        # because the mirror body was never opened.
        root = self._fake_root(tmp_path, monkeypatch)
        self._write_skill(root, ".claude/skills", "alpha", self._small())
        self._write_skill(root, "src/copilot-cli/skills", "big", self._oversized())

        assert main(["--ci"]) == 1

    def test_explicit_path_still_narrows_the_scan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # --path stays the narrowing override: the oversized mirror body is out
        # of scope when the caller names one tree.
        root = self._fake_root(tmp_path, monkeypatch)
        self._write_skill(root, ".claude/skills", "alpha", self._small())
        self._write_skill(root, "src/copilot-cli/skills", "big", self._oversized())

        assert main(["--ci", "--path", str(root / ".claude" / "skills")]) == 0

    def test_skill_path_env_var_still_narrows_the_scan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._fake_root(tmp_path, monkeypatch)
        self._write_skill(root, ".claude/skills", "alpha", self._small())
        self._write_skill(root, "src/copilot-cli/skills", "big", self._oversized())
        monkeypatch.setenv("SKILL_PATH", str(root / ".claude" / "skills"))

        assert main(["--ci"]) == 0

    def test_absent_tree_is_named_and_survivor_is_still_measured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A vendored install legitimately ships one tree, so an absent prefix is
        # not a failure. It is named, because silence about an unscanned tree is
        # what let the single-tree scan read as a whole-repository result.
        root = self._fake_root(tmp_path, monkeypatch)
        self._write_skill(root, ".claude/skills", "alpha", self._small())

        exit_code = main(["--ci"])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Scanning skill trees: .claude/skills" in out
        assert "absent, not scanned: src/copilot-cli/skills" in out
        assert "  Total:    1" in out

    def test_no_trees_present_reports_nothing_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._fake_root(tmp_path, monkeypatch)

        exit_code = main(["--ci"])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "(none present)" in out
        assert "No SKILL.md files found to validate." in out

    def test_default_corpus_files_is_anchored_on_project_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # cwd-independence (.claude/rules/ci-scripts.md MUST-8): running the
        # audit from a subdirectory must not change which corpus it measures.
        root = self._fake_root(tmp_path, monkeypatch)
        self._write_skill(root, ".claude/skills", "alpha", self._small())
        self._write_skill(root, "src/copilot-cli/skills", "beta", self._small())
        monkeypatch.chdir(root / "src")

        found = _skill_size_mod.default_corpus_files()

        assert [path.name for path in found] == ["SKILL.md", "SKILL.md"]
        assert {path.parent.name for path in found} == {"alpha", "beta"}
