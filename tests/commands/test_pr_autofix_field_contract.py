"""Contract test between `pr-autofix.md`'s jq reads and its producer scripts.

Refs #5094. The `/pr-autofix` command body pipes producer scripts through `jq`
and branches on the result. When a read names a path the producer never emits,
`jq` yields `null`, the `//` default fires, and the gate silently evaluates as
if it had evidence. Nothing fails; the gate just stops gating.

That defect shipped twice in this file, one script apart. First `TIER` read
`.Data.tier` from `check_pr_live_state.py`, which emits no tier field at all.
The repair then pointed at the right script but kept the envelope, reading
`.Data.Tier` from `test_pr_merge_ready.py`, which has no `--output-format` flag
and prints its result dict directly. Both instances left `TIER` pinned at
`UNKNOWN`.

A stuck sentinel does not fail one way. It fails whichever way each comparison
happens to read it, and the two gates downstream compare it in opposite
directions:

===========================  ==============================  =========================
Gate                         Condition                       Effect of TIER=UNKNOWN
===========================  ==============================  =========================
Round-cap circuit breaker    ``TIER = T3`` or ``TIER = T4``   never fired
Auto-merge disarm            ``TIER != T1``                   fired on every armed PR
===========================  ==============================  =========================

So the round-cap breaker was inert, while the disarm gate was stuck on and
stripped auto-merge from every armed PR, including genuine T1 PRs that had
earned it. Fixing the read arms the first and lets the second discriminate.
Calling both of them "disabled" is wrong in the second case, and this docstring
said so until Copilot caught it on PR #5176.

These tests close the class rather than the instance: every read in the command
body is checked against its producer's derived schema, in both envelope
directions and for field names on both producer styles. The parser lives in
`pr_autofix_field_parser.py`.
"""

from __future__ import annotations

import pytest

from tests.commands.pr_autofix_field_parser import (
    COMMAND_PATH,
    MIRROR_PATH,
    FieldRead,
    contract_violations,
    derive_producer_schema,
    extract_field_reads,
    jq_invocation_count,
    jq_invocation_lines,
    jq_paths,
    jq_programs,
    logical_lines,
    pathless_jq_programs,
    unparsed_jq_invocations,
)


@pytest.fixture(scope="module")
def command_body() -> str:
    return COMMAND_PATH.read_text(encoding="utf-8")


# Positive: the shipped command and its mirror honor every producer contract.


def test_source_command_has_no_contract_violations(command_body: str) -> None:
    violations = contract_violations(command_body)

    assert violations == [], "pr-autofix.md reads fields its producers never emit:\n" + "\n".join(
        violations
    )


def test_copilot_mirror_has_no_contract_violations() -> None:
    violations = contract_violations(MIRROR_PATH.read_text(encoding="utf-8"))

    assert violations == [], (
        "The shipped Copilot mirror drifted from producer contracts:\n" + "\n".join(violations)
    )


def test_mirror_reads_match_source_reads(command_body: str) -> None:
    """The mirror is generated, so its reads must equal the source's reads."""
    source = [(r.script, r.path) for r in extract_field_reads(command_body)]
    mirror = [
        (r.script, r.path) for r in extract_field_reads(MIRROR_PATH.read_text(encoding="utf-8"))
    ]

    assert source == mirror, (
        "src/copilot-cli/skills/pr-autofix/SKILL.md is stale. Re-run "
        "`uv run python build/scripts/generate_commands.py`."
    )


def test_tier_read_targets_the_authoritative_flat_producer(command_body: str) -> None:
    """Pin the specific regression from issue #5094 and its repeat."""
    tier_reads = [r for r in extract_field_reads(command_body) if r.path.endswith("Tier")]

    assert tier_reads, "The TIER read vanished; the round-cap gate lost its input."
    for read in tier_reads:
        assert read.script == "test_pr_merge_ready", (
            f"line {read.line}: tier must come from test_pr_merge_ready.py, the "
            f"authoritative tier source, not {read.script}.py."
        )
        assert read.path == ".Tier", (
            f"line {read.line}: expected `.Tier`, got `{read.path}`. "
            "test_pr_merge_ready.py emits no Data envelope."
        )


# Coverage: the extractor must not go blind and silently pass.


