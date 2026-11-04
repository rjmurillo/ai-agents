#!/usr/bin/env python3
"""Runtime contract for the installed plugin Stop group (REQ-048 AC-16, AC-26, AC-28).

These tests install a copy of ``src/claude/`` into a temp directory, run the
registered Stop command exactly as the host does (a shell, with
``CLAUDE_PLUGIN_ROOT`` set, from a directory that is not the plugin root), and
check what happens. They isolate ``HOME`` and ``XDG_STATE_HOME`` so the real
per-user marker directory is never touched.

AC-16 negative control: the same registration written as a bare relative path
fails from that directory, and works from the plugin root. That pair shows the
cwd is the cause and the test would notice a regression.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

from tests.hooks.friction_nudge_support import friction_records, write_transcript
from tests.hooks.reflect_nudge_support import human

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SOURCE = REPO_ROOT / "src" / "claude"
GROUP = "plugin-stop-1-reflect_nudge"
STATE_DIR_NAME = "ai-agents-reflect-nudge"
SESSION_ID = "sess-runtime-1"
TIMEOUT_SECONDS = 60


class Harness:
    """One installed plugin, one consumer project, isolated HOME and state."""

    def __init__(self, base: Path) -> None:
        self.plugin = base / "installed" / "project-toolkit"
        self.consumer = base / "consumer"
        self.home = base / "home"
        self.state = base / "state"
        self.bin = base / "bin"
        for directory in (self.consumer, self.home, self.state, self.bin):
            directory.mkdir(parents=True)
        self._install_plugin()
        self._install_python_shim()
        self.transcript = write_transcript(
            base / "transcript.jsonl",
            [human("no, wrong"), *friction_records(denials=6)],
        )

    def _install_plugin(self) -> None:
        self.plugin.mkdir(parents=True)
        for name in ("hooks", "lib", ".claude-plugin"):
            shutil.copytree(
                PLUGIN_SOURCE / name,
                self.plugin / name,
                ignore=shutil.ignore_patterns("__pycache__"),
            )

    def _install_python_shim(self) -> None:
        """A ``python3`` on PATH that runs the interpreter pytest runs under."""
        shim = self.bin / "python3"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
        shim.chmod(0o755)

    @property
    def command(self) -> str:
        doc = json.loads((self.plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        return str(doc["hooks"]["Stop"][0]["hooks"][0]["command"])

    @property
    def plugin_name(self) -> str:
        manifest = self.plugin / ".claude-plugin" / "plugin.json"
        return str(json.loads(manifest.read_text(encoding="utf-8"))["name"])

    def env(self) -> dict[str, str]:
        return {
            "PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin",
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.state),
            "CLAUDE_PLUGIN_ROOT": str(self.plugin),
            "CLAUDE_PROJECT_DIR": str(self.consumer),
        }

    def payload(self) -> str:
        return json.dumps(
            {
                "session_id": SESSION_ID,
                "transcript_path": str(self.transcript),
                "cwd": str(self.consumer),
            }
        )

    def run(self, command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/sh", "-c", command],
            cwd=cwd,
            env=self.env(),
            input=self.payload(),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )

    def markers(self) -> list[Path]:
        directory = self.state / STATE_DIR_NAME
        return sorted(directory.iterdir()) if directory.is_dir() else []


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


# --- AC-16, AC-26 ---------------------------------------------------------------


def test_the_registered_command_runs_the_hook_from_a_foreign_cwd(harness: Harness) -> None:
    result = harness.run(harness.command, cwd=harness.consumer)
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert set(doc) == {"systemMessage"}, "AC-26: a systemMessage document, not plain stdout"
    assert "/retrospective" in doc["systemMessage"]
    assert len(harness.markers()) >= 2, "both branches claimed a marker"


def test_negative_control_a_bare_relative_path_fails_from_a_foreign_cwd(harness: Harness) -> None:
    bare = f"python3 -u hooks/invoke_dispatch_claude.py --group {GROUP} --advisory"
    foreign = harness.run(bare, cwd=harness.consumer)
    assert foreign.returncode != 0
    assert "systemMessage" not in foreign.stdout
    assert harness.markers() == []
    from_root = harness.run(bare, cwd=harness.plugin)
    assert from_root.returncode == 0, from_root.stderr
    assert "systemMessage" in from_root.stdout, "same command works from the plugin root"


def test_the_command_does_not_depend_on_the_working_directory(
    harness: Harness, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere" / "deep"
    elsewhere.mkdir(parents=True)
    result = harness.run(harness.command, cwd=elsewhere)
    assert result.returncode == 0 and "systemMessage" in result.stdout


def test_inside_the_publishing_repo_the_plugin_stays_silent(harness: Harness) -> None:
    """The dogfood registration owns Stop there, so the plugin exits at once."""
    manifest = harness.consumer / ".claude" / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"name": harness.plugin_name}), encoding="utf-8")
    result = harness.run(harness.command, cwd=harness.consumer)
    assert result.returncode == 0
    assert result.stdout == ""
    assert harness.markers() == []


def test_a_broken_manifest_in_the_installed_plugin_does_not_block_a_stop(
    harness: Harness,
) -> None:
    (harness.plugin / "hooks" / "dispatch_groups.json").write_text("{not json", encoding="utf-8")
    result = harness.run(harness.command, cwd=harness.consumer)
    assert result.returncode == 0
    assert result.stdout == ""
    assert len([ln for ln in result.stderr.splitlines() if ln.strip()]) == 1


def test_a_plugin_without_its_dispatcher_library_exits_zero(harness: Harness) -> None:
    shutil.rmtree(harness.plugin / "lib")
    result = harness.run(harness.command, cwd=harness.consumer)
    assert result.returncode == 0
    assert "hooks DISABLED" in result.stderr


# --- AC-28: the open() audit --------------------------------------------------

DRIVER = textwrap.dedent(
    """
    import json, runpy, sys
    launcher, group, out_path, decoy = sys.argv[1:5]
    opened, active = [], [True]

    def hook(event, args):
        if event == "open" and active[0] and isinstance(args[0], (str, bytes)):
            path = args[0]
            opened.append(path.decode("utf-8", "replace") if isinstance(path, bytes) else path)

    sys.addaudithook(hook)
    sys.argv = [launcher, "--group", group, "--advisory"]
    if decoy:
        open(decoy, "rb").close()
    code = 0
    try:
        runpy.run_path(launcher, run_name="__main__")
    except SystemExit as exc:
        code = exc.code or 0
    active[0] = False
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(
            {"opened": opened, "code": code, "prefixes": [sys.prefix, sys.base_prefix]}, handle
        )
    """
)


def _run_audited(harness: Harness, tmp_path: Path, decoy: Path | None = None) -> dict:
    driver = tmp_path / "audit_driver.py"
    driver.write_text(DRIVER, encoding="utf-8")
    out = tmp_path / "audit.json"
    launcher = harness.plugin / "hooks" / "invoke_dispatch_claude.py"
    result = subprocess.run(
        [sys.executable, "-I", str(driver), str(launcher), GROUP, str(out), str(decoy or "")],
        cwd=harness.consumer,
        env=harness.env(),
        input=harness.payload(),
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    report["stdout"] = result.stdout
    return report


TEMP_NAME = re.compile(r"[a-z0-9_]{8}")


def _is_capture_temp_file(path: str) -> bool:
    """The launcher's own stdout and stderr capture (``output_capture.py``).

    It opens the temp directory itself (O_TMPFILE) or an anonymous
    ``tempfile.TemporaryFile`` one level below it. These hold the hook's own
    output, never another file's content. AC-28's list omits them; the owner
    should add them to the AC. Any deeper path under the temp directory is
    still reported.
    """
    tmp = os.path.realpath(tempfile.gettempdir())
    parent, name = os.path.split(path)
    return path == tmp or (parent == tmp and TEMP_NAME.fullmatch(name) is not None)


def _outside_allowed(harness: Harness, report: dict) -> list[str]:
    """Opened paths outside the AC-28 list. Compare resolved paths, not spellings."""

    def real(path: str | Path) -> str:
        return os.path.realpath(os.path.join(harness.consumer, str(path)))

    roots = [real(harness.plugin), real(harness.state / STATE_DIR_NAME)]
    roots += [real(prefix) for prefix in report["prefixes"]]
    exact = {
        real(harness.transcript),
        real(harness.consumer / ".claude" / ".claude-plugin" / "plugin.json"),
        real(harness.consumer / "src" / "claude" / ".claude-plugin" / "plugin.json"),
    }
    outside = []
    for raw in report["opened"]:
        path = real(raw)
        under_root = any(path == root or path.startswith(root + os.sep) for root in roots)
        if not under_root and path not in exact and not _is_capture_temp_file(path):
            outside.append(raw)
    return outside


def test_a_stop_with_both_branches_opens_only_the_allowed_files(
    harness: Harness, tmp_path: Path
) -> None:
    report = _run_audited(harness, tmp_path)
    assert report["code"] == 0
    assert "/retrospective" in json.loads(report["stdout"])["systemMessage"]
    assert len(harness.markers()) >= 2, "the run must exercise both branches"
    assert _outside_allowed(harness, report) == []


def test_the_audit_reads_the_transcript_and_the_state_it_is_allowed_to(
    harness: Harness, tmp_path: Path
) -> None:
    """Guard the guard: the probe saw the allowed files, so it was recording."""
    report = _run_audited(harness, tmp_path)
    opened = {os.path.realpath(path) for path in report["opened"]}
    assert os.path.realpath(harness.transcript) in opened
    assert any(STATE_DIR_NAME in path for path in opened)


def test_negative_control_a_planted_file_is_reported_as_outside(
    harness: Harness, tmp_path: Path
) -> None:
    decoy = tmp_path / "planted.txt"
    decoy.write_text("planted", encoding="utf-8")
    report = _run_audited(harness, tmp_path, decoy)
    assert _outside_allowed(harness, report) == [str(decoy)]


def test_the_state_directory_name_matches_the_hook() -> None:
    source = (PLUGIN_SOURCE / "hooks" / "Stop" / "_reflect_nudge_state.py").read_text("utf-8")
    assert re.search(rf"['\"]{STATE_DIR_NAME}['\"]", source)
