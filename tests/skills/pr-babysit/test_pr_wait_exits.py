"""Tests for pr_wait.py exit codes, any-change, help, and target edge cases."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from tests.skills.claude_skills_import import import_cached_module

# Load the shared helpers by path, so the test directory never joins sys.path.
_helpers: Any = import_cached_module(
    "tests/skills/pr-babysit/_pr_wait_helpers.py", "_pr_wait_helpers"
)
_gate = _helpers.gate_payload
_node = _helpers.node
_pr = _helpers.pr_payload
pw = _helpers.pw
pws = _helpers.pws


def test_main_exits_four_on_snapshot_auth_failure(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import github_core.api as api

    def no_auth(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("gh auth login required: HTTP 401 Bad credentials")

    monkeypatch.setattr(api, "gh_graphql", no_auth)

    assert pw.main(["5", "--repo", "o/r"]) == 4


def test_main_exits_three_on_null_pull_request(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import github_core.api as api

    monkeypatch.setattr(api, "gh_graphql", lambda *_a, **_k: {"repository": {"pullRequest": None}})

    assert pw.main(["5", "--repo", "o/r"]) == 3
    assert capsys.readouterr().out.startswith("not found:")


def test_transient_failures_reset_after_a_good_poll(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = iter([RuntimeError("HTTP 502"), RuntimeError("HTTP 502"), None])

    def snapshot(*_a: Any) -> Any:
        item = next(results, None)
        if isinstance(item, Exception):
            raise item
        return _pr(mergeStateStatus="CLEAN"), "me"

    monkeypatch.setattr(pw, "fetch_snapshot", snapshot)
    monkeypatch.setattr(pw, "fetch_gate", lambda *_a: _gate())

    assert pw.main(["5", "--repo", "o/r"]) == 0


def test_main_exits_two_on_gate_contract_break(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _gate()
    del gate["UnresolvedThreads"]
    monkeypatch.setattr(pw, "fetch_snapshot", lambda *_a: (_pr(), "me"))
    monkeypatch.setattr(pw, "fetch_gate", lambda *_a: gate)

    assert pw.main(["5", "--repo", "o/r"]) == 2


def test_push_then_green_does_not_rearm_changes_requested(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reviews = {"totalCount": 1, "nodes": [_node("r1", "rev", state="CHANGES_REQUESTED")]}
    pw.save_state(
        isolated_state / "o+r+5.json",
        pw.State(
            head="c" * 40,
            base_oid="b" * 40,
            blockers={"changes-requested:r1"},
            head_seen_at=1.0,
            totals={"reviews": 1},
            seen={"r1"},
        ),
    )
    snapshots = iter(
        [
            _pr(reviewDecision="CHANGES_REQUESTED", reviews=reviews),
            _pr(reviewDecision="CHANGES_REQUESTED", reviews=reviews),
            _pr(reviewDecision="APPROVED", reviews=reviews, mergeStateStatus="CLEAN"),
        ]
    )
    gates = iter([_gate(PendingRequired=["ci"]), _gate(), _gate()])
    approved = _pr(reviewDecision="APPROVED", reviews=reviews, mergeStateStatus="CLEAN")
    monkeypatch.setattr(pw, "fetch_snapshot", lambda *_a: (next(snapshots, approved), "me"))
    monkeypatch.setattr(pw, "fetch_gate", lambda *_a: next(gates, _gate()))

    assert pw.main(["5", "--repo", "o/r"]) == 0
    assert "blocked:" not in capsys.readouterr().out


def test_any_change_exits_when_last_thread_resolves_silently(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pw.save_state(
        isolated_state / "o+r+5.json",
        pw.State(head="a" * 40, base_oid="b" * 40, blockers={"thread:t1"}, head_seen_at=1.0),
    )
    monkeypatch.setattr(pw, "fetch_snapshot", lambda *_a: (_pr(mergeStateStatus="CLEAN"), "me"))
    monkeypatch.setattr(pw, "fetch_gate", lambda *_a: _gate())

    assert pw.main(["5", "--repo", "o/r", "--until", "any-change"]) == 0
    assert capsys.readouterr().out.startswith("green:")


def test_any_change_reports_an_absent_check(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pw.save_state(
        isolated_state / "o+r+5.json",
        pw.State(head="a" * 40, base_oid="b" * 40, green_head="a" * 40, head_seen_at=1.0),
    )
    gate = _gate(MissingRequired=["e2e"], AbsentRequired=["e2e"])
    monkeypatch.setattr(pw, "fetch_snapshot", lambda *_a: (_pr(), "me"))
    monkeypatch.setattr(pw, "fetch_gate", lambda *_a: gate)

    assert pw.main(["5", "--repo", "o/r", "--until", "any-change"]) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "blocked: absent:e2e:aaaaaaa"


def test_help_lists_the_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        pw.main(["--help"])

    out = capsys.readouterr().out
    assert "Exit codes" in out
    assert "unreachable" in out


def test_parse_target_accepts_dot_prefixed_repo_names() -> None:
    assert pw.parse_target("5", "octo/.github") == ("octo", ".github", 5)
    assert pw.parse_target("https://github.com/octo/.github/pull/9", None) == (
        "octo",
        ".github",
        9,
    )


@pytest.mark.parametrize("repo", ["o/.", "o/..", ".o/r", "o_x/r"])
def test_parse_target_rejects_dot_only_repos_and_bad_owners(repo: str) -> None:
    with pytest.raises(ValueError):
        pw.parse_target("5", repo)


def test_tests_do_not_add_their_directory_to_sys_path() -> None:
    here = str(Path(__file__).resolve().parent)

    assert here not in sys.path


def test_main_exits_two_at_once_when_gh_is_missing(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import github_core.api as api

    calls = {"n": 0}

    def no_gh(*_a: Any, **_k: Any) -> Any:
        calls["n"] += 1
        raise FileNotFoundError(2, "No such file or directory", "gh")

    monkeypatch.setattr(api, "gh_graphql", no_gh)

    assert pw.main(["5", "--repo", "o/r"]) == 2
    assert calls["n"] == 1
