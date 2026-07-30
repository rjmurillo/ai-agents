#!/usr/bin/env python3
"""Tests for scripts/validation/pr_commit_count.py (issue #3262).

Covers positive (threshold classification), negative (genuine errors), and
transient-error (503 / no-server / timeout / unparseable body) paths, plus
GITHUB_OUTPUT emission and CLI exit codes, per TESTING-RIGOR.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation import pr_commit_count as mod  # noqa: E402


def _completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["gh"], returncode=returncode, stdout=stdout, stderr=stderr)


def _commits_json(n: int) -> str:
    return json.dumps([{"sha": f"{i:040x}"} for i in range(n)])


# ---------------------------------------------------------------------------
# classify_count: threshold boundaries (issue #362)
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
        (21, "BLOCKED"),
        (99, "BLOCKED"),
    ],
)
def test_classify_count_thresholds(count: int, expected: str) -> None:
    assert mod.classify_count(count) == expected


@pytest.mark.parametrize(("count", "blocked"), [(19, False), (20, False), (21, True)])
def test_the_block_boundary_agrees_with_the_local_hook(count: int, blocked: bool) -> None:
    """The two enforcement points must draw the line in the same place.

    The local hook in ``scripts/validation/git_hook_policy.py`` allows a push
    when ``commit_count <= limit``, and ``AGENTS.md`` states the rule as
    ``<=20``. That ``limit`` is 20 by default, so at the default the two
    points now agree: 20 passes both, 21 fails both. A count of 20 that
    pushed cleanly and then failed the pull request check gave an author a red
    pull request with no local signal (issue #3721).

    The hook widens ``limit`` to 40 when the update contains a merge of main,
    and CI applies the same widening: ``count_pr_commits`` reads the pull
    request's own commit list through ``contains_base_merge``. A main-merge
    branch at 21 through 40 therefore needs no bypass label. This test pins
    only the default boundary; ``test_classify_count_honours_an_explicit_limit``
    pins the widened one.
    """
    assert (mod.classify_count(count) == "BLOCKED") is blocked


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
    assert result == mod.CountResult("OK", 3, transient=False)


def test_fetch_healthy_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, _commits_json(21)))
    result = mod.fetch_commit_count(42, "o", "r")
    assert result.status == "BLOCKED"
    assert result.count == 21
    assert result.transient is False


def test_fetch_at_the_limit_is_not_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A count the local hook accepts must survive the fetch path too (#3721)."""
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, _commits_json(20)))
    result = mod.fetch_commit_count(42, "o", "r")
    assert result.status == "ALERT"
    assert result.count == 20


def test_fetch_empty_list_is_ok_not_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # A healthy 200 with an empty list means zero commits, which is not over
    # the limit. The old inline step hard-failed here; the new contract is OK.
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, "[]"))
    result = mod.fetch_commit_count(42, "o", "r")
    assert result == mod.CountResult("OK", 0, transient=False)


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
    mod._write_github_output("BLOCKED", 22)
    content = out.read_text(encoding="utf-8")
    assert "status=BLOCKED\n" in content
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


def test_main_blocked_emits_error_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_repo(monkeypatch)
    monkeypatch.setattr(mod, "_run_gh", lambda argv: _completed(0, _commits_json(25)))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "gh_out"))
    rc = mod.main(["--pr-number", "42"])
    assert rc == 0
    assert "::error::PR exceeds commit limit" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Issue #3596: the main-merge relief must apply in CI, not only in the
# pre-push hook, and both ceilings must come from this module.
# ---------------------------------------------------------------------------


def _merge_commits_json(n: int, external_parent: bool) -> str:
    """Build a commits payload whose last entry is a merge commit.

    ``external_parent`` decides whether the merge's second parent is outside the
    PR's own commit list, which is what marks a merge as coming from the base.
    """
    commits: list[dict[str, object]] = [
        {"sha": f"{i:040x}", "parents": [{"sha": f"{i - 1:040x}"}]} for i in range(n - 1)
    ]
    second = "f" * 40 if external_parent else f"{0:040x}"
    commits.append(
        {"sha": f"{n - 1:040x}", "parents": [{"sha": f"{n - 2:040x}"}, {"sha": second}]}
    )
    return json.dumps(commits)


