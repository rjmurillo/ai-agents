"""Tests for the shared FailureClassifier (REQ-048 TASK-002).

Each class pins the REQ-048 acceptance criterion in its name. The criteria
are quoted from the 2026-11-01 amendment.
"""

from __future__ import annotations

import time

import pytest

from scripts.failure_classifier import (
    DENIAL_MARKERS,
    FINGERPRINT_MAX_CHARS,
    FailureEvent,
    canonical_input,
    canonicalize_input_text,
    check_command,
    classify,
    failure_fingerprint,
    fingerprint_tool,
    is_check_command,
)

TEST = "pytest tests/a.py"


def ev(
    tool: str,
    ok: bool,
    error: str = "",
    cmd: str | None = None,
    target: str | None = None,
    check: bool | None = None,
):
    return FailureEvent.build(tool=tool, ok=ok, error=error, input=cmd, target=target, check=check)


class TestAC29Fingerprint:
    def test_six_steps(self) -> None:
        line = "  Error AT line 12 in commit abcdef1234   and   0xDEADBEEF\nsecond line"
        assert failure_fingerprint(" Bash ", line) == "bash|error at line N in commit H and H"

    def test_first_non_blank_line(self) -> None:
        assert failure_fingerprint("Bash", "\n \n boom \nlater") == "bash|boom"

    def test_words_and_numbers_are_not_hex(self) -> None:
        assert failure_fingerprint("Bash", "file defaced 12345678") == "bash|file defaced N"

    def test_line_is_capped(self) -> None:
        key = failure_fingerprint("Bash", "x" * 500)
        assert key is not None and len(key) == len("bash|") + FINGERPRINT_MAX_CHARS

    @pytest.mark.parametrize("error", ["", "   \n\t"])
    def test_no_error_text_has_no_fingerprint(self, error: str) -> None:
        assert failure_fingerprint("Bash", error) is None


class TestAC01AC02ErrorKinds:
    def test_errored_result_is_a_tool_error(self) -> None:
        assert classify([ev("Bash", False, "exit code 1")]).tool_error == 1

    @pytest.mark.parametrize("marker", DENIAL_MARKERS)
    def test_denial_marker_is_a_permission_denial_not_a_tool_error(self, marker: str) -> None:
        signals = classify([ev("Bash", False, f"Action {marker.upper()} by policy")])
        assert (signals.permission_denial, signals.tool_error) == (1, 0)

    def test_successes_count_neither(self) -> None:
        signals = classify([ev("Bash", True)] * 3)
        assert (signals.tool_error, signals.permission_denial) == (0, 0)


class TestAC03AC04FailedRetry:
    def test_same_key_and_fingerprint_counts_each_match_after_the_first(self) -> None:
        assert classify([ev("Bash", False, "boom", TEST)] * 3).failed_retry == 2

    def test_not_back_to_back_still_counts(self) -> None:
        events = [
            ev("Bash", False, "boom", TEST),
            ev("Read", True, cmd="x"),
            ev("Bash", False, "boom", TEST),
        ]
        assert classify(events).failed_retry == 1

    def test_success_for_the_key_between_resets(self) -> None:
        events = [
            ev("Bash", False, "boom", TEST),
            ev("Bash", True, cmd=TEST),
            ev("Bash", False, "boom", TEST),
        ]
        assert classify(events).failed_retry == 0

    def test_different_fingerprint_does_not_count(self) -> None:
        events = [ev("Bash", False, "boom", TEST), ev("Bash", False, "bang", TEST)]
        assert classify(events).failed_retry == 0

    def test_success_for_another_key_does_not_reset(self) -> None:
        events = [
            ev("Bash", False, "boom", TEST),
            ev("Bash", True, cmd="ls"),
            ev("Bash", False, "boom", TEST),
        ]
        assert classify(events).failed_retry == 1

    def test_keyless_failures_are_not_retries(self) -> None:
        # A retry is the same call again; without `input` there is no call to match.
        assert classify([ev("Bash", False, "boom")] * 3).failed_retry == 0


