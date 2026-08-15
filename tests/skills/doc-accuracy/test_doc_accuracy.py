#!/usr/bin/env python3
# taste-lint: ignore file-size
# This file covers a wide surface (inventory, changed-files filter, link checks,
# freshness, symlink, real-git integration). 522 lines for 48 test cases is the
# right granularity; splitting the file would spread related fixtures.
"""Tests for doc_accuracy module."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/doc-accuracy/scripts/doc_accuracy.py",
    module_name="doc_accuracy",
)
SourceSymbol = mod.SourceSymbol
DocFile = mod.DocFile
Claim = mod.Claim
Finding = mod.Finding
run_assessment = mod.run_assessment
run_claim_extraction = mod.run_claim_extraction
run_compilability_check = mod.run_compilability_check
check_gate = mod.check_gate
generate_markdown_report = mod.generate_markdown_report
main = mod.main
_should_exclude = mod._should_exclude
_detect_language = mod._detect_language
_extract_identifiers = mod._extract_identifiers
_extract_quantitative_claims = mod._extract_quantitative_claims
_extract_python_symbols = mod._extract_python_symbols
_extract_csharp_symbols = mod._extract_csharp_symbols
_count_code_blocks = mod._count_code_blocks
_get_changed_files = mod._get_changed_files
_git_env = mod._git_env
_iter_git_files = mod._iter_git_files
_repo_relative = mod._repo_relative


def test_exit_code_documentation_covers_the_cli_contract() -> None:
    """Canonical skill cites its bundled script and lists every exit code."""
    contract = """Exit Codes:
    0: No findings at or above severity threshold
    1: Error or inconclusive run, including no source symbols for Phase 3
    2: Configuration error, including an invalid --diff-base
    3: External dependency failure, including unavailable or failed Git
    10: Findings at or above severity threshold"""
    skill_path = Path(mod.__file__).resolve().parents[1] / "SKILL.md"
    skill_docs = skill_path.read_text(encoding="utf-8")
    source_citation = (
        "Canonical source bundled with this skill:\n\n"
        "```text\n"
        "scripts/doc_accuracy.py\n"
        "```"
    )

    assert contract in (mod.__doc__ or "")
    assert source_citation in skill_docs
    assert (skill_path.parent / "scripts" / "doc_accuracy.py").is_file()
    assert f"```text\n{contract}\n```" in skill_docs


class TestShouldExclude:
    def test_excludes_git(self) -> None:
        assert _should_exclude(Path(".git/config"))

    def test_excludes_node_modules(self) -> None:
        assert _should_exclude(Path("node_modules/pkg/index.js"))

    def test_allows_normal_path(self) -> None:
        assert not _should_exclude(Path("src/main.py"))

    def test_excludes_doc_accuracy_output(self) -> None:
        assert _should_exclude(Path(".doc-accuracy/report.json"))


class TestDetectLanguage:
    def test_python(self) -> None:
        assert _detect_language("python") == "python"

    def test_py_alias(self) -> None:
        assert _detect_language("py") == "python"

    def test_csharp(self) -> None:
        assert _detect_language("csharp") == "csharp"

    def test_cs_alias(self) -> None:
        assert _detect_language("cs") == "csharp"

    def test_empty_string(self) -> None:
        assert _detect_language("") == ""

    def test_unknown_returns_token(self) -> None:
        assert _detect_language("fortran") == "fortran"


class TestExtractIdentifiers:
    def test_camel_case(self) -> None:
        result = _extract_identifiers("var x = MyClass.DoSomething();")
        assert "MyClass" in result
        assert "DoSomething" in result

    def test_method_calls(self) -> None:
        result = _extract_identifiers("obj.process(data)")
        assert "process" in result

    def test_named_params(self) -> None:
        result = _extract_identifiers("Foo(name: value)")
        assert "name" in result


class TestExtractQuantitativeClaims:
    def test_percentage(self) -> None:
        result = _extract_quantitative_claims("Achieves 95.5% accuracy")
        assert any("95.5%" in c for c in result)

    def test_timing(self) -> None:
        result = _extract_quantitative_claims("Response time is 100ms")
        assert any("100ms" in c for c in result)

    def test_no_claims(self) -> None:
        assert _extract_quantitative_claims("No numbers here") == []

    def test_comparison(self) -> None:
        result = _extract_quantitative_claims("Latency <5%")
        assert len(result) > 0


class TestCountCodeBlocks:
    def test_counts_fenced_blocks(self) -> None:
        md = "```python\ncode\n```\n\n```js\nmore\n```\n"
        # Counts both opening and closing fence lines matching the pattern
        assert _count_code_blocks(md) == 4

    def test_no_blocks(self) -> None:
        assert _count_code_blocks("Just text") == 0


class TestExtractPythonSymbols:
    def test_extracts_class(self) -> None:
        code = "class MyClass:\n    pass\n"
        symbols = _extract_python_symbols(code, "test.py")
        assert len(symbols) == 1
        assert symbols[0].name == "MyClass"
        assert symbols[0].kind == "class"

    def test_extracts_function(self) -> None:
        code = "def process_data(x):\n    return x\n"
        symbols = _extract_python_symbols(code, "test.py")
        assert len(symbols) == 1
        assert symbols[0].name == "process_data"
        assert symbols[0].kind == "function"

    def test_skips_private(self) -> None:
        code = "def _private():\n    pass\n"
        symbols = _extract_python_symbols(code, "test.py")
        assert len(symbols) == 0

    def test_records_line_number(self) -> None:
        code = "\n\ndef foo():\n    pass\n"
        symbols = _extract_python_symbols(code, "test.py")
        assert symbols[0].line == 3


class TestExtractCsharpSymbols:
    def test_extracts_class(self) -> None:
        code = "    public class Foo\n    {\n    }\n"
        symbols = _extract_csharp_symbols(code, "Foo.cs")
        assert len(symbols) == 1
        assert symbols[0].name == "Foo"
        assert symbols[0].kind == "class"

    def test_extracts_method(self) -> None:
        code = "    public void DoWork(int x)\n    {\n    }\n"
        symbols = _extract_csharp_symbols(code, "Bar.cs")
        assert len(symbols) == 1
        assert symbols[0].name == "DoWork"
        assert symbols[0].kind == "method"


class TestSourceSymbol:
    def test_to_dict(self) -> None:
        sym = SourceSymbol(
            name="Foo", kind="class", file="a.py", line=1,
            signature="class Foo:",
        )
        d = sym.to_dict()
        assert d["name"] == "Foo"
        assert d["visibility"] == "public"


class TestRunAssessment:
    def test_scans_directory(self, tmp_path: Path) -> None:
        (tmp_path / ".git").write_text("gitdir: missing\n")
        (tmp_path / "README.md").write_text("# Hello\n`MyFunc`\n")
        (tmp_path / "main.py").write_text("def MyFunc():\n    pass\n")

        result = run_assessment(tmp_path)

        assert len(result["documentation_files"]) >= 1
        assert len(result["source_symbols"]) >= 1
        assert "coverage_summary" in result
        assert result["changed_files"] is None

    def test_diff_base_scopes_doc_inventory_to_changed_files(
        self, tmp_path: Path
    ) -> None:
        """diff_base must restrict assessed docs to files changed since that ref.

        Regression for issue #4520: changed_files was computed but never used
        to filter the doc inventory, so --diff-base reported the full backlog
        even when no documentation files changed.
        """
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=main"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Base commit: two markdown docs and one Python source
        (repo / "old.md").write_text("# Old doc\n")
        (repo / "unchanged.md").write_text("# Unchanged doc\n")
        (repo / "main.py").write_text("def foo():\n    pass\n")
        subprocess.run(
            ["git", "add", "old.md", "unchanged.md", "main.py"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "base"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Second commit: only old.md changed; unchanged.md not touched
        (repo / "old.md").write_text("# Old doc updated\n")
        subprocess.run(
            ["git", "add", "old.md"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "update doc"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        result = run_assessment(repo, diff_base="HEAD~1")

        doc_paths = [d["path"] for d in result["documentation_files"]]
        # Only old.md changed since HEAD~1; unchanged.md must be excluded.
        assert "old.md" in doc_paths
        assert "unchanged.md" not in doc_paths
        # Source files are always indexed regardless of diff_base.
        assert any(s["name"] == "foo" for s in result["source_symbols"])

    def test_diff_base_no_changed_docs_yields_empty_inventory(
        self, tmp_path: Path
    ) -> None:
        """When only non-doc files changed, the doc inventory is empty."""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=main"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        (repo / "doc.md").write_text("# Doc\n")
        (repo / "script.sh").write_text("#!/bin/bash\necho hi\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "base"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Only the shell script changed, not the doc
        (repo / "script.sh").write_text("#!/bin/bash\necho bye\n")
        subprocess.run(
            ["git", "add", "script.sh"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "update script"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        result = run_assessment(repo, diff_base="HEAD~1")

        doc_paths = [d["path"] for d in result["documentation_files"]]
        # doc.md was not changed; must not appear in the scoped inventory.
        assert "doc.md" not in doc_paths

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = run_assessment(tmp_path)
        assert result["documentation_files"] == []
        assert result["source_symbols"] == []
        assert result["coverage_summary"]["coverage_pct"] == 100.0

    def test_diff_base_scopes_docs_to_changed_files(self, tmp_path: Path) -> None:
        (tmp_path / "changed.md").write_text("# Changed\n`PublicThing`\n")
        (tmp_path / "unchanged.md").write_text("# Unchanged\n")
        (tmp_path / "code.py").write_text("def PublicThing():\n    pass\n")
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "t"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "t@t"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True, capture_output=True,
        )

        with patch.object(mod, "_get_changed_files", return_value={"changed.md"}):
            result = run_assessment(
                tmp_path,
                doc_globs=["*.md"],
                diff_base="origin/main",
            )

        doc_paths = {doc["path"] for doc in result["documentation_files"]}
        source_names = {symbol["name"] for symbol in result["source_symbols"]}
        assert doc_paths == {"changed.md"}
        assert result["changed_files"] == ["changed.md"]
        assert "PublicThing" in source_names

    def test_diff_base_empty_change_set_yields_no_docs(self, tmp_path: Path) -> None:
        (tmp_path / "unchanged.md").write_text("# Unchanged\n")
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "t"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "t@t"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True, capture_output=True,
        )

        with patch.object(mod, "_get_changed_files", return_value=set()):
            result = run_assessment(
                tmp_path,
                doc_globs=["*.md"],
                diff_base="origin/main",
            )

        assert result["documentation_files"] == []
        assert result["changed_files"] == []


class TestGetChangedFiles:
    """Tests for _get_changed_files and its integration via main()."""

    @staticmethod
    def _init_repo(path: Path) -> None:
        """Create a minimal git repo with one empty commit."""
        import os
        subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(path), "config", "user.name", "t"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "config", "user.email", "t@t"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "commit", "--allow-empty", "-m", "init"],
            check=True, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "t",
                 "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                 "GIT_COMMITTER_EMAIL": "t@t"},
        )

    def test_invalid_ref_exits_2(self, tmp_path: Path) -> None:
        """Invalid --diff-base is config error => exit 2 (ADR-035)."""
        self._init_repo(tmp_path)
        exit_code = main([
            "--target", str(tmp_path),
            "--diff-base", "no-such-ref",
            "--phases", "1",
        ])
        assert exit_code == 2

    def test_corrupt_object_db_exits_3(self, tmp_path: Path) -> None:
        """Valid ref but object-DB failure (rc 128) => exit 3."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def corrupt_verify(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "--verify" in cmd:
                raise subprocess.CalledProcessError(
                    128, cmd,
                    stderr="fatal: unable to read object: permission denied",
                )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=corrupt_verify):
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", "HEAD",
                "--phases", "1",
            ])
        assert exit_code == 3

    def test_ref_to_missing_object_exits_3(self, tmp_path: Path) -> None:
        """A resolved ref with a missing object is an external Git failure."""
        self._init_repo(tmp_path)
        missing_oid = "1234567890abcdef1234567890abcdef12345678"
        ref = tmp_path / ".git" / "refs" / "heads" / "missing-object"
        ref.write_text(f"{missing_oid}\n")

        exit_code = main([
            "--target", str(tmp_path),
            "--diff-base", "missing-object",
            "--phases", "1",
        ])

        assert exit_code == 3

    def test_localized_stderr_invalid_ref_exits_2(self, tmp_path: Path) -> None:
        """Localized git with rc1 (unresolved ref) => exit 2, not pattern match."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def localized_verify(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "--verify" in cmd:
                # Non-English stderr, but rc 1 signals unresolved ref
                raise subprocess.CalledProcessError(
                    1, cmd,
                    stderr="fatale: unbekannte Revision 'no-such-ref'",
                )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=localized_verify):
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", "no-such-ref",
                "--phases", "1",
            ])
        assert exit_code == 2

    def test_invalid_git_directory_exits_3(self, tmp_path: Path) -> None:
        """Invalid Git metadata is an environment error => exit 3."""
        repo = tmp_path / "not-a-repo"
        repo.mkdir()
        (repo / ".git").write_text("gitdir: missing\n")

        exit_code = main([
            "--target", str(repo),
            "--diff-base", "HEAD",
            "--phases", "1",
        ])
        assert exit_code == 3

    def test_bare_repo_exits_3(self, tmp_path: Path) -> None:
        """Bare repo returns rc0 with stdout 'false'; must still exit 3."""
        subprocess.run(
            ["git", "init", "--bare", str(tmp_path / "bare.git")],
            capture_output=True, check=True,
        )
        exit_code = main([
            "--target", str(tmp_path / "bare.git"),
            "--diff-base", "HEAD",
            "--phases", "1",
        ])
        assert exit_code == 3

    def test_worktree_false_stdout_exits_3(self, tmp_path: Path) -> None:
        """rev-parse rc0 but stdout 'false' (bare/non-worktree) => exit 3."""
        real_run = subprocess.run

        def mock_worktree_false(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "--is-inside-work-tree" in cmd:
                result = MagicMock()
                result.stdout = "false\n"
                result.returncode = 0
                return result
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        self._init_repo(tmp_path)
        with patch.object(subprocess, "run", side_effect=mock_worktree_false):
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", "HEAD",
                "--phases", "1",
            ])
        assert exit_code == 3

    def test_missing_git_exits_3(self, tmp_path: Path) -> None:
        """Missing git binary is an environment error => exit 3."""
        with patch.object(
            subprocess, "run",
            side_effect=FileNotFoundError("git not found"),
        ):
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", "HEAD",
                "--phases", "1",
            ])
        assert exit_code == 3

    def test_rev_parse_timeout_exits_3(self, tmp_path: Path) -> None:
        """Timeout during rev-parse is an environment error => exit 3."""
        with patch.object(
            subprocess, "run",
            side_effect=subprocess.TimeoutExpired("git", 60),
        ):
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", "HEAD",
                "--phases", "1",
            ])
        assert exit_code == 3

    def test_ls_files_timeout_exits_3(self, tmp_path: Path) -> None:
        """Timeout during ls-files (after diff succeeds) => exit 3."""
        self._init_repo(tmp_path)
        real_run = subprocess.run
        ls_files_timeout_seen: list[object] = []

        def selective_timeout(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "ls-files" in cmd:
                ls_files_timeout_seen.append(kwargs.get("timeout"))
                raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 60))
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=selective_timeout):
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", "HEAD",
                "--phases", "1",
            ])
        assert exit_code == 3
        # Verify timeout kwarg was actually passed to ls-files subprocess call
        assert ls_files_timeout_seen, "ls-files was never called"
        assert all(t is not None for t in ls_files_timeout_seen), (
            "ls-files subprocess.run called without timeout kwarg"
        )

    def test_ls_files_error_with_diff_base_exits_3(self, tmp_path: Path) -> None:
        """ls-files CalledProcessError in diff-base mode => exit 3, not rglob fallback."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def fail_ls_files(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "ls-files" in cmd:
                raise subprocess.CalledProcessError(
                    128, cmd, stderr="fatal: index corrupted",
                )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=fail_ls_files):
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", "HEAD",
                "--phases", "1",
            ])
        assert exit_code == 3

    def test_no_diff_base_ls_files_fallback_works(self, tmp_path: Path) -> None:
        """Without diff-base, ls-files failure falls back to rglob (exit 0)."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def fail_ls_files(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "ls-files" in cmd:
                raise subprocess.CalledProcessError(
                    128, cmd, stderr="fatal: index corrupted",
                )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=fail_ls_files):
            exit_code = main([
                "--target", str(tmp_path),
                "--phases", "1",
            ])
        assert exit_code == 0

    def test_valid_empty_diff_exits_0(self, tmp_path: Path) -> None:
        """Valid diff-base with no changed files passes (exit 0)."""
        self._init_repo(tmp_path)
        exit_code = main([
            "--target", str(tmp_path),
            "--diff-base", "HEAD",
            "--phases", "1",
        ])
        assert exit_code == 0

    def test_changed_diff_exits_0(self, tmp_path: Path) -> None:
        """Valid diff-base with actual changes still passes."""
        import os
        self._init_repo(tmp_path)
        (tmp_path / "README.md").write_text("# Hello\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "README.md"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "add readme"],
            check=True, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "t",
                 "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                 "GIT_COMMITTER_EMAIL": "t@t"},
        )
        exit_code = main([
            "--target", str(tmp_path),
            "--diff-base", "HEAD~1",
            "--phases", "1",
        ])
        assert exit_code == 0

    def test_ignores_blank_diff_lines(self, tmp_path: Path) -> None:
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def selective_mock(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "diff" in cmd and "--name-only" in cmd:
                result = MagicMock()
                result.stdout = b"doc.md\x00\x00script.py\x00"
                result.returncode = 0
                return result
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=selective_mock):
            result = _get_changed_files("HEAD", tmp_path)

        assert result == {"doc.md", "script.py"}

    def test_unicode_and_newline_paths(self, tmp_path: Path) -> None:
        """Files with Unicode and special chars are returned via -z output."""
        self._init_repo(tmp_path)
        unicode_file = tmp_path / "\u00e9l\u00e8ve.md"
        newline_file = tmp_path / "line\nbreak.md"
        unicode_file.write_text("# Unicode\n")
        newline_file.write_text("# Newline\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "unicode"],
            check=True, capture_output=True,
        )
        changed = _get_changed_files("HEAD~1", tmp_path)
        assert "\u00e9l\u00e8ve.md" in changed
        assert "line\nbreak.md" in changed
        exit_code = main([
            "--target", str(tmp_path),
            "--diff-base", "HEAD~1",
            "--phases", "1",
        ])
        assert exit_code == 0

    def test_non_utf8_path_round_trips_through_nul_output(
        self, tmp_path: Path
    ) -> None:
        """NUL-delimited Git bytes use filesystem surrogate decoding."""
        import os

        if os.name == "nt":
            return
        self._init_repo(tmp_path)
        raw_name = b"invalid-\xff.md"
        raw_path = os.fsencode(tmp_path) + b"/" + raw_name
        fd = os.open(raw_path, os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(fd, b"# Invalid bytes\n")
        finally:
            os.close(fd)
        subprocess.run(
            [b"git", b"-C", os.fsencode(tmp_path), b"add", b"."],
            check=True, capture_output=True,
        )
        subprocess.run(
            [b"git", b"-C", os.fsencode(tmp_path), b"commit", b"-m", b"bytes"],
            check=True, capture_output=True,
        )

        expected = os.fsdecode(raw_name)
        assert expected in _get_changed_files("HEAD~1", tmp_path)
        tracked = {
            _repo_relative(path, tmp_path)
            for path in _iter_git_files(tmp_path, require_git=True)
        }
        assert expected in tracked

    def test_foreign_git_dir_ignored(self, tmp_path: Path) -> None:
        """GIT_DIR env var pointing elsewhere does not affect result."""
        self._init_repo(tmp_path)
        (tmp_path / "a.md").write_text("# A\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "add a"],
            check=True, capture_output=True,
        )
        # Set GIT_DIR to a bogus location; should be sanitized
        import os as _os
        old = _os.environ.get("GIT_DIR")
        _os.environ["GIT_DIR"] = "/nonexistent/.git"
        try:
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", "HEAD~1",
                "--phases", "1",
            ])
        finally:
            if old is None:
                _os.environ.pop("GIT_DIR", None)
            else:
                _os.environ["GIT_DIR"] = old
        assert exit_code == 0

    def test_git_config_count_injection_blocked(self, tmp_path: Path) -> None:
        """Malicious core.fsmonitor via GIT_CONFIG_COUNT cannot execute."""
        self._init_repo(tmp_path)
        (tmp_path / "a.md").write_text("# A\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True, capture_output=True,
        )
        sentinel = tmp_path / "pwned_sentinel"
        sentinel.unlink(missing_ok=True)
        import os as _os
        injections = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.fsmonitor",
            "GIT_CONFIG_VALUE_0": f"echo pwned > {sentinel}",
        }
        old_vals: dict[str, str | None] = {}
        for k, v in injections.items():
            old_vals[k] = _os.environ.get(k)
            _os.environ[k] = v
        try:
            subprocess.run(
                ["git", "-C", str(tmp_path), "status", "--porcelain"],
                check=True, capture_output=True,
            )
            assert sentinel.exists(), "config-count fsmonitor probe did not execute"
            sentinel.unlink()
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", "HEAD~1",
                "--phases", "1",
            ])
        finally:
            for k in injections:
                old_value = old_vals[k]
                if old_value is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = old_value
        assert exit_code == 0
        assert not sentinel.exists(), "fsmonitor injection executed despite env sanitization"

    def test_global_fsmonitor_config_is_ignored(self, tmp_path: Path) -> None:
        """User-level core.fsmonitor cannot execute during the scan."""
        import os

        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_repo(repo)
        (repo / "a.md").write_text("# A\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", "."],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add a"],
            check=True, capture_output=True,
        )

        sentinel = tmp_path / "global-fsmonitor-ran"
        hook = tmp_path / "global-fsmonitor.py"
        hook.write_text(
            f"#!{sys.executable}\n"
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('ran')\n",
        )
        hook.chmod(0o755)
        home = tmp_path / "home"
        home.mkdir()
        subprocess.run(
            [
                "git", "config", "--file", str(home / ".gitconfig"),
                "core.fsmonitor", str(hook),
            ],
            check=True, capture_output=True,
        )
        inherited_env = os.environ.copy()
        inherited_env["HOME"] = str(home)
        inherited_env.pop("GIT_CONFIG_GLOBAL", None)
        inherited_env.pop("GIT_CONFIG_NOSYSTEM", None)
        subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            check=True, capture_output=True,
            env=inherited_env,
        )
        assert sentinel.exists(), "global fsmonitor probe did not execute"
        sentinel.unlink()

        with patch.dict(os.environ, inherited_env, clear=True):
            exit_code = main([
                "--target", str(repo),
                "--diff-base", "HEAD~1",
                "--phases", "1",
            ])
        assert exit_code == 0
        assert not sentinel.exists()

    def test_system_fsmonitor_config_is_ignored(self, tmp_path: Path) -> None:
        """System-level core.fsmonitor cannot execute during the scan."""
        import os

        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_repo(repo)
        (repo / "a.md").write_text("# A\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", "."],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add a"],
            check=True, capture_output=True,
        )

        sentinel = tmp_path / "system-fsmonitor-ran"
        hook = tmp_path / "system-fsmonitor.py"
        hook.write_text(
            f"#!{sys.executable}\n"
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('ran')\n",
        )
        hook.chmod(0o755)
        system_config = tmp_path / "system.gitconfig"
        subprocess.run(
            [
                "git", "config", "--file", str(system_config),
                "core.fsmonitor", str(hook),
            ],
            check=True, capture_output=True,
        )
        inherited_env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": str(system_config),
        }
        inherited_env.pop("GIT_CONFIG_NOSYSTEM", None)
        subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            check=True, capture_output=True,
            env=inherited_env,
        )
        assert sentinel.exists(), "system fsmonitor probe did not execute"
        sentinel.unlink()

        with patch.dict(os.environ, inherited_env, clear=True):
            exit_code = main([
                "--target", str(repo),
                "--diff-base", "HEAD~1",
                "--phases", "1",
            ])
        assert exit_code == 0
        assert not sentinel.exists()

    def test_repository_fsmonitor_config_is_disabled(self, tmp_path: Path) -> None:
        """Repository-local core.fsmonitor cannot execute during the scan."""
        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_repo(repo)
        (repo / "a.md").write_text("# A\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", "."],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add a"],
            check=True, capture_output=True,
        )

        sentinel = tmp_path / "local-fsmonitor-ran"
        hook = tmp_path / "local-fsmonitor.py"
        hook.write_text(
            f"#!{sys.executable}\n"
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('ran')\n",
        )
        hook.chmod(0o755)
        subprocess.run(
            ["git", "-C", str(repo), "config", "core.fsmonitor", str(hook)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            check=True, capture_output=True,
        )
        assert sentinel.exists(), "repository fsmonitor probe did not execute"
        sentinel.unlink()

        exit_code = main([
            "--target", str(repo),
            "--diff-base", "HEAD~1",
            "--phases", "1",
        ])
        assert exit_code == 0
        assert not sentinel.exists()

    def test_graft_replace_shallow_overrides_ignored(self, tmp_path: Path) -> None:
        """GIT_GRAFT_FILE/REPLACE_REF_BASE/SHALLOW_FILE do not alter results."""
        self._init_repo(tmp_path)
        (tmp_path / "a.md").write_text("# A\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True, capture_output=True,
        )
        import os as _os
        overrides = {
            "GIT_GRAFT_FILE": "/nonexistent/grafts",
            "GIT_REPLACE_REF_BASE": "refs/replace-evil/",
            "GIT_SHALLOW_FILE": "/nonexistent/shallow",
        }
        old_vals: dict[str, str | None] = {}
        for k, v in overrides.items():
            old_vals[k] = _os.environ.get(k)
            _os.environ[k] = v
        try:
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", "HEAD~1",
                "--phases", "1",
            ])
        finally:
            for k in overrides:
                old_value = old_vals[k]
                if old_value is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = old_value
        assert exit_code == 0

    def test_git_env_sanitizes_local_and_config_vars_case_insensitively(
        self,
    ) -> None:
        """Git overrides cannot survive with Windows-style key casing."""
        import os as _os

        local_vars = [
            "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG",
            "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
            "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE",
            "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE", "GIT_INDEX_FILE",
            "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE", "GIT_PREFIX",
            "GIT_SHALLOW_FILE", "GIT_COMMON_DIR",
            "git_dir", "Git_Work_Tree", "git_object_directory",
        ]
        prefix_vars = ["GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0",
                       "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
                       "Git_Config_Arbitrary", "git_config_key_99"]
        all_test = local_vars + prefix_vars
        saved: dict[str, str | None] = {k: _os.environ.get(k) for k in all_test}
        for k in all_test:
            _os.environ[k] = "injected"
        try:
            env = _git_env()
        finally:
            for k in all_test:
                saved_value = saved[k]
                if saved_value is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = saved_value
        forced = {
            "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
            "GIT_GRAFT_FILE", "GIT_NO_REPLACE_OBJECTS", "GIT_SHALLOW_FILE",
        }
        for key in env:
            normalized = key.upper()
            if normalized.startswith("GIT_CONFIG_"):
                assert normalized in forced
        assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert env["GIT_GRAFT_FILE"] == _os.devnull
        assert env["GIT_SHALLOW_FILE"] == _os.devnull

    def test_repository_replace_ref_cannot_hide_changed_file(
        self, tmp_path: Path
    ) -> None:
        """A repository replace ref cannot rewrite the diff-base tree."""
        self._init_repo(tmp_path)
        base = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        (tmp_path / "changed.md").write_text("# Changed\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "changed"],
            check=True, capture_output=True,
        )
        head_tree = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD^{tree}"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        replacement = subprocess.run(
            ["git", "-C", str(tmp_path), "commit-tree", head_tree],
            check=True, capture_output=True, text=True,
            input="replacement\n",
        ).stdout.strip()
        subprocess.run(
            ["git", "-C", str(tmp_path), "replace", base, replacement],
            check=True, capture_output=True,
        )
        unsanitized = subprocess.run(
            [
                "git", "-C", str(tmp_path),
                "diff", "--name-only", base, "HEAD", "--",
            ],
            check=True, capture_output=True, text=True,
        )
        assert unsanitized.stdout == "", "replace ref probe did not hide the file"

        assert "changed.md" in _get_changed_files(base, tmp_path)

    def test_repository_graft_and_shallow_files_are_ignored(
        self, tmp_path: Path
    ) -> None:
        """Repository graft and shallow metadata cannot hide HEAD's parent."""
        self._init_repo(tmp_path)
        (tmp_path / "changed.md").write_text("# Changed\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "changed"],
            check=True, capture_output=True,
        )
        head = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        git_dir = tmp_path / ".git"
        (git_dir / "info" / "grafts").write_text(f"{head}\n")
        (git_dir / "shallow").write_text(f"{head}\n")
        unsanitized = subprocess.run(
            [
                "git", "-C", str(tmp_path),
                "rev-parse", "--verify", "--quiet", "HEAD~1^{commit}",
            ],
            capture_output=True,
        )
        assert unsanitized.returncode != 0, (
            "graft/shallow probe did not hide HEAD's parent"
        )

        assert "changed.md" in _get_changed_files("HEAD~1", tmp_path)

    def test_blob_and_tree_revision_expressions_exit_2(
        self, tmp_path: Path
    ) -> None:
        """Valid non-commit revisions are invalid diff-base configuration."""
        self._init_repo(tmp_path)
        (tmp_path / "README.md").write_text("# Readme\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "README.md"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "add readme"],
            check=True, capture_output=True,
        )

        for revision in ("HEAD^{tree}", "HEAD:README.md"):
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", revision,
                "--phases", "1",
            ])
            assert exit_code == 2

    def test_annotated_tag_and_symbolic_ref_are_accepted(
        self, tmp_path: Path
    ) -> None:
        """Commitish tags and symbolic refs resolve to immutable commit IDs."""
        self._init_repo(tmp_path)
        subprocess.run(
            ["git", "-C", str(tmp_path), "tag", "-a", "base", "-m", "base"],
            check=True, capture_output=True,
        )
        branch = subprocess.run(
            ["git", "-C", str(tmp_path), "symbolic-ref", "--short", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        subprocess.run(
            [
                "git", "-C", str(tmp_path), "symbolic-ref",
                "refs/heads/base-symbolic", f"refs/heads/{branch}",
            ],
            check=True, capture_output=True,
        )

        assert _get_changed_files("base", tmp_path) == set()
        assert _get_changed_files("base-symbolic", tmp_path) == set()

    def test_option_like_revision_exits_2(self, tmp_path: Path) -> None:
        """An option-like diff base remains data after --end-of-options."""
        self._init_repo(tmp_path)
        exit_code = main([
            "--target", str(tmp_path),
            "--diff-base=--help",
            "--phases", "1",
        ])
        assert exit_code == 2

    def test_malformed_rev_parse_stdout_exits_3(self, tmp_path: Path) -> None:
        """Successful rev-parse with malformed output is a tool failure."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def malformed(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "--verify" in cmd:
                return subprocess.CompletedProcess(cmd, 0, b"--output=owned", b"")
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=malformed):
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", "HEAD",
                "--phases", "1",
            ])
        assert exit_code == 3

    def test_every_git_boundary_call_is_isolated_and_timed(
        self, tmp_path: Path
    ) -> None:
        """Every scanner-owned Git subprocess disables inherited execution."""
        import os

        self._init_repo(tmp_path)
        real_run = subprocess.run
        observed: list[tuple[list[str], object, dict[str, str]]] = []

        def recording_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            observed.append(
                (cmd, kwargs.get("timeout"), kwargs.get("env", {})),
            )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=recording_run):
            _get_changed_files("HEAD", tmp_path)
            list(_iter_git_files(tmp_path, require_git=True))

        assert observed
        for command, timeout, env in observed:
            assert timeout == mod._GIT_TIMEOUT
            assert command[0] == "git"
            assert "--no-replace-objects" in command
            config_index = command.index("-c")
            assert command[config_index + 1] == "core.fsmonitor=false"
            assert env["GIT_CONFIG_NOSYSTEM"] == "1"
            assert env["GIT_CONFIG_GLOBAL"] == os.devnull
            assert env["GIT_CONFIG_SYSTEM"] == os.devnull

    def test_windows_paths_normalize_to_git_separators(self) -> None:
        """Repository-relative paths use slashes on Windows."""
        from pathlib import PureWindowsPath

        path = PureWindowsPath(r"C:\repo\docs\guide.md")
        root = PureWindowsPath(r"C:\repo")
        assert _repo_relative(path, root) == "docs/guide.md"

    def test_resolved_oid_missing_object_exits_3(self, tmp_path: Path) -> None:
        """OID resolved but cat-file fails (object gone) => exit 3."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def fail_cat_file(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "cat-file" in cmd:
                raise subprocess.CalledProcessError(
                    1, cmd, stderr=b"fatal: Not a valid object name",
                )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=fail_cat_file):
            exit_code = main([
                "--target", str(tmp_path),
                "--diff-base", "HEAD",
                "--phases", "1",
            ])
        assert exit_code == 3


class TestRunClaimExtraction:
    def test_extracts_code_example(self, tmp_path: Path) -> None:
        md = "# Doc\n\n```python\nMyClass()\n```\n"
        (tmp_path / "doc.md").write_text(md)

        assessment = {
            "documentation_files": [{
                "path": "doc.md",
                "mapped_source_files": [],
                "referenced_symbols": [],
            }],
            "source_symbols": [],
        }
        result = run_claim_extraction(tmp_path, assessment)
        assert len(result["claims"]) >= 1
        assert result["claims"][0]["type"] == "code_example"
        assert result["claims"][0]["language"] == "python"

    def test_extracts_quantitative_claim(self, tmp_path: Path) -> None:
        md = "Performance is 99.9% uptime.\n"
        (tmp_path / "perf.md").write_text(md)

        assessment = {
            "documentation_files": [{
                "path": "perf.md",
                "mapped_source_files": [],
                "referenced_symbols": [],
            }],
            "source_symbols": [],
        }
        result = run_claim_extraction(tmp_path, assessment)
        quant = [c for c in result["claims"] if c["type"] == "quantitative"]
        assert len(quant) >= 1


class TestRunCompilabilityCheck:
    def test_no_findings_when_symbol_exists(self) -> None:
        assessment = {
            "source_symbols": [{
                "name": "MyClass", "kind": "class",
                "file": "a.py", "line": 1,
                "signature": "class MyClass:", "visibility": "public",
            }],
        }
        claims = {
            "claims": [{
                "id": "claim-0001", "file": "doc.md", "line": 1,
                "type": "code_example", "language": "python",
                "content": "x = MyClass()",
                "symbols_referenced": ["MyClass"],
                "mapped_source": "a.py",
            }],
        }
        result = run_compilability_check(assessment, claims)
        assert result["status"] == "COMPLETED"
        assert result["findings"] == []

    def test_finds_unresolved_symbol(self) -> None:
        assessment = {
            "source_symbols": [{
                "name": "ExistingWidget", "kind": "class",
                "file": "a.py", "line": 1,
                "signature": "class ExistingWidget:", "visibility": "public",
            }],
        }
        claims = {
            "claims": [{
                "id": "claim-0001", "file": "doc.md", "line": 1,
                "type": "method_signature", "language": "",
                "content": "MyWidget does things",
                "symbols_referenced": ["MyWidget"],
                "mapped_source": "",
            }],
        }
        result = run_compilability_check(assessment, claims)
        assert result["status"] == "COMPLETED"
        assert len(result["findings"]) == 1
        assert result["findings"][0]["category"] == "unresolved_symbol"

    def test_skips_framework_types(self) -> None:
        assessment = {
            "source_symbols": [{
                "name": "ExistingWidget", "kind": "class",
                "file": "a.py", "line": 1,
                "signature": "class ExistingWidget:", "visibility": "public",
            }],
        }
        claims = {
            "claims": [{
                "id": "claim-0001", "file": "doc.md", "line": 1,
                "type": "method_signature", "language": "",
                "content": "Returns a List",
                "symbols_referenced": ["List"],
                "mapped_source": "",
            }],
        }
        result = run_compilability_check(assessment, claims)
        assert result["status"] == "COMPLETED"
        assert result["findings"] == []

    def test_does_not_run_without_source_symbols(self) -> None:
        claims = {
            "claims": [{
                "id": "claim-0001", "file": "doc.md", "line": 1,
                "type": "method_signature", "language": "",
                "content": "MyWidget does things",
                "symbols_referenced": ["MyWidget"],
                "mapped_source": "",
            }],
        }

        result = run_compilability_check({"source_symbols": []}, claims)

        assert result["status"] == "DID_NOT_RUN"
        assert result["findings"] == []
        assert "No source symbols found" in result["reason"]

    def test_does_not_run_without_source_symbols_or_claims(self) -> None:
        result = run_compilability_check(
            {"source_symbols": []},
            {"claims": []},
        )

        assert result["status"] == "DID_NOT_RUN"
        assert result["findings"] == []

    def test_skips_text_fence_ascii_diagram(self) -> None:
        """text fences (ASCII diagrams) must not produce unresolved-symbol findings."""
        assessment = {
            "source_symbols": [{
                "name": "ExistingClass", "kind": "class",
                "file": "a.cs", "line": 1,
                "signature": "class ExistingClass", "visibility": "public",
            }],
        }
        claims = {
            "claims": [{
                "id": "claim-0001", "file": "workflow.md", "line": 5,
                "type": "code_example", "language": "text",
                "content": "P1 --> P2 --> P3\nEvaluation\nREADY",
                "symbols_referenced": ["Evaluation", "READY"],
                "mapped_source": "a.cs",
            }],
        }
        result = run_compilability_check(assessment, claims)
        assert result["findings"] == []

    def test_skips_powershell_code_example(self) -> None:
        """PowerShell examples must not resolve against the C# symbol index."""
        assessment = {
            "source_symbols": [{
                "name": "ExistingClass", "kind": "class",
                "file": "a.cs", "line": 1,
                "signature": "class ExistingClass", "visibility": "public",
            }],
        }
        claims = {
            "claims": [{
                "id": "claim-0001", "file": "ops.md", "line": 10,
                "type": "code_example", "language": "powershell",
                "content": "Search-WorkItems.ps1 -FailOnTruncation -SearchText foo",
                "symbols_referenced": ["FailOnTruncation", "SearchText"],
                "mapped_source": "a.cs",
            }],
        }
        result = run_compilability_check(assessment, claims)
        assert result["findings"] == []

    def test_still_checks_csharp_code_example(self) -> None:
        """C# code examples must still be verified (positive control)."""
        assessment = {
            "source_symbols": [{
                "name": "RealClass", "kind": "class",
                "file": "a.cs", "line": 1,
                "signature": "class RealClass", "visibility": "public",
            }],
        }
        claims = {
            "claims": [{
                "id": "claim-0001", "file": "api.md", "line": 3,
                "type": "code_example", "language": "csharp",
                "content": "var x = new FakeWidget();",
                "symbols_referenced": ["FakeWidget"],
                "mapped_source": "a.cs",
            }],
        }
        result = run_compilability_check(assessment, claims)
        assert len(result["findings"]) == 1
        assert result["findings"][0]["category"] == "unresolved_symbol"

    def test_skips_unlabeled_fence_code_example(self) -> None:
        """Fences with no language label (empty string) are skipped."""
        assessment = {
            "source_symbols": [{
                "name": "ExistingClass", "kind": "class",
                "file": "a.cs", "line": 1,
                "signature": "class ExistingClass", "visibility": "public",
            }],
        }
        claims = {
            "claims": [{
                "id": "claim-0001", "file": "doc.md", "line": 1,
                "type": "code_example", "language": "",
                "content": "SomeIdentifier here",
                "symbols_referenced": ["SomeIdentifier"],
                "mapped_source": "a.cs",
            }],
        }
        result = run_compilability_check(assessment, claims)
        assert result["findings"] == []


class TestCheckGate:
    def test_pass_no_findings(self) -> None:
        result = check_gate({"findings": []}, "high")
        assert result["verdict"] == "PASS"
        assert result["blocking_findings"] == 0

    def test_pass_none(self) -> None:
        result = check_gate(None, "high")
        assert result["verdict"] == "PASS"

    def test_did_not_run_is_inconclusive(self) -> None:
        result = check_gate({
            "status": "DID_NOT_RUN",
            "reason": "No source symbols found.",
            "findings": [],
        }, "high")

        assert result["verdict"] == "DID_NOT_RUN"
        assert result["reason"] == "No source symbols found."
        assert result["total_findings"] == 0

    def test_fail_critical(self) -> None:
        findings = {"findings": [{
            "severity": "critical", "id": "f1",
        }]}
        result = check_gate(findings, "high")
        assert result["verdict"] == "FAIL"
        assert result["blocking_findings"] == 1

    def test_pass_below_threshold(self) -> None:
        findings = {"findings": [{
            "severity": "low", "id": "f1",
        }]}
        result = check_gate(findings, "high")
        assert result["verdict"] == "PASS"

    def test_severity_counts(self) -> None:
        findings = {"findings": [
            {"severity": "critical", "id": "f1"},
            {"severity": "critical", "id": "f2"},
            {"severity": "medium", "id": "f3"},
        ]}
        result = check_gate(findings, "critical")
        assert result["by_severity"]["critical"] == 2
        assert result["by_severity"]["medium"] == 1
        assert result["total_findings"] == 3


class TestGenerateMarkdownReport:
    def test_writes_report(self, tmp_path: Path) -> None:
        gate = {
            "verdict": "PASS", "threshold": "high",
            "blocking_findings": 0, "total_findings": 0,
            "by_severity": {},
        }
        report_path = tmp_path / "report.md"
        generate_markdown_report(None, None, None, gate, report_path)

        content = report_path.read_text()
        assert "# Documentation Accuracy Report" in content
        assert "PASS" in content

    def test_includes_findings(self, tmp_path: Path) -> None:
        gate = {
            "verdict": "FAIL", "threshold": "high",
            "blocking_findings": 1, "total_findings": 1,
            "by_severity": {"critical": 1},
        }
        comp = {"findings": [{
            "severity": "critical", "file": "doc.md",
            "line": 10, "description": "Bad symbol reference",
        }]}
        report_path = tmp_path / "report.md"
        generate_markdown_report(None, None, comp, gate, report_path)

        content = report_path.read_text()
        assert "Bad symbol reference" in content
        assert "FAIL" in content

    def test_includes_did_not_run_reason(self, tmp_path: Path) -> None:
        gate = {
            "verdict": "DID_NOT_RUN", "threshold": "high",
            "reason": "No source symbols found.",
            "blocking_findings": 0, "total_findings": 0,
            "by_severity": {},
        }
        report_path = tmp_path / "report.md"

        generate_markdown_report(None, None, None, gate, report_path)

        content = report_path.read_text()
        assert "DID_NOT_RUN" in content
        assert "No source symbols found." in content


class TestMain:
    def test_invalid_target(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nope"
        rc = main(["--target", str(nonexistent)])
        assert rc == 1

    def test_scan_docs_only_repo_is_inconclusive(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "```python\nMyWidget()\n```\n",
        )

        rc = main(["--target", str(tmp_path)])

        assert rc == 1
        output_dir = tmp_path / ".doc-accuracy"
        findings = json.loads(
            (output_dir / "compilability-findings.json").read_text(),
        )
        gate = json.loads((output_dir / "gate-result.json").read_text())
        assert findings["status"] == "DID_NOT_RUN"
        assert findings["findings"] == []
        assert gate["verdict"] == "DID_NOT_RUN"
        assert gate["total_findings"] == 0

    def test_scan_with_unresolved_symbol_fails(self, tmp_path: Path) -> None:
        subprocess.run(
            ["git", "init", str(tmp_path)],
            check=True,
            capture_output=True,
        )
        (tmp_path / "main.py").write_text(
            "def ExistingWidget():\n    pass\n",
        )
        (tmp_path / "README.md").write_text(
            "```python\nMyWidget()\n```\n",
        )

        rc = main(["--target", str(tmp_path)])

        assert rc == 10
        gate = json.loads(
            (tmp_path / ".doc-accuracy" / "gate-result.json").read_text(),
        )
        assert gate["verdict"] == "FAIL"
        assert gate["blocking_findings"] == 1

    def test_markdown_format(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Test\n")
        rc = main(["--target", str(tmp_path), "--format", "markdown"])
        assert rc == 1
        report = tmp_path / ".doc-accuracy" / "report.md"
        assert report.exists()
        assert "Documentation Accuracy Report" in report.read_text()
        assert "DID_NOT_RUN" in report.read_text()

    def test_summary_format(self, tmp_path: Path, capsys) -> None:
        rc = main(["--target", str(tmp_path), "--format", "summary"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "Gate: DID_NOT_RUN" in captured.out
        assert "No source symbols found" in captured.out

    def test_custom_output_dir(self, tmp_path: Path) -> None:
        out = tmp_path / "custom-output"
        rc = main([
            "--target", str(tmp_path),
            "--output-dir", str(out),
        ])
        assert rc == 1
        assert (out / "gate-result.json").exists()

    def test_phases_selection(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text("# Hi\n")
        rc = main(["--target", str(tmp_path), "--phases", "1"])
        assert rc == 0
        assert (tmp_path / ".doc-accuracy" / "assessment.json").exists()
        # claims.json should not exist when only phase 1 runs
        assert not (tmp_path / ".doc-accuracy" / "claims.json").exists()
