"""The response-size comment in eval-rule-activation.py names the right providers.

Follow-up to #6686: claude-cli reports output_tokens since #6721, so the
comment may name only providers that send no usage record.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestResponseCharsComment:
    """The size-signal comment names only providers that report no usage (follow-up to #6686)."""

    EVAL_SRC = REPO_ROOT / "scripts" / "eval" / "eval-rule-activation.py"

    def _comment(self) -> str:
        lines = self.EVAL_SRC.read_text(encoding="utf-8").splitlines()
        start = next(i for i, ln in enumerate(lines) if "Length of the response text" in ln)
        block = []
        for ln in lines[start:]:
            if not ln.strip().startswith("#"):
                break
            block.append(ln.strip())
        return " ".join(block)

    def test_comment_does_not_claim_claude_cli_lacks_usage(self):
        comment = self._comment()
        assert "subscription CLI provider returns" not in comment
        assert "claude-cli reports output_tokens" in comment

    @pytest.mark.parametrize("module", ["_codex_cli.py", "_copilot_cli.py"])
    def test_providers_named_in_the_comment_report_no_output_tokens(self, module):
        assert module.removesuffix(".py").lstrip("_").replace("_", "-") in self._comment()
        source = (REPO_ROOT / "scripts" / "eval" / module).read_text(encoding="utf-8")
        assert "self.output_tokens" not in source

    def test_claude_cli_sets_output_tokens(self):
        source = (REPO_ROOT / "scripts" / "eval" / "_claude_cli.py").read_text(encoding="utf-8")
        assert "self.output_tokens = self._read_output_tokens(payload)" in source