class TestAC30ProgressReset:
    def test_successful_ls_between_test_runs_resets_nothing(self) -> None:
        events = [
            ev("Bash", False, "boom", TEST),
            ev("Bash", True, cmd="ls"),
            ev("Bash", False, "boom", TEST),
        ]
        assert classify(events).repeat_totals() == {"bash|boom": 2}

    def test_fixed_make_build_keeps_the_npm_test_loop(self) -> None:
        events = [ev("Bash", False, "exit code 1", "npm test")] * 2
        events += [
            ev("Bash", False, "exit code 1", "make build"),
            ev("Bash", True, cmd="make build"),
        ]
        events += [ev("Bash", False, "exit code 1", "npm test")]
        signals = classify(events)
        assert signals.repeat_totals() == {"bash|exit code N": 3}
        assert list(signals.tally) == [("bash", "npm test")]

    def test_keyless_success_resets_nothing(self) -> None:
        events = [
            ev("Bash", False, "boom", TEST),
            ev("Bash", True),
            ev("Bash", False, "boom", TEST),
        ]
        assert classify(events).repeat_totals() == {"bash|boom": 2}

    def test_reset_also_removes_the_keys_churn_entries(self) -> None:
        events = [ev("Edit", True, target="a.py"), ev("Bash", False, "x", TEST)] * 2
        events += [ev("Bash", True, cmd=TEST)]
        assert classify(events).churn_totals() == {}


class TestAC31FailedEdits:
    def test_old_string_not_found_three_times(self) -> None:
        bad = ev("Edit", False, "old_string not found", "e1", "a.py")
        signals = classify([bad] * 3)
        assert signals.repeat_totals() == {"edit|old_string not found": 3}
        assert signals.failed_retry == 2


class TestAC32ChurnCycles:
    def test_cycles_sharing_a_fingerprint(self) -> None:
        events = [ev("Edit", True, target="./src//a.py"), ev("Bash", False, "x failed", TEST)] * 3
        signals = classify(events)
        assert signals.churn_totals() == {"src/a.py": {"bash|x failed": 3}}
        assert signals.churned_targets(3) == {"src/a.py": ("bash|x failed", 3)}

    def test_devins_case_reports_no_churn(self) -> None:
        cycle = [
            ev("Edit", True, target="a.py"),
            ev("Bash", True, cmd="pytest tests/a.py"),
            ev("Bash", False, "FAILED test_b", "pytest tests/b.py"),
        ]
        assert classify(cycle * 3).churn_totals() == {}

    def test_keyless_successful_check_ends_the_cycle(self) -> None:
        cycle = [
            ev("Edit", True, target="a.py"),
            ev("Bash", True, check=True),
            ev("Bash", False, "x", TEST),
        ]
        assert classify(cycle * 3).churn_totals() == {}

    def test_keyless_successful_read_leaves_the_cycle_open(self) -> None:
        cycle = [ev("Edit", True, target="a.py"), ev("Read", True), ev("Bash", False, "x", TEST)]
        assert classify(cycle * 3).churn_totals() == {"a.py": {"bash|x": 3}}

    def test_ls_and_git_status_leave_the_cycle_open(self) -> None:
        cycle = [
            ev("Edit", True, target="a.py"),
            ev("Bash", True, cmd="ls"),
            ev("Bash", True, cmd="git status"),
            ev("Bash", False, "x", TEST),
        ]
        signals = classify(cycle * 3)
        assert signals.churn_totals() == {"a.py": {"bash|x": 3}}
        assert signals.churned_targets(3) == {"a.py": ("bash|x", 3)}

    def test_failed_cat_leaves_the_cycle_open_and_a_passing_check_ends_it(self) -> None:
        events = [
            ev("Edit", True, target="a.py"),
            ev("Bash", False, "cat: missing.txt: No such file", "cat missing.txt"),
            ev("Bash", True, cmd="pytest tests/a.py"),
        ]
        assert classify(events).churn_totals() == {}

    def test_failed_cat_does_not_become_the_outcome(self) -> None:
        events = [
            ev("Edit", True, target="a.py"),
            ev("Bash", False, "cat: missing.txt: No such file", "cat missing.txt"),
            ev("Bash", False, "x", TEST),
        ]
        assert classify(events).churn_totals() == {"a.py": {"bash|x": 1}}

    def test_edit_twice_then_failing_check_is_one_cycle(self) -> None:
        events = [
            ev("Edit", True, target="a.py"),
            ev("Write", True, target="./a.py"),
            ev("Edit", True, target="a.py"),
            ev("Bash", False, "x", TEST),
        ]
        assert classify(events).churn_totals() == {"a.py": {"bash|x": 1}}

    def test_check_false_failure_closes_nothing(self) -> None:
        events = [
            ev("Edit", True, target="a.py"),
            ev("Bash", False, "x", TEST, check=False),
        ]
        assert classify(events).churn_totals() == {}

    def test_check_false_success_ends_nothing(self) -> None:
        events = [
            ev("Edit", True, target="a.py"),
            ev("Bash", True, cmd=TEST, check=False),
            ev("Bash", False, "x", TEST),
        ]
        assert classify(events).churn_totals() == {"a.py": {"bash|x": 1}}

    def test_non_shell_check_true_failure_closes_the_cycle(self) -> None:
        events = [
            ev("Edit", True, target="a.py"),
            ev("Task", False, "verifier failed", check=True),
        ]
        assert classify(events).churn_totals() == {"a.py": {"task|verifier failed": 1}}

    def test_failed_edit_closes_no_cycle(self) -> None:
        events = [ev("Edit", True, target="a.py"), ev("Edit", False, "nope", target="b.py")]
        events += [ev("Bash", False, "x", TEST)]
        assert classify(events).churn_totals() == {"a.py": {"bash|x": 1}}

    def test_edit_without_target_opens_none(self) -> None:
        assert classify([ev("Edit", True), ev("Bash", False, "x", TEST)] * 3).churn_totals() == {}

    def test_edit_leaves_other_pending_cycles(self) -> None:
        events = [
            ev("Edit", True, target="a.py"),
            ev("Write", True, target="b.py"),
            ev("Bash", False, "x", TEST),
        ]
        assert classify(events).churn_totals() == {"a.py": {"bash|x": 1}, "b.py": {"bash|x": 1}}

    def test_unfingerprinted_failure_does_not_close(self) -> None:
        events = [
            ev("Edit", True, target="a.py"),
            ev("Bash", False, ""),
            ev("Bash", False, "x", TEST),
        ]
        assert classify(events).churn_totals() == {"a.py": {"bash|x": 1}}

    def test_several_edits_before_one_failure_are_one_cycle(self) -> None:
        events = [ev("Edit", True, target="a.py")] * 3 + [ev("Bash", False, "x", TEST)]
        assert classify(events).churn_totals() == {"a.py": {"bash|x": 1}}


