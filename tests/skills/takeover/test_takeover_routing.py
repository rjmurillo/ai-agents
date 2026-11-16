"""Autoplan routes takeover requests to the takeover skill, and nothing else to it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if _TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_SKILLS_ROOT = REPO_ROOT / ".claude" / "skills"

resolver = import_skill_script(".claude/skills/autoplan/scripts/resolve_route.py")
REAL_NAMESPACE = resolver._default_namespace(REAL_SKILLS_ROOT)
TAKEOVER_ROUTE = f"{REAL_NAMESPACE}:takeover"


def _real_roots() -> list[object]:
    return [resolver.Root(path=REAL_SKILLS_ROOT, namespace=REAL_NAMESPACE)]


@pytest.mark.parametrize(
    "request_text",
    [
        "Take over PR 123 from the other agent.",
        "Take over this branch and finish it.",
        "Take over this thread.",
        "Finish someone else's abandoned PR.",
    ],
)
def test_takeover_requests_route_to_takeover(request_text: str) -> None:
    result = resolver.resolve(request_text, _real_roots())

    assert result["kind"] == "specialist"
    assert result["route"] == TAKEOVER_ROUTE
    assert result["candidates"] == [TAKEOVER_ROUTE]


@pytest.mark.parametrize(
    "request_text",
    [
        "Resolve merge conflicts on this PR.",
        "Reply to the open review comments on my own PR.",
    ],
)
def test_non_takeover_requests_do_not_route_to_takeover(request_text: str) -> None:
    result = resolver.resolve(request_text, _real_roots())

    assert result["route"] != TAKEOVER_ROUTE
    assert TAKEOVER_ROUTE not in result["candidates"]
