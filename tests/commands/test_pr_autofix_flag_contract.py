"""Contract test between `pr-autofix.md`'s script calls and producer parsers.

Refs #5551. `test_pr_autofix_field_contract.py` closed the read side: a `jq`
path naming a field its producer never emits. This closes the write side, which
drifted the same way and is louder when it does. A field read that misses yields
`null` and lets the `//` default fire. A flag the producer never registered
makes `argparse` exit 2 with `unrecognized arguments`, so the call does no work
at all.

The instance was the auto-merge disarm gate (issue #3913, CWE-284). It passed
`--output-format json` to `set_pr_auto_merge.py`, which registers no such
option, so every armed non-T1 pull request took the gate's failure branch. The
branch skips the pull request, which is the safe half, and leaves auto-merge
armed on a pull request whose readiness the session never verified, which is the
outcome the gate exists to prevent. The log line said the opposite: it claimed
the pull request was skipped "to avoid unguarded merge" while the merge stayed
unguarded.
"""

from __future__ import annotations

import pytest

from tests.commands.pr_autofix_flag_parser import (
    COMMAND_PATH,
    MIRROR_PATH,
    derive_accepted_flags,
    extract_flag_uses,
    extract_invocations,
    flag_violations,
    script_reference_lines,
)


@pytest.fixture(scope="module")
def command_body() -> str:
    return COMMAND_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def mirror_body() -> str:
    return MIRROR_PATH.read_text(encoding="utf-8")


# Positive: the shipped command and its generated mirror pass every parser.


def test_source_command_has_no_flag_violations(command_body: str) -> None:
    violations = flag_violations(command_body)

    assert violations == [], "pr-autofix.md passes options its producers reject:\n" + "\n".join(
        violations
    )


def test_copilot_mirror_has_no_flag_violations(mirror_body: str) -> None:
    violations = flag_violations(mirror_body)

    assert violations == [], (
        "The shipped Copilot mirror passes options its producers reject:\n" + "\n".join(violations)
    )


def test_disarm_gate_passes_only_options_the_script_registers(command_body: str) -> None:
    """The reported defect, asserted on the shipped body rather than a fixture.

    A general violation sweep would also go green if the disarm gate were
    deleted. This names the gate's own invocation and the two options it is
    supposed to carry.
    """
    by_call: dict[int, set[str]] = {}
    for use in extract_flag_uses(command_body):
        if use.script == "set_pr_auto_merge":
            by_call.setdefault(use.line, set()).add(use.flag)
    disarm = [flags for flags in by_call.values() if "--disable" in flags]

    assert len(disarm) == 1, (
        "expected exactly one set_pr_auto_merge.py --disable call in pr-autofix.md; "
        f"found {len(disarm)}"
    )
    assert disarm[0] == {"--pull-request", "--disable"}, (
        "the disarm gate carries an option set_pr_auto_merge.py does not register; "
        f"found {sorted(disarm[0])}"
    )


# Negative: the defect this test exists to catch, and its neighbors.


def test_the_reported_regression_is_reported() -> None:
    body = (
        'if run_pr_mutation_if_live python3 "$SCRIPTS_DIR/set_pr_auto_merge.py" '
        '--pull-request "$PR" --disable --output-format json; then'
    )

    violations = flag_violations(body)

    assert len(violations) == 1
    assert "--output-format" in violations[0]
    assert "set_pr_auto_merge.py" in violations[0]
    assert "line 1" in violations[0]


def test_unregistered_flag_on_any_producer_is_reported() -> None:
    body = 'python3 "$SCRIPTS_DIR/get_pr_context.py" --pull-request "$PR" --nonesuch'

    violations = flag_violations(body)

    assert len(violations) == 1
    assert "--nonesuch" in violations[0]


def test_invocation_of_a_missing_script_is_reported() -> None:
    body = 'python3 "$SCRIPTS_DIR/no_such_producer.py" --pull-request "$PR"'

    violations = flag_violations(body)

    assert len(violations) == 1
    assert "no_such_producer.py" in violations[0]
    assert "not in" in violations[0]


def test_registered_flag_is_not_reported() -> None:
    body = 'python3 "$SCRIPTS_DIR/set_pr_auto_merge.py" --pull-request "$PR" --disable'

    assert flag_violations(body) == []


# Edge: the shapes the command body actually uses.


