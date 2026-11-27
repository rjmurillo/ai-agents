"""A 64 character hex run is no longer a pass (owner decision D3).

Plan M1-T9, premortem R4. Only a 40 character run is a git object id and is reported. A 64
character run is the length of a SHA-256 digest, an API key, or a token, so it blocks
unless `--allow-hex-rows` names the row. The 32 character public bot ids are unchanged.
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

_HEX64 = "0123456789abcdef" * 4
_HEX40 = "0123456789abcdef0123456789abcdef01234567"
_HEX32 = "0123456789abcdef0123456789abcdef"


def _row(body: str, row_id: str = "R") -> dict[str, Any]:
    return {"id": row_id, "body": body, "thread_replies": [], "diff_hunk": None}


class TestScanLevel:
    def test_a_64_hex_run_blocks(self) -> None:
        """A 64 hex run is blocked as hex-secret."""
        result = scan.scan_secrets([_row(f"digest {_HEX64}")])

        assert result.blocking == {"R": ["hex-secret"]}
        assert result.hex_reported == []

    def test_a_64_hex_run_passes_when_the_row_is_allowed_and_is_reported(self) -> None:
        """--allow-hex-rows names the row, so it is reported for review instead."""
        result = scan.scan_secrets([_row(f"digest {_HEX64}")], allow_hex_rows=frozenset({"R"}))

        assert result.blocking == {}
        assert result.hex_reported == ["R"]

    def test_the_allowance_is_per_row(self) -> None:
        """Naming one row does not excuse another."""
        rows = [_row(f"a {_HEX64}", "KEEP"), _row(f"b {_HEX64}", "BLOCK")]

        result = scan.scan_secrets(rows, allow_hex_rows=frozenset({"KEEP"}))

        assert set(result.blocking) == {"BLOCK"}

    def test_a_40_hex_run_is_still_reported_not_blocked(self) -> None:
        """The git object id length is unchanged."""
        result = scan.scan_secrets([_row(f"see {_HEX40}")])

        assert result.blocking == {}
        assert result.hex_reported == ["R"]

    def test_a_64_run_after_a_public_id_prefix_still_blocks(self) -> None:
        """The public-id prefixes cover exactly 32 characters and nothing longer."""
        result = scan.scan_secrets([_row(f"pr-review-job-{_HEX64}")])

        assert result.blocking == {"R": ["hex-secret"]}
        assert result.public_ids == 0

    def test_the_public_id_prefixes_are_unchanged(self) -> None:
        """A 32-hex run after either known prefix still passes as a public id."""
        for body in (f"pr-review-job-{_HEX32}", f"Syntactic id: {_HEX32}"):
            result = scan.scan_secrets([_row(body)])

            assert result.blocking == {}
            assert result.public_ids == 1

    def test_a_64_run_in_a_reply_and_in_a_path_blocks_too(self) -> None:
        """Every scanned field follows the rule."""
        reply = {**_row("clean"), "thread_replies": [f"x {_HEX64}"]}
        path = {**_row("clean", "P"), "path": f"dir/{_HEX64}/f.py"}

        result = scan.scan_secrets([reply, path])

        assert set(result.blocking) == {"R", "P"}

    def test_the_allowed_length_set_is_only_40(self) -> None:
        """The constant says what the docs say."""
        assert scan.HEX_ALLOWED_LENGTHS == frozenset({40})

    def test_the_module_docstring_no_longer_calls_64_a_git_id(self) -> None:
        """The prose matches the rule."""
        doc = scan.__doc__ or ""

        assert "40 or 64" not in doc
        assert "64" in doc


class TestCliLevel:
    def _sample_argv(self, tmp_path: Path, body: str, *extra: str) -> tuple[list[str], Path]:
        prs = write_prs(
            tmp_path / "prs.json", [make_pr(1, make_thread(make_node("PRRC_H64", body)))]
        )
        out = tmp_path / "corpus.jsonl"
        argv = ["sample", "--prs", str(prs), "--output", str(out)]
        argv += ["--band-count", "2", "--outside-count", "0", "--dev-count", "0", *extra]
        return argv, out

    def test_sample_exits_one_on_a_64_hex_body(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Through main(argv): the corpus is not written and the row is named."""
        argv, out = self._sample_argv(tmp_path, f"Consider a helper {_HEX64}")

        code = cc.main(argv)

        err = capsys.readouterr().err
        assert code == 1
        assert not out.exists()
        assert "row PRRC_H64" in err
        assert _HEX64 not in err

    def test_sample_exits_zero_when_the_row_is_allowed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The allowance turns the block into a reviewed report."""
        argv, out = self._sample_argv(
            tmp_path, f"Consider a helper {_HEX64}", "--allow-hex-rows", "PRRC_H64"
        )

        code = cc.main(argv)

        assert code == 0
        assert out.exists()
        assert "review: hex-like strings in rows PRRC_H64" in capsys.readouterr().err

    def test_predict_exits_one_on_a_64_hex_body_before_any_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The predict gate follows the same rule."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        fake = install_call_api(monkeypatch, FakeCallApi())
        rows = [make_row("H0", body=f"digest {_HEX64}")]

        code = aa.main(provider_argv(write_corpus_file(tmp_path, rows), tmp_path / "p.jsonl"))

        assert code == 1
        assert fake.calls == []
