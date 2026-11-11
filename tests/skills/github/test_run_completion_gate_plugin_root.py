"""The completion gate runs the plugin-root path it verifies.

Plugin-self-containment MUST 2 wants every shipped command to name its script
through ``${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}``. Trust
verification already expanded that form, but dispatch ran the argv unexpanded,
so a criterion written in the documented form named no file at execution.
``_format_command`` now expands it, and both verification and dispatch call it.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tests.skills.github.dynamic_load_helpers import REPO_ROOT, gate, write

_FORM = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
_EMIT = "skills/probe/scripts/emit.py"
_CONFIG = REPO_ROOT / ".claude" / "skills" / "pr-review" / "pr-review-config.yaml"


@pytest.fixture(autouse=True)
def _no_plugin_root(monkeypatch: pytest.MonkeyPatch) -> None:
    # Hooks export these; each test sets the value it is about.
    monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)


def _command(script: str = _EMIT) -> str:
    return f'{shlex.quote(sys.executable)} "{_FORM}/{script}" --pull-request {{pr}}'


class TestFormatCommandExpandsThePluginRoot:
    def test_unset_roots_default_to_the_repo_claude_tree(self) -> None:
        argv = gate._format_command(_command(), 7)
        assert argv == [sys.executable, f".claude/{_EMIT}", "--pull-request", "7"]

    @pytest.mark.parametrize("variable", ["COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"])
    def test_a_declared_root_wins(self, monkeypatch: pytest.MonkeyPatch, variable: str) -> None:
        monkeypatch.setenv(variable, "/opt/plugin root")
        assert gate._format_command(_command(), 7)[1] == f"/opt/plugin root/{_EMIT}"

    def test_copilot_root_wins_over_claude_root(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", "/copilot")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/claude")
        assert gate._format_command(_command(), 7)[1] == f"/copilot/{_EMIT}"

    def test_an_empty_root_falls_through_like_the_shell(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", "")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/claude")
        assert gate._format_command(_command(), 7)[1] == f"/claude/{_EMIT}"

    @pytest.mark.parametrize(
        ("form", "env", "expected"),
        [
            (_FORM, {"COPILOT_PLUGIN_ROOT": "/c", "CLAUDE_PLUGIN_ROOT": "/a"}, "/c"),
            (
                "${CLAUDE_PLUGIN_ROOT:-${COPILOT_PLUGIN_ROOT:-.claude}}",
                {"COPILOT_PLUGIN_ROOT": "/c", "CLAUDE_PLUGIN_ROOT": "/a"},
                "/a",
            ),
            (
                "${CLAUDE_PLUGIN_ROOT:-${COPILOT_PLUGIN_ROOT:-.claude}}",
                {"COPILOT_PLUGIN_ROOT": "/c"},
                "/c",
            ),
            ("${COPILOT_PLUGIN_ROOT:-.claude}", {"CLAUDE_PLUGIN_ROOT": "/a"}, ".claude"),
            ("${COPILOT_PLUGIN_ROOT:-.claude}", {"COPILOT_PLUGIN_ROOT": "/c"}, "/c"),
            ("${CLAUDE_PLUGIN_ROOT:-.claude}", {"COPILOT_PLUGIN_ROOT": "/c"}, ".claude"),
            ("${CLAUDE_PLUGIN_ROOT:-.claude}", {"CLAUDE_PLUGIN_ROOT": "/a"}, "/a"),
        ],
    )
    def test_each_form_resolves_as_the_shell_would(
        self, monkeypatch: pytest.MonkeyPatch, form: str, env: dict[str, str], expected: str
    ) -> None:
        # Verified and executed paths must both match what a shell resolves.
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        shell = subprocess.run(
            ["sh", "-c", f'printf %s "{form}"'],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            env={**os.environ, **env},
        ).stdout
        assert shell == expected
        assert gate._format_command(f'python3 "{form}/x.py"', 7)[1] == f"{expected}/x.py"

    def test_other_shell_syntax_stays_literal(self) -> None:
        # Not general shell emulation: anything but the documented forms is
        # left for _unverifiable_argv to report.
        argv = gate._format_command('python3 "$HOME/verify.py" {pr}', 7)
        assert argv == ["python3", "$HOME/verify.py", "7"]


def test_dispatch_runs_the_expanded_path() -> None:
    criterion = {
        "name": "Probe",
        "verification": "command",
        "command": _command(),
        "pass_when": "stdout-json.ok == true",
    }
    completed = subprocess.CompletedProcess([], 0, stdout='{"ok": true}', stderr="")
    with patch.object(gate.subprocess, "run", return_value=completed) as run:
        result = gate._evaluate_criterion(criterion, 7)
    assert run.call_args.args[0][1] == f".claude/{_EMIT}"
    assert result["passed"] is True
    assert f".claude/{_EMIT}" in result["command"]


def _git(cwd: Path, *args: str) -> None:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(cwd),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


@pytest.fixture
def trusted_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real work tree whose trusted ref holds a plugin-root criterion."""
    monkeypatch.setattr(gate, "_PROJECT_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    _git(tmp_path, "init", "-q")
    write(
        tmp_path,
        f".claude/{_EMIT}",
        """\
        import json, pathlib
        pathlib.Path("ran.txt").write_text("ran", encoding="utf-8")
        print(json.dumps({"ok": True}))
        """,
    )
    criterion = {
        "name": "Probe",
        "verification": "command",
        "command": _command(),
        "pass_when": "stdout-json.ok == true",
    }
    config = tmp_path / "pr-review-config.yaml"
    config.write_text(yaml.safe_dump({"completion_criteria": [criterion]}), encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "trusted")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return tmp_path


def _run_gate(repo: Path) -> int:
    return gate.main(
        ["--config", str(repo / "pr-review-config.yaml"), "--pull-request", "7", "--json"]
    )


def test_the_verified_plugin_root_script_is_the_one_that_runs(
    trusted_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_gate(trusted_repo) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command_trust"]["checked_files"] == [f".claude/{_EMIT}"]
    criterion = payload["criteria"][0]
    assert criterion["exit_code"] == 0
    assert criterion["stdout_json"] == {"ok": True}
    assert (trusted_repo / "ran.txt").read_text(encoding="utf-8") == "ran"


def test_a_tampered_plugin_root_script_halts_before_it_runs(
    trusted_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (trusted_repo / ".claude" / _EMIT).write_text("print('{}')\n", encoding="utf-8")
    assert _run_gate(trusted_repo) == 2
    assert not (trusted_repo / "ran.txt").exists()
    assert f".claude/{_EMIT}" in capsys.readouterr().err


def test_every_shipped_criterion_names_its_script_through_the_plugin_root() -> None:
    criteria = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))["completion_criteria"]
    for criterion in criteria:
        argv = shlex.split(criterion["command"])
        assert argv[0] == "python3", criterion["name"]
        assert argv[1].startswith(f"{_FORM}/skills/"), criterion["name"]


def test_every_shipped_criterion_script_is_verified_from_the_repo_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The classification dispatch shares: from the repo root with the Claude
    # plugin tree declared as the plugin root, every criterion script is a
    # tracked file under it. The default `.claude` root is not usable in this
    # repository: `.claude/skills/<name>` is a symlink into `src/claude/skills`
    # (ADR-119), and the gate refuses a symlinked component (CWE-59).
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "src/claude")
    criteria = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))["completion_criteria"]
    to_verify, external, escaping = gate._collect_command_paths(criteria, 7, REPO_ROOT)
    scripts = [shlex.split(c["command"])[1].replace(_FORM, "src/claude") for c in criteria]
    assert all(script in to_verify for script in scripts), (scripts, to_verify)
    assert (external, escaping) == ([], [])


