"""Tests for the ai-agents-build-and-env skill script env_probe.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/ai-agents-build-and-env/scripts/env_probe.py"
spec = importlib.util.spec_from_file_location("env_probe", SCRIPT)
assert spec is not None and spec.loader is not None
env_probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(env_probe)


def make_repo(tmp_path: Path, *, drop: str | None = None) -> Path:
    files = {
        ".python-version": "3.99.1\n",
        "pyproject.toml": 'requires-python = ">=3.99"\n  "PyYAML==9.9.9",\n  "lefthook==8.8.8",\n',
        "scripts/bootstrap-vm.sh": "    NODE_MAJOR=77\n",
        "scripts/validation/validate_python_syntax.py": "_SUPPORT_FLOOR = (3, 9)\n",
        ".env.example": "# header\nFOO_KEY=x\n# BAR_KEY=y\nFOO_KEY=dup\n",
    }
    for rel, text in files.items():
        if rel == drop:
            continue
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (tmp_path / ".serena/memories").mkdir(parents=True)
    (tmp_path / ".serena/memories/a.md").write_text("x")
    (tmp_path / ".serena/memories/.hidden").write_text("x")
    return tmp_path


def test_ai_agents_build_and_env_pins_positive(tmp_path, capsys):
    repo = make_repo(tmp_path)
    assert env_probe.main(["--repo", str(repo), "pins"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["pins"] == {
        "python": "3.99.1",
        "requires_python": ">=3.99",
        "pyyaml": "9.9.9",
        "lefthook": "8.8.8",
        "node_major": "77",
        "syntax_floor": "3.9",
        "serena_memory_entries": 1,
    }
    assert out["examined"] == 7


def test_pins_missing_source_exits_2(tmp_path, capsys):
    repo = make_repo(tmp_path, drop=".python-version")
    assert env_probe.main(["--repo", str(repo), "pins"]) == 2
    assert "missing source file" in capsys.readouterr().out


def test_pins_pattern_absent_exits_2(tmp_path, capsys):
    repo = make_repo(tmp_path)
    (repo / "scripts/bootstrap-vm.sh").write_text("nothing\n")
    assert env_probe.main(["--repo", str(repo), "pins"]) == 2


def test_bad_repo_and_bad_command_exit_2(tmp_path):
    assert env_probe.main(["--repo", str(tmp_path / "nope"), "pins"]) == 2
    assert env_probe.main(["bogus"]) == 2


def test_envfile_keys_and_untracked(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path)
    monkeypatch.setattr(env_probe, "_git_ls_files", lambda r, rel: [])
    assert env_probe.main(["--repo", str(repo), "envfile"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["example_keys"] == ["FOO_KEY"]
    assert out["commented_keys"] == ["BAR_KEY"]
    assert out["env_exists"] is False and out["tracked_env"] is False


def test_envfile_tracked_env_exits_1(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path)
    monkeypatch.setattr(env_probe, "_git_ls_files", lambda r, rel: [".env"])
    assert env_probe.main(["--repo", str(repo), "envfile"]) == 1
    assert json.loads(capsys.readouterr().out)["tracked_env"] is True


def test_git_missing_exits_3(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path)

    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(env_probe.subprocess, "run", boom)
    assert env_probe.main(["--repo", str(repo), "envfile"]) == 3


def _fake_run(lefthook="8.8.8", check_rc=0, collected="28 tests collected in 0.1s"):
    def run(cmd, **kwargs):
        if cmd[-1] == "version":
            return subprocess.CompletedProcess(cmd, 0, lefthook + "\n", "")
        if cmd[-1] == "check-install":
            return subprocess.CompletedProcess(cmd, check_rc, "", "")
        return subprocess.CompletedProcess(cmd, 0, collected + "\n", "")

    return run


def test_smoke_all_ok(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path)
    monkeypatch.setattr(env_probe.subprocess, "run", _fake_run())
    assert env_probe.main(["--repo", str(repo), "smoke"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["examined"] == 3 and out["results"][2]["value"] == 28


def test_smoke_lefthook_mismatch_exits_1(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    monkeypatch.setattr(env_probe.subprocess, "run", _fake_run(lefthook="1.0.0"))
    assert env_probe.main(["--repo", str(repo), "smoke"]) == 1


def test_smoke_uv_missing_exits_3(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)

    def boom(*a, **k):
        raise FileNotFoundError("uv")

    monkeypatch.setattr(env_probe.subprocess, "run", boom)
    assert env_probe.main(["--repo", str(repo), "smoke"]) == 3


def test_help_exits_0():
    assert env_probe.main(["--help"]) == 0


def test_real_repo_pins_resolve():
    assert env_probe.read_pins(ROOT)["python"] == (ROOT / ".python-version").read_text().strip()


@pytest.mark.parametrize("cmd", ["pins"])
def test_cli_runs(cmd):
    argv = ["python3", str(SCRIPT), "--repo", str(ROOT), cmd]
    proc = subprocess.run(argv, capture_output=True, text=True)
    assert proc.returncode == 0 and "examined" in proc.stdout
