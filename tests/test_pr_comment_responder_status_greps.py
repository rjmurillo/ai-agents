# taste-lint: ignore file-size, one contract across nine carriers; splitting it
# would duplicate the carrier list, the canonical patterns, and the comment-map
# fixtures that every case here shares.
"""Regression coverage for pr-comment-responder comment-map status greps.

Issue #4034: the workflow greps searched for ``Status: [X]`` while the
comment-map detail field emits ``**Status**: [X]``. The old patterns counted
zero pending, complete, and wontfix comments, which made the gates dead.

Issue #4054: the vocabulary was published twice, the two copies both omitted
``[DUPLICATE]`` and ``[DEFERRED]``, and the two gate families disagreed about
what an unlisted status meant. Gate 4 and Gate 5 enumerated pending statuses,
so any status outside their list was silently treated as non-pending and the
gate passed; Phase 8.1 subtracted the terminal statuses, so the same status
blocked. Every gate now derives pending by subtracting the terminal count, so
an unrecognized status fails closed everywhere.

Subtraction alone still fails open on a corrupted map: strip every
``**Status**:`` field and both counts read zero, so the difference is zero
pending and the gate clears an artifact that describes nothing. Every gate now
also compares ``TOTAL`` against ``$TOTAL_COMMENTS``, the API count Phase 1
recorded, and blocks when the two disagree.

The counting tests read the quoted argument out of the carrier and hand it to a
real ``grep -Ec`` subprocess against a rendered comment map. A Python ``re``
mirror cannot catch a shell-side typo, because the engines disagree silently:
``\\d`` is a digit class in Python and a literal ``d`` in POSIX ERE. See
``test_python_regex_mirror_would_miss_an_ere_typo``.

The structural tests parse each fenced block separately and hold each one to the
whole derivation. Flattening every grep in a carrier and asking whether the
canonical pattern appears somewhere lets one gate drop a step while a sibling
gate's intact copy keeps the assertion green.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

GREP = shutil.which("grep")
BASH = shutil.which("bash")
# Phase 8.3's append parses the re-fetched payload with jq, the same tool the
# fence already uses to read ``.TotalComments``. Executing the append is the
# only way to prove the fence produces the row, so the tool is required rather
# than mocked away.
JQ = shutil.which("jq")
# Phase 8.3 fetches the fresh payload by invoking ``python3`` on the github
# skill's script. The producer-failure cases have to observe that invocation's
# exit status reach the shipped guard, so the fence's own command line runs
# against a stand-in script rather than being replaced by a synthesized
# assignment.
PYTHON3 = shutil.which("python3")

# The shared template generates VS Code and Copilot CLI source copies via
# build/generate_agents.py. src/claude and installed agent copies are
# hand-maintained per ADR-036 and install-parity rules. The skill reference is
# generated from .claude/skills/pr-comment-responder/ by build_all.py.
#
# Every carrier that publishes the status greps AND the vocabulary table that
# defines them. Hardcoded, never discovered from file content: a carrier that
# loses its table must fail this suite, not quietly drop out of it.
VOCABULARY_CARRIERS: tuple[Path, ...] = (
    REPO_ROOT / "templates/agents/pr-comment-responder.shared.md",
    REPO_ROOT / ".claude/agents/pr-comment-responder.md",
    REPO_ROOT / ".github/agents/pr-comment-responder.agent.md",
    REPO_ROOT / ".github/agents/pr-comment-responder.prompt.md",
    REPO_ROOT / "src/claude/pr-comment-responder.md",
    REPO_ROOT / "src/copilot-cli/agents/pr-comment-responder.agent.md",
    REPO_ROOT / "src/vs-code-agents/pr-comment-responder.agent.md",
)

# Skill references that publish the greps and point at the agent's one table
# rather than restating it. They carry the gates, not the vocabulary.
GATE_REFERENCE_CARRIERS: tuple[Path, ...] = (
    REPO_ROOT / ".claude/skills/pr-comment-responder/references/gates.md",
    REPO_ROOT / "src/copilot-cli/skills/pr-comment-responder/references/gates.md",
)

CARRIER_PATHS: tuple[Path, ...] = VOCABULARY_CARRIERS + GATE_REFERENCE_CARRIERS

# The skill entrypoint and its generated plugin copy. They publish completion
# criteria in prose, not the greps, so they carry no derivation fence. They are
# still what an agent reads first, so a stale copy hands out criteria narrower
# than the gates enforce.
SKILL_ENTRYPOINTS: tuple[Path, ...] = (
    REPO_ROOT / ".claude/skills/pr-comment-responder/SKILL.md",
    REPO_ROOT / "src/copilot-cli/skills/pr-comment-responder/SKILL.md",
)

# The four terminal status tokens the vocabulary table publishes. Spelled with
# brackets so a prose mention of the bare word cannot satisfy the assertion.
TERMINAL_STATUS_TOKENS: tuple[str, ...] = (
    "[COMPLETE]",
    "[WONTFIX]",
    "[DUPLICATE]",
    "[DEFERRED]",
)

VOCABULARY_HEADING = "## Comment Map Status Vocabulary"

# The shell regexes every carrier must publish, quoted verbatim from
# templates/agents/pr-comment-responder.shared.md. TOTAL counts every rendered
# status field; TERMINAL counts the ones the table marks terminal. Pending is
# the difference, never an enumeration, so an unlisted status stays pending.
#
# The trailing ``[[:space:]]*$`` is load-bearing. Without it a matching prefix
# was enough, so ``[COMPLETE]oops`` and ``[DEFERRED] Refs #4054garbage``
# counted as terminal and cleared the gate.
STATUS_LINE_PATTERN = r"^\*\*Status\*\*: "
TERMINAL_BODY = r"(\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[1-9][0-9]*)"
END_ANCHOR = r"[[:space:]]*$"
TERMINAL_PATTERN = STATUS_LINE_PATTERN + TERMINAL_BODY + END_ANCHOR
# The failure diagnostic pipes through `grep -En`, which prefixes each line
# with `N:`, so the complement drops the `^` anchor and keeps everything else.
COMPLEMENT_PATTERN = r"\*\*Status\*\*: " + TERMINAL_BODY + END_ANCHOR
REQUIRED_PATTERN_TEXT = (STATUS_LINE_PATTERN, TERMINAL_PATTERN)

# A status field reference that is not the emitted bold form. Matches the
# escaped shell-regex spelling (``Status: \[NEW\]``) and the bare spelling
# (``Status: [NEW]``) regardless of what precedes it, so an alternative buried
# in a ``|`` chain is still caught. The emitted form reads ``**Status**: [NEW]``
# and cannot match, because ``Status`` there is followed by ``**``.
DEAD_STATUS_FIELD_RE = re.compile(
    r"Status: (?:\\?\[(?:NEW|ACKNOWLEDGED|COMPLETE|WONTFIX|DUPLICATE|DEFERRED)\\?\]"
    r"|pending)"
)

# The fail-closed derivation published in the vocabulary section.
FAIL_CLOSED_DERIVATION = "PENDING=$((TOTAL - TERMINAL))"

# The guard that proves the comment map exists before any gate counts it.
MAP_EXISTS_GUARD = 'if [ ! -f "$COMMENT_MAP" ]; then'

# The two counting assignments as the carriers publish them, shell text and all.
TOTAL_ASSIGNMENT_TEXT = f'TOTAL=$(grep -Ec "{STATUS_LINE_PATTERN}" "$COMMENT_MAP" || true)'
TERMINAL_ASSIGNMENT_TEXT = f'TERMINAL=$(grep -Ec "{TERMINAL_PATTERN}" "$COMMENT_MAP" || true)'

# The artifact Phase 1 records the API comment count in, and the block every
# later fence reads it back with. Shell variables do not survive between fenced
# blocks: an agent harness runs each one in a fresh shell, so a fence that read
# ``$TOTAL_COMMENTS`` directly saw an empty string. ``[ -ne ]`` then printed
# ``integer expression expected`` and exited 2, ``if`` reads a nonzero exit as
# false, and the BLOCKED body below never ran. The invariant was inert.
COUNT_ARTIFACT_PATH = ".project-toolkit/pr-comments/PR-[number]/total_comments.txt"
COUNT_READ_BLOCK = (
    f'COUNT_FILE="{COUNT_ARTIFACT_PATH}"\n'
    'if [ ! -f "$COUNT_FILE" ]; then\n'
    '  echo "[BLOCKED] API comment count not recorded: $COUNT_FILE"\n'
    "  exit 1\n"
    "fi\n"
    'TOTAL_COMMENTS=$(cat "$COUNT_FILE")\n'
    'case "$TOTAL_COMMENTS" in\n'
    "  ''|*[!0-9]*) echo \"[BLOCKED] Recorded comment count is not numeric: "
    '$TOTAL_COMMENTS"; exit 1 ;;\n'
    "esac"
)

# The steps Phase 1 must publish to record the count. The reader above and this
# writer must name the same path, which
# ``test_the_recorded_count_reaches_the_gate_that_reads_it`` proves by running
# both against a real filesystem rather than by comparing these strings.
COUNT_RECORD_STEPS: tuple[str, ...] = (
    f'COUNT_FILE="{COUNT_ARTIFACT_PATH}"',
    'mkdir -p "$(dirname "$COUNT_FILE")"',
    'printf \'%s\\n\' "$TOTAL_COMMENTS" > "$COUNT_FILE"',
)

# Phase 8.3 re-fetches after a push and appends the comments that arrived since
# Phase 1 to the map with status ``[NEW]``. The recorded count is how many
# status fields the map should carry, so it has to move with that append. Left
# at the Phase 1 snapshot it is permanently smaller than the map, and the
# API-count invariant below blocks every later pass on correct work.
RECHECK_SECTION_KEY = "Phase 8.3"
RECHECK_BLOCK_OPEN = 'if [ "$NEW_COMMENTS" -gt "$TOTAL_COMMENTS" ]; then'
COUNT_REFRESH_STEP = 'printf \'%s\\n\' "$NEW_COMMENTS" > "$COUNT_FILE"'

# Phase 8.3's re-fetch, and the two guards that keep its failures from reading
# as "no new comments arrived".
#
# The fence shipped both producers unchecked through PR #5342: the assignment
# ignored the script's exit status, and ``jq '.TotalComments'`` can emit an
# empty string or ``null`` from a payload it could not parse or that carries no
# such key. ``[ "$NEW_COMMENTS" -gt "$TOTAL_COMMENTS" ]`` then raises ``integer
# expression expected`` and exits 2, ``if`` reads that nonzero exit as false,
# and the new-comment branch is skipped. The re-fetch is the only thing that
# can see a comment posted since the last pass, so a failed one silently
# cleared the very case Phase 8.3 exists for (PR #5342 review).
#
# Same defect class as the TOTAL_COMMENTS guard in commit e6726cd74, a
# different variable and a different comparison site, so the numeric check
# reuses that commit's ``case ... in ''|*[!0-9]*)`` idiom verbatim.
RECHECK_PRODUCER_LINE = (
    'RECHECK_PAYLOAD=$(python3 "$SCRIPTS_DIR/pr/get_pr_review_comments.py"'
    " --pull-request [number] --include-issue-comments)"
)
RECHECK_STATUS_GUARD = (
    "RECHECK_STATUS=$?\n"
    'if [ "$RECHECK_STATUS" -ne 0 ]; then\n'
    '  echo "[BLOCKED] Comment re-fetch failed (exit $RECHECK_STATUS)"\n'
    "  exit 1\n"
    "fi"
)
NEW_COUNT_ASSIGNMENT = "NEW_COMMENTS=$(printf '%s' \"$RECHECK_PAYLOAD\" | jq '.TotalComments')"
NEW_COUNT_GUARD = (
    "JQ_STATUS=$?\n"
    'if [ "$JQ_STATUS" -ne 0 ]; then\n'
    '  echo "[BLOCKED] Comment re-fetch payload is not parseable JSON'
    ' (jq exit $JQ_STATUS)"\n'
    "  exit 1\n"
    "fi\n"
    'case "$NEW_COMMENTS" in\n'
    "  ''|*[!0-9]*) echo \"[BLOCKED] Re-fetched comment count is not numeric:"
    ' $NEW_COMMENTS"; exit 1 ;;\n'
    "esac"
)

# The stand-in the producer-failure cases install where the fence looks for the
# real fetch script. Reads the payload from a sibling file so no payload text
# has to survive a round trip through Python source quoting.
RECHECK_PRODUCER_STUB = (
    "import pathlib\n"
    "import sys\n"
    "\n"
    'sys.stdout.write(pathlib.Path(__file__).with_name("payload.json").read_text(\n'
    '    encoding="utf-8"\n'
    "))\n"
    "sys.exit({exit_code})\n"
)

# Payloads the re-fetch can hand back that are not a usable comment count.
# ``not json`` is what a traceback or a proxy error page looks like to jq, and
# ``{}`` is a well-formed response missing the one key the fence reads.
UNPARSEABLE_PAYLOAD = "not json\n"
KEYLESS_PAYLOAD = "{}\n"

# The map Phase 8.3 appends to, at the path the fence hardcodes. The gates read
# the same file, so the append and every later count have to meet on disk.
COMMENT_MAP_ARTIFACT_PATH = ".project-toolkit/pr-comments/PR-[number]/comments.md"

# Phase 8.3's append: the pipeline that turns the re-fetched payload into the
# rows the gates count. Shipped as a bare ``# Fetch new comments`` comment
# through PR #5342, so the count refresh below moved while the map never did
# and Gate 4's API-count invariant blocked every later pass (Copilot review of
# commit e82aa27cc). Quoted verbatim so a carrier that drops it fails here.
APPEND_STEP = (
    "printf '%s' \"$RECHECK_PAYLOAD\" \\\n"
    '    | jq -r \'.Comments[] | [(.Id|tostring), (.Author // "unknown"), '
    '(.CommentType // "Review"), (.Path // "-"), (.Line // "-"), '
    '(.CreatedAt // "-")] | @tsv\' \\\n'
    "    | while IFS=\"$(printf '\\t')\" read -r ID AUTHOR CTYPE CPATH CLINE CREATED; do\n"
    '        if grep -q "^### Comment $ID " "$COMMENT_MAP"; then\n'
    "          continue\n"
    "        fi\n"
    "        {\n"
    '          printf \'### Comment %s (@%s)\\n\\n\' "$ID" "$AUTHOR"\n'
    "          printf '**Type**: %s\\n' \"$CTYPE\"\n"
    "          printf '**Path**: %s\\n' \"$CPATH\"\n"
    "          printf '**Line**: %s\\n' \"$CLINE\"\n"
    "          printf '**Created**: %s\\n' \"$CREATED\"\n"
    "          printf '**Status**: [NEW]\\n\\n'\n"
    "          printf -- '---\\n\\n'\n"
    '        } >> "$COMMENT_MAP"\n'
    "      done"
)

# The check that proves the append landed before the count is refreshed. The
# refresh is the one write that can clear the API-count invariant, so refreshing
# it over a map that never grew is the fail-open the invariant exists to catch.
APPEND_VERIFY_STEP = (
    'APPENDED_STATUS=$(grep -c "^\\*\\*Status\\*\\*: " "$COMMENT_MAP" || true)\n'
    '  if [ "$APPENDED_STATUS" -ne "$NEW_COMMENTS" ]; then\n'
    '    echo "[BLOCKED] Comment map carries $APPENDED_STATUS status fields '
    'after the append, API reported $NEW_COMMENTS"\n'
    "    exit 1\n"
    "  fi"
)

# The guard that proves the map is complete before the subtraction is trusted.
# A map whose status fields were stripped counts zero total and zero terminal,
# so the difference is zero pending and the gate clears an empty artifact.
API_COUNT_INVARIANT = (
    'if [ "$TOTAL" -ne "$TOTAL_COMMENTS" ]; then\n'
    '  echo "[BLOCKED] Comment map carries $TOTAL status fields, '
    'API reported $TOTAL_COMMENTS"\n'
    "  exit 1\n"
    "fi"
)

# Every step a fence that counts the comment map must publish, in this order.
REQUIRED_DERIVATION_STEPS: tuple[str, ...] = (
    MAP_EXISTS_GUARD,
    TOTAL_ASSIGNMENT_TEXT,
    TERMINAL_ASSIGNMENT_TEXT,
    FAIL_CLOSED_DERIVATION,
    COUNT_READ_BLOCK,
    API_COUNT_INVARIANT,
)

# The blocking half of a gate: the check that turns a nonzero pending count into
# a nonzero exit. Gate 4 and Phase 8.1 test ``$PENDING`` alone; Gate 5 also
# tests the unresolved-thread count, so the pattern matches the whole line.
PENDING_BLOCK_RE = re.compile(r'^if \[ [^\n]*"\$PENDING" -ne 0 \][^\n]*; then$', re.M)
BLOCK_END = "\nfi"

# The gate's GitHub reads. This suite exercises the comment-map derivation, so
# they are stubbed rather than dropped: dropping the assignment would leave the
# blocking check comparing an unset variable, which is the defect under test.
GH_GRAPHQL_ASSIGNMENT_RE = re.compile(r"^([A-Z_]+)=\$\(gh api graphql[^\n]*\)$", re.M)
GH_STUB_PREAMBLE = "REMAINING=0\nUNRESOLVED_API=0\n"

# The sections that own a counting fence. Hardcoded, never discovered from the
# file: a carrier that loses Gate 4's fence must fail, not drop out of the set.
VOCABULARY_SECTION_KEY = "Comment Map Status Vocabulary"
GATE_SECTION_KEYS: tuple[str, ...] = ("Gate 4", "Gate 5", "Phase 8.1")
# Phase 8.5 re-derives the counts in its own fence. It is a separate shell from
# Phase 8.1, so $TOTAL and $TERMINAL do not survive into it and its completion
# summary printed an empty numerator over an empty denominator. Only the agent
# carriers publish it as a fence; the gate reference states it as a table.
AGENT_ONLY_SECTION_KEYS: tuple[str, ...] = ("Phase 8.5",)
SECTION_KEYS: tuple[str, ...] = (
    VOCABULARY_SECTION_KEY,
    *GATE_SECTION_KEYS,
    *AGENT_ONLY_SECTION_KEYS,
)

EXPECTED_DERIVATION_SECTIONS: dict[Path, frozenset[str]] = {
    **{path: frozenset(SECTION_KEYS) for path in VOCABULARY_CARRIERS},
    **{path: frozenset(GATE_SECTION_KEYS) for path in GATE_REFERENCE_CARRIERS},
}

MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")

# Any quoted argument to a grep invocation, whatever the flags.
GREP_ANY_PATTERN_RE = re.compile(r"grep [^\"\n]*\"([^\"]+)\"")
# Counting greps, complement greps, and the two named assignments.
GREP_COUNT_PATTERN_RE = re.compile(r'grep -Ec "([^"]+)"')
GREP_COMPLEMENT_PATTERN_RE = re.compile(r'grep -Ev "([^"]+)"')
TERMINAL_ASSIGNMENT_RE = re.compile(r'TERMINAL=\$\(grep -Ec "([^"]+)"')
TOTAL_ASSIGNMENT_RE = re.compile(r'TOTAL=\$\(grep -Ec "([^"]+)"')

# A grep argument that enumerates pending statuses instead of subtracting the
# terminal ones. This is the fail-open shape issue #4054 reports.
ENUMERATED_PENDING_RE = re.compile(r"\\\[(?:NEW|ACKNOWLEDGED)\\\]|Status\\?\*?\*?: pending")

# The accumulators the subtraction retired. ``ADDRESSED`` and ``WONTFIX`` were
# separate counts that Phase 8.1 summed; every gate now derives TERMINAL and
# TOTAL instead. A carrier that still reads one gets 0 from bash, which treats
# an unset name in arithmetic as zero, so its summary reports no comments
# resolved after a fully successful run.
#
# The lookbehind excludes ``[`` and ``\``, so the vocabulary table's
# ``[WONTFIX]`` and the terminal grep's ``\[WONTFIX\]`` are not accumulators.
RETIRED_ACCUMULATOR_RE = re.compile(
    r"(?<![\w\\\[-])ADDRESSED(?![\w\]-])"
    r"|(?<![\w\\\[-])WONTFIX\s*="
    r"|\$\{?WONTFIX\}?(?!\w)"
)

# A status token rendered anywhere in the Step 2.2 Comment Index. Gate 3
# rewrites the ``**Status**:`` detail line and never touches the index, so an
# index status cell keeps whatever the template rendered for the life of the
# artifact and ends up disagreeing with the detail entry it summarizes.
COMMENT_INDEX_HEADING = "## Comment Index"
INDEX_STATUS_TOKEN_RE = re.compile(
    r"\[(?:NEW|ACKNOWLEDGED|COMPLETE|WONTFIX|DUPLICATE|DEFERRED)\]|(?<![\w-])pending(?![\w-])",
    re.IGNORECASE,
)

# One rendered comment map. Thirteen detail entries: five terminal, eight that
# must stay pending. The pending eight cover every way a status can fail to be
# terminal: not yet worked ([NEW], [ACKNOWLEDGED]), a [DEFERRED] with no
# tracking reference, an invented [BOGUS] that appears in no table, two
# malformed values whose valid prefix used to be enough to pass the gate, and
# two unresolvable issue numbers.
#
# ``Refs #0`` and ``Refs #007`` are the guaranteed-non-reference cases. GitHub
# numbers issues and pull requests from 1, so neither can ever resolve. The
# terminal pattern reads ``#[1-9][0-9]*``; the older ``#[0-9]+`` admitted both
# and let deferred work go terminal against a tracking issue nobody can open.
SAMPLE_COMMENT_MAP_LINES: tuple[str, ...] = (
    "| 123 | @reviewer | review | file.py#12 | TBD | - |",
    "**Status**: [NEW]",
    "**Status**: [ACKNOWLEDGED]",
    "**Status**: [COMPLETE]",
    "**Status**: [WONTFIX]",
    "**Status**: [DUPLICATE]",
    "**Status**: [DEFERRED] Refs #4054",
    "**Status**: [COMPLETE]  ",
    "**Status**: [DEFERRED]",
    "**Status**: [BOGUS]",
    "**Status**: [COMPLETE]oops",
    "**Status**: [DEFERRED] Refs #4054garbage",
    "**Status**: [DEFERRED] Refs #0",
    "**Status**: [DEFERRED] Refs #007",
)
SAMPLE_TOTAL_STATUS_LINES = 13
SAMPLE_TERMINAL_LINES = 5
SAMPLE_PENDING_LINES = SAMPLE_TOTAL_STATUS_LINES - SAMPLE_TERMINAL_LINES

# The status lines that must never count as terminal, each paired with why. A
# dedicated case per line so a regression names the shape it readmitted rather
# than only moving an aggregate count.
NON_TERMINAL_STATUS_LINES: tuple[tuple[str, str], ...] = (
    ("**Status**: [NEW]", "fetched, not yet acknowledged"),
    ("**Status**: [ACKNOWLEDGED]", "reaction posted, fix not committed"),
    ("**Status**: [DEFERRED]", "no tracking reference"),
    ("**Status**: [BOGUS]", "appears in no vocabulary table"),
    ("**Status**: [COMPLETE]oops", "trailing garbage after a valid prefix"),
    ("**Status**: [DEFERRED] Refs #4054garbage", "trailing garbage after the reference"),
    ("**Status**: [DEFERRED] Refs #0", "GitHub numbers issues from 1, so #0 never resolves"),
    ("**Status**: [DEFERRED] Refs #007", "leading zero is not a GitHub issue number"),
)

# Three comments the API reported, all of them worked to a terminal status.
API_COMMENT_COUNT = 3
COMPLETE_COMMENT_MAP_LINES: tuple[str, ...] = (
    "### Comment 123 (@reviewer)",
    "**Status**: [COMPLETE]",
    "### Comment 124 (@reviewer)",
    "**Status**: [WONTFIX]",
    "### Comment 125 (@reviewer)",
    "**Status**: [DEFERRED] Refs #4054",
)

# The comments the API reports on a second pass: the three Phase 1 recorded,
# plus the bot answer that arrived after the push. The four-comment map is NOT
# written here. Building it by hand is what let the earlier version of these
# tests stay green while Phase 8.3's append was a bare shell comment: the test
# supplied the row it claimed to verify. The map has to come out of the fence.
FIRST_PASS_COMMENTS: tuple[tuple[int, str], ...] = (
    (123, "reviewer"),
    (124, "reviewer"),
    (125, "reviewer"),
)
NEW_COMMENT_ID = 126
NEW_COMMENT_AUTHOR = "bot"
SECOND_PASS_COMMENTS: tuple[tuple[int, str], ...] = FIRST_PASS_COMMENTS + (
    (NEW_COMMENT_ID, NEW_COMMENT_AUTHOR),
)
SECOND_PASS_COMMENT_COUNT = len(SECOND_PASS_COMMENTS)
APPENDED_HEADING = f"### Comment {NEW_COMMENT_ID} (@{NEW_COMMENT_AUTHOR})"
APPENDED_STATUS_LINE = "**Status**: [NEW]"

# The same three comments with one still unworked. All three status fields are
# present, so the API-count invariant clears and the gate's blocking check on
# $PENDING is what has to reject it.
PENDING_COMMENT_MAP_LINES: tuple[str, ...] = (
    "### Comment 123 (@reviewer)",
    "**Status**: [COMPLETE]",
    "### Comment 124 (@reviewer)",
    "**Status**: [ACKNOWLEDGED]",
    "### Comment 125 (@reviewer)",
    "**Status**: [DEFERRED] Refs #4054",
)

# The same map after a bad edit stripped every status field. Both counts read
# zero, so the subtraction reports zero pending on an artifact that records
# nothing about the three comments the API said exist.
STRIPPED_COMMENT_MAP_LINES: tuple[str, ...] = (
    "### Comment 123 (@reviewer)",
    "[COMPLETE]",
    "### Comment 124 (@reviewer)",
    "[WONTFIX]",
    "### Comment 125 (@reviewer)",
    "[DEFERRED] Refs #4054",
)

# One field survived the edit. Two comments lost theirs, so the map is short.
PARTIAL_COMMENT_MAP_LINES: tuple[str, ...] = (
    "### Comment 123 (@reviewer)",
    "**Status**: [COMPLETE]",
    "### Comment 124 (@reviewer)",
    "[WONTFIX]",
    "### Comment 125 (@reviewer)",
    "[DEFERRED] Refs #4054",
)

VOCABULARY_ROW_RE = re.compile(
    r"^\| `\[(?P<status>[A-Z]+)\][^`]*` \| [^|]+ \| (?P<terminal>[^|]+)\|"
)
TABLE_HEADER = "| Status | Meaning |"

requires_grep = pytest.mark.skipif(GREP is None, reason="grep is not on PATH")
requires_bash = pytest.mark.skipif(BASH is None, reason="bash is not on PATH")
requires_jq = pytest.mark.skipif(JQ is None, reason="jq is not on PATH")
requires_python3 = pytest.mark.skipif(PYTHON3 is None, reason="python3 is not on PATH")


def _render_comment_map(tmp_path: Path, lines: Sequence[str]) -> Path:
    target = tmp_path / "comments.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _render_session_comment_map(work_dir: Path, lines: Sequence[str]) -> Path:
    """Render the map at the path Phase 8.3 hardcodes, relative to ``work_dir``.

    Phase 8.3 opens the map by literal path rather than by injected variable,
    so a test that wants the fence to append has to put the pre-append map
    where the fence will look for it.
    """
    target = work_dir / COMMENT_MAP_ARTIFACT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _recheck_payload(comments: Sequence[tuple[int, str]]) -> str:
    """The ``get_pr_review_comments.py --include-issue-comments`` response shape.

    Only the fields the append reads are populated. ``TotalComments`` is derived
    from the row count rather than passed in, so the fixture cannot claim a
    total its own comment list does not support.
    """
    rows = [
        {
            "Id": comment_id,
            "Author": author,
            "CommentType": "Review",
            "Path": "src/example.py",
            "Line": index + 1,
            "CreatedAt": f"2026-08-27T00:0{index}:00Z",
        }
        for index, (comment_id, author) in enumerate(comments)
    ]
    return json.dumps({"TotalComments": len(rows), "Comments": rows})


def _grep_count(pattern: str, comment_map: Path) -> int:
    """Run the published ``grep -Ec PATTERN FILE`` and return its real stdout.

    Exercises the shipped shell command, not a Python translation of it.
    ``grep -c`` exits 1 and prints ``0`` when nothing matches; exit 2 means
    grep refused the pattern, which is the failure this runner exists to
    surface.
    """
    assert GREP is not None
    proc = subprocess.run(
        [GREP, "-Ec", pattern, str(comment_map)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode in (0, 1), (
        f"grep rejected the published pattern {pattern!r} "
        f"(exit {proc.returncode}): {proc.stderr.strip()}"
    )
    return int(proc.stdout.strip())


def _vocabulary_section(text: str) -> str:
    start = text.index(VOCABULARY_HEADING)
    next_heading = text.find("\n## ", start + len(VOCABULARY_HEADING))
    end = len(text) if next_heading == -1 else next_heading
    return text[start:end]


def _terminal_statuses_in_pattern(pattern: str) -> set[str]:
    return set(re.findall(r"\\\[([A-Z]+)\\\]", pattern))


def _carrier_id(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _bash_fences(text: str) -> list[tuple[str, str]]:
    """Return ``(owning heading, fence body)`` for every ``bash`` fence.

    Every fenced block is consumed, not only the bash ones, so a ``#`` comment
    inside a ``text`` or ``python`` fence cannot be mistaken for a heading and
    mislabel the next bash fence.
    """
    fences: list[tuple[str, str]] = []
    heading = ""
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            opener = line.strip()
            index += 1
            body: list[str] = []
            while index < len(lines) and lines[index].strip() != "```":
                body.append(lines[index])
                index += 1
            if opener == "```bash":
                fences.append((heading, "\n".join(body) + "\n"))
            index += 1
            continue
        match = MARKDOWN_HEADING_RE.match(line)
        if match is not None:
            heading = match.group("title")
        index += 1
    return fences


def _section_key(heading: str) -> str | None:
    for key in SECTION_KEYS:
        if heading.startswith(key):
            return key
    return None


def _recheck_fence(path: Path) -> str:
    """The Phase 8.3 fence that compares the fresh API count to the recorded one.

    Matched on the heading rather than discovered from the body, so a carrier
    that loses the fence fails here instead of dropping out of the set.
    """
    for heading, body in _bash_fences(path.read_text(encoding="utf-8")):
        if heading.startswith(RECHECK_SECTION_KEY) and RECHECK_BLOCK_OPEN in body:
            return body
    raise AssertionError(f"{_carrier_id(path)} publishes no {RECHECK_SECTION_KEY} fence")


def _install_recheck_producer(work_dir: Path, payload: str, *, exit_code: int = 0) -> Path:
    """Install a stand-in for the fetch script Phase 8.3 runs, and return SCRIPTS_DIR.

    The fence invokes ``python3 "$SCRIPTS_DIR/pr/get_pr_review_comments.py"``.
    Only ``SCRIPTS_DIR`` is injected, so the shipped command line, its exit
    status, and the guard that reads that status all run for real. ``exit_code``
    is the producer-failure control: a nonzero exit with whatever the script
    managed to print is exactly what a network error or a traceback leaves
    behind.
    """
    scripts_dir = work_dir / "stub-github-scripts"
    target = scripts_dir / "pr" / "get_pr_review_comments.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    (target.parent / "payload.json").write_text(payload, encoding="utf-8")
    target.write_text(RECHECK_PRODUCER_STUB.format(exit_code=exit_code), encoding="utf-8")
    return scripts_dir


def _recheck_script(
    fence: str,
    scripts_dir: Path,
    *,
    with_fetch_guards: bool = True,
    with_append: bool = True,
    with_verify: bool = True,
    with_refresh: bool = True,
) -> str:
    """Lift Phase 8.3's re-fetch, count read, and new-comment branch out verbatim.

    Sliced from the ``RECHECK_PAYLOAD=`` assignment, so the fetch the fence
    publishes is the command that runs and its exit status is the one the
    shipped guard reads. ``SCRIPTS_DIR`` is injected to point the invocation at
    the stand-in ``_install_recheck_producer`` wrote; the ``sleep 45`` above it
    is left out. ``NEW_COMMENTS`` is derived by the fence's own
    ``jq '.TotalComments'``, so the fixture cannot hand the branch a total its
    own payload does not support.

    The slice ends at the first column-zero ``fi`` at or after the branch
    opener. Every ``fi`` inside the branch is indented, so this is the branch's
    own terminator and not the append's guard or the verification below it. The
    guards added ahead of the opener close at column zero too, which is why the
    search starts at the opener rather than at the top of the slice.

    ``with_fetch_guards``, ``with_append``, ``with_verify``, and
    ``with_refresh`` are the negative controls. Dropping the fetch guards
    reproduces the shape PR #5342 shipped: a failed or malformed re-fetch reads
    as "no new comments" and the pass continues. Dropping the append reproduces
    the earlier one: the recorded count advances while the map never gains the
    row.
    """
    assert RECHECK_PRODUCER_LINE in fence, "Phase 8.3 publishes no re-fetch"
    assert RECHECK_STATUS_GUARD in fence, (
        "Phase 8.3 uses the re-fetch payload without checking the producer's "
        "exit status, so a failed fetch leaves NEW_COMMENTS empty, `[ -gt ]` "
        "errors out, and the pass continues as though no new comments arrived"
    )
    assert NEW_COUNT_ASSIGNMENT in fence, "Phase 8.3 publishes no NEW_COMMENTS assignment"
    assert NEW_COUNT_GUARD in fence, (
        "Phase 8.3 compares NEW_COMMENTS without checking jq or validating the "
        "value, so an unparseable or keyless payload reads as no new comments"
    )
    assert COUNT_READ_BLOCK in fence, "Phase 8.3 publishes no count-artifact read"
    assert APPEND_STEP in fence, (
        "Phase 8.3 advances the recorded count without appending the new "
        "comments to the map, so the count grows while the map does not and "
        "Gate 4's API-count invariant blocks every later pass"
    )
    assert APPEND_VERIFY_STEP in fence, (
        "Phase 8.3 refreshes the recorded count without proving the append "
        "landed, so a refresh over an unchanged map clears the invariant"
    )
    assert COUNT_REFRESH_STEP in fence, (
        "Phase 8.3 appends new comments to the map without refreshing the "
        "recorded count, so Gate 4's API-count invariant blocks every later pass"
    )
    start = fence.index(RECHECK_PRODUCER_LINE)
    end = fence.index(BLOCK_END, fence.index(RECHECK_BLOCK_OPEN)) + len(BLOCK_END)
    body = fence[start:end]
    if not with_fetch_guards:
        body = body.replace(RECHECK_STATUS_GUARD, ":").replace(NEW_COUNT_GUARD, ":")
    if not with_append:
        body = body.replace(APPEND_STEP, ":")
    if not with_verify:
        body = body.replace(APPEND_VERIFY_STEP, ":")
    if not with_refresh:
        body = body.replace(COUNT_REFRESH_STEP, ":")
    return f"SCRIPTS_DIR={shlex.quote(str(scripts_dir))}\n{body}\n"


def _counting_fences(text: str) -> list[tuple[str, str]]:
    """Every bash fence that counts status fields out of the comment map."""
    return [
        (heading, body)
        for heading, body in _bash_fences(text)
        if GREP_COUNT_PATTERN_RE.search(body) and '"$COMMENT_MAP"' in body
    ]


def _record_api_count(work_dir: Path, value: object | None) -> Path:
    """Write the count artifact Phase 1 records, or leave it absent.

    The carrier hardcodes the path, so the test creates it under the working
    directory the derivation runs in rather than injecting a variable. Passing
    ``None`` omits the file, which is the missing-artifact case.
    """
    count_file = work_dir / COUNT_ARTIFACT_PATH
    if value is None:
        return count_file
    count_file.parent.mkdir(parents=True, exist_ok=True)
    count_file.write_text(f"{value}\n", encoding="utf-8")
    return count_file


def _derivation_script(
    fence: str,
    comment_map: Path,
    *,
    with_invariant: bool = True,
    with_count_read: bool = True,
) -> str:
    """Lift a fence's counting steps out verbatim and make them runnable.

    The slice runs from the ``TOTAL=`` assignment through the end of the
    blocking check that turns a nonzero pending count into a nonzero exit, so
    the shipped gate's own ``exit 1`` is executed rather than described. Only
    ``COMMENT_MAP`` is injected; the count artifact is read from the path the
    carrier publishes, relative to the working directory the caller runs in.

    ``with_invariant`` and ``with_count_read`` exist for the negative controls:
    removing either step must let a bad comment map clear the gate.
    """
    assert TOTAL_ASSIGNMENT_TEXT in fence, "fence publishes no canonical TOTAL assignment"
    assert API_COUNT_INVARIANT in fence, (
        "fence publishes no API-count invariant, so a stripped comment map "
        "computes zero pending and clears the gate"
    )
    assert COUNT_READ_BLOCK in fence, (
        "fence publishes no count-artifact read, so $TOTAL_COMMENTS is unset "
        "and the invariant below it never fires"
    )
    start = fence.index(TOTAL_ASSIGNMENT_TEXT)
    invariant_end = fence.index(API_COUNT_INVARIANT) + len(API_COUNT_INVARIANT)
    body = fence[start : _pending_block_end(fence, invariant_end)]
    if not with_invariant:
        body = body.replace(API_COUNT_INVARIANT, ":")
    if not with_count_read:
        body = body.replace(COUNT_READ_BLOCK, ":")
    body = GH_GRAPHQL_ASSIGNMENT_RE.sub(r"\1=0", body)
    return (
        f"COMMENT_MAP={shlex.quote(str(comment_map))}\n"
        f"{GH_STUB_PREAMBLE}"
        f"{body}\n"
        'echo "PENDING=$PENDING"\n'
    )


def _pending_block_end(fence: str, after: int) -> int:
    """Offset just past the ``fi`` of the fence's pending blocking check.

    Slicing at the API-count invariant stopped one line short of the block the
    gate exists for, so every derivation test observed a printed count and no
    gate was ever proven to exit nonzero on pending work.
    """
    match = PENDING_BLOCK_RE.search(fence, after)
    assert match is not None, (
        "fence publishes no blocking check on $PENDING, so a pending comment "
        "map reports a count instead of failing the gate"
    )
    return fence.index(BLOCK_END, match.end()) + len(BLOCK_END)


def _run_derivation(script: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        cwd=None if cwd is None else str(cwd),
    )


def _gate_fence(path: Path, section: str) -> str:
    for heading, body in _counting_fences(path.read_text(encoding="utf-8")):
        if _section_key(heading) == section:
            return body
    raise AssertionError(f"{_carrier_id(path)} publishes no {section} counting fence")


def _gate_four_fence(path: Path) -> str:
    return _gate_fence(path, "Gate 4")


def _count_record_fence(path: Path) -> str:
    """The Phase 1 steps that write the count artifact, ready to run.

    Sliced from the ``COUNT_FILE=`` assignment so the preceding ``gh`` and
    ``jq`` calls the retrieval fence makes are left out; ``TOTAL_COMMENTS`` is
    supplied by the caller in their place.
    """
    for _, body in _bash_fences(path.read_text(encoding="utf-8")):
        if COUNT_RECORD_STEPS[2] in body:
            start = body.index(COUNT_RECORD_STEPS[0])
            end = body.index(COUNT_RECORD_STEPS[2]) + len(COUNT_RECORD_STEPS[2])
            return body[start:end]
    raise AssertionError(f"{_carrier_id(path)} never records the API comment count")


def _comment_index_rows(text: str) -> list[str]:
    """The table rows the Step 2.2 template renders under ``## Comment Index``."""
    start = text.index(COMMENT_INDEX_HEADING)
    end = text.index("\n## ", start + len(COMMENT_INDEX_HEADING))
    return [line for line in text[start:end].splitlines() if line.startswith("|")]


