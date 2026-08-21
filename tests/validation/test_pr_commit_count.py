#!/usr/bin/env python3
"""Tests for scripts/validation/pr_commit_count.py (issue #3262, #5230).

Covers positive (threshold classification), negative (genuine errors), and
transient-error (503 / no-server / timeout / unparseable body) paths, plus
GITHUB_OUTPUT emission and CLI exit codes, per TESTING-RIGOR.

The commit count is advisory only (ADR-099): there is no BLOCKED status and
no bypass label. These tests pin that classify_count never returns anything
outside {OK, WARNING, ALERT} and that main() always exits 0 on a healthy
fetch, however large the count.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.validation import pr_commit_count as mod

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["gh"], returncode=returncode, stdout=stdout, stderr=stderr)


def _commits_json(n: int) -> str:
    return json.dumps([{"sha": f"{i:040x}"} for i in range(n)])


# ---------------------------------------------------------------------------
# classify_count: threshold boundaries (issue #362), no block (ADR-099)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, "OK"),
        (9, "OK"),
        (10, "WARNING"),
        (14, "WARNING"),
        (15, "ALERT"),
        (19, "ALERT"),
        (20, "ALERT"),
        (21, "ALERT"),
        (99, "ALERT"),
        (1000, "ALERT"),
    ],
)
def test_classify_count_thresholds(count: int, expected: str) -> None:
    assert mod.classify_count(count) == expected


def test_classify_count_has_no_block_status_at_any_size() -> None:
    """Negative control for ADR-099: no count, however large, yields BLOCKED.

    This is the discriminating case for the removed gate: restoring a
    BLOCK_THRESHOLD-style branch would make this fail at some large count.
    """
    for count in (0, 1, 20, 21, 40, 41, 10_000):
        assert mod.classify_count(count) != "BLOCKED"


def test_agents_md_mid_gate_names_warning_threshold() -> None:
    """AGENTS.md must state the WARNING_THRESHOLD (10) on the mid-session check line.

    Issue #3944: AGENTS.md previously said 'warn >15' which is the ALERT band,
    not the WARNING band. An agent following that would miss CI notices from
    commit 10 through 14. This test pins the correct value so the doc cannot
    silently revert to the stale number.
    """
    agents_md = (_PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    gate_line = next(
        (ln for ln in agents_md.splitlines() if "rev-list" in ln),
        "",
    )
    assert gate_line, "AGENTS.md must contain a mid-session commit gate line with rev-list"
    assert str(mod.WARNING_THRESHOLD) in gate_line, (
        f"AGENTS.md mid-gate line must name WARNING_THRESHOLD ({mod.WARNING_THRESHOLD}); "
        f"found: {gate_line!r}"
    )


def test_agents_md_mid_gate_does_not_claim_a_block() -> None:
    """ADR-099: the mid-session line must not claim commits are ever blocked.

    It may explain that there is *no* block (advisory-only wording); it must
    not carry the old `block >N` enforcement syntax.
    """
    agents_md = (_PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    gate_line = next(
        (ln for ln in agents_md.splitlines() if "rev-list" in ln),
        "",
    )
    assert gate_line
    assert "block >" not in gate_line.lower()


def test_agents_md_context_budget_is_not_8kb() -> None:
    """AGENTS.md must not claim the context budget is less than 8KB.

    Issue #3907: AGENTS.md previously stated '<8KB' which is 12x below the
    enforced gate ceiling (~99KB). This test pins that the stale value is gone.
    """
    agents_md = (_PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    context_line = next(
        (ln for ln in agents_md.splitlines() if "Knowledge -> context" in ln),
        "",
    )
    assert context_line, "AGENTS.md must contain the Knowledge -> context line"
    assert "<8KB" not in context_line, (
        "AGENTS.md must not claim context budget is <8KB; "
        f"found: {context_line!r}"
    )


# ---------------------------------------------------------------------------
# is_transient_error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stderr",
    [
        "gh: No server is currently available to service your request (HTTP 503)",
        "HTTP 502 Bad Gateway",
        "HTTP 504",
        "Service Unavailable",
        "connection reset by peer",
        "connection refused",
        "timeout was reached",
        "net/http: TLS handshake timeout",
        "unexpected EOF",
        # A quota refusal clears on its own. Treating it as fatal red-blocked a
        # clean PR during a quota window; the old substring list excluded 403 by
        # design, so nothing here could see it (issue #4326 defect 1).
        "gh: API rate limit exceeded for user ID 6811113 (HTTP 403)",
        "failed to get commits: HTTP 403: API rate limit exceeded for user ID 6811113",
        "You have exceeded a secondary rate limit and have been temporarily blocked "
        "from content creation. Please retry your request again later.",
        # gh's own connectivity wording, captured from gh 2.97.0.
        "error connecting to api.github.com\ncheck your internet connection",
        "dial tcp: lookup api.github.com: no such host",
    ],
)
def test_is_transient_error_true(stderr: str) -> None:
    assert mod.is_transient_error(stderr) is True


@pytest.mark.parametrize(
    "stderr",
    [
        "",
        "HTTP 404: Not Found",
        "HTTP 401: Bad credentials",
        "HTTP 403: Resource not accessible by integration",
        "gh: Not Found (HTTP 404)",
    ],
)
def test_is_transient_error_false(stderr: str) -> None:
    assert mod.is_transient_error(stderr) is False


# ---------------------------------------------------------------------------
# fetch_commit_count: positive
# ---------------------------------------------------------------------------


def test_fetch_healthy_below_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, _commits_json(3)))
    result = mod.fetch_commit_count(42, "o", "r")
    assert result == mod.CountResult("OK", 3, transient=False, total_count=3)


def test_fetch_healthy_large_count_is_alert_not_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-099: a very large PR classifies as ALERT, never BLOCKED."""
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, _commits_json(60)))
    result = mod.fetch_commit_count(42, "o", "r")
    assert result.status == "ALERT"
    assert result.count == 60
    assert result.transient is False