def test_every_read_binds_to_a_producer(command_body: str) -> None:
    """An unbound read is unchecked, so treat it as a failure, not a skip."""
    unbound = [r for r in extract_field_reads(command_body) if r.script is None]

    assert unbound == [], "Reads that bind to no producer are unchecked:\n" + "\n".join(
        f"line {r.line}: `{r.path}`" for r in unbound
    )


def test_extractor_reaches_every_jq_invocation(command_body: str) -> None:
    """A read the extractor never saw is invisible, not reported unbound.

    `test_every_read_binds_to_a_producer` only covers reads that were found.
    This compares against the jq invocations actually present, so a quoting
    style the regexes miss fails here instead of passing silently.

    Compares per invocation, not per line and not by path count. Line presence
    lets a second jq command hide behind a parsed first one. Path count is no
    better: a multi-path program supplies enough paths to balance the arithmetic
    for a sibling the parser never read. So this asserts the parser extracted a
    program for every invocation, and got a path out of every program.
    """
    unparsed = [
        (lineno, jq_invocation_count(line), len(jq_programs(line)), line.strip())
        for lineno, line in jq_invocation_lines(command_body)
        if unparsed_jq_invocations(line)
    ]

    assert unparsed == [], "jq invocations the extractor never parsed:\n" + "\n".join(
        f"line {lineno}: {count} invocation(s), {parsed} program(s) parsed: {line[:100]}"
        for lineno, count, parsed, line in unparsed
    )

    pathless = [
        (lineno, program)
        for lineno, line in jq_invocation_lines(command_body)
        for program in pathless_jq_programs(line)
    ]

    assert pathless == [], "jq programs the extractor read no path from:\n" + "\n".join(
        f"line {lineno}: {program[:100]}" for lineno, program in pathless
    )


def test_every_consumed_producer_has_derivable_keys(command_body: str) -> None:
    """The field check must not stand down on a producer the command reads.

    `_field_violation` returns None when `top_level_keys` is None, which is
    correct for "cannot tell" but is a fail-open path: a producer refactor that
    broke derivation would silently stop field-checking every read against it,
    and every other test would stay green. Pin derivability for the producers
    actually in use so that regression fails here.
    """
    scripts = {r.script for r in extract_field_reads(command_body) if r.script}
    undecidable = sorted(s for s in scripts if derive_producer_schema(s).top_level_keys is None)

    assert undecidable == [], (
        "Field checking silently stands down for these producers:\n"
        + "\n".join(f"  {s}.py" for s in undecidable)
    )


def test_a_multi_path_program_cannot_mask_an_unparsed_sibling() -> None:
    """The masking case: enough paths to balance a count, half the line unread.

    Two jq commands on one line. The first is a multi-path program the parser
    reads fine; the second is double-quoted and yields no program at all. Path
    count comes out 2 against 2 invocations, so a path-vs-invocation comparison
    reports the line fully reached while the second command is never checked.
    Counting programs against invocations is what catches it.
    """
    line = (
        "X=$(echo \"$LIVE\" | jq -r '.Data.action // .Data.reason') && "
        'Y=$(echo "$LIVE" | jq -r ".Data.$field")'
    )

    assert jq_invocation_count(line) == 2
    assert len(jq_paths(line)) == 2, "the path count balances, which is the trap"
    assert len(jq_programs(line)) == 1, "only the single-quoted program is readable"
    assert unparsed_jq_invocations(line) == 1


def test_a_program_yielding_no_path_is_reported() -> None:
    """Read but pathless is unchecked too, one stage later than unread."""
    assert pathless_jq_programs("X=$(echo \"$L\" | jq -r 'length')") == ["length"]
    assert pathless_jq_programs("X=$(echo \"$L\" | jq -r '.Data.action')") == []


def test_multi_path_jq_programs_yield_every_path() -> None:
    """A fallback between two paths is two reads, and both must be checked."""
    assert jq_paths("X=$(echo \"$LIVE\" | jq -r '.Data.action // .Data.reason')") == [
        ".Data.action",
        ".Data.reason",
    ]


def test_literal_defaults_are_not_read_as_paths() -> None:
    """`// \"UNKNOWN\"` and `// empty` are values, not producer fields."""
    assert jq_paths("X=$(echo \"$L\" | jq -r '.Data.action // empty')") == [".Data.action"]
    assert jq_paths('X=$(echo "$L" | jq -r \'.Tier // "UNKNOWN"\')') == [".Tier"]


