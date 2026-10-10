"""Fetching main's testmon database: trust checks, fallbacks, and the key.

Issue #6239. The fetch runs inside pre-push, so every failure must come back as
a `SeedResult(False, reason)` and never raise, and nothing may be accepted from
outside a `push` run on `main` of the canonical repository.
"""

from __future__ import annotations

import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from scripts.validation import testmon_seed as seed

REPO = seed.CANONICAL_REPO


def _write_inputs(root: Path, lock: str = "lock-v1", project: str = "project-v1") -> None:
    (root / "uv.lock").write_text(lock, encoding="utf-8")
    (root / "pyproject.toml").write_text(project, encoding="utf-8")


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _run(run_id: int, *, event: str = "push", branch: str = "main", repo: str = REPO) -> dict:
    return {
        "id": run_id,
        "event": event,
        "head_branch": branch,
        "head_repository": {"full_name": repo},
    }


class FakeGh:
    """A `gh api` stand-in keyed by endpoint substring; records every endpoint."""

    def __init__(self, routes: dict[str, bytes | int]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
        endpoint = args[0]
        self.calls.append(endpoint)
        for needle, payload in self.routes.items():
            if needle in endpoint:
                if isinstance(payload, int):
                    return subprocess.CompletedProcess(args, payload, b"", b"gh: not logged in")
                return subprocess.CompletedProcess(args, 0, payload, b"")
        return subprocess.CompletedProcess(args, 1, b"", b"gh: HTTP 404")


def _routes(
    root: Path, runs: list[dict], artifacts: dict[int, list[dict]], database: bytes
) -> dict[str, bytes | int]:
    routes: dict[str, bytes | int] = {"/workflows/pytest.yml/runs": _json({"workflow_runs": runs})}
    for run_id, listing in artifacts.items():
        routes[f"/runs/{run_id}/artifacts"] = _json({"artifacts": listing})
    routes["/artifacts/900/zip"] = _zip({".testmondata": database})
    return routes


def _json(value: object) -> bytes:
    return json.dumps(value).encode()


def _artifact(root: Path, artifact_id: int = 900, **overrides: object) -> dict:
    entry: dict[str, object] = {
        "id": artifact_id,
        "name": seed.seed_artifact_name(root),
        "expired": False,
    }
    entry.update(overrides)
    return entry


def _fetch(root: Path, gh: FakeGh, timeout_seconds: float = 30.0) -> seed.SeedResult:
    return seed.fetch_seed(
        root, runner=gh, gh_available=lambda: True, timeout_seconds=timeout_seconds
    )


DATABASE = seed.SQLITE_MAGIC + b"rest-of-file"


class TestSeedKey:
    def test_the_key_is_stable_for_unchanged_inputs(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path)
        assert seed.seed_key(tmp_path) == seed.seed_key(tmp_path)

    @pytest.mark.parametrize("changed", ["lock", "project"])
    def test_either_input_changes_the_key(self, tmp_path: Path, changed: str) -> None:
        _write_inputs(tmp_path)
        before = seed.seed_key(tmp_path)
        _write_inputs(
            tmp_path,
            lock="lock-v2" if changed == "lock" else "lock-v1",
            project="project-v2" if changed == "project" else "project-v1",
        )
        assert seed.seed_key(tmp_path) != before

    def test_bytes_cannot_move_between_the_two_files(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path, lock="ab", project="c")
        first = seed.seed_key(tmp_path)
        _write_inputs(tmp_path, lock="a", project="bc")
        assert seed.seed_key(tmp_path) != first

    def test_a_missing_input_raises_rather_than_hashing_nothing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            seed.seed_key(tmp_path)

    def test_the_artifact_name_carries_the_prefix(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path)
        assert seed.seed_artifact_name(tmp_path).startswith(seed.SEED_ARTIFACT_PREFIX)


class TestRunTrust:
    def test_a_push_to_main_of_the_canonical_repo_is_trusted(self) -> None:
        assert seed.run_is_trusted(_run(1))

    @pytest.mark.parametrize(
        "run",
        [
            _run(1, event="pull_request"),
            _run(1, event="merge_group"),
            _run(1, event="workflow_dispatch"),
            _run(1, branch="feature/x"),
            _run(1, branch="main-evil"),
            _run(1, repo="attacker/ai-agents"),
            {"id": 1, "event": "push", "head_branch": "main"},
            {
                "id": "1",
                "event": "push",
                "head_branch": "main",
                "head_repository": {"full_name": REPO},
            },
            {"event": "push", "head_branch": "main", "head_repository": {"full_name": REPO}},
        ],
    )
    def test_everything_else_is_refused(self, run: dict) -> None:
        assert not seed.run_is_trusted(run)


class TestArtifactSelection:
    def test_exact_name_match_wins(self) -> None:
        artifacts = [{"id": 1, "name": "testmon-db-other", "expired": False}]
        artifacts.append({"id": 2, "name": "testmon-db-key", "expired": False})
        assert seed.select_artifact_id(artifacts, "testmon-db-key") == 2

    def test_a_prefix_or_suffix_match_is_not_a_match(self) -> None:
        artifacts = [
            {"id": 1, "name": "testmon-db-key-extra", "expired": False},
            {"id": 2, "name": "x-testmon-db-key", "expired": False},
        ]
        assert seed.select_artifact_id(artifacts, "testmon-db-key") is None

    @pytest.mark.parametrize("expired", [True, None, "false"])
    def test_an_expired_or_unmarked_artifact_is_refused(self, expired: object) -> None:
        artifacts = [{"id": 1, "name": "testmon-db-key", "expired": expired}]
        assert seed.select_artifact_id(artifacts, "testmon-db-key") is None

    @pytest.mark.parametrize("junk", [None, "x", 3, {"id": 1}, [None, "x"]])
    def test_malformed_listings_select_nothing(self, junk: object) -> None:
        assert seed.select_artifact_id(junk, "testmon-db-key") is None


class TestFetchSeed:
    def test_a_matching_main_push_artifact_is_written(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path)
        gh = FakeGh(_routes(tmp_path, [_run(7)], {7: [_artifact(tmp_path)]}, DATABASE))
        result = _fetch(tmp_path, gh)
        assert result.seeded, result.detail
        assert (tmp_path / ".testmondata").read_bytes() == DATABASE
        assert not list(tmp_path.glob("*.tmp"))

    def test_the_newest_run_with_the_key_is_chosen(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path)
        routes = _routes(
            tmp_path,
            [_run(8), _run(7)],
            {8: [{"id": 1, "name": "other", "expired": False}], 7: [_artifact(tmp_path)]},
            DATABASE,
        )
        gh = FakeGh(routes)
        assert _fetch(tmp_path, gh).seeded
        artifact_calls = [c for c in gh.calls if c.endswith("/artifacts")]
        assert [c.split("/")[-2] for c in artifact_calls] == ["8", "7"]

    @pytest.mark.parametrize(
        "run",
        [_run(7, event="pull_request"), _run(7, branch="topic"), _run(7, repo="fork/ai-agents")],
    )
    def test_an_untrusted_run_is_never_listed_or_downloaded(
        self, tmp_path: Path, run: dict
    ) -> None:
        _write_inputs(tmp_path)
        gh = FakeGh(_routes(tmp_path, [run], {7: [_artifact(tmp_path)]}, DATABASE))
        result = _fetch(tmp_path, gh)
        assert not result.seeded
        assert not (tmp_path / ".testmondata").exists()
        assert not any("/runs/7/" in call or "/zip" in call for call in gh.calls)

    def test_the_run_query_asks_for_main_push_runs_only(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path)
        gh = FakeGh(_routes(tmp_path, [], {}, DATABASE))
        _fetch(tmp_path, gh)
        assert "event=push" in gh.calls[0]
        assert "branch=main" in gh.calls[0]
        assert f"repos/{REPO}/" in gh.calls[0]

    def test_a_key_mismatch_finds_no_artifact(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path)
        stale = _artifact(tmp_path, name="testmon-db-" + "0" * 64)
        gh = FakeGh(_routes(tmp_path, [_run(7)], {7: [stale]}, DATABASE))
        result = _fetch(tmp_path, gh)
        assert not result.seeded
        assert "no main push run" in result.detail

    def test_an_existing_database_is_never_replaced_and_nothing_is_fetched(
        self, tmp_path: Path
    ) -> None:
        _write_inputs(tmp_path)
        (tmp_path / ".testmondata").write_bytes(b"mine")
        gh = FakeGh({})
        result = _fetch(tmp_path, gh)
        assert not result.seeded
        assert (tmp_path / ".testmondata").read_bytes() == b"mine"
        assert gh.calls == []

    def test_a_missing_gh_falls_back(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path)
        gh = FakeGh({})
        result = seed.fetch_seed(tmp_path, runner=gh, gh_available=lambda: False)
        assert result == seed.SeedResult(False, "gh is not installed")
        assert gh.calls == []

    def test_an_unauthenticated_gh_falls_back(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path)
        result = _fetch(tmp_path, FakeGh({"/workflows/": 4}))
        assert not result.seeded
        assert "gh api failed" in result.detail

    def test_offline_falls_back(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path)

        def offline(args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(args, 1, b"", b"dial tcp: no such host")

        result = seed.fetch_seed(tmp_path, runner=offline, gh_available=lambda: True)
        assert not result.seeded
        assert "no such host" in result.detail

    def test_a_subprocess_timeout_falls_back(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path)

        def slow(args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
            raise subprocess.TimeoutExpired(args, timeout)

        result = seed.fetch_seed(tmp_path, runner=slow, gh_available=lambda: True)
        assert not result.seeded
        assert "timed out" in result.detail

    def test_the_whole_fetch_shares_one_deadline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_inputs(tmp_path)
        seen: list[float] = []
        clock = {"now": 100.0}
        monkeypatch.setattr(seed.time, "monotonic", lambda: clock["now"])

        def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
            seen.append(timeout)
            clock["now"] += 20.0
            body = _json({"workflow_runs": [_run(7), _run(8)]})
            return subprocess.CompletedProcess(args, 0, body, b"")

        result = seed.fetch_seed(
            tmp_path, runner=runner, gh_available=lambda: True, timeout_seconds=30.0
        )
        assert not result.seeded
        assert seen[0] == pytest.approx(30.0)
        assert seen[1] == pytest.approx(10.0)
        assert len(seen) == 2
        assert "deadline" in result.detail

    def test_the_default_deadline_is_short(self) -> None:
        assert seed.SEED_FETCH_TIMEOUT_SECONDS <= 30.0

    @pytest.mark.parametrize(
        "payload",
        [b"not a zip", _zip({"other": DATABASE}), _zip({".testmondata": b"not sqlite"})],
    )
    def test_a_bad_download_falls_back_and_writes_nothing(
        self, tmp_path: Path, payload: bytes
    ) -> None:
        _write_inputs(tmp_path)
        routes = _routes(tmp_path, [_run(7)], {7: [_artifact(tmp_path)]}, DATABASE)
        routes["/artifacts/900/zip"] = payload
        result = _fetch(tmp_path, FakeGh(routes))
        assert not result.seeded
        assert not (tmp_path / ".testmondata").exists()
        assert not list(tmp_path.glob("*.tmp"))

    def test_a_path_traversal_member_is_never_extracted(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path)
        routes = _routes(tmp_path, [_run(7)], {7: [_artifact(tmp_path)]}, DATABASE)
        routes["/artifacts/900/zip"] = _zip({"../.testmondata": DATABASE})
        assert not _fetch(tmp_path, FakeGh(routes)).seeded
        assert not (tmp_path.parent / ".testmondata").exists()

    def test_an_oversized_database_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_inputs(tmp_path)
        monkeypatch.setattr(seed, "MAX_DATABASE_BYTES", 4)
        gh = FakeGh(_routes(tmp_path, [_run(7)], {7: [_artifact(tmp_path)]}, DATABASE))
        result = _fetch(tmp_path, gh)
        assert not result.seeded
        assert "size cap" in result.detail

    def test_missing_dependency_inputs_fall_back_without_raising(self, tmp_path: Path) -> None:
        result = _fetch(tmp_path, FakeGh({}))
        assert not result.seeded

    def test_garbled_json_falls_back(self, tmp_path: Path) -> None:
        _write_inputs(tmp_path)
        result = _fetch(tmp_path, FakeGh({"/workflows/": b"<html>"}))
        assert not result.seeded


def test_main_prints_the_artifact_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_inputs(tmp_path)
    assert seed.main(["testmon_seed.py", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == seed.seed_artifact_name(tmp_path)
