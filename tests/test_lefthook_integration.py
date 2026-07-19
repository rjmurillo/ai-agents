from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEFTHOOK = shutil.which("lefthook")
ACTIVE_REFERENCE_ROOTS = (
    "README.md",
    "CONTRIBUTING.md",
    ".config",
    "scripts",
    ".github",
    "docs",
    "templates",
    "build",
    ".claude",
    "src/claude",
    "src/copilot-cli",
    "src/vs-code-agents",
)
HISTORICAL_REFERENCE_PREFIXES = (
    ".claude/skills/ai-agents-failure-archaeology/references/",
    "src/copilot-cli/skills/ai-agents-failure-archaeology/references/",
)


@pytest.fixture(autouse=True)
def _isolate_git_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.delenv("GIT_CONFIG_PARAMETERS", raising=False)
    for name in tuple(os.environ):
        if name.startswith("GIT_CONFIG_") and name not in {
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_SYSTEM",
        }:
            monkeypatch.delenv(name, raising=False)


def _run(
    repo: Path,
    *args: str,
    stdin: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    assert LEFTHOOK is not None
    return subprocess.run(
        [LEFTHOOK, *args],
        cwd=repo,
        input=stdin,
        text=True,
        capture_output=True,
        check=check,
    )


def _init_repo(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
    )


def _write_payload(repo: Path, name: str, body: str) -> None:
    payload = repo / "scripts" / "hooks" / name
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    payload.chmod(0o755)


def _copy_config(repo: Path) -> None:
    shutil.copy2(PROJECT_ROOT / "lefthook.yml", repo / "lefthook.yml")


def _active_legacy_references() -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", *ACTIVE_REFERENCE_ROOTS],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    failures: list[str] = []
    for raw_path in tracked:
        if not raw_path:
            continue
        relative = raw_path.decode("utf-8")
        if relative.startswith(HISTORICAL_REFERENCE_PREFIXES):
            continue
        text = (PROJECT_ROOT / relative).read_text(encoding="utf-8", errors="replace")
        if ".githooks" in text or "install_git_hooks.py" in text:
            failures.append(relative)
    return failures


def test_configuration_is_thin() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    assert config == {
        "pre-commit": {
            "commands": {"repository-guardrails": {"run": "scripts/hooks/pre-commit"}}
        },
        "commit-msg": {
            "commands": {
                "message-dash-guard": {"run": 'scripts/hooks/commit-msg "{1}"'}
            }
        },
        "pre-push": {
            "commands": {
                "repository-guardrails": {
                    "run": "scripts/hooks/pre-push",
                    "use_stdin": True,
                }
            }
        },
    }


def test_no_active_legacy_hook_manager_references() -> None:
    assert not (PROJECT_ROOT / ".githooks").exists()
    assert not (PROJECT_ROOT / "scripts" / "install_git_hooks.py").exists()
    assert not (PROJECT_ROOT / "tests" / "test_install_git_hooks.py").exists()
    assert _active_legacy_references() == []


def test_install_resets_legacy_hooks_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _copy_config(repo)
    subprocess.run(
        ["git", "-C", str(repo), "config", "core.hooksPath", ".githooks"],
        check=True,
    )

    _run(repo, "install", "--reset-hooks-path")

    _run(repo, "check-install")
    hooks_path = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "core.hooksPath"],
        capture_output=True,
        text=True,
    )
    assert hooks_path.returncode == 1
    assert os.access(repo / ".git" / "hooks" / "pre-push", os.X_OK)


def test_dispatch_preserves_argument_stdin_and_exit_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _copy_config(repo)
    _write_payload(repo, "commit-msg", 'printf "%s" "$1" > commit-msg.arg')
    _write_payload(repo, "pre-push", "cat > pre-push.stdin")
    _write_payload(repo, "pre-commit", "exit 17")

    _run(repo, "run", "commit-msg", "message.txt", "--force")
    push_input = "refs/heads/main local refs/heads/main remote\n"
    _run(repo, "run", "pre-push", "--force", stdin=push_input)
    blocked = _run(repo, "run", "pre-commit", "--force", check=False)

    assert (repo / "commit-msg.arg").read_text(encoding="utf-8") == "message.txt"
    assert (repo / "pre-push.stdin").read_text(encoding="utf-8") == push_input
    assert blocked.returncode == 1
    assert "exit status 17" in blocked.stdout


def test_installed_hooks_work_from_linked_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    _init_repo(repo)
    _copy_config(repo)
    _write_payload(repo, "pre-commit", "exit 0")
    (repo / "tracked").write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-q", str(worktree), "-b", "other"],
        check=True,
    )

    _run(repo, "install", "--reset-hooks-path")

    _run(worktree, "check-install")
    _run(worktree, "run", "pre-commit", "--force")
