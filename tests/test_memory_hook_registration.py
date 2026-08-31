"""The three memory hooks are registered and run under the real contract.

Issue #4011: the hooks existed and were tested, but nothing invoked them, so
no confidence score was ever written outside pytest. These tests pin both
halves: the registration in .claude/settings.json, and the exit code each
invoker returns when Claude Code pipes it a real payload.

The invokers run as subprocesses launched with the command string from
settings.json, not with sys.executable. Under pytest sys.executable is the uv
virtualenv, which carries python-frontmatter; settings.json says `python3`,
which usually does not. Testing the venv interpreter passed green while the
shipped command recalled nothing.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
SETTINGS = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
ALL_REGISTERED_COMMANDS = tuple(
    hook.get("command", "")
    for groups in SETTINGS["hooks"].values()
    for group in groups
    for hook in group.get("hooks", [])
)

# (event, invoker path relative to .claude/hooks/)
REGISTERED_HOOKS = (
    ("UserPromptSubmit", "UserPromptSubmit/invoke_memory_recall.py"),
    ("SessionEnd", "SessionEnd/invoke_memory_reflection.py"),
)


def _commands(event: str) -> list[str]:
    return [
        hook.get("command", "")
        for group in SETTINGS["hooks"].get(event, [])
        for hook in group.get("hooks", [])
    ]


def _registered_command(event: str, invoker: str) -> str:
    """Return the exact command registered for one hook."""
    return next(c for c in _commands(event) if invoker in c)


def _command_argv(command: str) -> list[str]:
    """Return the program arguments after the project-directory anchor."""
    _anchor, program = command.split("&&", maxsplit=1)
    return shlex.split(program)


def _registered_argv(event: str, invoker: str) -> list[str]:
    return _command_argv(_registered_command(event, invoker))


def _launcher_probe(command: str) -> str:
    """Validate one launcher's executable and script without running the hook."""
    anchor, program = command.split("&&", maxsplit=1)
    argv = shlex.split(program)
    executable = argv[0]
    checks = []
    if "/" in executable:
        checks.append(f"test -x {shlex.quote(executable)}")
    else:
        checks.append(f"command -v {shlex.quote(executable)} >/dev/null")
    checks.extend(
        f"test -f {shlex.quote(argument)}"
        for argument in argv[1:]
        if argument.startswith(".claude/hooks/")
    )
    return f"{anchor.strip()} && {' && '.join(checks)}"


def _fake_repo(tmp_path: Path) -> Path:
    """A throwaway checkout the hooks can walk up to.

    Keeps the real .serena/memories tree out of reach even though the hooks
    are read-only, so a regression that reintroduces a write cannot touch it.
    """
    (tmp_path / ".git").mkdir(exist_ok=True)
    memories = tmp_path / ".serena" / "memories" / "workflows"
    memories.mkdir(parents=True, exist_ok=True)
    (memories / "dispatch-groups.md").write_text(
        "# Dispatch Groups (2026-01-01)\n\nHow dispatch group registration works.\n",
        encoding="utf-8",
    )
    return tmp_path


def _harness_env(project_dir: Path = REPO_ROOT) -> dict[str, str]:
    """The environment Claude Code hooks actually run in.

    `uv run pytest` puts .venv/bin first on PATH, so a bare `python3` in a
    subprocess resolves to the virtualenv interpreter and the registered
    command looks healthy even when it is not. Claude Code activates no
    virtualenv, so the test drops it before launching.
    """
    env = dict(os.environ)
    virtual_env = env.pop("VIRTUAL_ENV", "")
    if virtual_env:
        venv_bin = {str(Path(virtual_env) / "bin"), str(Path(virtual_env) / "Scripts")}
        entries = [e for e in env.get("PATH", "").split(os.pathsep) if e not in venv_bin]
        env["PATH"] = os.pathsep.join(entries)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return env


def _run(
    event: str,
    invoker: str,
    payload: dict,
    cwd: Path,
    project_dir: Path = REPO_ROOT,
) -> subprocess.CompletedProcess:
    """Run one invoker exactly as registered, from an arbitrary cwd."""
    return _run_command(
        _registered_command(event, invoker),
        payload,
        cwd,
        project_dir,
    )


def _run_command(
    command: str,
    payload: dict,
    cwd: Path,
    project_dir: Path = REPO_ROOT,
) -> subprocess.CompletedProcess:
    """Run one settings command under the Claude Code shell contract."""
    env = _harness_env(project_dir)
    return subprocess.run(
        ["sh", "-c", command],
        input=json.dumps(payload),
        capture_output=True,
        encoding="utf-8",
        cwd=str(cwd),
        env=env,
        timeout=60,
        check=False,
    )


def _missing_interpreters() -> list[str]:
    """Return unavailable interpreters for hooks that are registered."""
    interpreters = set()
    for event, invoker in REGISTERED_HOOKS:
        command = next((c for c in _commands(event) if invoker in c), "")
        if command:
            interpreters.add(_registered_argv(event, invoker)[0])
    return sorted(interpreter for interpreter in interpreters if not shutil.which(interpreter))


_MISSING_INTERPRETERS = _missing_interpreters()