class TestAC37Unfingerprinted:
    def test_counted_as_tool_error_and_unfingerprinted_only(self) -> None:
        signals = classify([ev("Bash", False, "", TEST)] * 3)
        assert (signals.tool_error, signals.unfingerprinted) == (3, 3)
        assert (signals.failed_retry, signals.repeat_totals()) == (0, {})


class TestAC39InputCanonicalization:
    def test_json_document_gets_the_ac38_form(self) -> None:
        text = ' {"timeout": 5,  "command": "ls"} '
        assert canonicalize_input_text(text) == canonical_input({"command": "ls", "timeout": 5})

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("  pytest tests/a.py  ", "pytest tests/a.py"),
            ("{not json", "{not json"),
            ("[" * 100_000, "[" * 100_000),
        ],
    )
    def test_other_text_is_used_as_given_after_trimming(self, text: str, expected: str) -> None:
        assert canonicalize_input_text(text) == expected

    def test_json_null_text_canonicalizes_to_the_string_null(self) -> None:
        # Parsed JSON null is a key, not keyless: the text "null" is present.
        assert canonicalize_input_text(" null ") == "null"
        assert FailureEvent.build(tool="Bash", ok=False, input="null").progress_key == (
            "bash",
            "null",
        )

    @pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity", '{"a": NaN}', "[Infinity]"])
    def test_nan_and_infinity_are_plain_text(self, text: str) -> None:
        assert canonicalize_input_text(f"  {text} ") == text

    def test_keys_out_of_order_and_extra_whitespace_give_one_form(self) -> None:
        a = canonicalize_input_text('{"b":1,\n  "a": [1, 2]}')
        b = canonicalize_input_text('\t{ "a" : [1,2], "b" : 1 }  ')
        assert a == b == '{"a":[1,2],"b":1}'

    def test_non_ascii_is_escaped(self) -> None:
        assert canonicalize_input_text('{"a": "\u00e9é"}') == '{"a":"\\u00e9\\u00e9"}'
        assert canonical_input({"a": "é"}) == '{"a":"\\u00e9"}'

    def test_repeated_key_last_wins(self) -> None:
        assert canonicalize_input_text('{"a": 1, "a": 2}') == '{"a":2}'

    def test_non_json_command_string_is_trimmed_only(self) -> None:
        assert canonicalize_input_text("  pytest -k 'a b'  ") == "pytest -k 'a b'"

    def test_scalar_json_round_trips(self) -> None:
        assert canonicalize_input_text('"ls"') == '"ls"'


