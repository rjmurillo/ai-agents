"""Find acceptance criteria that assert the outcome of running a command.

Issue #5366. The `Validate Spec Coverage` check feeds a PR's own
`## Acceptance criteria` list to a diff-only reviewer that has no shell.
`scripts/ci/build_ai_review_context.py` injects the PR body verbatim as
`## PR Description`, so a criterion phrased as a command-execution claim (for
example "``uv run python scripts/validation/pre_pr.py`` passes") is
unsatisfiable by construction. The reviewer marks it
`[~] PARTIALLY SATISFIED`, and `PARTIAL` is a failure token in
`_COMPLETENESS_FAILURES` in `scripts/ai_review_common/verdict.py`, quoted
verbatim:

    _COMPLETENESS_FAILURES = frozenset({"CRITICAL_FAIL", "FAIL", "PARTIAL", "NEEDS_REVIEW"})

so the whole gate fails closed on every re-run no matter how correct the
implementation is. PR #5350 hit exactly this: 7 of 8 criteria SATISFIED, one
PARTIAL for a `pre_pr.py`-passes criterion, `VERDICT: PARTIAL`, check red.

`scripts/ci/spec_prepare_context.py` renders this module's output as a
`## Non-Executable Criteria Declaration` in the reviewer's additional context,
and `.github/prompts/spec-check-completeness.md` tells the reviewer what to do
with the named criteria.

That is a description, not a parity claim. An earlier version said this block
mirrors the `## Incremental Scope Declaration` built for issue #2255, which
`.claude/rules/canonical-source-mirror.md` requires be backed by the path plus
the verbatim contract. Both sections are under active revision, so a quoted
rule number here went stale twice in one review cycle. The comparison, with its
quotes and the one place the two deliberately disagree, lives in
`.agents/retrospective/2026-09-01-issue-5366-spec-coverage-nonexecutable-criteria.md`,
which is a dated record rather than a live document.

This repo's own PR template already puts that evidence elsewhere: the
`uv run python scripts/validation/pre_pr.py` checkbox lives under
`## Author Pre-flight`, not under `## Acceptance criteria`.

Stricter/looser/different than the prompt rule it feeds: this detector is
deliberately narrower. It fires only when the criterion is nothing but run
evidence, which means the named command is the subject of a result verb, that
verb ends the criterion, and the criterion states no condition:

    - [x] `pytest` passes                             -> fires
    the helper passes the flag to `run_gh`            -> no command as subject
    `pre_pr.py` passes the changed-file list to ruff  -> transitive, not a run
    the wrapper returns zero when `pytest` passes     -> conditional
    `wrapper.py` returns zero when `pytest` passes    -> conditional
    `pytest` passes locally and the parser rejects    -> trailing requirement
    the parser rejects an empty ref and `pytest` pass -> leading requirement
    - [ ] `pytest` passes                             -> author says unmet

Every line below the first states something about the code under review, or
about whether the author considers it done, and a diff reviewer can and must
check it. Each escaped an earlier draft a different way: scanning for a command
and a result verb independently anywhere in the bullet; truncating a
conditional at its subordinator, which left "`wrapper.py` returns zero" reading
as run evidence about the script under test; letting `Pattern.match` succeed on
a prefix or on a suffix, so a bullet that also carried a real requirement was
classified away with the requirement inside it; and dropping the checkbox state
while parsing, which turned an admitted gap into an exemption. Sample text
inside a fenced block was read as a real section for the same reason: nothing
told the parser the lines were not the document.

Every check rejects on its own, which costs under-firing: a real claim written
with a leading adverbial ("after the rename, `pytest` passes") or a trailing
qualifier ("`pytest` passes with the new flag") is not detected. That trade is
deliberate. Under-firing is safe, because the prompt rule still tells the
reviewer to treat an unexecutable criterion as N/A when no declaration names
it. Over-firing is not safe: it would silently drop a real criterion from the
gate.

Criterion text reaches the reviewer only after `_normalize` strips control
characters and collapses newlines, and `_sanitize` drops leading markdown
structure and truncates. That bounds the shape of the injected block; it does
not make the text trustworthy, and it does not need to, because
`build_ai_review_context.py` already hands the reviewer the same PR body
verbatim.
"""

from __future__ import annotations

import re

