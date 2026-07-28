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
the graph itself (ADR-089). The two suites left never touched causality; they
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
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

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
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

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
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

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
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

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
        # `local` is cut here rather than by start-point later: the suite's
        # head guard exports GIT_TRACE_REFS, and git 2.43 rejects an explicit
        # commit as a branch point while that trace is on.
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
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
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
        # `local` is cut here rather than by start-point later: the suite's
        # head guard exports GIT_TRACE_REFS, and git 2.43 rejects an explicit
        # commit as a branch point while that trace is on.
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
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

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
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)

        assert policy.check_adr_review_policy([path], tmp_path) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err


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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
