"""The previous promoted manifest: selection from releases, download, and the gate flag.

ADR-113 Resolved Question 3 and decision 9. The baseline feeds only the
non-blocking `remediated` class, but a stale or malformed one must still not be
read silently, so every refusal below is a raise or a non-zero exit.
"""

from __future__ import annotations

import json
import runpy
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.fetch_previous_manifest import EXIT_CONFIG, EXIT_EXTERNAL, EXIT_OK, main
from scripts.validation.promotion_baseline import (
    MANIFEST_ASSET_NAME,
    MAX_MANIFEST_BYTES,
    fetch_baseline,
    select_baseline,
)
from scripts.validation.promotion_fetch import GhCliReader, GitHubApiError, paginate
from scripts.validation.promotion_findings import ManifestError
from scripts.validation.promotion_gate import EXIT_CONFIG as GATE_CONFIG
from scripts.validation.promotion_gate import EXIT_OK as GATE_OK
from scripts.validation.promotion_gate import main as gate_main

SHA = "a" * 40
OLD = "b" * 40
REPO = "owner/repo"


def _asset(asset_id: int = 11, created: str = "2026-09-01T00:00:00Z", **overrides: Any) -> dict:
    asset: dict[str, Any] = {
        "id": asset_id,
        "name": MANIFEST_ASSET_NAME,
        "state": "uploaded",
        "size": 500,
        "created_at": created,
        "uploader": {"login": "github-actions[bot]"},
    }
    asset.update(overrides)
    return asset


def _release(tag: str = "v1", assets: Any = None, **overrides: Any) -> dict[str, Any]:
    release: dict[str, Any] = {
        "tag_name": tag,
        "draft": False,
        "assets": [_asset()] if assets is None else assets,
    }
    release.update(overrides)
    return release


def _manifest(sha: str = OLD, **overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": "1",
        "verdict": "promote",
        "enforced": True,
        "candidate": {"sha": sha},
        "findings": [],
    }
    document.update(overrides)
    return document


class FakeReader:
    def __init__(self, releases: Any, bodies: Mapping[int, bytes] | None = None) -> None:
        self.releases = releases
        self.bodies = bodies or {}
        self.calls: list[tuple[str, str | None]] = []

    def get_json(self, path: str, params: Mapping[str, str] | None = None) -> object:
        self.calls.append((path, None))
        return self.releases

    def get_bytes(self, path: str, accept: str | None = None) -> bytes:
        self.calls.append((path, accept))
        return self.bodies[int(path.rsplit("/", 1)[1])]


class TestSelect:
    def test_the_newest_manifest_asset_wins(self) -> None:
        releases = [
            _release("v1", [_asset(1, "2026-08-01T00:00:00Z")]),
            _release("v2", [_asset(2, "2026-09-01T00:00:00Z")]),
        ]
        chosen = select_baseline(releases, "")
        assert chosen is not None
        assert (chosen.tag, chosen.asset_id) == ("v2", 2)

    def test_no_releases_means_a_first_promotion(self) -> None:
        assert select_baseline([], "") is None

    def test_a_release_with_no_manifest_asset_is_skipped(self) -> None:
        assert select_baseline([_release("v1", [])], "") is None
        assert select_baseline([_release("v1", [_asset(name="other.json")])], "") is None

    def test_the_tag_being_promoted_is_never_its_own_baseline(self) -> None:
        assert select_baseline([_release("v2")], "v2") is None

    @pytest.mark.parametrize(
        "release",
        [
            _release(draft=True),
            _release(draft=None),
            _release(tag_name=None),
            _release(tag_name=5),
            _release(assets="nope"),
            _release(assets=[None, "x"]),
            "junk",
            None,
        ],
    )
    def test_an_unusable_release_is_skipped(self, release: Any) -> None:
        assert select_baseline([release], "") is None

    @pytest.mark.parametrize(
        "overrides",
        [
            {"state": "open"},
            {"state": None},
            {"uploader": {"login": "someone"}},
            {"uploader": None},
            {"size": 0},
            {"size": MAX_MANIFEST_BYTES + 1},
            {"size": "5"},
            {"size": True},
            {"id": "11"},
            {"id": True},
            {"created_at": None},
            {"created_at": "yesterday"},
        ],
    )
    def test_an_asset_that_fails_a_check_is_not_a_baseline(self, overrides: dict[str, Any]) -> None:
        assert select_baseline([_release(assets=[_asset(**overrides)])], "") is None

    def test_a_human_upload_does_not_hide_the_bots_older_asset(self) -> None:
        human = _asset(2, "2026-09-09T00:00:00Z", uploader={"login": "someone"})
        bot = _asset(1, "2026-08-01T00:00:00Z")
        chosen = select_baseline([_release("v2", [human]), _release("v1", [bot])], "")
        assert chosen is not None
        assert chosen.asset_id == 1

    def test_times_that_cannot_be_ordered_raise(self) -> None:
        releases = [
            _release("v1", [_asset(1, "2026-08-01T00:00:00")]),
            _release("v2", [_asset(2, "2026-09-01T00:00:00Z")]),
        ]
        with pytest.raises(GitHubApiError, match="compared"):
            select_baseline(releases, "")