def test_backslash_continued_invocation_is_bound_to_its_script() -> None:
    body = (
        "if run_pr_mutation_if_live \\\n"
        '    python3 "$SCRIPTS_DIR/set_pr_auto_merge.py" \\\n'
        '    --pull-request "$PR" --disable --output-format json; then'
    )

    violations = flag_violations(body)

    assert len(violations) == 1, "a continued invocation must be joined before scanning"
    assert "line 1" in violations[0], "the finding must point at the first physical line"


def test_downstream_options_do_not_attach_to_the_upstream_producer() -> None:
    body = (
        'python3 "$SCRIPTS_DIR/get_pr_checks.py" --pull-request "$PR" | '
        'python3 "$SCRIPTS_DIR/get_pr_check_logs.py" --pull-request "$PR" --checks-input -'
    )

    uses = extract_flag_uses(body)

    assert {(u.script, u.flag) for u in uses} == {
        ("get_pr_checks", "--pull-request"),
        ("get_pr_check_logs", "--pull-request"),
        ("get_pr_check_logs", "--checks-input"),
    }
    assert flag_violations(body) == []


def test_jq_program_after_a_pipe_donates_no_options() -> None:
    body = (
        'python3 "$SCRIPTS_DIR/get_pr_context.py" --pull-request "$PR" | '
        "jq -r '.Data.auto_merge_method // \"--nonesuch\"'"
    )

    assert flag_violations(body) == []


def test_option_in_equals_form_is_extracted() -> None:
    body = 'python3 "$SCRIPTS_DIR/get_pr_context.py" --pull-request="$PR" --nonesuch=1'

    violations = flag_violations(body)

    assert len(violations) == 1
    assert "--nonesuch" in violations[0]


def test_interpreter_option_before_the_script_is_not_attributed_to_it() -> None:
    body = 'python3 -X dev --check-hash-based-pycs never "$SCRIPTS_DIR/get_pr_context.py" --field x'

    uses = extract_flag_uses(body)

    assert {u.flag for u in uses} == {"--field"}
    assert flag_violations(body) == []


def test_bare_double_dash_terminator_is_not_read_as_an_option() -> None:
    body = 'python3 "$SCRIPTS_DIR/get_pr_context.py" --pull-request "$PR" -- rest'

    assert extract_flag_uses(body) == [
        use for use in extract_flag_uses(body) if use.flag == "--pull-request"
    ]
    assert flag_violations(body) == []


def test_commented_invocation_is_skipped() -> None:
    body = '# python3 "$SCRIPTS_DIR/set_pr_auto_merge.py" --pull-request 1 --output-format json'

    assert extract_invocations(body) == []
    assert flag_violations(body) == []


def test_short_option_is_ignored() -> None:
    body = 'python3 "$SCRIPTS_DIR/get_pr_context.py" -q --field x'

    assert {u.flag for u in extract_flag_uses(body)} == {"--field"}


# Producer-side derivation.


def test_shared_helper_options_count_as_registered() -> None:
    """`--output-format` reaches nine producers through `add_output_format_arg`.

    Without following the helper call, the derivation would judge the option
    unregistered and report every legitimate use of it as a violation.
    """
    accepted = derive_accepted_flags("get_pr_context")

    assert accepted is not None
    assert "--output-format" in accepted


def test_mutually_exclusive_group_options_count_as_registered() -> None:
    accepted = derive_accepted_flags("set_pr_auto_merge")

    assert accepted is not None
    assert {"--enable", "--disable"} <= accepted
    assert "--output-format" not in accepted, (
        "set_pr_auto_merge.py grew an --output-format flag; the disarm gate can "
        "pass it again and this contract should be re-derived, not deleted"
    )


def test_missing_script_derives_no_flag_set() -> None:
    assert derive_accepted_flags("no_such_producer") is None


# Reach: the extractor must see every invocation the body contains.


@pytest.mark.parametrize("which", ["source", "mirror"])
def test_every_script_reference_line_yields_an_invocation(
    which: str, command_body: str, mirror_body: str
) -> None:
    """A guard against a silently narrowing extractor.

    `flag_violations` can only judge an invocation it found. One it never saw
    (an unusual quoting style, a separator the splitter does not know) leaves
    this suite green while checking nothing. `script_reference_lines` spots the
    two substrings `SCRIPTS_DIR` and `.py` without reusing the invocation regex,
    so it cannot go blind in lockstep with the thing it guards.
    """
    body = command_body if which == "source" else mirror_body
    seen = {lineno for lineno, _ in extract_invocations(body)}

    missed = [
        f"line {lineno}: {line.strip()[:120]}"
        for lineno, line in script_reference_lines(body)
        if lineno not in seen
    ]

    assert missed == [], "the invocation extractor did not reach every call:\n" + "\n".join(missed)
