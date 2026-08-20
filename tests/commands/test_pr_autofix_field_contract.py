"""Contract test between `pr-autofix.md`'s jq reads and its producer scripts.

Refs #5094. The `/pr-autofix` command body pipes producer scripts through `jq`
and branches on the result. When a read names a path the producer never emits,
`jq` yields `null`, the `//` default fires, and every downstream comparison
reads the fallback instead of the producer's value. Nothing fails, and which
way each branch then goes depends on how it compares the sentinel.

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

from pathlib import Path

import pytest

from tests.commands.pr_autofix_field_parser import (
    COMMAND_PATH,
    MIRROR_PATH,
    FieldRead,
    contract_violations,
    derive_producer_schema,
    extract_field_reads,
    logical_lines,
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


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_tier_read_targets_the_authoritative_flat_producer(doc: Path) -> None:
    """Pin the specific regression from issue #5094 and its repeat."""
    body = doc.read_text(encoding="utf-8")
    tier_reads = [r for r in extract_field_reads(body) if r.path.endswith("Tier")]

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


# Coverage guards for the checker itself live in
# `test_pr_autofix_coverage_guards.py`, split out when this file crossed the
# 500-line taste rule. This file checks the command; that one checks the check.


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
