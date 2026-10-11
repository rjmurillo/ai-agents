"""Pins the claude.yml concurrency group that ADR-114 relies on.

`claude-response` runs in `agent-claude`, which requires a reviewer, so every
authorized event waits for a click. Without a group, waiting runs pile up. The
group sits on the job, after `check-authorization`, so an event that fails
authorization skips the job by its `if:` (inferred, not observed).

A comment or review is a person's request, so it is keyed on its own id and is
never replaced. Push, label, assign, and issue events share one key per issue
or pull request. `cancel-in-progress` is false: GitHub keeps one running and
one pending job per group and a newer pending job replaces the older one
(docs.github.com, "Control the concurrency of workflows and jobs"), so the
thread queue stays short without cutting off a Claude run that is already
working.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "claude.yml"
# Each branch of the group expression, in evaluation order.
BRANCHES = (
    "github.event.comment.id && format('comment-{0}', github.event.comment.id)",
    "github.event.review.id && format('review-{0}', github.event.review.id)",
    "format('thread-{0}', github.event.issue.number"
    " || github.event.pull_request.number || github.run_id)",
)


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def group(workflow: dict[str, Any]) -> str:
    return workflow["jobs"]["claude-response"]["concurrency"]["group"]


def test_the_workflow_has_no_run_level_group(workflow: dict[str, Any]) -> None:
    """A run-level group would let a bot comment cancel an authorized run."""
    assert "concurrency" not in workflow


def test_check_authorization_is_outside_the_group(workflow: dict[str, Any]) -> None:
    assert "concurrency" not in workflow["jobs"]["check-authorization"]


def test_claude_response_never_cancels_running_work(workflow: dict[str, Any]) -> None:
    concurrency = workflow["jobs"]["claude-response"]["concurrency"]
    assert concurrency["cancel-in-progress"] is False


def test_the_group_is_one_expression_with_a_fixed_prefix(group: str) -> None:
    assert group.startswith("claude-response-${{ ")
    assert group.endswith(" }}")
    assert group.count("${{") == 1


def test_the_branches_appear_in_evaluation_order(group: str) -> None:
    positions = [group.index(branch) for branch in BRANCHES]
    assert positions == sorted(positions), "comment, then review, then the thread fallback"


@pytest.mark.parametrize("branch", BRANCHES)
def test_each_branch_is_present(group: str, branch: str) -> None:
    """Negative control: dropping a branch would merge distinct requests or threads."""
    assert branch in group


@pytest.mark.parametrize("prefix", ["'comment-{0}'", "'review-{0}'", "'thread-{0}'"])
def test_each_key_family_has_its_own_prefix(group: str, prefix: str) -> None:
    """A comment id and an issue number can be equal; the prefix keeps them apart."""
    assert group.count(prefix) == 1


# A minimal evaluator for the expression subset the group uses: property paths,
# string literals, `format('...{0}', x)`, `&&` and `||`. That `||` returns an
# operand is documented by the concurrency example `github.head_ref ||
# github.run_id` (docs.github.com, "Control the concurrency of workflows and
# jobs"). That `&&` returns its right operand and binds tighter than `||` is the
# common `a && b || c` idiom; it is INFERRED, not documented on the operators
# page, so this evaluator encodes the assumption the group relies on.
_TOKEN = re.compile(r"\s*(\|\||&&|\(|\)|,|'[^']*'|[A-Za-z_][\w.\-]*)")


def _tokens(text: str) -> list[str]:
    out, pos = [], 0
    while pos < len(text.rstrip()):
        match = _TOKEN.match(text, pos)
        assert match, f"unexpected text at {text[pos:]!r}"
        out.append(match.group(1))
        pos = match.end()
    return out


def _evaluate(expression: str, context: dict[str, Any]) -> Any:
    tokens = _tokens(expression)

    def primary(i: int) -> tuple[Any, int]:
        tok = tokens[i]
        if tok.startswith("'"):
            return tok[1:-1], i + 1
        if tok == "format":
            assert tokens[i + 1] == "("
            template, i = disjunction(i + 2)
            assert tokens[i] == ","
            value, i = disjunction(i + 1)
            assert tokens[i] == ")"
            return template.replace("{0}", str(value)), i + 1
        node: Any = context
        for part in tok.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        return node, i + 1

    def conjunction(i: int) -> tuple[Any, int]:
        value, i = primary(i)
        while i < len(tokens) and tokens[i] == "&&":
            right, i = primary(i + 1)
            value = right if value else value
        return value, i

    def disjunction(i: int) -> tuple[Any, int]:
        value, i = conjunction(i)
        while i < len(tokens) and tokens[i] == "||":
            right, i = conjunction(i + 1)
            value = value or right
        return value, i

    value, end = disjunction(0)
    assert end == len(tokens), f"unparsed tail {tokens[end:]}"
    return value


def _key(group: str, event: dict[str, Any], run_id: int = 999) -> str:
    inner = group[len("claude-response-${{ ") : -len(" }}")]
    return "claude-response-" + str(
        _evaluate(inner, {"github": {"event": event, "run_id": run_id}})
    )


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"issue": {"number": 7}, "comment": {"id": 501}}, "comment-501"),
        ({"pull_request": {"number": 7}, "comment": {"id": 502}}, "comment-502"),
        ({"pull_request": {"number": 7}, "review": {"id": 601}}, "review-601"),
        ({"pull_request": {"number": 7}}, "thread-7"),
        ({"issue": {"number": 7}}, "thread-7"),
        ({}, "thread-999"),
    ],
    ids=[
        "issue_comment",
        "pull_request_review_comment",
        "pull_request_review",
        "pull_request",
        "issues",
        "workflow_dispatch",
    ],
)
def test_each_event_shape_gets_its_key(group: str, event: dict[str, Any], expected: str) -> None:
    assert _key(group, event) == f"claude-response-{expected}"


def test_a_comment_never_shares_a_key_with_its_thread(group: str) -> None:
    """A push and a comment on the same pull request must not replace each other."""
    comment = _key(group, {"pull_request": {"number": 7}, "comment": {"id": 7}})
    push = _key(group, {"pull_request": {"number": 7}})
    assert comment != push


def test_two_comments_on_one_thread_get_distinct_keys(group: str) -> None:
    first = _key(group, {"issue": {"number": 7}, "comment": {"id": 1}})
    second = _key(group, {"issue": {"number": 7}, "comment": {"id": 2}})
    assert first != second


def test_the_evaluator_returns_operands_not_booleans() -> None:
    """Negative control: a boolean-returning evaluator would make every key True."""
    assert _evaluate("a && 'x' || 'y'", {"a": 1}) == "x"
    assert _evaluate("a && 'x' || 'y'", {"a": None}) == "y"


def test_the_job_declares_its_authorization_gate(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["claude-response"]
    assert job["needs"] == "check-authorization"
    assert "authorized == 'true'" in job["if"]
