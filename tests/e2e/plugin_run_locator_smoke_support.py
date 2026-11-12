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
from typing import NoReturn

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# tests/e2e has no __init__.py under --import-mode=importlib, and the launcher and
# cli_exec live outside it. The path edit is undone once the imports are bound, so
# it cannot leak into later tests.
_original_sys_path = sys.path.copy()
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
    import copilot_hook_probe
    import smoke_skip_policy
    from plugin_run_launcher import render_locator

    from scripts.cli_exec import resolve_executable
finally:
    sys.path[:] = _original_sys_path

RESOLVER_SOURCE = REPO_ROOT / "src" / "claude" / "lib" / "ptk_run.py"
PLUGIN_NAME = "ptkloc"
TARGET_REL = "skills/stub/scripts/echo_marker.py"
TARGET_ARG = "one"
MARKER = "ptk-ran"
MODEL = "haiku"
TIMEOUT_SECONDS = 170
ATTEMPTS = 2
ENV_STRIP = frozenset({"CLAUDE_PLUGIN_DATA"})
PERMISSION_MODE = "dontAsk"
TAIL_CHARS = 600

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


LOCATOR_MARKER = "lib/ptk_run.py"
LEGACY_TEXT = "COPILOT_PLUGIN_ROOT:-"


@dataclass(frozen=True, slots=True)
class BashCall:
    """One Bash ``tool_use`` and the ``tool_result`` that carries its ``tool_use_id``."""

    command: str
    result: str | None


@dataclass(frozen=True, slots=True)
class Observation:
    """What one ``claude -p`` run did, read from its stream-json output."""

    calls: tuple[BashCall, ...]
    stdout: str
    stderr: str
    returncode: int

    @property
    def bash_commands(self) -> tuple[str, ...]:
        return tuple(call.command for call in self.calls)

    @property
    def tool_results(self) -> tuple[str, ...]:
        return tuple(call.result for call in self.calls if call.result is not None)

    def locator_ran(self, plugin: Path) -> bool:
        """True when the locator command, after host substitution, printed our JSON line.

        The producing command must hold ``lib/ptk_run.py`` and the absolute plugin
        directory. That rejects a stub the model ran directly and a command whose
        ``${CLAUDE_PLUGIN_ROOT}`` stayed literal.
        """
        roots = {str(plugin), str(plugin.resolve())}
        return any(
            LOCATOR_MARKER in call.command
            and any(root in call.command for root in roots)
            and _holds_marker_line(call.result)
            for call in self.calls
        )

    def legacy_attempted(self) -> bool:
        """True when a Bash call ran the legacy nested form."""
        return any(LEGACY_TEXT in call.command for call in self.calls)

    def legacy_leaked(self) -> bool:
        """True when any paired result, or the model's own output, holds the marker."""
        in_results = any(MARKER in (call.result or "") for call in self.calls)
        return in_results or self.marker_anywhere()

    def marker_anywhere(self) -> bool:
        return MARKER in self.stdout

    def describe(self) -> str:
        return (
            f"returncode={self.returncode}\nbash_commands={list(self.bash_commands)!r}\n"
            f"tool_results={list(self.tool_results)!r}\n"
            f"--- full stdout ---\n{self.stdout}\n--- stderr ---\n{self.stderr}"
        )


def _holds_marker_line(result: str | None) -> bool:
    return any(
        payload.get("marker") == MARKER and payload.get("argv") == [TARGET_ARG]
        for payload in json_lines(result or "")
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


def parse_stream(stdout: str) -> tuple[BashCall, ...]:
    """Pair each Bash ``tool_use`` (by ``id``) with its ``tool_result`` (by ``tool_use_id``).

    A result whose id matches no Bash call is dropped. A call with no result keeps
    ``result=None``. Calls stay in the order the model issued them.
    """
    commands: dict[str, str] = {}
    results: dict[str, str] = {}
    for event in json_lines(stdout):
        for block in _content_blocks(event):
            if block.get("type") == "tool_use" and block.get("name") == "Bash":
                tool_input = block.get("input")
                if isinstance(tool_input, dict):
                    commands[str(block.get("id", ""))] = str(tool_input.get("command", ""))
            elif block.get("type") == "tool_result":
                results[str(block.get("tool_use_id", ""))] = _result_text(block.get("content"))
    return tuple(BashCall(command, results.get(use_id)) for use_id, command in commands.items())


def observe(run: subprocess.CompletedProcess[str]) -> Observation:
    return Observation(
        parse_stream(run.stdout or ""), run.stdout or "", run.stderr or "", run.returncode
    )


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
        PERMISSION_MODE,
        "--output-format",
        "stream-json",
        "--verbose",
    ]


def _decode_partial(output: bytes | str | None) -> str:
    """``TimeoutExpired`` holds bytes even when the run asked for text."""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output or ""


def _redacted_tail(text: str) -> str:
    """Redact before slicing, so a token cut at the boundary is still caught."""
    return repr(copilot_hook_probe.redact(text).text[-TAIL_CHARS:])


def _fail_on_timeout(skill: str, exc: subprocess.TimeoutExpired) -> NoReturn:
    """Classify the partial streams, then skip or fail the timeout.

    A spent quota or an expired login can keep the CLI retrying until the deadline.
    The marker it printed before the kill is still a classified block. A timeout with
    no marker is a real hang and fails in CI, skips loudly elsewhere.
    """
    partial = subprocess.CompletedProcess(
        exc.cmd, -9, _decode_partial(exc.stdout), _decode_partial(exc.stderr)
    )
    smoke_skip_policy.skip_or_fail_on_claude_block(partial, f"ADR-121 locator smoke ({skill})")
    message = (
        f"claude run exceeded {TIMEOUT_SECONDS}s with no block marker. "
        f"stdout={_redacted_tail(partial.stdout)} stderr={_redacted_tail(partial.stderr)}"
    )
    smoke_skip_policy.skip_or_fail_unmarked(message)
    # skip_or_fail_unmarked never returns; mypy cannot see that through the importlib path.
    raise AssertionError(message) from exc


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
    except subprocess.TimeoutExpired as exc:
        _fail_on_timeout(skill, exc)
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
