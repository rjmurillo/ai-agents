#!/usr/bin/env python3
"""A comment-only edit to a CRITICAL file needs no security marker (issue #6509).

Path-only detection scored a one-line ``# comment`` edit in a workflow as
CRITICAL, so it demanded a full security review. With ``--diff-base`` the
detector reads the diff and exempts a change that touches plain comments and
blank lines only. A directive comment, a mode change, a code edit, a file kind
with no ``#`` comments, and a git failure all keep the gate closed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

from tests.validation._main_merge_repo import BRANCH, git, publish_main, write_commit

mod = import_skill_script(
    ".claude/skills/security-detection/detect_infrastructure.py",
    module_name="detect_infrastructure_comment_only_under_test",
)

WORKFLOW = ".github/workflows/ci.yml"
WORKFLOW_TEXT = "# build the project\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n"


def _diff(old: str, new: str) -> str:
    """Return a ``--unified=0`` style diff body for one hunk."""
    removed = "".join(f"-{line}\n" for line in old.splitlines())
    added = "".join(f"+{line}\n" for line in new.splitlines())
    header = "diff --git a/f b/f\nindex 1..2 100644\n--- a/f\n+++ b/f\n@@ -1 +1 @@\n"
    return header + removed + added


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("# old words", "# new words"),
        ("# note", "# note\n\n# more"),
        ("   # indented note", "   # reworded note"),
        ("", "# added comment"),
    ],
)
def test_plain_comment_edits_are_comment_only(old: str, new: str) -> None:
    assert mod._diff_is_comment_only(_diff(old, new)) is True


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("run: make", "run: make all"),
        ("# was a comment", "run: make"),
        ("run: make", "# run: make"),
        ("run: make  # trailing", "run: make  # other"),
        ("# note", "# " + "nosec B101"),
        ("# note", "# /// script"),
        ("# note", "# sourcery skip: no-loop"),
        ("# note", "# nolint"),
        ("# note", "# {{ matrix.os }}"),
        ("# note", "# Note: beware"),
        ("# note", "# key=value"),
        ("# note", "# yapf: disable"),
        ("# note", "# " + "noqa: E501"),
        ("# note", "# zizmor: ignore[template-injection]"),
        ("# note", "# shellcheck disable=SC2086"),
        ("# note", "# pragma: no cover"),
        (
            "# note",
            "# type: " + "ignore",
        ),  # built in two parts so the repo-wide ratchet does not count it
        ("# note", "# gitleaks:allow"),
        ("#!/bin/sh", "#!/bin/bash"),
        ("# note", "#!/bin/bash"),
    ],
)
def test_code_and_directive_edits_are_not_comment_only(old: str, new: str) -> None:
    assert mod._diff_is_comment_only(_diff(old, new)) is False


def test_empty_diff_is_not_comment_only() -> None:
    assert mod._diff_is_comment_only("") is False


@pytest.mark.parametrize(
    "header",
    [
        "diff --git a/f b/f\nold mode 100644\nnew mode 100755\n",
        "diff --git a/f b/f\nnew file mode 100644\nindex 0..1\n--- /dev/null\n+++ b/f\n",
        "diff --git a/f b/f\ndeleted file mode 100644\nindex 1..0\n--- a/f\n+++ /dev/null\n",
        "diff --git a/f b/f\nBinary files a/f and b/f differ\n",
    ],
)
def test_mode_new_deleted_and_binary_changes_are_not_comment_only(header: str) -> None:
    assert mod._diff_is_comment_only(header + "@@ -0,0 +1 @@\n+# comment\n") is False


def test_no_newline_marker_does_not_hide_a_comment_edit() -> None:
    diff = _diff("# old", "# new") + "\\ No newline at end of file\n"

    assert mod._diff_is_comment_only(diff) is True


# Real git ----------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    write_commit(tmp_path, WORKFLOW, WORKFLOW_TEXT)
    write_commit(
        tmp_path, "scripts/validation/git_hook_policy.py", "VALUE = 1\nOTHER = 2\n\n# policy\n"
    )
    write_commit(tmp_path, "lefthook.json", '{"a": 1}\n')
    publish_main(tmp_path)
    git(tmp_path, "checkout", "-q", "-b", BRANCH)
    return tmp_path


def _base(repo: Path) -> str:
    return git(repo, "merge-base", "origin/main", "HEAD")


def _enforce(repo: Path, files: list[str], diff_base: str | None = None):
    result = mod.detect_infrastructure(changed_files=files)
    code = mod.enforce_security_review(result, "HEAD", repo, diff_base=diff_base)
    return code, result["security_review"]


def test_comment_only_workflow_edit_needs_no_marker(repo: Path) -> None:
    write_commit(repo, WORKFLOW, WORKFLOW_TEXT.replace("build the project", "compile it"))

    code, review = _enforce(repo, [WORKFLOW], _base(repo))

    assert code == 0
    assert review["state"] == "SKIP"
    assert review["reason"] == "policy.exempt"
    assert review["satisfied"] is True
    assert "comments only" in review["detail"]


def test_comment_only_edit_without_diff_base_still_needs_a_marker(repo: Path) -> None:
    write_commit(repo, WORKFLOW, WORKFLOW_TEXT.replace("build the project", "compile it"))

    code, review = _enforce(repo, [WORKFLOW])

    assert code == 1
    assert review["state"] == "FAIL"


def test_code_edit_to_a_workflow_still_needs_a_marker(repo: Path) -> None:
    write_commit(repo, WORKFLOW, WORKFLOW_TEXT.replace("push", "pull_request_target"))

    code, review = _enforce(repo, [WORKFLOW], _base(repo))

    assert code == 1
    assert review["reason"] == "violations.found"


def test_two_commits_one_comment_one_code_still_need_a_marker(repo: Path) -> None:
    write_commit(repo, WORKFLOW, WORKFLOW_TEXT.replace("build the project", "compile it"))
    write_commit(repo, WORKFLOW, WORKFLOW_TEXT.replace("ubuntu-latest", "self-hosted"))

    code, _ = _enforce(repo, [WORKFLOW], _base(repo))

    assert code == 1


def test_one_code_file_among_comment_only_files_blocks(repo: Path) -> None:
    write_commit(repo, WORKFLOW, WORKFLOW_TEXT.replace("build the project", "compile it"))
    write_commit(
        repo, "scripts/validation/git_hook_policy.py", "VALUE = 2\nOTHER = 2\n\n# policy\n"
    )

    code, _ = _enforce(repo, [WORKFLOW, "scripts/validation/git_hook_policy.py"], _base(repo))

    assert code == 1


def test_comment_only_edits_to_two_critical_files_pass(repo: Path) -> None:
    write_commit(repo, WORKFLOW, WORKFLOW_TEXT.replace("build the project", "compile it"))
    write_commit(
        repo, "scripts/validation/git_hook_policy.py", "VALUE = 1\nOTHER = 2\n\n# policy notes\n"
    )

    code, _ = _enforce(repo, [WORKFLOW, "scripts/validation/git_hook_policy.py"], _base(repo))

    assert code == 0


def test_added_nosec_comment_still_needs_a_marker(repo: Path) -> None:
    write_commit(repo, WORKFLOW, WORKFLOW_TEXT + "# zizmor: ignore[template-injection]\n")

    code, _ = _enforce(repo, [WORKFLOW], _base(repo))

    assert code == 1


def test_mode_change_is_not_a_comment_edit(repo: Path) -> None:
    path = "scripts/validation/git_hook_policy.py"
    git(repo, "update-index", "--chmod=+x", path)
    git(repo, "commit", "-q", "-m", "chmod")

    code, _ = _enforce(repo, [path], _base(repo))

    assert code == 1


def test_file_kind_without_hash_comments_is_never_exempt(repo: Path) -> None:
    write_commit(repo, "lefthook.json", '{"a": 1}\n\n')

    code, _ = _enforce(repo, ["lefthook.json"], _base(repo))

    assert code == 1


def test_deleted_workflow_is_not_a_comment_edit(repo: Path) -> None:
    git(repo, "rm", "-q", WORKFLOW)
    git(repo, "commit", "-q", "-m", "drop workflow")

    code, _ = _enforce(repo, [WORKFLOW], _base(repo))

    assert code == 1


RUN_BLOCK = (
    "on: push\njobs:\n  build:\n    steps:\n      - run: |\n"
    "          echo one \\\n          # old note\n          echo two\n"
)


def test_comment_line_inside_a_run_block_is_content_not_a_comment(repo: Path) -> None:
    write_commit(repo, WORKFLOW, RUN_BLOCK)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _base(repo)
    write_commit(repo, WORKFLOW, RUN_BLOCK.replace("# old note\n          ", ""))

    code, _ = _enforce(repo, [WORKFLOW], base)

    assert code == 1


def test_reworded_line_inside_a_run_block_is_not_exempt(repo: Path) -> None:
    write_commit(repo, WORKFLOW, RUN_BLOCK)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _base(repo)
    write_commit(repo, WORKFLOW, RUN_BLOCK.replace("# old note", "# new note"))

    code, _ = _enforce(repo, [WORKFLOW], base)

    assert code == 1


def test_blank_line_inside_a_block_scalar_is_not_exempt(repo: Path) -> None:
    write_commit(repo, WORKFLOW, RUN_BLOCK)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _base(repo)
    write_commit(repo, WORKFLOW, RUN_BLOCK.replace("echo one", "\n          echo one"))

    code, _ = _enforce(repo, [WORKFLOW], base)

    assert code == 1


def test_comment_outside_a_block_scalar_in_a_rich_workflow_is_exempt(repo: Path) -> None:
    write_commit(repo, WORKFLOW, "# top\n" + RUN_BLOCK)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _base(repo)
    write_commit(repo, WORKFLOW, "# reworded top\n" + RUN_BLOCK)

    code, _ = _enforce(repo, [WORKFLOW], base)

    assert code == 0


def test_yaml_exemption_needs_pyyaml(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_commit(repo, WORKFLOW, WORKFLOW_TEXT.replace("build the project", "compile it"))
    monkeypatch.setitem(sys.modules, "yaml", None)

    code, _ = _enforce(repo, [WORKFLOW], _base(repo))

    assert code == 1


def test_unparseable_yaml_is_not_exempt(repo: Path) -> None:
    write_commit(repo, WORKFLOW, "# note\non: [unclosed\n")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _base(repo)
    write_commit(repo, WORKFLOW, "# reworded\non: [unclosed\n")

    code, _ = _enforce(repo, [WORKFLOW], base)

    assert code == 1


PY_PATH = "scripts/validation/git_hook_policy.py"


def test_comment_line_inside_a_python_string_is_not_exempt(repo: Path) -> None:
    write_commit(repo, PY_PATH, 'PROMPT = """\n# old\n"""\n')
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _base(repo)
    write_commit(repo, PY_PATH, 'PROMPT = """\n# new\n"""\n')

    code, _ = _enforce(repo, [PY_PATH], base)

    assert code == 1


