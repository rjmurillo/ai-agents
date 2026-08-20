"""The push gate's suppression parser and ADR-review merge scope must hold.

``check_pushed_suppressions`` reads the diff a push would send and blocks
unjustified lint suppressions. Its bypasses are all parser-shaped: a bare
ruff-honored comment, a notebook cell the textual diff renders differently, a
new branch with no merge base, a shallow clone. Each one is a way to land a
suppression the gate was built to catch, so each gets a test.

``check_adr_review_policy`` blocks an ADR change carrying no adr-review
evidence. The exception is a merge in progress: an ADR reviewed on main arrives
in the merge commit with no evidence of its own, and blocking there would wedge
every merge that touches architecture.

The fixtures below use ``+``-concatenated string literals to build suppression
tokens (e.g. ``"# " + "nos" + "ec"``). This form is formatter-stable: ``ruff
format`` does not collapse it into a single string, so the push gate cannot
detect the token in source. See issue #4153.

The filename is historical. This file now covers suppression policy and ADR
merge scope, not causal restore. Renaming it remains separate scope because
test selectors and review references use the current path. Filed as issue 3635.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validation import git_hook_policy as policy


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["git"], returncode, stdout, "")


def _run_suppression_push(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    diff_text: str,
    changed_paths: tuple[str, ...] = ("pkg/module.py",),
    *,
    base: str | None = "c" * 40,
    remote_sha: str = "b" * 40,
    rename_status_output: str = "",
    refs_present: bool = False,
    shallow: bool = False,
) -> int:
    head = "a" * 40
    expected_base = base
    if expected_base is None and refs_present and not shallow:
        expected_base = policy.EMPTY_TREE_SHA1
    expected_range = f"{expected_base}..{head}" if expected_base is not None else None
    monkeypatch.setattr(policy, "_check_history_integrity", lambda root: 0)
    monkeypatch.setattr(policy, "_merge_base", lambda root, base_ref, head_ref: base)
    monkeypatch.setattr(policy, "_commit_ref_exists", lambda root, ref: refs_present)
    monkeypatch.setattr(policy, "_is_shallow_repository", lambda root: shallow)
    monkeypatch.setattr(policy, "_empty_tree_sha", lambda root: policy.EMPTY_TREE_SHA1)

    def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["ls-tree", "-r"]:
            assert "-z" in args, "ls-tree must use -z for NUL-separated output"
            assert args[-1] == head
            return _completed("\0".join(changed_paths) + "\0")
        if args[0] == "diff" and "--name-only" in args and "--diff-filter=ACMRT" in args:
            for flag in policy.TEXTUAL_DIFF_FLAGS:
                assert flag in args
            assert "-z" in args, "diff --name-only must use -z for NUL-separated output"
            assert "--no-renames" in args, "diff --name-only must use --no-renames"
            assert expected_range is not None
            assert expected_range in args
            return _completed("\0".join(changed_paths) + "\0")
        if args[0] == "diff" and "--name-status" in args and "--diff-filter=R" in args:
            assert expected_range is not None
            assert expected_range in args
            assert "--find-renames" in args
            assert "--no-renames" not in args
            return _completed(rename_status_output)
        if "diff" in args and "--unified=0" in args:
            assert expected_range is not None
            assert expected_range in args
            for flag in policy.TEXTUAL_DIFF_FLAGS:
                assert flag in args
            assert "--find-renames" in args
            assert "--no-renames" not in args
            assert args[-1] == "--"
            return _completed(diff_text)
        if args[0] == "show":
            return _completed("")
        raise AssertionError(f"unexpected git call: {args!r}")

    monkeypatch.setattr(policy, "_run_git", _run_git)
    stdin = io.StringIO(f"refs/heads/topic {head} refs/heads/topic {remote_sha}\n")
    return policy.check_pushed_suppressions(stdin, repo_root)


def _tool(name: str) -> str:
    resolved = shutil.which(name)
    assert resolved is not None, f"{name} is required for this regression test"
    return resolved


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = _run(["git", *args], repo)
    assert result.returncode == 0, result.stderr
    return result


def _init_push_repo(repo: Path) -> None:
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", base_sha)
    _git(repo, "checkout", "-b", "topic")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _point_origin_main_at_head(repo: Path) -> str:
    """Make the local `origin/main` cache agree with what this repo has at HEAD."""
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", head)
    return head


def _run_real_suppression_push(repo: Path, head: str) -> int:
    stdin = io.StringIO(f"refs/heads/topic {head} refs/heads/topic {'0' * 40}\n")
    return policy.check_pushed_suppressions(stdin, repo)


def _write_ruff_notebook(path: Path, source: str | list[str]) -> None:
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [source] if isinstance(source, str) else source,
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(notebook), encoding="utf-8")


class TestPushedSuppressionPolicy:
    def test_bare_noqa_is_honored_by_ruff_and_blocked_by_push_gate(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        comment = "# no" + "qa"
        analyzer_file = tmp_path / "ruff_bare_noqa.py"
        analyzer_file.write_text(f"import os  {comment}\n", encoding="utf-8")
        analyzer = _run([_tool("ruff"), "check", "--select", "F401", str(analyzer_file)], _ROOT)
        assert analyzer.returncode == 0, analyzer.stdout + analyzer.stderr
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+import os  {comment}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:1" in capsys.readouterr().err

    def test_bare_type_ignore_is_honored_by_mypy_and_allowed_by_security_gate(
        self,
        tmp_path,
        monkeypatch,
    ):
        comment = "# type" + ": ignore"
        analyzer_file = tmp_path / "mypy_bare_type_ignore.py"
        analyzer_file.write_text(f"value: int = 'wrong'  {comment}\n", encoding="utf-8")
        analyzer = _run([_tool("mypy"), "--show-error-codes", str(analyzer_file)], _ROOT)
        assert analyzer.returncode == 0, analyzer.stdout + analyzer.stderr
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+value: int = 'wrong'  {comment}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0

    def test_newly_added_type_ignore_is_allowed(self, tmp_path, monkeypatch):
        suppression = "# type" + ": ignore[arg-type]"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -1,0 +2 @@
+value = call()  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0

    def test_diff_without_suppression_is_allowed(self, tmp_path, monkeypatch):
        diff = """diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -2 +2 @@
-old = 1
+new = 1
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0

    def test_added_file_with_type_ignore_is_allowed(self, tmp_path, monkeypatch):
        suppression = "# type" + ": ignore[assignment]"
        diff = f"""diff --git a/pkg/new.py b/pkg/new.py
new file mode 100644
--- /dev/null
+++ b/pkg/new.py
@@ -0,0 +1,2 @@
+from pkg import value
+result = value  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff, ("pkg/new.py",)) == 0

    def test_security_suppression_on_context_line_adjacent_to_edit_is_allowed(
        self,
        tmp_path,
        monkeypatch,
    ):
        suppression = "# nos" + "ec"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -1,2 +1,2 @@
 value = call()  {suppression}
-old = 1
+new = 1
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0

    def test_added_plus_plus_line_with_nosec_is_blocked(self, tmp_path, monkeypatch, capsys):
        suppression = "# nos" + "ec"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -1,0 +4 @@
+++counter  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:4" in capsys.readouterr().err

    def test_no_prefix_diff_with_nosec_addition_is_blocked(self, tmp_path, monkeypatch, capsys):
        suppression = "# nos" + "ec"
        diff = f"""diff --git pkg/module.py pkg/module.py
