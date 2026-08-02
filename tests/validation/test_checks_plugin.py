from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import checks_plugin


def test_workflow_local_run_warns_on_missing_local_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = tmp_path
    script = repo_root / "scripts" / "validation" / "run_workflow_local_test.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('stub')\n", encoding="utf-8")

    workflow = repo_root / ".github" / "workflows" / "secret.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: secret\n", encoding="utf-8")

    monkeypatch.setattr(checks_plugin, "_resolve_default_base_ref", lambda _root: "origin/main")

    def fake_run_subprocess(args: list[str], *_, **__) -> tuple[int, str, str]:
        if args[:4] == ["git", "-C", str(repo_root), "diff"]:
            return 0, ".github/workflows/secret.yml\n", ""
        return 4, "unrunnable-locally: actionlint passed\n", ""

    monkeypatch.setattr(checks_plugin, "_run_subprocess", fake_run_subprocess)

    assert checks_plugin.validate_workflow_local_run(repo_root) is True

    output = capsys.readouterr().out
    assert "unrunnable-locally: actionlint passed" in output
    assert "workflow local-run auth material unavailable locally" in output


def _lines(paths: list[str]) -> str:
    return "".join(f"{path}\n" for path in paths)


def _install_workflow_gate(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    committed: list[str] | None = None,
    staged: list[str] | None = None,
    unstaged: list[str] | None = None,
    untracked: list[str] | None = None,
    on_disk: list[str] | None = None,
) -> dict[str, list[str] | None]:
    """Stub the runner script, git sources, and capture the runner's --files.

    Files listed in ``on_disk`` are created so ``is_file`` keeps them; any path
    named in a source but absent from ``on_disk`` acts as a deleted path.
    """
    script = repo_root / "scripts" / "validation" / "run_workflow_local_test.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("print('stub')\n", encoding="utf-8")

    for rel in on_disk or []:
        target = repo_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("name: wf\n", encoding="utf-8")

    monkeypatch.setattr(checks_plugin, "_resolve_default_base_ref", lambda _root: "origin/main")

    captured: dict[str, list[str] | None] = {"files": None}

    def fake_run_subprocess(args: list[str], *_: object, **__: object) -> tuple[int, str, str]:
        if args and args[0] == "git":
            if "ls-files" in args:
                return 0, _lines(untracked or []), ""
            if "--cached" in args:
                return 0, _lines(staged or []), ""
            if any(str(arg).endswith("...HEAD") for arg in args):
                return 0, _lines(committed or []), ""
            return 0, _lines(unstaged or []), ""
        if "--files" in args:
            captured["files"] = args[args.index("--files") + 1 :]
        return 0, "", ""

    monkeypatch.setattr(checks_plugin, "_run_subprocess", fake_run_subprocess)
    return captured


def test_workflow_local_run_detects_committed_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = ".github/workflows/committed.yml"
    captured = _install_workflow_gate(
        tmp_path, monkeypatch, committed=[workflow], on_disk=[workflow]
    )

    assert checks_plugin.validate_workflow_local_run(tmp_path) is True
    assert captured["files"] == [workflow]


def test_workflow_local_run_detects_staged_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = ".github/workflows/staged.yml"
    captured = _install_workflow_gate(
        tmp_path, monkeypatch, staged=[workflow], on_disk=[workflow]
    )

    assert checks_plugin.validate_workflow_local_run(tmp_path) is True
    assert captured["files"] == [workflow]


def test_workflow_local_run_detects_unstaged_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = ".github/workflows/unstaged.yml"
    captured = _install_workflow_gate(
        tmp_path, monkeypatch, unstaged=[workflow], on_disk=[workflow]
    )

    assert checks_plugin.validate_workflow_local_run(tmp_path) is True
    assert captured["files"] == [workflow]


def test_workflow_local_run_detects_untracked_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = ".github/workflows/untracked.yml"
    captured = _install_workflow_gate(
        tmp_path, monkeypatch, untracked=[workflow], on_disk=[workflow]
    )

    assert checks_plugin.validate_workflow_local_run(tmp_path) is True
    assert captured["files"] == [workflow]


def test_workflow_local_run_skips_deleted_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = ".github/workflows/live.yml"
    gone = ".github/workflows/gone.yml"
    captured = _install_workflow_gate(
        tmp_path, monkeypatch, committed=[live, gone], on_disk=[live]
    )

    assert checks_plugin.validate_workflow_local_run(tmp_path) is True
    assert captured["files"] == [live]


def test_workflow_local_run_dedupes_across_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = ".github/workflows/dup.yml"
    captured = _install_workflow_gate(
        tmp_path,
        monkeypatch,
        committed=[workflow],
        staged=[workflow],
        unstaged=[workflow],
        on_disk=[workflow],
    )

    assert checks_plugin.validate_workflow_local_run(tmp_path) is True
    assert captured["files"] == [workflow]


def test_workflow_local_run_fast_skips_when_no_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured = _install_workflow_gate(tmp_path, monkeypatch)

    assert checks_plugin.validate_workflow_local_run(tmp_path) is True
    assert captured["files"] is None
    assert "No changed workflow files" in capsys.readouterr().out


def test_agent_content_parity_decodes_subprocess_output_with_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "build" / "scripts" / "check_agent_content_parity.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('stub')\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(checks_plugin.subprocess, "run", fake_run)

    assert checks_plugin.validate_agent_content_parity(tmp_path) is True
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
