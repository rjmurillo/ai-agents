"""Hook: user_prompt_transformed - Auto-recall relevant memories for Copilot CLI.

Copilot CLI drops all output from config-file ``userPromptSubmitted`` hooks,
so the Claude Code recall path is inert there (issue #4727). The documented
channel is ``userPromptTransformed``: this hook prints one
``{"modifiedTransformedPrompt": ...}`` object that appends the
``<memory-context>`` block to the model-facing prompt. The event itself
selects the host.

The only environment check skips recall inside the Copilot cloud agent. That
agent runs unattended with pre-approved tools and reads .serena/memories from
a checked-out branch (ADR-068 amendment for issue #4727).

Hook Type: userPromptTransformed (Copilot CLI). Imported by
``invoke_memory_recall.py --copilot-transformed``; not run directly.
Exit Codes:
    0 = always. Printing nothing leaves the model-facing content unchanged.
"""

from __future__ import annotations

import json
import os
import sys

from .user_prompt_submit_memory import recall_block

# The GitHub hook reference documents these as set only inside the Copilot
# cloud agent sandbox.
_CLOUD_AGENT_ENV_VARS = ("COPILOT_AGENT_PROMPT", "GITHUB_COPILOT_API_TOKEN")


def main() -> int:
    """Append recall to ``transformedPrompt`` as one JSON object, or print nothing.

    Prints nothing when recall finds no match, the payload lacks a usable
    ``prompt`` or ``transformedPrompt``, or the hook runs in the cloud agent.
    """
    if any(os.environ.get(name) for name in _CLOUD_AGENT_ENV_VARS):
        return 0

    payload = _read_payload()
    transformed = payload.get("transformedPrompt")
    prompt = payload.get("prompt")
    if not isinstance(transformed, str) or not transformed.strip():
        return 0
    if not isinstance(prompt, str):
        return 0

    results = recall_block(prompt)
    if results:
        print(json.dumps({"modifiedTransformedPrompt": f"{transformed}\n\n{results}"}))

    return 0


def _read_payload() -> dict[str, object]:
    """Read the hook payload from stdin as a JSON object, or return {}."""
    try:
        data = json.loads(sys.stdin.read())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