--- pkg/module.py
+++ pkg/module.py
@@ -1,0 +3 @@
+value = call()  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:3" in capsys.readouterr().err

    def test_pure_rename_with_existing_suppression_is_allowed(
        self,
        tmp_path,
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        _git(repo, "checkout", "main")
        source = repo / "source.py"
        source.write_text("import os  # no" + "qa\n", encoding="utf-8")
        _commit(repo, "add suppression")
        _point_origin_main_at_head(repo)

        _git(repo, "checkout", "topic")
        _git(repo, "merge", "--ff-only", "main")
        _git(repo, "mv", "source.py", "target.py")
        head = _commit(repo, "rename source")

        assert _run_real_suppression_push(repo, head) == 0

    def test_rename_with_edit_preserves_existing_suppression_credit(
        self,
        tmp_path,
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        _git(repo, "checkout", "main")
        source = repo / "source.py"
        content = (
            "value = call()  # nos"
            + "ec\n"
            + "".join(f"value_{index} = {index}\n" for index in range(10))
        )
        source.write_text(content, encoding="utf-8")
        _commit(repo, "add suppression")
        _point_origin_main_at_head(repo)

        _git(repo, "checkout", "topic")
        _git(repo, "merge", "--ff-only", "main")
        _git(repo, "mv", "source.py", "target.py")
        (repo / "target.py").write_text(content + "changed = True\n", encoding="utf-8")
        head = _commit(repo, "rename and edit source")

        assert _run_real_suppression_push(repo, head) == 0

    def test_rename_into_scanned_suffix_with_existing_suppression_is_blocked(
        self,
        tmp_path,
        capsys,
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        _git(repo, "checkout", "main")
        payload = repo / "payload.txt"
        payload.write_text("value = call()  # nos" + "ec\n", encoding="utf-8")
        _commit(repo, "add unscanned suppression")
        _point_origin_main_at_head(repo)

        _git(repo, "checkout", "topic")
        _git(repo, "merge", "--ff-only", "main")
        _git(repo, "mv", "payload.txt", "payload.py")
        head = _commit(repo, "promote payload to Python")

        assert _run_real_suppression_push(repo, head) == 1
        assert "payload.py:1" in capsys.readouterr().err

    def test_new_branch_without_merge_base_is_config_error(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        suppression = "# nos" + "ec"
        diff = f"""diff --git a/source.py b/source.py
new file mode 100644
--- /dev/null
+++ b/source.py
@@ -0,0 +1 @@
+value = call()  {suppression}
"""

        assert (
            _run_suppression_push(
                monkeypatch,
                tmp_path,
                diff,
                ("source.py",),
                base=None,
                remote_sha="0" * 40,
            )
            == 2
        )
        err = capsys.readouterr().err
        assert "could not determine push base for new branch" in err
        assert "fetch origin/main" in err
        assert "unshallow" in err

    def test_new_branch_with_merge_base_scans_only_pushed_range(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        suppression = "# nos" + "ec"
        diff = f"""diff --git a/source.py b/source.py
new file mode 100644
--- /dev/null
+++ b/source.py
@@ -0,0 +1 @@
+value = call()  {suppression}
"""

        assert (
            _run_suppression_push(
                monkeypatch,
                tmp_path,
                diff,
                ("source.py",),
                base="d" * 40,
                remote_sha="0" * 40,
            )
            == 1
        )
        assert "source.py:1" in capsys.readouterr().err

    def test_removed_line_starting_with_two_dashes_does_not_shift_added_line_number(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        suppression = "# nos" + "ec"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -10,2 +10,1 @@
--- removed content line
+real = 1  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:10" in capsys.readouterr().err

    def test_diff_attribute_cannot_hide_added_suppression(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        suppression = "# nos" + "ec"
        (repo / ".gitattributes").write_text("scripts/tls_probe.py -diff\n", encoding="utf-8")
        script = repo / "scripts" / "tls_probe.py"
        script.parent.mkdir()
        script.write_text(f"import ssl\nssl.PROTOCOL_SSLv3  {suppression}\n", encoding="utf-8")
        head = _commit(repo, "add hidden suppression")

        assert _run_real_suppression_push(repo, head) == 1

    def test_external_diff_cannot_hide_added_suppression(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        # Create a portable external-diff stub that swallows all output
        stub = tmp_path / "ext-diff-stub"
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
        _git(repo, "config", "diff.external", str(stub))
        suppression = "# nos" + "ec"
        path = repo / "pkg" / "module.py"
        path.parent.mkdir()
        path.write_text(f"import ssl\nssl.PROTOCOL_SSLv3  {suppression}\n", encoding="utf-8")
        head = _commit(repo, "add external hidden suppression")

        assert _run_real_suppression_push(repo, head) == 1

    def test_textconv_driver_cannot_hide_added_suppression(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        _git(repo, "config", "diff.hide.textconv", "true")
        (repo / ".gitattributes").write_text("*.py diff=hide\n", encoding="utf-8")
        suppression = "# nos" + "ec"
        path = repo / "pkg" / "module.py"
        path.parent.mkdir()
        path.write_text(f"import ssl\nssl.PROTOCOL_SSLv3  {suppression}\n", encoding="utf-8")
        head = _commit(repo, "add textconv hidden suppression")

        assert _run_real_suppression_push(repo, head) == 1

    def test_suppression_suffixes_cover_ruff_count_ratchet_scan_globs(self):
        assert policy._ruff_scan_suffixes() <= policy.SECURITY_SUPPRESSION_SUFFIXES
        assert {".pyi", ".ipynb", ".pyw"} <= policy.SECURITY_SUPPRESSION_SUFFIXES

    def test_pyi_suppression_is_honored_by_ruff_and_blocked_by_push_gate(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        comment = "# no" + "qa"
        analyzer_file = tmp_path / "stub.pyi"
        analyzer_file.write_text(f"import os  {comment}\n", encoding="utf-8")
        analyzer = _run([_tool("ruff"), "check", "--select", "F401", str(analyzer_file)], _ROOT)
        assert analyzer.returncode == 0, analyzer.stdout + analyzer.stderr
        diff = f"""diff --git a/pkg/stub.pyi b/pkg/stub.pyi
--- a/pkg/stub.pyi
+++ b/pkg/stub.pyi
@@ -0,0 +1 @@
+import os  {comment}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff, ("pkg/stub.pyi",)) == 1
        assert "pkg/stub.pyi:1" in capsys.readouterr().err

    def test_pyw_suppression_is_honored_by_bandit_and_blocked_by_push_gate(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        comment = "# nos" + "ec"
        path = repo / "tools" / "legacy_tls.pyw"
        path.parent.mkdir()
        path.write_text(
            f"import ssl\nssl.wrap_socket(ssl_version=ssl.PROTOCOL_SSLv3)  {comment}\n",
            encoding="utf-8",
        )
        analyzer = _run([_tool("bandit"), "-q", str(path)], _ROOT)
        assert analyzer.returncode == 0, analyzer.stdout + analyzer.stderr
        head = _commit(repo, "add pyw suppression")

        assert _run_real_suppression_push(repo, head) == 1

    def test_notebook_unicode_escape_suppression_is_honored_by_ruff_and_blocked(
        self,
        tmp_path,
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        path = repo / "notebooks" / "analysis.ipynb"
        path.parent.mkdir()
        _write_ruff_notebook(path, "import os  # no" + "qa\n")
        path.write_text(
            path.read_text(encoding="utf-8").replace("noqa", "no\\u0071a"),
            encoding="utf-8",
        )
        analyzer = _run([_tool("ruff"), "check", "--select", "F401", str(path)], _ROOT)
        assert analyzer.returncode == 0, analyzer.stdout + analyzer.stderr
        head = _commit(repo, "add notebook suppression")

        assert _run_real_suppression_push(repo, head) == 1

    def test_true_orphan_branch_scans_from_empty_tree(self, tmp_path, monkeypatch, capsys):
        suppression = "# nos" + "ec"
        diff = f"""diff --git a/source.py b/source.py
new file mode 100644
--- /dev/null
+++ b/source.py
@@ -0,0 +1 @@
+value = call()  {suppression}
"""

        assert (
            _run_suppression_push(
                monkeypatch,
                tmp_path,
                diff,
                ("source.py",),
                base=None,
                remote_sha="0" * 40,
                refs_present=True,
                shallow=False,
            )
            == 1
        )
        assert "source.py:1" in capsys.readouterr().err

    def test_shallow_new_branch_without_merge_base_stays_config_error(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        suppression = "# nos" + "ec"
        diff = f"""diff --git a/source.py b/source.py
new file mode 100644
--- /dev/null
+++ b/source.py
@@ -0,0 +1 @@
+value = call()  {suppression}
"""

        assert (
            _run_suppression_push(
                monkeypatch,
                tmp_path,
                diff,
                ("source.py",),
                base=None,
                remote_sha="0" * 40,
                refs_present=True,
                shallow=True,
            )
            == 2
        )
        err = capsys.readouterr().err
        assert "could not determine push base for new branch" in err
        assert "unshallow" in err

    def test_non_security_noqa_is_not_blocked_by_push_gate(self, tmp_path, monkeypatch):
        # E402 is not a security rule; after the regex narrowing it must pass.
        comment = "# no" "qa: E402"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+import os  {comment}
"""
        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0

    def test_security_noqa_is_still_blocked_by_push_gate(self, tmp_path, monkeypatch, capsys):
        # A suppression carrying an S-prefixed rule must still be blocked.
        comment = "# no" + "qa: S603"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+subprocess.call(cmd)  {comment}
"""
        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:1" in capsys.readouterr().err

    def test_moved_security_noqa_is_allowed(self, tmp_path, monkeypatch):
        # A noqa: S603 that appears on both a removed and an added line (the line
        # was refactored but not newly suppressed) must not be flagged.
        comment = "# no" + "qa: S603"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -5,1 +5,1 @@
-subprocess.call(cmd)  {comment}
+subprocess.call(cmd, env=env)  {comment}
"""
        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0

    def test_moved_nosemgrep_is_allowed(self, tmp_path, monkeypatch):
        # A nosemgrep comment that moves (same payload on - and + line) must pass.
        comment = "# nos" + "emgrep: python.lang.security.insecure-subprocess-call"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -10,1 +10,1 @@
-foo(bar)  {comment}
+foo(bar, extra=True)  {comment}
"""
        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0

    def test_net_new_security_noqa_after_removal_is_still_blocked(
        self, tmp_path, monkeypatch, capsys
    ):
        # One removal + two additions: the first addition consumes the removal
        # credit; the second is net-new and must be blocked.
        comment = "# no" + "qa: S603"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -5,1 +5,2 @@
-subprocess.call(old_cmd)  {comment}
+subprocess.call(new_cmd)  {comment}
+subprocess.call(extra_cmd)  {comment}
"""
        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:6" in capsys.readouterr().err

    def test_mixed_noqa_with_security_rule_is_blocked(self, tmp_path, monkeypatch, capsys):
        # A suppression listing E402, S603 includes a security rule; must be blocked.
        comment = "# no" + "qa: E402, S603"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+import something  {comment}
"""
        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:1" in capsys.readouterr().err

    def test_ann_noqa_is_not_blocked(self, tmp_path, monkeypatch):
        # ANN rules are not security rules; noqa: ANN001 must pass.
        comment = "# noqa: ANN001"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+def fn(x):  {comment}
"""
        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0


class _GitStub:
    """Minimal git subprocess stub for check_staged_suppressions tests."""

    def __init__(
        self,
        diff_output: str,
        *,
        returncode: int = 0,
        paths: tuple[str, ...] = ("pkg/module.py",),
        rename_status_output: str = "",
    ) -> None:
        self._diff_output = diff_output
        self._returncode = returncode
        self._paths = paths
        self._rename_status_output = rename_status_output

    def __call__(self, repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        if "--name-only" in args:
            stdout = "\0".join((*self._paths, ""))
        elif "--name-status" in args:
            stdout = self._rename_status_output
        else:
            stdout = self._diff_output
        return subprocess.CompletedProcess(args, self._returncode, stdout, "")


class TestStagedSuppressionPolicy:
    def _run_staged(
        self,
        monkeypatch: pytest.MonkeyPatch,
        repo_root: Path,
        diff_output: str,
        *,
        git_returncode: int = 0,
        paths: tuple[str, ...] = ("pkg/module.py",),
        rename_status_output: str = "",
    ) -> int:
        monkeypatch.setattr(policy, "_staged_suppression_base", lambda root: "HEAD")
        monkeypatch.setattr(
            policy,
            "_run_git",
            _GitStub(
                diff_output,
                returncode=git_returncode,
                paths=paths,
                rename_status_output=rename_status_output,
            ),
        )
        return policy.check_staged_suppressions(repo_root)

    def test_staged_security_noqa_is_blocked(self, tmp_path, monkeypatch, capsys):
        comment = "# no" + "qa: S603"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+subprocess.call(cmd)  {comment}
"""
        assert self._run_staged(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:1" in capsys.readouterr().err

    def test_staged_non_security_noqa_is_not_blocked(self, tmp_path, monkeypatch):
        comment = "# noqa: E402"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+import something  {comment}
"""
        assert self._run_staged(monkeypatch, tmp_path, diff) == 0

    @pytest.mark.parametrize(
        "directive",
        (
            "# ruff: no" + "qa",
            "# ruff: no" + "qa: S602",
            "# flake8: no" + "qa",
            "# no" + "qa: E501 S602",
            "# no" + "qa: ANN001 S603",
        ),
    )
    def test_staged_file_level_security_noqa_is_blocked(
        self,
        tmp_path,
        monkeypatch,
        directive,
    ):
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+{directive}
"""
        assert self._run_staged(monkeypatch, tmp_path, diff) == 1

    def test_staged_file_level_non_security_noqa_is_not_blocked(
        self,
        tmp_path,
        monkeypatch,
    ):
        directive = "# ruff: noqa: E402"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+{directive}
"""
        assert self._run_staged(monkeypatch, tmp_path, diff) == 0

    def test_staged_uppercase_security_noqa_is_blocked(
        self,
        tmp_path,
        monkeypatch,
    ):
        directive = "# NO" + "QA: S603"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+{directive}
"""
        assert self._run_staged(monkeypatch, tmp_path, diff) == 1

    def test_staged_codeql_suppression_is_blocked(
        self,
        tmp_path,
        monkeypatch,
    ):
        directive = "# code" + "ql[js/xss]"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+{directive}
"""
        assert self._run_staged(monkeypatch, tmp_path, diff) == 1

    def test_staged_non_security_noqa_with_s_number_in_rationale_is_allowed(
        self,
        tmp_path,
        monkeypatch,
    ):
        directive = "# noqa: E501  # explains the S3 bucket"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+{directive}
"""
        assert self._run_staged(monkeypatch, tmp_path, diff) == 0

    def test_empty_staged_diff_passes(self, tmp_path, monkeypatch):
        assert self._run_staged(monkeypatch, tmp_path, "") == 0

    def test_git_failure_returns_2(self, tmp_path, monkeypatch):
        assert self._run_staged(monkeypatch, tmp_path, "", git_returncode=1) == 2

    def test_staged_moved_security_noqa_is_allowed(self, tmp_path, monkeypatch):
        # Same suppression on removed and added line: move, not a new suppression.
        comment = "# no" + "qa: S603"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -3,1 +3,1 @@
-old_call()  {comment}
+new_call()  {comment}
"""
        assert self._run_staged(monkeypatch, tmp_path, diff) == 0

    def test_staged_suppression_in_unscanned_file_is_ignored(
        self,
        tmp_path,
        monkeypatch,
    ):
        suppression = "# nos" + "ec"
        diff = f"""diff --git a/docs/example.md b/docs/example.md
--- a/docs/example.md
+++ b/docs/example.md
@@ -0,0 +1 @@
+example  {suppression}
"""
        assert (
            self._run_staged(
                monkeypatch,
                tmp_path,
                diff,
                paths=("docs/example.md",),
            )
            == 0
        )

    def test_staged_notebook_security_suppression_is_blocked(self, tmp_path, capsys):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        path = repo / "notebooks" / "analysis.ipynb"
        path.parent.mkdir()
        _write_ruff_notebook(path, "import os  # no" + "qa: S603\n")
        _git(repo, "add", str(path.relative_to(repo)))

        assert policy.check_staged_suppressions(repo) == 1
        assert "notebooks/analysis.ipynb:1" in capsys.readouterr().err

    def test_staged_notebook_split_source_suppression_is_blocked(self, tmp_path, capsys):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        path = repo / "notebooks" / "analysis.ipynb"
        path.parent.mkdir()
        _write_ruff_notebook(path, ["import os  # no", "qa: S603\n"])
        _git(repo, "add", str(path.relative_to(repo)))

        assert policy.check_staged_suppressions(repo) == 1
        assert "notebooks/analysis.ipynb:1" in capsys.readouterr().err

    def test_staged_type_change_to_python_file_is_blocked(self, tmp_path, capsys):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        path = repo / "module.py"
        path.symlink_to("README.md")
        _commit(repo, "add Python symlink")
        path.unlink()
        path.write_text("import subprocess  # nos" + "ec\n", encoding="utf-8")
        _git(repo, "add", str(path.relative_to(repo)))

        assert policy.check_staged_suppressions(repo) == 1
        assert "module.py:1" in capsys.readouterr().err

    def test_staged_unicode_python_path_is_blocked(self, tmp_path, capsys):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        path = repo / "café.py"
        path.write_text("import subprocess  # nos" + "ec\n", encoding="utf-8")
        _git(repo, "add", str(path.relative_to(repo)))

        assert policy.check_staged_suppressions(repo) == 1
        assert "café.py:1" in capsys.readouterr().err

    def test_staged_pure_python_rename_is_allowed(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        path = repo / "old.py"
        path.write_text("import subprocess  # nos" + "ec\n", encoding="utf-8")
        _commit(repo, "add suppression")
        _git(repo, "mv", "old.py", "new.py")

        assert policy.check_staged_suppressions(repo) == 0

    def test_staged_python_rename_with_edit_is_allowed(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        path = repo / "old.py"
        source = (
            "import subprocess  # nos"
            + "ec\n"
            + "".join(f"value_{index} = {index}\n" for index in range(10))
        )
        path.write_text(source, encoding="utf-8")
        _commit(repo, "add suppression")
        _git(repo, "mv", "old.py", "new.py")
        (repo / "new.py").write_text(source + "changed = True\n", encoding="utf-8")
        _git(repo, "add", "new.py")

        assert policy.check_staged_suppressions(repo) == 0

    def test_staged_rename_into_scanned_suffix_is_blocked(self, tmp_path, capsys):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        path = repo / "payload.txt"
        path.write_text("value = call()  # nos" + "ec\n", encoding="utf-8")
        _commit(repo, "add unscanned suppression")
        _git(repo, "mv", "payload.txt", "payload.py")

        assert policy.check_staged_suppressions(repo) == 1
        assert "payload.py:1" in capsys.readouterr().err

    def test_staged_pure_notebook_rename_is_allowed(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        path = repo / "old.ipynb"
        _write_ruff_notebook(path, "import os  # no" + "qa: S603\n")
        _commit(repo, "add notebook suppression")
        _git(repo, "mv", "old.ipynb", "new.ipynb")

        assert policy.check_staged_suppressions(repo) == 0

    def test_merge_ignores_suppression_arriving_from_merge_head(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        _git(repo, "checkout", "main")
        incoming = repo / "incoming.py"
        incoming.write_text("import subprocess  # nos" + "ec\n", encoding="utf-8")
        _commit(repo, "incoming suppression")
        _point_origin_main_at_head(repo)

        _git(repo, "checkout", "topic")
        (repo / "local.py").write_text("local = True\n", encoding="utf-8")
        _commit(repo, "local work")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "main"], repo)
        assert merge.returncode == 0, merge.stderr

        assert policy.check_staged_suppressions(repo) == 0

    def test_merge_blocks_suppression_authored_on_local_branch(
        self,
        tmp_path,
        capsys,
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        _git(repo, "checkout", "main")
        (repo / "incoming.py").write_text("incoming = True\n", encoding="utf-8")
        _commit(repo, "incoming work")
        _point_origin_main_at_head(repo)

        _git(repo, "checkout", "topic")
        local = repo / "local.py"
        local.write_text("import subprocess  # nos" + "ec\n", encoding="utf-8")
        _commit(repo, "local suppression")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "main"], repo)
        assert merge.returncode == 0, merge.stderr

        assert policy.check_staged_suppressions(repo) == 1
        assert "local.py:1" in capsys.readouterr().err

    def test_merge_blocks_suppression_from_unapproved_merge_head(
        self,
        tmp_path,
        capsys,
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        _git(repo, "checkout", "-b", "side", "main")
        side = repo / "side.py"
        side.write_text("import subprocess  # nos" + "ec\n", encoding="utf-8")
        _commit(repo, "side suppression")

        _git(repo, "checkout", "topic")
        (repo / "local.py").write_text("local = True\n", encoding="utf-8")
        _commit(repo, "local work")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "side"], repo)
        assert merge.returncode == 0, merge.stderr

        assert policy.check_staged_suppressions(repo) == 1
        assert "side.py:1" in capsys.readouterr().err

    def test_precommit_globs_cover_all_suppression_suffixes(self):
        config = (_ROOT / "lefthook.yml").read_text(encoding="utf-8")
        precommit = config.index("pre-commit:")
        start = config.index("- name: security-suppressions-staged", precommit)
        end = config.index("\n    - group:", start)
        hook = config[start:end]

        for suffix in policy.SECURITY_SUPPRESSION_SUFFIXES:
            assert f'"**/*{suffix}"' in hook

    def test_pre_merge_commit_runs_staged_suppression_gate(self):
        config = (_ROOT / "lefthook.yml").read_text(encoding="utf-8")
        start = config.index("pre-merge-commit:")
        end = config.index("\npre-commit:", start)
        hook = config[start:end]

        assert "security-suppressions-staged" in hook


class TestAdrReviewPolicyMergeScope:
    def test_non_merge_adr_without_review_evidence_is_blocked(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: False)
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )

        result = policy.check_adr_review_policy(
            [".agents/architecture/ADR-999-test.md"],
            tmp_path,
        )

        assert result == 1
        assert "ADR changes require a debate log" in capsys.readouterr().err

    def test_merge_in_progress_with_staged_adr_from_main_is_allowed(self, tmp_path, monkeypatch):
        path = ".agents/architecture/ADR-120-reviewed-on-main.md"
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_read_index_blob", lambda root, relative_path: b"main adr")
        monkeypatch.setattr(policy, "_read_head_blob", lambda root, relative_path: None)
        monkeypatch.setattr(
            policy,
            "_approved_merge_head_commits",
            lambda root: ["main-parent"],
            raising=False,
        )
        monkeypatch.setattr(
            policy,
            "_read_commit_blob_bytes",
            lambda root, commit, relative_path: b"main adr",
            raising=False,
        )

        result = policy.check_adr_review_policy(
            [path],
            tmp_path,
        )

        assert result == 0

    def test_merge_in_progress_with_branch_authored_adr_is_gated(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        path = ".agents/architecture/ADR-999-branch-authored-during-merge.md"
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_read_index_blob", lambda root, relative_path: b"authored adr")
        monkeypatch.setattr(policy, "_read_head_blob", lambda root, relative_path: b"branch adr")
        monkeypatch.setattr(
            policy,
            "_approved_merge_head_commits",
            lambda root: ["main-parent"],
            raising=False,
        )
        monkeypatch.setattr(
            policy,
            "_read_commit_blob_bytes",
            lambda root, commit, relative_path: b"main adr",
            raising=False,
        )
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )

        result = policy.check_adr_review_policy(
            [path],
            tmp_path,
        )

        assert result == 1
        assert "ADR changes require a debate log" in capsys.readouterr().err

    def test_merge_in_progress_with_conflicted_adr_is_gated_when_stage_zero_is_absent(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        path = ".agents/architecture/ADR-998-conflicted.md"
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_read_index_blob", lambda root, relative_path: None)
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )

        result = policy.check_adr_review_policy(
            [path],
            tmp_path,
        )

        assert result == 1
        assert "ADR changes require a debate log" in capsys.readouterr().err

    def test_blob_readers_preserve_raw_git_bytes(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        # Neutralize text normalization the same way the CRLF fixtures below
        # do. A host with core.autocrlf set (or an inherited gitattributes)
        # otherwise folds the raw CRLF and lone-CR bytes this test asserts on
        # during `git add`, so the assertion fails on the environment rather
        # than on the reader under test.
        (repo / ".gitattributes").write_text("* -text\n", encoding="utf-8")
        relative = ".agents/architecture/ADR-006-raw-bytes.md"
        adr = repo / relative
        adr.parent.mkdir(parents=True)
        raw = b"# ADR 006\r\n\xffraw byte and lone carriage\rreturn\n"
        adr.write_bytes(raw)
        _git(repo, "add", relative)

        assert policy._read_index_blob(repo, relative) == raw
        commit = _commit(repo, "raw ADR bytes")
        assert policy._read_head_blob(repo, relative) == raw
        assert policy._read_commit_blob_bytes(repo, commit, relative) == raw

    def test_head_copy_is_checked_across_origin_main_renames(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        old_relative = ".agents/architecture/ADR-007-old-name.md"
        new_relative = ".agents/architecture/ADR-007-new-name.md"
        old_adr = repo / old_relative
        new_adr = repo / new_relative
        old_body = "# ADR 007\n\nold reviewed position.\nstable line.\n"
        new_body = "# ADR 007\n\nnew reviewed position.\nstable line.\n"
        old_adr.write_text(old_body, encoding="utf-8")
        _commit(repo, "old reviewed ADR")
        _git(repo, "mv", old_relative, new_relative)
        new_adr.write_text(new_body, encoding="utf-8")
        main_tip = _commit(repo, "rename and revise ADR")
        _git(repo, "update-ref", "refs/remotes/origin/main", main_tip)
        _git(repo, "checkout", "-b", "feature")
        new_adr.write_text(old_body, encoding="utf-8")
        _commit(repo, "branch keeps older reviewed ADR content at the new path")

        assert policy._head_copy_is_one_main_has_carried(repo, new_relative) is True

    def test_merge_of_a_shared_branch_tip_allows_content_already_on_main(
        self,
        tmp_path,
        monkeypatch,
    ):
        """The exemption has to follow the content, not the merge parent.

        `_approved_merge_head_commits` keeps only parents that are ancestors of
        `origin/main`, so it covers merging main in directly. It does not cover
        the other way a branch takes main's work: someone else merges main into
        the shared branch and pushes, and the next author merges that remote
        tip. The parent is then the branch, not main, so every ADR main
        contributed reads as branch-authored and the gate demands review
        evidence for a file the author never opened.

        Comparing the staged blob against `origin/main` closes that without
        widening the gate, because content that already sits on main already
        cleared this policy on the pull request that put it there.
        """
        path = ".agents/architecture/ADR-089-arrived-through-the-branch.md"
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_read_index_blob", lambda root, relative_path: b"main adr")
        monkeypatch.setattr(policy, "_read_head_blob", lambda root, relative_path: None)
        monkeypatch.setattr(
            policy,
            "_approved_merge_head_commits",
            lambda root: [],
            raising=False,
        )
        monkeypatch.setattr(
            policy,
            "_merge_head_commits",
            lambda root: ["the-shared-branch-tip"],
            raising=False,
        )
        blobs = {"the-shared-branch-tip": b"main adr", "origin/main": b"main adr"}
        monkeypatch.setattr(
            policy,
            "_read_commit_blob_bytes",
            lambda root, commit, relative_path: blobs.get(commit),
            raising=False,
        )

        assert policy.check_adr_review_policy([path], tmp_path) == 0

    def test_an_adr_reverted_to_a_stale_origin_main_during_a_merge_is_still_gated(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Content sitting on main is not a licence to put it back.

        A local `origin/main` ref goes stale the moment someone else pushes.
        Matching content against it alone would let an author revert an ADR to
        the stale state mid-merge and walk past the gate, and the revert would
        then overwrite the newer copy on the next push. Reverting is a fresh
        decision no matter how old the bytes are, so the content has to arrive
        through the merge as well as match main.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-001-superseded.md"
        adr.write_text("# ADR 001\n\nthe old position.\n", encoding="utf-8")
        _commit(repo, "old position")
        # The local ref stops here. Someone else already pushed the revision.
        head = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "update-ref", "refs/remotes/origin/main", head)
        adr.write_text("# ADR 001\n\nthe revised position.\n", encoding="utf-8")
        _commit(repo, "revised position")

        _git(repo, "checkout", "-b", "feature")
        (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
        _commit(repo, "feature work")
        _git(repo, "branch", "sibling")
        _git(repo, "checkout", "sibling")
        (repo / "sibling.txt").write_text("sibling\n", encoding="utf-8")
        _commit(repo, "sibling work")
        _git(repo, "checkout", "feature")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "sibling"], repo)
        assert merge.returncode == 0, merge.stderr

        relative = ".agents/architecture/ADR-001-superseded.md"
        adr.write_text("# ADR 001\n\nthe old position.\n", encoding="utf-8")
        _git(repo, "add", relative)

        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require a debate log" in capsys.readouterr().err

    def test_an_adr_a_collaborator_wrote_on_the_shared_branch_is_still_gated(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Arriving through the merge is not enough on its own.

        A collaborator can write an ADR on the shared branch and push it. The
        content then sits on a merge parent without ever having been reviewed
        on main. Exempting it because the merge carried it would let any pair
        of branches walk an ADR onto main with no review evidence at all, so
        the content has to match main as well as arrive through the merge.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-003-collaborator.md"
        adr.write_text("# ADR 003\n\nthe reviewed position.\n", encoding="utf-8")
        _commit(repo, "reviewed position")
        head = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "update-ref", "refs/remotes/origin/main", head)

        _git(repo, "checkout", "-b", "shared")
        adr.write_text("# ADR 003\n\nthe collaborator position.\n", encoding="utf-8")
        _commit(repo, "collaborator writes the adr on the branch")

        _git(repo, "checkout", "main")
        _git(repo, "checkout", "-b", "feature")
        (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
        _commit(repo, "feature work")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "shared"], repo)
        assert merge.returncode == 0, merge.stderr

        relative = ".agents/architecture/ADR-003-collaborator.md"
        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require a debate log" in capsys.readouterr().err

    def test_an_approved_merge_parent_exempts_content_origin_main_does_not_carry(
        self,
        tmp_path,
        monkeypatch,
    ):
        """The approved-parent rule has to keep working on its own.

        Merging an older main commit brings content that the local `origin/main`
        tip no longer carries, so the blob comparison against main cannot
        exempt it and the ancestry rule is the only thing that can. Without
        this the ancestry rule could be deleted outright and every other test
        here would stay green.
        """
        path = ".agents/architecture/ADR-002-an-earlier-main.md"
        blobs = {"an-approved-parent": b"earlier main", "origin/main": b"later main"}
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_read_index_blob", lambda root, relative_path: b"earlier main")
        monkeypatch.setattr(policy, "_read_head_blob", lambda root, relative_path: None)
        monkeypatch.setattr(
            policy,
            "_approved_merge_head_commits",
            lambda root: ["an-approved-parent"],
            raising=False,
        )
        monkeypatch.setattr(
            policy,
            "_merge_head_commits",
            lambda root: ["an-approved-parent"],
            raising=False,
        )
        monkeypatch.setattr(
            policy,
            "_read_commit_blob_bytes",
            lambda root, commit, relative_path: blobs.get(commit),
            raising=False,
        )

        assert policy.check_adr_review_policy([path], tmp_path) == 0

    def test_a_carrier_branch_cannot_launder_a_reversion_past_a_stale_origin_main(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Matching a stale `origin/main` is not evidence of review.

        Requiring the blob to sit on a merge parent stops an author typing a
        reversion during someone else's merge, but it does not stop an author
        who builds the merge. Branch off the newer commit, commit the older
        ADR text there, merge that branch back, and both halves of the rule
        are satisfied: the blob is on a merge parent because the author put it
        there, and it matches `origin/main` because `origin/main` is stale.

        The gate cannot tell a stale ref from a current one offline, so it
        asks a different question instead: is the copy this branch already has
        one that main has ever carried. Here it is not, because the newer text
        was written locally and never pushed, which makes the merge a
        regression of local work rather than main's content arriving.

        Found by adversarial security review, Finding 3. It reproduces with no
        write to `.git` and no ref surgery, which is what separates it from
        the other two findings that round returned.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-004-carrier.md"
        adr.write_text("# ADR 004\n\nold reviewed position.\n", encoding="utf-8")
        old = _commit(repo, "the old position")
        _git(repo, "update-ref", "refs/remotes/origin/main", old)

        adr.write_text("# ADR 004\n\nnewer reviewed position.\n", encoding="utf-8")
        newer = _commit(repo, "the newer position, not yet pushed")

        _git(repo, "update-ref", "refs/heads/carrier", newer)
        _git(repo, "checkout", "carrier")
        adr.write_text("# ADR 004\n\nold reviewed position.\n", encoding="utf-8")
        _commit(repo, "carrier quietly restores the old text")

        _git(repo, "checkout", "main")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "--no-ff", "carrier"], repo)
        assert merge.returncode == 0, merge.stderr

        relative = ".agents/architecture/ADR-004-carrier.md"
        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require a debate log" in capsys.readouterr().err

    def test_a_synthetic_merge_head_that_head_already_contains_is_not_a_merge(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """A hand-written `MERGE_HEAD` naming an ancestor is never a real merge.

        `git merge <ancestor>` reports "Already up to date" and writes no
        `MERGE_HEAD` at all, so any `MERGE_HEAD` that HEAD already contains
        was placed there by something other than git. Reading it as a merge
        in progress hands the whole merge exemption to anyone who can write a
        file, and the older commit it names is an approved parent by
        construction, so the reversion it authorises is the exact thing the
        gate exists to catch.

        Found by adversarial security review, Finding 2. Unlike the carrier
        case this one needs a write inside `.git`, and an author who has that
        can also skip the hook outright. It is fixed anyway because the check
        costs one ancestry query and removes a way to get the same result
        while the hook still reports success.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-005-synthetic.md"
        adr.write_text("# ADR 005\n\nold reviewed position.\n", encoding="utf-8")
        old = _commit(repo, "the old position")

        adr.write_text("# ADR 005\n\nnewer reviewed position.\n", encoding="utf-8")
        newer = _commit(repo, "the newer position")
        _git(repo, "update-ref", "refs/remotes/origin/main", newer)

        adr.write_text("# ADR 005\n\nold reviewed position.\n", encoding="utf-8")
        _git(repo, "add", ".")
        (repo / ".git" / "MERGE_HEAD").write_text(f"{old}\n", encoding="utf-8")

        relative = ".agents/architecture/ADR-005-synthetic.md"
        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require a debate log" in capsys.readouterr().err

    def test_a_real_merge_of_a_shared_branch_tip_exempts_the_adr_main_contributed(
        self,
        tmp_path,
        monkeypatch,
    ):
        """End-to-end proof against a real repository, no git calls stubbed.

        The monkeypatched checks above describe the shape of the bug. This one
        reproduces it: main gains an ADR, a collaborator merges main into the
        shared branch and the next author merges that branch tip, so MERGE_HEAD
        names the branch and not main. The staged ADR is byte-identical to
        main's copy, so the gate must let it through.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        _commit(repo, "base")
        # `local` is cut here rather than by start-point later: git 2.43
        # rejects an explicit commit as a branch point when GIT_TRACE_REFS
        # leaks in from the environment. The head guard blocks that variable.
        _git(repo, "branch", "local")

        _git(repo, "checkout", "-b", "shared")
        (repo / "branch.txt").write_text("branch work\n", encoding="utf-8")
        _commit(repo, "branch work")

        _git(repo, "checkout", "main")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-089-from-main.md"
        adr.write_text("# ADR 089\n\nmain wrote this.\n", encoding="utf-8")
        _commit(repo, "adr on main")
        main_tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "update-ref", "refs/remotes/origin/main", main_tip)

        # A collaborator merges main into the shared branch and pushes.
        _git(repo, "checkout", "shared")
        _git(repo, "merge", "--no-edit", "main")

        # The author, still on the old branch point, merges that shared tip.
        _git(repo, "checkout", "local")
        (repo / "local.txt").write_text("local work\n", encoding="utf-8")
        _commit(repo, "local work")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "shared"], repo)
        assert merge.returncode == 0, merge.stderr

        relative = ".agents/architecture/ADR-089-from-main.md"
        assert policy._merge_in_progress(repo) is True
        assert policy._merge_authored_adr_paths([relative], repo) == []

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )
        assert policy.check_adr_review_policy([relative], repo) == 0

    def test_a_real_merge_still_gates_an_adr_the_author_wrote_on_the_branch(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Negative control for the real-repository check above.

        Same repository shape, but the staged ADR differs from main's copy
        because the author edited it during the merge. Nothing on main carries
        that content, so no exemption applies and the gate blocks.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        _commit(repo, "base")
        # `local` is cut here rather than by start-point later: git 2.43
        # rejects an explicit commit as a branch point when GIT_TRACE_REFS
        # leaks in from the environment. The head guard blocks that variable.
        _git(repo, "branch", "local")

        _git(repo, "checkout", "-b", "shared")
        (repo / "branch.txt").write_text("branch work\n", encoding="utf-8")
        _commit(repo, "branch work")

        _git(repo, "checkout", "main")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-089-from-main.md"
        adr.write_text("# ADR 089\n\nmain wrote this.\n", encoding="utf-8")
        _commit(repo, "adr on main")
        main_tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "update-ref", "refs/remotes/origin/main", main_tip)

        _git(repo, "checkout", "shared")
        _git(repo, "merge", "--no-edit", "main")

        _git(repo, "checkout", "local")
        (repo / "local.txt").write_text("local work\n", encoding="utf-8")
        _commit(repo, "local work")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "shared"], repo)
        assert merge.returncode == 0, merge.stderr

        relative = ".agents/architecture/ADR-089-from-main.md"
        (repo / relative).write_text("# ADR 089\n\nthe author rewrote this.\n", encoding="utf-8")
        _git(repo, "add", relative)

        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require a debate log" in capsys.readouterr().err

    def test_merge_of_a_shared_branch_tip_still_gates_content_main_does_not_have(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Negative control for the check above.

        An ADR written on the branch during the same merge differs from main's
        copy, or main has no copy at all, so the blob comparison must not
        exempt it. Without this the previous test would pass just as well
        against a check that exempted every path once a merge was underway.
        """
        path = ".agents/architecture/ADR-999-written-during-the-merge.md"
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_read_index_blob", lambda root, relative_path: b"authored adr")
        monkeypatch.setattr(policy, "_read_head_blob", lambda root, relative_path: None)
        monkeypatch.setattr(
            policy,
            "_approved_merge_head_commits",
            lambda root: [],
            raising=False,
        )
        monkeypatch.setattr(
            policy,
            "_merge_head_commits",
            lambda root: ["the-shared-branch-tip"],
            raising=False,
        )
        blobs = {"the-shared-branch-tip": b"main adr", "origin/main": b"main adr"}
        monkeypatch.setattr(
            policy,
            "_read_commit_blob_bytes",
            lambda root, commit, relative_path: blobs.get(commit),
            raising=False,
        )
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )

        assert policy.check_adr_review_policy([path], tmp_path) == 1
        assert "ADR changes require a debate log" in capsys.readouterr().err

    def test_line_endings_alone_do_not_make_a_staged_adr_mains_content(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """The exemption is byte identity, so it has to be read in bytes.

        The blob readers ran `git show` through a text-mode pipe, which
        translates every `\\r\\n` and every lone `\\r` to `\\n` before the bytes are
        handed back. Two blobs that differ only in how they end their lines
        arrived identical, so a staged ADR the merge never carried satisfied
        both blob halves of the rule and left through main's exemption.

        Found by adversarial review round 51.
        """
        repo = _merge_carrying_main_adr(
            tmp_path, b"# ADR 090\n\nmain wrote this.\n", "ADR-090-endings.md"
        )
        relative = ".agents/architecture/ADR-090-endings.md"
        (repo / relative).write_bytes(b"# ADR 090\r\n\r\nmain wrote this.\r\n")
        _git(repo, "add", relative)

        assert policy._read_index_blob(repo, relative) != policy._read_head_blob(repo, relative)
        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require a debate log" in capsys.readouterr().err

    def test_two_different_undecodable_blobs_are_not_one_blob(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Decoding with `errors="replace"` collapses distinct bytes to one.

        Every byte the decoder cannot read becomes U+FFFD, so any two blobs
        that differ only inside undecodable runs compared equal. This is the
        same defect as the line-ending case and the wider half of it: the
        collision needs no agreement about what the differing bytes mean.

        Found by adversarial review round 51.
        """
        repo = _merge_carrying_main_adr(
            tmp_path, b"# ADR 091\n\nmain \xff\xfe wrote this.\n", "ADR-092-endings.md"
        )
        relative = ".agents/architecture/ADR-092-endings.md"
        (repo / relative).write_bytes(b"# ADR 091\n\nmain \x80\x81 wrote this.\n")
        _git(repo, "add", relative)

        assert policy._read_index_blob(repo, relative) != policy._read_head_blob(repo, relative)
        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require a debate log" in capsys.readouterr().err

    def test_a_merge_that_carries_crlf_content_keeps_mains_exemption(
        self,
        tmp_path,
    ):
        """Reading the merge parent as text costs the exemption it should grant.

        This is the same normalization seen from the other side. When main's
        own ADR ends its lines with `\r\n`, a text-mode read of the parent
        hands back `\n` while the staged blob still holds what git stored, so
        the two stop matching and an ADR the author never opened is reported
        as branch-authored. Nothing is let through, but review evidence is
        demanded for someone else's file, which is how a gate loses its
        audience.

        Found by adversarial review round 51.
        """
        relative = ".agents/architecture/ADR-094-carried.md"
        carried = b"# ADR 094\r\n\r\nmain wrote this.\r\n"
        repo = _merge_carrying_main_adr(tmp_path, carried, "ADR-094-carried.md")

        assert policy._read_index_blob(repo, relative) == carried
        assert policy._merge_authored_adr_paths([relative], repo) == []

    def test_crlf_content_the_merge_left_alone_is_still_unchanged_from_head(
        self,
        tmp_path,
    ):
        """A path the merge did not touch is recognized by HEAD's bytes.

        The branch wrote this ADR itself and the merge brought something
        else, so the staged copy is what HEAD already had and no merge
        exemption is involved. A text-mode read of HEAD folds the `\r\n`
        endings the branch committed, the staged copy no longer matches, and
        an untouched file is pushed down the merge-exemption path to be
        reported as authored by a merge that never saw it.

        Found by adversarial review round 51.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        (repo / ".gitattributes").write_text("* -text\n", encoding="utf-8")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        _commit(repo, "base")
        _git(repo, "branch", "local")

        (repo / "README.md").write_text("main moved on\n", encoding="utf-8")
        _commit(repo, "main work")
        _point_origin_main_at_head(repo)

        _git(repo, "checkout", "local")
        relative = ".agents/architecture/ADR-095-branch.md"
        (repo / relative).parent.mkdir(parents=True)
        (repo / relative).write_bytes(b"# ADR 095\r\n\r\nthe branch wrote this.\r\n")
        _commit(repo, "branch adr")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "--no-ff", "main"], repo)
        assert merge.returncode == 0, merge.stderr

        assert policy._read_head_blob(repo, relative) == policy._read_index_blob(repo, relative)
        assert policy._merge_authored_adr_paths([relative], repo) == []

    def test_typing_mains_text_during_an_unrelated_merge_is_not_the_merge_carrying_it(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """The merge-parent clause had no test that failed when it was removed.

        Round 50 claimed every clause of this rule was mutation-proved. It was
        not. The stale-`origin/main` test fails the head-copy clause as well,
        so deleting the merge-parent clause left the whole class green. This
        is the discriminator that separates them: the staged blob matches
        `origin/main`, the copy it replaces is one `origin/main` has carried,
        and the merge carried nothing of the kind.

        The exemption is for what a merge brought in. An author who types the
        text during someone else's merge has not been reviewed by that merge,
        and whether the text is current or a reversion depends on how stale
        `origin/main` is, which this gate cannot see.

        Found by adversarial review round 51.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-092-typed.md"
        adr.write_text("# ADR 092\n\nfirst position.\n", encoding="utf-8")
        _commit(repo, "first position")
        _git(repo, "branch", "local")
        _git(repo, "branch", "side")

        adr.write_text("# ADR 092\n\nsecond position.\n", encoding="utf-8")
        _commit(repo, "second position")
        _point_origin_main_at_head(repo)

        _git(repo, "checkout", "side")
        (repo / "side.txt").write_text("side work\n", encoding="utf-8")
        _commit(repo, "side work")

        _git(repo, "checkout", "local")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "--no-ff", "side"], repo)
        assert merge.returncode == 0, merge.stderr

        relative = ".agents/architecture/ADR-092-typed.md"
        adr.write_text("# ADR 092\n\nsecond position.\n", encoding="utf-8")
        _git(repo, "add", relative)

        staged = policy._read_index_blob(repo, relative)
        merge_parents = policy._merge_head_commits(repo)
        assert policy._blob_is_at_any(repo, merge_parents, relative, staged) is False
        assert policy._read_commit_blob_bytes(repo, "origin/main", relative) == staged
        assert policy._head_copy_is_one_main_has_carried(repo, relative) is True

        assert policy._merge_authored_adr_paths([relative], repo) == [relative]
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require a debate log" in capsys.readouterr().err

    def test_a_rename_does_not_hide_the_history_the_head_copy_came_from(
        self,
        tmp_path,
        monkeypatch,
    ):
        """Renaming an ADR must not turn main's own revision into gated work.

        The head-copy clause asked `rev-list` for the commits touching one
        pathname, which stops at the rename. An ADR renamed on both branches
        and revised on main then failed the clause on the branch's own copy,
        because that copy lived under the former name, and a merge that only
        brought main's revision in demanded review evidence for it.

        Found by adversarial review round 51.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        old_name = ".agents/architecture/ADR-093-old.md"
        new_name = ".agents/architecture/ADR-093-new.md"
        # Long enough that a one-line revision still scores as a rename. Git
        # pairs paths at 50% similarity by default, and a three-line fixture
        # would need the threshold lowered to pass, which would be tuning the
        # gate to the test rather than to the documents it guards.
        body = "\n".join(f"Context paragraph {index}." for index in range(20))
        first = f"# ADR 093\n\n{body}\n\nDecision: first position.\n"
        second = f"# ADR 093\n\n{body}\n\nDecision: second position.\n"
        (repo / old_name).write_text(first, encoding="utf-8")
        _commit(repo, "first position")
        _git(repo, "branch", "local")

        _git(repo, "mv", old_name, new_name)
        (repo / new_name).write_text(second, encoding="utf-8")
        _commit(repo, "rename and revise on main")
        _point_origin_main_at_head(repo)

        _git(repo, "checkout", "local")
        _git(repo, "mv", old_name, new_name)
        _commit(repo, "the branch renamed it too")

        # Both sides moved the file, so the merge pairs the renames and takes
        # main's revision on its own. Nothing here is authored by the branch.
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "--no-ff", "main"], repo)
        assert merge.returncode == 0, merge.stderr
        assert policy._read_index_blob(repo, new_name) == second.encode("utf-8")

        assert policy._head_copy_is_one_main_has_carried(repo, new_name) is True
        assert policy._merge_authored_adr_paths([new_name], repo) == []

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(
            policy, "_session_log_for_current_branch", lambda sessions_dir, repo_root: None
        )
        assert policy.check_adr_review_policy([new_name], repo) == 0

    def test_a_conflict_main_resolved_in_a_merge_is_a_state_main_has_carried(
        self,
        tmp_path,
    ):
        """`git log --raw` says nothing about a merge unless it is asked to.

        Without `-m`, git prints no diff for a merge commit, so an ADR whose
        only appearance in that state was a conflict resolution left no blob id
        behind. A branch sitting on that resolution held content main really
        had carried and still failed the head-copy clause, which demands review
        evidence for a file the branch never opened.

        The revision after the merge is what makes this observable: without it
        the resolution is `origin/main`'s tip and the tip lookup covers it.

        Found by adversarial review round 52.
        """
        repo, name, resolved = _repo_where_main_resolved_an_adr_in_a_merge(tmp_path)

        assert policy._read_head_blob(repo, name) == resolved

        assert policy._head_copy_is_one_main_has_carried(repo, name) is True

    def test_a_users_diff_merges_setting_does_not_hide_the_resolution(
        self,
        tmp_path,
    ):
        """`-m` takes its output format from the user's `log.diffMerges`.

        `-m` means `--diff-merges=on`, and `on` defers to whatever
        `log.diffMerges` says. Set to `combined` or `dense-combined`, the merge
        prints one `::` record instead of one `:` record per parent, and that
        record is laid out differently: the fourth field is the first parent's
        pre-image rather than the post-image. So the resolution blob went
        missing again, and a blob nobody asked about took its place in the set.

        Asking for `separate` by name pins the format the parser was written
        for. The setting is a normal user preference, not an attack, and the
        gate runs on whatever machine the developer configured.

        Found by a bot reviewer on PR #3680.
        """
        repo, name, resolved = _repo_where_main_resolved_an_adr_in_a_merge(
            tmp_path,
            diff_merges="combined",
        )

        assert policy._read_head_blob(repo, name) == resolved

        assert policy._head_copy_is_one_main_has_carried(repo, name) is True

    def test_the_blob_set_is_the_same_under_every_diff_merges_setting(
        self,
        tmp_path,
    ):
        """No user preference may change what this gate accepts.

        `log.diffMerges` has seven values in git 2.43 and `-m` honours all of
        them, so the set the gate reasons about moved with a setting the
        developer chose for readability. Naming the format instead makes the
        answer the same on every machine, which is the property worth
        asserting: not that one value works, but that the setting is not an
        input.

        `remerge` is included so the enumeration is the whole set rather than
        the values that happened to come to mind. It reconstructs the merge
        rather than reporting it, so it is the value least like the others.
        """
        answers = {}
        for setting in (
            "combined",
            "dense-combined",
            "separate",
            "on",
            "first-parent",
            "off",
            "remerge",
        ):
            repo, name, _ = _repo_where_main_resolved_an_adr_in_a_merge(
                tmp_path / setting,
                diff_merges=setting,
            )
            answers[setting] = policy._origin_main_blob_ids(repo, name)

        assert len(set(map(frozenset, answers.values()))) == 1, answers

    def test_a_state_only_the_plain_traversal_reaches_is_still_carried(
        self,
        tmp_path,
    ):
        """Asking for merge diffs must not cost a state main already had.

        `--follow` rewrites the path it is following each time it detects a
        rename, so which rename it sees decides which lineage it walks. Asking
        for merge diffs makes the merge-versus-first-parent rename visible, and
        following that one walks main's side of the history and reports the
        side branch's file as a deletion rather than crossing into it.

        The side branch's revision is a state of this file on `origin/main`,
        and the implementation before merge diffs were asked for returned it.
        Trading it away for the resolution blob swaps one silent gap for
        another: a branch sitting on that revision holds content main really
        carried, and demanding review evidence for it is the false positive
        this whole lookup exists to prevent.
        """
        repo, name, side_blob = _repo_where_a_rename_crossed_a_merge(tmp_path)

        assert side_blob in policy._origin_main_blob_ids(repo, name)

    def test_an_adr_whose_name_needs_quoting_is_still_read(
        self,
        tmp_path,
    ):
        """A path git quotes has to reach the scope test as git spells it.

        `core.quotePath` is on by default, so a name outside ASCII prints
        octal-escaped inside double quotes. The trailing quote alone defeats
        the end anchor the scope pattern ends on, and the escapes defeat the
        word characters before it, so every record for the file drops and its
        history reads as empty. The gate governs the file either way, so the
        answer would be review evidence demanded for an ADR whose only
        peculiarity is its name.
        """
        repo = tmp_path / "repo"
        repo.mkdir(parents=True)
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        # On by default. Named so the test states what it exercises rather
        # than inheriting it from whoever runs it.
        _git(repo, "config", "core.quotePath", "true")
        name = ".agents/architecture/ADR-100-caf\u00e9.md"
        (repo / ".agents" / "architecture").mkdir(parents=True)
        (repo / name).write_text("decision\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "add")
        _git(repo, "update-ref", "refs/remotes/origin/main", "main")
        blob = _git(repo, "rev-parse", "main:" + name).stdout.strip()

        assert blob in policy._origin_main_blob_ids(repo, name)

    def test_an_adr_under_a_quoted_directory_is_still_read(
        self,
        tmp_path,
    ):
        """Turning quoting off is not the same as never being quoted.

        git quotes a path carrying a double quote, a backslash or a control
        character whatever `core.quotePath` says, so suppressing the setting
        answers only the accented-name half. Reading the records in a format
        that separates paths by NUL answers both.
        """
        repo = tmp_path / "repo"
        repo.mkdir(parents=True)
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        directory = repo / ".agents" / 'arch"itecture'
        directory.mkdir(parents=True)
        name = '.agents/arch"itecture/ADR-101-quoted.md'
        (repo / name).write_text("decision\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "add")
        _git(repo, "update-ref", "refs/remotes/origin/main", "main")
        blob = _git(repo, "rev-parse", "main:" + name).stdout.strip()

        assert blob in policy._origin_main_blob_ids(repo, name)

    def test_a_path_that_only_a_newline_rewrite_makes_governed_is_not_carried(
        self,
        tmp_path,
    ):
        """A carriage return in a path must not turn it into a governed one.

        `-z` is passed so paths arrive raw, but reading the stream in text mode
        applies universal newline translation, so a trailing carriage return
        becomes a newline, and `$` matches before a trailing newline. A path
        this gate does not govern then reads as one, and content that never sat
        at a governed path joins the set of blobs main is treated as having
        carried. A branch holding that content is then exempted from review
        (issue #3722).
        """
        repo = tmp_path / "repo"
        repo.mkdir(parents=True)
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        directory = repo / ".agents" / "architecture"
        directory.mkdir(parents=True)
        governed = ".agents/architecture/ADR-101-real.md"
        ungoverned = governed + "\r"
        (repo / ungoverned).write_text("never reviewed\n" + "a\n" * 40, encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "add under a carriage return name")
        unreviewed = _git(repo, "rev-parse", "main:" + ungoverned).stdout.strip()
        _git(repo, "mv", ungoverned, governed)
        (repo / governed).write_text("the reviewed decision\n" + "a\n" * 40, encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "rename onto the governed name and revise")
        reviewed = _git(repo, "rev-parse", "main:" + governed).stdout.strip()
        _git(repo, "update-ref", "refs/remotes/origin/main", "main")

        carried = policy._origin_main_blob_ids(repo, governed)

        assert unreviewed not in carried
        assert reviewed in carried

    def test_a_path_carrying_invalid_utf8_survives_the_read(
        self,
        tmp_path,
    ):
        """Reading bytes must not drop a governed record on undecodable bytes.

        This pins the read path rather than the error handler. Identity here is
        the record's number, so a byte spent elsewhere in the path reaches no
        decision, and a `replace` handler passes this too. What would fail it is
        a read that errors or drops the record outright.
        """
        repo = tmp_path / "repo"
        repo.mkdir(parents=True)
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        directory_name = os.fsdecode(b"arch\xffitecture")
        directory = repo / ".agents" / directory_name
        directory.mkdir(parents=True)
        name = f".agents/{directory_name}/ADR-102-undecodable.md"
        (repo / name).write_text("decision\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "add")
        _git(repo, "update-ref", "refs/remotes/origin/main", "main")
        blob = _git(repo, "rev-parse", "main:" + name).stdout.strip()

        assert blob in policy._origin_main_blob_ids(repo, name)

    def test_the_resolution_and_the_side_state_are_both_carried(
        self,
        tmp_path,
    ):
        """Neither traversal alone answers the question, so both must run."""
        repo, name, side_blob = _repo_where_a_rename_crossed_a_merge(tmp_path)
        resolution = _git(repo, "rev-parse", "HEAD~1:" + name).stdout.strip()

        carried = policy._origin_main_blob_ids(repo, name)

        assert {side_blob, resolution} <= carried

    def test_a_combined_diff_record_is_never_read_as_a_post_image(
        self,
        tmp_path,
        monkeypatch,
    ):
        """Refuse a record shape the field positions do not describe.

        A `::` record carries one pre-image per parent before the post-image,
        so its fourth field is a pre-image and its width grows with the parent
        count. Reading it as a post-image puts a blob in the carried set that
        answers a question nobody asked.

        Naming the format should mean these never arrive. Skipping them is what
        keeps that true when a later git, or a flag someone adds here, produces
        one anyway, and the field positions are not self-describing enough to
        notice on their own.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        adr = ".agents/architecture/ADR-095-synthetic.md"
        combined = (
            "::100644 100644 100644 "
            "1111111111111111111111111111111111111111 "
            "2222222222222222222222222222222222222222 "
            "3333333333333333333333333333333333333333 MM\0" + adr + "\0"
            ":100644 100644 "
            "4444444444444444444444444444444444444444 "
            "5555555555555555555555555555555555555555 M\0" + adr + "\0"
            # Contains "ADR" and is not a path this gate governs. The
            # membership test the records are filtered by is the gate's own,
            # not a substring the name happens to carry.
            ":100644 100644 "
            "6666666666666666666666666666666666666666 "
            "7777777777777777777777777777777777777777 M\0docs/ADR-overview.md\0"
            # A file moved in to become an ADR. The post-image is at the ADR
            # path from this commit on, so the destination is what decides it,
            # and reading the source instead would drop a state main holds.
            ":100644 100644 "
            "9999999999999999999999999999999999999999 "
            "8888888888888888888888888888888888888888 R100\0notes.md\0" + adr + "\0"
        )
        monkeypatch.setattr(
            policy,
            "_run_git_bytes",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0, stdout=combined.encode("utf-8", "surrogateescape")
            ),
        )

        assert policy._origin_main_blob_ids(repo, adr) == {"5" * 40, "8" * 40}

    def test_a_deletions_empty_post_image_is_never_carried(
        self,
        tmp_path,
        monkeypatch,
    ):
        """A record that removes a file names no blob afterwards.

        Its post-image field is all zeros, which is not a state main carried
        and not an object at all. The width of that field follows the
        repository's hash, so dropping only the shorter one leaves the longer
        one in the set.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        adr = ".agents/architecture/ADR-098-deleted.md"
        records = (
            ":100644 000000 "
            "1111111111111111111111111111111111111111 " + "0" * 40 + " D\0" + adr + "\0"
            ":100644 000000 " + "2" * 64 + " " + "0" * 64 + " D\0" + adr + "\0"
            ":100644 100644 "
            "3333333333333333333333333333333333333333 "
            "4444444444444444444444444444444444444444 M\0" + adr + "\0"
        )
        monkeypatch.setattr(
            policy,
            "_run_git_bytes",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0, stdout=records.encode("utf-8", "surrogateescape")
            ),
        )

        assert policy._origin_main_blob_ids(repo, adr) == {"4" * 40}

    def test_a_lineage_the_gate_does_not_govern_is_not_carried(
        self,
        tmp_path,
    ):
        """`--follow` will cross into a file that was never an ADR.

        Rename detection is similarity, not provenance. A commit that drops one
        file and adds another is indistinguishable from a move, so `--follow`
        rewrites the path it is tracking onto the dropped file and keeps
        walking. Every state that file ever held then reads as a state of this
        ADR.

        When the file it crossed into is not one this gate governs, those
        states never faced ADR review at all: an ordinary file changes under
        ordinary review, and its contents were never a decision record. A
        branch placing one of them at an ADR path would be exempted from the
        review it exists to require, on content main never carried there.

        Found independently by two reviewers on PR #3680.
        """
        repo, adr_path, foreign = _repo_where_a_merge_linked_a_non_adr_file(tmp_path)
        moved_in = _git(repo, "rev-parse", "side:" + adr_path).stdout.strip()

        carried = policy._origin_main_blob_ids(repo, adr_path)

        assert foreign not in carried
        assert policy._head_copy_is_one_main_has_carried(repo, adr_path) is False
        # The state the file held once it was an ADR is main's to carry: the
        # record that moved it in has the ADR as its destination. Qualifying on
        # the source path instead would drop it and demand review evidence for
        # a state main really held at this path.
        assert moved_in in carried

    def test_a_file_merely_ending_in_the_protocol_name_is_not_carried(
        self,
        tmp_path,
    ):
        """A suffix match is not a path this gate governs.

        The ADR half of the path test is anchored to a path segment, so
        `docs/not-ADR-096-x.md` is correctly foreign. The protocol half was
        not, so any name ending in the protocol's filename matched it:
        `docs/fake-SESSION-PROTOCOL.md` read as governed, and a lineage
        `--follow` crossed into it was admitted as one main had carried.

        Found by review on PR #3680.
        """
        repo, adr_path, foreign = _repo_where_a_merge_linked_a_non_adr_file(
            tmp_path,
            ordinary="docs/fake-SESSION-PROTOCOL.md",
        )

        carried = policy._origin_main_blob_ids(repo, adr_path)

        assert foreign not in carried
        assert policy._head_copy_is_one_main_has_carried(repo, adr_path) is False

    def test_a_lineage_into_a_different_decision_record_is_not_carried(
        self,
        tmp_path,
    ):
        """Two ADRs are two decisions, however alike their text.

        Records written from one template share most of their lines, so git
        scores a commit that drops one and adds another as a rename of it.
        `--follow` then walks from the new record into the old one and every
        state the old one held reads as a state of the new.

        Both are paths this gate governs, so scoping the walk to governed
        paths does not refuse it. The content did face ADR review, but it
        faced it as a different decision. Placing it under this record's
        number is a decision nobody reviewed.

        Found by review on PR #3680.
        """
        repo, target, only_ever_elsewhere = _repo_where_a_merge_linked_two_adrs(tmp_path)

        carried = policy._origin_main_blob_ids(repo, target)

        assert only_ever_elsewhere not in carried
        assert policy._head_copy_is_one_main_has_carried(repo, target) is False

    def test_a_rename_within_one_adr_is_still_carried(
        self,
        tmp_path,
    ):
        """Refusing foreign lineages must not refuse the one this gate wants.

        The negative control for the two tests above. One decision record
        that main moved and revised keeps its number across the rename, so
        the states under its former name are still states of this record and
        stay carried.
        """
        repo, name, side_blob = _repo_where_a_rename_crossed_a_merge(tmp_path)

        assert side_blob in policy._origin_main_blob_ids(repo, name)

    def test_a_rename_that_only_repads_the_number_is_still_carried(
        self,
        tmp_path,
    ):
        """One record padded differently is still the same record.

        The identity is read as the literal text of the number, so `ADR-0003`
        and `ADR-003` compare unequal and the walk stops at the rename between
        them. This repo really made that rename, so a branch restoring a state
        the record held under its wider name is refused for no reason.
        """
        repo, name, before = _repo_where_a_rename_repadded_the_number(tmp_path, "ADR-003")

        assert before in policy._origin_main_blob_ids(repo, name)

    def test_a_rename_that_changes_the_number_is_still_refused(
        self,
        tmp_path,
    ):
        """The negative control. Repadding is not licence to cross records.

        Reading `ADR-0003` and `ADR-003` as one record must not also read
        `ADR-0003` and `ADR-004` as one: those are two decisions, and a state
        of the first is not a reviewed state of the second.
        """
        repo, name, before = _repo_where_a_rename_repadded_the_number(tmp_path, "ADR-004")

        assert before not in policy._origin_main_blob_ids(repo, name)

    def test_a_number_written_in_other_digits_stays_its_own_record(
        self,
        tmp_path,
    ):
        """Normalizing the padding must not normalize away the digits.

        `\\d` matches every decimal digit, not only ASCII, so a name written
        in Arabic-Indic digits is governed too. Reading its number as an
        integer would give it the identity of the ASCII record holding the
        same value, and a brand new file would inherit that record's reviewed
        history. Padding is normalized by text, so this stays distinct.
        """
        arabic = policy._governed_document_identity("ADR-\u0660\u0660\u0663.md")

        assert arabic is not None
        assert arabic != policy._governed_document_identity("ADR-3.md")

    def test_a_zero_inside_the_number_is_not_stripped(
        self,
        tmp_path,
    ):
        """Dropping the padding must not drop the value.

        Only the zeros in front are padding. Removing every zero would read
        `ADR-100` as `ADR-1`, and a hundredth record would inherit the first
        record's reviewed history.
        """
        hundredth = policy._governed_document_identity("ADR-100.md")

        assert hundredth != policy._governed_document_identity("ADR-1.md")
        assert hundredth == "ADR-100"

    def test_a_record_numbered_zero_keeps_a_number(
        self,
        tmp_path,
    ):
        """Stripping the padding off `ADR-000` must leave a number behind.

        The edge case of the strip: every digit is padding. The identity has
        to stay a number rather than become the bare prefix, or `ADR-000` and
        a name carrying no digits at all would read alike.
        """
        assert policy._governed_document_identity("ADR-000.md") == "ADR-0"

    def test_a_signed_history_is_still_read(
        self,
        tmp_path,
    ):
        """`log.showSignature` decorates the stream this gate parses.

        Set in the developer's own git config, it prefixes each commit's raw
        records with the verification result. The first field of the stream
        then begins with that text rather than with the colon every record
        starts with, so every record is skipped and the walk reports that
        main has carried nothing here. That refuses a record main plainly
        did carry, and it refuses it only for developers holding that
        setting.
        """
        repo, adr, carried = _repo_where_the_history_is_signed(tmp_path)

        assert carried in policy._origin_main_blob_ids(repo, adr)

    def test_an_unsigned_history_is_read_the_same_way(
        self,
        tmp_path,
    ):
        """The negative control for the test above.

        Naming the signature behaviour must not change what an ordinary
        repository reports, which is the whole point of naming it.
        """
        repo, adr, carried = _repo_where_the_history_is_signed(
            tmp_path,
            sign=False,
        )

        assert carried in policy._origin_main_blob_ids(repo, adr)


def _repo_where_a_merge_linked_a_non_adr_file(
    tmp_path: Path,
    ordinary: str = "notes.md",
) -> tuple[Path, str, str]:
    """Build a repo where `--follow` crosses from an ADR into an ordinary file.

    One branch edits `notes.md`; another drops it and adds an ADR holding that
    same text, which git scores as a rename. Merging the two puts the link on
    `origin/main`, so following the ADR walks into the file's history.

    Returns the repo, the ADR path, and a blob `notes.md` held before the link
    that was never at the ADR path in any commit.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "diff.renames", "true")

    adr = ".agents/architecture/ADR-096-linked.md"
    (repo / ".agents" / "architecture").mkdir(parents=True)
    (repo / ordinary).parent.mkdir(parents=True, exist_ok=True)
    (repo / ordinary).write_bytes(b"the state that was never an adr\n")
    _git(repo, "add", "--", ordinary)
    _git(repo, "commit", "-qm", "an ordinary file")
    foreign = _git(repo, "rev-parse", "HEAD:" + ordinary).stdout.strip()

    _git(repo, "checkout", "-qb", "side", "HEAD")
    _git(repo, "rm", "-q", "--", ordinary)
    (repo / adr).write_bytes(b"carried text\n")
    _git(repo, "add", "--", adr)
    _git(repo, "commit", "-qm", "side drops the file and adds an adr")

    _git(repo, "checkout", "-q", "main")
    (repo / ordinary).write_bytes(b"carried text\n")
    _git(repo, "commit", "-qam", "main edits the ordinary file")

    _run(["git", "merge", "--no-edit", "side"], repo)
    (repo / ordinary).unlink(missing_ok=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "merge keeps the adr and drops the file")

    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

    _git(repo, "checkout", "-qb", "feature")
    (repo / adr).write_bytes(b"the state that was never an adr\n")
    _git(repo, "commit", "-qam", "place the file's old text at the adr path")
    return repo, adr, foreign


class TestGovernedDocumentIdentity:
    """The record a path holds, which is what scopes a followed history."""

    def test_one_record_keeps_its_identity_when_it_is_renamed(self):
        """The name after the number is free to change; the number is not."""
        assert policy._governed_document_identity(
            ".agents/architecture/ADR-201-old-name.md"
        ) == policy._governed_document_identity(".agents/architecture/ADR-201-new-name.md")

    def test_a_number_written_in_either_case_is_one_record(self):
        """The path test ignores case, so the identity read out of it must too.

        Read case-sensitively, a record renamed from a lowercased name to an
        uppercased one would look like two records and its earlier states
        would be refused, which is the false refusal following renames exists
        to remove.
        """
        assert policy._governed_document_identity(
            ".agents/architecture/adr-201-old-name.md"
        ) == policy._governed_document_identity(".agents/architecture/ADR-201-new-name.md")

    def test_two_numbers_are_two_records(self):
        assert policy._governed_document_identity(
            ".agents/architecture/ADR-201-first.md"
        ) != policy._governed_document_identity(".agents/architecture/ADR-202-second.md")

    def test_a_directory_named_for_a_record_does_not_shadow_the_file(self):
        """The number is read where the path test anchors: the last segment.

        Read across the whole path, the first number wins, so a file under a
        directory carrying another record's number reports that record. Two
        different decisions would then share one identity and a walk would
        cross between them, which is the hole scoping the walk closed.
        """
        nested = ".agents/ADR-201-old/ADR-202-new.md"

        assert policy._governed_document_identity(nested) == policy._governed_document_identity(
            ".agents/architecture/ADR-202-second.md"
        )
        assert policy._governed_document_identity(nested) != policy._governed_document_identity(
            ".agents/architecture/ADR-201-first.md"
        )

    def test_a_windows_separator_still_names_the_last_segment(self):
        """The path test accepts a backslash, so reading the number must too."""
        assert policy._governed_document_identity(
            r".agents\ADR-201-old\ADR-202-new.md"
        ) == policy._governed_document_identity(".agents/architecture/ADR-202-second.md")

    @pytest.mark.parametrize(
        "path",
        [
            "docs/ADR-overview.md",
            "docs/fake-SESSION-PROTOCOL.md",
            "notes.md",
            "",
        ],
    )
    def test_a_path_this_gate_does_not_govern_holds_no_record(self, path):
        assert policy._governed_document_identity(path) is None


def _repo_where_a_merge_linked_two_adrs(tmp_path: Path) -> tuple[Path, str, str]:
    """Build a repo where `--follow` crosses from one ADR into another.

    Both records carry the same template body and differ only in their title
    and their decision, which is enough alike that git reads a commit
    dropping the first and adding the second as a rename. Merging that branch
    puts the link on `origin/main`.

    Returns the repo, the second record's path, and a blob the first record
    held that the second one's path never held in any commit on main.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "diff.renames", "true")
    shared = "".join(f"a line every record from the template carries {i}\n" for i in range(60))

    first = ".agents/architecture/ADR-201-first.md"
    second = ".agents/architecture/ADR-202-second.md"
    (repo / ".agents" / "architecture").mkdir(parents=True)
    (repo / first).write_text("# ADR-201\n" + shared + "decision alpha\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "the first record")
    only_ever_elsewhere = _git(repo, "rev-parse", "HEAD:" + first).stdout.strip()

    (repo / first).write_text("# ADR-201\n" + shared + "decision alpha revised\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "revise the first record")

    _git(repo, "checkout", "-qb", "side", "HEAD~1")
    _git(repo, "rm", "-q", "--", first)
    (repo / ".agents" / "architecture").mkdir(parents=True, exist_ok=True)
    (repo / second).write_text("# ADR-202\n" + shared + "decision beta\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "side replaces it with a second record")

    _git(repo, "checkout", "-q", "main")
    (repo / ".agents" / "architecture").mkdir(parents=True, exist_ok=True)
    _run(["git", "merge", "--no-edit", "side"], repo)
    (repo / first).unlink(missing_ok=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "the merge keeps only the second record")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

    _git(repo, "checkout", "-qb", "feature")
    (repo / second).write_text("# ADR-201\n" + shared + "decision alpha\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "place the first record's old text under the second number")
    return repo, second, only_ever_elsewhere


def _repo_where_a_rename_crossed_a_merge(tmp_path: Path) -> tuple[Path, str, str]:
    """Build a repo where the rename is detectable on both sides of a merge.

    The side branch renames and edits, main edits the old name, and the merge
    resolves at the new name. The bodies are long enough that both the side
    rename and the merge-versus-first-parent rename clear git's similarity
    threshold, which is what makes the two traversals disagree about which
    lineage to follow. Short fixtures do not reproduce it.

    Returns the repo, the followed path, and the blob the side branch left.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "diff.renames", "true")
    body = "header\n" + "same line\n" * 30

    old_name = ".agents/architecture/ADR-097-moved.md"
    new_name = ".agents/architecture/ADR-097-renamed.md"
    (repo / ".agents" / "architecture").mkdir(parents=True)
    (repo / old_name).write_bytes((body + "base\n").encode("utf-8"))
    _git(repo, "add", "--", old_name)
    _git(repo, "commit", "-qm", "base")

    _git(repo, "checkout", "-qb", "side")
    _git(repo, "mv", old_name, new_name)
    (repo / new_name).write_bytes((body + "side renamed\n").encode("utf-8"))
    _git(repo, "commit", "-qam", "side renames and edits")
    side_blob = _git(repo, "rev-parse", "HEAD:" + new_name).stdout.strip()

    _git(repo, "checkout", "-q", "main")
    (repo / old_name).write_bytes((body + "main edit\n").encode("utf-8"))
    _git(repo, "commit", "-qam", "main edits the old name")

    merge = _run(["git", "merge", "--no-edit", "side"], repo)
    assert merge.returncode != 0, "the fixture needs the merge to conflict"
    (repo / old_name).unlink(missing_ok=True)
    (repo / new_name).write_bytes((body + "resolved renamed\n").encode("utf-8"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "merge resolves at the new name")

    (repo / new_name).write_bytes((body + "later\n").encode("utf-8"))
    _git(repo, "commit", "-qam", "later edit")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo, new_name, side_blob


def _repo_where_main_resolved_an_adr_in_a_merge(
    tmp_path: Path,
    diff_merges: str | None = None,
) -> tuple[Path, str, bytes]:
    """Build a repo whose ADR reached its current text inside a merge.

    Main and a side branch each revise the ADR, the merge conflicts, and main
    resolves it by hand. Main then revises the file again, which is what makes
    the resolution observable: without that last commit the resolution is
    `origin/main`'s tip and the separate tip lookup accounts for it.

    `local` sits on the resolution, so it holds content main really carried
    and any answer other than True demands review evidence for a file the
    branch never opened.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    if diff_merges is not None:
        _git(repo, "config", "log.diffMerges", diff_merges)
    adr_dir = repo / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    name = ".agents/architecture/ADR-096-contested.md"
    (repo / name).write_text("# ADR 096\n\nbase.\n", encoding="utf-8")
    _commit(repo, "base")

    _git(repo, "checkout", "-b", "sideways")
    (repo / name).write_text("# ADR 096\n\nsideways.\n", encoding="utf-8")
    _commit(repo, "sideways position")

    _git(repo, "checkout", "main")
    (repo / name).write_text("# ADR 096\n\nmainline.\n", encoding="utf-8")
    _commit(repo, "mainline position")

    conflicted = _run(["git", "merge", "--no-edit", "sideways"], repo)
    assert conflicted.returncode != 0, "the fixture needs a real conflict"
    resolved = "# ADR 096\n\nresolved in the merge.\n"
    (repo / name).write_text(resolved, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "--no-edit", "-m", "resolve the ADR while merging")
    _git(repo, "branch", "local")

    (repo / name).write_text("# ADR 096\n\nlater still.\n", encoding="utf-8")
    _commit(repo, "revise after the merge")
    _point_origin_main_at_head(repo)

    _git(repo, "checkout", "local")
    return repo, name, resolved.encode("utf-8")


def _merge_carrying_main_adr(tmp_path: Path, adr_bytes: bytes, name: str) -> Path:
    """Build a repo mid-merge whose staged ADR is the one main contributed.

    The exemption holds here, which is the point: each caller then restages
    bytes that differ from main's only in ways a text-mode pipe erases, so a
    test that still sees an exemption is reporting the normalization and not
    the rule.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / ".gitattributes").write_text("* -text\n", encoding="utf-8")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _commit(repo, "base")
    _git(repo, "branch", "local")

    adr_dir = repo / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / name).write_bytes(adr_bytes)
    _commit(repo, "adr on main")
    _point_origin_main_at_head(repo)

    _git(repo, "checkout", "local")
    (repo / "local.txt").write_text("local work\n", encoding="utf-8")
    _commit(repo, "local work")
    merge = _run(["git", "merge", "--no-edit", "--no-commit", "--no-ff", "main"], repo)
    assert merge.returncode == 0, merge.stderr
    return repo