class TestFetch:
    def test_a_promoted_manifest_is_written_byte_for_byte(self, tmp_path: Path) -> None:
        body = json.dumps(_manifest()).encode()
        reader = FakeReader([_release("v1")], {11: body})
        chosen = fetch_baseline(reader, repo=REPO, exclude_tag="", output_dir=tmp_path / "out")
        assert chosen is not None
        assert (tmp_path / "out" / MANIFEST_ASSET_NAME).read_bytes() == body
        assert reader.calls[-1] == (
            "repos/owner/repo/releases/assets/11",
            "application/octet-stream",
        )

    def test_no_baseline_writes_nothing_and_downloads_nothing(self, tmp_path: Path) -> None:
        reader = FakeReader([_release("v1", [])])
        assert fetch_baseline(reader, repo=REPO, exclude_tag="", output_dir=tmp_path / "o") is None
        assert not (tmp_path / "o").exists()
        assert len(reader.calls) == 1

    @pytest.mark.parametrize(
        "body",
        [
            b"{nope",
            b"[]",
            b"\xff\xfe",
            json.dumps(_manifest(verdict="block")).encode(),
            json.dumps(_manifest(enforced=False)).encode(),
            json.dumps(_manifest(schema_version="9")).encode(),
            b"x" * (MAX_MANIFEST_BYTES + 1),
            ("[" * 5000 + "]" * 5000).encode(),
        ],
    )
    def test_a_newest_asset_that_is_not_a_promoted_manifest_raises(
        self, tmp_path: Path, body: bytes
    ) -> None:
        reader = FakeReader([_release("v1")], {11: body})
        with pytest.raises(ManifestError):
            fetch_baseline(reader, repo=REPO, exclude_tag="", output_dir=tmp_path / "o")
        assert not (tmp_path / "o").exists()

    def test_an_api_failure_propagates(self, tmp_path: Path) -> None:
        reader = FakeReader("not a list")
        with pytest.raises(GitHubApiError):
            fetch_baseline(reader, repo=REPO, exclude_tag="", output_dir=tmp_path)


class TestReaderPlumbing:
    def test_a_bare_list_body_is_paginated(self) -> None:
        assert paginate(FakeReader([1, 2]), "p", None, {}) == [1, 2]

    def test_the_cli_reader_sends_the_accept_header(self) -> None:
        import subprocess

        done = subprocess.CompletedProcess(["gh"], 0, stdout=b"x", stderr=b"")
        with patch.object(subprocess, "run", return_value=done) as run:
            assert (
                GhCliReader().get_bytes("repos/o/r/releases/assets/1", "application/octet-stream")
                == b"x"
            )
        assert run.call_args.args[0][-2:] == ["-H", "Accept: application/octet-stream"]


def _argv(tmp_path: Path, *extra: str) -> list[str]:
    return ["--repo", REPO, "--output-dir", str(tmp_path / "prev"), *extra]


