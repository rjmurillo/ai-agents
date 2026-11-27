"""Public reviewer-bot hex identifiers in the secret scan (plan M1-T9, premortem R4).

Two bot formats embed a 32-hex identifier that is public, not a credential:
Devin review markers (`pr-review-job-<32hex>`) and semgrep (`Syntactic id: <32hex>`).
Only that exact length after that exact prefix is allowed.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_corpus_test_support import (
    cc,
    make_node,
    make_pr,
    make_thread,
    write_prs,
)

pytestmark = pytest.mark.usefixtures("freeze_actionability_clock")

scan = importlib.import_module("scripts.eval.actionability_scan")

_HEX32 = "0123456789abcdef0123456789abcdef"


def _row(body: str, row_id: str = "R") -> dict[str, Any]:
    return {"id": row_id, "body": body, "thread_replies": [], "diff_hunk": None}


def _scan(body: str) -> Any:
    return scan.scan_secrets([_row(body)])


class TestAllowedPublicIds:
    @pytest.mark.parametrize(
        "body",
        [
            f"pr-review-job-{_HEX32}",
            f"Syntactic id: {_HEX32}",
            f'<!-- devin-review-comment {{"id": "BUG_pr-review-job-{_HEX32}"}} -->',
            f'<!-- devin-review-comment {{"id": "ANALYSIS_pr-review-job-{_HEX32}"}} -->',
            f'<!-- devin-review-comment {{"id": "SEC_pr-review-job-{_HEX32}"}} -->',
            f"Finding.\nSyntactic id: {_HEX32}\nMore text.",
        ],
    )
    def test_a_32_hex_run_after_a_known_bot_prefix_passes(self, body: str) -> None:
        """The two documented bot formats are public identifiers, not secrets."""
        result = _scan(body)

        assert result.blocking == {}
        assert result.hex_reported == []
        assert result.public_ids == 1

    def test_each_public_id_in_a_row_is_counted(self) -> None:
        """The summary counts runs, not rows."""
        result = _scan(f"pr-review-job-{_HEX32} and Syntactic id: {'f' * 32}")

        assert result.blocking == {}
        assert result.public_ids == 2


class TestStillBlocked:
    def test_the_same_run_with_no_prefix_blocks(self) -> None:
        """Without the bot prefix a 32-hex run is an unknown secret shape."""
        result = _scan(f"value {_HEX32}")

        assert result.blocking == {"R": ["hex-secret"]}
        assert result.public_ids == 0

    @pytest.mark.parametrize(
        "prefix",
        [
            "pr-review-jobs-",
            "pr-review-job",
            "pr-review-job_",
            "PR-REVIEW-JOB-",
            "id: ",
            "Syntactic id:",
            "Syntactic ID: ",
            "syntactic id: ",
            "Semantic id: ",
        ],
    )
    def test_a_near_miss_prefix_blocks(self, prefix: str) -> None:
        """The prefix must match exactly, including case, separator, and trailing space."""
        result = _scan(f"{prefix}{_HEX32}")

        assert result.blocking == {"R": ["hex-secret"]}
        assert result.public_ids == 0

    @pytest.mark.parametrize("length", [33, 36, 41, 64])
    def test_a_longer_run_after_a_known_prefix_blocks(self, length: int) -> None:
        """Only exactly 32 is a public id. Other lengths follow the ordinary hex rules."""
        result = _scan(f"pr-review-job-{'a' * length}")

        assert result.public_ids == 0
        assert result.blocking == {"R": ["hex-secret"]}

    def test_a_public_id_does_not_excuse_a_second_unprefixed_run_in_the_row(self) -> None:
        """Each run is judged alone."""
        result = _scan(f"pr-review-job-{_HEX32}\nother {'b' * 32}")

        assert result.blocking == {"R": ["hex-secret"]}
        assert result.public_ids == 1

    def test_a_public_id_does_not_excuse_a_token_in_the_same_row(self) -> None:
        """The allowance covers hex only."""
        token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"

        result = _scan(f"pr-review-job-{_HEX32} {token}")

        assert "github-token-embedded" in result.blocking["R"]

    def test_a_31_hex_run_is_below_the_hex_rule_and_is_not_a_public_id(self) -> None:
        """Short runs never matched the hex rule, so they are neither blocked nor counted."""
        result = _scan(f"pr-review-job-{'a' * 31}")

        assert result.blocking == {}
        assert result.public_ids == 0

    def test_the_allow_list_still_covers_other_32_hex_runs(self) -> None:
        """--allow-hex-rows keeps working for runs that are not public ids."""
        rows = [_row(f"value {_HEX32}", "KEEP")]

        result = scan.scan_secrets(rows, allow_hex_rows=frozenset({"KEEP"}))

        assert result.blocking == {}
        assert result.hex_reported == ["KEEP"]


class TestGitIdsUnchanged:
    def test_a_git_sha_is_reported_not_blocked_and_not_a_public_id(self) -> None:
        """Group 4 behavior is intact: a 40 hex run is reported for review."""
        result = _scan(f"see commit {'c' * 40}")

        assert result.blocking == {}
        assert result.hex_reported == ["R"]
        assert result.public_ids == 0


class TestSummaryAndCli:
    def test_summary_line_reports_the_public_id_count(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group 4d extended: `public-id A` closes the summary line."""
        scan.report_scan(_scan(f"pr-review-job-{_HEX32} Syntactic id: {'e' * 32}"))

        err = capsys.readouterr().err
        assert "scanned 1 rows (+0 hunks): blocking 0, hex-reported 0, public-id 2" in err

    def test_summary_line_shows_zero_when_there_are_none(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The count prints even when it is zero."""
        scan.report_scan(_scan("plain text"))

        assert "public-id 0" in capsys.readouterr().err

    def test_sample_passes_a_bot_marker_without_an_allowance_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The CLI exits 0 on a Devin marker and reports it as a public id."""
        marker = f'<!-- devin-review-comment {{"id": "BUG_pr-review-job-{_HEX32}"}} -->'
        body = f"Consider a helper {marker}"
        node = make_node("PRRC_BOT", body)
        prs = write_prs(tmp_path / "prs.json", [make_pr(1, make_thread(node))])
        out = tmp_path / "corpus.jsonl"
        argv = ["sample", "--prs", str(prs), "--output", str(out)]
        argv += ["--band-count", "2", "--outside-count", "0", "--dev-count", "0"]

        code = cc.main(argv)

        assert code == 0
        assert out.exists()
        assert "public-id 1" in capsys.readouterr().err


class TestPublicIdRows:
    """Review round 2, finding 10: rows kept only by the public-id rule are named."""

    def test_a_row_whose_only_hex_is_a_public_id_is_listed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """So a reviewer can look at what the prefix rule let through."""
        rows = [_row(f"pr-review-job-{_HEX32}", "BOT1"), _row("plain", "PLAIN")]

        result = scan.scan_secrets(rows)
        scan.report_scan(result)

        assert result.public_id_rows == ["BOT1"]
        assert "public-id rows: BOT1" in capsys.readouterr().err

    def test_a_row_with_a_public_id_and_a_git_sha_is_hex_reported_not_public(self) -> None:
        """The sha already puts the row in the review list."""
        result = scan.scan_secrets([_row(f"Syntactic id: {_HEX32} and {'c' * 40}", "BOTH")])

        assert result.hex_reported == ["BOTH"]
        assert result.public_id_rows == []

    def test_a_blocked_row_is_not_listed(self) -> None:
        """A row that blocks is reported as blocking only."""
        result = scan.scan_secrets([_row(f"pr-review-job-{_HEX32} and {'b' * 33}", "BAD")])

        assert set(result.blocking) == {"BAD"}
        assert result.public_id_rows == []

    def test_rows_are_listed_in_input_order(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Stable output."""
        rows = [_row(f"pr-review-job-{_HEX32}", "B2"), _row(f"Syntactic id: {'e' * 32}", "A1")]

        scan.report_scan(scan.scan_secrets(rows))

        assert "public-id rows: B2, A1" in capsys.readouterr().err

    def test_no_line_when_there_are_none(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Nothing to list, nothing printed."""
        scan.report_scan(scan.scan_secrets([_row("plain")]))

        assert "public-id rows" not in capsys.readouterr().err

    def test_sample_prints_the_line_through_main(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Driven through the CLI, with the exit code asserted."""
        marker = f'<!-- devin-review-comment {{"id": "BUG_pr-review-job-{_HEX32}"}} -->'
        node = make_node("PRRC_BOT", f"Consider a helper {marker}")
        prs = write_prs(tmp_path / "prs.json", [make_pr(1, make_thread(node))])
        out = tmp_path / "corpus.jsonl"
        argv = ["sample", "--prs", str(prs), "--output", str(out)]
        argv += ["--band-count", "2", "--outside-count", "0", "--dev-count", "0"]

        code = cc.main(argv)

        assert code == 0
        assert "public-id rows: PRRC_BOT" in capsys.readouterr().err
