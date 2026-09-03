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
from scripts.ci.spec_nonexecutable_criteria import (  # noqa: E402
    _ELISION,
    _MAX_CRITERION_CHARS,
)
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


def _longest_shared_run(secret: str, haystack: str, floor: int = 8) -> str:
    """Return the longest substring of `secret` of length >= floor in `haystack`.

    Checking for the whole token is not enough once truncation is in play,
    because the elision splits it and each half reaches the model on its own.
    """
    for size in range(len(secret), floor - 1, -1):
        for start in range(0, len(secret) - size + 1):
            fragment = secret[start : start + size]
            if fragment in haystack:
                return fragment
    return ""


class TestRedactionRunsBeforeTruncation:
    """Order matters: `_sanitize` elides the middle of an over-long criterion.

    A token straddling that cut is split into two fragments, and a split token
    matches neither its exact value nor any shape, so a redaction pass that ran
    only on the truncated entry had nothing to match. Measured before the fix,
    the entry rendered as `ghp_ABCDEF ... Z0123456789`, putting both halves in
    front of the model.
    """

    @staticmethod
    def _straddling_criterion() -> str:
        """A criterion whose token crosses the head cut and whose text exceeds the cap."""
        budget = _MAX_CRITERION_CHARS - len(_ELISION)
        head_cut = budget - budget // 3
        # Pad so the token starts just before the cut, then overrun the cap.
        lead = ("pytest " + "-k aaa " * 30)[: head_cut - 11] + " "
        command = lead + _GITHUB_PAT + " --zzz" + "y" * 40
        return f"- [x] `{command}` passes"

    def test_the_fixture_actually_straddles_the_cut(self) -> None:
        """Control: without this the test could pass on a criterion never truncated.

        A short criterion is redacted correctly by either ordering, so the
        fixture has to be shown to trigger truncation and to place the token
        across the cut before the assertions below mean anything.
        """
        budget = _MAX_CRITERION_CHARS - len(_ELISION)
        head_cut = budget - budget // 3
        cleaned = self._straddling_criterion().removeprefix("- [x] ")
        token_at = cleaned.index(_GITHUB_PAT)

        assert len(cleaned) > _MAX_CRITERION_CHARS, "fixture is not long enough to truncate"
        assert token_at < head_cut < token_at + len(_GITHUB_PAT), (
            f"token spans {token_at}..{token_at + len(_GITHUB_PAT)} which does not "
            f"cross the head cut at {head_cut}"
        )

    def test_no_fragment_of_a_straddling_token_reaches_the_reviewer(self, tmp_path: Path) -> None:
        context = _render(self._straddling_criterion(), tmp_path)

        assert "## Non-Executable Criteria Declaration" in context

        # Deliberately not asserting the elision marker is present. Redacting
        # first replaces a 40-character token with a 24-character marker, which
        # can pull the entry back under the cap, so requiring truncation here
        # would fail on correct behavior. The precondition that matters, that
        # the raw criterion would truncate across the token, is proven by
        # test_the_fixture_actually_straddles_the_cut.
        leaked = _longest_shared_run(_GITHUB_PAT, context)

        assert not leaked, (
            f"{leaked!r} is a {len(leaked)}-character run of the token and reached "
            f"the reviewer's context. Redaction must run on the full body before "
            f"truncation splits the token. Context:\n{context}"
        )
