"""CLI boundary tests for build_third_party_gap_corpus.py: input shape and output errors."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.eval._third_party_gap_test_support import load_script


@pytest.fixture
def cli() -> Any:
    return load_script("build_third_party_gap_corpus")


def _dump(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "dump.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestDumpShape:
    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            ([], "JSON object"),
            ({"pull_requests": None, "mined_on": "2026-11-15"}, "list of objects"),
            ({"pull_requests": [1], "mined_on": "2026-11-15"}, "list of objects"),
            ({"pull_requests": [{"number": "1", "baseRefOid": "b"}]}, "integer number"),
            ({"pull_requests": [{"number": 1, "baseRefOid": 7}]}, "integer number"),
            ({"pull_requests": []}, "mined_on"),
            ({"pull_requests": [], "mined_on": "15 Nov"}, "mined_on"),
            ({"pull_requests": [], "mined_on": "2026-13-45"}, "calendar date"),
        ],
    )
    def test_a_malformed_dump_is_refused_by_name(
        self, cli: Any, payload: object, message: str
    ) -> None:
        with pytest.raises(ValueError, match=message):
            cli.validate_dump(payload)

    def test_a_malformed_dump_exits_2(self, cli: Any, tmp_path: Path) -> None:
        labels = tmp_path / "labels.jsonl"
        labels.write_text("", encoding="utf-8")
        payload = {"pull_requests": None, "mined_on": "2026-11-15"}

        code = cli.main(["--dump", str(_dump(tmp_path, payload)), "--labels", str(labels)])

        assert code == 2

    def test_the_mining_date_comes_from_the_dump(self, cli: Any) -> None:
        prs, mined_on = cli.validate_dump({"pull_requests": [], "mined_on": "2026-12-01"})

        assert (prs, mined_on) == ([], "2026-12-01")


class TestOutputErrors:
    def test_a_missing_output_directory_is_created(self, cli: Any, tmp_path: Path) -> None:
        out = tmp_path / "new" / "dir"

        code = cli.write({"findings.jsonl": "x\n"}, out, {})

        assert code == 0
        assert (out / "findings.jsonl").read_text(encoding="utf-8") == "x\n"

    def test_an_unwritable_output_exits_2(self, cli: Any, tmp_path: Path) -> None:
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")

        assert cli.write({"findings.jsonl": "x\n"}, blocker / "out", {}) == 2

    @pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs POSIX non-root")
    def test_a_target_in_an_unreadable_directory_exits_2(self, cli: Any, tmp_path: Path) -> None:
        locked = tmp_path / "locked"
        locked.mkdir()
        (locked / "findings.jsonl").write_text("x\n", encoding="utf-8")
        locked.chmod(0)
        try:
            assert cli.check({"findings.jsonl": "x\n"}, locked) == 2
        finally:
            locked.chmod(0o700)

    @pytest.mark.skipif(os.name != "posix", reason="Windows cannot remove the working directory")
    def test_a_removed_working_directory_exits_2(
        self, cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gone = tmp_path / "gone"
        gone.mkdir()
        monkeypatch.chdir(gone)
        gone.rmdir()

        assert cli.write({"findings.jsonl": "x\n"}, tmp_path / "out", {}) == 2

    def test_an_unreadable_check_target_exits_2(self, cli: Any, tmp_path: Path) -> None:
        (tmp_path / "findings.jsonl").mkdir()

        assert cli.check({"findings.jsonl": "x\n"}, tmp_path) == 2


class TestSelectionText:
    def test_the_frozen_input_renders_the_committed_texts(self, cli: Any) -> None:
        corpus = json.loads(
            (cli.REPO_ROOT / cli.OUT_DIR / "io-portability-corpus.json").read_text(encoding="utf-8")
        )

        assert cli.IO_RULE.format(first=6110, last=7380, cutoff=7066) == corpus["selection"]["rule"]

    def test_selection_texts_take_the_range_and_cutoff_of_the_input(self, cli: Any) -> None:
        replay, io = cli.selection_texts([7300, 7001, 8000], 7650)

        assert "PR >= 7650" in replay
        assert ("#7001 to #8000" in io, "PR >= 7650" in io) == (True, True)

    def test_a_new_window_states_its_own_cutoff_and_range(self, cli: Any) -> None:
        text = cli.IO_RULE.format(first=7001, last=8000, cutoff=7650)

        assert ("#7001 to #8000" in text, "PR >= 7650" in text) == (True, True)
        assert "PR >= 7650" in cli.REPLAY_RULE.format(cutoff=7650)


class TestWriteGuard:
    def test_write_under_the_checkout_from_outside_it_is_refused(
        self, cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import shutil
        import uuid

        # Under .pytest_tmp/ and removed afterwards, so a regressed guard leaves no artifact.
        out = cli.REPO_ROOT / ".pytest_tmp" / f"refused-write-{uuid.uuid4().hex}"
        monkeypatch.chdir(tmp_path)
        try:
            code = cli.write({"findings.jsonl": "x\n"}, out, {})

            assert code == 2
            assert not out.exists()
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_write_to_a_directory_outside_the_checkout_is_allowed(
        self, cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        code = cli.write({"findings.jsonl": "x\n"}, tmp_path, {})

        assert code == 0
        assert (tmp_path / "findings.jsonl").read_text(encoding="utf-8") == "x\n"

    def test_write_under_the_checkout_from_inside_it_is_allowed(
        self, cli: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import shutil
        import uuid

        out = cli.REPO_ROOT / ".pytest_tmp" / f"corpus-write-{uuid.uuid4().hex}"
        out.mkdir(parents=True)
        monkeypatch.chdir(cli.REPO_ROOT)
        try:
            code = cli.write({"findings.jsonl": "x\n"}, out, {})

            assert code == 0
            assert (out / "findings.jsonl").read_text(encoding="utf-8") == "x\n"
        finally:
            shutil.rmtree(out)