def test_python_file_that_does_not_parse_is_not_exempt(repo: Path) -> None:
    write_commit(repo, PY_PATH, "VALUE = (1,\nOTHER = 2\n\n# policy\n")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _base(repo)
    write_commit(repo, PY_PATH, "VALUE = (1,\nOTHER = 2\n\n# policy notes\n")

    code, _ = _enforce(repo, [PY_PATH], base)

    assert code == 1


PEP723 = '# /// script\n# dependencies = ["{}"]\n# ///\nVALUE = 1\n'


def test_dependency_line_in_a_pep723_block_is_not_exempt(repo: Path) -> None:
    write_commit(repo, PY_PATH, PEP723.format("requests"))
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _base(repo)
    write_commit(repo, PY_PATH, PEP723.format("evil-package"))

    code, _ = _enforce(repo, [PY_PATH], base)

    assert code == 1


def test_yaml_with_an_alias_is_not_exempt(repo: Path) -> None:
    text = "# note\nbase: &b {a: 1}\nuse: *b\n"
    write_commit(repo, WORKFLOW, text)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _base(repo)
    write_commit(repo, WORKFLOW, text.replace("# note", "# reworded"))

    code, _ = _enforce(repo, [WORKFLOW], base)

    assert code == 1


def test_yaml_value_error_blocks_instead_of_raising(repo: Path) -> None:
    text = "# note\nwhen: 2001-02-30\n"
    write_commit(repo, WORKFLOW, text)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _base(repo)
    write_commit(repo, WORKFLOW, text.replace("# note", "# reworded"))

    code, _ = _enforce(repo, [WORKFLOW], base)

    assert code == 1


