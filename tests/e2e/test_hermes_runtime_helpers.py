"""Always-on tests for ``hermes_runtime.py``, the helpers the Hermes smoke uses.

They need no ``hermes`` CLI. They prove the helpers confine the run to a scratch
home, parse the launcher, stage a committable repo, and refuse a leaked variable,
so the real smoke in ``test_hermes_plugin_smoke.py`` is not the only check on them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_E2E_DIR = Path(__file__).resolve().parent
if str(_E2E_DIR) not in sys.path:
    sys.path.insert(0, str(_E2E_DIR))

import hermes_runtime as hr  # noqa: E402


def write_launcher(path: Path, first_line: str) -> Path:
    path.write_text(f"{first_line}\nprint('x')\n", encoding="utf-8")
    return path


def test_hermes_python_prefers_the_python_beside_the_launcher(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    launcher = write_launcher(tmp_path / "bin" / "hermes", "#!/bin/sh")
    sibling = tmp_path / "bin" / "python"
    sibling.symlink_to(sys.executable)

    assert hr.hermes_python(launcher) == sibling


def test_hermes_python_follows_a_link_to_the_launcher(tmp_path: Path) -> None:
    (tmp_path / "venv" / "bin").mkdir(parents=True)
    launcher = write_launcher(tmp_path / "venv" / "bin" / "hermes", "#!/bin/sh")
    sibling = tmp_path / "venv" / "bin" / "python"
    sibling.symlink_to(sys.executable)
    link = tmp_path / "hermes-link"
    link.symlink_to(launcher)

    assert hr.hermes_python(link) == sibling


def test_hermes_python_falls_back_to_a_python_shebang(tmp_path: Path) -> None:
    launcher = write_launcher(tmp_path / "hermes", f"#!{sys.executable} -E")

    assert hr.hermes_python(launcher) == Path(sys.executable)


@pytest.mark.parametrize(
    "first_line", ["print('no shebang')", "", "#!", "#!/bin/sh", "#!/usr/bin/env"]
)
def test_hermes_python_rejects_a_launcher_without_a_python(tmp_path: Path, first_line: str) -> None:
    with pytest.raises(hr.HermesRuntimeError, match="cannot find the Python"):
        hr.hermes_python(write_launcher(tmp_path / "hermes", first_line))


def test_hermes_python_rejects_a_missing_interpreter(tmp_path: Path) -> None:
    launcher = write_launcher(tmp_path / "hermes", "#!/nonexistent/venv/bin/python")

    with pytest.raises(hr.HermesRuntimeError, match="cannot find the Python"):
        hr.hermes_python(launcher)


def test_scratch_env_confines_home_and_hermes_home(tmp_path: Path) -> None:
    env = hr.scratch_env(tmp_path / "h")

    assert env["HOME"] == str(tmp_path / "h")
    assert env["HERMES_HOME"] == str(tmp_path / "h" / "hermes-home")
    assert Path(env["HERMES_HOME"]).is_dir()
    assert ".hermes" not in env["HERMES_HOME"]


def test_run_uses_only_the_environment_it_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEAK_CHECK", "leaked")

    done = hr.run(
        [sys.executable, "-c", "import os; print(os.environ.get('LEAK_CHECK', 'absent'))"],
        {"PATH": "/usr/bin:/bin"},
        cwd=tmp_path,
    )

    assert done.stdout.strip() == "absent"


def test_script_env_sets_plugin_root_and_omits_the_other_roots(tmp_path: Path) -> None:
    env = hr.script_env(tmp_path, tmp_path / "pack")

    assert env["PLUGIN_ROOT"] == str(tmp_path / "pack")
    for key in hr.SCRIPT_ENV_KEYS_THAT_MUST_BE_UNSET:
        assert key not in env


def test_script_env_ignores_variables_set_in_the_test_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in hr.SCRIPT_ENV_KEYS_THAT_MUST_BE_UNSET:
        monkeypatch.setenv(key, "/should/not/leak")

    env = hr.script_env(tmp_path, tmp_path)

    assert not set(hr.SCRIPT_ENV_KEYS_THAT_MUST_BE_UNSET) & set(env)


def test_stage_git_repo_commits_a_copy_of_the_tree(tmp_path: Path) -> None:
    source = tmp_path / "packs"
    (source / "p").mkdir(parents=True)
    (source / "p" / "plugin.json").write_text("{}", encoding="utf-8")
    uncommitted_edit = source / "p" / "note.txt"
    uncommitted_edit.write_text("edit", encoding="utf-8")

    repo = hr.stage_git_repo(source, tmp_path / "repo", subdir="hermes")

    tracked = subprocess.run(
        ["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True
    ).stdout.split()
    assert tracked == ["hermes/p/note.txt", "hermes/p/plugin.json"]


def test_run_script_help_runs_under_isolated_mode(tmp_path: Path) -> None:
    script = tmp_path / "s.py"
    script.write_text("import sys; print('isolated', sys.flags.isolated)\n", encoding="utf-8")

    done = hr.run_script_help(script, hr.script_env(tmp_path, tmp_path), cwd=tmp_path)

    assert done.stdout.strip() == "isolated 1"


def test_python_json_returns_the_last_stdout_line(tmp_path: Path) -> None:
    parsed, stderr = hr.python_json(
        Path(sys.executable),
        "import sys, json; print('noise'); print(json.dumps([1, 2])); sys.stderr.write('warn')",
        {"PATH": "/usr/bin:/bin"},
        cwd=tmp_path,
    )

    assert parsed == [1, 2]
    assert stderr == "warn"


def test_python_json_rejects_a_snippet_that_prints_no_json(tmp_path: Path) -> None:
    with pytest.raises(hr.HermesRuntimeError, match="no JSON"):
        hr.python_json(
            Path(sys.executable), "print('plain')", {"PATH": "/usr/bin:/bin"}, cwd=tmp_path
        )


def test_python_json_rejects_a_snippet_that_exits_nonzero(tmp_path: Path) -> None:
    with pytest.raises(hr.HermesRuntimeError, match="snippet failed"):
        hr.python_json(
            Path(sys.executable), "raise SystemExit(3)", {"PATH": "/usr/bin:/bin"}, cwd=tmp_path
        )


def test_python_json_rejects_a_snippet_with_empty_stdout(tmp_path: Path) -> None:
    with pytest.raises(hr.HermesRuntimeError, match="no JSON"):
        hr.python_json(Path(sys.executable), "pass", {"PATH": "/usr/bin:/bin"}, cwd=tmp_path)


def test_force_is_allowed_for_a_caution_pack_on_the_allowlist() -> None:
    assert hr.force_for_verdict("project-toolkit-delivery", "caution") is True


def test_a_safe_pack_installs_without_force() -> None:
    assert hr.force_for_verdict("project-toolkit-delivery", "safe") is False
    assert hr.force_for_verdict("project-toolkit-knowledge", "safe") is False


@pytest.mark.parametrize("verdict", ["caution", "dangerous", "unknown", ""])
def test_a_pack_off_the_allowlist_fails_unless_safe(verdict: str) -> None:
    with pytest.raises(ValueError, match="project-toolkit-knowledge"):
        hr.force_for_verdict("project-toolkit-knowledge", verdict)


@pytest.mark.parametrize("verdict", ["dangerous", "unknown"])
def test_an_allowlisted_pack_never_gets_force_past_a_worse_verdict(verdict: str) -> None:
    with pytest.raises(ValueError, match="--force"):
        hr.force_for_verdict("project-toolkit-delivery", verdict)