# The published patterns, executed by the shell they are written for.


@requires_grep
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_published_greps_count_a_rendered_comment_map(path: Path, tmp_path: Path) -> None:
    """Run each carrier's own shell greps: they must count real rows.

    The patterns are read out of the carrier and handed to grep verbatim, so a
    typo in the shipped command fails here rather than shipping.
    """
    text = path.read_text(encoding="utf-8")
    comment_map = _render_comment_map(tmp_path, SAMPLE_COMMENT_MAP_LINES)

    published_total = TOTAL_ASSIGNMENT_RE.findall(text)
    published_terminal = TERMINAL_ASSIGNMENT_RE.findall(text)
    assert published_total, f"{_carrier_id(path)} publishes no TOTAL counting grep"
    assert published_terminal, f"{_carrier_id(path)} publishes no TERMINAL counting grep"

    for pattern in published_total:
        assert _grep_count(pattern, comment_map) == SAMPLE_TOTAL_STATUS_LINES

    for pattern in published_terminal:
        terminal = _grep_count(pattern, comment_map)
        assert terminal == SAMPLE_TERMINAL_LINES, (
            f"{_carrier_id(path)} TERMINAL grep counted {terminal}, expected "
            f"{SAMPLE_TERMINAL_LINES}; pattern {pattern!r}"
        )
        assert SAMPLE_TOTAL_STATUS_LINES - terminal == SAMPLE_PENDING_LINES


