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

# The project-directory anchor every hook command must open with. Copilot CLI
# loads `.claude/settings.json` too but never exports `CLAUDE_PROJECT_DIR`, so a
# bare `cd "$CLAUDE_PROJECT_DIR"` is `cd ""` there: a silent sh/dash no-op that
# leaves relative script paths resolving against the host cwd. Measurement and
# controls in `probe-evidence.md` section 8b (issue #4727).
PROJECT_DIR_ANCHOR = 'cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}" && '

# The one memory the recall cases search for, so their prompt matches a body
# this file controls rather than whatever the live repository happens to hold.
DISPATCH_GROUPS_MEMORY = (
    "# Dispatch Groups (2026-01-01)\n\nHow dispatch group registration works.\n"
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


def _probe_launcher(
    command: str, env: dict[str, str], cwd: Path | None = None
) -> subprocess.CompletedProcess:
    """Run one launcher's resolution checks from a cwd that is not the root."""
    return subprocess.run(
        ["sh", "-c", _launcher_probe(command)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd if cwd is not None else REPO_ROOT / "scripts"),
        env=env,
        timeout=60,
        check=False,
    )


def _fake_repo(tmp_path: Path) -> Path:
    """A throwaway checkout the hooks can walk up to when cwd decides the root.

    Controls the memory tree only for a caller that ALSO passes it as
    `project_dir`: every registered command cd's there first, and
    `find_repo_root` walks up from that cwd, so passing it as cwd alone leaves
    the hook searching this repository's real `.serena/memories`. Use
    `_seeded_memory_checkout` when an assertion depends on which memories exist.
    """
    (tmp_path / ".git").mkdir(exist_ok=True)
    memories = tmp_path / ".serena" / "memories" / "workflows"
    memories.mkdir(parents=True, exist_ok=True)
    (memories / "dispatch-groups.md").write_text(DISPATCH_GROUPS_MEMORY, encoding="utf-8")
    return tmp_path


def _seeded_memory_checkout(tmp_path: Path) -> Path:
    """One memory the prompt hits. Pass as BOTH cwd and project_dir."""
    repo = _empty_memory_checkout(tmp_path)
    (repo / ".serena" / "memories" / "dispatch-groups.md").write_text(
        DISPATCH_GROUPS_MEMORY, encoding="utf-8"
    )
    return repo


def _empty_memory_checkout(tmp_path: Path) -> Path:
    """A checkout the hook can run inside whose memory tree starts empty.

    The registered command cd's to CLAUDE_PROJECT_DIR, so a foreign cwd alone
    still searches this repository's memories. Pointing the project directory
    at a throwaway checkout is what makes the memory tree controllable; the
    package tree and virtualenv are linked so the hook still loads its real
    dependencies instead of failing open.
    """
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    (repo / ".serena" / "memories").mkdir(parents=True)
    (repo / "scripts").symlink_to(REPO_ROOT / "scripts", target_is_directory=True)
    (repo / ".claude").symlink_to(REPO_ROOT / ".claude", target_is_directory=True)
    venv = REPO_ROOT / ".venv"
    if venv.is_dir():
        (repo / ".venv").symlink_to(venv, target_is_directory=True)
    return repo


def _harness_env(project_dir: Path = REPO_ROOT) -> dict[str, str]:
    """The environment Claude Code hooks actually run in.

    `uv run pytest` puts .venv/bin first on PATH, so a bare `python3` in a
    subprocess resolves to the virtualenv interpreter and the registered
    command looks healthy even when it is not. Claude Code activates no
    virtualenv, so the test drops it before launching.
    """
    env = dict(os.environ)
    # Drop both harness-identity signals; only the case that names one sets it
    # back. Either inherited value flips the recall hook's stdout shape (issue
    # #4727). CLAUDE_CODE_ENTRYPOINT is confirmed for Claude Code; COPILOT_CLI is
    # assumed, not vendor-confirmed. See _render_for_host, testing.md SHOULD-12.
    env.pop("COPILOT_CLI", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
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
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run one invoker exactly as registered, from an arbitrary cwd."""
    return _run_command(
        _registered_command(event, invoker),
        payload,
        cwd,
        project_dir,
        extra_env,
    )


def _run_command(
    command: str,
    payload: dict,
    cwd: Path,
    project_dir: Path = REPO_ROOT,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run one settings command under the Claude Code shell contract."""
    env = _harness_env(project_dir)
    env.update(extra_env or {})
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
        """The anchor must carry the fallback; see PROJECT_DIR_ANCHOR."""
        relative = [
            command
            for event in SETTINGS["hooks"]
            for command in _commands(event)
            if ".claude/hooks/" in command
            and not command.startswith(PROJECT_DIR_ANCHOR)
        ]

        assert relative == []

    @pytest.mark.unit
    @pytest.mark.parametrize("command", ALL_REGISTERED_COMMANDS)
    def test_every_launcher_resolves_with_the_project_dir_unset(self, command, tmp_path):
        """The Copilot case: same command, no CLAUDE_PROJECT_DIR, foreign cwd.

        The bare-anchor control proves the case discriminates; without it a
        probe passing for an unrelated reason would read as evidence.
        """
        env = _harness_env()
        del env["CLAUDE_PROJECT_DIR"]
        bare = 'cd "$CLAUDE_PROJECT_DIR" && ' + command[len(PROJECT_DIR_ANCHOR) :]

        result = _probe_launcher(command, env)
        control = _probe_launcher(bare, env)

        assert result.returncode == 0, result.stderr
        assert control.returncode != 0, "negative control passed; the probe proves nothing"

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
        result = _probe_launcher(command, _harness_env(), tmp_path)

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


class TestRecallOutputShapePerHost:
    """The recall hook's stdout shape is what each host actually consumes.

    Issue #4727 probed Copilot CLI 1.0.79-6 on this same registration surface
    with a matched pair: plain stdout was discarded, and a top-level
    ``{"additionalContext": "..."}`` document reached the model. Claude Code
    reads plain stdout on this event. The probe varied the output form, not the
    environment; these cases vary COPILOT_CLI, the variable the hook branches on to
    choose that form. It is simulated, not confirmed (see ``_render_for_host``).

    A unit test cannot observe host output handling, so the assertion is on
    the shape the host parses: one JSON document with a top-level
    ``additionalContext`` string, or bare text that is not JSON at all.

    Every case runs inside a seeded throwaway checkout passed as both cwd and
    project directory, so the recall comes from a memory this file writes.
    Reading the live tree instead would fail with an uncaught JSONDecodeError
    the day someone renames the memory the prompt happens to match.
    """

    RECALL = ("UserPromptSubmit", "UserPromptSubmit/invoke_memory_recall.py")
    PROMPT = {"prompt": "how does dispatch group registration work"}

    @pytest.mark.unit
    def test_copilot_receives_a_parseable_top_level_envelope(self, tmp_path):
        repo = _seeded_memory_checkout(tmp_path)

        result = _run(*self.RECALL, self.PROMPT, repo, repo, {"COPILOT_CLI": "1"})

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert isinstance(payload, dict)
        assert "<memory-context>" in payload["additionalContext"]

    @pytest.mark.unit
    def test_claude_still_receives_the_bare_block(self, tmp_path):
        repo = _seeded_memory_checkout(tmp_path)

        result = _run(*self.RECALL, self.PROMPT, repo, repo)

        assert result.returncode == 0, result.stderr
        assert result.stdout.lstrip().startswith("<memory-context>")
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.stdout)

    @pytest.mark.unit
    def test_a_live_claude_session_outranks_an_inherited_copilot_cli(self, tmp_path):
        """COPILOT_CLI is simulated, not vendor-confirmed (see _render_for_host);
        if real, a nested Claude session inherits it. Claude reads a nested
        hookSpecificOutput envelope and silently drops a top-level document."""
        repo = _seeded_memory_checkout(tmp_path)

        result = _run(
            *self.RECALL,
            self.PROMPT,
            repo,
            repo,
            {"COPILOT_CLI": "1", "CLAUDE_CODE_ENTRYPOINT": "cli"},
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.lstrip().startswith("<memory-context>")

    @pytest.mark.unit
    def test_an_empty_copilot_cli_value_is_not_a_copilot_session(self, tmp_path):
        """Presence of the name alone must not flip the shape; an exported but
        empty variable is indistinguishable from unset for identity."""
        repo = _seeded_memory_checkout(tmp_path)

        result = _run(*self.RECALL, self.PROMPT, repo, repo, {"COPILOT_CLI": ""})

        assert result.returncode == 0, result.stderr
        assert result.stdout.lstrip().startswith("<memory-context>")

    @pytest.mark.unit
    def test_no_recall_emits_nothing_rather_than_an_empty_envelope(self, tmp_path):
        """Silence, not an envelope wrapping an empty block.

        The paired control writes one matching memory into the same checkout
        and requires an envelope, so an empty stdout produced by a hook that
        failed open cannot pass this case.
        """
        repo = _empty_memory_checkout(tmp_path)

        empty = _run(*self.RECALL, self.PROMPT, repo, repo, {"COPILOT_CLI": "1"})

        assert empty.returncode == 0, empty.stderr
        assert empty.stdout == ""

        (repo / ".serena" / "memories" / "dispatch-groups.md").write_text(
            DISPATCH_GROUPS_MEMORY, encoding="utf-8"
        )
        populated = _run(*self.RECALL, self.PROMPT, repo, repo, {"COPILOT_CLI": "1"})

        assert populated.returncode == 0, populated.stderr
        assert "<memory-context>" in json.loads(populated.stdout)["additionalContext"]


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