def test_contains_base_merge_is_false_for_a_linear_branch() -> None:
    payload = json.loads(_merge_commits_json(5, external_parent=False))
    assert mod.contains_base_merge(payload) is False


def test_contains_base_merge_is_true_when_a_merge_parent_is_outside_the_branch() -> None:
    payload = json.loads(_merge_commits_json(5, external_parent=True))
    assert mod.contains_base_merge(payload) is True


def test_contains_base_merge_ignores_a_merge_between_two_branch_commits() -> None:
    """An internal merge is the branch's own history, not a merge from main."""
    payload = [
        {"sha": "a" * 40, "parents": [{"sha": "0" * 40}]},
        {"sha": "b" * 40, "parents": [{"sha": "0" * 40}]},
        {"sha": "c" * 40, "parents": [{"sha": "a" * 40}, {"sha": "b" * 40}]},
    ]
    assert mod.contains_base_merge(payload) is False


@pytest.mark.parametrize(
    "payload",
    [
        [],
        ["not-a-dict"],
        [{"sha": "a" * 40}],
        [{"sha": "a" * 40, "parents": "not-a-list"}],
        [{"sha": "a" * 40, "parents": [{"sha": "b" * 40}, "not-a-dict"]}],
    ],
    ids=["empty", "non-dict", "no-parents", "parents-not-list", "parent-not-dict"],
)
def test_contains_base_merge_fails_closed_on_malformed_payloads(
    payload: list[object],
) -> None:
    """Malformed data must not grant the relief: False keeps the stricter 20."""
    assert mod.contains_base_merge(payload) is False


def test_classify_count_honours_an_explicit_limit() -> None:
    """The boundary is strict: the limit itself is allowed, one past it blocks.

    The pre-push hook in ``git_hook_policy._check_commit_limit`` accepts
    ``commit_count <= limit`` (issue #3721). Blocking at ``count == limit``
    here would reject in CI the exact push the hook had just waved through.
    """
    assert mod.classify_count(20, mod.BLOCK_THRESHOLD) == "ALERT"
    assert mod.classify_count(21, mod.BLOCK_THRESHOLD) == "BLOCKED"
    assert mod.classify_count(20, mod.MAIN_MERGE_BLOCK_THRESHOLD) == "ALERT"
    assert mod.classify_count(39, mod.MAIN_MERGE_BLOCK_THRESHOLD) == "ALERT"
    assert mod.classify_count(40, mod.MAIN_MERGE_BLOCK_THRESHOLD) == "ALERT"
    assert mod.classify_count(41, mod.MAIN_MERGE_BLOCK_THRESHOLD) == "BLOCKED"


def test_classify_count_default_limit_is_unchanged() -> None:
    """The default argument keeps every pre-existing caller on the 20 ceiling."""
    assert mod.classify_count(21) == "BLOCKED"
    assert mod.classify_count(20) == "ALERT"
    assert mod.classify_count(19) == "ALERT"


def test_a_branch_merging_main_is_not_blocked_below_forty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """25 commits with a merge from main passes CI, matching the pre-push hook."""
    monkeypatch.setattr(
        mod, "_run_gh", lambda argv: _completed(0, _merge_commits_json(25, True))
    )
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "gh_out"))
    assert mod.main(["--pr-number", "42"]) == 0
    assert "::error::PR exceeds commit limit" not in capsys.readouterr().out
    written = (tmp_path / "gh_out").read_text(encoding="utf-8")
    assert "status=ALERT" in written
    assert f"commit_limit={mod.MAIN_MERGE_BLOCK_THRESHOLD}" in written