@requires_grep
def test_end_anchor_keeps_malformed_terminal_values_pending(tmp_path: Path) -> None:
    """Trailing garbage after a valid prefix must not count as terminal."""
    malformed = (
        "**Status**: [COMPLETE]oops",
        "**Status**: [DEFERRED] Refs #4054garbage",
        "**Status**: [WONTFIX] but actually not",
        "**Status**: [DEFERRED] Refs #",
        "**Status**: [DEFERRED]",
    )
    comment_map = _render_comment_map(tmp_path, malformed)
    assert _grep_count(TERMINAL_PATTERN, comment_map) == 0

    well_formed = (
        "**Status**: [COMPLETE]",
        "**Status**: [WONTFIX]",
        "**Status**: [DUPLICATE]",
        "**Status**: [DEFERRED] Refs #4054",
        "**Status**: [COMPLETE]\t",
        "**Status**: [DEFERRED] Refs #4054 ",
    )
    comment_map = _render_comment_map(tmp_path, well_formed)
    assert _grep_count(TERMINAL_PATTERN, comment_map) == len(well_formed)


@requires_grep
@pytest.mark.parametrize(
    ("status_line", "reason"),
    NON_TERMINAL_STATUS_LINES,
    ids=[line.removeprefix("**Status**: ") for line, _ in NON_TERMINAL_STATUS_LINES],
)
def test_a_non_terminal_status_line_stays_pending(
    status_line: str, reason: str, tmp_path: Path
) -> None:
    """Each way a status can fail to be terminal, named one shape per case."""
    comment_map = _render_comment_map(tmp_path, (status_line,))
    assert _grep_count(TERMINAL_PATTERN, comment_map) == 0, (
        f"{status_line!r} counted as terminal; it must stay pending because {reason}"
    )


