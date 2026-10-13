"""The Copilot CLI launcher is one recipe, and it runs under pwsh (issue #5521).

`build/scripts/copilot_launcher.py` defines the command line that runs a shipped
script from a Windows Copilot CLI host. These tests pin three things:

1. The renderer rejects a path it cannot place inside the payload.
2. Every `scripts.copilot` entry in `pr-review-config.yaml` is the renderer's
   output for its own script, so the recipe cannot fork into per-entry copies.
3. The rendered command runs under `pwsh`, dispatched through `bash -c` the way
   a workflow dispatches it, from a working directory that is not the repo.
   That covers root resolution, the interpreter chain (including the `py -3` and
   `python` arms, which only resolve on a Windows host), and argument quoting.

No Windows runner exists in CI. Everything here runs on the Linux runner; the
Windows-only facts it cannot see are the `py` launcher itself and PowerShell's
native-argument quoting on Windows.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

from copilot_launcher import (  # noqa: E402
    LAUNCHER_PREFIX,
    LauncherError,
    render_launcher,
    render_payload,
    split_launcher,
)

CONFIG = REPO_ROOT / ".claude" / "skills" / "pr-review" / "pr-review-config.yaml"
PLUGIN_ROOT = REPO_ROOT / "src" / "copilot-cli"
PLACEHOLDERS = {"{number}": "1", "{thread_id}": "t1", "{body}": "x", "{pr}": "1"}

PWSH = shutil.which("pwsh")
BASH = shutil.which("bash")


def _pwsh_supports_command_with_args() -> bool:
    if PWSH is None:
        return False
    probe = subprocess.run(
        [PWSH, "-NoProfile", "-Command", "$PSVersionTable.PSVersion -ge [version]'7.4'"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return probe.stdout.strip() == "True"


requires_pwsh = pytest.mark.skipif(
    BASH is None or not _pwsh_supports_command_with_args(),
    reason="bash and pwsh 7.4 or later are required for -CommandWithArgs",
)


def _copilot_map() -> dict[str, str]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return dict(config["scripts"]["copilot"])


def _env(**extra: str) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"}
    }
    env.update(extra)
    return env


def _run(command: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, "-c", command],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _fake_root(tmp_path: Path) -> Path:
    """A plugin root whose one script prints its own argv as JSON."""
    root = tmp_path / "plugin"
    script = root / "skills" / "demo" / "scripts" / "echo_args.py"
    script.parent.mkdir(parents=True)
    script.write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8")
    return root


DEMO = "skills/demo/scripts/echo_args.py"


class TestRenderer:
    def test_command_is_pwsh_with_one_single_quoted_payload(self):
        command = render_launcher(DEMO, "--flag")

        assert command.startswith(LAUNCHER_PREFIX + "'")
        payload = command[len(LAUNCHER_PREFIX) + 1 :].split("' ", 1)[0]
        assert "'" not in payload
        assert command.endswith("' --flag")

    def test_payload_has_no_pipe(self):
        """A pipe would split a Markdown table row the launcher is quoted in."""
        assert "|" not in render_payload(DEMO)

    def test_payload_names_the_root_chain_and_interpreter_chain(self):
        payload = render_payload(DEMO)

        assert payload.index("COPILOT_PLUGIN_ROOT") < payload.index("CLAUDE_PLUGIN_ROOT")
        assert payload.index("python3") < payload.index('"py"') < payload.index('"python"')
        assert '"-3"' in payload

    def test_no_args_means_no_trailing_space(self):
        assert render_launcher(DEMO).endswith("exit $LASTEXITCODE'")

    @pytest.mark.parametrize(
        "bad",
        [
            "../skills/x/y.py",
            "skills/../../etc/x.py",
            "/skills/x/y.py",
            "skills/x/y.sh",
            "scripts/x/y.py",
            'skills/x/"y".py',
            "skills/x/$y.py",
            "skills/x y/z.py",
            "skills/x\\y.py",
            "skills/x/y.py'; calc",
            "",
        ],
    )
    def test_refuses_a_path_it_cannot_quote(self, bad):
        with pytest.raises(LauncherError):
            render_launcher(bad)

    def test_split_is_the_inverse_of_render(self):
        assert split_launcher(render_launcher(DEMO, "--a {number}")) == (DEMO, "--a {number}")
        assert split_launcher(render_launcher(DEMO)) == (DEMO, "")

    @pytest.mark.parametrize(
        "command",
        [
            'python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/x/y.py"',
            "pwsh -NoProfile -Command 'whatever'",
            "",
        ],
    )
    def test_split_returns_none_for_anything_else(self, command):
        assert split_launcher(command) is None


class TestShippedMap:
    def test_every_entry_is_the_renderer_output_for_its_own_script(self):
        for key, command in _copilot_map().items():
            parsed = split_launcher(command)
            assert parsed is not None, f"{key} is not the launcher form"
            rel, args = parsed
            assert command == render_launcher(rel, args), f"{key} forked the launcher recipe"

    def test_every_entry_names_a_script_that_ships(self):
        for key, command in _copilot_map().items():
            parsed = split_launcher(command)
            assert parsed is not None, key
            assert (PLUGIN_ROOT / parsed[0]).is_file(), f"{key} names a missing script"

    def test_copilot_map_covers_every_claude_code_key(self):
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        claude = set(config["scripts"]["claude_code"])
        assert claude <= set(config["scripts"]["copilot"])

    def test_the_shipped_copy_carries_the_same_map(self):
        shipped = PLUGIN_ROOT / "skills" / "pr-review" / "pr-review-config.yaml"
        source = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["scripts"]["copilot"]
        copy = yaml.safe_load(shipped.read_text(encoding="utf-8"))["scripts"]["copilot"]
        assert copy == source


@requires_pwsh
class TestLauncherRunsUnderPwsh:
    """Run the real command from a foreign cwd. Each case has a negative control."""

    @pytest.mark.parametrize("key", sorted(_copilot_map()))
    def test_every_shipped_entry_reaches_its_script(self, key, tmp_path):
        command = _copilot_map()[key]
        for placeholder, value in PLACEHOLDERS.items():
            command = command.replace(placeholder, value)

        result = _run(
            f"{command} --help",
            tmp_path,
            _env(COPILOT_PLUGIN_ROOT=str(PLUGIN_ROOT)),
        )

        assert result.returncode == 0, f"{key}: {result.stdout}{result.stderr}"
        assert "usage" in result.stdout.lower()

    def test_without_a_plugin_root_the_fallback_does_not_resolve(self, tmp_path):
        """Negative control: a launcher that hardcoded this checkout would pass above."""
        result = _run(render_launcher(DEMO), tmp_path, _env())

        assert result.returncode != 0

    def test_claude_plugin_root_alone_resolves(self, tmp_path):
        root = _fake_root(tmp_path)

        result = _run(render_launcher(DEMO), tmp_path, _env(CLAUDE_PLUGIN_ROOT=str(root)))

        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == []

    def test_copilot_root_wins_over_claude_root(self, tmp_path):
        root = _fake_root(tmp_path)

        result = _run(
            render_launcher(DEMO),
            tmp_path,
            _env(COPILOT_PLUGIN_ROOT=str(root), CLAUDE_PLUGIN_ROOT=str(tmp_path / "missing")),
        )

        assert result.returncode == 0, result.stderr

    def test_an_empty_copilot_root_falls_through_like_the_posix_default(self, tmp_path):
        """`${A:-${B:-x}}` treats an empty A as unset; the payload must too."""
        root = _fake_root(tmp_path)

        result = _run(
            render_launcher(DEMO),
            tmp_path,
            _env(COPILOT_PLUGIN_ROOT="", CLAUDE_PLUGIN_ROOT=str(root)),
        )

        assert result.returncode == 0, result.stderr

    def test_a_quoted_multi_word_argument_arrives_as_one_argument(self, tmp_path):
        root = _fake_root(tmp_path)

        result = _run(
            render_launcher(DEMO, "--body \"two words\" --x 'it works'"),
            tmp_path,
            _env(COPILOT_PLUGIN_ROOT=str(root)),
        )

        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == ["--body", "two words", "--x", "it works"]

    def test_the_script_exit_code_propagates(self, tmp_path):
        root = _fake_root(tmp_path)
        (root / DEMO).write_text("import sys\nsys.exit(7)\n", encoding="utf-8")

        result = _run(render_launcher(DEMO), tmp_path, _env(COPILOT_PLUGIN_ROOT=str(root)))

        assert result.returncode == 7


@requires_pwsh
class TestInterpreterChain:
    """Force each fallback arm by renaming the candidate before it.

    The Linux runner has `python3`, so the `py -3` and `python` arms never run
    on their own. Renaming the earlier candidate inside the real payload makes
    `Get-Command` miss it, and a stub on PATH answers for the next name.
    """

    @staticmethod
    def _stub(directory: Path, name: str) -> Path:
        directory.mkdir(exist_ok=True)
        mark = directory / f"{name}.argv"
        stub = directory / name
        stub.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "$1" > "{mark}"\n'
            'if [ "$1" = "-3" ]; then shift; fi\n'
            f'exec "{sys.executable}" "$@"\n',
            encoding="utf-8",
        )
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        return mark

    @staticmethod
    def _absent(command: str, name: str) -> str:
        needle = f"Get-Command {name} "
        assert command.count(needle) == 1
        return command.replace(needle, f"Get-Command {name}-absent ")

    def _env_with_stubs(self, tmp_path, root):
        stubs = tmp_path / "stubs"
        return stubs, _env(
            COPILOT_PLUGIN_ROOT=str(root),
            PATH=f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}",
        )

    def test_py_launcher_arm_passes_dash_three(self, tmp_path):
        root = _fake_root(tmp_path)
        stubs, env = self._env_with_stubs(tmp_path, root)
        mark = self._stub(stubs, "py")
        command = self._absent(render_launcher(DEMO, "--k v"), "python3")

        result = _run(command, tmp_path, env)

        assert result.returncode == 0, result.stderr
        assert mark.read_text(encoding="utf-8").strip() == "-3"
        assert json.loads(result.stdout) == ["--k", "v"]

    def test_python_arm_runs_when_neither_python3_nor_py_exists(self, tmp_path):
        root = _fake_root(tmp_path)
        stubs, env = self._env_with_stubs(tmp_path, root)
        mark = self._stub(stubs, "python")
        command = self._absent(self._absent(render_launcher(DEMO), "python3"), "py")

        result = _run(command, tmp_path, env)

        assert result.returncode == 0, result.stderr
        assert mark.read_text(encoding="utf-8").strip() != "-3"

    def test_py_arm_is_skipped_while_python3_exists(self, tmp_path):
        """Negative control: the stub must not answer when python3 resolves."""
        root = _fake_root(tmp_path)
        stubs, env = self._env_with_stubs(tmp_path, root)
        mark = self._stub(stubs, "py")

        result = _run(render_launcher(DEMO), tmp_path, env)

        assert result.returncode == 0, result.stderr
        assert not mark.exists()
