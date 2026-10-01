"""Tests for new_issue.py: CLI contract, source flag, and label handling.

Acceptance criteria (AC-N) refer to .project-toolkit/specs/SPEC-5700-new-issue-source.md.
"""

import json
from unittest.mock import patch

import pytest

from .new_issue_harness import (
    AGENT_ARGS,
    FakeGh,
    _body_arg,
    _error,
    _make_proc,
    _run,
    main,
    mod,
    resolve_repo_fixture,  # noqa: F401  (autouse fixture)
)


class TestNewIssue:
    """Existing behavior, now under an explicit --source."""

    def test_create_basic_issue(self, capsys):
        rc, _ = _run(["--title", "Test Title", "--source", "human"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["Success"] is True
        assert data["Data"]["issue_number"] == 42
        assert data["Data"]["title"] == "Test Title"

    def test_data_number_is_positive_int_and_url_set_on_success(self, capsys):
        # Regression for issue #2767: callers read Data.number, which was null.
        gh = FakeGh(issue_create=_make_proc(stdout="https://github.com/owner/repo/issues/2767\n"))
        rc, _ = _run(["--title", "Test Title", "--source", "human"], gh)
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        number = data["Data"]["number"]
        assert isinstance(number, int) and number > 0
        assert number == 2767
        assert data["Data"]["url"] == "https://github.com/owner/repo/issues/2767"

    def test_create_with_body_and_labels(self):
        rc, gh = _run(
            ["--title", "Title", "--body", "Body text", "--labels", "bug,P1", "--source", "human"]
        )
        assert rc == 0
        assert "--body" in gh.find("issue", "create")
        assert gh.find("issue", "edit").count("--add-label") == 2

    def test_api_error_exits_3(self, capsys):
        gh = FakeGh(issue_create=_make_proc(returncode=1, stderr="API error"))
        rc, _ = _run(["--title", "Title", "--source", "human"], gh)
        assert rc == 3
        data = json.loads(capsys.readouterr().out)
        assert data["Success"] is False
        assert data["Error"]["Type"] == "ApiError"

    def test_unparseable_result_exits_3(self, capsys):
        gh = FakeGh(issue_create=_make_proc(stdout="no url here"))
        rc, _ = _run(["--title", "Title", "--source", "human"], gh)
        assert rc == 3
        data = json.loads(capsys.readouterr().out)
        assert data["Error"]["Type"] == "ApiError"

    def test_empty_body_carries_only_the_human_marker(self):
        _, gh = _run(["--title", "Title", "--body", "", "--source", "human"])
        create = gh.find("issue", "create")
        assert create[create.index("--body") + 1] == "<!-- source:human -->"

    def test_empty_labels_apply_only_the_source_label(self):
        _, gh = _run(["--title", "Title", "--labels", "", "--source", "human"])
        create = gh.find("issue", "create")
        assert create.count("--label") == 1
        assert ("issue", "edit") not in gh.verbs()


class TestSourceFlag:
    """AC-1, AC-8, AC-9: provenance is required, labeled atomically, validated first."""

    def test_missing_source_exits_2_before_any_call(self, resolve_repo):
        """AC-1: argparse refuses a missing --source."""
        gh = FakeGh()
        with patch("subprocess.run", side_effect=gh), pytest.raises(SystemExit) as exc:
            main(["--title", "x"])
        assert exc.value.code == 2
        assert gh.calls == []
        resolve_repo.assert_not_called()

    def test_invalid_source_value_exits_2(self):
        """AC-1: only human or agent is accepted."""
        with pytest.raises(SystemExit) as exc:
            main(["--title", "x", "--source", "bot"])
        assert exc.value.code == 2

    def test_human_source_labels_in_create_call_without_step0(self):
        """AC-8: the source label rides in the create call; no Step 0 for human."""
        rc, gh = _run(["--title", "T", "--body", "b", "--source", "human"])
        assert rc == 0
        create = gh.find("issue", "create")
        assert create[create.index("--label") + 1] == "source:human"
        assert "## Step 0" not in _body_arg(create)

    def test_source_label_is_ensured_before_create(self):
        """AC-8: the label is created in the target repo before the issue."""
        _, gh = _run(["--title", "T", "--source", "human"])
        assert gh.verbs()[:2] == [("label", "create"), ("issue", "create")]
        label_call = gh.find("label", "create")
        assert label_call[3] == "source:human"
        assert label_call[label_call.index("--repo") + 1] == "owner/repo"

    def test_existing_label_does_not_block_create(self):
        """AC-8: 'already exists' from gh label create is the normal case."""
        exists = 'label with name "source:agent" already exists'
        gh = FakeGh(label_create=_make_proc(1, stderr=exists))
        rc, _ = _run(["--title", "T", *AGENT_ARGS], gh)
        assert rc == 0

    def test_label_ensure_failure_defers_to_create_call(self, capsys):
        """AC-8: a failed ensure leaves the create call as the fail-closed point."""
        gh = FakeGh(
            label_create=_make_proc(1, stderr="HTTP 403: Resource not accessible"),
            issue_create=_make_proc(1, stderr="could not add label: 'source:agent' not found"),
        )
        rc, _ = _run(["--title", "T", *AGENT_ARGS], gh)
        assert rc == 3
        assert ("issue", "edit") not in gh.verbs()
        assert "source:agent" in _error(capsys)

    def test_label_ensure_timeout_defers_to_create_call(self):
        """AC-8: a hung ensure does not abort; the create call still decides."""
        gh = FakeGh()

        def _route(args, **kwargs):
            if args[1:3] == ["label", "create"]:
                raise mod.subprocess.TimeoutExpired(args, 30)
            return gh(args, **kwargs)

        with patch("subprocess.run", side_effect=_route):
            rc = main(["--title", "T", "--source", "human", "--output-format", "json"])
        assert rc == 0
        assert gh.verbs() == [("issue", "create")]

    def test_success_output_reports_source(self, capsys):
        rc, _ = _run(["--title", "T", *AGENT_ARGS])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["Data"]["source"] == "agent"

    def test_invalid_input_never_resolves_repo(self, resolve_repo):
        """AC-9: validation runs before repository resolution."""
        rc, gh = _run(["--title", "T", "--source", "agent"])
        assert rc == 2
        assert gh.calls == []
        resolve_repo.assert_not_called()

    def test_empty_title_never_resolves_repo(self, resolve_repo):
        """AC-9: the title check moved ahead of repository resolution."""
        rc, gh = _run(["--title", "  ", "--source", "human"])
        assert rc == 2
        assert gh.calls == []
        resolve_repo.assert_not_called()


class TestSourceLabelConflicts:
    """AC-6: at most one source label, matching --source."""

    def test_conflicting_source_label_exits_2(self, capsys):
        rc, gh = _run(["--title", "T", "--labels", "bug,source:human", *AGENT_ARGS])
        assert rc == 2
        assert gh.calls == []
        assert _error(capsys) == (
            "--labels carries source:human, which conflicts with --source agent"
        )

    def test_matching_source_label_is_passed_once(self):
        """AC-6: dedupe, case-insensitive; the create call carries it, edit does not."""
        rc, gh = _run(["--title", "T", "--labels", "bug, SOURCE:AGENT", *AGENT_ARGS])
        assert rc == 0
        create = gh.find("issue", "create")
        assert create.count("--label") == 1
        edit = gh.find("issue", "edit")
        assert edit[edit.index("--add-label") + 1 :] == ["bug"]

    def test_only_source_label_in_labels_skips_edit_call(self):
        rc, gh = _run(["--title", "T", "--labels", "source:agent", *AGENT_ARGS])
        assert rc == 0
        assert ("issue", "edit") not in gh.verbs()
