"""Tests for edit_issue_body.py.

PR #1965 copilot eo6 / epC: skill script lacked coverage. Tests pin:

- Mutual exclusivity of --body / --body-file (exit 1)
- Missing both arguments (exit 1)
- assert_valid_body_file enforcement (exit 2 on bad path)
- gh invocation passes --body-file through (NOT --body) when file given
- gh invocation passes --body when --body provided
- Auth error -> exit 4
- gh CLI missing -> exit 2
- gh timeout -> exit 2
- gh non-zero non-auth -> exit 3
- Success -> exit 0 with structured JSON output
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script  # noqa: E402

mod = import_skill_script(
    ".claude/skills/github/scripts/issue/edit_issue_body.py"
)
main = mod.main


def _make_proc(
    returncode: int = 0, stdout: str = "", stderr: str = "",
) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


@pytest.fixture
def mock_auth():
    with patch.object(mod, "resolve_repo_params") as mock_resolve:
        info = MagicMock()
        info.owner = "owner"
        info.repo = "repo"
        mock_resolve.return_value = info
        yield mock_resolve


class TestEditIssueBodyArgs:
    def test_missing_both_body_args_exits_1(self, mock_auth):
        with pytest.raises(SystemExit) as exc:
            main(["--issue", "42"])
        assert exc.value.code == 1

    def test_mutually_exclusive_body_args_exits_1(self, mock_auth):
        with pytest.raises(SystemExit) as exc:
            main(["--issue", "42", "--body", "x", "--body-file", "/tmp/x.md"])
        assert exc.value.code == 1

    def test_empty_body_string_exits_1(self, mock_auth):
        # PR #1965 cursor 6mMA: --body "" must be rejected before the
        # truthiness branch downstream falls through and crashes.
        with pytest.raises(SystemExit) as exc:
            main(["--issue", "42", "--body", ""])
        assert exc.value.code == 1

    def test_empty_body_file_string_exits_1(self, mock_auth):
        # Same shape as test_empty_body_string_exits_1 for --body-file.
        with pytest.raises(SystemExit) as exc:
            main(["--issue", "42", "--body-file", ""])
        assert exc.value.code == 1


class TestEditIssueBodyFileEnforcement:
    def test_invalid_body_file_path_exits_2(self, mock_auth, tmp_path):
        # assert_valid_body_file rejects non-existent / outside-repo paths.
        # Symlinks and traversal are also rejected; testing the
        # not-found path is enough to confirm the gate fires.
        bad = tmp_path / "missing.md"
        with pytest.raises(SystemExit) as exc:
            main(["--issue", "42", "--body-file", str(bad)])
        assert exc.value.code == 2


class TestEditIssueBodySuccess:
    def test_body_inline_calls_gh_with_body(self, mock_auth, capsys):
        captured_args = []

        def fake_run(args, **kwargs):
            captured_args.extend(args)
            return _make_proc(stdout="", stderr="", returncode=0)

        with patch("subprocess.run", side_effect=fake_run):
            result = main(["--issue", "42", "--body", "hello"])
        assert result == 0
        # gh is invoked with --body, NOT --body-file
        assert "--body" in captured_args
        assert captured_args[captured_args.index("--body") + 1] == "hello"
        assert "--body-file" not in captured_args
        data = json.loads(capsys.readouterr().out)
        assert data["Success"] is True
        assert data["Data"]["status"] == "updated"
        assert data["Data"]["issue"] == 42

    def test_body_file_passes_through(self, mock_auth, tmp_path, capsys):
        # Coderabbit eoz/epC: when --body-file is provided, gh should be
        # called with --body-file <path>, not --body <content>.
        body_file = tmp_path / "body.md"
        body_file.write_text("file body\n", encoding="utf-8")
        captured_args = []

        def fake_run(args, **kwargs):
            captured_args.extend(args)
            return _make_proc(returncode=0)

        with patch("subprocess.run", side_effect=fake_run), patch.object(
            mod, "assert_valid_body_file"
        ):
            result = main(
                ["--issue", "42", "--body-file", str(body_file)]
            )
        assert result == 0
        assert "--body-file" in captured_args
        # The argument after --body-file should be the resolved path
        idx = captured_args.index("--body-file")
        assert captured_args[idx + 1].endswith("body.md")
        # Bare --body should NOT appear with file content as the next arg
        assert "--body" not in captured_args


class TestEditIssueBodyErrors:
    def test_gh_missing_exits_2(self, mock_auth):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "42", "--body", "x"])
        assert exc.value.code == 2

    def test_gh_timeout_exits_2(self, mock_auth):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "42", "--body", "x"])
        assert exc.value.code == 2

    def test_auth_error_exits_4(self, mock_auth):
        proc = _make_proc(returncode=1, stderr="authentication required")
        with patch("subprocess.run", return_value=proc):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "42", "--body", "x"])
        assert exc.value.code == 4

    def test_not_logged_in_exits_4(self, mock_auth):
        proc = _make_proc(returncode=1, stderr="error: not logged in")
        with patch("subprocess.run", return_value=proc):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "42", "--body", "x"])
        assert exc.value.code == 4

    def test_other_gh_failure_exits_3(self, mock_auth):
        proc = _make_proc(returncode=1, stderr="API rate limit exceeded")
        with patch("subprocess.run", return_value=proc):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "42", "--body", "x"])
        assert exc.value.code == 3
