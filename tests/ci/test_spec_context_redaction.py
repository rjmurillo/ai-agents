"""Criterion text is redacted before it reaches the reviewer (CWE-200).

`scripts/ci/build_ai_review_context.py` redacts the PR title and body before
handing them to a model. The Non-Executable Criteria Declaration carries a
slice of that same author-controlled body to the same model by a different
route, and that route had no redaction, so a token written into an acceptance
criterion arrived unredacted while the identical bytes elsewhere in the body
were masked.

The criterion text is bounded and structure-stripped by `_sanitize`, which is
about injection shape rather than secrecy: neither the length cap nor the
control-character strip touches a token.

These are the shapes a criterion plausibly carries, since the whole point of
the classifier is that these criteria quote commands someone ran.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from scripts.ci.spec_prepare_context import run  # noqa: E402

_GITHUB_PAT = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
_BEARER = "sk-livesecret0123456789abcd"


def _render(criterion: str, tmp_path: Path) -> str:
    """Return the spec context built from a body carrying `criterion`."""
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("content", encoding="utf-8")
    out_file = tmp_path / "out.txt"
    env = {
        "SPEC_FILE": str(spec_file),
        "INCREMENTAL_SCOPE": "",
        "PR_BODY": f"## Acceptance criteria\n\n{criterion}\n",
        "GITHUB_OUTPUT": str(out_file),
    }

    with patch.dict(os.environ, env):
        assert run() == 0

    return out_file.read_text(encoding="utf-8")


class TestClassifiedCriteriaAreRedacted:
    @pytest.mark.parametrize(
        ("secret", "criterion"),
        [
            (_GITHUB_PAT, f"- [x] `pytest --token {_GITHUB_PAT}` passes"),
            (_AWS_KEY, f"- [x] `pytest --key {_AWS_KEY}` passes"),
            (_BEARER, f"- [x] `pytest -H 'Authorization: Bearer {_BEARER}'` passes"),
        ],
    )
    def test_a_token_in_a_criterion_does_not_reach_the_reviewer(
        self, secret: str, criterion: str, tmp_path: Path
    ) -> None:
        context = _render(criterion, tmp_path)

        assert "## Non-Executable Criteria Declaration" in context, (
            "The criterion was not classified, so nothing was injected and "
            "this assertion would pass without redacting anything."
        )
        assert secret not in context, (
            f"{secret!r} reached the reviewer's additional context verbatim. Context:\n{context}"
        )

    def test_the_criterion_survives_redaction_as_a_readable_entry(self, tmp_path: Path) -> None:
        """Redaction must not eat the entry it is protecting.

        The declaration exists so the reviewer can match a named criterion
        against the PR body. A redactor that dropped the line, or mangled the
        command out of recognition, would satisfy the assertions above while
        destroying what the block is for.
        """
        context = _render(f"- [x] `pytest --token {_GITHUB_PAT}` passes", tmp_path)

        entry = next(line for line in context.splitlines() if line.startswith("- `pytest"))

        assert entry.endswith("` passes")
        assert "[redacted" in entry


class TestRedactionDoesNotFireOnOrdinaryCriteria:
    def test_an_ordinary_command_criterion_is_unchanged(self, tmp_path: Path) -> None:
        """Control: redaction is scoped to credential shapes.

        Without this, a redactor that masked everything would pass every
        assertion above.
        """
        context = _render("- [x] `uv run python scripts/validation/pre_pr.py` passes", tmp_path)

        assert "- `uv run python scripts/validation/pre_pr.py` passes" in context
        assert "redacted" not in context
