"""--dry-run tests for ``new_pr.py``: every check runs, nothing is created or logged."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.new_pr_test_support import _completed, _mod, main


@pytest.fixture(autouse=True)
def _head_is_on_origin(monkeypatch):
    monkeypatch.setattr(main.__globals__["_pr_val"], "head_on_origin", lambda head: True)


def _preamble(tmp_path):
    """Calls main() makes before creation: repo root, gh --version, base probe."""
    return [
        _completed(stdout=str(tmp_path), rc=0),
        _completed(rc=0),
        _completed(rc=0),
    ]


class TestDryRun:
    def test_reports_plan_and_never_calls_gh_pr_create(self, tmp_path, capsys):
        calls = _preamble(tmp_path)
        with (
            patch("subprocess.run", side_effect=calls) as run,
            patch.object(_mod, "run_validations") as validations,
        ):
            rc = main(["--title", "feat: test", "--head", "feat/x", "--base", "main", "--dry-run"])

        assert rc == 0
        validations.assert_called_once()
        assert "Dry run: would create PR feat/x -> main" in capsys.readouterr().out
        for call in run.call_args_list:
            assert call.args[0][:3] != ["gh", "pr", "create"]

    def test_reports_draft(self, tmp_path, capsys):
        with (
            patch("subprocess.run", side_effect=_preamble(tmp_path)),
            patch.object(_mod, "run_validations"),
        ):
            rc = main(
                [
                    "--title",
                    "feat: test",
                    "--head",
                    "feat/x",
                    "--base",
                    "main",
                    "--draft",
                    "--dry-run",
                ]
            )

        assert rc == 0
        assert "(draft)" in capsys.readouterr().out

    def test_invalid_title_still_returns_2(self, tmp_path):
        with (
            patch("subprocess.run", side_effect=_preamble(tmp_path)),
            patch.object(_mod, "run_validations") as validations,
        ):
            rc = main(["--title", "Bad title", "--head", "feat/x", "--base", "main", "--dry-run"])

        assert rc == 2
        validations.assert_not_called()

    def test_validation_failure_still_fails(self, tmp_path):
        with (
            patch("subprocess.run", side_effect=_preamble(tmp_path)),
            patch.object(_mod, "run_validations", side_effect=SystemExit(1)),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--title", "feat: test", "--head", "feat/x", "--base", "main", "--dry-run"])

        assert exc.value.code == 1

    def test_skip_validation_writes_no_audit_log(self, tmp_path, capsys):
        with (
            patch("subprocess.run", side_effect=_preamble(tmp_path)),
            patch.object(_mod, "write_audit_log") as audit,
        ):
            rc = main(
                [
                    "--title",
                    "feat: test",
                    "--head",
                    "feat/x",
                    "--base",
                    "main",
                    "--skip-validation",
                    "--audit-reason",
                    "hotfix",
                    "--dry-run",
                ]
            )

        assert rc == 0
        audit.assert_not_called()
        assert "no audit log" in capsys.readouterr().err

    def test_skip_validation_without_reason_still_returns_2(self, tmp_path):
        with patch("subprocess.run", side_effect=_preamble(tmp_path)):
            rc = main(
                [
                    "--title",
                    "feat: t",
                    "--head",
                    "feat/x",
                    "--base",
                    "main",
                    "--skip-validation",
                    "--dry-run",
                ]
            )

        assert rc == 2
