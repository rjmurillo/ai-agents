"""AC-DUP-5: Shared reactions retain fallback ordering and diagnostics."""

from __future__ import annotations

import subprocess

import pytest

from scripts.github_core.comment_processing import (
    add_comment_reaction,
    format_wontfix_reply,
    report_comment_action,
)


@pytest.mark.parametrize("successful_endpoint", ["pulls", "issues", None])
def test_reaction_fallback_uses_the_existing_endpoints(
    successful_endpoint: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", ReactionTransport(successful_endpoint, calls))

    assert add_comment_reaction("o", "r", 7) == (successful_endpoint is not None)
    expected = ["pulls"] if successful_endpoint == "pulls" else ["pulls", "issues"]
    assert [call[2] for call in calls] == [
        f"repos/o/r/{endpoint}/comments/7/reactions" for endpoint in expected
    ]


class ReactionTransport:
    def __init__(self, successful_endpoint: str | None, calls: list[list[str]]) -> None:
        self.endpoint = successful_endpoint
        self.calls = calls

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        success = self.endpoint is not None and f"/{self.endpoint}/" in argv[2]
        return subprocess.CompletedProcess(argv, 0 if success else 1, "", "not found")


def test_wontfix_reply_preserves_the_existing_text() -> None:
    assert format_wontfix_reply("Reason") == (
        "Thank you for the feedback. After review, "
        "we've decided not to implement this change:\n\nReason"
    )


@pytest.mark.parametrize(
    "classification,expected",
    [
        ("stale", "  Stale comment needs manual resolution (thread ID required)\n"),
        ("question", "  Needs human response: Summary\n"),
        ("quick-fix", "  Action needed: Action - Summary\n"),
        ("standard", "  Action needed: Action - Summary\n"),
        ("strategic", "  Action needed: Action - Summary\n"),
        ("unknown", "  Unknown classification 'unknown', skipping\n"),
    ],
)
def test_nonreply_messages_remain_unchanged(
    classification: str, expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    report_comment_action(classification, {"action": "Action", "summary": "Summary"})
    assert capsys.readouterr().out == expected
