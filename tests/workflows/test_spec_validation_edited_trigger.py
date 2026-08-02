"""Contract test: ai-spec-validation.yml must re-run when the PR body is edited.

Issue #4213: the workflow derives required-check scope from the PR body. If the
body changes after the gate passed, the verdict is stale. The fix is adding
``edited`` to the ``pull_request`` event types. This test asserts that fix is
still present so it cannot be silently removed.

The concurrency group uses ``cancel-in-progress: true``. That is safe for
``edited`` because an ``edited`` event on a PR whose body has changed should
cancel the previous run (which used the stale body) and start fresh. The test
also asserts the ``cancel-in-progress`` flag remains set so a future PR cannot
convert the group to ``cancel-in-progress: false`` and then drop ``edited``
silently.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ai-spec-validation.yml"


@lru_cache(maxsize=1)
def _load() -> dict[Any, Any]:
    # PyYAML can produce non-string keys (e.g. the 'on:' key parses as boolean True).
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), f"expected mapping, got {type(doc).__name__}"
    return doc


def _on_block() -> dict[str, Any]:
    # PyYAML parses the bare 'on:' key as the boolean True, not the string "on".
    doc = _load()
    result = doc.get("on") or doc.get(True)
    assert isinstance(result, dict), f"expected mapping under 'on', got {type(result).__name__}"
    return result


def test_edited_trigger_present() -> None:
    """``edited`` must appear in pull_request.types so body edits re-run the gate."""
    types = _on_block()["pull_request"]["types"]
    assert "edited" in types, (
        f"ai-spec-validation.yml is missing 'edited' in pull_request.types. "
        f"Without it, changing the PR body after the check passes leaves a stale verdict. "
        f"Current types: {types}"
    )


def test_existing_triggers_unchanged() -> None:
    """``opened``, ``synchronize``, and ``reopened`` must still be present."""
    types = _on_block()["pull_request"]["types"]
    for required in ("opened", "synchronize", "reopened"):
        assert required in types, (
            f"ai-spec-validation.yml: pull_request trigger '{required}' was removed. "
            f"Current types: {types}"
        )


def test_concurrency_cancel_in_progress() -> None:
    """cancel-in-progress must be True so the stale run is replaced, not queued."""
    concurrency = _load()["concurrency"]
    assert concurrency.get("cancel-in-progress") is True, (
        f"ai-spec-validation.yml: concurrency.cancel-in-progress must be true. "
        f"Without it, an edited-body rerun queues behind the stale run. "
        f"Actual concurrency block: {concurrency}"
    )
