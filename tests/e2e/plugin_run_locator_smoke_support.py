"""Support for the ADR-121 locator smoke: gate, stream parsing, plugin builder, runner.

The live tests are in ``test_plugin_run_locator_claude_smoke.py`` and the unit
tests of these helpers are in ``test_plugin_run_locator_smoke_support.py``. The
split keeps each file under the 500 line taste limit.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import copilot_hook_probe  # noqa: E402
import smoke_skip_policy  # noqa: E402
from plugin_run_launcher import render_locator  # noqa: E402

from scripts.cli_exec import resolve_executable  # noqa: E402

RESOLVER_SOURCE = REPO_ROOT / "src" / "claude" / "lib" / "ptk_run.py"
PLUGIN_NAME = "ptkloc"
TARGET_REL = "skills/stub/scripts/echo_marker.py"
TARGET_ARG = "one"
MARKER = "ptk-ran"
MODEL = "haiku"
TIMEOUT_SECONDS = 170
ATTEMPTS = 2
ENV_STRIP = frozenset({"CLAUDE_PLUGIN_DATA"})

POSITIVE_SKILL = "runit"
LEGACY_SKILL = "runlegacy"
LEGACY_COMMAND = (
    'python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/'
    f'{TARGET_REL}" {TARGET_ARG}'
)

STUB_SOURCE = (
    f'import json\nimport sys\nprint(json.dumps({{"marker": "{MARKER}", "argv": sys.argv[1:]}}))\n'
)

SKILL_TEMPLATE = """---
name: {name}
description: Run one fixed shell command and report its raw output.
---

# {name}

Run exactly the command in the fenced block below, once, with the Bash tool.
Do not edit it, retry it, or look for another way to run the script.

```bash
{command}
```

Reply with the raw command output only.
"""


def gate_skip_reason(environ: Mapping[str, str], claude_path: str | None) -> str | None:
    """Return why the live run cannot start, or ``None`` when it can."""
    missing = []
    if environ.get("RUN_CLI_E2E") != "1":
        missing.append("RUN_CLI_E2E=1")
    if environ.get("RUN_CLI_MODEL_E2E") != "1":
        missing.append("RUN_CLI_MODEL_E2E=1 (this smoke makes a model call)")
    if not claude_path:
        missing.append("the claude CLI on PATH")
    if not missing:
        return None
    return "ADR-121 locator smoke SKIPPED, it needs " + ", ".join(missing)


_SKIP_REASON = gate_skip_reason(os.environ, shutil.which("claude"))
requires_model_run = pytest.mark.skipif(
    _SKIP_REASON is not None, reason=_SKIP_REASON or "gate open"
)


@dataclass(frozen=True, slots=True)
class Observation:
    """What one ``claude -p`` run did, read from its stream-json output."""

    bash_commands: tuple[str, ...]
    tool_results: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int

    def marker_ran(self) -> bool:
        """True when a Bash tool result holds the stub's JSON line with our argument."""
        return any(
            payload.get("marker") == MARKER and payload.get("argv") == [TARGET_ARG]
            for text in self.tool_results
            for payload in json_lines(text)
        )

    def marker_anywhere(self) -> bool:
        return MARKER in self.stdout

    def describe(self) -> str:
        return (
            f"returncode={self.returncode}\nbash_commands={list(self.bash_commands)!r}\n"
            f"tool_results={list(self.tool_results)!r}\n"
            f"--- full stdout ---\n{self.stdout}\n--- stderr ---\n{self.stderr}"
        )


def json_lines(text: str) -> list[dict[str, object]]:
    """Every line of ``text`` that parses as a JSON object."""
    found = []
    for line in text.splitlines():
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        if isinstance(doc, dict):
            found.append(doc)
    return found


def _content_blocks(event: dict[str, object]) -> list[dict[str, object]]:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


def parse_stream(stdout: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return ``(Bash commands, tool result texts)`` from a stream-json transcript."""
    commands: list[str] = []
    results: list[str] = []
    for event in json_lines(stdout):
        for block in _content_blocks(event):
            if block.get("type") == "tool_use" and block.get("name") == "Bash":
                tool_input = block.get("input")
                if isinstance(tool_input, dict):
                    commands.append(str(tool_input.get("command", "")))
            elif block.get("type") == "tool_result":
                results.append(_result_text(block.get("content")))
    return tuple(commands), tuple(results)


def observe(run: subprocess.CompletedProcess[str]) -> Observation:
    commands, results = parse_stream(run.stdout or "")
    return Observation(commands, results, run.stdout or "", run.stderr or "", run.returncode)


def skill_text(name: str, command: str) -> str:
    return SKILL_TEMPLATE.format(name=name, command=command)


def build_plugin(root: Path) -> Path:
    """Write the throwaway ``ptkloc`` plugin under ``root`` and return its directory."""
    plugin = root / "plugin"
    manifest = {
        "name": PLUGIN_NAME,
        "description": "ADR-121 locator smoke plugin",
        "version": "0.0.1",
        "author": {"name": "e2e"},
    }
    files = {
        ".claude-plugin/plugin.json": json.dumps(manifest),
        f"skills/{POSITIVE_SKILL}/SKILL.md": skill_text(
            POSITIVE_SKILL, render_locator(TARGET_REL, TARGET_ARG)
        ),
        f"skills/{LEGACY_SKILL}/SKILL.md": skill_text(LEGACY_SKILL, LEGACY_COMMAND),
        TARGET_REL: STUB_SOURCE,
    }
    for rel, body in files.items():
        path = plugin / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    (plugin / "lib").mkdir()
    shutil.copyfile(RESOLVER_SOURCE, plugin / "lib" / "ptk_run.py")
    return plugin


def smoke_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment with inherited plugin-root and plugin-data variables removed."""
    env = copilot_hook_probe.clean_env()
    for key in list(env):
        if key.upper() in ENV_STRIP:
            env.pop(key)
    env.update(extra or {})
    return env


def claude_command(plugin: Path, skill: str) -> list[str]:
    return [
        resolve_executable("claude"),
        "-p",
        f"Run the {skill} skill (/{PLUGIN_NAME}:{skill}).",
        "--plugin-dir",
        str(plugin),
        "--model",
        MODEL,
        "--allowedTools",
        "Bash",
        "--setting-sources",
        "project",
        "--permission-mode",
        "default",
        "--output-format",
        "stream-json",
        "--verbose",
    ]


def run_skill(plugin: Path, cwd: Path, skill: str, env: dict[str, str]) -> Observation:
    """One ``claude -p`` run. A blocked run skips or fails per ``smoke_skip_policy``."""
    try:
        run = subprocess.run(
            claude_command(plugin, skill),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        smoke_skip_policy.skip_or_fail_unmarked(f"claude run exceeded {TIMEOUT_SECONDS}s")
    smoke_skip_policy.skip_or_fail_on_claude_block(run, f"ADR-121 locator smoke ({skill})")
    return observe(run)


def run_with_retry(
    plugin: Path,
    cwd: Path,
    skill: str,
    env: dict[str, str],
    settled: Callable[[Observation], bool],
) -> Observation:
    """Run up to ``ATTEMPTS`` times; stop at the first run that ``settled`` accepts.

    A model can refuse or paraphrase. The retry covers that, and the caller asserts
    on the last run with its full output attached.
    """
    observation = run_skill(plugin, cwd, skill, env)
    for _ in range(ATTEMPTS - 1):
        if settled(observation):
            break
        observation = run_skill(plugin, cwd, skill, env)
    return observation


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    return build_plugin(tmp_path), cwd