@requires_grep
@pytest.mark.parametrize("issue_number", ("1", "9", "10", "4054"))
def test_a_real_issue_number_still_marks_deferred_terminal(
    issue_number: str, tmp_path: Path
) -> None:
    """The tightened number class must not cost a legitimate reference.

    Guards the inverse of ``test_a_non_terminal_status_line_stays_pending``:
    narrowing ``#[0-9]+`` to ``#[1-9][0-9]*`` must reject only the numbers
    GitHub cannot issue, never a tracked deferral.
    """
    comment_map = _render_comment_map(tmp_path, (f"**Status**: [DEFERRED] Refs #{issue_number}",))
    assert _grep_count(TERMINAL_PATTERN, comment_map) == 1


@requires_grep
def test_the_old_number_class_is_the_bug_the_new_one_fixes(tmp_path: Path) -> None:
    """Negative control: ``#[0-9]+`` admits the numbers GitHub never issues.

    Issues and pull requests are numbered from 1, so ``Refs #0`` names nothing
    that can be opened. Under the old class it counted terminal, so the gates
    cleared deferred work whose tracking issue does not and cannot exist.
    """
    old_pattern = (
        STATUS_LINE_PATTERN
        + r"(\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[0-9]+)"
        + END_ANCHOR
    )
    unresolvable = (
        "**Status**: [DEFERRED] Refs #0",
        "**Status**: [DEFERRED] Refs #007",
    )
    comment_map = _render_comment_map(tmp_path, unresolvable)

    assert _grep_count(old_pattern, comment_map) == len(unresolvable)
    assert _grep_count(TERMINAL_PATTERN, comment_map) == 0