def _repo_where_the_history_is_signed(
    tmp_path: Path,
    sign: bool = True,
) -> tuple[Path, str, str]:
    """Build a repo whose commits carry signatures the developer asks to see.

    Signing uses the ssh backend so the fixture needs only `ssh-keygen`, and
    verification is left to fail: an unknown signer still makes git print a
    verification line, which is the decoration under test. `sign=False`
    builds the same history without signatures for the negative control.
    """
    repo = tmp_path / "signed"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    if sign:
        key = repo / "signing-key"
        _run(
            [_tool("ssh-keygen"), "-q", "-t", "ed25519", "-N", "", "-C", "t", "-f", str(key)],
            repo,
        )
        assert key.with_suffix(".pub").exists(), "ssh-keygen produced no public key"
        _git(repo, "config", "gpg.format", "ssh")
        _git(repo, "config", "user.signingkey", str(key.with_suffix(".pub")))
        _git(repo, "config", "commit.gpgsign", "true")
    # The setting under test lives in the developer's own config, so the
    # fixture puts it there rather than passing it on the command line.
    _git(repo, "config", "log.showSignature", "true")

    # A session fixture in tests/conftest.py injects `commit.gpgsign=false`
    # through GIT_CONFIG_COUNT, which outranks the repo config written above.
    # Passing the setting on the command line outranks the injection in turn.
    signing = ("-c", "commit.gpgsign=true") if sign else ()

    adr = ".agents/architecture/ADR-099-signed.md"
    document = repo / adr
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text("first\n", encoding="utf-8")
    _git(repo, "add", adr)
    _git(repo, *signing, "commit", "-m", "add a decision")
    document.write_text("second\n", encoding="utf-8")
    _git(repo, *signing, "commit", "-am", "revise it")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", head)
    if sign:
        signed = _git(repo, "cat-file", "commit", "HEAD").stdout
        assert "gpgsig" in signed, "the fixture did not actually sign the commit"

    carried = _git(repo, "rev-parse", "HEAD:" + adr).stdout.strip()
    return repo, adr, carried


