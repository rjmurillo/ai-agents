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
deliberately narrower. It fires only when the named command is itself the
subject of the result verb, in the criterion's leading clause:

    `pytest` passes                                   -> fires
    the helper passes the flag to `run_gh`            -> no command as subject
    `pre_pr.py` passes the changed-file list to ruff  -> transitive, not a run
    the wrapper returns zero when `pytest` passes     -> subordinate clause
    the fallback passes when `ruff` reports an error  -> subordinate clause

The last two shapes are behavioral contracts on the code under review, which a
diff reviewer can and must check. Scanning for a command and for a result verb
independently anywhere in one bullet classified them as unverifiable and
dropped them from the gate.

Cutting at the first subordinator also costs a real claim written with a
leading adverbial ("after the rename, `pytest` passes"). That trade is
deliberate. Under-firing is safe, because the prompt rule still tells the
reviewer to treat an unexecutable criterion as N/A when no declaration names
it. Over-firing is not safe: it would silently drop a real criterion from the
gate.

Criterion text reaches the reviewer only after `_normalize` strips control
characters and collapses newlines and `_sanitize` drops leading markdown
structure and truncates.
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
# The whole heading title, not a substring of it. A prefix or suffix word makes
# a different section: "Acceptance Criteria Verification" holds evidence and
# "Non-Acceptance Criteria" holds what the PR is not claiming, and treating
# either one's bullets as requirements misreads the document. Trailing `#` is
# Markdown's optional closing fence on an ATX heading.
_ACCEPTANCE_TITLE = re.compile(r"(?i)acceptance\s+criteri(?:a|on)\s*:?\s*#*\s*")
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

# What may sit between the command span and the result verb that governs it.
# Only enough to carry "Run `make build` and it completes successfully"; any
# wider and the verb stops belonging to the command.
_RESULT_BRIDGE = re.compile(r"(?i)[\s,:;]*(?:(?:and|then|it|still)\s+)*")

# A subordinator opens a clause that describes a condition, not the deliverable.
# "The wrapper returns zero when `pytest` passes" asserts what the wrapper must
# do; the `pytest` run is the premise. Only the leading clause can carry a
# command-execution claim, so everything from the first subordinator on is cut
# before the command is looked for.
_SUBORDINATOR = re.compile(
    r"(?i)\b(?:after|although|assuming|because|before|even|given|if|once"
    r"|provided|since|so|though|unless|until|when|whenever|while)\b"
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
        if _ACCEPTANCE_TITLE.fullmatch(heading.group(2)):
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


def _leading_clause(text: str) -> str:
    """Return `text` up to its first subordinator, where the deliverable is."""
    subordinator = _SUBORDINATOR.search(text)
    return text if subordinator is None else text[: subordinator.start()]


def _command_span_ends(text: str) -> list[int]:
    """Offsets just past each inline code span that reads as a runnable command."""
    ends: list[int] = []
    for span in _CODE_SPAN.finditer(text):
        token = span.group(1).strip().lstrip("$>").strip()
        if not token:
            continue
        first = token.split()[0].lower().lstrip("./")
        if first in _COMMAND_LAUNCHERS or first.endswith(_SCRIPT_SUFFIXES):
            ends.append(span.end())
    return ends


def _asserts_execution_result(text: str, command_end: int) -> bool:
    """True when a result verb governs the command that ended at `command_end`.

    The verb has to follow the command with nothing but a short bridge between
    them, so that the command is the thing said to have passed. A verb sitting
    anywhere else in the criterion belongs to some other subject.
    """
    bridge = _RESULT_BRIDGE.match(text, command_end)
    if bridge is None:
        return False
    verb = _RESULT_VERB.match(text, bridge.end())
    if verb is None:
        return False
    return _RESULT_TAIL.match(text, verb.end()) is not None


def _is_command_execution_claim(text: str) -> bool:
    """True when `text` claims how a run turned out, not what the code does."""
    clause = _leading_clause(text)
    return any(_asserts_execution_result(clause, end) for end in _command_span_ends(clause))


def _normalize(text: str) -> str:
    """Collapse a criterion to one line of printable characters.

    Classification runs on the normalized text, not the raw bullet: a control
    character between the command and its result verb would otherwise break the
    adjacency `_asserts_execution_result` depends on.
    """
    return " ".join(_CONTROL_CHARS.sub(" ", text).split())


def _sanitize(text: str) -> str:
    """Flatten a normalized criterion to one bounded, structure-free line."""
    cleaned = _LEADING_MARKUP.sub("", text)
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
        normalized = _normalize(bullet)
        if not _is_command_execution_claim(normalized):
            continue
        cleaned = _sanitize(normalized)
        if cleaned and cleaned not in found:
            found.append(cleaned)
        if len(found) >= _MAX_CRITERIA:
            break

    return found
