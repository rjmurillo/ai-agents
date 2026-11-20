#!/usr/bin/env python3
"""Runtime contract for the plugin memory recall group (issue #7493, ADR-109 amendment 2026-11-20).

The tests install a copy of the shipped plugin (``src/claude`` with symlinks
followed) into a temp directory outside this repository, create a consumer
repository that carries one Serena memory, and run the registered
``UserPromptSubmit`` command exactly as Claude Code does: through a shell, with
``CLAUDE_PLUGIN_ROOT`` and ``CLAUDE_PROJECT_DIR`` set, from a subdirectory of
the consumer repository. The only ``python3`` on ``PATH`` belongs to a venv with
no packages, so a ``frontmatter`` or ``yaml`` import in the recall closure would
fail here, which is the consumer's situation.

Negative controls: the same run with ``lib/memory_enhancement`` removed injects
nothing and names the missing package. A corrupt manifest exits 0 for the recall
group and 2 for an unreserved group.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SOURCE = REPO_ROOT / "src" / "claude"
GROUP = "plugin-userpromptsubmit-1-memory_recall"
MEMORY_ID = "zebra-migration-playbook"
MEMORY_TITLE = "Zebra Migration Playbook"  # unreadable without PyYAML
PROMPT = "zebra migration playbook"
TIMEOUT_SECONDS = 60
# The three trees the hook reads. skills/, agents/, and rules/ are not read by
# the hook and hold symlinks that need not resolve outside this repository.
PLUGIN_DIRS = ("hooks", "lib", ".claude-plugin")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_SECONDS,
    )


def _bare_venv_python_blocks(venv_python: Path, module: str) -> bool:
    """True when the venv interpreter cannot import ``module``."""
    result = subprocess.run(
        [str(venv_python), "-I", "-c", f"import {module}"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_SECONDS,
    )
    return result.returncode != 0


class Harness:
    """One installed plugin, one consumer repository, one package-free interpreter."""

    def __init__(self, base: Path, base_python: str | None = None) -> None:
        self._base_python = base_python
        self._plugin = base / "installed" / "project-toolkit"
        self._consumer = base / "consumer"
        self._workdir = self._consumer / "src" / "app"
        self._home = base / "home"
        self._venv = base / "bare-venv"
        self._home.mkdir(parents=True)
        self._workdir.mkdir(parents=True)
        self._install_plugin()
        self._create_consumer_repository()
        self._create_bare_interpreter()

    def _install_plugin(self) -> None:
        self._plugin.mkdir(parents=True)
        for name in PLUGIN_DIRS:
            shutil.copytree(
                PLUGIN_SOURCE / name,
                self._plugin / name,
                symlinks=False,
                ignore=shutil.ignore_patterns("__pycache__"),
            )

    def _create_consumer_repository(self) -> None:
        _git(self._consumer, "init", "-q")
        memories = self._consumer / ".serena" / "memories"
        memories.mkdir(parents=True)
        (memories / f"{MEMORY_ID}.md").write_text(
            f"---\ntitle: {MEMORY_TITLE}\ntags: [migration]\nconfidence: 0.9\n---\n\n"
            "Move every zebra service behind the gateway before the cutover.\n",
            encoding="utf-8",
        )

    def _create_bare_interpreter(self) -> None:
        base_python = self._base_python or getattr(sys, "_base_executable", sys.executable)
        subprocess.run(
            [base_python, "-m", "venv", "--without-pip", str(self._venv)],
            check=True,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
        )

    @property
    def plugin(self) -> Path:
        return self._plugin

    @property
    def consumer(self) -> Path:
        return self._consumer

    @property
    def venv_bin(self) -> Path:
        return self._venv / ("Scripts" if os.name == "nt" else "bin")

    @property
    def venv_python(self) -> Path:
        return self.venv_bin / ("python.exe" if os.name == "nt" else "python3")

    @property
    def command(self) -> str:
        doc = json.loads((self._plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        return str(doc["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"])

    def env(self) -> dict[str, str]:
        env = {
            "PATH": f"{self.venv_bin}{os.pathsep}/usr/bin{os.pathsep}/bin",
            "HOME": str(self._home),
            "CLAUDE_PLUGIN_ROOT": str(self._plugin),
            "CLAUDE_PROJECT_DIR": str(self._consumer),
            # CI redirects the temp root (run_pytest_non_tmp.py); keep it.
            "TMPDIR": tempfile.gettempdir(),
        }
        if "AI_AGENTS_MEMORY_RECALL" in os.environ:
            env["AI_AGENTS_MEMORY_RECALL"] = os.environ["AI_AGENTS_MEMORY_RECALL"]
        return env

    def payload(self, prompt: str = PROMPT) -> str:
        return json.dumps(
            {"prompt": prompt, "hook_event_name": "UserPromptSubmit", "cwd": str(self._workdir)}
        )

    def run(
        self, command: str | None = None, prompt: str = PROMPT
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", command or self.command],
            cwd=self._workdir,
            env=self.env(),
            input=self.payload(prompt),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
        )

    def dispatcher_command(self, group: str) -> list[str]:
        script = self._plugin / "hooks" / "invoke_dispatch_claude.py"
        return [str(self.venv_python), "-I", "-u", str(script), "--group", group]

    def run_dispatcher(self, group: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.dispatcher_command(group),
            cwd=self._workdir,
            env=self.env(),
            input=self.payload(),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
        )


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    if shutil.which("git") is None:
        pytest.skip("git is required to create the consumer repository")
    return Harness(tmp_path)


def _find_python_310() -> str | None:
    """A uv-managed 3.10 interpreter, or None. ``--no-project`` skips the 3.14 pin."""
    uv = shutil.which("uv")
    if uv is None:
        return None
    result = subprocess.run(
        [uv, "python", "find", "3.10", "--no-project"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_SECONDS,
    )
    found = result.stdout.strip().splitlines()
    return found[-1] if result.returncode == 0 and found else None


@pytest.fixture
def harness_310(tmp_path: Path) -> Harness:
    python_310 = _find_python_310()
    if python_310 is None:
        pytest.skip("no Python 3.10 found by `uv python find 3.10`; the launcher floor is untested")
    if shutil.which("git") is None:
        pytest.skip("git is required to create the consumer repository")
    return Harness(tmp_path, base_python=python_310)


def test_interpreter_under_test_has_neither_yaml_nor_frontmatter(harness: Harness) -> None:
    """The precondition: this is the consumer's interpreter, not the dev venv."""
    assert _bare_venv_python_blocks(harness.venv_python, "yaml")
    assert _bare_venv_python_blocks(harness.venv_python, "frontmatter")