class TestForeignPluginRootIsSkipped:
    """Another plugin's exported root must not displace the repo script (issue #7281).

    context-mode exports CLAUDE_PLUGIN_ROOT inside ctx_execute. The shell form
    then resolves into that plugin and the script is not found.
    """

    @pytest.fixture
    def repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.chdir(tmp_path)
        write(tmp_path, f".claude/{_EMIT}", "print('{}')")
        return tmp_path

    @pytest.fixture
    def foreign(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        root = tmp_path_factory.mktemp("context-mode") / "2.1.7"
        root.mkdir()
        return root

    @pytest.mark.parametrize("variable", ["COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"])
    def test_a_root_without_the_script_falls_back_to_the_repo_tree(
        self, repo: Path, foreign: Path, monkeypatch: pytest.MonkeyPatch, variable: str
    ) -> None:
        monkeypatch.setenv(variable, str(foreign))
        assert gate._format_command(_command(), 7)[1] == f".claude/{_EMIT}"

    def test_a_foreign_copilot_root_falls_through_to_a_valid_claude_root(
        self,
        repo: Path,
        foreign: Path,
        tmp_path_factory: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ours = tmp_path_factory.mktemp("project-toolkit")
        write(ours, _EMIT, "print('{}')")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(foreign))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(ours))
        assert gate._format_command(_command(), 7)[1] == f"{ours}/{_EMIT}"

    def test_a_root_that_holds_the_script_still_wins(
        self,
        repo: Path,
        tmp_path_factory: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ours = tmp_path_factory.mktemp("project-toolkit")
        write(ours, _EMIT, "print('{}')")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(ours))
        assert gate._format_command(_command(), 7)[1] == f"{ours}/{_EMIT}"

    def test_no_candidate_keeps_the_first_set_root_so_the_failure_is_loud(
        self, tmp_path: Path, foreign: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(foreign))
        assert gate._format_command(_command(), 7)[1] == f"{foreign}/{_EMIT}"

    def test_a_parent_traversal_is_never_probed(
        self, repo: Path, foreign: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write(repo, "outside.py", "print('{}')")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(foreign))
        token = f"{_FORM}/../../outside.py"
        assert gate._expand_plugin_root(token, probe=True) == f"{foreign}/../../outside.py"

    def test_a_remainder_without_a_separator_is_never_probed(
        self, repo: Path, foreign: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``${...}evil/x.py`` must not probe ``<root>/evil/x.py``."""
        write(foreign, "evil/x.py", "print('{}')")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(foreign))
        token = f"{_FORM}evil/x.py"
        assert gate._expand_plugin_root(token, probe=True) == f"{foreign}evil/x.py"
        assert gate._plugin_root_holds(str(foreign), "evil/x.py") is False
        assert gate._plugin_root_holds(str(foreign), "/evil/x.py") is True

    def test_an_absolute_remainder_is_never_probed(
        self, repo: Path, foreign: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``${...}//abs/x.py`` must not probe ``/abs/x.py`` outside the root."""
        outside = repo / "outside" / "x.py"
        write(repo, "outside/x.py", "print('{}')")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(foreign))
        remainder = f"/{outside}"
        assert gate._plugin_root_holds(str(foreign), remainder) is False
        token = f"{_FORM}{remainder}"
        assert gate._expand_plugin_root(token, probe=True) == f"{foreign}{remainder}"

    def test_a_form_inside_a_larger_token_is_not_probed(
        self, repo: Path, foreign: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(foreign))
        token = f"--script={_FORM}/{_EMIT}"
        assert gate._expand_plugin_root(token, probe=True) == f"--script={foreign}/{_EMIT}"

    def test_the_launcher_token_keeps_first_set_semantics(
        self, repo: Path, foreign: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The PowerShell payload has no existence check, so the classified file
        # must be the one the launcher runs.
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(foreign))
        assert gate._launcher_script_token(gate._render_launcher(_EMIT)) == f"{foreign}/{_EMIT}"

    def test_the_gate_runs_the_repo_script_under_a_foreign_root(
        self,
        trusted_repo: Path,
        foreign: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(foreign))
        assert _run_gate(trusted_repo) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["command_trust"]["checked_files"] == [f".claude/{_EMIT}"]
        assert payload["criteria"][0]["exit_code"] == 0
        assert (trusted_repo / "ran.txt").read_text(encoding="utf-8") == "ran"

    def test_without_probing_the_gate_fails_under_a_foreign_root(
        self,
        trusted_repo: Path,
        foreign: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Negative control: the first-set expansion cannot run the repo script."""
        expand = gate._expand_plugin_root
        monkeypatch.setattr(gate, "_expand_plugin_root", lambda t, *, probe=False: expand(t))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(foreign))
        assert _run_gate(trusted_repo) != 0
        assert not (trusted_repo / "ran.txt").exists()