def _repo_where_a_rename_repadded_the_number(
    tmp_path: Path,
    renamed_to: str,
) -> tuple[Path, str, str]:
    """Build a history where main renamed one record and kept its value.

    Modelled on this repo's own `ADR-0003-...` to `ADR-003-...` rename. The
    caller chooses the new number so the same fixture serves the negative
    control, where the rename really does cross into another record.
    """
    repo = tmp_path / ("repad-" + renamed_to)
    repo.mkdir()
    _init_push_repo(repo)

    before_name = ".agents/architecture/ADR-0003-tool-selection.md"
    after_name = f".agents/architecture/{renamed_to}-tool-selection.md"
    # Git reads a rename by similarity, so the revision has to leave most of
    # the body alone or there is no rename for the walk to cross.
    body = ["# Tool selection", "", "## Context", "", "One line per criterion.", ""]
    body += [f"criterion {n}" for n in range(20)]
    document = repo / before_name
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text("\n".join(body) + "\n", encoding="utf-8")
    _git(repo, "add", before_name)
    _git(repo, "commit", "-m", "record the decision")
    before = _git(repo, "rev-parse", "HEAD:" + before_name).stdout.strip()

    _git(repo, "mv", before_name, after_name)
    body[4] = "One line per criterion, revised."
    (repo / after_name).write_text("\n".join(body) + "\n", encoding="utf-8")
    _git(repo, "add", after_name)
    _git(repo, "commit", "-m", "drop the extra zero")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", head)

    return repo, after_name, before


