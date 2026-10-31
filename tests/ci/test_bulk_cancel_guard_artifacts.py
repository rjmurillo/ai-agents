"""CLI behavior of ``--report-artifacts`` (issue #5365).

The artifact count costs one REST call per run with no batch form. The
acceptance criteria require that a fake client prove the call count, and that
the default path stay unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.bulk_cancel_guard import EXIT_AUTH, EXIT_EXTERNAL, EXIT_OK, main
from tests.ci.bulk_cancel_cli_fixtures import argv, write_runs
from tests.ci.bulk_cancel_fixtures import make_run
from tests.ci.workflow_runs_fixtures import FakeClient, page_url

REPOSITORY = "rjmurillo/ai-agents"


def artifacts_endpoint(run_id: int) -> str:
    return f"repos/{REPOSITORY}/actions/runs/{run_id}/artifacts"


def artifact_page(count: int) -> dict:
    return {"artifacts": [{"id": n, "expired": False} for n in range(count)]}


def artifact_gets(client: FakeClient) -> list[str]:
    return [url for url in client.gets if "/artifacts" in url]


class TestDefaultPathUnchanged:
    def test_no_artifact_call_and_no_artifact_line_without_the_flag(
        self, tmp_path: Path, workflows: Path, capsys
    ):
        runs_file = write_runs(tmp_path / "runs.json", [make_run(1), make_run(2)])
        client = FakeClient()

        code = main(argv(runs_file, workflows, "--recovery-event", "reopened"), client=client)

        assert code == EXIT_OK
        assert artifact_gets(client) == []
        assert "artifacts" not in capsys.readouterr().out

    def test_the_default_manifest_carries_no_artifact_total(self, tmp_path: Path, workflows: Path):
        runs_file = write_runs(tmp_path / "runs.json", [make_run(1)])
        manifest_path = tmp_path / "recovery.json"

        main(
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
        assert "artifacts" not in payload["blast_radius"]


class TestReportArtifacts:
    def _client(self) -> FakeClient:
        return FakeClient(
            {
                page_url(artifacts_endpoint(1), 1): artifact_page(2),
                page_url(artifacts_endpoint(2), 1): artifact_page(3),
                page_url(artifacts_endpoint(3), 1): artifact_page(0),
            }
        )

    def test_one_artifact_call_per_run_and_the_total_is_printed(
        self, tmp_path: Path, workflows: Path, capsys
    ):
        runs = [make_run(1), make_run(2), make_run(3)]
        runs_file = write_runs(tmp_path / "runs.json", runs)
        client = self._client()

        code = main(
            argv(runs_file, workflows, "--recovery-event", "reopened", "--report-artifacts"),
            client=client,
        )

        out = capsys.readouterr().out
        assert code == EXIT_OK
        assert len(artifact_gets(client)) == len(runs)
        assert "artifacts           : 5" in out
        assert client.posts == []

    def test_a_truncated_count_is_labelled_in_the_report(
        self, tmp_path: Path, workflows: Path, capsys, monkeypatch
    ):
        monkeypatch.setattr("scripts.github_core.workflow_runs._MAX_PAGES", 1)
        runs_file = write_runs(tmp_path / "runs.json", [make_run(1)])
        client = FakeClient({page_url(artifacts_endpoint(1), 1): artifact_page(100)})

        main(
            argv(runs_file, workflows, "--recovery-event", "reopened", "--report-artifacts"),
            client=client,
        )

        assert "100 or more (TRUNCATED" in capsys.readouterr().out

    def test_the_artifact_line_sits_inside_the_blast_radius_block(
        self, tmp_path: Path, workflows: Path, capsys
    ):
        runs_file = write_runs(tmp_path / "runs.json", [make_run(1)])
        client = self._client()

        main(
            argv(runs_file, workflows, "--recovery-event", "reopened", "--report-artifacts"),
            client=client,
        )

        lines = capsys.readouterr().out.splitlines()
        required = next(i for i, line in enumerate(lines) if "required contexts" in line)
        assert "artifacts" in lines[required + 1]

    def test_the_manifest_records_the_total(self, tmp_path: Path, workflows: Path):
        runs_file = write_runs(tmp_path / "runs.json", [make_run(1), make_run(2)])
        manifest_path = tmp_path / "recovery.json"

        main(
            argv(
                runs_file,
                workflows,
                "--recovery-event",
                "reopened",
                "--report-artifacts",
                "--manifest",
                str(manifest_path),
            ),
            client=self._client(),
        )

        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["blast_radius"]["artifacts"] == 5

    def test_a_failed_artifact_read_exits_external(self, tmp_path: Path, workflows: Path, capsys):
        class Failing(FakeClient):
            def rest_get(self, endpoint: str):
                raise RuntimeError("HTTP 502")

        runs_file = write_runs(tmp_path / "runs.json", [make_run(1)])

        code = main(
            argv(runs_file, workflows, "--recovery-event", "reopened", "--report-artifacts"),
            client=Failing(),
        )

        assert code == EXIT_EXTERNAL
        assert "GitHub API read failed" in capsys.readouterr().err

    def test_the_flag_needs_credentials_even_for_a_runs_file(self, tmp_path: Path, workflows: Path):
        class Anonymous(FakeClient):
            def is_authenticated(self) -> bool:
                return False

        runs_file = write_runs(tmp_path / "runs.json", [make_run(1)])
        client = Anonymous()

        code = main(
            argv(runs_file, workflows, "--recovery-event", "reopened", "--report-artifacts"),
            client=client,
        )

        assert code == EXIT_AUTH
        assert client.gets == []
