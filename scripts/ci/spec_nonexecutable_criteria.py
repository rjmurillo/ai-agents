"""Find acceptance criteria that assert the outcome of running a command.

Issue #5366. The `Validate Spec Coverage` check feeds a PR's own
`## Acceptance criteria` list to a diff-only reviewer that has no shell.
`scripts/ci/build_ai_review_context.py` injects the PR body verbatim as
`## PR Description`, so a criterion phrased as a command-execution claim (for
example "``uv run python scripts/validation/pre_pr.py`` passes") is
unsatisfiable by construction. The reviewer marks it
`[~] PARTIALLY SATISFIED`, and `PARTIAL` is a failure token in
`scripts/ai_review_common/verdict.py:216`, quoted verbatim:

    _COMPLETENESS_FAILURES = frozenset({"CRITICAL_FAIL", "FAIL", "PARTIAL", "NEEDS_REVIEW"})

so the whole gate fails closed on every re-run no matter how correct the
implementation is. PR #5350 hit exactly this: 7 of 8 criteria SATISFIED, one
PARTIAL for a `pre_pr.py`-passes criterion, `VERDICT: PARTIAL`, check red.

`scripts/ci/spec_prepare_context.py` renders this module's output as a
`## Non-Executable Criteria Declaration`, mirroring the
`## Incremental Scope Declaration` escape hatch built for issue #2255, and
`.github/prompts/spec-check-completeness.md` tells the reviewer to mark the
named criteria `N/A` and exclude them from the completeness percentage.

This repo's own PR template already puts that evidence elsewhere: the
`uv run python scripts/validation/pre_pr.py` checkbox lives under
`## Author Pre-flight`, not under `## Acceptance criteria`.

Stricter/looser/different than the prompt rule it feeds: this detector is
deliberately narrower. It fires only when a criterion BOTH names a runnable
command inside an inline code span AND asserts an execution result in
intransitive position, so "the helper passes the flag to ``run_gh``" does not
match. Under-firing is safe, because the prompt rule still tells the reviewer
to treat an unexecutable criterion as N/A when no declaration names it.
Over-firing is not safe: it would silently drop a real criterion from the gate.

Criterion text reaches the reviewer only after `_sanitize` strips control
characters, collapses newlines, drops leading markdown structure, and truncates.
That bounds the shape of the injected block; it does not make the text
trustworthy, and it does not need to, because
`build_ai_review_context.py` already hands the reviewer the same PR body
verbatim.
"""

from __future__ import annotations

import re

# Bound the injected block. A PR body is author-controlled and unbounded; the
# declaration is a hint for the reviewer, not a transcript of the PR.
_MAX_CRITERIA = 20
_MAX_CRITERION_CHARS = 200

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_ACCEPTANCE_TITLE = re.compile(r"(?i)acceptance\s+criteri(?:a|on)")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX~-]\]\s*)?(?P<text>.*)$")
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LEADING_MARKUP = re.compile(r"^[#>\s]+")

# First token of an inline code span that makes the span a command rather than
# a symbol or a path reference.
_COMMAND_LAUNCHERS = frozenset(
    {
        "bash",
        "cargo",
        "docker",
        "dotnet",
        "gh",
        "git",
        "go",
        "invoke-pester",
        "lefthook",
        "make",
        "mypy",
        "node",
        "npm",
        "npx",
        "pester",
        "pip",
        "pnpm",
        "poetry",
        "pwsh",
        "pytest",
        "python",
        "python3",
        "ruff",
        "semgrep",
        "sh",
        "tox",
        "uv",
        "uvx",
        "yarn",
    }
)
_SCRIPT_SUFFIXES = (".py", ".ps1", ".sh", ".bat", ".cmd")

# An assertion about how a run turned out.
_RESULT_VERB = re.compile(
    r"(?i)\b(?:"
    r"pass(?:es|ed)?"
    r"|succeed(?:s|ed)?"
    r"|runs?\s+clean(?:ly)?"
    r"|completes?\s+successfully"
    r"|exits?\s+(?:0|zero)"
    r"|returns?\s+(?:0|zero)"
    r"|is\s+green"
    r"|reports?\s+no\s+\w+"
    r")\b"
)

# The result verb must sit in intransitive position: at the end of the
# criterion, or followed by an adverbial. "passes" with a direct object after
# it ("passes the flag to X") is ordinary prose about the code, not a claim
# about a run, and must not fire. `Pattern.match(text, pos)` anchors this, so
# it carries no `^`: in a non-multiline pattern `^` matches the start of the
# string, not the start position handed to match().
_RESULT_TAIL = re.compile(
    r"(?i)(?:"
    r"[\s.;,:!?)\]}]*$"
    r"|\s+(?:locally|clean(?:ly)?|green|in\s+ci|on\s+ci|with|without"
    r"|after|before|again|for|when)\b"
    r")"
)


def _acceptance_lines(pr_body: str) -> list[str]:
    """Return the non-heading lines under every Acceptance Criteria heading."""
    collected: list[str] = []
    inside = False
    level = 0

    for line in pr_body.splitlines():
        heading = _HEADING.match(line)
        if heading is None:
            if inside:
                collected.append(line)
            continue
        depth = len(heading.group(1))
        if _ACCEPTANCE_TITLE.search(heading.group(2)):
            inside = True
            level = depth
        elif inside and depth <= level:
            inside = False

    return collected


def _bullets(lines: list[str]) -> list[str]:
    """Return list items from `lines`, folding wrapped continuation lines in."""
    bullets: list[str] = []
    open_index = -1

    for line in lines:
        item = _BULLET.match(line)
        if item is not None:
            bullets.append(item.group("text").strip())
            open_index = len(bullets) - 1
            continue
        if not line.strip():
            open_index = -1
            continue
        if open_index >= 0:
            bullets[open_index] = f"{bullets[open_index]} {line.strip()}"

    return [bullet for bullet in bullets if bullet]


def _names_command(text: str) -> bool:
    """True when an inline code span in `text` reads as a runnable command."""
    for span in _CODE_SPAN.findall(text):
        token = span.strip().lstrip("$>").strip()
        if not token:
            continue
        first = token.split()[0].lower().lstrip("./")
        if first in _COMMAND_LAUNCHERS or first.endswith(_SCRIPT_SUFFIXES):
            return True
    return False


def _asserts_execution_result(text: str) -> bool:
    """True when `text` claims how a run turned out, not what the code does."""
    return any(_RESULT_TAIL.match(text, match.end()) for match in _RESULT_VERB.finditer(text))


def _sanitize(text: str) -> str:
    """Flatten a criterion to one bounded, structure-free line."""
    cleaned = _CONTROL_CHARS.sub(" ", text)
    cleaned = " ".join(cleaned.split())
    cleaned = _LEADING_MARKUP.sub("", cleaned)
    if len(cleaned) > _MAX_CRITERION_CHARS:
        cleaned = cleaned[: _MAX_CRITERION_CHARS - 3].rstrip() + "..."
    return cleaned


def find_nonexecutable_criteria(pr_body: str) -> list[str]:
    """Return acceptance criteria that a shell-less reviewer cannot verify.

    Order follows the PR body. Duplicates are dropped and the result is capped
    at `_MAX_CRITERIA` entries.
    """
    if not pr_body:
        return []

    found: list[str] = []
    for bullet in _bullets(_acceptance_lines(pr_body)):
        if not (_names_command(bullet) and _asserts_execution_result(bullet)):
            continue
        cleaned = _sanitize(bullet)
        if cleaned and cleaned not in found:
            found.append(cleaned)
        if len(found) >= _MAX_CRITERIA:
            break

    return found