class TestBlobIdentityAndRenameLookup:
    """Blob identity and rename-crossing lookups behind the ADR-review gate."""

    def test_blob_readers_do_not_normalise_line_endings_or_undecodable_bytes(self, tmp_path):
        """Distinct blobs must not compare equal. Refs #3679.

        The readers ran through `_run_git`, which decodes with universal
        newlines and `errors="replace"`. A CRLF copy of an ADR and its LF
        original came back equal, and so did two files differing only in
        undecodable bytes. This gate reads equal as "the merge carried main's
        content", so a lossy comparison hands that decision to whoever stages
        the lossy copy.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        _git(repo, "config", "core.autocrlf", "false")
        (repo / ".gitattributes").write_text("* -text\n", encoding="utf-8")
        (repo / "lf.md").write_bytes(b"# ADR\n\nmain wrote this.\n")
        (repo / "invalid-a.bin").write_bytes(b"\xff\x01")
        (repo / "invalid-b.bin").write_bytes(b"\xfe\x02")
        _commit(repo, "base")

        (repo / "lf.md").write_bytes(b"# ADR\r\n\r\nmain wrote this.\r\n")
        _git(repo, "add", "lf.md")

        head = policy._read_head_blob(repo, "lf.md")
        staged = policy._read_index_blob(repo, "lf.md")
        assert head == b"# ADR\n\nmain wrote this.\n"
        assert staged == b"# ADR\r\n\r\nmain wrote this.\r\n"
        assert head != staged

        first = policy._read_head_blob(repo, "invalid-a.bin")
        second = policy._read_head_blob(repo, "invalid-b.bin")
        assert first == b"\xff\x01"
        assert second != first

    def test_head_copy_lookup_crosses_a_rename(self, tmp_path):
        """A copy main carried under a former name still counts. Refs #3679.

        `git rev-list -- <path>` stops at a rename, so an ADR main moved and
        revised in one commit left its earlier states behind under the former
        name. A branch holding a copy main really had carried then failed on
        the pathname alone and had review evidence demanded of it for someone
        else's revision.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        original = adr_dir / "ADR-100-former-name.md"
        first_text = "# ADR 100\n\n" + "".join(f"line {n}\n" for n in range(40))
        original.write_text(first_text, encoding="utf-8")
        _commit(repo, "adr under its first name")
        _git(repo, "branch", "local")

        renamed = ".agents/architecture/ADR-100-current-name.md"
        _git(repo, "mv", ".agents/architecture/ADR-100-former-name.md", renamed)
        (repo / renamed).write_text(first_text + "one revision line\n", encoding="utf-8")
        _commit(repo, "rename and revise in one commit")
        tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "update-ref", "refs/remotes/origin/main", tip)

        # The branch holds main's earlier text, already under the current name.
        _git(repo, "checkout", "local")
        (repo / renamed).parent.mkdir(parents=True, exist_ok=True)
        (repo / renamed).write_text(first_text, encoding="utf-8")
        (repo / ".agents" / "architecture" / "ADR-100-former-name.md").unlink()
        _git(repo, "add", "-A")
        _commit(repo, "carry main's earlier text under the current name")

        assert policy._head_copy_is_one_main_has_carried(repo, renamed) is True
        # Negative control: the walk that stops at the rename cannot see it.
        stopped = _git(repo, "rev-list", "origin/main", "--", renamed).stdout.split()
        assert len(stopped) == 1

    def test_head_copy_lookup_rejects_text_main_never_held(self, tmp_path):
        """Negative control for the rename fix. Refs #3679.

        Following renames widens the set of blobs the walk sees, so it has to
        be shown that the wider set still excludes content main never carried.
        Without this, returning every blob in the repository would pass.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        relative = ".agents/architecture/ADR-101-only-on-main.md"
        (repo / relative).write_text("# ADR 101\n\nmain wrote this.\n", encoding="utf-8")
        _commit(repo, "adr on main")
        tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "update-ref", "refs/remotes/origin/main", tip)

        (repo / relative).write_text("# ADR 101\n\nthe branch rewrote this.\n", encoding="utf-8")
        _git(repo, "add", relative)
        _commit(repo, "branch rewrite")

        assert policy._head_copy_is_one_main_has_carried(repo, relative) is False

    def test_the_merge_parent_clause_carries_a_case_the_later_clause_cannot(self, tmp_path):
        """Real-repository proof for the merge-parent clause. Refs #3679.

        The monkeypatched test above pins the code path. This one pins the git
        semantics behind it against a real repository: merging a main commit
        that is not main's tip leaves the staged blob on an approved merge
        parent while `origin/main` has moved on, so the later clause refuses it
        and only the merge-parent clause can carry the case.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        _commit(repo, "base")
        _git(repo, "branch", "local")

        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        relative = ".agents/architecture/ADR-102-revised-on-main.md"
        (repo / relative).write_text("# ADR 102\n\nfirst state.\n", encoding="utf-8")
        _commit(repo, "adr first state")
        _git(repo, "branch", "main-first-state")

        (repo / relative).write_text("# ADR 102\n\nsecond state.\n", encoding="utf-8")
        _commit(repo, "adr second state")
        tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "update-ref", "refs/remotes/origin/main", tip)

        _git(repo, "checkout", "local")
        # Local work first, or the merge fast-forwards and leaves no MERGE_HEAD.
        (repo / "local.txt").write_text("local work\n", encoding="utf-8")
        _commit(repo, "local work")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "main-first-state"], repo)
        assert merge.returncode == 0, merge.stderr

        staged = policy._read_index_blob(repo, relative)
        assert staged == b"# ADR 102\n\nfirst state.\n"
        parents = policy._merge_head_commits(repo)
        assert parents != []
        assert policy._approved_merge_head_commits(repo) == parents
        # The later clause cannot carry this case on its own.
        assert policy._blob_arrived_through_the_merge(repo, parents, relative, staged) is False
        # The merge-parent clause does, so the path is not branch-authored.
        assert policy._merge_authored_adr_paths([relative], repo) == []


