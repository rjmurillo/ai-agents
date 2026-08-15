"""The bot identity diagnostic separates MATCH from MISMATCH from UNKNOWN.

Issue #4607: ``BOT_PAT`` held a token for the human account and no run log
could show it. The diagnostic must report the resolved identity loudly, must
never report a failed probe as a pass, and in strict mode must exit nonzero
from ``main()`` so a blocking step actually blocks.
"""

from __future__ import annotations

import pytest

from scripts.ci.check_bot_identity import (
    EXIT_AUTH,
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    ProbeResult,
    main,
    probe_user,
)

BOT_ID = "250269933"
HUMAN_ID = "6811113"


def _probe(result: ProbeResult):
    def probe(token: str, api_url: str) -> ProbeResult:
        assert token, "probe must never be called without a token"
        return result

    return probe


def _bot() -> ProbeResult:
    return ProbeResult(ok=True, login="rjmurillo-bot", account_id=BOT_ID)


def _human() -> ProbeResult:
    return ProbeResult(ok=True, login="rjmurillo", account_id=HUMAN_ID)


def _failed(error: str) -> ProbeResult:
    return ProbeResult(ok=False, error=error)


class TestMatch:
    def test_expected_bot_id_exits_zero_and_names_the_identity(self, capsys):
        rc = main([], probe=_probe(_bot()), environ={"IDENTITY_TOKEN": "tok"})

        out = capsys.readouterr().out
        assert rc == EXIT_OK
        assert "MATCH" in out
        assert "rjmurillo-bot" in out
        assert BOT_ID in out

    def test_match_never_prints_the_token(self, capsys):
        main([], probe=_probe(_bot()), environ={"IDENTITY_TOKEN": "ghp_secret123"})

        assert "ghp_secret123" not in capsys.readouterr().out


class TestMismatch:
    def test_wrong_account_warns_but_does_not_block_by_default(self, capsys):
        rc = main([], probe=_probe(_human()), environ={"IDENTITY_TOKEN": "tok"})

        out = capsys.readouterr().out
        assert rc == EXIT_OK
        assert "::warning::" in out
        assert "MISMATCH" in out
        assert HUMAN_ID in out
        assert "4607" in out

    def test_wrong_account_in_strict_mode_exits_nonzero_from_main(self, capsys):
        rc = main(
            [],
            probe=_probe(_human()),
            environ={"IDENTITY_TOKEN": "tok", "IDENTITY_STRICT": "true"},
        )

        out = capsys.readouterr().out
        assert rc == EXIT_AUTH
        assert rc != 0
        assert "::error::" in out

    def test_mismatch_tells_the_owner_what_to_do(self, capsys):
        main([], probe=_probe(_human()), environ={"IDENTITY_TOKEN": "tok"})

        out = capsys.readouterr().out
        assert "rjmurillo-bot" in out
        assert "repository secret" in out


class TestProbeFailure:
    @pytest.mark.parametrize(
        "error",
        [
            "HTTP 401 from /user",
            "HTTP 403 from /user",
            "network error: timed out",
            "/user payload missing login or id",
        ],
    )
    def test_failed_probe_is_unknown_never_a_match(self, error, capsys):
        rc = main([], probe=_probe(_failed(error)), environ={"IDENTITY_TOKEN": "tok"})

        out = capsys.readouterr().out
        assert rc == EXIT_OK
        assert "UNKNOWN" in out
        assert "not a pass" in out
        assert "MATCH:" not in out

    def test_failed_probe_in_strict_mode_exits_external(self):
        rc = main(
            [],
            probe=_probe(_failed("HTTP 500 from /user")),
            environ={"IDENTITY_TOKEN": "tok", "IDENTITY_STRICT": "1"},
        )

        assert rc == EXIT_EXTERNAL
        assert rc != 0


class TestMissingToken:
    def test_empty_token_reports_missing_without_probing(self, capsys):
        def exploding_probe(token: str, api_url: str) -> ProbeResult:
            raise AssertionError("probe must not run without a token")

        rc = main([], probe=exploding_probe, environ={})

        out = capsys.readouterr().out
        assert rc == EXIT_OK
        assert "MISSING" in out

    def test_empty_token_in_strict_mode_is_a_config_error(self):
        rc = main([], probe=_probe(_bot()), environ={"IDENTITY_STRICT": "true"})

        assert rc == EXIT_CONFIG
        assert rc != 0


class TestConfiguration:
    def test_non_numeric_expected_id_is_a_config_error(self):
        rc = main(
            [],
            probe=_probe(_bot()),
            environ={"IDENTITY_TOKEN": "tok", "EXPECTED_BOT_ID": "not-a-number"},
        )

        assert rc == EXIT_CONFIG

    def test_arguments_are_rejected(self):
        assert main(["--unexpected"]) == EXIT_CONFIG

    def test_custom_expected_id_wins_over_default(self, capsys):
        rc = main(
            [],
            probe=_probe(_human()),
            environ={"IDENTITY_TOKEN": "tok", "EXPECTED_BOT_ID": HUMAN_ID},
        )

        assert rc == EXIT_OK
        assert "MATCH" in capsys.readouterr().out


class TestGithubSurfaces:
    def test_verdict_lands_in_step_summary_and_output(self, tmp_path):
        summary = tmp_path / "summary.md"
        output = tmp_path / "output.txt"

        main(
            [],
            probe=_probe(_human()),
            environ={
                "IDENTITY_TOKEN": "tok",
                "GITHUB_STEP_SUMMARY": str(summary),
                "GITHUB_OUTPUT": str(output),
            },
        )

        assert "MISMATCH" in summary.read_text(encoding="utf-8")
        assert "identity_verdict=MISMATCH" in output.read_text(encoding="utf-8")

    def test_no_summary_files_written_when_env_unset(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        rc = main([], probe=_probe(_bot()), environ={"IDENTITY_TOKEN": "tok"})

        assert rc == EXIT_OK
        assert list(tmp_path.iterdir()) == []


class TestProbeUser:
    def test_probe_returns_unknown_on_connection_refused(self):
        result = probe_user("tok", api_url="https://127.0.0.1:9")

        assert not result.ok
        assert "network error" in result.error

    @pytest.mark.parametrize("url", ["http://api.github.com", "file:///etc/passwd", "ftp://x"])
    def test_probe_refuses_non_https_schemes_without_opening(self, url):
        result = probe_user("tok", api_url=url)

        assert not result.ok
        assert "non-https" in result.error
