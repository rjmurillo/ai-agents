#!/usr/bin/env python3
"""Live end-to-end security review: run the agent, assert it enumerated and ruled (issue #5619).

Issue #4781 shipped the security agent's enumeration contract in PR #5356 and
pinned it with structural tests. None runs a review and reads what comes back. A
pinned-reader tool that returned an empty diff instead of erroring would leave
every one of them green while the agent silently reviewed nothing.

This module writes a fixed two-file diff artifact, runs the REAL ``claude`` CLI as
the ``security`` agent against it, and asserts three observations the structural
tests cannot make:

  1. The agent read the artifact (a ``Read`` tool call on its path).
  2. The review names every changed file the artifact carries.
  3. The review ends in a verdict token from the agent's Completion Trigger
     Taxonomy (``APPROVED``, ``CONDITIONAL``, ``BLOCKED``), and that token is not
     the ``[BLOCKED] Cannot evaluate`` form, which is the agent admitting it
     reviewed nothing.

The negative control (acceptance criterion 5) runs the same review against an
empty artifact. Nothing is enumerable, so ``assert_review_covers_scope`` must
reject the output. The prompt never names the expected files, so the agent cannot
pass by echoing them.

Opt-in: the live tests spawn the real CLI, which needs authentication and spends
model credits. They run only when ``RUN_CLI_E2E=1`` is set and ``claude`` is on
PATH, and skip with a loud reason otherwise. They carry the ``claude`` marker but
not ``smoke``, so ``plugin-cli-smoke.yml`` (``-m "smoke and claude"``) does not
select them. ``test_security_review_probe.py`` pins the helpers with no CLI.

Run locally:
    RUN_CLI_E2E=1 uv run pytest tests/e2e/test_security_review_e2e.py -v -m claude
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from security_review_probe import (
    EXPECTED_CHANGED_FILES,
    FIXTURE_DIFF,
    REVIEW_TIMEOUT_SECONDS,
    assert_read_artifact,
    assert_review_covers_scope,
    review_text,
    run_security_review,
)

_RUN = os.environ.get("RUN_CLI_E2E") == "1"
# pytest-timeout's global 120s is shorter than one run, so each live test declares
# its own budget (same reasoning as `_cli_budget` in test_plugin_load_smoke.py).
_PYTEST_MARGIN_SECONDS = 30

requires_claude = pytest.mark.skipif(
    not (_RUN and shutil.which("claude")),
    reason="needs RUN_CLI_E2E=1 and the claude CLI on PATH (real auth + credits)",
)

_LIVE_BUDGET = pytest.mark.timeout(REVIEW_TIMEOUT_SECONDS + _PYTEST_MARGIN_SECONDS)


@pytest.mark.claude
@requires_claude
@_LIVE_BUDGET
def test_claude_security_review_enumerates_the_changeset_and_returns_a_verdict(
    tmp_path: Path,
) -> None:
    """The security agent reads a pinned diff, names its files, and rules (issue #5619)."""
    artifact = tmp_path / "review.diff"
    artifact.write_text(FIXTURE_DIFF, encoding="utf-8")

    events = run_security_review(artifact)

    assert_read_artifact(events, artifact)
    assert_review_covers_scope(review_text(events), EXPECTED_CHANGED_FILES)


@pytest.mark.claude
@requires_claude
@_LIVE_BUDGET
def test_claude_security_review_of_an_empty_artifact_fails_the_scope_assertion(
    tmp_path: Path,
) -> None:
    """Negative control: with nothing to enumerate, the same assertion must reject.

    The prompt names only the artifact path, never the expected files, so the
    review can name them only by reading them. An empty artifact holds none.
    """
    artifact = tmp_path / "empty.diff"
    artifact.write_text("", encoding="utf-8")

    events = run_security_review(artifact)

    with pytest.raises(AssertionError):
        assert_review_covers_scope(review_text(events), EXPECTED_CHANGED_FILES)
