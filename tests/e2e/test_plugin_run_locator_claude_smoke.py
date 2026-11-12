#!/usr/bin/env python3
"""Real Claude Code smoke for the ADR-121 plugin-root locator, inside a SKILL.md fence.

ADR-121 Rollout step 2 requires a real-CLI check that the committed locator
(``build/scripts/plugin_run_launcher.render_locator``) runs under Claude Code,
including when it sits in a fenced code block of a ``SKILL.md``. The host rewrites
the bare ``${CLAUDE_PLUGIN_ROOT}`` token inside such a block to the absolute plugin
directory. The locator then finds ``lib/ptk_run.py`` under that root and runs the
target script through it.

The test builds a throwaway plugin (``ptkloc``) with a byte copy of
``src/claude/lib/ptk_run.py``, a stub target that prints one JSON line, and two
skills that each hold one fenced command. It runs ``claude -p`` with a model call.

Cases:

* Positive: the ``runit`` skill holds the rendered locator. The stub's marker
  must reach a Bash tool result, with the argument ``one`` intact.
* Negative control 1: the ``runlegacy`` skill holds the legacy nested form. The
  host leaves it literal and the neutral cwd holds no ``.claude``, so the marker
  must not appear. The control also requires that a Bash call was attempted, so
  a model that refuses to run anything cannot pass it.
* Negative control 2 (foreign root): the positive skill runs with
  ``CLAUDE_PLUGIN_ROOT`` pointing at an empty directory with no resolver. The
  marker must still appear.

Gating: it needs ``RUN_CLI_E2E=1``, ``RUN_CLI_MODEL_E2E=1`` (a model call costs
quota), and ``claude`` on PATH. A missing piece skips with a reason that names it.
A blocked run (auth, quota, timeout) goes through ``smoke_skip_policy``. It is
not listed in ``plugin-cli-smoke.yml``.

Run locally:

    RUN_CLI_E2E=1 RUN_CLI_MODEL_E2E=1 env -u CLAUDE_PLUGIN_ROOT -u CLAUDE_PLUGIN_DATA \\
        uv run pytest tests/e2e/test_plugin_run_locator_claude_smoke.py \\
        -m "smoke and claude" -v

Stricter than the issue brief: the run uses ``--output-format stream-json`` so the
assertions read Bash tool results and not the model's paraphrase.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plugin_run_locator_smoke_support import (
    LEGACY_SKILL,
    POSITIVE_SKILL,
    Observation,
    _workspace,
    gate_skip_reason,
    run_with_retry,
    smoke_env,
)

_SKIP_REASON = gate_skip_reason(os.environ, shutil.which("claude"))
requires_model_run = pytest.mark.skipif(
    _SKIP_REASON is not None, reason=_SKIP_REASON or "gate open"
)


@pytest.mark.smoke
@pytest.mark.claude
@requires_model_run
def test_locator_in_a_skill_fence_runs_the_target(tmp_path: Path) -> None:
    plugin, cwd = _workspace(tmp_path)

    seen = run_with_retry(plugin, cwd, POSITIVE_SKILL, smoke_env(), Observation.marker_ran)

    assert seen.marker_ran(), f"the locator did not run the target.\n{seen.describe()}"


@pytest.mark.smoke
@pytest.mark.claude
@requires_model_run
def test_legacy_nested_form_in_a_skill_fence_does_not_run_the_target(tmp_path: Path) -> None:
    """Negative control 1: the host leaves the nested form literal, and cwd has no .claude."""
    plugin, cwd = _workspace(tmp_path)

    def attempted_or_leaked(obs: Observation) -> bool:
        return bool(obs.bash_commands) or obs.marker_anywhere()

    seen = run_with_retry(plugin, cwd, LEGACY_SKILL, smoke_env(), attempted_or_leaked)

    assert not seen.marker_anywhere(), f"the legacy form ran the target.\n{seen.describe()}"
    assert seen.bash_commands, (
        f"no Bash call was made, so the control is vacuous.\n{seen.describe()}"
    )


@pytest.mark.smoke
@pytest.mark.claude
@requires_model_run
def test_locator_survives_a_foreign_plugin_root_in_the_environment(tmp_path: Path) -> None:
    """Negative control 2: a foreign CLAUDE_PLUGIN_ROOT with no resolver must not win."""
    plugin, cwd = _workspace(tmp_path)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    env = smoke_env({"CLAUDE_PLUGIN_ROOT": str(foreign)})

    seen = run_with_retry(plugin, cwd, POSITIVE_SKILL, env, Observation.marker_ran)

    assert seen.marker_ran(), f"a foreign root broke the locator.\n{seen.describe()}"
