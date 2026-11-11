"""Tests for main() exit codes, path confinement and report rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import report_reviewer_intervention_clusters as rep
from tests.report_reviewer_intervention_helpers import (
    FakeGraphQL,
    make_page,
    make_pr,
    make_thread,
    three_repeat_pages,
)

DISP = ".project-toolkit/pr-checks/disp.json"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(rep, "workspace", str(tmp_path))
    (tmp_path / ".project-toolkit/pr-checks").mkdir(parents=True)
    (tmp_path / ".project-toolkit/metrics").mkdir(parents=True)
    monkeypatch.setattr(
        rep, "resolve_repo_params", lambda owner, repo: type("R", (), {"owner": "o", "repo": "r"})()
    )
    return tmp_path


def test_main_writes_the_report_and_exits_zero(workspace: Path, caplog) -> None:
    caplog.set_level("INFO")

    code = rep.main(
        ["--output", ".project-toolkit/metrics/out/report.json"], graphql=three_repeat_pages()
    )

    assert code == 0
    written = json.loads(
        (workspace / ".project-toolkit/metrics/out/report.json").read_text(encoding="utf-8")
    )
    assert written["cluster_count"] == 2
    assert "2 clusters in 3 interventions" in caplog.text


def test_main_reads_dispositions_from_the_named_file(workspace: Path) -> None:
    entries = {f"{n}:0": {"disposition": "not-applicable", "reason": "r"} for n in range(3)}
    (workspace / DISP).write_text(json.dumps(entries), encoding="utf-8")
    gql = FakeGraphQL({None: make_page([])})

    code = rep.main(
        ["--output", ".project-toolkit/metrics/r.json", "--dispositions-file", DISP],
        graphql=gql,
    )

    written = json.loads(
        (workspace / ".project-toolkit/metrics/r.json").read_text(encoding="utf-8")
    )
    assert code == 0
    assert [(c["signal"], c["key"], c["count"]) for c in written["clusters"]] == [
        ("disposition", "not-applicable", 3)
    ]


def test_main_treats_a_missing_dispositions_file_as_empty(workspace: Path) -> None:
    code = rep.main(
        ["--output", ".project-toolkit/metrics/r.json"], graphql=FakeGraphQL({None: make_page([])})
    )

    written = json.loads(
        (workspace / ".project-toolkit/metrics/r.json").read_text(encoding="utf-8")
    )
    assert code == 0
    assert written["examined"]["dispositions"] == 0
    assert written["cluster_count"] == 0


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_main_exits_2_on_a_bad_dispositions_file(workspace: Path, content: str) -> None:
    (workspace / DISP).write_text(content, encoding="utf-8")

    code = rep.main(
        ["--output", ".project-toolkit/metrics/r.json", "--dispositions-file", DISP],
        graphql=FakeGraphQL({None: make_page([])}),
    )

    assert code == 2
    assert not (workspace / ".project-toolkit/metrics/r.json").exists()


@pytest.mark.parametrize(
    "output",
    [
        "../escape.json",
        ".project-toolkit/metrics/report.txt",
        ".mcp.json",
        "/etc/passwd.json",
        ".project-toolkit/metrics/../../.mcp.json",
    ],
)
def test_main_exits_2_on_an_output_path_outside_the_contract(workspace: Path, output: str) -> None:
    code = rep.main(["--output", output], graphql=FakeGraphQL({None: make_page([])}))

    assert code == 2


def test_main_exits_2_on_bad_arguments(workspace: Path) -> None:
    assert rep.main(["--no-such-flag"]) == 2


def test_main_exits_3_and_writes_nothing_when_pagination_is_incomplete(workspace: Path) -> None:
    page = make_page([make_pr(1, [])], "x")
    page["repository"]["pullRequests"]["pageInfo"]["endCursor"] = None

    code = rep.main(
        ["--output", ".project-toolkit/metrics/r.json"], graphql=FakeGraphQL({None: page})
    )

    assert code == 3
    assert not (workspace / ".project-toolkit/metrics/r.json").exists()


def test_main_exits_3_on_a_malformed_intervention(workspace: Path) -> None:
    bad = make_pr(1, [make_thread("T1")])
    bad["reviewThreads"]["nodes"][0]["comments"]["nodes"][0]["createdAt"] = "yesterday"

    code = rep.main(
        ["--output", ".project-toolkit/metrics/r.json"],
        graphql=FakeGraphQL({None: make_page([bad])}),
    )

    assert code == 3
    assert not (workspace / ".project-toolkit/metrics/r.json").exists()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("GraphQL request failed: HTTP 502", 3),
        ("GraphQL request failed: HTTP 401 bad credentials", 4),
    ],
)
def test_main_maps_api_failures_to_external_or_auth(
    workspace: Path, message: str, expected: int
) -> None:
    def boom(query: str, variables: dict | None = None) -> dict:
        raise RuntimeError(message)

    assert rep.main(["--output", ".project-toolkit/metrics/r.json"], graphql=boom) == expected
    assert not (workspace / ".project-toolkit/metrics/r.json").exists()


def _report(cluster_count: int) -> dict[str, Any]:
    clusters = [
        {
            "signal": "rule",
            "key": f"ADR-{n:03d}",
            "unit": "pull_request",
            "count": 3,
            "evidence": [{"pr": p, "threads": [f"T{p}"]} for p in (1, 2, 3)],
        }
        for n in range(cluster_count)
    ]
    return {
        "as_of": "2026-11-11",
        "cluster_count": cluster_count,
        "clusters": clusters,
        "examined": {"interventions": 3, "pull_requests": 9},
        "repository": "o/r",
        "threshold": 3,
        "window_days": 90,
    }


@pytest.mark.parametrize("count", [0, 1, 40])
def test_render_report_round_trips_as_valid_json(count: int) -> None:
    report = _report(count)

    text = rep.render_report(report)

    assert json.loads(text) == report
    assert text.endswith("}\n")


def test_render_report_keeps_one_line_per_cluster() -> None:
    text = rep.render_report(_report(40))

    assert len(text.splitlines()) == 40 + 10


def test_render_report_orders_keys_so_a_daily_diff_is_stable() -> None:
    keys = [
        line.split('"')[1]
        for line in rep.render_report(_report(1)).splitlines()
        if line.startswith('  "')
    ]

    assert keys == sorted(keys)


@pytest.mark.parametrize(
    "path", ["../outside.json", "/etc/hosts.json", "evil.json", "x/../../y.json"]
)
def test_main_exits_2_on_a_dispositions_path_outside_the_registry_dir(
    workspace: Path, path: str
) -> None:
    code = rep.main(
        ["--output", ".project-toolkit/metrics/r.json", "--dispositions-file", path],
        graphql=FakeGraphQL({None: make_page([])}),
    )

    assert code == 2
    assert not (workspace / ".project-toolkit/metrics/r.json").exists()


def test_main_reports_a_message_containing_author_as_external_not_auth(workspace: Path) -> None:
    def boom(query: str, variables: dict | None = None) -> dict:
        raise RuntimeError("GraphQL request failed: could not resolve field author")

    assert rep.main([], graphql=boom) == 3
