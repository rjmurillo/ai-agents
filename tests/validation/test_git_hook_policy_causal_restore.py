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

The filename is stale and this file no longer tests causal restore. Three
classes covering the causal graph's snapshot-and-restore path were removed with
the graph itself (ADR-088). The two suites left never touched causality; they
shared this file only because both exercise ``git_hook_policy``.

Do not run ``ruff format`` on this file. The fixtures below split their
suppression tokens across adjacent string literals on purpose, so the push
gate's own scanner does not flag this file as introducing what it tests for.
Joining them, which the formatter does, re-arms the trap. Nothing in CI or the
hooks runs ``ruff format``, so the split form survives.

The honest fix for the name is a rename, and it is blocked. The gate diffs with
``--no-renames`` on purpose, so a rename reads as a wholesale add and the one
real suppression here, the ``E402`` on the import below, trips it. Renaming
requires teaching the gate to skip pure renames first. Filed as issue 3635.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validation import git_hook_policy as policy  # noqa: E402


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
    diff_without_no_renames: str | None = None,
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
        if "diff" in args and "--unified=0" in args:
            assert expected_range is not None
            assert expected_range in args
            for flag in policy.TEXTUAL_DIFF_FLAGS:
                assert flag in args
            if "--no-renames" not in args and diff_without_no_renames is not None:
                return _completed(diff_without_no_renames)
            separator = args.index("--")
            assert tuple(args[separator + 1 :]) == changed_paths
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


def _run_real_suppression_push(repo: Path, head: str) -> int:
    stdin = io.StringIO(f"refs/heads/topic {head} refs/heads/topic {'0' * 40}\n")
    return policy.check_pushed_suppressions(stdin, repo)


def _write_ruff_notebook(path: Path, source: str) -> None:
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [source],
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
        comment = "# no" "qa"
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

    def test_bare_type_ignore_is_honored_by_mypy_and_blocked_by_push_gate(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        comment = "# type" ": ignore"
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

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:1" in capsys.readouterr().err

    def test_newly_added_type_ignore_is_blocked(self, tmp_path, monkeypatch, capsys):
        suppression = "# type" ": ignore[arg-type]"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -1,0 +2 @@
+value = call()  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        err = capsys.readouterr().err
        assert "security suppression comments detected" in err
        assert "pkg/module.py:2" in err

    def test_pre_existing_type_ignore_touched_elsewhere_is_allowed(self, tmp_path, monkeypatch):
        diff = """diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -2 +2 @@
-old = 1
+new = 1
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0

    def test_added_file_with_type_ignore_is_blocked(self, tmp_path, monkeypatch, capsys):
        suppression = "# type" ": ignore[assignment]"
        diff = f"""diff --git a/pkg/new.py b/pkg/new.py
new file mode 100644
--- /dev/null
+++ b/pkg/new.py
@@ -0,0 +1,2 @@
+from pkg import value
+result = value  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff, ("pkg/new.py",)) == 1
        assert "pkg/new.py:2" in capsys.readouterr().err

    def test_type_ignore_on_context_line_adjacent_to_edit_is_allowed(self, tmp_path, monkeypatch):
        suppression = "# type" ": ignore[arg-type]"
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
        suppression = "# no" "sec"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -1,0 +4 @@
+++counter  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:4" in capsys.readouterr().err

    def test_no_prefix_diff_with_nosec_addition_is_blocked(self, tmp_path, monkeypatch, capsys):
        suppression = "# no" "sec"
        diff = f"""diff --git pkg/module.py pkg/module.py
--- pkg/module.py
+++ pkg/module.py
@@ -1,0 +3 @@
+value = call()  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:3" in capsys.readouterr().err

    def test_rename_into_scanned_suffix_with_existing_suppression_is_blocked(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        suppression = "# no" "sec"
        rename_only_diff = """diff --git a/pkg/payload.txt b/pkg/payload.py
similarity index 100%
rename from pkg/payload.txt
rename to pkg/payload.py
"""
        no_rename_diff = f"""diff --git a/pkg/payload.txt b/pkg/payload.py
deleted file mode 100644
--- a/pkg/payload.txt
+++ /dev/null
@@ -1 +0,0 @@
-value = call()
diff --git a/pkg/payload.py b/pkg/payload.py
new file mode 100644
--- /dev/null
+++ b/pkg/payload.py
@@ -0,0 +1 @@
+value = call()  {suppression}
"""

        assert (
            _run_suppression_push(
                monkeypatch,
                tmp_path,
                no_rename_diff,
                ("pkg/payload.py",),
                diff_without_no_renames=rename_only_diff,
            )
            == 1
        )
        assert "pkg/payload.py:1" in capsys.readouterr().err

    def test_new_branch_without_merge_base_is_config_error(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        suppression = "# type" ": ignore[arg-type]"
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
        suppression = "# type" ": ignore[arg-type]"
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
        suppression = "# no" "sec"
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
        suppression = "# no" "sec"
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
        suppression = "# no" "sec"
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
        suppression = "# no" "sec"
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
        comment = "# no" "qa"
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
        comment = "# no" "sec"
        path = repo / "tools" / "legacy_tls.pyw"
        path.parent.mkdir()
        path.write_text(
            "import ssl\n"
            "ssl.wrap_socket(ssl_version=ssl.PROTOCOL_SSLv3)  "
            f"{comment}\n",
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
        _write_ruff_notebook(path, "import os  # no" "qa\n")
        path.write_text(
            path.read_text(encoding="utf-8").replace("no" "qa", "no\\u0071a"),
            encoding="utf-8",
        )
        analyzer = _run([_tool("ruff"), "check", "--select", "F401", str(path)], _ROOT)
        assert analyzer.returncode == 0, analyzer.stdout + analyzer.stderr
        head = _commit(repo, "add notebook suppression")

        assert _run_real_suppression_push(repo, head) == 1

    def test_true_orphan_branch_scans_from_empty_tree(self, tmp_path, monkeypatch, capsys):
        suppression = "# type" ": ignore[arg-type]"
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
        suppression = "# type" ": ignore[arg-type]"
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


class TestAdrReviewPolicyMergeScope:
    def test_non_merge_adr_without_review_evidence_is_blocked(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: False)
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)

        result = policy.check_adr_review_policy(
            [".agents/architecture/ADR-999-test.md"],
            tmp_path,
        )

        assert result == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

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
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)

        result = policy.check_adr_review_policy(
            [path],
            tmp_path,
        )

        assert result == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

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
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)

        result = policy.check_adr_review_policy(
            [path],
            tmp_path,
        )

        assert result == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