def test_multi_path_violation_is_reported_for_the_second_path() -> None:
    """The class stays closed on the fallback half, not just the leading path."""
    body = (
        'LIVE=$(python3 "$SCRIPTS_DIR/check_pr_live_state.py" --pull-request "$PR")\n'
        "X=$(echo \"$LIVE\" | jq -r '.Data.action // .Data.tier')\n"
    )

    violations = contract_violations(body)

    assert len(violations) == 1
    assert "emits no `tier` field" in violations[0]


def test_extractor_finds_reads_for_every_producer_style(command_body: str) -> None:
    """Both envelope styles must be represented, or the check proves little."""
    scripts = {r.script for r in extract_field_reads(command_body)}
    schemas = [derive_producer_schema(s) for s in scripts if s]

    assert any(s.wraps_in_data for s in schemas), "No Data-wrapped producer covered."
    assert any(not s.wraps_in_data for s in schemas), "No flat producer covered."


@pytest.mark.parametrize(
    ("script", "expected_wrap"),
    [
        ("test_pr_merge_ready", False),
        ("test_pr_merged", False),
        ("check_pr_live_state", True),
        ("check_pr_round_cap", True),
        ("get_pr_context", True),
        ("pr_autofix_lease", True),
    ],
)
def test_producer_envelope_classification(script: str, expected_wrap: bool) -> None:
    assert derive_producer_schema(script).wraps_in_data is expected_wrap


def test_flat_producer_keys_include_the_fields_the_command_reads() -> None:
    schema = derive_producer_schema("test_pr_merge_ready")

    assert schema.top_level_keys is not None
    assert "Tier" in schema.top_level_keys, "Tier is set via `result['Tier'] = ...`."
    assert "CanMerge" in schema.top_level_keys


# Negative controls: the check must actually fail on each known defect shape.


def _piped_read(script: str, jq_path: str) -> str:
    """A one-line command body piping `script` straight into a `jq` read."""
    return (
        f'VALUE=$(python3 "$SCRIPTS_DIR/{script}.py" --pull-request "$PR" | jq -r \'{jq_path}\')\n'
    )


def test_detects_data_prefix_on_flat_producer() -> None:
    """The exact regression this PR fixes must be caught."""
    body = _piped_read("test_pr_merge_ready", '.Data.Tier // "UNKNOWN"')

    violations = contract_violations(body)

    assert len(violations) == 1
    assert "flat object with no Data envelope" in violations[0]


def test_detects_unknown_field_on_flat_producer() -> None:
    """The originally reported shape: a field no producer emits."""
    body = _piped_read("test_pr_merge_ready", '.tier // "UNKNOWN"')

    violations = contract_violations(body)

    assert len(violations) == 1
    assert "emits no `tier` field" in violations[0]


def test_detects_missing_data_prefix_on_wrapped_producer() -> None:
    """The mirror-image defect: dropping the envelope a producer does emit."""
    body = _piped_read("check_pr_live_state", ".action")

    violations = contract_violations(body)

    assert len(violations) == 1
    assert "wraps its payload in a Data envelope" in violations[0]


def test_detects_unknown_field_on_wrapped_producer() -> None:
    """The shape issue #5094 opened on, verbatim.

    `.Data.tier` from `check_pr_live_state.py` has the right envelope and a
    field that producer never emits. An envelope-only check passes it, which is
    how the original defect stayed invisible.
    """
    body = _piped_read("check_pr_live_state", '.Data.tier // "UNKNOWN"')

    violations = contract_violations(body)

    assert len(violations) == 1
    assert "emits no `tier` field" in violations[0]


def test_wrapped_producer_payload_keys_are_derivable() -> None:
    """Field checking on wrapped producers is real, not silently skipped.

    If key derivation ever returns None the field check short-circuits and the
    negative control above passes for the wrong reason.
    """
    schema = derive_producer_schema("check_pr_live_state")

    assert schema.wraps_in_data is True
    assert schema.top_level_keys is not None
    assert {"action", "reason", "state", "head_sha", "base_sha"} <= schema.top_level_keys
    assert "tier" not in schema.top_level_keys


