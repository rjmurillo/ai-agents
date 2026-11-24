"""Always-on tests for ``hermes_runtime.py``, the helpers the Hermes smoke uses.

They need no ``hermes`` CLI. They prove the helpers confine the run to a scratch
home, parse the launcher, stage a committable repo, and refuse a leaked variable,
so the real smoke in ``test_hermes_plugin_smoke.py`` is not the only check on them.
"""

from __future__ import annotations

import hashlib
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


_DELIVERY = "project-toolkit-delivery"
_KNOWLEDGE = "project-toolkit-knowledge"
_QUALITY = "project-toolkit-quality"
_AUTHORING = "project-toolkit-authoring"
_NEW_FINDING = ("inline_shell_exec", "skills/new-skill/SKILL.md", 3, "0" * 64)


def _one_reviewed(pack: str) -> tuple[str, str, int, str]:
    return sorted(hr.FORCE_ALLOWED_FINDINGS[pack])[0]


@pytest.mark.parametrize("pack", [_DELIVERY, _AUTHORING])
def test_force_is_allowed_when_every_high_finding_was_reviewed(pack: str) -> None:
    reviewed = hr.FORCE_ALLOWED_FINDINGS[pack]

    assert hr.force_for_verdict(pack, "caution", reviewed) is True


def test_force_is_allowed_for_a_reviewed_subset() -> None:
    one = frozenset({_one_reviewed(_DELIVERY)})

    assert hr.force_for_verdict(_DELIVERY, "caution", one) is True


@pytest.mark.parametrize("pack", [_DELIVERY, _KNOWLEDGE, _QUALITY, _AUTHORING])
def test_a_safe_pack_installs_without_force(pack: str) -> None:
    assert hr.force_for_verdict(pack, "safe", frozenset()) is False


@pytest.mark.parametrize("pack", [_DELIVERY, _AUTHORING])
def test_a_new_high_finding_in_a_reviewed_pack_blocks_force(pack: str) -> None:
    found = hr.FORCE_ALLOWED_FINDINGS[pack] | {_NEW_FINDING}

    with pytest.raises(ValueError, match="new-skill"):
        hr.force_for_verdict(pack, "caution", found)


@pytest.mark.parametrize("pack", [_DELIVERY, _AUTHORING])
def test_a_reviewed_finding_that_moved_blocks_force(pack: str) -> None:
    pid, rel, line, digest = _one_reviewed(pack)

    with pytest.raises(ValueError, match="unreviewed"):
        hr.force_for_verdict(pack, "caution", frozenset({(pid, rel, line + 1, digest)}))


@pytest.mark.parametrize("pack", [_DELIVERY, _AUTHORING])
def test_a_reviewed_finding_whose_line_changed_blocks_force(pack: str) -> None:
    pid, rel, line, _ = _one_reviewed(pack)

    with pytest.raises(ValueError, match="unreviewed"):
        hr.force_for_verdict(pack, "caution", frozenset({(pid, rel, line, "unreadable")}))


def test_a_reviewed_finding_does_not_carry_to_another_pack() -> None:
    delivery_only = hr.FORCE_ALLOWED_FINDINGS[_DELIVERY]

    with pytest.raises(ValueError, match="unreviewed"):
        hr.force_for_verdict(_AUTHORING, "caution", delivery_only)


@pytest.mark.parametrize("pack", [_KNOWLEDGE, _QUALITY])
def test_a_pack_with_no_reviewed_findings_fails_on_caution(pack: str) -> None:
    with pytest.raises(ValueError, match=pack):
        hr.force_for_verdict(pack, "caution", frozenset({_NEW_FINDING}))


def test_only_delivery_and_authoring_carry_reviewed_findings() -> None:
    assert set(hr.FORCE_ALLOWED_FINDINGS) == {_DELIVERY, _AUTHORING}


def test_caution_with_no_high_finding_fails() -> None:
    with pytest.raises(ValueError, match="no high findings"):
        hr.force_for_verdict(_DELIVERY, "caution", frozenset())


@pytest.mark.parametrize("verdict", ["dangerous", "unknown", ""])
@pytest.mark.parametrize("pack", [_DELIVERY, _KNOWLEDGE, _QUALITY, _AUTHORING])
def test_force_never_passes_a_verdict_worse_than_caution(verdict: str, pack: str) -> None:
    with pytest.raises(ValueError, match="only caution"):
        hr.force_for_verdict(pack, verdict, hr.FORCE_ALLOWED_FINDINGS.get(pack, frozenset()))


@pytest.mark.parametrize("pack", [_DELIVERY, _AUTHORING])
def test_every_reviewed_finding_hashes_the_line_it_names(pack: str) -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "hermes" / pack
    for _, rel, line, digest in hr.FORCE_ALLOWED_FINDINGS[pack]:
        text = (root / rel).read_text(encoding="utf-8-sig").split("\n")[line - 1]

        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == digest, (rel, line)


_FAKE_GUARD = """
from types import SimpleNamespace as NS

def scan_plugin(path, source):
    findings = [
        NS(severity="high", pattern_id="inline_shell_exec", file="skills/a/SKILL.md", line=2),
        NS(severity="high", pattern_id="inline_shell_exec", file="skills/a/SKILL.md", line=2),
        NS(severity="critical", pattern_id="read_secrets_file", file="skills/b/run.py", line=9),
        NS(severity="high", pattern_id="x", file="skills/a/SKILL.md", line=0),
        NS(severity="medium", pattern_id="python_subprocess", file="skills/c/run.py", line=1),
    ]
    return NS(verdict="dangerous", findings=findings)
"""


def test_guard_snippet_reports_verdict_and_line_hashed_high_findings(tmp_path: Path) -> None:
    fake = tmp_path / "fake"
    (fake / "tools").mkdir(parents=True)
    (fake / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (fake / "tools" / "plugin_guard.py").write_text(_FAKE_GUARD, encoding="utf-8")
    pack = tmp_path / "pack"
    (pack / "skills" / "a").mkdir(parents=True)
    # A BOM and a form feed: the guard strips the first and does not split on the second.
    (pack / "skills" / "a" / "SKILL.md").write_text(
        "\ufeffone\f!`x`\n!`git status`\n", encoding="utf-8"
    )
    # python -I ignores PYTHONPATH, so the fake guard goes on sys.path in the snippet.
    snippet = f"import sys\nsys.path.insert(0, {str(fake)!r})\n{hr.GUARD_SNIPPET}"

    parsed, _ = hr.python_json(
        Path(sys.executable), snippet, {"PATH": "/usr/bin:/bin"}, cwd=tmp_path, argv=[str(pack)]
    )

    digest = hashlib.sha256(b"!`git status`").hexdigest()
    assert parsed == {
        str(pack): {
            "verdict": "dangerous",
            "high": [
                ["inline_shell_exec", "skills/a/SKILL.md", 2, digest],
                ["read_secrets_file", "skills/b/run.py", 9, "unreadable"],
                ["x", "skills/a/SKILL.md", 0, "unreadable"],
            ],
        }
    }