# Bound the injected block. A PR body is author-controlled and unbounded; the
# declaration is a hint for the reviewer, not a transcript of the PR.
_MAX_CRITERIA = 20
_MAX_CRITERION_CHARS = 200
_ELISION = " ... "

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# A fenced block holds sample text. A PR body that demonstrates this feature by
# quoting an acceptance-criteria section would otherwise have its own example
# read as a real section. `_FENCE_OPEN_LINE` in
# `scripts/validation/pr_description.py` masks
# fences before extracting file claims for the same reason; its
# `_FENCE_OPEN_LINE` reads, quoted verbatim:
#
#     r"^[ ]{0,3}(?:(`{3,})(?![^\n]*`)|(~{3,}))[^\n]*\n"
#
# Stricter/looser/different than that canonical source, three ways:
#
# 1. This matches a single line rather than a line plus its newline, because
#    the caller iterates `splitlines()` instead of walking offsets.
# 2. Indented four-space blocks are deliberately NOT treated as code: a wrapped
#    criterion's continuation line is indented, and `_bullets` folds it into
#    the bullet above.
# 3. The lookahead's inner scan is `[^`\n]*` here against the canonical
#    `[^\n]*`. That one character is the difference between linear and
#    quadratic. The canonical scan can cross a backtick, so it re-walks the
#    remainder once per backtrack of the leading run; measured on a line shaped
#    ("`" * n) + ("x" * n) + "`" + ("x" * n), it costs 0.020s at 12KB, 0.268s
#    at 46KB and 0.481s at 62KB, on an author-controlled PR body (CWE-1333).
#    Excluding the backtick stops each scan at the first one, which is the same
#    rule and 0.0013s on the 100KB fixture
#    `test_a_late_backtick_in_a_long_fence_like_line_stays_out_of_the_gate`
#    uses.
#
# The quote above is the canonical text as it stands, not as it ought to stand.
# `pr_description.py` still carries the quadratic form and parses PR bodies
# too, so it is exposed the same way; flagged on PR #5451 rather than changed
# here, because that validator feeds gates well outside this one.
_FENCE_LINE = re.compile(r"^ {0,3}(?:(`{3,})(?![^`\n]*`)|(~{3,}))\s*(?P<info>.*)$")
# The whole heading title, not a substring of it. A prefix or suffix word makes
# a different section: "Acceptance Criteria Verification" holds evidence and
# "Non-Acceptance Criteria" holds what the PR is not claiming, and treating
# either one's bullets as requirements misreads the document. Trailing `#` is
# Markdown's optional closing fence on an ATX heading.
_ACCEPTANCE_TITLE = re.compile(r"(?i)acceptance\s+criteri(?:a|on)\s*:?\s*#*\s*")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[(?P<mark>[ xX~-])\]\s*)?(?P<text>.*)$")
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

# The result verb must sit in intransitive position and must end the criterion.
# Two things ride on that.
#
# "passes" with a direct object after it ("passes the flag to X") is ordinary
# prose about the code, not a claim about a run.
#
# The `$` is load-bearing, because `Pattern.match` succeeds on a prefix.
# Without it, "`pytest` passes locally and the parser rejects an empty ref"
# matched on "locally" alone and the whole bullet was classified away, taking
# the parser requirement with it. A bullet that carries anything past the run
# evidence is not pure run evidence, so it stays in scope.
#
# The pattern carries no `^`: `Pattern.match(text, pos)` already anchors the
# start, and in a non-multiline pattern `^` matches the start of the string
# rather than the position handed to match().
_RESULT_TAIL = re.compile(
    r"(?i)(?:\s+(?:locally|clean(?:ly)?|green|in\s+ci|on\s+ci))?[\s.;,:!?)\]}]*$"
)

# What may sit before the command span. The claim has to open the criterion,
# modulo leading markdown structure and a word that introduces a run. Real
# content in front of it means the criterion says something else as well:
# "the parser rejects an empty ref and `pytest` passes" carries a requirement
# the diff establishes, and classifying the bullet away takes it along. This is
# the mirror of the end anchor on `_RESULT_TAIL`, and costs the same
# under-firing.
#
# `run` only. `then` was here too and let a Given/When/Then bullet through:
# "Then `wrapper.py` exits 0" cleared the prefix, the `.py` launcher check and
# the result tail, so a required exit code was classified as run evidence and
# dropped from the gate. A full "Given ... then ..." line was rejected anyway,
# because `given` is a subordinator, which is what made the one-clause-per-
# bullet form the shape that leaked. `then` introduces a consequence, and a
# consequence of something the diff establishes is a behavioral contract, which
# is the category the completeness prompt keeps in scope by name.
_CLAIM_PREFIX = re.compile(r"(?i)[#>\s]*(?:run\s+)*")

# What may sit between the command span and the result verb that governs it.
# Only enough to carry "Run `make build` and it completes successfully"; any
# wider and the verb stops belonging to the command.
_RESULT_BRIDGE = re.compile(r"(?i)[\s,:;]*(?:(?:and|then|it|still)\s+)*")

# A subordinator opens a clause that describes a condition. A criterion built
# around one states behavior under that condition, which is a contract the diff
# establishes, not a report of a run: "the wrapper returns zero when `pytest`
# passes" asserts what the wrapper must do.
#
# A conditional criterion is rejected whole rather than truncated at the
# subordinator. Truncating left a fragment that reads as run evidence on its
# own: "`wrapper.py` returns zero when `pytest` passes" became "`wrapper.py`
# returns zero", whose command span is the script under test rather than the
# command the sentence conditions on, and the whole criterion was classified
# away. Rejecting cannot produce that inversion, and costs only under-firing.
_SUBORDINATOR = re.compile(
    r"(?i)\b(?:after|although|assuming|because|before|even|given|if|once"
    r"|provided|since|so|though|unless|until|when|whenever|while)\b"
)