def test_file_over_the_size_cap_is_not_exempt(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_commit(repo, WORKFLOW, WORKFLOW_TEXT.replace("build the project", "compile it"))
    monkeypatch.setattr(mod, "MAX_STRUCTURE_BYTES", 10)

    code, _ = _enforce(repo, [WORKFLOW], _base(repo))

    assert code == 1


def test_symlink_retarget_between_hash_prefixed_targets_is_not_exempt(repo: Path) -> None:
    link = repo / ".github" / "workflows" / "linked.yml"
    link.symlink_to("# one")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "link")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _base(repo)
    link.unlink()
    link.symlink_to("# two")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "retarget")

    code, _ = _enforce(repo, [".github/workflows/linked.yml"], base)

    assert code == 1


def test_blank_line_that_shifts_a_shebang_off_line_one_is_not_exempt(repo: Path) -> None:
    write_commit(repo, PY_PATH, "#!/usr/bin/env python3\nVALUE = 1\n")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _base(repo)
    write_commit(repo, PY_PATH, "\n#!/usr/bin/env python3\nVALUE = 1\n")

    code, _ = _enforce(repo, [PY_PATH], base)

    assert code == 1


def test_git_calls_read_pathspecs_literally(repo: Path) -> None:
    write_commit(repo, "docs/a.yml", "a: 1\n")

    listed = mod._git(["diff", "--name-only", "HEAD~1", "HEAD", "--", ":(glob)docs/*.yml"], repo)

    assert listed == ""


def test_unknown_diff_base_is_a_git_failure_not_an_exemption(repo: Path) -> None:
    write_commit(repo, WORKFLOW, WORKFLOW_TEXT.replace("build the project", "compile it"))

    code, review = _enforce(repo, [WORKFLOW], "f" * 40)

    assert code == 3
    assert review["satisfied"] is False


def test_option_like_diff_base_is_rejected(repo: Path) -> None:
    code, review = _enforce(repo, [WORKFLOW], "--output=/tmp/x")

    assert code == 3
    assert "must not start with" in review["detail"]


def test_cli_diff_base_exempts_a_comment_only_push(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_commit(repo, WORKFLOW, WORKFLOW_TEXT.replace("build the project", "compile it"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "detect_infrastructure.py",
            "--files",
            WORKFLOW,
            "--require-security-review",
            "--diff-base",
            _base(repo),
            "--repo-root",
            str(repo),
        ],
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert "policy.exempt" in capsys.readouterr().err