WRAPPERS = [
    "cd src &&",
    "FOO=bar",
    "A_1=",
    "uv run",
    "npx",
    "python -m",
    "python3 -m",
    "timeout 30",
]
CHECK_COMMANDS = [
    *("pytest", "py.test", "unittest", "tox", "nox", "jest", "vitest", "mocha"),
    *("make", "mvn", "gradle", "make build"),
    *(
        f"{pm} {run}{verb}"
        for pm in ("npm", "yarn", "pnpm")
        for run in ("", "run ")
        for verb in ("test", "build", "lint", "typecheck")
    ),
    *("cargo test", "cargo build", "cargo check", "cargo clippy"),
    *("go test ./...", "go build", "go vet ./..."),
    *("dotnet test", "dotnet build"),
    *("tsc", "eslint .", "ruff check", "mypy src", "pyright", "shellcheck a.sh"),
    *("markdownlint docs", "markdownlint-cli2 docs", "markdownlint-cli2-fix"),
    *("python tests/test_a.py", "python3 scripts/check_x.py --flag"),
    *("python scripts/validate_y.py", "python3 pre_pr.py", "python scripts/pre_pr.py"),
    *("python3 C:\\repo\\scripts\\validate_z.py",),
    *("lefthook run pre-commit", "pre-commit run --all-files"),
]
NOT_CHECK_COMMANDS = [
    "pytester",
    "pytest-fixture",
    "makefile",
    "npm install",
    "npm run start",
    "npm testing",
    "yarn add x",
    "cargo run",
    "go run main.go",
    "go get x",
    "dotnet run",
    "dotnet publish",
    "markdown",
    "python3 foo.py",
    "python3 scripts/foo.py",
    "python test_utils/run.py",
    "python3 check_dir/deploy.py",
    "python scripts/pre_pr.sh",
    "python scripts/precheck_x.py",
    "lefthook install",
    "pre-commit install",
    "ls",
    "git status",
    "cat missing.txt",
    "echo pytest",
    "",
]


class TestAC40Heads:
    @pytest.mark.parametrize("command", CHECK_COMMANDS)
    def test_check_heads_match(self, command: str) -> None:
        assert is_check_command(command) is True

    @pytest.mark.parametrize("command", NOT_CHECK_COMMANDS)
    def test_other_commands_do_not_match(self, command: str) -> None:
        assert is_check_command(command) is False

    def test_long_wrapper_run_stays_linear(self) -> None:
        # CWE-400: 200,000 assignment wrappers. Slicing per wrapper was
        # quadratic; the offset loop finishes well inside the bound.
        command = "a=1 " * 200_000 + "pytest"
        start = time.perf_counter()
        assert is_check_command(command) is True
        assert time.perf_counter() - start < 2.0

    @pytest.mark.parametrize("wrapper", WRAPPERS)
    def test_each_wrapper_is_stripped(self, wrapper: str) -> None:
        assert is_check_command(f"{wrapper} pytest tests/a.py") is True

    def test_wrappers_stack(self) -> None:
        assert is_check_command("cd src && FOO=1 timeout 5 uv run python -m pytest -q") is True

    def test_wrapper_alone_is_not_a_check(self) -> None:
        assert is_check_command("uv run ls") is False
        assert is_check_command("cd src && ls") is False

    def test_matching_is_case_insensitive(self) -> None:
        assert is_check_command("NPX ESLINT .") is True
        assert is_check_command("Uv Run PyTest") is True
        assert is_check_command("MARKDOWNLINT-CLI2 x") is True

    def test_leading_and_trailing_space_is_ignored(self) -> None:
        assert is_check_command("   pytest   ") is True

    def test_only_markdownlint_may_be_followed_by_a_dash(self) -> None:
        assert is_check_command("pytest-cov") is False
        assert is_check_command("ruff-fmt") is False