def test_fetch_at_the_old_ceiling_is_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    """A count that used to sit exactly at the removed 20-commit ceiling."""
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, _commits_json(20)))
    result = mod.fetch_commit_count(42, "o", "r")
    assert result.status == "ALERT"
    assert result.count == 20


def test_fetch_empty_list_is_ok_not_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # A healthy 200 with an empty list means zero commits, which is not over
    # the limit. The old inline step hard-failed here; the new contract is OK.
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, "[]"))
    result = mod.fetch_commit_count(42, "o", "r")
    assert result == mod.CountResult("OK", 0, transient=False, total_count=0)


# ---------------------------------------------------------------------------
# fetch_commit_count: transient degradation
# ---------------------------------------------------------------------------


def test_fetch_transient_503_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mod,
        "_run_gh",
        lambda argv: _completed(1, "", "No server is currently available (HTTP 503)"),
    )
    result = mod.fetch_commit_count(42, "o", "r")
    assert result == mod.CountResult(mod.STATUS_UNKNOWN, None, transient=True)


def test_fetch_unparseable_body_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, "<html>502</html>"))
    result = mod.fetch_commit_count(42, "o", "r")
    assert result.status == mod.STATUS_UNKNOWN
    assert result.transient is True


def test_fetch_timeout_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=argv, timeout=30)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    result = mod.fetch_commit_count(42, "o", "r")
    assert result.transient is True
    assert result.status == mod.STATUS_UNKNOWN


# ---------------------------------------------------------------------------
# fetch_commit_count: genuine (non-transient) failures raise
# ---------------------------------------------------------------------------


def test_fetch_auth_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(1, "", "HTTP 401: Bad credentials"))
    with pytest.raises(RuntimeError, match="Failed to fetch commits"):
        mod.fetch_commit_count(42, "o", "r")


