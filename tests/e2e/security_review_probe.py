#!/usr/bin/env python3
"""Helpers for the security-agent end-to-end review test (issue #5619).

Holds the fixed diff fixture, the stream-json parsers, the scope and verdict
assertion, and the live ``claude`` runner. ``test_security_review_e2e.py`` drives
the live runs; ``test_security_review_probe.py`` pins these helpers with no CLI.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parents[2]
# smoke_skip_policy lives beside this module; importlib mode does not add the dir.
sys.path.insert(0, str(Path(__file__).resolve().parent))
_original_sys_path = sys.path.copy()
try:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from cli_exec import resolve_executable
    from redact_secrets import redact
finally:
    sys.path[:] = _original_sys_path

from smoke_skip_policy import PLUGIN_ROOT_ENV_KEYS, skip_or_fail_on_claude_block  # noqa: E402

# A review of a two-file diff reads one artifact and answers. 180s bounds a slow
# model turn; a hang is a defect.
REVIEW_TIMEOUT_SECONDS = 180

# The verdict taxonomy in .claude/agents/security.md, "Completion Trigger Taxonomy".
VERDICT_TOKENS = ("APPROVED", "CONDITIONAL", "BLOCKED")
_VERDICT_PATTERN = re.compile(r"\b(" + "|".join(VERDICT_TOKENS) + r")\b")
# The agent's no-verdict answer: `[BLOCKED] Cannot evaluate: <missing artifact>`.
_CANNOT_EVALUATE_PATTERN = re.compile(r"\bCannot evaluate\b", re.IGNORECASE)

# The fixed changeset. Both files are added, so the diff carries their full
# content; no untracked-file half is missing (security.md, step 2 of Review
# Scope Enumeration). A unit test checks the expected list against the diff, so
# the two cannot drift apart.
EXPECTED_CHANGED_FILES = ("src/greeter.py", "tests/test_greeter.py")
FIXTURE_DIFF = """\
diff --git a/src/greeter.py b/src/greeter.py
new file mode 100644
index 0000000..3b18e51
--- /dev/null
+++ b/src/greeter.py
@@ -0,0 +1,3 @@
+def greet(name: str) -> str:
+    \"\"\"Return a greeting for a name.\"\"\"
+    return f"Hello, {name}!"
diff --git a/tests/test_greeter.py b/tests/test_greeter.py
new file mode 100644
index 0000000..9a2b7c4
--- /dev/null
+++ b/tests/test_greeter.py
@@ -0,0 +1,5 @@
+from src.greeter import greet
+
+
+def test_greet_names_the_person() -> None:
+    assert greet("Ada") == "Hello, Ada!"
"""

REVIEW_PROMPT = (
    "Run a security review of the change in the diff artifact at {path}. "
    "The artifact is a complete snapshot. Do not write any file. "
    "State the scope you reviewed, then end with your verdict."
)


# --------------------------------------------------------------------------- #
# Pure helpers (exercised by the always-on unit tests).
# --------------------------------------------------------------------------- #


def changed_files_in_diff(diff: str) -> tuple[str, ...]:
    """Return the ``b/`` path of every ``diff --git`` header, in order."""
    return tuple(re.findall(r"^diff --git a/\S+ b/(\S+)$", diff, flags=re.MULTILINE))


def parse_stream_events(stdout: str) -> list[dict[str, object]]:
    """Decode newline-delimited ``stream-json`` output into event objects."""
    events: list[dict[str, object]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        assert isinstance(event, dict), f"CLI event must be an object: {event!r}"
        events.append(event)
    return events


def _content_blocks(event: dict[str, object]) -> list[dict[str, object]]:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def review_text(events: list[dict[str, object]]) -> str:
    """Return the agent's final answer.

    The ``result`` event carries it. When a run ends without one, fall back to
    the assistant text blocks so a truncated run still yields what was said.
    """
    for event in reversed(events):
        if event.get("type") == "result" and isinstance(event.get("result"), str):
            return str(event["result"])
    return "\n".join(
        str(block.get("text", ""))
        for event in events
        if event.get("type") == "assistant"
        for block in _content_blocks(event)
        if block.get("type") == "text"
    )


def read_paths(events: list[dict[str, object]]) -> list[Path]:
    """Return every path the agent passed to the ``Read`` tool, resolved."""
    paths: list[Path] = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in _content_blocks(event):
            tool_input = block.get("input")
            if block.get("type") != "tool_use" or block.get("name") != "Read":
                continue
            if isinstance(tool_input, dict) and isinstance(tool_input.get("file_path"), str):
                paths.append(Path(tool_input["file_path"]).resolve())
    return paths


def assert_read_artifact(events: list[dict[str, object]], artifact: Path) -> None:
    """Fail unless the agent called ``Read`` on the artifact it was asked to review."""
    paths = read_paths(events)
    assert artifact.resolve() in paths, (
        f"the security agent never read the diff artifact {artifact}. Read calls: "
        f"{[str(path) for path in paths]}. A verdict without a read of the pinned "
        f"snapshot reviewed something else."
    )


def assert_review_covers_scope(text: str, expected_files: tuple[str, ...]) -> None:
    """Fail unless the review enumerated every expected file and reached a verdict.

    Order of checks matters for the failure message: an empty enumeration is the
    defect issue #5619 names, so the missing-file check runs before the verdict
    check. A verdict with no enumerated files is exactly the silent failure.
    """
    missing = [path for path in expected_files if path not in text]
    assert not missing, (
        f"the review never named these changed files: {missing}. The agent returned "
        f"without enumerating the changeset. output_tail={_redacted_tail(text)}"
    )
    verdicts = _VERDICT_PATTERN.findall(text)
    assert verdicts, (
        f"the review carries no verdict token ({'/'.join(VERDICT_TOKENS)}). "
        f"output_tail={_redacted_tail(text)}"
    )
    assert not _CANNOT_EVALUATE_PATTERN.search(text), (
        f"the verdict is the 'Cannot evaluate' form: the agent gave a no-verdict answer. "
        f"output_tail={_redacted_tail(text)}"
    )


def _redacted_tail(text: str) -> str:
    """Redact before slicing, so a token cut at the boundary is still caught."""
    return repr(redact(text).text[-600:])


# --------------------------------------------------------------------------- #
# Live runs.
# --------------------------------------------------------------------------- #


def clean_env() -> dict[str, str]:
    """Env with the inherited PLUGIN_ROOT_ENV_KEYS vars stripped (smoke_skip_policy.py)."""
    env = os.environ.copy()
    for key in list(env):
        if key.upper() in PLUGIN_ROOT_ENV_KEYS:
            env.pop(key, None)
    return env


def claude_review_args(artifact: Path) -> list[str]:
    return [
        resolve_executable("claude"),
        "-p",
        "--agent",
        "security",
        "--setting-sources",
        "project",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--allowedTools",
        "Read,Glob,Grep",
        "--add-dir",
        str(artifact.parent),
        "--permission-mode",
        "dontAsk",
        "--output-format",
        "stream-json",
        "--verbose",
        REVIEW_PROMPT.format(path=artifact),
    ]


def fail_on_timeout(subject: str, exc: subprocess.TimeoutExpired) -> NoReturn:
    raise AssertionError(
        f"{subject} exceeded {exc.timeout}s; a review that never returns is a defect."
    ) from exc


def run_security_review(artifact: Path) -> list[dict[str, object]]:
    """Run the Claude security agent on ``artifact`` and return its event stream."""
    subject = f"claude security review of {artifact.name}"
    try:
        run = subprocess.run(
            claude_review_args(artifact),
            cwd=REPO_ROOT,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=REVIEW_TIMEOUT_SECONDS,
            check=False,
            env=clean_env(),
        )
    except subprocess.TimeoutExpired as exc:
        fail_on_timeout(subject, exc)
    if run.returncode != 0:
        skip_or_fail_on_claude_block(run, subject)
        raise AssertionError(
            f"{subject} failed (rc={run.returncode}). "
            f"stdout={_redacted_tail(run.stdout)} stderr={_redacted_tail(run.stderr)}"
        )
    return parse_stream_events(run.stdout)