class TestAC40CommandExtraction:
    def test_json_object_string_command(self) -> None:
        assert check_command('{"command":"pytest tests/a.py","timeout":5}') == "pytest tests/a.py"

    def test_json_command_is_trimmed(self) -> None:
        assert check_command('{"command": "  ls  "}') == "ls"

    @pytest.mark.parametrize(
        "text",
        ['{"timeout":5}', '{"command":5}', '{"command":null}', '{"command":["pytest"]}'],
    )
    def test_missing_or_non_string_command_is_none(self, text: str) -> None:
        assert check_command(text) is None

    @pytest.mark.parametrize("text", ['"pytest"', "42", "[1]", "true", "null", '["pytest"]'])
    def test_non_object_parse_is_none(self, text: str) -> None:
        assert check_command(text) is None

    def test_plain_text_is_the_command(self) -> None:
        assert check_command("  pytest tests/a.py ") == "pytest tests/a.py"

    def test_nan_text_is_plain_text(self) -> None:
        assert check_command("NaN") == "NaN"

    def test_no_input_is_none(self) -> None:
        assert check_command(None) is None

    def test_extraction_does_not_change_the_progress_key(self) -> None:
        raw = '{"timeout": 5, "command": "pytest tests/a.py"}'
        event = FailureEvent.build(tool="Bash", ok=False, input=raw)
        assert event.is_check is True
        assert event.input == raw  # the classifier keeps the full input as given


class TestAC40IsCheck:
    @pytest.mark.parametrize("tool", ["bash", "Bash", " SHELL ", "PowerShell"])
    def test_shell_tool_with_check_head(self, tool: str) -> None:
        assert ev(tool, True, cmd="pytest").is_check is True

    @pytest.mark.parametrize("tool", ["Read", "Task", "grep", "WebFetch"])
    def test_non_shell_tool_is_not_a_derived_check(self, tool: str) -> None:
        assert ev(tool, True, cmd="pytest").is_check is False

    def test_shell_tool_without_input_is_not_a_check(self) -> None:
        assert ev("Bash", True).is_check is False

    def test_json_command_event_is_a_check(self) -> None:
        assert ev("Bash", True, cmd='{"command":"pytest tests/a.py"}').is_check is True

    def test_json_without_command_is_not_a_check(self) -> None:
        assert ev("Bash", True, cmd='{"description":"pytest"}').is_check is False
        assert ev("Bash", True, cmd='"pytest"').is_check is False
        assert ev("Bash", True, cmd="42").is_check is False

    def test_check_true_marks_a_non_shell_tool(self) -> None:
        assert ev("Task", True, check=True).is_check is True

    def test_check_false_beats_a_check_head(self) -> None:
        assert ev("Bash", True, cmd="pytest", check=False).is_check is False

    def test_check_true_beats_a_plain_command(self) -> None:
        assert ev("Bash", True, cmd="ls", check=True).is_check is True

    @pytest.mark.parametrize("tool", ["Edit", "write", "MultiEdit", "str_replace", "create"])
    def test_check_is_ignored_on_an_edit(self, tool: str) -> None:
        assert ev(tool, True, target="a.py", check=True).is_check is False
        assert ev(tool, True, target="a.py", cmd="pytest").is_check is False

    def test_marked_check_edit_still_opens_a_cycle(self) -> None:
        events = [ev("Edit", True, target="a.py", check=True), ev("Bash", False, "x", TEST)]
        assert classify(events).churn_totals() == {"a.py": {"bash|x": 1}}


def test_fingerprint_tool_reads_the_tool_part() -> None:
    fingerprint = failure_fingerprint("Bash", "boom|bang")
    assert fingerprint is not None
    assert fingerprint_tool(fingerprint) == "bash"