def test_fetch_missing_gh_binary_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_missing(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("gh")

    monkeypatch.setattr(subprocess, "run", _raise_missing)
    with pytest.raises(FileNotFoundError, match="not installed or not found on PATH"):
        mod.fetch_commit_count(42, "o", "r")


def test_fetch_non_list_payload_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, '{"message":"x"}'))
    with pytest.raises(RuntimeError, match="expected a list"):
        mod.fetch_commit_count(42, "o", "r")


# ---------------------------------------------------------------------------
# _write_github_output
# ---------------------------------------------------------------------------


def test_write_github_output_writes_kv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    mod._write_github_output("ALERT", 22)
    content = out.read_text(encoding="utf-8")
    assert "status=ALERT\n" in content
    assert "commit_count=22\n" in content


def test_write_github_output_unknown_count_is_blank(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    mod._write_github_output(mod.STATUS_UNKNOWN, None)
    content = out.read_text(encoding="utf-8")
    assert "status=UNKNOWN\n" in content
    assert "commit_count=\n" in content


def test_write_github_output_noop_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    # Must not raise when GITHUB_OUTPUT is unset (local runs).
    mod._write_github_output("OK", 1)


def test_write_github_output_emits_no_commit_limit_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-099: there is no ceiling left to report, so no commit_limit key."""
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    mod._write_github_output("ALERT", 60)
    content = out.read_text(encoding="utf-8")
    assert "commit_limit" not in content


# ---------------------------------------------------------------------------
# main: exit codes + output emission
# ---------------------------------------------------------------------------


def _stub_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.github_core.api import RepoInfo

    monkeypatch.setattr(mod, "resolve_repo_params", lambda o, r: RepoInfo(owner="o", repo="r"))


def test_main_healthy_returns_0_and_emits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_repo(monkeypatch)
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, _commits_json(12)))
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    rc = mod.main(["--pr-number", "42"])
    assert rc == 0
    content = out.read_text(encoding="utf-8")
    assert "status=WARNING\n" in content
    assert "commit_count=12\n" in content


def test_main_transient_returns_0_with_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_repo(monkeypatch)
    monkeypatch.setattr(
        mod, "_run_gh", lambda argv: _completed(1, "", "HTTP 503 service unavailable")
    )
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    rc = mod.main(["--pr-number", "42"])
    assert rc == 0
    assert "status=UNKNOWN\n" in out.read_text(encoding="utf-8")
    assert "::warning::" in capsys.readouterr().out


def test_main_genuine_failure_returns_3(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_repo(monkeypatch)
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(1, "", "HTTP 401: Bad credentials"))
    assert mod.main(["--pr-number", "42"]) == 3


def test_main_missing_gh_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_repo(monkeypatch)
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(127, "", ""))
    assert mod.main(["--pr-number", "42"]) == 2
    assert "not installed or not found on PATH" in capsys.readouterr().err


def test_main_unresolvable_repo_emits_flag_hint_and_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _exit_2(owner: str, repo: str) -> object:
        raise SystemExit(2)

    monkeypatch.setattr(mod, "resolve_repo_params", _exit_2)
    assert mod.main(["--pr-number", "42"]) == 2
    assert "--owner and --repo" in capsys.readouterr().err


def test_main_invalid_pr_number_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    assert mod.main(["--pr-number", "0"]) == 2


def test_main_very_large_pr_returns_0_with_alert_not_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR-099: a 25-commit PR must never produce ::error:: or a nonzero exit.

    This is the discriminating case for the removed gate: the old behavior
    (a BLOCKED status requiring a bypass label) would have printed ::error::
    here once enforce_pr_validation.py's label check failed to find the label.
    """
    _stub_repo(monkeypatch)
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, _commits_json(25)))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "gh_out"))
    rc = mod.main(["--pr-number", "42"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "::warning::" in out
    assert "::error::" not in out
    written = (tmp_path / "gh_out").read_text(encoding="utf-8")
    assert "status=ALERT" in written


# ---------------------------------------------------------------------------
# Issue #3920: authored commit count excludes branch-maintenance merge commits
# ---------------------------------------------------------------------------


def _commits_with_parents(specs: list[int]) -> list[dict]:
    """Build a commits list. Each spec is the number of parents for that commit."""
    return [
        {
            "sha": f"{i:040x}",
            "parents": [{"sha": f"p{i}{j:040x}"} for j in range(n_parents)],
        }
        for i, n_parents in enumerate(specs)
    ]


@pytest.mark.parametrize(
    ("label", "specs", "expected"),
    [
        ("all regular (1 parent each)", [1, 1, 1], 3),
        ("all initial/orphan (0 parents)", [0, 0], 2),
        ("all merge commits (2 parents each)", [2, 2, 2], 0),
        ("mixed: 4 authored + 25 merges", [1] * 4 + [2] * 25, 4),
        ("commit missing parents key is counted (fail-closed)", [None], 1),
        ("commit is not a dict (fail-closed)", None, 1),  # handled below
        ("empty list", [], 0),
    ],
)
def test_authored_commit_count(label: str, specs: list[int] | None, expected: int) -> None:
    """_authored_commit_count counts authored commits, fail-closed on malformed input."""
    if specs is None:
        # Non-dict entry: the function should count it as authored
        commits: list = ["bare-string"]
    elif any(s is None for s in specs):
        # None spec means missing the parents key entirely
        commits = [{"sha": f"{i:040x}"} for i, _ in enumerate(specs)]
    else:
        commits = _commits_with_parents(specs)
    assert mod._authored_commit_count(commits) == expected, label


def test_authored_count_excludes_merges_from_classification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PR #3780 scenario: 25 merge + 4 authored = 4 classified, not 29.

    The authored count (4) must be used for classification; the total count
    (29) must appear in the GITHUB_OUTPUT for audit but must not push status
    past OK (issue #3920).
    """
    from scripts.github_core.api import RepoInfo

    payload = json.dumps(_commits_with_parents([2] * 25 + [1] * 4))
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, payload))
    monkeypatch.setattr(mod, "resolve_repo_params", lambda *a: RepoInfo(owner="o", repo="r"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "gh_out"))
    rc = mod.main(["--pr-number", "42", "--owner", "o", "--repo", "r"])
    assert rc == 0
    written = (tmp_path / "gh_out").read_text(encoding="utf-8")
    # 4 authored commits < WARNING_THRESHOLD=10, so status is deterministically OK.
    assert "status=OK" in written
    assert "commit_count=4" in written


def test_total_count_field_in_count_result() -> None:
    """CountResult.total_count stores raw total for audit while count stores authored."""
    r = mod.CountResult(status="OK", count=4, transient=False, total_count=29)
    assert r.total_count == 29
    assert r.count == 4


def test_total_count_shown_in_output_when_different(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When total != authored, both counts must appear in the summary line."""
    from scripts.github_core.api import RepoInfo

    payload = json.dumps(_commits_with_parents([2] * 25 + [1] * 4))
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, payload))
    monkeypatch.setattr(mod, "resolve_repo_params", lambda *a: RepoInfo(owner="o", repo="r"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "gh_out"))
    mod.main(["--pr-number", "1", "--owner", "o", "--repo", "r"])
    out = capsys.readouterr().out
    # The line must include the authored count (4) and total (29)
    assert "29" in out
    assert "4" in out


# ---------------------------------------------------------------------------
# ADR-099: the block/relief machinery is gone, not merely unused (issue #4047
# established the same discipline for contains_base_merge; this pins its
# successor generation of removed names so a future caller cannot reach for
# them and silently reintroduce the block).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "BLOCK_THRESHOLD",
        "MAIN_MERGE_BLOCK_THRESHOLD",
        "main_first_parent_shas",
        "contains_main_merge",
        "main_merge_evidence",
        "ReliefEvidence",
        "GitRunner",
        "_run_git",
        "_is_external_parent",
        "_external_non_first_parent_shas",
    ],
)
def test_the_block_and_relief_machinery_is_not_importable(name: str) -> None:
    assert not hasattr(mod, name)