@requires_grep
def test_unanchored_terminal_pattern_is_the_bug_the_anchor_fixes(tmp_path: Path) -> None:
    """Negative control: drop the anchor and the malformed values pass."""
    unanchored = STATUS_LINE_PATTERN + TERMINAL_BODY
    comment_map = _render_comment_map(tmp_path, SAMPLE_COMMENT_MAP_LINES)

    assert _grep_count(unanchored, comment_map) == SAMPLE_TERMINAL_LINES + 2
    assert _grep_count(TERMINAL_PATTERN, comment_map) == SAMPLE_TERMINAL_LINES


@requires_grep
def test_python_regex_mirror_would_miss_an_ere_typo(tmp_path: Path) -> None:
    """Why these tests shell out instead of mirroring the pattern in Python.

    ``\\d`` is a digit class to Python and a literal ``d`` to POSIX ERE. A
    Python mirror of the shipped command accepts the typo and reports the
    correct count; the shell that actually runs it reports zero. Neither
    engine errors, so only running the real command catches it.
    """
    typo = r"^\*\*Status\*\*: \[DEFERRED\] Refs #\d+"
    lines = ("**Status**: [DEFERRED] Refs #4054",)
    comment_map = _render_comment_map(tmp_path, lines)

    assert _grep_count(typo, comment_map) == 0
    assert sum(1 for line in lines if re.search(typo, line)) == 1


@requires_grep
def test_grep_runner_fails_loudly_on_a_pattern_grep_refuses(tmp_path: Path) -> None:
    """Negative control: an uncompilable ERE must fail, not read as zero."""
    comment_map = _render_comment_map(tmp_path, SAMPLE_COMMENT_MAP_LINES)
    with pytest.raises(AssertionError, match="grep rejected the published pattern"):
        _grep_count(r"^\*\*Status\*\*: [[:bogus:]]", comment_map)


# Every gate must publish the one canonical pattern, not a near copy.


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_every_counting_fence_publishes_the_whole_derivation(path: Path) -> None:
    """Each fence, on its own, must carry every step in order.

    Flattening the file and asking whether each step appears somewhere lets one
    gate drop its subtraction, or its API-count invariant, while a sibling
    gate's intact copy keeps the assertion green. The fence is the unit.
    """
    fences = _counting_fences(path.read_text(encoding="utf-8"))
    assert fences, f"{_carrier_id(path)} publishes no fence that counts the comment map"

    for heading, body in fences:
        offsets: list[int] = []
        for step in REQUIRED_DERIVATION_STEPS:
            assert step in body, (
                f"{_carrier_id(path)} section {heading!r} counts the comment map "
                f"without publishing {step!r}"
            )
            offsets.append(body.index(step))
        assert offsets == sorted(offsets), (
            f"{_carrier_id(path)} section {heading!r} publishes the derivation "
            f"steps out of order; the map-exists guard, the two counts, the "
            f"subtraction, and the API-count invariant must run in that order"
        )


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_every_expected_section_owns_a_counting_fence(path: Path) -> None:
    """Deleting a gate's fence must fail, not shrink the set under test.

    The expected sections are hardcoded per carrier. A gate that loses its
    fence stops being checked otherwise, which is how a per-fence assertion
    silently becomes a no-op.
    """
    found = {
        key
        for heading, _ in _counting_fences(path.read_text(encoding="utf-8"))
        if (key := _section_key(heading)) is not None
    }
    unkeyed = [
        heading
        for heading, _ in _counting_fences(path.read_text(encoding="utf-8"))
        if _section_key(heading) is None
    ]

    assert not unkeyed, (
        f"{_carrier_id(path)} counts the comment map under unrecognized "
        f"section(s) {unkeyed}; add the section to SECTION_KEYS so the "
        f"derivation there is checked"
    )
    assert found == EXPECTED_DERIVATION_SECTIONS[path], (
        f"{_carrier_id(path)} counts the comment map in {sorted(found)}, "
        f"expected {sorted(EXPECTED_DERIVATION_SECTIONS[path])}"
    )


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_every_gate_publishes_the_canonical_patterns(path: Path) -> None:
    """Per-gate, not per-file: one gate dropping [DUPLICATE] must fail.

    Asserting the canonical pattern appears somewhere in the file lets a second
    gate ship a narrower terminal list unnoticed. Every counting grep in the
    carrier is checked instead.
    """
    text = path.read_text(encoding="utf-8")

    counting = GREP_COUNT_PATTERN_RE.findall(text)
    assert counting, f"{_carrier_id(path)} publishes no counting grep"
    offenders = [p for p in counting if p not in REQUIRED_PATTERN_TEXT]
    assert not offenders, (
        f"{_carrier_id(path)} publishes counting grep(s) that are neither the "
        f"status-line total nor the canonical terminal pattern: {offenders}"
    )

    for pattern in TERMINAL_ASSIGNMENT_RE.findall(text):
        assert pattern == TERMINAL_PATTERN, (
            f"{_carrier_id(path)} assigns TERMINAL from {pattern!r}, not the "
            f"canonical {TERMINAL_PATTERN!r}"
        )
    for pattern in TOTAL_ASSIGNMENT_RE.findall(text):
        assert pattern == STATUS_LINE_PATTERN, (
            f"{_carrier_id(path)} assigns TOTAL from {pattern!r}, not the "
            f"canonical {STATUS_LINE_PATTERN!r}"
        )
    for pattern in GREP_COMPLEMENT_PATTERN_RE.findall(text):
        assert pattern == COMPLEMENT_PATTERN, (
            f"{_carrier_id(path)} diagnoses with {pattern!r}, which is not the "
            f"complement of the canonical terminal pattern"
        )


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_every_counting_gate_proves_the_comment_map_exists(path: Path) -> None:
    """A missing map must block, not compute zero pending and pass.

    ``grep -Ec`` on an absent file exits non-zero and prints nothing, ``|| true``
    turns that into an empty string, and ``$(( ))`` reads an empty string as 0.
    Every fenced block that counts the map must prove it exists first.
    """
    unguarded = []
    for heading, block in _counting_fences(path.read_text(encoding="utf-8")):
        first_count = min(m.start() for m in GREP_COUNT_PATTERN_RE.finditer(block))
        guard = block.find(MAP_EXISTS_GUARD)
        if guard == -1 or guard > first_count:
            unguarded.append(heading)

    assert not unguarded, (
        f"{_carrier_id(path)} counts the comment map without proving it exists "
        f"first, so an absent map computes zero pending and clears the gate "
        f"(issue #4054): {unguarded}"
    )


# The API-count invariant, executed by the shell the carriers publish it for.