def test_annotated_payload_assignment_is_derived() -> None:
    """`get_pr_context.py` builds its payload as `data: dict[...] = {...}`.

    An `ast.Assign`-only walk misses `ast.AnnAssign` and yields three keys
    instead of thirty, which fails the valid `.Data.auto_merge_method` read as
    a phantom field.
    """
    schema = derive_producer_schema("get_pr_context")

    assert schema.top_level_keys is not None
    assert "auto_merge_method" in schema.top_level_keys


def test_detects_violation_through_a_captured_variable() -> None:
    """Binding via a shell variable must be checked, not just direct pipes."""
    body = (
        'LIVE=$(python3 "$SCRIPTS_DIR/check_pr_live_state.py" --pull-request "$PR")\n'
        "ACTION=$(echo \"$LIVE\" | jq -r '.action')\n"
    )

    violations = contract_violations(body)

    assert len(violations) == 1
    assert "check_pr_live_state.py" in violations[0]


def test_correct_reads_produce_no_violations() -> None:
    """Guard against a check that fails everything and looks strict."""
    body = (
        'LIVE=$(python3 "$SCRIPTS_DIR/check_pr_live_state.py" --pull-request "$PR")\n'
        "ACTION=$(echo \"$LIVE\" | jq -r '.Data.action')\n"
        'TIER=$(python3 "$SCRIPTS_DIR/test_pr_merge_ready.py" --pull-request "$PR" '
        "| jq -r '.Tier // \"UNKNOWN\"')\n"
    )

    assert contract_violations(body) == []


# Edge cases in the extraction helpers.


def test_logical_lines_joins_backslash_continuations() -> None:
    joined = logical_lines(
        'CTX=$(python3 "$SCRIPTS_DIR/get_pr_context.py" \\\n    --output-format json)\n'
    )

    assert len(joined) == 1
    assert joined[0][0] == 1
    assert "get_pr_context.py" in joined[0][1]
    assert "--output-format" in joined[0][1]


def test_logical_lines_reports_the_first_physical_line() -> None:
    joined = logical_lines("alpha\nbeta \\\n    gamma\ndelta\n")

    assert [lineno for lineno, _ in joined] == [1, 2, 4]


def test_commented_reads_are_ignored() -> None:
    """Prose in comments explains defects; it must not be read as code."""
    body = "# Reading .Data.Tier here would pin TIER at UNKNOWN | jq -r '.Data.Tier'\n"

    assert extract_field_reads(body) == []


def test_a_read_with_no_producer_in_scope_is_reported_unbound() -> None:
    assert extract_field_reads("VALUE=$(echo \"$OTHER\" | jq -r '.Data.action')\n") == [
        FieldRead(line=1, script=None, path=".Data.action")
    ]


def test_two_producers_on_one_line_each_bind_to_their_own_jq() -> None:
    """The second pipeline must not be checked against the first producer.

    Binding per line assigned every path to the first producer found, so the
    second read here was validated against `check_pr_live_state.py` and its
    real producer was never consulted. The coverage guard permits several jq
    commands per line, so nothing else objected. Same shape as the guard bugs
    before it: an aggregate over the line where the unit is the invocation.
    """
    line = (
        "A=$(python3 \"$SCRIPTS_DIR/check_pr_live_state.py\" | jq -r '.Data.action') && "
        "B=$(python3 \"$SCRIPTS_DIR/test_pr_merge_ready.py\" | jq -r '.Tier')\n"
    )

    assert extract_field_reads(line) == [
        FieldRead(line=1, script="check_pr_live_state", path=".Data.action"),
        FieldRead(line=1, script="test_pr_merge_ready", path=".Tier"),
    ]


def test_a_captured_variable_nearer_the_jq_wins_over_an_earlier_producer() -> None:
    """Nearest input wins, so a producer captured earlier does not steal the bind.

    `X=$(a.py); printf '%s' "$LIVE" | jq` feeds the jq from `$LIVE`. Taking the
    last producer seen on the line would bind it to `a.py` instead.
    """
    body = (
        'LIVE=$(python3 "$SCRIPTS_DIR/check_pr_live_state.py" --output-format json)\n'
        'X=$(python3 "$SCRIPTS_DIR/test_pr_merge_ready.py" --pull-request "$PR") '
        "&& Y=$(printf '%s' \"$LIVE\" | jq -r '.Data.action')\n"
    )

    assert extract_field_reads(body) == [
        FieldRead(line=2, script="check_pr_live_state", path=".Data.action")
    ]
