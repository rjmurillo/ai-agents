"""The file path is part of what the model sees, so the secret scan covers it (finding 3).

Plan M1-T9, premortem R4. Token fixtures are concatenated so no full credential shape sits
in the source file.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_arms_test_support import (
    FakeCallApi,
    aa,
    install_call_api,
    make_row,
    provider_argv,
    write_corpus_file,
)
from tests.eval._actionability_corpus_test_support import (
    cc,
    make_node,
    make_pr,
    make_thread,
    write_prs,
)

pytestmark = pytest.mark.usefixtures("freeze_actionability_clock")

scan = importlib.import_module("scripts.eval.actionability_scan")

_ANT_TOKEN = "sk-" + "ant-" + "a1B2c3D4e5F6g7H8i9J0k1L2"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


def _row(path: Any) -> dict[str, Any]:
    return {"id": "R", "body": "clean", "thread_replies": [], "diff_hunk": None, "path": path}


class TestScanSecretsPath:
    def test_a_token_in_the_path_blocks(self) -> None:
        """The path leaves the machine in the predict message, so it is scanned."""
        result = scan.scan_secrets([_row(f"src/{_ANT_TOKEN}/a.py")])

        assert result.blocking == {"R": ["anthropic-api-key"]}

    def test_the_path_is_scanned_even_when_the_hunk_is_not(self) -> None:
        """predict skips the hunk (it is not sent) but still scans the path."""
        result = scan.scan_secrets([_row(f"x/{_ANT_TOKEN}.py")], include_hunk=False)

        assert "anthropic-api-key" in result.blocking["R"]

    @pytest.mark.parametrize("path", [None, "", "src/a.py", "docs/sk-learn/notes.md"])
    def test_ordinary_paths_pass(self, path: str | None) -> None:
        """A null, empty, or ordinary path is clean, including prose that looks like a prefix."""
        assert scan.scan_secrets([_row(path)]).blocking == {}

    def test_a_row_with_no_path_key_still_scans(self) -> None:
        """Rows written before a path existed are not an error here."""
        row: dict[str, Any] = {"id": "R", "body": "clean", "thread_replies": [], "diff_hunk": None}

        assert scan.scan_secrets([row]).blocking == {}

    def test_a_non_string_path_is_ignored_by_the_scan_itself(self) -> None:
        """Type checking is the validator's job; the scan must not crash on it."""
        assert scan.scan_secrets([_row(7)]).blocking == {}


class TestSamplePath:
    def test_a_token_in_a_comment_path_exits_one_and_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T9: sample stores the path in the corpus and the sheet, so it blocks."""
        node = make_node(
            "PRRC_PATH",
            "Consider a helper here",
            path=f"src/{_ANT_TOKEN}/a.py",
        )
        prs = write_prs(tmp_path / "prs.json", [make_pr(1, make_thread(node))])
        out = tmp_path / "corpus.jsonl"
        argv = ["sample", "--prs", str(prs), "--output", str(out)]
        argv += ["--band-count", "2", "--outside-count", "0", "--dev-count", "0"]

        code = cc.main(argv)

        err = capsys.readouterr().err
        assert code == 1
        assert not out.exists()
        assert "row PRRC_PATH" in err
        assert "anthropic-api-key" in err
        assert _ANT_TOKEN not in err


class TestPredictPath:
    def test_a_token_in_the_path_exits_one_before_any_call(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Plan M1-T14: the path is in the message, so a secret there stops the run."""
        fake = install_call_api(monkeypatch, FakeCallApi())
        rows = [make_row("H0"), make_row("H1", path=f"deploy/{_ANT_TOKEN}.yml")]
        out = tmp_path / "pred.jsonl"

        code = aa.main(provider_argv(write_corpus_file(tmp_path, rows), out))

        err = capsys.readouterr().err
        assert code == 1
        assert fake.calls == []
        assert not out.exists()
        assert "row H1" in err
        assert _ANT_TOKEN not in err