def test_a_linear_branch_of_twenty_five_is_still_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Negative control: the relief must not fire without a merge from the base."""
    monkeypatch.setattr(
        mod, "_run_gh", lambda argv: _completed(0, _merge_commits_json(25, False))
    )
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "gh_out"))
    assert mod.main(["--pr-number", "42"]) == 0
    assert "::error::PR exceeds commit limit" in capsys.readouterr().out
    written = (tmp_path / "gh_out").read_text(encoding="utf-8")
    assert "status=BLOCKED" in written
    assert f"commit_limit={mod.BLOCK_THRESHOLD}" in written


_CEILING_NAMES = ("BLOCK_THRESHOLD", "MAIN_MERGE_BLOCK_THRESHOLD")


def _ceilings_restated_in(source: str) -> set[str]:
    """Return the ceiling names this source assigns instead of importing.

    An identity assertion cannot answer the drift question: CPython interns
    small integers, so ``a.BLOCK_THRESHOLD is b.BLOCK_THRESHOLD`` holds even
    when both modules restate ``20`` independently. The property that actually
    fails on drift is structural, so read it off the syntax tree.
    """
    tree = ast.parse(source)
    restated: set[str] = set()
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id in _CEILING_NAMES:
                restated.add(target.id)
    return restated


def _ceilings_imported_in(source: str) -> set[str]:
    """Return the ceiling names this source pulls in through an import."""
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _CEILING_NAMES:
                    imported.add(alias.name)
    return imported


def test_the_hook_and_ci_read_the_same_two_ceilings() -> None:
    """Issue #3596: one number in one place. A second literal would drift."""
    source = (
        _PROJECT_ROOT / "scripts" / "validation" / "git_hook_policy.py"
    ).read_text(encoding="utf-8")

    assert _ceilings_restated_in(source) == set()
    assert _ceilings_imported_in(source) == set(_CEILING_NAMES)


def test_the_drift_detector_flags_a_restated_ceiling() -> None:
    """The detector must be able to fail, or the check above proves nothing.

    This is the control the interned-integer assertion could never have: a
    source that genuinely restates the literal is flagged, so a green run of
    the test above is evidence rather than a tautology.
    """
    drifted = "BLOCK_THRESHOLD = 20\nMAIN_MERGE_BLOCK_THRESHOLD: int = 40\n"

    assert _ceilings_restated_in(drifted) == set(_CEILING_NAMES)
    assert _ceilings_imported_in(drifted) == set()


def test_the_drift_detector_ignores_unrelated_assignments() -> None:
    """Names that merely look similar must not be read as a restated ceiling."""
    unrelated = "OTHER_BLOCK_THRESHOLD = 20\nthreshold = 40\n"

    assert _ceilings_restated_in(unrelated) == set()


# ---------------------------------------------------------------------------
# contains_base_merge: malformed parents must not grant the relaxed ceiling
# ---------------------------------------------------------------------------


def _merge(*parent_entries: object) -> list[dict[str, object]]:
    """Build a one-commit payload whose merge parents are the given entries."""
    return [{"sha": "own", "parents": [{"sha": "own"}, *parent_entries]}]


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("parent dict without a sha key", _merge({"url": "https://example"})),
        ("parent sha is null", _merge({"sha": None})),
        ("parent sha is empty", _merge({"sha": ""})),
        ("parent sha is not a string", _merge({"sha": 17})),
        ("every parent is malformed", _merge({"sha": None}, {"nope": 1})),
    ],
)
def test_malformed_parents_do_not_grant_the_relaxed_ceiling(
    label: str, payload: list[dict[str, object]]
) -> None:
    """Malformed payloads fail closed, keeping the stricter 20-commit ceiling.

    ``contains_base_merge`` gates an *exemption*: True raises the ceiling from
    BLOCK_THRESHOLD to MAIN_MERGE_BLOCK_THRESHOLD. A parent entry we cannot
    read is not evidence of a base merge, so it must not buy the relief.
    """
    assert mod.contains_base_merge(payload) is False, label


@pytest.mark.parametrize(
    ("label", "payload", "expected"),
    [
        ("parent outside the branch is a real base merge", _merge({"sha": "external"}), True),
        ("all parents authored by the branch", _merge({"sha": "own"}), False),
        ("parent entry is not a mapping", _merge("external"), False),
        ("malformed beside a genuine external parent", _merge({"sha": None}, {"sha": "ext"}), True),
        ("no merge commit at all", [{"sha": "own", "parents": [{"sha": "own"}]}], False),
        ("parents key missing", [{"sha": "own"}], False),
        ("commit is not a mapping", ["own"], False),
        ("empty payload", [], False),
    ],
)
def test_contains_base_merge_controls(
    label: str, payload: list[object], expected: bool
) -> None:
    """Behaviour that must survive the malformed-parent narrowing unchanged."""
    assert mod.contains_base_merge(payload) is expected, label
