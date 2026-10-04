"""The capability probe never copies, links, or reads a credential file."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.eval._harness_capability_test_support import UNPROBED_MATRIX, cli

_SCRIPTS = Path(str(cli.__file__)).resolve().parent
_SOURCES = (
    _SCRIPTS / "eval_harness_capability.py",
    _SCRIPTS / "_runtime_harness.py",
    _SCRIPTS / "_durable_live.py",
    _SCRIPTS / "eval_durable_live.py",
    _SCRIPTS / "_routing_live.py",
)
_FORBIDDEN = (
    "auth.json",
    ".credentials.json",
    "copyfileobj",
    "copyfile",
    "symlink_to",
    "O_NOFOLLOW",
)


@pytest.fixture(autouse=True)
def _start_from_the_unprobed_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "DEFAULT_MATRIX", UNPROBED_MATRIX)


def test_the_parser_rejects_the_codex_auth_file_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--codex-auth-file", "somewhere"])

    assert exit_info.value.code == 2
    assert "--codex-auth-file" in capsys.readouterr().err


@pytest.mark.parametrize("source", _SOURCES, ids=lambda path: path.name)
@pytest.mark.parametrize("token", _FORBIDDEN)
def test_probe_sources_hold_no_credential_handling(source: Path, token: str) -> None:
    assert token not in source.read_text(encoding="utf-8")


def test_a_codex_probe_leaves_no_credential_in_the_isolated_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = tmp_path / "probes.json"
    plan.write_text(
        json.dumps(
            {
                "probes": [
                    {
                        "harness": "codex",
                        "capability": "effort_override",
                        "parent_value": "medium",
                        "child_value": "low",
                        "argv": ["codex", "exec", "--json", "-m", "gpt-5.6-sol"],
                        "request_flag": "-c",
                        "env": {"RUST_LOG": "tungstenite::protocol=trace"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli.shutil, "which", lambda name: f"/bin/{name}" if name == "codex" else None
    )
    frame = '{"type":"response.completed","response":{"reasoning":{"effort":"low"}}}'
    homes: list[list[str]] = []  # entry names seen under CODEX_HOME during the probe
    links: list[str] = []  # symlinks of any name seen under CODEX_HOME during the probe

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, "codex-cli 0.156.0", "")
        env = kwargs.get("env")
        assert isinstance(env, dict)
        home = Path(str(env["CODEX_HOME"]))
        homes.append(sorted(path.name for path in home.rglob("*")))
        links.extend(path.name for path in home.rglob("*") if path.is_symlink())
        stdout = json.dumps({"type": "turn.completed", "data": {"usage": {}}}) + "\n"
        return subprocess.CompletedProcess(
            args, 0, stdout, f"TRACE tungstenite::protocol: Received message {frame}\n"
        )

    code = cli.main(
        ["--output", str(tmp_path / "report.json"), "--behavioral-probes", str(plan)],
        runner=runner,
    )

    assert code == 0
    assert len(homes) == 1
    assert "auth.json" not in homes[0]
    assert links == []
