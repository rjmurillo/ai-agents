"""Wiring tests: the staged markdown job and the pre-PR sequence reach check_md_links.

A unit test of the checker cannot show that a call site invokes it, so these
drive ``pre_pr.main`` and the gate registry, each with a control that differs
only in the condition under test.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.validation import pre_pr, pre_pr_sequence


def _run(
    monkeypatch: pytest.MonkeyPatch, skip_autofix: str | None, files: list[str]
) -> tuple[int, list]:
    if skip_autofix is None:
        monkeypatch.delenv("SKIP_AUTOFIX", raising=False)
    else:
        monkeypatch.setenv("SKIP_AUTOFIX", skip_autofix)
    calls: list = []

    def fake_links(_root, passed, *_a, **_k) -> bool:
        calls.append(passed)
        return False

    with (
        patch.object(pre_pr, "validate_markdown_lint", return_value=True),
        patch.object(pre_pr, "validate_staged_md_links", side_effect=fake_links),
    ):
        code = pre_pr.main(["--markdown-lint-only", "--", *files])
    return code, calls


def test_check_pass_runs_the_link_check_and_its_failure_fails_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code, calls = _run(monkeypatch, "1", ["docs/a.md"])

    assert calls == [["docs/a.md"]]
    assert code == 1


def test_autofix_pass_skips_the_link_check(monkeypatch: pytest.MonkeyPatch) -> None:
    code, calls = _run(monkeypatch, None, ["docs/a.md"])

    assert calls == []
    assert code == 0


def test_pre_pr_sequence_registers_the_gate_after_adr_links() -> None:
    names = [gate.name for gate in pre_pr_sequence._SEQUENCE]

    assert names.index("Markdown Link Resolution") == names.index("ADR Link Resolution") + 1
