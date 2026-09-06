"""Codex coverage for the runtime-parity evaluator (issue #5423 reopen).

`_runtime_parity.runtime_env` and `probe_version` branched only on "claude"
and "copilot" before this change, so `runtime_env(workspace, "codex")` raised
`KeyError: 'codex'` from the `authentication[harness]` lookup, and any call to
`probe_version` for codex failed the same way (it builds its env through
`runtime_env`). Every test here was run against that pre-fix code and failed
with `KeyError`; each now passes. See the session report for the exact
pre-fix output.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.eval._runtime_parity_test_support import parity

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _version_runner(stdout: str = "codex-cli 0.34.0\n", *, returncode: int = 0) -> Runner:
    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        return subprocess.CompletedProcess(args, returncode, stdout, "")

    return runner


# --- Positive: the codex profile builds ---------------------------------------


def test_runtime_env_builds_isolated_codex_profile(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", "/operator/home")
    workspace = tmp_path / "codex"
    workspace.mkdir()

    env = parity.runtime_env(workspace, "codex")

    assert env["HOME"].startswith(str(workspace))
    assert env["CODEX_HOME"].startswith(str(workspace))
    assert Path(env["CODEX_HOME"]).is_dir()
    assert "/operator/home" not in env.values()


def test_codex_receives_only_its_own_credentials(tmp_path: Path, monkeypatch) -> None:
    credentials = {
        "ANTHROPIC_API_KEY": "anthropic",
        "COPILOT_GITHUB_TOKEN": "copilot",
        "CODEX_API_KEY": "codex-key",
        "CODEX_ACCESS_TOKEN": "codex-token",
    }
    for key, value in credentials.items():
        monkeypatch.setenv(key, value)
    workspace = tmp_path / "codex"
    workspace.mkdir()

    env = parity.runtime_env(workspace, "codex")

    assert env["CODEX_API_KEY"] == "codex-key"
    assert env["CODEX_ACCESS_TOKEN"] == "codex-token"
    assert "ANTHROPIC_API_KEY" not in env
    assert "COPILOT_GITHUB_TOKEN" not in env


def test_probe_version_parses_well_formed_codex_version(tmp_path: Path) -> None:
    runner = _version_runner("codex-cli 0.34.0\n")

    version = parity.probe_version(
        "codex", "codex", tmp_path / "probe", runner, 30
    )

    assert version == "codex-cli 0.34.0"


def test_probe_version_argv_for_codex_has_no_extra_flag(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def recording_runner(argv: list[str], **_kwargs: object):
        args = [str(value) for value in argv]
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "codex-cli 0.34.0\n", "")

    parity.probe_version("codex", "codex", tmp_path / "probe", recording_runner, 30)

    # Unlike copilot, which inserts "--no-auto-update", codex takes the bare
    # [executable, "--version"] argv.
    assert calls == [["codex", "--version"]]


# --- Edge: malformed codex version output fails closed -------------------------


def test_empty_codex_version_output_fails_closed(tmp_path: Path) -> None:
    runner = _version_runner("")

    with pytest.raises(RuntimeError, match="returned no version"):
        parity.probe_version("codex", "codex", tmp_path / "probe", runner, 30)


def test_nonzero_exit_codex_version_probe_fails_closed(tmp_path: Path) -> None:
    runner = _version_runner("", returncode=1)

    with pytest.raises(RuntimeError, match="--version failed"):
        parity.probe_version("codex", "codex", tmp_path / "probe", runner, 30)
