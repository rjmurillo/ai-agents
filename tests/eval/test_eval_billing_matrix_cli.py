"""Tests for `scripts/eval/eval_billing_matrix.py` and the copilot/api cell.

Offline: readiness is an environment and PATH check, and the copilot/api
provider is built without a client, so nothing here reaches a network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
_ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(_EVAL_DIR))
try:
    import _providers
    import eval_billing_matrix as cli
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH

_ALL_CREDENTIAL_VARS = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CODEX_ACCESS_TOKEN",
    "COPILOT_API_BASE_URL",
    "COPILOT_API_HEADERS",
    "COPILOT_API_KEY",
    "GITHUB_COPILOT_TOKEN",
    "OPENAI_API_KEY",
)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ALL_CREDENTIAL_VARS:
        monkeypatch.delenv(name, raising=False)
    for name in ("CLAUDE_CLI_BIN", "CODEX_CLI_BIN", "COPILOT_CLI_BIN"):
        monkeypatch.delenv(name, raising=False)


def _rows(capsys: pytest.CaptureFixture[str], *argv: str) -> list[dict[str, Any]]:
    assert cli.main(["--json", *argv]) == cli.EXIT_OK
    return json.loads(capsys.readouterr().out)["cells"]


# --- Listing ------------------------------------------------------------


def test_default_listing_covers_all_six_cells(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rows = _rows(capsys)

    assert len(rows) == 6
    assert {row["harness"] for row in rows} == {"claude", "codex", "copilot"}


def test_text_output_renders_the_table_and_a_readiness_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main([]) == cli.EXIT_OK

    out = capsys.readouterr().out
    assert "| Harness | Billing |" in out
    assert "Readiness on this machine:" in out
    assert "claude-subscription:" in out


def test_a_harness_filter_returns_that_column(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rows = _rows(capsys, "--harness", "codex")

    assert {row["cell"] for row in rows} == {"codex-api", "codex-subscription"}


def test_a_billing_filter_returns_that_row(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rows = _rows(capsys, "--billing", "subscription")

    assert len(rows) == 3
    assert all(row["cost_basis"] == "requests" for row in rows)


def test_both_axes_select_exactly_one_cell(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rows = _rows(capsys, "--harness", "claude", "--billing", "api")

    assert [row["cell"] for row in rows] == ["claude-api"]


def test_a_provider_name_selects_its_cell(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rows = _rows(capsys, "--provider", "anthropic-sdk")

    assert [row["cell"] for row in rows] == ["claude-api"]


def test_a_conflicting_selection_exits_config(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        ["--provider", "copilot-cli", "--harness", "claude", "--billing", "api"]
    )

    assert exit_code == cli.EXIT_CONFIG
    assert "error:" in capsys.readouterr().err


def test_an_unknown_provider_exits_config(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--provider", "gemini"]) == cli.EXIT_CONFIG
    assert "error:" in capsys.readouterr().err


def test_an_unknown_harness_is_rejected_by_argparse() -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--harness", "gemini"])

    assert excinfo.value.code == 2


# --- Readiness ----------------------------------------------------------


def test_a_missing_credential_is_not_ready(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rows = _rows(capsys, "--harness", "claude", "--billing", "api")

    assert rows[0]["readiness"] == cli.NOT_READY
    assert "ANTHROPIC_API_KEY" in rows[0]["missing"][0]


def test_a_present_credential_is_ready(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    rows = _rows(capsys, "--harness", "claude", "--billing", "api")

    assert rows[0]["readiness"] == cli.READY
    assert rows[0]["missing"] == []


def test_every_missing_requirement_is_reported_not_just_the_first(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    rows = _rows(capsys, "--harness", "copilot", "--billing", "api")

    missing = " ".join(str(item) for item in rows[0]["missing"])
    assert "COPILOT_API_KEY" in missing
    assert "COPILOT_API_BASE_URL" in missing


def test_an_uninstalled_cli_is_not_ready(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    rows = _rows(capsys, "--harness", "copilot", "--billing", "subscription")

    assert rows[0]["readiness"] == cli.NOT_READY
    assert "copilot is not on PATH" in rows[0]["missing"]


def test_an_executable_override_is_the_one_checked(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("COPILOT_CLI_BIN", "/opt/copilot-nightly")
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    rows = _rows(capsys, "--harness", "copilot", "--billing", "subscription")

    assert "/opt/copilot-nightly is not on PATH" in rows[0]["missing"]


def test_an_optional_credential_with_the_cli_present_is_unknown_not_ready(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `codex login` on disk is invisible here; do not claim it is absent."""
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/codex")

    rows = _rows(capsys, "--harness", "codex", "--billing", "subscription")

    assert rows[0]["readiness"] == cli.UNKNOWN
    assert "does not read" in rows[0]["missing"][0]


def test_require_ready_exits_external_on_a_missing_requirement(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(["--harness", "claude", "--billing", "api", "--require-ready"])

    assert exit_code == cli.EXIT_EXTERNAL
    assert "not ready" in capsys.readouterr().err


def test_require_ready_passes_when_the_credential_is_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    assert (
        cli.main(["--harness", "claude", "--billing", "api", "--require-ready"])
        == cli.EXIT_OK
    )


def test_require_ready_does_not_fail_on_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable on-disk login is not evidence of a missing one."""
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/codex")

    exit_code = cli.main(
        ["--harness", "codex", "--billing", "subscription", "--require-ready"]
    )

    assert exit_code == cli.EXIT_OK


# --- The copilot/api provider it reports on -----------------------------


def test_copilot_api_refuses_without_a_base_url() -> None:
    with pytest.raises(RuntimeError, match="no default endpoint"):
        _providers.resolve_provider("copilot-api")


def test_copilot_api_uses_the_operator_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COPILOT_API_BASE_URL", "https://gateway.example/v1")

    provider = _providers.resolve_provider("copilot-api")

    assert provider.name == "copilot-api"
    assert provider._base_url == "https://gateway.example/v1"
    assert provider._default_headers is None


def test_copilot_api_forwards_operator_supplied_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COPILOT_API_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("COPILOT_API_HEADERS", '{"Copilot-Integration-Id": "vscode"}')

    provider = _providers.resolve_provider("copilot-api")

    assert provider._default_headers == {"Copilot-Integration-Id": "vscode"}


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '{"a": 1}', '"header"'])
def test_copilot_api_refuses_malformed_headers(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("COPILOT_API_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("COPILOT_API_HEADERS", raw)

    with pytest.raises(RuntimeError, match="JSON object"):
        _providers.resolve_provider("copilot-api")
