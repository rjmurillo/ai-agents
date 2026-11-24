#!/usr/bin/env python3
"""Real Claude Code CLI smoke for plugin per-prompt memory recall (issue #7493).

Launches the real ``claude`` CLI with a copy of ``src/claude/`` as
``--plugin-dir``. The working directory is a consumer repository, not the
plugin root. The repository holds one Serena memory with a canary token that
the model cannot know. File and shell tools are disallowed, so the token can
reach the answer only through the plugin's UserPromptSubmit recall hook.

The negative control runs the same prompt with ``AI_AGENTS_MEMORY_RECALL=off``,
the consumer opt-out, and expects the token to be absent.

Opt-in like the other real-CLI cases in ``test_cli_hook_e2e.py``: it needs
``RUN_CLI_E2E=1``, the ``claude`` CLI on PATH, real auth, and credits. It is not
listed in ``plugin-cli-smoke.yml``, so normal CI never runs it. Run locally:

    RUN_CLI_E2E=1 uv run pytest tests/e2e/test_cli_memory_recall_e2e.py -m "smoke and claude" -v

Run live 2026-11-20 on Claude Code 2.1.329: 3 passed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT))

import copilot_hook_probe  # noqa: E402
import smoke_skip_policy  # noqa: E402

from scripts.cli_exec import resolve_executable  # noqa: E402

CANARY = "QUOKKA-7731"
MEMORY_ID = "zebra-gateway-policy"
MEMORY_TEXT = (
    "---\n"
    "title: Zebra gateway policy\n"
    "---\n"
    "# Zebra gateway policy\n\n"
    f"The canary token for the zebra gateway policy is {CANARY}.\n"
)
# Recall keeps a memory only when at least half of the first five query terms
# name it (``_MIN_RELEVANCE`` in user_prompt_submit_memory.py). Here "zebra",
# "gateway", and "policy" name the memory id, so 3 of 5 terms match.
PROMPT = (
    "zebra gateway policy canary token: reply with the canary token only. "
    "Do not use any tools. If you do not know it, reply UNKNOWN."
)
DISALLOWED_TOOLS = "Read,Grep,Glob,Bash,LS,Task,WebFetch,WebSearch,NotebookRead"
TIMEOUT_SECONDS = 300

_RUN = os.environ.get("RUN_CLI_E2E") == "1"
requires_claude = pytest.mark.skipif(
    not (_RUN and shutil.which("claude")),
    reason="needs RUN_CLI_E2E=1 and the claude CLI on PATH (real auth + credits)",
)


def install_plugin(tmp_path: Path) -> Path:
    """Copy the shipped plugin pieces the hook reads, outside this checkout."""
    plugin = tmp_path / "plugin"
    for name in ("hooks", "lib", ".claude-plugin"):
        shutil.copytree(
            REPO_ROOT / "src" / "claude" / name,
            plugin / name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    return plugin


def create_consumer_repository(tmp_path: Path) -> Path:
    """A git repository with one Serena memory that names the canary."""
    consumer = tmp_path / "consumer"
    memories = consumer / ".serena" / "memories"
    memories.mkdir(parents=True)
    (memories / f"{MEMORY_ID}.md").write_text(MEMORY_TEXT, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(consumer)], check=True)
    return consumer


def run_claude(
    plugin: Path, consumer: Path, extra_env: dict[str, str]
) -> subprocess.CompletedProcess:
    env = copilot_hook_probe.clean_env()
    env.update(extra_env)
    try:
        return subprocess.run(
            [
                resolve_executable("claude"),
                "-p",
                PROMPT,
                "--plugin-dir",
                str(plugin),
                "--disallowedTools",
                DISALLOWED_TOOLS,
            ],
            cwd=consumer,
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
        raise


@pytest.mark.smoke
@pytest.mark.claude
@requires_claude
def test_plugin_recall_puts_the_consumer_memory_in_model_context(tmp_path: Path) -> None:
    plugin = install_plugin(tmp_path)
    consumer = create_consumer_repository(tmp_path)

    run = run_claude(plugin, consumer, {})
    smoke_skip_policy.skip_or_fail_on_claude_block(run, "claude memory recall e2e")

    assert CANARY in run.stdout, (
        "the recalled memory never reached the model. "
        f"stdout={run.stdout[-600:]!r} stderr={run.stderr[-600:]!r}"
    )


@pytest.mark.smoke
@pytest.mark.claude
@requires_claude
def test_opt_out_keeps_the_memory_out_of_model_context(tmp_path: Path) -> None:
    plugin = install_plugin(tmp_path)
    consumer = create_consumer_repository(tmp_path)

    run = run_claude(plugin, consumer, {"AI_AGENTS_MEMORY_RECALL": "off"})
    smoke_skip_policy.skip_or_fail_on_claude_block(run, "claude memory recall opt-out e2e")

    assert run.returncode == 0, run.stderr[-600:]
    assert CANARY not in run.stdout, "the canary reached the model with recall turned off"


def test_prompt_names_the_memory_id_with_at_least_half_the_query_terms() -> None:
    """Guard the live test's premise without the CLI: recall must select the memory."""
    sys.path.insert(0, str(REPO_ROOT / "src" / "claude" / "lib"))
    from memory_enhancement.hooks import user_prompt_submit_memory as recall

    query_terms = recall._extract_query(PROMPT).split()
    naming = [term for term in query_terms if term in MEMORY_ID]
    assert len(naming) / len(query_terms) >= recall._MIN_RELEVANCE