@requires_bash
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_a_stripped_comment_map_blocks_the_gate(path: Path, tmp_path: Path) -> None:
    """A map whose status fields were stripped must block, not read as done.

    Both counts read zero, so the subtraction reports zero pending. Only the
    comparison against the API count can tell that apart from a finished map.
    """
    comment_map = _render_comment_map(tmp_path, STRIPPED_COMMENT_MAP_LINES)
    _record_api_count(tmp_path, API_COMMENT_COUNT)
    script = _derivation_script(_gate_four_fence(path), comment_map)

    result = _run_derivation(script, cwd=tmp_path)

    assert result.returncode == 1, (
        f"{_carrier_id(path)} Gate 4 cleared a comment map with every status "
        f"field stripped: exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "[BLOCKED] Comment map carries 0 status fields, API reported 3" in result.stdout
    assert "PENDING=" not in result.stdout, (
        f"{_carrier_id(path)} Gate 4 reached the pending report after the "
        f"invariant should have exited"
    )


@requires_bash
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_a_partially_stripped_comment_map_blocks_the_gate(path: Path, tmp_path: Path) -> None:
    """Losing some status fields must block too, not shrink the denominator."""
    comment_map = _render_comment_map(tmp_path, PARTIAL_COMMENT_MAP_LINES)
    _record_api_count(tmp_path, API_COMMENT_COUNT)
    script = _derivation_script(_gate_four_fence(path), comment_map)

    result = _run_derivation(script, cwd=tmp_path)

    assert result.returncode == 1, (
        f"{_carrier_id(path)} Gate 4 cleared a comment map holding 1 of 3 "
        f"status fields: exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "[BLOCKED] Comment map carries 1 status fields, API reported 3" in result.stdout


@requires_bash
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_a_complete_comment_map_clears_the_invariant(path: Path, tmp_path: Path) -> None:
    """Control: a map that matches the API count must clear the whole gate.

    The slice now runs through Gate 4's own ``exit 1`` on pending work, so this
    control proves the blocking half stays quiet on a finished map rather than
    blocking everything unconditionally.
    """
    comment_map = _render_comment_map(tmp_path, COMPLETE_COMMENT_MAP_LINES)
    _record_api_count(tmp_path, API_COMMENT_COUNT)
    script = _derivation_script(_gate_four_fence(path), comment_map)

    result = _run_derivation(script, cwd=tmp_path)

    assert result.returncode == 0, (
        f"{_carrier_id(path)} Gate 4 blocked a complete comment map: "
        f"exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "PENDING=0" in result.stdout


@requires_bash
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_a_pending_comment_map_blocks_the_gate(path: Path, tmp_path: Path) -> None:
    """The blocking half of the gate must exit nonzero, not report a count.

    Three comments, one still ``[ACKNOWLEDGED]``. The API count matches, so
    the invariant clears and control reaches Gate 4's own
    ``if [ "$PENDING" -ne 0 ]``. Until the slice reached that block no test in
    this suite ever executed a gate's ``exit 1``.
    """
    comment_map = _render_comment_map(tmp_path, PENDING_COMMENT_MAP_LINES)
    _record_api_count(tmp_path, API_COMMENT_COUNT)
    script = _derivation_script(_gate_four_fence(path), comment_map)

    result = _run_derivation(script, cwd=tmp_path)

    assert result.returncode == 1, (
        f"{_carrier_id(path)} Gate 4 cleared a comment map holding 1 pending "
        f"comment: exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "[BLOCKED] Comment map still has 1 pending comment(s)" in result.stdout


@requires_bash
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_gate_five_blocks_a_pending_comment_map(path: Path, tmp_path: Path) -> None:
    """Gate 5 owns the same blocking check and must also exit nonzero.

    Its condition also reads the unresolved-thread count, which the slice
    stubs to zero, so a nonzero exit here can only come from pending work.
    """
    comment_map = _render_comment_map(tmp_path, PENDING_COMMENT_MAP_LINES)
    _record_api_count(tmp_path, API_COMMENT_COUNT)
    script = _derivation_script(_gate_fence(path, "Gate 5"), comment_map)

    result = _run_derivation(script, cwd=tmp_path)

    assert result.returncode == 1, (
        f"{_carrier_id(path)} Gate 5 cleared a comment map holding 1 pending "
        f"comment: exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "[BLOCKED] API unresolved: 0, Artifact pending: 1" in result.stdout


@requires_bash
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_a_missing_count_artifact_blocks_the_gate(path: Path, tmp_path: Path) -> None:
    """No recorded API count means the invariant has nothing to check.

    This is the shape the review reported: ``$TOTAL_COMMENTS`` never reached
    the gate, so the comparison errored, read as false, and a comment map with
    zero status fields passed. The gate must refuse to run instead.
    """
    comment_map = _render_comment_map(tmp_path, STRIPPED_COMMENT_MAP_LINES)
    count_file = _record_api_count(tmp_path, None)
    assert not count_file.exists(), "the missing-artifact case must start with no artifact"
    script = _derivation_script(_gate_four_fence(path), comment_map)

    result = _run_derivation(script, cwd=tmp_path)

    assert result.returncode == 1, (
        f"{_carrier_id(path)} Gate 4 ran without a recorded API count: "
        f"exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "[BLOCKED] API comment count not recorded" in result.stdout
    assert "PENDING=" not in result.stdout


@requires_bash
@pytest.mark.parametrize("bad_value", ["", "null", "-1", "3abc"])
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_a_non_numeric_recorded_count_blocks_the_gate(
    path: Path, bad_value: str, tmp_path: Path
) -> None:
    """A recorded count that is not a number must fail closed.

    Phase 1 sets the count via ``jq`` without ``-e``; an API or script failure
    records an empty string or ``null``. ``[ "$TOTAL" -ne "$TOTAL_COMMENTS" ]``
    on a non-numeric right side prints ``integer expression expected`` and
    exits 2, which ``if`` reads as false, so the BLOCKED body is skipped and a
    terminal-looking map clears this fail-closed gate anyway.
    """
    comment_map = _render_comment_map(tmp_path, COMPLETE_COMMENT_MAP_LINES)
    _record_api_count(tmp_path, bad_value)
    script = _derivation_script(_gate_four_fence(path), comment_map)

    result = _run_derivation(script, cwd=tmp_path)

    assert result.returncode == 1, (
        f"{_carrier_id(path)} accepted a recorded count of {bad_value!r}: "
        f"exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "[BLOCKED] Recorded comment count is not numeric" in result.stdout
    assert "PENDING=" not in result.stdout


@requires_bash
def test_without_the_count_read_an_unset_variable_clears_the_gate(tmp_path: Path) -> None:
    """Negative control: reading the artifact is what makes the invariant fire.

    Remove only the count-artifact read and the fence is the shape the review
    reported: ``$TOTAL_COMMENTS`` is unset, ``[ -ne ]`` exits 2 on the empty
    right side, ``if`` reads that as false, and a comment map with every status
    field stripped exits 0 reporting zero pending. The shipped fence, given the
    same map and the same empty environment, exits 1.
    """
    fence = _gate_four_fence(REPO_ROOT / "templates/agents/pr-comment-responder.shared.md")
    comment_map = _render_comment_map(tmp_path, STRIPPED_COMMENT_MAP_LINES)
    count_file = _record_api_count(tmp_path, None)
    assert not count_file.exists()

    without = _run_derivation(
        _derivation_script(fence, comment_map, with_count_read=False), cwd=tmp_path
    )
    shipped = _run_derivation(_derivation_script(fence, comment_map), cwd=tmp_path)

    assert without.returncode == 0, (
        "the pre-fix shape must reproduce the fail-open, or this control "
        "proves nothing about the fix"
    )
    assert "PENDING=0" in without.stdout
    assert "integer expression expected" in without.stderr
    assert shipped.returncode == 1
    assert "[BLOCKED] API comment count not recorded" in shipped.stdout


@requires_bash
def test_without_the_invariant_a_stripped_map_clears_the_gate(tmp_path: Path) -> None:
    """Negative control: the invariant is what catches the stripped map.

    Take the shipped Gate 4 derivation, remove only the API-count invariant,
    and the same stripped map exits 0 with zero pending. That is the fail-open
    Copilot reported on PR #5342, reproduced against the real shell.
    """
    fence = _gate_four_fence(REPO_ROOT / "templates/agents/pr-comment-responder.shared.md")
    comment_map = _render_comment_map(tmp_path, STRIPPED_COMMENT_MAP_LINES)
    _record_api_count(tmp_path, API_COMMENT_COUNT)

    without = _run_derivation(
        _derivation_script(fence, comment_map, with_invariant=False), cwd=tmp_path
    )
    with_invariant = _run_derivation(_derivation_script(fence, comment_map), cwd=tmp_path)

    assert without.returncode == 0
    assert "PENDING=0" in without.stdout
    assert with_invariant.returncode == 1


@requires_bash
@pytest.mark.parametrize("path", VOCABULARY_CARRIERS, ids=_carrier_id)
def test_the_recorded_count_reaches_the_gate_that_reads_it(path: Path, tmp_path: Path) -> None:
    """Run Phase 1's writer and Gate 4's reader against one filesystem.

    Comparing the two published path literals would only prove the document is
    internally consistent. Executing the writer, then the reader, in the same
    working directory proves the artifact the workflow creates is the artifact
    the gate opens, which is the whole point of moving the count out of a
    shell variable.
    """
    record = _count_record_fence(path)
    comment_map = _render_comment_map(tmp_path, COMPLETE_COMMENT_MAP_LINES)
    count_file = _record_api_count(tmp_path, None)
    assert not count_file.exists(), "Phase 1 must be the step that creates the artifact"

    written = _run_derivation(f"TOTAL_COMMENTS={API_COMMENT_COUNT}\n{record}\n", cwd=tmp_path)
    assert written.returncode == 0, (
        f"{_carrier_id(path)} Phase 1 failed to record the count: {written.stderr!r}"
    )
    assert count_file.exists(), (
        f"{_carrier_id(path)} Phase 1 wrote no artifact at {COUNT_ARTIFACT_PATH}"
    )

    result = _run_derivation(_derivation_script(_gate_four_fence(path), comment_map), cwd=tmp_path)

    assert result.returncode == 0, (
        f"{_carrier_id(path)} Gate 4 rejected the count Phase 1 recorded: "
        f"exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "PENDING=0" in result.stdout


def _work_appended_row_to_terminal(comment_map: Path) -> None:
    """Stand in for the agent's Phase 5 work on the row Phase 8.3 appended.

    Phase 5 rewrites the status field with a ``sed`` range edit once the fix
    lands. Only that one field is touched here; the heading and the block Phase
    8.3 wrote are left exactly as the fence emitted them, so what Gate 4 counts
    is still the fence's output and not the test's.
    """
    text = comment_map.read_text(encoding="utf-8")
    assert text.count(APPENDED_STATUS_LINE) == 1, (
        "expected exactly one appended [NEW] row to work to terminal"
    )
    comment_map.write_text(
        text.replace(APPENDED_STATUS_LINE, "**Status**: [COMPLETE]"), encoding="utf-8"
    )


@requires_bash
@requires_jq
@requires_python3
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_phase_eight_three_appends_the_new_comment_then_the_gate_clears(
    path: Path, tmp_path: Path
) -> None:
    """Run Phase 8.3 against a real pre-append map, then run Gate 4 on its output.

    The starting state is the three-comment map Phase 1 built and the count it
    recorded. Phase 8.3 is handed a payload reporting four, and the fence
    itself has to fetch the fourth and write its ``### Comment`` block at a
    non-terminal status. Asserting that mutation before the gate runs is the
    point: the earlier version of this test wrote the four-comment map itself,
    so it stayed green while the append was a bare shell comment (Copilot
    review of commit e82aa27cc).
    """
    count_file = _record_api_count(tmp_path, API_COMMENT_COUNT)
    comment_map = _render_session_comment_map(tmp_path, COMPLETE_COMMENT_MAP_LINES)
    before = comment_map.read_text(encoding="utf-8")
    assert APPENDED_HEADING not in before, "the pre-append map must not carry the new row"
    scripts_dir = _install_recheck_producer(tmp_path, _recheck_payload(SECOND_PASS_COMMENTS))

    refreshed = _run_derivation(
        _recheck_script(_recheck_fence(path), scripts_dir),
        cwd=tmp_path,
    )

    assert refreshed.returncode == 0, (
        f"{_carrier_id(path)} Phase 8.3 failed on a new comment: "
        f"exit {refreshed.returncode}, stdout {refreshed.stdout!r}, "
        f"stderr {refreshed.stderr!r}"
    )
    assert "[NEW COMMENTS] 1 new comments detected" in refreshed.stdout

    after = comment_map.read_text(encoding="utf-8")
    assert APPENDED_HEADING in after, (
        f"{_carrier_id(path)} Phase 8.3 advanced the recorded count without "
        f"appending {APPENDED_HEADING!r} to the map"
    )
    assert after.count(APPENDED_STATUS_LINE) == 1, (
        f"{_carrier_id(path)} Phase 8.3 appended the row at a status other "
        f"than {APPENDED_STATUS_LINE!r}, or appended it more than once"
    )
    assert after.startswith(before), "the append must not rewrite the rows already in the map"
    assert count_file.read_text(encoding="utf-8").strip() == str(SECOND_PASS_COMMENT_COUNT), (
        f"{_carrier_id(path)} left the recorded count behind the appended map"
    )

    _work_appended_row_to_terminal(comment_map)
    result = _run_derivation(_derivation_script(_gate_four_fence(path), comment_map), cwd=tmp_path)

    assert result.returncode == 0, (
        f"{_carrier_id(path)} Gate 4 blocked a second pass in which every "
        f"comment reached a terminal status: exit {result.returncode}, "
        f"stdout {result.stdout!r}"
    )
    assert "PENDING=0" in result.stdout


@requires_bash
@requires_jq
@requires_python3
def test_the_shipped_stub_advances_the_count_and_never_appends(tmp_path: Path) -> None:
    """Negative control: today's shipped Phase 8.3, reproduced exactly.

    PR #5342 shipped the count read, a bare ``# Fetch new comments`` comment
    where the append belongs, and the refresh. Stripping the append and the
    verification from the canonical fence rebuilds that shape. The recorded
    count advances to four, the map still carries three rows, and every later
    gate blocks on the difference. The assertions the positive test makes on
    the appended row have to fail here, or they prove nothing about the fence.
    """
    path = REPO_ROOT / "templates/agents/pr-comment-responder.shared.md"
    count_file = _record_api_count(tmp_path, API_COMMENT_COUNT)
    comment_map = _render_session_comment_map(tmp_path, COMPLETE_COMMENT_MAP_LINES)
    scripts_dir = _install_recheck_producer(tmp_path, _recheck_payload(SECOND_PASS_COMMENTS))

    stub = _run_derivation(
        _recheck_script(
            _recheck_fence(path),
            scripts_dir,
            with_append=False,
            with_verify=False,
        ),
        cwd=tmp_path,
    )

    assert stub.returncode == 0, "the shipped stub exited 0; the control must reproduce that"
    assert APPENDED_HEADING not in comment_map.read_text(encoding="utf-8"), (
        "the control must reproduce the missing append, not perform it"
    )
    assert count_file.read_text(encoding="utf-8").strip() == str(SECOND_PASS_COMMENT_COUNT)

    result = _run_derivation(_derivation_script(_gate_four_fence(path), comment_map), cwd=tmp_path)

    assert result.returncode == 1, (
        "a count advanced past a map that never grew has to block Gate 4, "
        f"but the gate exited {result.returncode}: {result.stdout!r}"
    )
    assert "[BLOCKED] Comment map carries 3 status fields, API reported 4" in result.stdout


@requires_bash
@requires_jq
@requires_python3
def test_the_refresh_is_refused_when_the_append_does_not_land(tmp_path: Path) -> None:
    """Phase 8.3 must not write a count the map cannot support.

    The refresh is the one write that can clear the API-count invariant, so a
    refresh over a map that never grew is the fail-open the invariant exists to
    catch, produced by the line that feeds it. Removing only the append leaves
    the verification in place, and the fence has to block rather than record a
    total it just failed to create.
    """
    path = REPO_ROOT / "templates/agents/pr-comment-responder.shared.md"
    count_file = _record_api_count(tmp_path, API_COMMENT_COUNT)
    _render_session_comment_map(tmp_path, COMPLETE_COMMENT_MAP_LINES)
    scripts_dir = _install_recheck_producer(tmp_path, _recheck_payload(SECOND_PASS_COMMENTS))

    result = _run_derivation(
        _recheck_script(
            _recheck_fence(path),
            scripts_dir,
            with_append=False,
        ),
        cwd=tmp_path,
    )

    assert result.returncode == 1, (
        f"Phase 8.3 recorded a count its own append never produced: {result.stdout!r}"
    )
    assert "[BLOCKED] Comment map carries 3 status fields after the append" in result.stdout
    assert count_file.read_text(encoding="utf-8").strip() == str(API_COMMENT_COUNT), (
        "the refresh must not run once the verification blocks"
    )


@requires_bash
@requires_jq
@requires_python3
def test_without_the_refresh_a_second_pass_can_never_clear(tmp_path: Path) -> None:
    """Negative control for the refresh (PR #5342 review).

    An earlier Phase 8.3 read the count and appended with no write back to the
    artifact. The map then carried four status fields against a recorded three,
    so Gate 4's API-count invariant blocked, and nothing an agent could do to
    the comments moved either number. Removing only the refresh reproduces it,
    against the four-comment map the fence's own append produced.
    """
    path = REPO_ROOT / "templates/agents/pr-comment-responder.shared.md"
    _record_api_count(tmp_path, API_COMMENT_COUNT)
    comment_map = _render_session_comment_map(tmp_path, COMPLETE_COMMENT_MAP_LINES)
    scripts_dir = _install_recheck_producer(tmp_path, _recheck_payload(SECOND_PASS_COMMENTS))

    stale = _run_derivation(
        _recheck_script(
            _recheck_fence(path),
            scripts_dir,
            with_refresh=False,
        ),
        cwd=tmp_path,
    )
    assert stale.returncode == 0
    assert APPENDED_HEADING in comment_map.read_text(encoding="utf-8"), (
        "the append must still run; only the refresh is under control here"
    )

    _work_appended_row_to_terminal(comment_map)
    result = _run_derivation(_derivation_script(_gate_four_fence(path), comment_map), cwd=tmp_path)

    assert result.returncode == 1, (
        "without the refresh a fully worked second pass still has to block, "
        f"but the gate exited {result.returncode}: {result.stdout!r}"
    )
    assert "[BLOCKED] Comment map carries 4 status fields, API reported 3" in result.stdout


# The three ways the re-fetch can come back unusable, each paired with the
# producer exit status that produces it and the diagnostic the fence owes the
# reader. A case per shape so a regression names the one it readmitted.
BROKEN_RECHECK_CASES: tuple[tuple[str, str, int, str], ...] = (
    (
        "producer-failure",
        "",
        1,
        "[BLOCKED] Comment re-fetch failed (exit 1)",
    ),
    (
        "unparseable-payload",
        UNPARSEABLE_PAYLOAD,
        0,
        "[BLOCKED] Comment re-fetch payload is not parseable JSON",
    ),
    (
        "keyless-payload",
        KEYLESS_PAYLOAD,
        0,
        "[BLOCKED] Re-fetched comment count is not numeric: null",
    ),
)


@requires_bash
@requires_jq
@requires_python3
@pytest.mark.parametrize(
    ("payload", "exit_code", "expected"),
    [case[1:] for case in BROKEN_RECHECK_CASES],
    ids=[case[0] for case in BROKEN_RECHECK_CASES],
)
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_a_broken_recheck_blocks_instead_of_reading_as_no_new_comments(
    path: Path, payload: str, exit_code: int, expected: str, tmp_path: Path
) -> None:
    """A re-fetch that fails or returns garbage must block Phase 8.3.

    The re-fetch is the only thing in the loop that can see a comment posted
    since the last pass, so treating its failure as "nothing arrived" clears the
    exact case the phase exists for. The fence's own producer line runs against
    a stand-in that reproduces each failure, and the shipped guards are what
    have to turn it into a nonzero exit.
    """
    count_file = _record_api_count(tmp_path, API_COMMENT_COUNT)
    comment_map = _render_session_comment_map(tmp_path, COMPLETE_COMMENT_MAP_LINES)
    scripts_dir = _install_recheck_producer(tmp_path, payload, exit_code=exit_code)

    result = _run_derivation(_recheck_script(_recheck_fence(path), scripts_dir), cwd=tmp_path)

    assert result.returncode == 1, (
        f"{_carrier_id(path)} Phase 8.3 continued past a broken re-fetch: "
        f"exit {result.returncode}, stdout {result.stdout!r}, "
        f"stderr {result.stderr!r}"
    )
    assert expected in result.stdout, (
        f"{_carrier_id(path)} blocked without naming the failure: {result.stdout!r}"
    )
    assert count_file.read_text(encoding="utf-8").strip() == str(API_COMMENT_COUNT), (
        "a blocked re-fetch must not move the recorded count"
    )
    assert APPENDED_HEADING not in comment_map.read_text(encoding="utf-8"), (
        "a blocked re-fetch must not append rows the payload never carried"
    )


@requires_bash
@requires_jq
@requires_python3
@pytest.mark.parametrize(
    ("payload", "exit_code"),
    [case[1:3] for case in BROKEN_RECHECK_CASES],
    ids=[case[0] for case in BROKEN_RECHECK_CASES],
)
def test_without_the_fetch_guards_a_broken_recheck_reads_as_no_new_comments(
    payload: str, exit_code: int, tmp_path: Path
) -> None:
    """Negative control: the fail-open PR #5342 shipped, reproduced exactly.

    The shipped fence assigned RECHECK_PAYLOAD without reading the producer's
    exit status and derived NEW_COMMENTS with a bare ``jq '.TotalComments'``.
    Stripping only the two guards rebuilds that shape. Every case here exits 0
    with no diagnostic and no append, which is a pass reporting no new comments
    on a re-fetch that never returned a count. If these assertions did not hold,
    the positive test above would prove nothing about the guards.
    """
    path = REPO_ROOT / "templates/agents/pr-comment-responder.shared.md"
    _record_api_count(tmp_path, API_COMMENT_COUNT)
    comment_map = _render_session_comment_map(tmp_path, COMPLETE_COMMENT_MAP_LINES)
    scripts_dir = _install_recheck_producer(tmp_path, payload, exit_code=exit_code)

    result = _run_derivation(
        _recheck_script(_recheck_fence(path), scripts_dir, with_fetch_guards=False),
        cwd=tmp_path,
    )

    assert result.returncode == 0, (
        "the control must reproduce the shipped fail-open, which exited 0: "
        f"exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "[BLOCKED]" not in result.stdout, (
        f"the control must block nothing, but printed {result.stdout!r}"
    )
    assert "[NEW COMMENTS]" not in result.stdout, (
        "the shipped shape skipped the branch entirely rather than entering it"
    )
    assert APPENDED_HEADING not in comment_map.read_text(encoding="utf-8"), (
        "the control must reproduce the skipped branch, not perform the append"
    )


@requires_bash
@requires_jq
@requires_python3
def test_a_healthy_recheck_with_no_new_comments_still_clears(tmp_path: Path) -> None:
    """The guards must not block the case they sit in front of.

    A re-fetch that succeeds and reports the same count the artifact records is
    the ordinary quiet pass. Blocking it would turn every clean loop into a
    false stop, which is the inverse failure of the fail-open under test.
    """
    path = REPO_ROOT / "templates/agents/pr-comment-responder.shared.md"
    count_file = _record_api_count(tmp_path, API_COMMENT_COUNT)
    comment_map = _render_session_comment_map(tmp_path, COMPLETE_COMMENT_MAP_LINES)
    scripts_dir = _install_recheck_producer(tmp_path, _recheck_payload(FIRST_PASS_COMMENTS))

    result = _run_derivation(_recheck_script(_recheck_fence(path), scripts_dir), cwd=tmp_path)

    assert result.returncode == 0, (
        f"Phase 8.3 blocked a healthy re-fetch reporting no new comments: "
        f"exit {result.returncode}, stdout {result.stdout!r}, stderr {result.stderr!r}"
    )
    assert "[BLOCKED]" not in result.stdout
    assert "[NEW COMMENTS]" not in result.stdout
    assert count_file.read_text(encoding="utf-8").strip() == str(API_COMMENT_COUNT)
    assert APPENDED_HEADING not in comment_map.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", VOCABULARY_CARRIERS, ids=_carrier_id)
def test_phase_one_records_the_api_count_on_every_retrieval_path(path: Path) -> None:
    """Both retrieval paths must record the count, not just the preferred one.

    The raw ``gh`` alternative computes the same total. A carrier that records
    on one path only leaves every gate blocked for anyone who took the other.
    """
    text = path.read_text(encoding="utf-8")
    records = [body for _, body in _bash_fences(text) if COUNT_RECORD_STEPS[2] in body]

    assert len(records) == 2, (
        f"{_carrier_id(path)} records the API count in {len(records)} fence(s); "
        f"the preferred and raw-gh retrieval paths both need it"
    )
    for body in records:
        for step in COUNT_RECORD_STEPS:
            assert step in body, f"{_carrier_id(path)} records the count without {step!r}"


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_status_greps_anchor_to_bold_comment_map_field(path: Path) -> None:
    """Every carrier must grep the emitted bold status field, not dead text."""
    assert path.exists(), f"Expected carrier at {_carrier_id(path)}"
    text = path.read_text(encoding="utf-8")

    for pattern_text in REQUIRED_PATTERN_TEXT:
        assert pattern_text in text, (
            f"{_carrier_id(path)} must use anchored comment-map "
            f"status pattern {pattern_text!r} for issues #4034 and #4054"
        )

    dead = [
        f"line {number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), 1)
        if DEAD_STATUS_FIELD_RE.search(line)
    ]
    assert not dead, (
        f"{_carrier_id(path)} still references an unbolded status "
        f"field that greps zero rows: {dead}"
    )


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_no_carrier_enumerates_pending_statuses(path: Path) -> None:
    """No gate may enumerate pending statuses; an unlisted status must block."""
    text = path.read_text(encoding="utf-8")

    offenders = [
        f"line {number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), 1)
        for pattern in GREP_ANY_PATTERN_RE.findall(line)
        if ENUMERATED_PENDING_RE.search(pattern)
    ]
    assert not offenders, (
        f"{_carrier_id(path)} still enumerates pending statuses, so a "
        f"status outside the table is counted as non-pending and the gate passes "
        f"(issue #4054): {offenders}"
    )


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_no_carrier_reads_a_retired_status_accumulator(path: Path) -> None:
    """The subtraction retired ADDRESSED and WONTFIX as separate counts.

    Bash reads an unset name in arithmetic as 0, so a leftover
    ``$((ADDRESSED + WONTFIX))`` prints ``0`` for a run in which every comment
    reached a terminal status, contradicting the checklist row directly above
    it. Nothing else in this suite can catch a retired variable: the dead-field
    detector matches status spellings, not accumulator names.
    """
    offenders = [
        f"line {number}: {line.strip()}"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if RETIRED_ACCUMULATOR_RE.search(line)
    ]
    assert not offenders, (
        f"{_carrier_id(path)} still reads an accumulator the terminal-count "
        f"derivation retired, which reports 0 resolved on a finished run "
        f"(issue #4054): {offenders}"
    )


@pytest.mark.parametrize("path", VOCABULARY_CARRIERS, ids=_carrier_id)
def test_the_comment_index_template_renders_no_status_cell(path: Path) -> None:
    """Step 2.2 must not publish a status the vocabulary table does not define.

    The index rendered ``pending``, a value that appears in no row of the
    authoritative table the same document calls the only place the vocabulary
    is defined. Gate 3 never rewrites the index, so a fully worked PR ended
    with the index reading ``pending`` for every comment while the detail entry
    read terminal: the two-disagreeing-representations defect issue #4054 is
    about, moved from the vocabulary tables into the comment map itself.
    """
    text = path.read_text(encoding="utf-8")
    assert text.count(COMMENT_INDEX_HEADING) == 1, (
        f"{_carrier_id(path)} publishes {text.count(COMMENT_INDEX_HEADING)} "
        f"comment indexes; the template renders exactly one"
    )

    rows = _comment_index_rows(text)
    assert len(rows) == 3, (
        f"{_carrier_id(path)} comment index has {len(rows)} table lines, "
        f"expected a header, a separator, and one template row"
    )
    assert "Status" not in rows[0], (
        f"{_carrier_id(path)} comment index still declares a Status column, "
        f"which Gate 3 never writes back: {rows[0]}"
    )
    offenders = [row for row in rows if INDEX_STATUS_TOKEN_RE.search(row)]
    assert not offenders, (
        f"{_carrier_id(path)} comment index renders a status token that Gate 3 "
        f"never updates, so it disagrees with the detail entry: {offenders}"
    )


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_phase_eight_one_blocks_instead_of_warning(path: Path) -> None:
    """Phase 8.1 is a gate. A warning-only copy lets pending comments through."""
    text = path.read_text(encoding="utf-8")
    if "Phase 8.1" not in text:
        pytest.skip(f"{_carrier_id(path)} carries no Phase 8.1 sub-gate")

    assert "[WARNING] INCOMPLETE" not in text, (
        f"{_carrier_id(path)} Phase 8.1 warns instead of blocking, so pending "
        f"comments do not stop the run (issue #4054)"
    )
    assert "[BLOCKED] INCOMPLETE" in text, (
        f"{_carrier_id(path)} Phase 8.1 must print a [BLOCKED] diagnostic"
    )


@pytest.mark.parametrize("path", SKILL_ENTRYPOINTS, ids=_carrier_id)
def test_skill_entrypoint_completion_criteria_name_every_terminal_status(
    path: Path,
) -> None:
    """The entrypoint states completion; a stale copy narrows the vocabulary.

    ``SKILL.md`` is what an agent reads before it reaches the gates. While it
    defined completion as ``COMPLETE or WONTFIX`` it contradicted the gates,
    which also accept ``[DUPLICATE]`` and a tracked ``[DEFERRED]``. An agent
    following the entrypoint would keep working comments the gates already
    counted terminal, or file the outcome under the wrong status.
    """
    text = path.read_text(encoding="utf-8")

    assert "COMPLETE or WONTFIX" not in text, (
        f"{_carrier_id(path)} still defines completion as the two-status "
        f"vocabulary that predates [DUPLICATE] and [DEFERRED] (issue #4054)"
    )
    for status in TERMINAL_STATUS_TOKENS:
        assert status in text, (
            f"{_carrier_id(path)} completion criteria omit {status}, so an "
            f"agent reading the entrypoint gets criteria the gates disagree with"
        )


# The vocabulary table is the single authority the greps are derived from.


@pytest.mark.parametrize("path", VOCABULARY_CARRIERS, ids=_carrier_id)
def test_vocabulary_is_published_exactly_once(path: Path) -> None:
    """One table, one vocabulary. A second copy is how statuses go missing."""
    text = path.read_text(encoding="utf-8")
    assert text.count(TABLE_HEADER) == 1, (
        f"{_carrier_id(path)} publishes {text.count(TABLE_HEADER)} status "
        f"vocabulary tables; issue #4054 requires exactly one"
    )


@pytest.mark.parametrize("path", GATE_REFERENCE_CARRIERS, ids=_carrier_id)
def test_gate_references_do_not_restate_the_vocabulary(path: Path) -> None:
    """The skill reference points at the agent's table; it never copies it."""
    text = path.read_text(encoding="utf-8")
    assert TABLE_HEADER not in text, (
        f"{_carrier_id(path)} restates the status vocabulary; a second copy is "
        f"how [DUPLICATE] and [DEFERRED] went missing (issue #4054)"
    )


@pytest.mark.parametrize("path", VOCABULARY_CARRIERS, ids=_carrier_id)
def test_vocabulary_section_publishes_fail_closed_derivation(path: Path) -> None:
    """The vocabulary section must show how pending is derived, fail closed."""
    section = _vocabulary_section(path.read_text(encoding="utf-8"))

    assert FAIL_CLOSED_DERIVATION in section, (
        f"{_carrier_id(path)} vocabulary section must publish "
        f"{FAIL_CLOSED_DERIVATION!r}, not an enumerating pending grep"
    )
    assert sorted(GREP_COUNT_PATTERN_RE.findall(section)) == sorted(REQUIRED_PATTERN_TEXT), (
        f"{_carrier_id(path)} vocabulary section must count only the "
        f"status-line total and the terminal statuses {REQUIRED_PATTERN_TEXT}"
    )


@pytest.mark.parametrize("path", VOCABULARY_CARRIERS, ids=_carrier_id)
def test_table_terminal_column_agrees_with_the_terminal_grep(path: Path) -> None:
    """Every status the table calls terminal must be in the terminal grep."""
    section = _vocabulary_section(path.read_text(encoding="utf-8"))

    tabled_terminal: set[str] = set()
    tabled_pending: set[str] = set()
    for line in section.splitlines():
        match = VOCABULARY_ROW_RE.match(line)
        if match is None:
            continue
        target = (
            tabled_terminal if match.group("terminal").strip().startswith("Yes") else tabled_pending
        )
        target.add(match.group("status"))

    assert tabled_terminal, f"{_carrier_id(path)} table parsed no terminal rows"
    assert tabled_terminal == _terminal_statuses_in_pattern(TERMINAL_PATTERN), (
        f"{_carrier_id(path)} table marks {sorted(tabled_terminal)} terminal "
        f"but the grep matches {sorted(_terminal_statuses_in_pattern(TERMINAL_PATTERN))}"
    )
    assert not tabled_pending & tabled_terminal
    assert tabled_pending == {"NEW", "ACKNOWLEDGED"}


# The Python-side detectors this suite uses to scan the carriers.


def test_dead_detector_flags_the_pattern_shipped_before_this_fix() -> None:
    """The detector must catch every alternative of the old dead example."""
    dead_line = '`grep -Ec "Status: \\[NEW\\]|Status: \\[ACKNOWLEDGED\\]|Status: pending"`.'
    assert DEAD_STATUS_FIELD_RE.findall(dead_line) == [
        "Status: \\[NEW\\]",
        "Status: \\[ACKNOWLEDGED\\]",
        "Status: pending",
    ]
    assert DEAD_STATUS_FIELD_RE.search("Status: [DUPLICATE]")
    assert DEAD_STATUS_FIELD_RE.search("Status: [DEFERRED]")
    assert not DEAD_STATUS_FIELD_RE.search("**Status**: [NEW]")
    assert DEAD_STATUS_FIELD_RE.search("**Status: [NEW]")


def test_enumerated_pending_detector_flags_the_shape_shipped_before_this_fix() -> None:
    """The detector must catch the fail-open greps issue #4054 reports."""
    gate_five = (
        r"^\*\*Status\*\*: pending|^\*\*Status\*\*: \[ACKNOWLEDGED\]"
        r"|^\*\*Status\*\*: \[NEW\]"
    )
    assert ENUMERATED_PENDING_RE.search(gate_five)
    assert ENUMERATED_PENDING_RE.search(r"^\*\*Status\*\*: \[NEW\]")
    assert not ENUMERATED_PENDING_RE.search(TERMINAL_PATTERN)
    assert not ENUMERATED_PENDING_RE.search(STATUS_LINE_PATTERN)


def test_retired_accumulator_detector_flags_the_shape_shipped_before_this_fix() -> None:
    """The detector must catch the accumulators, not the status vocabulary.

    ``[WONTFIX]`` is a live terminal status and appears in the table, in the
    terminal grep, and in prose. Flagging any of those would make the sweep
    unusable, so the detector keys on the accumulator spellings alone.
    """
    assert RETIRED_ACCUMULATOR_RE.search(
        'echo "[ ] Comments: $((ADDRESSED + WONTFIX))/$TOTAL resolved"'
    )
    assert RETIRED_ACCUMULATOR_RE.search('WONTFIX=$(grep -c "wontfix" "$COMMENT_MAP")')
    assert RETIRED_ACCUMULATOR_RE.search('echo "$WONTFIX"')
    assert RETIRED_ACCUMULATOR_RE.search("ADDRESSED=0")

    assert not RETIRED_ACCUMULATOR_RE.search(
        "| `[WONTFIX]` | Explicitly decided not to change | Yes |"
    )
    assert not RETIRED_ACCUMULATOR_RE.search(TERMINAL_PATTERN)
    assert not RETIRED_ACCUMULATOR_RE.search("**Status**: [ACKNOWLEDGED]")
    assert not RETIRED_ACCUMULATOR_RE.search("Track, Map, Addressed, Conversation")


def test_index_status_detector_flags_the_cell_shipped_before_this_fix() -> None:
    """The detector must catch the retired ``pending`` cell and any status token."""
    assert INDEX_STATUS_TOKEN_RE.search(
        "| [id] | @[author] | review/issue | [path]#[line] | pending | TBD | - |"
    )
    assert INDEX_STATUS_TOKEN_RE.search(
        "| [id] | @[author] | review/issue | [path]#[line] | [ACKNOWLEDGED] | TBD | - |"
    )
    assert not INDEX_STATUS_TOKEN_RE.search(
        "| [id] | @[author] | review/issue | [path]#[line] | TBD | - |"
    )
    assert not INDEX_STATUS_TOKEN_RE.search("| ID | Author | Type | Path/Line | Priority |")


def test_terminal_statuses_in_pattern_reads_the_alternation() -> None:
    """The table-vs-grep comparison depends on parsing the alternation."""
    assert _terminal_statuses_in_pattern(TERMINAL_PATTERN) == {
        "COMPLETE",
        "WONTFIX",
        "DUPLICATE",
        "DEFERRED",
    }
    assert _terminal_statuses_in_pattern(STATUS_LINE_PATTERN) == set()
