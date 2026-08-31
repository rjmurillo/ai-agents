"""Coverage guards for the `pr-autofix` jq contract checker.

Refs #5094. These do not check the command; they check the checker. Each one
exists because a previous version of the gate could pass while seeing nothing:
a read the extractor never parsed, a producer whose schema would not derive, a
producer consumed without an envelope pin, or a nested path the field check
cannot inspect. A gate that cannot fail is worse than no gate, because it also
tells the next reader the question was asked.

Every guard runs over both shipped documents. Running them on the source alone
leaves the mirror's blindness unguarded: `contract_violations` and
`test_mirror_reads_match_source_reads` both compare only reads the extractor
already found, so an invocation neither side parses contributes to neither
check and stays invisible.

Split out of `test_pr_autofix_field_contract.py` when it crossed the 500-line
taste rule, on the seam already there: that file checks the command, this one
checks the check.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.commands.pr_autofix_field_parser import (
    COMMAND_PATH,
    MIRROR_PATH,
    contract_violations,
    derive_producer_schema,
    extract_field_reads,
    jq_invocation_count,
    jq_invocation_lines,
    jq_paths,
    jq_programs,
    pathless_jq_programs,
    unparsed_jq_invocations,
)

# Coverage: the extractor must not go blind and silently pass.
#
# All three guards run over both shipped documents. Running them on the source
# alone leaves the mirror's blindness unguarded: `contract_violations` and
# `test_mirror_reads_match_source_reads` both compare only reads the extractor
# already found, so an invocation neither side parses contributes to neither
# check and stays invisible. Copilot caught that on PR #5176, on the guard
# below; the other two took the same source-only fixture, so all three are
# parameterized rather than only the one reported.


# A bracketed token in argument position, the shape `[--is-bot]` had. Anchored on a
# preceding space so a shell array subscript or a jq array literal is unaffected, and
# on a leading dash so a markdown link label inside a fence is not read as an argument.
_BRACKETED_ARGUMENT = re.compile(r"\s\[-{1,2}[A-Za-z][A-Za-z0-9-]*\]")


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_every_read_binds_to_a_producer(doc: Path) -> None:
    """An unbound read is unchecked, so treat it as a failure, not a skip."""
    body = doc.read_text(encoding="utf-8")
    unbound = [r for r in extract_field_reads(body) if r.script is None]

    assert unbound == [], (
        f"{doc.name}: reads that bind to no producer are unchecked:\n"
        + "\n".join(f"line {r.line}: `{r.path}`" for r in unbound)
    )


@pytest.mark.parametrize(
    ("program", "expected"),
    [
        ('.Data | has("author_is_bot.nonesuch")', "author_is_bot.nonesuch"),
        ('(.Data) | has("nonesuch")', "nonesuch"),
    ],
)
def test_literal_has_keys_are_validated_exactly(program: str, expected: str) -> None:
    """Dots and parentheses must not weaken literal-key checks."""
    body = (
        'VALUE=$(python3 "$SCRIPTS_DIR/get_pr_context.py" '
        f"--pull-request \"$PR\" | jq -r '{program}')\n"
    )

    violations = contract_violations(body)

    assert len(violations) == 1
    assert f"emits no `{expected}` field" in violations[0]


def test_dynamic_has_key_fails_closed() -> None:
    """A key the parser cannot name must not pass unchecked."""
    body = (
        'VALUE=$(python3 "$SCRIPTS_DIR/get_pr_context.py" '
        "--pull-request \"$PR\" | jq -r '.Data | has($field)')\n"
    )

    violations = contract_violations(body)

    assert len(violations) == 1
    assert "uses a `has` form the extractor cannot validate" in violations[0]


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_extractor_reaches_every_jq_invocation(doc: Path) -> None:
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
    body = doc.read_text(encoding="utf-8")
    unparsed = [
        (lineno, jq_invocation_count(line), len(jq_programs(line)), line.strip())
        for lineno, line in jq_invocation_lines(body)
        if unparsed_jq_invocations(line)
    ]

    assert unparsed == [], f"{doc.name}: jq invocations the extractor never parsed:\n" + "\n".join(
        f"line {lineno}: {count} invocation(s), {parsed} program(s) parsed: {line[:100]}"
        for lineno, count, parsed, line in unparsed
    )

    pathless = [
        (lineno, program)
        for lineno, line in jq_invocation_lines(body)
        for program in pathless_jq_programs(line)
    ]

    assert pathless == [], (
        f"{doc.name}: jq programs the extractor read no path from:\n"
        + "\n".join(f"line {lineno}: {program[:100]}" for lineno, program in pathless)
    )


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_every_consumed_producer_has_derivable_keys(doc: Path) -> None:
    """The field check must not stand down on a producer the command reads.

    `_field_violation` returns None when `top_level_keys` is None, which is
    correct for "cannot tell" but is a fail-open path: a producer refactor that
    broke derivation would silently stop field-checking every read against it,
    and every other test would stay green. Pin derivability for the producers
    actually in use so that regression fails here.
    """
    body = doc.read_text(encoding="utf-8")
    scripts = {r.script for r in extract_field_reads(body) if r.script}
    undecidable = sorted(s for s in scripts if derive_producer_schema(s).top_level_keys is None)

    assert undecidable == [], (
        f"{doc.name}: field checking silently stands down for these producers:\n"
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


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_extractor_finds_reads_for_every_producer_style(doc: Path) -> None:
    """Both envelope styles must be represented, or the check proves little."""
    scripts = {r.script for r in extract_field_reads(doc.read_text(encoding="utf-8"))}
    schemas = [derive_producer_schema(s) for s in scripts if s]

    assert any(s.wraps_in_data for s in schemas), "No Data-wrapped producer covered."
    assert any(not s.wraps_in_data for s in schemas), "No flat producer covered."


_ENVELOPE_CLASSIFICATION: dict[str, bool] = {
    "test_pr_merge_ready": False,
    "test_pr_merged": False,
    "check_pr_live_state": True,
    "check_pr_round_cap": True,
    "get_pr_context": True,
    "pr_autofix_lease": True,
}


@pytest.mark.parametrize(("script", "expected_wrap"), sorted(_ENVELOPE_CLASSIFICATION.items()))
def test_producer_envelope_classification(script: str, expected_wrap: bool) -> None:
    assert derive_producer_schema(script).wraps_in_data is expected_wrap


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_every_consumed_producer_has_a_pinned_envelope(doc: Path) -> None:
    """The converse of the pins above: nothing may be consumed without one.

    Without this, the pins cover a hardcoded list rather than the producers the
    command actually reads, so a newly consumed script gets no wrap pin and the
    suite stays green. Same shape as the guard bugs before it: the set that is
    checked and the set that matters were allowed to drift apart.

    Over both docs, so a producer reachable only from the mirror cannot evade
    the pin. Spec validation named this and the producer-style guard after the
    first three were parameterized; the tier-read pin above was source-only too
    and nobody had named it.
    """
    consumed = {r.script for r in extract_field_reads(doc.read_text(encoding="utf-8")) if r.script}
    unpinned = sorted(consumed - _ENVELOPE_CLASSIFICATION.keys())

    assert unpinned == [], (
        "These producers are read by the command but have no envelope pin, so a "
        "misclassification would go unnoticed:\n"
        + "\n".join(f"  {script}.py" for script in unpinned)
    )


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_no_read_needs_nested_field_checking(doc: Path) -> None:
    """`_field_violation` checks one segment, so no read may have two.

    The field check reduces a read to `path.lstrip(".").split(".")[0]` after the
    envelope, so a rename below that segment would pass unnoticed. That was
    filed as a known limit and left as prose, which is worse than it sounds: a
    limit nobody can trip over is a limit nobody maintains.

    Measured rather than assumed, and stated as the property rather than the
    measurement: every read in the command body is single-segment, so the limit
    is latent, not active. The one nested path anyone cites,
    `Data.superseded_by_base.fully_superseded`, appears only in a comment and is
    not a read at all; the extractor excludes comment lines by design, so it was
    never in scope. An earlier draft of the known limit presented it as a live
    example, and two spec-validation runs reasoned from that error. An earlier
    draft of this docstring then pinned "all 16 reads" and a line number, which
    is the count-where-a-property-belongs mistake this PR has now made in five
    places; CodeRabbit caught this one.

    This guard turns the limit fail-closed. Adding a nested read fails here and
    says what to do, instead of silently landing under a check that cannot see
    it.
    """
    body = doc.read_text(encoding="utf-8")
    nested = [
        r
        for r in extract_field_reads(body)
        if len(r.path.lstrip(".").split(".")) > (2 if r.path.startswith(".Data.") else 1)
    ]

    assert nested == [], (
        f"{doc.name}: these reads have a segment past the one the field check "
        "inspects, so their nested key is unverified. Extend `_field_violation` "
        "to derive nested literal shapes before adding a read like this:\n"
        + "\n".join(f"  line {r.line}: `{r.path}`" for r in nested)
    )


def test_flat_producer_keys_include_the_fields_the_command_reads() -> None:
    schema = derive_producer_schema("test_pr_merge_ready")

    assert schema.top_level_keys is not None
    assert "Tier" in schema.top_level_keys, "Tier is set via `result['Tier'] = ...`."
    assert "CanMerge" in schema.top_level_keys


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_the_checklist_orders_the_disarm_before_the_round_cap(doc: Path) -> None:
    """The checklist must not describe the gate order the reorder replaced.

    Sibling of the guard below, and it exists because that guard's subject had
    a twin nobody looked at. Copilot found the disarm item describing a
    condition the gate no longer had, and it got a guard. Two other lines
    described the *ordering* the gate no longer had, and got neither: the block
    comment and this checklist item both said the breaker runs "immediately
    after the tier is known", which stopped being true when the disarm gate
    moved ahead of it to close CWE-284. The checklist also listed the two items
    in the old order. The spec validator caught it on a later run.

    That matters more than a stale comment usually would, because this
    checklist is the artifact agents report compliance against. An agent
    reading it in order would disarm after escalating, which is the CWE-284
    sequence this PR exists to remove, and would report itself compliant.

    Position rather than wording, because ordering is the property that
    drifted. A guard that tried to parse "after the disarm gate" out of English
    would fail for the wrong reasons.
    """
    body = doc.read_text(encoding="utf-8")
    lines = body.splitlines()

    disarm = [i for i, line in enumerate(lines) if line.startswith("- [ ] Auto-merge disarm ran")]
    round_cap = [
        i for i, line in enumerate(lines) if line.startswith("- [ ] Round-cap circuit breaker ran")
    ]

    assert len(disarm) == 1, f"expected exactly one disarm checklist item, found {len(disarm)}"
    assert len(round_cap) == 1, (
        f"expected exactly one round-cap checklist item, found {len(round_cap)}"
    )
    assert disarm[0] < round_cap[0], (
        f"{doc.name} lists the round-cap breaker before the auto-merge disarm, which is the "
        "order the gates had before the CWE-284 reorder; an agent working the checklist in "
        "order would hand an escalated PR to a human with auto-merge still armed"
    )


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_the_verification_checklist_covers_the_completeness_half(doc: Path) -> None:
    """Prose that agents report compliance against must track the gate.

    The disarm checklist item said "any non-T1 PR" while the gate had started
    disarming a T1 whose evidence was incomplete. An agent reading the checklist
    as its definition of done could report compliance without ever verifying the
    new disarm, which is prose drifting from behavior in the one direction that
    matters: the artifact used as evidence.

    Copilot caught it. This guard is here so the next widening of the gate
    cannot leave the checklist behind quietly. It is deliberately weak, since it
    asks only that the checklist name the field the gate reads; a guard that
    tried to parse the condition out of English would fail for the wrong
    reasons.
    """
    body = doc.read_text(encoding="utf-8")
    block = body[body.index("# tier-dispatch:start") : body.index("# tier-dispatch:end")]
    # Asserted, not skipped. The first version called `pytest.skip` when the
    # gate stopped reading a completeness field, which turns deleting the gate
    # into a green run and needs a tracking issue under testing.md MUST NOT 2.
    # Worse, it is the guard's own subject: a test that disappears exactly when
    # the thing it protects is removed protects nothing. This PR requires the
    # gate, so its absence is a failure.
    assert "PAGES_COMPLETE" in block, (
        "the dispatch block no longer reads a completeness field, so the earned-T1 "
        "exemption this PR added is gone; if that removal is intended, delete this "
        "guard and the checklist clause together"
    )

    checklist = [
        line
        for line in body.splitlines()
        if line.startswith("- [ ]") and "Auto-merge disarm" in line
    ]

    assert checklist, "the auto-merge disarm checklist item vanished"
    assert any("fetched_pages_complete" in line for line in checklist), (
        "the dispatch block disarms on incomplete completeness evidence, but the "
        "verification checklist still describes the disarm as non-T1 only, so an "
        "agent can report compliance without checking the newer condition"
    )


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_the_scripts_reference_block_carries_no_optional_argument_placeholder(doc: Path) -> None:
    """A runnable fence must not carry a token argparse rejects.

    The `## Scripts` block is a bash fence whose every line runs as written once
    `{pr}` is substituted, and it exists to serve the CI-triage fix pattern. It
    shipped `test_pr_merge_ready.py --pull-request {pr} [--is-bot]`, so an agent
    following the block literally handed argparse an extra positional and got
    `unrecognized arguments`. Issue #5208 named this invocation site alongside
    the tier-dispatch one; only the dispatch site was made executable.

    The guard is on the shape rather than on the wording: a bracketed token in a
    command line inside a bash fence is a placeholder wherever it appears, and
    the fix for one is the fix for all of them, which is to derive the value.
    """
    body = doc.read_text(encoding="utf-8")
    fences = body.split("```")
    placeholders = [
        line.strip()
        for index, fence in enumerate(fences)
        if index % 2 == 1 and fence.startswith("bash")
        for line in fence.splitlines()
        if not line.lstrip().startswith("#") and _BRACKETED_ARGUMENT.search(line)
    ]

    assert placeholders == [], (
        f"{doc.name} carries a bracketed optional-argument placeholder on a runnable line: "
        f"{placeholders}. argparse reads it as a positional and the command exits on "
        "`unrecognized arguments`. Derive the flag instead, as the tier-dispatch block does."
    )
