"""Step 0 of the pr-review skill must stop on unverifiable command tokens.

Audit #6506 rows merge-pr-automation-16 and -17: the Step 0 wording is the
gate. Exit 0 with a non-empty `unverifiable_command_tokens` list stops the
run, and `transport_preflight.command_key` is read from the config file the
verifier just checked. These tests pin that wording in every rendered copy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW = REPO_ROOT / ".claude" / "skills" / "pr-review" / "SKILL.md"
PROMPT = REPO_ROOT / ".github" / "prompts" / "pr-review.prompt.md"
COPILOT_REVIEW = REPO_ROOT / "src" / "copilot-cli" / "skills" / "pr-review" / "SKILL.md"


class TestStepZeroStopsOnUnverifiableTokens:
    @pytest.mark.parametrize("path", [REVIEW, COPILOT_REVIEW, PROMPT])
    def test_non_empty_unverifiable_tokens_stop_the_run(self, path):
        body = path.read_text(encoding="utf-8")
        assert "A non-empty list stops the run" in body
        assert "empty `unverifiable_command_tokens` list" in body

    @pytest.mark.parametrize("path", [REVIEW, COPILOT_REVIEW, PROMPT])
    def test_command_key_is_read_from_the_verified_config(self, path):
        body = path.read_text(encoding="utf-8")
        step_1 = body.index("### Step 1")
        window = body[body.rindex("Only after exit 0", 0, step_1) : step_1]
        assert "`$PR_REVIEW_CONFIG` file just verified" in window
        assert "resolved once" in window
        assert "from config" not in window

    @pytest.mark.parametrize("path", [REVIEW, COPILOT_REVIEW, PROMPT])
    def test_old_continue_on_exit_zero_wording_is_gone(self, path):
        body = path.read_text(encoding="utf-8")
        assert "Only after exit 0, run `transport_preflight.command_key` from config" not in body
