"""Tests for scripts/validation/check_io_portability.py.

The rules are pure AST checks, so most tests feed source text to
``scan_source``. Diff scope and the gate entry run against a throwaway git
repository in ``tmp_path``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation import check_io_portability as checker

TEST_PATH = "tests/test_sample.py"
CODE_PATH = "scripts/sample.py"


def rules(source: str, path: str = TEST_PATH) -> list[str]:
    return [v.rule for v in checker.scan_source(path, source)]


class TestSubprocessTextEncoding:
    def test_text_mode_without_encoding_is_flagged(self) -> None:
        source = "import subprocess\nsubprocess.run(['git'], text=True)\n"

        assert rules(source) == ["subprocess-text-encoding"]

    def test_text_mode_with_a_none_encoding_is_flagged(self) -> None:
        source = "import subprocess\nsubprocess.run(['git'], text=True, encoding=None)\n"

        assert rules(source) == ["subprocess-text-encoding"]

    def test_universal_newlines_without_encoding_is_flagged(self) -> None:
        source = "import subprocess\nsubprocess.check_output(['git'], universal_newlines=True)\n"

        assert rules(source) == ["subprocess-text-encoding"]

    def test_text_mode_with_encoding_passes(self) -> None:
        source = (
            "import subprocess\n"
            "subprocess.run(['git'], text=True, encoding='utf-8', errors='replace')\n"
        )

        assert rules(source) == []

    def test_bytes_mode_passes(self) -> None:
        source = "import subprocess\nsubprocess.run(['git'], capture_output=True)\n"

        assert rules(source) == []

    def test_star_kwargs_is_not_judged(self) -> None:
        source = "import subprocess\nsubprocess.run(['git'], text=True, **opts)\n"

        assert rules(source) == []

    def test_aliased_module_and_imported_name_are_tracked(self) -> None:
        source = (
            "import subprocess as sp\nfrom subprocess import run as go\n"
            "sp.Popen(['a'], text=True)\ngo(['b'], text=True)\n"
        )

        assert rules(source) == ["subprocess-text-encoding", "subprocess-text-encoding"]

    def test_unrelated_run_method_is_ignored(self) -> None:
        source = "runner.run(['git'], text=True)\n"

        assert rules(source) == []


class TestFileTextEncoding:
    @pytest.mark.parametrize(
        "call",
        [
            "p.read_text()",
            "p.write_text('x')",
            "open('f')",
            "open('f', 'w')",
            "open(file='f', mode='w')",
            "p.read_text(encoding=None)",
            "p.read_text(None)",
            "p.write_text('x', None)",
            "open('f', 'w', -1, None)",
        ],
    )
    def test_text_io_without_encoding_is_flagged(self, call: str) -> None:
        assert rules(f"{call}\n") == ["file-text-encoding"]

    @pytest.mark.parametrize(
        "call",
        [
            "p.read_text(encoding='utf-8')",
            "p.write_text('x', encoding='utf-8')",
            "p.write_text('x', 'utf-8')",
            "open('f', 'rb')",
            "open('f', mode='wb')",
            "open(file='f', mode='rb')",
            "open(*args)",
            "open('f', *rest)",
            "p.read_text(*opts)",
            "p.write_text('x', *opts)",
            "open('f', encoding='utf-8')",
            "open('f', 'r', -1, 'utf-8')",
            "open('f', computed_mode)",
            "zf.open('member')",
            "p.read_bytes()",
        ],
    )
    def test_explicit_encoding_binary_or_unjudgeable_passes(self, call: str) -> None:
        assert rules(f"{call}\n") == []

    def test_rule_applies_outside_test_paths(self) -> None:
        assert rules("p.read_text()\n", CODE_PATH) == ["file-text-encoding"]


class TestScanSource:
    def test_suppression_comment_silences_its_line(self) -> None:
        assert rules("p.read_text()  # io-portability: ignore fixture bytes\n") == []

    def test_suppression_line_survives_a_form_feed_earlier_in_the_file(self) -> None:
        source = "# section\x0c break\np.read_text()  # io-portability: ignore fixture\n"

        assert rules(source) == []

    def test_a_marker_inside_a_string_does_not_suppress(self) -> None:
        source = "p.write_text('# io-portability: ignore example')\n"

        assert rules(source) == ["file-text-encoding"]

    def test_suppression_line_survives_a_lone_carriage_return_line_end(self) -> None:
        source = "x = 1\rp.read_text()  # io-portability: ignore fixture\r"

        assert rules(source) == []

    def test_suppression_without_a_reason_does_not_silence(self) -> None:
        assert rules("p.read_text()  # io-portability: ignore\n") == ["file-text-encoding"]

    def test_syntax_error_yields_nothing(self) -> None:
        assert rules("def broken(:\n") == []

    def test_multiline_call_spans_first_to_last_line(self) -> None:
        source = "import subprocess\nsubprocess.run(\n    ['git'],\n    text=True,\n)\n"

        (violation,) = checker.scan_source(TEST_PATH, source)

        assert (violation.line, violation.end_line) == (2, 5)
        assert violation.spans(5) and not violation.spans(6)


class TestMirrorPrefixes:
    def test_mirror_prefixes_match_the_generated_mirror_map(self) -> None:
        from scripts.validation.git_hook_policy import _GENERATED_MIRRORS

        python_trees = ("/skills/", "/lib/", "/hooks/")
        generated = {
            output
            for output, _source, _suffix in _GENERATED_MIRRORS
            if output.startswith("src/") and any(output.endswith(t) for t in python_trees)
        }
        expected = (generated - {"src/claude/skills/"}) | {"src/hermes/"}

        assert set(checker.MIRROR_PREFIXES) == expected

    def test_canonical_skill_scripts_are_checked(self) -> None:
        assert not checker.is_skipped_path("src/claude/skills/x/scripts/y.py")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "old.py").write_text("p.read_text()\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "branch", "base")
    return tmp_path


def _commit(repo: Path, rel: str, text: str) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", f"edit {rel}")


class TestScanDiff:
    def test_only_lines_the_branch_commits_add_are_reported(self, repo: Path) -> None:
        _commit(repo, "old.py", "p.read_text()\nq.write_text('x')\n")

        found, examined = checker.scan_diff("base", repo)

        assert [(v.path, v.line) for v in found] == [("old.py", 2)]
        assert examined == 1

    def test_mirror_and_fixture_trees_are_skipped(self, repo: Path) -> None:
        _commit(repo, "src/cursor/skills/s/x.py", "p.read_text()\n")
        _commit(repo, "tests/fixtures/x.py", "p.read_text()\n")

        found, examined = checker.scan_diff("base", repo)

        assert (found, examined) == ([], 0)

    def test_added_lines_in_a_renamed_file_are_checked(self, repo: Path) -> None:
        body = "".join(f"value_{i} = {i}\n" for i in range(30))
        _commit(repo, "a.py", body)
        _git(repo, "branch", "-f", "base")
        _git(repo, "mv", "a.py", "b.py")
        _commit(repo, "b.py", body + "q.read_text()\n")

        found, _ = checker.scan_diff("base", repo)

        assert [(v.path, v.line) for v in found] == [("b.py", 31)]

    @pytest.mark.parametrize(
        ("key", "value"),
        [("diff.noprefix", "true"), ("diff.mnemonicPrefix", "true"), ("color.diff", "always")],
    )
    def test_contributor_diff_config_cannot_empty_the_scan(
        self, repo: Path, key: str, value: str
    ) -> None:
        _git(repo, "config", key, value)
        _commit(repo, "new.py", "open('f')\n")

        found, examined = checker.scan_diff("base", repo)

        assert (len(found), examined) == (1, 1)

    def test_uncommitted_violation_does_not_block(self, repo: Path) -> None:
        _commit(repo, "c.py", "x = 1\n")
        (repo / "c.py").write_text("x = 1\nopen('f')\n", encoding="utf-8")

        assert checker.scan_diff("base", repo)[0] == []

    def test_uncommitted_fix_does_not_hide_a_committed_violation(self, repo: Path) -> None:
        _commit(repo, "c.py", "open('f')\n")
        (repo / "c.py").write_text("open('f', encoding='utf-8')\n", encoding="utf-8")

        assert len(checker.scan_diff("base", repo)[0]) == 1

    def test_added_line_numbers_reads_an_explicit_commit_pair(self, repo: Path) -> None:
        _commit(repo, "c.py", "x = 1\nopen('f')\n")
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout.strip()
        _commit(repo, "c.py", "x = 1\nopen('f')\ny = 2\n")

        added = checker.added_line_numbers(repo, "base", head)

        assert added == {"c.py": {1, 2}}

    def test_a_line_moved_unchanged_is_not_new(self, repo: Path) -> None:
        _commit(repo, "old.py", "x = 1\np.read_text()\n")

        assert checker.scan_diff("base", repo)[0] == []

    def test_a_violation_moved_below_other_lines_is_not_new(self, repo: Path) -> None:
        _commit(repo, "old.py", "p.read_text()\nx = 1\ny = 2\n")
        _git(repo, "branch", "-f", "base")
        _commit(repo, "old.py", "x = 1\ny = 2\np.read_text()\n")

        found, _ = checker.scan_diff("base", repo)

        assert found == []

    def test_a_moved_line_that_changes_is_new(self, repo: Path) -> None:
        _commit(repo, "old.py", "p.read_text()\nx = 1\ny = 2\n")
        _git(repo, "branch", "-f", "base")
        _commit(repo, "old.py", "x = 1\ny = 2\nq.read_text()\n")

        found, _ = checker.scan_diff("base", repo)

        assert [(v.path, v.line) for v in found] == [("old.py", 3)]

    def test_unknown_base_raises(self, repo: Path) -> None:
        with pytest.raises(ValueError, match="no-such-ref"):
            checker.scan_diff("no-such-ref", repo)


class TestGateEntry:
    def test_clean_branch_passes(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            sys.modules["checks_common"], "_resolve_default_base_ref", lambda _root: "base"
        )

        assert checker.validate_io_portability(repo) is True

    def test_violation_fails(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            sys.modules["checks_common"], "_resolve_default_base_ref", lambda _root: "base"
        )
        _commit(repo, "new.py", "open('f')\n")

        assert checker.validate_io_portability(repo) is False

    def test_no_base_ref_skips(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            sys.modules["checks_common"], "_resolve_default_base_ref", lambda _root: None
        )

        assert checker.validate_io_portability(repo) is True

    def test_git_failure_fails(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            sys.modules["checks_common"], "_resolve_default_base_ref", lambda _root: "missing"
        )

        assert checker.validate_io_portability(repo) is False


class TestMain:
    def test_files_with_violation_exit_1_and_print_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "a.py"
        target.write_text("open('f')\n", encoding="utf-8")

        code = checker.main([str(target)])

        assert code == 1
        assert "1 io-portability violation(s) in 1 file(s) examined" in capsys.readouterr().out

    def test_clean_file_exits_0(self, tmp_path: Path) -> None:
        target = tmp_path / "a.py"
        target.write_text("open('f', encoding='utf-8')\n", encoding="utf-8")

        assert checker.main([str(target)]) == 0

    @pytest.mark.parametrize("argv", [[], ["a.py", "--base-ref", "main"]])
    def test_neither_or_both_scopes_exit_2(self, argv: list[str]) -> None:
        assert checker.main(argv) == 2

    def test_base_ref_run_from_a_subdirectory_sees_the_whole_diff(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _commit(repo, "pkg/inner/a.py", "open('f')\n")
        _commit(repo, "top.py", "open('g')\n")
        monkeypatch.chdir(repo / "pkg")

        assert checker.main(["--base-ref", "base"]) == 1

    def test_base_ref_run_on_a_clean_branch_exits_0(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _commit(repo, "pkg/a.py", "open('f', encoding='utf-8')\n")
        monkeypatch.chdir(repo / "pkg")

        assert checker.main(["--base-ref", "base"]) == 0

    def test_git_that_cannot_run_is_a_config_error(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def timeout(*_a: object, **_k: object) -> None:
            raise subprocess.TimeoutExpired("git", 60)

        monkeypatch.setattr(subprocess, "run", timeout)

        with pytest.raises(ValueError, match="could not run"):
            checker.repository_root()

    def test_base_ref_run_exits_2_when_git_times_out(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(repo)

        def timeout(*_a: object, **_k: object) -> None:
            raise subprocess.TimeoutExpired("git", 60)

        monkeypatch.setattr(subprocess, "run", timeout)

        assert checker.main(["--base-ref", "base"]) == 2

    def test_base_ref_run_exits_2_when_the_diff_fails(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(repo)

        def failing(_root: object, base: str, head: str = "HEAD") -> dict[str, set[int]]:
            raise ValueError(f"git diff {base}...{head} failed")

        monkeypatch.setattr(checker, "added_line_numbers", failing)

        assert checker.main(["--base-ref", "base"]) == 2

    def test_unreadable_file_exits_2(self, tmp_path: Path) -> None:
        assert checker.main([str(tmp_path / "missing.py")]) == 2