def _complete_history_reply(
    repo_root: Path, args: list[str]
) -> subprocess.CompletedProcess[str] | None:
    """Answer the history-integrity probes, or None if this is not one of them.

    `check_suppression_diff` and `check_range_suppressions` gate on
    `_check_history_integrity` before they read any range (issue #4680), which
    adds two `rev-parse` calls ahead of every case below. These cases are about
    what the range check concludes on an intact clone, so the probes are
    answered as complete. The shallow and grafted legs are covered against real
    git in tests/ci/test_shallow_fetch_graft_guards.py.

    One helper rather than a copy per fake: six argv dispatchers answering the
    same two probes is six chances for them to drift apart.
    """
    if args == ["rev-parse", "--is-shallow-repository"]:
        return _completed("false\n")
    if args == ["rev-parse", "--git-path", "info/grafts"]:
        # `_check_no_grafts` treats a missing grafts file as clean, and nothing
        # creates this path under tmp_path, so this answers "no grafts".
        return _completed(str(repo_root / ".git" / "info" / "grafts") + "\n")
    return None


def _run_suppression_diff(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    diff_text: str,
    changed_paths: tuple[str, ...] = ("pkg/module.py",),
    *,
    base_ref: str = "c" * 40,
    rename_status_output: str = "",
) -> int:
    range_spec = f"{base_ref}..HEAD"

    def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        if (reply := _complete_history_reply(repo_root, args)) is not None:
            return reply
        if args[0] == "diff" and "--name-only" in args and "--diff-filter=ACMRT" in args:
            assert range_spec in args
            return _completed("\0".join(changed_paths) + "\0")
        if args[0] == "diff" and "--name-status" in args and "--diff-filter=R" in args:
            assert range_spec in args
            return _completed(rename_status_output)
        if "diff" in args and "--unified=0" in args:
            assert range_spec in args
            return _completed(diff_text)
        if args[0] == "show":
            return _completed("")
        raise AssertionError(f"unexpected git call: {args!r}")

    monkeypatch.setattr(policy, "_run_git", _run_git)
    return policy.check_suppression_diff(base_ref, repo_root)


