"""CLI tests for the bulk cancellation guard (issue #4835).

Acceptance criteria from the issue, each covered below:

- dry run against a 41-PR fixture reports the blast radius without mutation
- a required workflow that omits ``reopened`` blocks a close/reopen plan
- non-required runs cancel without a recovery event
- required runs cancel only when the manifest validates
- pagination, queued/in-progress states, duplicate workflows, and partial
  cancellation failures all have cases

Manifest replay and path-filter blocking live in
``tests/ci/test_bulk_cancel_guard_replay.py``; the corpus writers and the
default-manifest redirect they share with this module live in
``tests/ci/bulk_cancel_cli_fixtures.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import bulk_cancel_guard
from scripts.bulk_cancel_guard import (
    EXIT_BLOCKED,
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    main,
)
from scripts.github_core import pull_request_targets
from tests.ci.bulk_cancel_cli_fixtures import argv, write_runs
from tests.ci.bulk_cancel_fixtures import (
    INCIDENT_PR_COUNT,
    OPTIONAL_CONTEXT,
    REQUIRED_CONTEXT,
    SECOND_REQUIRED_CONTEXT,
    incident_runs,
)
from tests.ci.workflow_runs_fixtures import (
    FakeClient,
    page_url,
)


class TestDryRun:
    def test_41_pr_fixture_reports_the_blast_radius_and_mutates_nothing(
        self, tmp_path: Path, workflows: Path, capsys
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs())
        client = FakeClient()

        code = main(
            argv(runs_file, workflows, "--recovery-event", "reopened"), client=client
        )

        out = capsys.readouterr().out
        assert code == EXIT_OK
        assert f"pull requests       : {INCIDENT_PR_COUNT}" in out
        assert f"workflow runs       : {INCIDENT_PR_COUNT * 3}" in out
        assert "queued runs" in out and "in-progress runs" in out
        assert "Re-run with --confirm" in out
        assert client.posts == []

    def test_dry_run_writes_a_manifest_that_names_every_run(
        self, tmp_path: Path, workflows: Path
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs())
        manifest_path = tmp_path / "out" / "recovery.json"

        code = main(
            argv(
                runs_file,
                workflows,
                "--recovery-event",
                "reopened",
                "--manifest",
                str(manifest_path),
            ),
            client=FakeClient(),
        )

        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert code == EXIT_OK
        assert payload["safe"] is True
        assert payload["recovery_event"] == "reopened"
        assert len(payload["entries"]) == INCIDENT_PR_COUNT * 3

    def test_duplicate_run_ids_in_the_input_are_reported_once(
        self, tmp_path: Path, workflows: Path, capsys
    ):
        runs = incident_runs(pr_count=1)
        runs_file = write_runs(tmp_path / "runs.json", runs + runs)

        main(argv(runs_file, workflows, "--recovery-event", "reopened"), client=FakeClient())

        assert "workflow runs       : 3" in capsys.readouterr().out


class TestBlocking:
    def test_a_workflow_omitting_reopened_blocks_a_close_reopen_plan(
        self, tmp_path: Path, workflows_missing_reopened: Path, capsys
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs())
        client = FakeClient()

        code = main(
            argv(runs_file, workflows_missing_reopened, "--recovery-event", "reopened"),
            client=client,
        )

        captured = capsys.readouterr()
        assert code == EXIT_BLOCKED
        assert "refusing to cancel" in captured.err
        assert "does not subscribe to 'reopened'" in captured.out
        assert client.posts == []

    def test_confirm_does_not_override_a_blocked_plan(
        self, tmp_path: Path, workflows_missing_reopened: Path
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs())
        client = FakeClient()

        code = main(
            argv(
                runs_file,
                workflows_missing_reopened,
                "--recovery-event",
                "reopened",
                "--confirm",
            ),
            client=client,
        )

        assert code == EXIT_BLOCKED
        assert client.posts == []

    def test_omitting_the_recovery_event_blocks_required_runs(
        self, tmp_path: Path, workflows: Path
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs(pr_count=1))

        code = main(argv(runs_file, workflows), client=FakeClient())

        assert code == EXIT_BLOCKED

    def test_blocked_listing_is_truncated_with_a_remainder_count(
        self, tmp_path: Path, workflows_missing_reopened: Path, capsys
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs())

        main(
            argv(runs_file, workflows_missing_reopened, "--recovery-event", "reopened"),
            client=FakeClient(),
        )

        out = capsys.readouterr().out
        assert out.count("[BLOCKED]") == 20
        assert f"... and {INCIDENT_PR_COUNT - 20} more blocked runs" in out


class TestExecution:
    def test_non_required_runs_cancel_without_a_recovery_event(
        self, tmp_path: Path, workflows: Path
    ):
        optional_only = [
            run for run in incident_runs(pr_count=2)
            if run.contexts == (OPTIONAL_CONTEXT,)
        ]
        runs_file = write_runs(tmp_path / "runs.json", optional_only)
        client = FakeClient()

        code = main(argv(runs_file, workflows, "--confirm"), client=client)

        assert code == EXIT_OK
        assert len(client.posts) == len(optional_only)

    def test_required_runs_cancel_once_the_manifest_validates(
        self, tmp_path: Path, workflows: Path
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs(pr_count=2))
        client = FakeClient()

        code = main(
            argv(runs_file, workflows, "--recovery-event", "reopened", "--confirm"),
            client=client,
        )

        assert code == EXIT_OK
        assert len(client.posts) == 6

    def test_partial_cancellation_failure_exits_external_and_names_the_run(
        self, tmp_path: Path, workflows: Path, capsys
    ):
        runs = incident_runs(pr_count=1)
        runs_file = write_runs(tmp_path / "runs.json", runs)
        client = FakeClient()
        doomed = runs[1].run_id
        client.post_failures[f"repos/rjmurillo/ai-agents/actions/runs/{doomed}/cancel"] = (
            RuntimeError("409 Conflict")
        )

        code = main(
            argv(runs_file, workflows, "--recovery-event", "reopened", "--confirm"),
            client=client,
        )

        out = capsys.readouterr().out
        assert code == EXIT_EXTERNAL
        assert f"[FAIL] run {doomed}: 409 Conflict" in out
        assert "partial cancellation: 1 runs still active" in out


class TestInputHandling:
    def test_missing_runs_file_exits_config(self, tmp_path: Path, workflows: Path, capsys):
        code = main(argv(tmp_path / "absent.json", workflows), client=FakeClient())

        assert code == EXIT_CONFIG
        assert "cannot read" in capsys.readouterr().err

    def test_malformed_json_exits_config(self, tmp_path: Path, workflows: Path):
        broken = tmp_path / "runs.json"
        broken.write_text("{not json", encoding="utf-8")

        assert main(argv(broken, workflows), client=FakeClient()) == EXIT_CONFIG

    def test_json_object_without_a_runs_list_exits_config(
        self, tmp_path: Path, workflows: Path
    ):
        wrong = tmp_path / "runs.json"
        wrong.write_text(json.dumps({"runs": "nope"}), encoding="utf-8")

        assert main(argv(wrong, workflows), client=FakeClient()) == EXIT_CONFIG

    def test_runs_key_wrapper_object_is_accepted(self, tmp_path: Path, workflows: Path):
        runs = incident_runs(pr_count=1)
        wrapped = tmp_path / "runs.json"
        plain = write_runs(tmp_path / "plain.json", runs)
        wrapped.write_text(
            json.dumps({"runs": json.loads(plain.read_text(encoding="utf-8"))}),
            encoding="utf-8",
        )

        code = main(
            argv(wrapped, workflows, "--recovery-event", "reopened"), client=FakeClient()
        )

        assert code == EXIT_OK

    def test_a_source_argument_is_required(self, workflows: Path):
        with pytest.raises(SystemExit) as excinfo:
            main(["--workflows-dir", str(workflows)], client=FakeClient())

        assert excinfo.value.code == 2

    def test_unknown_recovery_event_is_rejected_by_argparse(
        self, tmp_path: Path, workflows: Path
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs(pr_count=1))

        with pytest.raises(SystemExit):
            main(argv(runs_file, workflows, "--recovery-event", "closed"), client=FakeClient())

    def test_unwritable_manifest_path_exits_config(
        self, tmp_path: Path, workflows: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs(pr_count=1))

        def explode(*_args, **_kwargs):
            raise OSError("read-only filesystem")

        monkeypatch.setattr(bulk_cancel_guard, "write_manifest", explode)

        code = main(
            argv(
                runs_file,
                workflows,
                "--recovery-event",
                "reopened",
                "--manifest",
                str(tmp_path / "m.json"),
            ),
            client=FakeClient(),
        )

        assert code == EXIT_CONFIG
        assert "cannot write manifest" in capsys.readouterr().err


class TestArrayPagination:
    def test_walks_past_a_full_page_and_stops_on_the_short_one(self):
        endpoint = "repos/o/r/pulls?state=open"
        first = [{"number": index} for index in range(100)]
        client = FakeClient(
            {
                page_url(endpoint, 1): first,
                page_url(endpoint, 2): [{"number": 999}],
            }
        )

        items = pull_request_targets.iter_paginated_list(client, endpoint)

        assert len(items) == 101
        assert len(client.gets) == 2

    def test_the_page_cap_bounds_the_walk(self, monkeypatch: pytest.MonkeyPatch):
        endpoint = "repos/o/r/pulls"
        full_page = [{"number": index} for index in range(100)]

        class AlwaysFull(FakeClient):
            def rest_get(self, url: str):
                self.gets.append(url)
                return full_page

        monkeypatch.setattr(pull_request_targets, "_MAX_LIST_PAGES", 3)
        client = AlwaysFull()

        items = pull_request_targets.iter_paginated_list(client, endpoint)

        assert len(client.gets) == 3
        assert len(items) == 300

    def test_a_non_list_body_ends_the_walk(self):
        client = FakeClient({page_url("repos/o/r/pulls", 1): {"message": "Not Found"}})

        assert pull_request_targets.iter_paginated_list(client, "repos/o/r/pulls") == []


def test_main_builds_a_default_client_when_none_is_injected(tmp_path: Path, workflows: Path):
    """The default transport is constructed lazily and reaches no network here.

    Constructing GhCliClient runs no subprocess, so an argument error still
    exits 2 without touching GitHub.
    """
    code = main(argv(tmp_path / "absent.json", workflows))

    assert code == EXIT_CONFIG


def test_required_context_names_used_by_the_fixtures_are_really_required():
    """Guard against the fixtures drifting from the pinned ruleset contract."""
    from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS

    assert REQUIRED_CONTEXT in REQUIRED_CONTEXTS
    assert SECOND_REQUIRED_CONTEXT in REQUIRED_CONTEXTS
    assert OPTIONAL_CONTEXT not in REQUIRED_CONTEXTS