def test_registered_command_injects_the_memory_under_a_bare_interpreter(
    harness: Harness,
) -> None:
    result = harness.run()

    assert result.returncode == 0, result.stderr
    assert "<memory-context>" in result.stdout, (result.stdout, result.stderr)
    # With no PyYAML the frontmatter title is unreadable (ADR-109 amendment
    # 2026-11-20, decision 5), so the heading is the memory id. The body is intact.
    assert f"### {MEMORY_ID} " in result.stdout
    assert "Move every zebra service behind the gateway" in result.stdout
    assert "title:" not in result.stdout


def test_registered_command_runs_without_the_advisory_flag(harness: Harness) -> None:
    assert f"--group {GROUP}" in harness.command
    assert "--advisory" not in harness.command


def test_prompt_naming_no_memory_injects_nothing(harness: Harness) -> None:
    result = harness.run(prompt="quokka telemetry exporter")

    assert result.returncode == 0, result.stderr
    assert "<memory-context>" not in result.stdout


def test_missing_package_fails_open_and_names_the_expected_path(harness: Harness) -> None:
    """Negative control: without lib/memory_enhancement the hook injects nothing."""
    shutil.rmtree(harness.plugin / "lib" / "memory_enhancement")

    result = harness.run()

    assert result.returncode == 0, result.stderr
    assert "<memory-context>" not in result.stdout
    assert "memory_enhancement" in result.stderr
    assert str(harness.plugin / "lib") in result.stderr


def test_corrupt_manifest_preserves_the_prompt_for_the_recall_registration(
    harness: Harness,
) -> None:
    (harness.plugin / "hooks" / "dispatch_groups.json").write_text("{not json", encoding="utf-8")

    result = harness.run()

    assert result.returncode == 0, result.stderr
    assert "<memory-context>" not in result.stdout
    assert "cannot load group" in result.stderr


def test_corrupt_manifest_still_blocks_an_unreserved_group(harness: Harness) -> None:
    """Negative control: only the reserved id fails open."""
    (harness.plugin / "hooks" / "dispatch_groups.json").write_text("{not json", encoding="utf-8")

    result = harness.run_dispatcher("sessionstart-1-context_loader")

    assert result.returncode == 2, result.stderr


def test_unknown_recall_group_contract_error_still_exits_zero(harness: Harness) -> None:
    """A manifest that drops the shim list is a contract error. The prompt survives."""
    manifest = harness.plugin / "hooks" / "dispatch_groups.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["groups"][GROUP]["shims"] = []
    manifest.write_text(json.dumps(data), encoding="utf-8")

    result = harness.run_dispatcher(GROUP)

    assert result.returncode == 0, result.stderr


def test_registered_command_injects_the_memory_under_python_310(harness_310: Harness) -> None:
    """The launcher accepts 3.10, so the shipped closure must run there."""
    version = subprocess.run(
        [str(harness_310.venv_python), "-I", "-c", "import sys;print(sys.version_info[:2])"],
        capture_output=True,
        encoding="utf-8",
        timeout=TIMEOUT_SECONDS,
    )
    assert version.stdout.strip() == "(3, 10)", version

    result = harness_310.run()

    assert result.returncode == 0, result.stderr
    assert "<memory-context>" in result.stdout, (result.stdout, result.stderr)
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("value", ["0", "off", "false", "OFF"])
def test_opt_out_env_disables_recall_through_the_registered_command(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("AI_AGENTS_MEMORY_RECALL", value)

    result = harness.run()

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_opt_out_env_set_to_another_value_still_recalls(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: the opt-out is the cause of the silence above."""
    monkeypatch.setenv("AI_AGENTS_MEMORY_RECALL", "1")

    result = harness.run()

    assert "<memory-context>" in result.stdout


def test_a_memories_symlink_out_of_the_repository_recalls_nothing(harness: Harness) -> None:
    outside = harness.consumer.parent / "outside"
    outside.mkdir()
    (outside / f"{MEMORY_ID}.md").write_text(
        f"---\ntitle: {MEMORY_TITLE}\n---\n\nMove every zebra service.\n", encoding="utf-8"
    )
    memories = harness.consumer / ".serena" / "memories"
    shutil.rmtree(memories)
    try:
        memories.symlink_to(outside, target_is_directory=True)
    except OSError as exc:  # pragma: no cover - Windows without developer mode
        pytest.skip(f"symlinks unavailable: {exc}")

    result = harness.run()

    assert result.returncode == 0, result.stderr
    assert "<memory-context>" not in result.stdout