class TestCli:
    def test_a_found_baseline_exits_zero_and_names_the_release(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        reader = FakeReader([_release("v1")], {11: json.dumps(_manifest()).encode()})
        assert main(_argv(tmp_path), reader) == EXIT_OK
        assert 'release "v1" asset 11' in capsys.readouterr().out
        assert (tmp_path / "prev" / MANIFEST_ASSET_NAME).is_file()

    def test_no_baseline_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(_argv(tmp_path), FakeReader([])) == EXIT_OK
        assert "none (first promotion)" in capsys.readouterr().out

    def test_the_current_tag_is_excluded(self, tmp_path: Path) -> None:
        reader = FakeReader([_release("v2")], {11: json.dumps(_manifest()).encode()})
        assert main(_argv(tmp_path, "--current-tag", "v2"), reader) == EXIT_OK
        assert not (tmp_path / "prev").exists()

    @pytest.mark.parametrize("repo", ["owner", "../..", "o/..", "o/.", "a b/c"])
    def test_a_bad_repo_exits_two(self, tmp_path: Path, repo: str) -> None:
        argv = ["--repo", repo, "--output-dir", str(tmp_path)]
        assert main(argv, FakeReader([])) == EXIT_CONFIG

    def test_a_malformed_baseline_exits_two(self, tmp_path: Path) -> None:
        assert main(_argv(tmp_path), FakeReader([_release("v1")], {11: b"{"})) == EXIT_CONFIG

    def test_a_github_failure_exits_three(self, tmp_path: Path) -> None:
        assert main(_argv(tmp_path), FakeReader({"not": "a list"})) == EXIT_EXTERNAL

    def test_an_unwritable_output_exits_three(self, tmp_path: Path) -> None:
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")
        reader = FakeReader([_release("v1")], {11: json.dumps(_manifest()).encode()})
        argv = ["--repo", REPO, "--output-dir", str(blocker / "sub")]
        assert main(argv, reader) == EXIT_EXTERNAL

    def test_the_entry_point_guard_returns_the_exit_code(self) -> None:
        script = Path(main.__code__.co_filename)
        with (
            patch.object(sys, "argv", [str(script), "--repo", REPO]),
            pytest.raises(SystemExit) as stop,
        ):
            runpy.run_path(str(script), run_name="__main__")
        assert stop.value.code == EXIT_CONFIG


class TestGateFlag:
    def _args(self, tmp_path: Path, *extra: str) -> list[str]:
        (tmp_path / "ev").mkdir(exist_ok=True)
        return ["--repo-root", str(tmp_path), "--evidence-dir", str(tmp_path / "ev"),
                "--candidate-sha", SHA, "--output", str(tmp_path / "m.json"), *extra]  # fmt: skip

    def test_an_absent_file_in_the_directory_is_a_first_promotion(self, tmp_path: Path) -> None:
        (tmp_path / "prev").mkdir()
        assert (
            gate_main(self._args(tmp_path, "--previous-manifest-dir", str(tmp_path / "prev")))
            == GATE_OK
        )
        assert json.loads((tmp_path / "m.json").read_text("utf-8"))["remediated"] == []

    def test_a_missing_directory_is_a_first_promotion(self, tmp_path: Path) -> None:
        assert (
            gate_main(self._args(tmp_path, "--previous-manifest-dir", str(tmp_path / "none")))
            == GATE_OK
        )

    def test_a_present_file_must_parse(self, tmp_path: Path) -> None:
        directory = tmp_path / "prev"
        directory.mkdir()
        (directory / MANIFEST_ASSET_NAME).write_text("{nope", encoding="utf-8")
        assert (
            gate_main(self._args(tmp_path, "--previous-manifest-dir", str(directory)))
            == GATE_CONFIG
        )

    def test_a_valid_file_is_loaded(self, tmp_path: Path) -> None:
        directory = tmp_path / "prev"
        directory.mkdir()
        (directory / MANIFEST_ASSET_NAME).write_text(json.dumps(_manifest()), encoding="utf-8")
        assert gate_main(self._args(tmp_path, "--previous-manifest-dir", str(directory))) == GATE_OK

    def test_the_two_flags_are_mutually_exclusive(self, tmp_path: Path) -> None:
        argv = self._args(tmp_path, "--previous-manifest", "a.json", "--previous-manifest-dir", "d")
        assert gate_main(argv) == GATE_CONFIG
