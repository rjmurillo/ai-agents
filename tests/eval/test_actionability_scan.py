"""Tests for scripts/eval/actionability_scan.py (plan M1-T9, premortem R4).

Token fixtures are built by concatenation so no complete credential shape sits in
the source file.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from scripts.redact_secrets import redact
from tests.eval._actionability_corpus_test_support import (
    FROZEN_NOW,
    cc,
    corpus_prs,
    make_node,
    make_pr,
    make_thread,
    read_rows,
    write_prs,
)

pytestmark = pytest.mark.usefixtures("freeze_actionability_clock")

scan = importlib.import_module("scripts.eval.actionability_scan")


def _row(row_id: str, body: str, **extra: Any) -> dict[str, Any]:
    return {"id": row_id, "body": body, "thread_replies": [], "diff_hunk": None, **extra}


def _reasons(body: str, **kwargs: Any) -> list[str]:
    result = scan.scan_secrets([_row("R", body)], **kwargs)
    return result.blocking.get("R", [])


_ALNUM36 = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
_ALNUM20 = "a1B2c3D4e5F6g7H8i9J0"
_URLSAFE35 = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r"
_SG = "SG." + "a" * 22 + "." + "b" * 43

_POSITIVE_TOKENS = {
    "anthropic-api-key": "sk-" + "ant-" + _ALNUM20 + "x-y_z",
    "openai-project-key": "sk-" + "proj-" + _ALNUM20 + "x-y_z",
    "openai-api-key": "sk-" + _ALNUM20,
    "google-api-key": "AIza" + _URLSAFE35,
    "gitlab-pat": "glpat-" + _ALNUM20,
    "npm-token": "npm_" + _ALNUM36,
    "slack-token": "xoxb-" + "1234567890-abcdef",
    "sendgrid-api-key": _SG,
    "github-token-embedded": "ghp_" + _ALNUM36,
    "github-pat-embedded": "github_pat_" + _ALNUM36,
}


class TestBlockingPatterns:
    @pytest.mark.parametrize("reason", sorted(_POSITIVE_TOKENS))
    def test_each_pattern_blocks_its_token(self, reason: str) -> None:
        """Plan M1-T9, premortem R4: one positive test per table entry."""
        token = _POSITIVE_TOKENS[reason]

        reasons = _reasons(f"here is the value {token} in prose")

        assert reason in reasons

    def test_the_table_and_the_positive_fixtures_cover_the_same_names(self) -> None:
        """Plan M1-T9: a new table entry needs a fixture, a removed one drops its fixture."""
        assert {name for name, _ in scan.BLOCKING_PATTERNS} == set(_POSITIVE_TOKENS)

    @pytest.mark.parametrize("name", ["xoxa", "xoxp", "xoxr"])
    def test_slack_variants_abpr_are_blocked(self, name: str) -> None:
        """Plan M1-T9: xox[abpr]- all match."""
        assert "slack-token" in _reasons(f"{name}-1234567890-abcdef")

    @pytest.mark.parametrize("prefix", ["ghs", "gho", "ghu", "ghr"])
    def test_every_github_token_family_is_blocked_after_an_underscore(self, prefix: str) -> None:
        """Plan M1-T9: `\\b` fails after `_`, so TOKEN_ghp_... slipped past the base rule."""
        assert "github-token-embedded" in _reasons(f"GITHUB_TOKEN_{prefix}_{_ALNUM36}")

    def test_underscore_prefixed_token_is_missed_by_the_base_redactor(self) -> None:
        """Plan M1-T9: documents why the embedded pattern exists, so removing it is visible."""
        text = f"MY_TOKEN_ghp_{_ALNUM36}"

        assert "github-token" not in redact(text).reasons
        assert "github-token-embedded" in _reasons(text)

    @pytest.mark.parametrize(
        "prose",
        [
            "use sk-learn for this",
            "the task-ant problem",
            "sk-learn-compatible-estimator-api is fine",
            "mask-anthropic-keys-in-logs",
            "run npm_install again",
            "AIza is a prefix",
            "glpat-short",
            "SG.something and SG.other",
            "ask-anything-about-sk",
            "xoxo hugs",
        ],
    )
    def test_prose_that_resembles_a_prefix_is_not_blocked(self, prose: str) -> None:
        """Plan M1-T9, premortem R4: no false positive on ordinary text."""
        assert _reasons(prose) == []


class TestRedactCiSinkReasons:
    def test_credential_assignment_blocks(self) -> None:
        """Plan M1-T9: assignment redaction is on, so `password = value` blocks."""
        assert "credential-assignment" in _reasons("password = hunter2hunter2")

    def test_url_credential_blocks(self) -> None:
        """Plan M1-T9: a URL with user:password blocks."""
        assert "url-credential" in _reasons("clone https://user:pw12345@example.com/repo.git")

    def test_authorization_header_blocks(self) -> None:
        """Plan M1-T9: an Authorization wrapper blocks."""
        blocking = _reasons("Authorization: Bearer abcdefgh12345678")

        assert blocking

    def test_plain_code_is_clean(self) -> None:
        """Plan M1-T9: no reason, no block."""
        assert _reasons("x = compute(1)\nreturn x") == []


class TestHexRules:
    def test_a_40_hex_git_sha_is_reported_not_blocked(self) -> None:
        """Plan M1-T9, premortem R4: only a 40 hex run counts as a git object id."""
        result = scan.scan_secrets([_row("R", f"see commit {'a' * 40}")])

        assert result.blocking == {}
        assert result.hex_reported == ["R"]

    @pytest.mark.parametrize("length", [32, 33, 39, 41, 63, 64, 65, 128])
    def test_other_hex_lengths_block(self, length: int) -> None:
        """Plan M1-T9: any other 32+ hex run is blocked."""
        assert _reasons(f"value {'b' * length}") == ["hex-secret"]

    def test_one_odd_run_blocks_a_row_that_also_holds_a_sha(self) -> None:
        """Plan M1-T9: every hex run must be exactly 40."""
        assert _reasons(f"{'a' * 40} and {'c' * 33}") == ["hex-secret"]

    def test_allow_list_lets_a_named_row_through_and_reports_it(self) -> None:
        """Plan M1-T9: --allow-hex-rows names a row whose odd-length hex was reviewed."""
        rows = [_row("OK1", f"x {'d' * 36}"), _row("BAD", f"y {'e' * 36}")]

        result = scan.scan_secrets(rows, allow_hex_rows=frozenset({"OK1"}))

        assert set(result.blocking) == {"BAD"}
        assert "OK1" in result.hex_reported

    def test_allow_list_never_excuses_a_non_hex_reason(self) -> None:
        """Plan M1-T9: the allowance is for hex only."""
        row = _row("R", f"{'f' * 36} and ghp_{_ALNUM36}")

        result = scan.scan_secrets([row], allow_hex_rows=frozenset({"R"}))

        assert "github-token-embedded" in result.blocking["R"]
        assert "hex-secret" not in result.blocking["R"]

    @pytest.mark.parametrize("length", [31, 32, 33, 40, 64, 65])
    def test_hex_run_pattern_agrees_with_the_redactor(self, length: int) -> None:
        """Plan M1-T9: the local hex-run pattern flags exactly what redact() flags."""
        text = f"pre {'a' * length} post"

        local = len(scan.HEX_RUN.findall(text))
        canonical = redact(text).reasons.count("hex-secret")

        assert local == canonical


class TestParseAllowHexRows:
    def test_splits_trims_and_drops_empty_items(self) -> None:
        """Plan M1-T9: ID[,ID...] with stray spaces and commas."""
        assert scan.parse_allow_hex_rows("A, B ,,C,") == frozenset({"A", "B", "C"})

    def test_empty_text_is_an_empty_set(self) -> None:
        """Plan M1-T9: the default is no allowance."""
        assert scan.parse_allow_hex_rows("") == frozenset()


class TestScanScope:
    def test_body_replies_and_hunk_are_all_scanned(self) -> None:
        """Plan M1-T9: a secret in any of the three fields blocks."""
        token = "ghp_" + _ALNUM36
        for field in ("body", "reply", "hunk"):
            row = _row("R", "clean")
            if field == "body":
                row["body"] = token
            elif field == "reply":
                row["thread_replies"] = [token]
            else:
                row["diff_hunk"] = token

            assert scan.scan_secrets([row]).blocking, field

    def test_hunk_is_skipped_when_not_requested(self) -> None:
        """Plan M1-T9: predict sends no hunk, so it scans none."""
        row = _row("R", "clean", diff_hunk="ghp_" + _ALNUM36)

        result = scan.scan_secrets([row], include_hunk=False)

        assert result.blocking == {}
        assert result.hunks_scanned == 0

    def test_counts_rows_and_non_null_hunks(self) -> None:
        """Plan M1-T9: the report states how much was examined."""
        rows = [_row("A", "x", diff_hunk="@@"), _row("B", "y"), _row("C", "z", diff_hunk="@@ 2")]

        result = scan.scan_secrets(rows)

        assert (result.rows_scanned, result.hunks_scanned) == (3, 2)


class TestReportScan:
    def test_prints_the_count_line_on_a_clean_scan(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T9: the examined count prints even with zero findings."""
        ok = scan.report_scan(scan.scan_secrets([_row("A", "x", diff_hunk="@@")]))

        assert ok is True
        assert "scanned 1 rows (+1 hunks): blocking 0, hex-reported 0" in capsys.readouterr().err

    def test_prints_blocking_rows_reasons_and_count_never_the_text(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T9: row id and reason names only."""
        token = "ghp_" + _ALNUM36
        result = scan.scan_secrets([_row("BADROW", token), _row("FINE", "x")])

        ok = scan.report_scan(result)

        err = capsys.readouterr().err
        assert ok is False
        assert "BADROW" in err
        assert "github-token" in err
        assert token not in err
        assert "blocking 1, hex-reported 0" in err

    def test_lists_hex_reported_rows(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Plan M1-T9: hex-only rows are named for review."""
        ok = scan.report_scan(scan.scan_secrets([_row("SHA1", "c" * 40)]))

        err = capsys.readouterr().err
        assert ok is True
        assert "review: hex-like strings in rows SHA1" in err
        assert "hex-reported 1" in err


class TestSampleCliAllowance:
    def _prs(self, tmp_path: Path, body: str) -> Path:
        node = make_node("PRRC_HEX", body)
        return write_prs(tmp_path / "prs.json", [make_pr(1, make_thread(node))])

    def _argv(self, prs: Path, out: Path, *extra: str) -> list[str]:
        return [
            "sample",
            "--prs",
            str(prs),
            "--output",
            str(out),
            "--band-count",
            "2",
            "--outside-count",
            "0",
            "--dev-count",
            "0",
            *extra,
        ]

    def test_odd_length_hex_blocks_sample_with_exit_one(self, tmp_path: Path) -> None:
        """Plan M1-T9: a 36-char hex run is not a git id, so sample exits 1."""
        prs = self._prs(tmp_path, f"Consider a helper {'a' * 36}")
        out = tmp_path / "corpus.jsonl"

        assert cc.main(self._argv(prs, out)) == 1
        assert not out.exists()

    def test_allow_hex_rows_lets_the_named_row_through(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T9: --allow-hex-rows PRRC_HEX makes the same input exit 0."""
        prs = self._prs(tmp_path, f"Consider a helper {'a' * 36}")
        out = tmp_path / "corpus.jsonl"

        code = cc.main(self._argv(prs, out, "--allow-hex-rows", "PRRC_HEX"))

        assert code == 0
        assert read_rows(out)[0]["id"] == "PRRC_HEX"
        assert "review: hex-like strings in rows PRRC_HEX" in capsys.readouterr().err

    def test_clean_sample_still_prints_the_scan_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T9: the count line prints on a clean run too."""
        prs = write_prs(tmp_path / "prs.json", corpus_prs(band=2, outside=0))

        code = cc.main(self._argv(prs, tmp_path / "o.jsonl"))

        assert code == 0
        assert "scanned 2 rows (+0 hunks): blocking 0, hex-reported 0" in capsys.readouterr().err
        assert FROZEN_NOW


class TestFetchHunksCliAllowance:
    def test_allow_hex_rows_applies_to_a_hunk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan M1-T9: fetch-hunks takes the same --allow-hex-rows flag."""
        from tests.eval._actionability_corpus_test_support import (
            FakeGraphql,
            corpus_row,
            write_corpus,
        )

        monkeypatch.setattr(cc, "gh_graphql", FakeGraphql({"A": f"@@\n+# {'9' * 36}"}))
        corpus = write_corpus(tmp_path / "c.jsonl", [corpus_row("A")])
        argv = ["fetch-hunks", "--corpus", str(corpus), "--output", str(tmp_path / "o.jsonl")]

        assert cc.main(argv) == 1
        assert cc.main([*argv, "--allow-hex-rows", "A"]) == 0