pytestmark = pytest.mark.skipif(
    bool(_MISSING_INTERPRETERS),
    reason=f"registered interpreter not on PATH: {_MISSING_INTERPRETERS}",
)


class TestRegistration:
    """Every hook is wired into settings.json and its invoker exists."""

    @pytest.mark.unit
    @pytest.mark.parametrize(("event", "invoker"), REGISTERED_HOOKS)
    def test_invoker_exists_inside_hooks_dir(self, event, invoker):
        path = (HOOKS_DIR / invoker).resolve()

        assert path.is_file()
        assert path.is_relative_to(HOOKS_DIR.resolve())

    @pytest.mark.unit
    @pytest.mark.parametrize(("event", "invoker"), REGISTERED_HOOKS)
    def test_settings_registers_the_invoker(self, event, invoker):
        assert any(invoker in command for command in _commands(event))

    @pytest.mark.unit
    def test_every_hook_command_anchors_scripts_to_project_dir(self):
        relative = [
            command
            for event in SETTINGS["hooks"]
            for command in _commands(event)
            if ".claude/hooks/" in command
            and not command.startswith('cd "$CLAUDE_PROJECT_DIR" && ')
        ]

        assert relative == []

    @pytest.mark.unit
    def test_no_registration_names_a_missing_script(self):
        missing = [
            token
            for event in SETTINGS["hooks"]
            for command in _commands(event)
            for token in _command_argv(command)
            if token.endswith(".py") and not (REPO_ROOT / token).is_file()
        ]

        assert missing == []

    @pytest.mark.unit
    @pytest.mark.parametrize("command", ALL_REGISTERED_COMMANDS)
    def test_every_hook_launcher_resolves_from_foreign_cwd(self, command, tmp_path):
        result = subprocess.run(
            ["sh", "-c", _launcher_probe(command)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(tmp_path),
            env=_harness_env(),
            timeout=60,
            check=False,
        )

        assert result.returncode == 0, result.stderr


class TestInvokerExitCodes:
    """CLI contract: the exit code each event actually needs.

    Launched with the registered interpreter, so a hook that cannot import
    its dependency under that interpreter fails here instead of shipping.
    """

    @pytest.mark.unit
    def test_recall_never_returns_two_when_a_memory_matches(self, tmp_path):
        result = _run(
            "UserPromptSubmit",
            "UserPromptSubmit/invoke_memory_recall.py",
            {"prompt": "how does dispatch group registration work"},
            _fake_repo(tmp_path),
        )

        assert result.returncode == 0, result.stderr
        assert "<memory-context>" in result.stdout
        assert "<memory-context>" not in result.stderr

    @pytest.mark.unit
    def test_recall_reports_no_missing_dependency(self, tmp_path):
        """The registered `python3` usually lacks python-frontmatter. The
        invoker re-execs under .venv rather than failing open (issue #4011)."""
        result = _run(
            "UserPromptSubmit",
            "UserPromptSubmit/invoke_memory_recall.py",
            {"prompt": "how does dispatch group registration work"},
            _fake_repo(tmp_path),
        )

        assert "No module named" not in result.stderr
        assert result.stdout.strip() != ""

    @pytest.mark.unit
    def test_unanchored_command_fails_from_foreign_cwd(self, tmp_path):
        command = _registered_command(
            "UserPromptSubmit",
            "UserPromptSubmit/invoke_memory_recall.py",
        )
        _anchor, unanchored = command.split("&&", maxsplit=1)

        result = _run_command(
            unanchored.strip(),
            {"prompt": "how does dispatch group registration work"},
            tmp_path,
        )

        assert result.returncode != 0
        assert "<memory-recall>" not in result.stdout
        assert "can't open file" in result.stderr

    @pytest.mark.unit
    def test_reflection_returns_zero_and_writes_nothing(self, tmp_path):
        repo = _fake_repo(tmp_path)
        memory = repo / ".serena" / "memories" / "workflows" / "dispatch-groups.md"
        before = memory.read_text(encoding="utf-8")

        result = _run(
            "SessionEnd", "SessionEnd/invoke_memory_reflection.py", {"reason": "clear"}, repo
        )

        assert result.returncode == 0, result.stderr
        assert "<session-reflection>" in result.stderr
        assert memory.read_text(encoding="utf-8") == before


class TestFailOpenWithoutTheScriptsTree:
    """A consumer install has no scripts/ and no .venv, so every invoker
    no-ops silently. This is the only case the silence is allowed to cover:
    inside this repository the re-exec in memory_enhancement.interpreter
    resolves the dependency instead."""

    @pytest.mark.unit
    @pytest.mark.parametrize(("event", "invoker"), REGISTERED_HOOKS)
    def test_missing_package_returns_zero(self, event, invoker, tmp_path):
        env = _harness_env()
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        env["PYTHONPATH"] = ""

        result = subprocess.run(
            [
                *(_registered_argv(event, invoker)[:2]),
                str(HOOKS_DIR / invoker),
            ],
            input="{}",
            capture_output=True,
            encoding="utf-8",
            cwd=str(tmp_path),
            env=env,
            timeout=60,
            check=False,
        )

        assert result.returncode == 0, result.stderr