class TestSuppressionDiff:
    """Tests for check_suppression_diff - CI backstop for issue #4061.

    Two-directional: blocks what it must block, permits what it must permit.
    """

    def test_new_nosec_in_diff_is_blocked(self, tmp_path, monkeypatch, capsys):
        comment = "# nos" + "ec"
        diff = (
            "diff --git a/pkg/module.py b/pkg/module.py\n"
            "--- a/pkg/module.py\n"
            "+++ b/pkg/module.py\n"
            "@@ -0,0 +1 @@\n"
            f"+import subprocess  {comment}\n"
        )
        assert _run_suppression_diff(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:1" in capsys.readouterr().err

    def test_new_s_rule_noqa_in_diff_is_blocked(self, tmp_path, monkeypatch, capsys):
        comment = "# no" + "qa: S101"
        diff = (
            "diff --git a/pkg/module.py b/pkg/module.py\n"
            "--- a/pkg/module.py\n"
            "+++ b/pkg/module.py\n"
            "@@ -0,0 +1 @@\n"
            f"+assert True  {comment}\n"
        )
        assert _run_suppression_diff(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:1" in capsys.readouterr().err

    def test_non_security_noqa_in_diff_is_allowed(self, tmp_path, monkeypatch):
        comment = "# noqa: E402"
        diff = (
            "diff --git a/pkg/module.py b/pkg/module.py\n"
            "--- a/pkg/module.py\n"
            "+++ b/pkg/module.py\n"
            "@@ -0,0 +1 @@\n"
            f"+import os  {comment}\n"
        )
        assert _run_suppression_diff(monkeypatch, tmp_path, diff) == 0

    def test_clean_diff_is_allowed(self, tmp_path, monkeypatch):
        diff = (
            "diff --git a/pkg/module.py b/pkg/module.py\n"
            "--- a/pkg/module.py\n"
            "+++ b/pkg/module.py\n"
            "@@ -1 +1 @@\n"
            "-old = 1\n"
            "+new = 1\n"
        )
        assert _run_suppression_diff(monkeypatch, tmp_path, diff) == 0

    def test_empty_changed_file_list_is_allowed(self, tmp_path, monkeypatch):
        def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
            if (reply := _complete_history_reply(tmp_path, args)) is not None:
                return reply
            if args[0] == "diff" and "--name-only" in args:
                return _completed("")
            raise AssertionError(f"unexpected git call: {args!r}")

        monkeypatch.setattr(policy, "_run_git", _run_git)
        assert policy.check_suppression_diff("c" * 40, tmp_path) == 0

    def test_git_error_on_initial_diff_returns_3(self, tmp_path, monkeypatch):
        def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
            if (reply := _complete_history_reply(tmp_path, args)) is not None:
                return reply
            return subprocess.CompletedProcess(["git"], 128, "", "fatal: not a git repo")

        monkeypatch.setattr(policy, "_run_git", _run_git)
        assert policy.check_suppression_diff("c" * 40, tmp_path) == 3

    def test_git_error_on_renames_returns_3(self, tmp_path, monkeypatch):
        base_ref = "c" * 40

        def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
            if (reply := _complete_history_reply(tmp_path, args)) is not None:
                return reply
            if args[0] == "diff" and "--name-only" in args:
                return _completed("pkg/module.py\0")
            if args[0] == "diff" and "--name-status" in args:
                return subprocess.CompletedProcess(["git"], 128, "", "fatal")
            raise AssertionError(f"unexpected git call: {args!r}")

        monkeypatch.setattr(policy, "_run_git", _run_git)
        assert policy.check_suppression_diff(base_ref, tmp_path) == 3

    def test_pure_rename_suppression_is_allowed(self, tmp_path, monkeypatch):
        """A suppression that moved via a pure rename is not flagged as new."""
        rename_output = "R100\0old/module.py\0new/module.py"
        assert (
            _run_suppression_diff(
                monkeypatch,
                tmp_path,
                "",
                changed_paths=("new/module.py",),
                rename_status_output=rename_output,
            )
            == 0
        )

    def test_non_py_extension_is_not_scanned(self, tmp_path, monkeypatch):
        """Files with extensions outside SECURITY_SUPPRESSION_SUFFIXES are skipped."""

        def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
            if (reply := _complete_history_reply(tmp_path, args)) is not None:
                return reply
            if args[0] == "diff" and "--name-only" in args:
                return _completed("pkg/data.csv\0pkg/README.md\0")
            raise AssertionError(f"unexpected git call: {args!r}")

        monkeypatch.setattr(policy, "_run_git", _run_git)
        assert policy.check_suppression_diff("c" * 40, tmp_path) == 0

    def test_invalid_base_ref_for_notebook_returns_rc3(self, tmp_path, monkeypatch):
        """_commit_text_for_base returns None on git failures that are NOT
        'file not in tree'.  That None propagates rc=3 through
        _diff_notebook_suppression_violations instead of producing spurious
        rc=1 violations (issue #4141 reviewer finding)."""
        base_ref = "c" * 40

        def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
            if (reply := _complete_history_reply(tmp_path, args)) is not None:
                return reply
            if args[0] == "diff" and "--name-only" in args and "--diff-filter=ACMRT" in args:
                return _completed("pkg/notebook.ipynb\0")
            if args[0] == "diff" and "--name-status" in args and "--diff-filter=R" in args:
                return _completed("")
            if "diff" in args and "--unified=0" in args:
                return _completed("")
            if args[0] == "show" and args[1].endswith(":pkg/notebook.ipynb"):
                ref = args[1].split(":")[0]
                if ref == "HEAD":
                    return _completed("{}")  # valid notebook at HEAD
                # base_ref: simulate git failure (bad ref or corrupt repo)
                return subprocess.CompletedProcess(
                    args, returncode=128, stdout="", stderr="fatal: some git error"
                )
            raise AssertionError(f"unexpected git call: {args!r}")

        monkeypatch.setattr(policy, "_run_git", _run_git)
        assert policy.check_suppression_diff(base_ref, tmp_path) == 3

    def test_new_notebook_file_missing_from_base_is_treated_as_empty(self, tmp_path, monkeypatch):
        """When a notebook is new (absent from base_ref), _commit_text_for_base
        returns '' so all suppressions in HEAD count as net-new additions.  A
        notebook with no security suppressions must still be rc=0."""
        base_ref = "c" * 40
        notebook_content = json.dumps(
            {"cells": [{"cell_type": "code", "source": "x = 1  # plain comment\n"}]}
        )

        def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
            if (reply := _complete_history_reply(tmp_path, args)) is not None:
                return reply
            if args[0] == "diff" and "--name-only" in args and "--diff-filter=ACMRT" in args:
                return _completed("pkg/new_nb.ipynb\0")
            if args[0] == "diff" and "--name-status" in args and "--diff-filter=R" in args:
                return _completed("")
            if "diff" in args and "--unified=0" in args:
                return _completed("")
            if args[0] == "show" and args[1].endswith(":pkg/new_nb.ipynb"):
                ref = args[1].split(":")[0]
                if ref == "HEAD":
                    return _completed(notebook_content)
                # file absent from base: git returns "does not exist in"
                return subprocess.CompletedProcess(
                    args,
                    returncode=128,
                    stdout="",
                    stderr=f"fatal: path 'pkg/new_nb.ipynb' does not exist in '{base_ref}'",
                )
            raise AssertionError(f"unexpected git call: {args!r}")

        monkeypatch.setattr(policy, "_run_git", _run_git)
        assert policy.check_suppression_diff(base_ref, tmp_path) == 0


def test_commit_text_for_base_returns_empty_for_new_file(tmp_path, monkeypatch):
    """_commit_text_for_base returns '' when git reports the file is absent
    from the base ref (new-file case), not None."""

    def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args,
            returncode=128,
            stdout="",
            stderr="fatal: path 'pkg/new.py' does not exist in 'abc123'",
        )

    monkeypatch.setattr(policy, "_run_git", _run_git)
    result = policy._commit_text_for_base("abc123", "pkg/new.py", tmp_path)
    assert result == ""


def test_commit_text_for_base_returns_none_on_git_error(tmp_path, monkeypatch, capsys):
    """_commit_text_for_base returns None (and prints stderr) when git fails for
    reasons other than the file being absent."""

    def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args, returncode=128, stdout="", stderr="fatal: bad object invalid_ref"
        )

    monkeypatch.setattr(policy, "_run_git", _run_git)
    result = policy._commit_text_for_base("invalid_ref", "pkg/new.py", tmp_path)
    assert result is None
    # Should print the git error so CI logs are diagnosable
    captured = capsys.readouterr()
    assert "bad object" in captured.out or "bad object" in captured.err


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