def _outside_fences(pr_body: str) -> list[str]:
    """Return `pr_body`'s lines with every fenced code block removed.

    A fence closes on the same character with a run at least as long as the
    opener's (CommonMark 0.31.2 section 4.5). An unclosed fence swallows the
    rest of the body, which is the safe direction: sample text never reaches
    the gate.
    """
    lines: list[str] = []
    open_run: str | None = None

    for line in pr_body.splitlines():
        fence = _FENCE_LINE.match(line)
        if open_run is None:
            if fence is not None:
                open_run = fence.group(1) or fence.group(2)
            else:
                lines.append(line)
            continue
        closes = (
            fence is not None
            and not fence.group("info")
            and (fence.group(1) or fence.group(2)).startswith(open_run[0] * len(open_run))
        )
        if closes:
            open_run = None

    return lines


def _acceptance_lines(pr_body: str) -> list[str]:
    """Return the non-heading lines under every Acceptance Criteria heading."""
    collected: list[str] = []
    inside = False
    level = 0

    for line in _outside_fences(pr_body):
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
    """Return classifiable list items, folding wrapped continuation lines in.

    An explicitly unchecked box is dropped. The PR template says so directly at
    `.github/PULL_REQUEST_TEMPLATE.md`, quoted verbatim:

        Check a box only once the criterion is actually met; an unchecked box
        makes the spec-coverage signal report FAIL (non-blocking).

    So `- [ ]` is the author stating the criterion is unmet, and turning that
    into `N/A` would erase an admitted gap from the completeness count. A
    bullet with no checkbox at all is not a statement either way and stays
    classifiable.

    Stricter/looser/different than the canonical source: the template names
    only `- [ ]` and `- [x]`. `[~]` and `[-]` are treated as unchecked here,
    because neither claims the criterion is met.
    """
    texts: list[str] = []
    unchecked: list[bool] = []
    open_index = -1

    for line in lines:
        item = _BULLET.match(line)
        if item is not None:
            texts.append(item.group("text").strip())
            unchecked.append(item.group("mark") in {" ", "~", "-"})
            open_index = len(texts) - 1
            continue
        if not line.strip():
            open_index = -1
            continue
        if open_index >= 0:
            texts[open_index] = f"{texts[open_index]} {line.strip()}"

    return [text for text, skip in zip(texts, unchecked, strict=True) if text and not skip]


def _is_conditional(text: str) -> bool:
    """True when `text` states behavior under a condition rather than a run."""
    return _SUBORDINATOR.search(text) is not None


def _command_span_ends(text: str) -> list[int]:
    """Offsets just past each command span that opens the criterion.

    A span with real content in front of it is skipped, so the returned offsets
    are only for commands the criterion leads with.
    """
    ends: list[int] = []
    for span in _CODE_SPAN.finditer(text):
        token = span.group(1).strip().lstrip("$>").strip()
        if not token:
            continue
        first = token.split()[0].lower().lstrip("./")
        if first not in _COMMAND_LAUNCHERS and not first.endswith(_SCRIPT_SUFFIXES):
            continue
        if _CLAIM_PREFIX.fullmatch(text[: span.start()]) is None:
            continue
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
    """True when `text` claims how a run turned out, and claims nothing else.

    Three conditions, each of which rejects on its own: the criterion states no
    condition, it names a runnable command, and a result verb governs that
    command and ends the criterion.
    """
    if _is_conditional(text):
        return False
    return any(_asserts_execution_result(text, end) for end in _command_span_ends(text))


def _normalize(text: str) -> str:
    """Collapse a criterion to one line of printable characters.

    Classification runs on the normalized text, not the raw bullet: a control
    character between the command and its result verb would otherwise break the
    adjacency `_asserts_execution_result` depends on.
    """
    return " ".join(_CONTROL_CHARS.sub(" ", text).split())


def _sanitize(text: str) -> str:
    """Flatten a normalized criterion to one bounded, structure-free line.

    A criterion longer than the cap loses its middle, not its end. The
    declaration exists so a reviewer can see which criterion was classified and
    why; the head carries the command and the tail carries the result verb, and
    those two are the evidence. Cutting from the end kept the command and threw
    away the half that says what was claimed about it, which left an entry the
    reviewer could not check the classification against.
    """
    cleaned = _LEADING_MARKUP.sub("", text)
    if len(cleaned) <= _MAX_CRITERION_CHARS:
        return cleaned
    budget = _MAX_CRITERION_CHARS - len(_ELISION)
    tail = budget // 3
    return cleaned[: budget - tail].rstrip() + _ELISION + cleaned[-tail:].lstrip()


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
