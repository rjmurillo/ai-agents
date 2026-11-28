"""Tests for scripts.failure_classifier.workarounds: candidates, inventory, validator."""

from __future__ import annotations

import json
from typing import Any

import pytest

from scripts.failure_classifier import (
    KIND_ALTERNATIVE,
    KIND_FIX_THEN_RETRY,
    FailureEvent,
    events_from_records,
    inline_script_inventory,
    redact_text,
    unmarked_failures,
    validate_friction_block,
    workaround_candidates,
)
from scripts.failure_classifier import workarounds as wa
from scripts.redact_secrets import redact


def use(use_id: str, name: str, tool_input: Any, sidechain: bool = False) -> dict[str, Any]:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {
            "content": [{"type": "tool_use", "id": use_id, "name": name, "input": tool_input}]
        },
    }


def result(use_id: str, content: str, is_error: bool | None = None) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": use_id, "content": content}
    if is_error is not None:
        block["is_error"] = is_error
    return {"type": "user", "isSidechain": False, "message": {"content": [block]}}


def calls(*steps: tuple[str, dict[str, Any], str, bool]) -> list[FailureEvent]:
    """Events from (tool, input, output, failed) steps, in order."""
    records: list[dict[str, Any]] = []
    for number, (tool, tool_input, output, failed) in enumerate(steps):
        records.append(use(f"t{number}", tool, tool_input))
        records.append(result(f"t{number}", output, True if failed else None))
    return events_from_records(records)


def bash(command: str) -> dict[str, Any]:
    return {"command": command}


BODY_FILE_FAIL = "Exit code 2\nerror: --body-file rejected: path is inside a dot directory"
PERM_FAIL = "Exit code 1\nerror: refusing a group-writable file"


# ---------------------------------------------------------------------------
# workaround_candidates
# ---------------------------------------------------------------------------


class TestCandidatesPositive:
    def test_related_success_with_different_input_is_an_alternative(self) -> None:
        events = calls(
            (
                "Bash",
                bash("post_reply.py --pr 5 --body-file .notes/reply.md"),
                BODY_FILE_FAIL,
                True,
            ),
            ("Bash", bash("post_reply.py --pr 5 --body 'text'"), "posted", False),
        )
        found = workaround_candidates(events)
        assert len(found) == 1
        assert found[0].kind == KIND_ALTERNATIVE
        assert "--body-file" in found[0].failed
        assert "--body 'text'" in found[0].succeeded
        assert "dot directory" in found[0].error

    def test_fix_then_retry_names_the_intervening_call(self) -> None:
        events = calls(
            ("Bash", bash("edit_pr_body.py --file pr_body.md"), PERM_FAIL, True),
            ("Bash", bash("chmod 600 pr_body.md"), "", False),
            ("Bash", bash("edit_pr_body.py --file pr_body.md"), "updated", False),
        )
        found = workaround_candidates(events)
        assert len(found) == 1
        assert found[0].kind == KIND_FIX_THEN_RETRY
        assert found[0].succeeded == "chmod 600 pr_body.md"

    def test_alternative_survives_an_edit_before_the_identical_retry(self) -> None:
        events = calls(
            ("Bash", bash("post_reply.py --pr 5 --body-file .n/r.md"), BODY_FILE_FAIL, True),
            ("Bash", bash("post_reply.py --pr 5 --body 'text'"), "posted", False),
            ("Edit", {"file_path": "/repo/post_reply.py"}, "edited", False),
            ("Bash", bash("post_reply.py --pr 5 --body-file .n/r.md"), "posted", False),
        )
        found = workaround_candidates(events)
        assert [c.kind for c in found] == [KIND_ALTERNATIVE]
        assert "--body 'text'" in found[0].succeeded

    def test_same_failure_twice_collapses_with_a_count(self) -> None:
        step_fail = ("Bash", bash("post_reply.py --body-file .a/x.md"), BODY_FILE_FAIL, True)
        step_ok = ("Bash", bash("post_reply.py --body 'x'"), "ok", False)
        found = workaround_candidates(calls(step_fail, step_ok, step_fail, step_ok))
        assert len(found) == 1
        assert found[0].count == 2

    def test_candidates_keep_transcript_order(self) -> None:
        events = calls(
            ("Bash", bash("post_reply.py --body-file .a/x.md"), BODY_FILE_FAIL, True),
            ("Bash", bash("post_reply.py --body 'x'"), "ok", False),
            ("Bash", bash("edit_pr_body.py --file pr.md"), PERM_FAIL, True),
            ("Bash", bash("chmod 600 pr.md"), "", False),
            ("Bash", bash("edit_pr_body.py --file pr.md"), "updated", False),
        )
        found = workaround_candidates(events)
        assert [c.index for c in found] == sorted(c.index for c in found)
        assert len(found) == 2


class TestCandidatesNegative:
    def test_identical_retry_with_nothing_between_is_not_a_workaround(self) -> None:
        events = calls(
            ("Bash", bash("curl http://x"), "Exit code 7\nerror: connection refused", True),
            ("Bash", bash("curl http://x"), "ok", False),
        )
        assert workaround_candidates(events) == []

    def test_edit_between_failure_and_retry_is_not_a_workaround(self) -> None:
        events = calls(
            (
                "Bash",
                bash("pytest tests/test_app.py"),
                "Exit code 1\nerror: assertion failed",
                True,
            ),
            ("Edit", {"file_path": "/repo/app.py"}, "edited", False),
            ("Bash", bash("pytest tests/test_app.py"), "1 passed", False),
        )
        assert workaround_candidates(events) == []

    def test_user_rejection_is_not_friction(self) -> None:
        events = calls(
            ("Bash", bash("rm build.log"), "The user doesn't want to take this action", True),
            ("Bash", bash("rm build.log --force"), "ok", False),
        )
        assert workaround_candidates(events) == []

    def test_check_command_failure_is_not_friction(self) -> None:
        events = calls(
            ("Bash", bash("set -o pipefail; pytest tests/"), "Exit code 1\nerror: 3 failed", True),
            ("Bash", bash("pytest tests/test_one.py"), "ok", False),
        )
        assert workaround_candidates(events) == []

    def test_non_shell_tools_are_never_candidates(self) -> None:
        events = calls(
            ("Read", {"file_path": "/a/b.txt"}, "error: no such file", True),
            ("Read", {"file_path": "/a/c.txt"}, "content", False),
        )
        assert workaround_candidates(events) == []

    def test_failure_with_no_failure_words_is_dropped(self) -> None:
        events = calls(
            ("Bash", bash("grep -q needle hay.txt"), "Exit code 1", True),
            ("Bash", bash("grep -q needle other.txt"), "", False),
        )
        assert workaround_candidates(events) == []

    def test_success_marked_ok_is_never_a_failure(self) -> None:
        events = calls(
            ("Bash", bash("cat log.txt"), "error: old failure in the log", False),
            ("Bash", bash("cat log2.txt"), "fine", False),
        )
        assert workaround_candidates(events) == []

    def test_unrelated_success_is_not_a_workaround(self) -> None:
        events = calls(
            ("Bash", bash("post_reply.py --body-file .a/x.md"), BODY_FILE_FAIL, True),
            ("Bash", bash("git status"), "clean", False),
        )
        assert workaround_candidates(events) == []

    def test_running_own_scratch_script_is_not_friction(self) -> None:
        events = calls(
            (
                "Bash",
                bash("python3 .project-toolkit/scratch/probe.py"),
                "Exit code 1\nTraceback (most recent call last):\nValueError: x",
                True,
            ),
            ("Bash", bash("python3 .project-toolkit/scratch/probe.py --fix"), "ok", False),
        )
        assert workaround_candidates(events) == []

    def test_sidechain_calls_are_ignored(self) -> None:
        records = [
            use("s1", "Bash", bash("post_reply.py --body-file .a/x.md"), sidechain=True),
            {**result("s1", BODY_FILE_FAIL, True), "isSidechain": True},
            use("s2", "Bash", bash("post_reply.py --body 'x'"), sidechain=True),
            {**result("s2", "ok"), "isSidechain": True},
        ]
        assert workaround_candidates(events_from_records(records)) == []

    def test_empty_input_gives_no_candidates(self) -> None:
        assert workaround_candidates([]) == []


class TestCandidatesOutputSafety:
    def test_secret_in_command_is_redacted(self) -> None:
        token = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
        events = calls(
            (
                "Bash",
                bash(f"gh api user -H 'Authorization: Bearer {token}' --body-file .d/x"),
                "Exit code 1\nerror: --body-file rejected: dot directory",
                True,
            ),
            ("Bash", bash("gh api user --body 'x'"), "ok", False),
        )
        found = workaround_candidates(events)
        assert len(found) == 1
        assert token not in found[0].failed
        assert "Bearer" not in found[0].failed or "[redacted]" in found[0].failed

    def test_secret_in_error_text_is_redacted(self) -> None:
        events = calls(
            (
                "Bash",
                bash("deploy.py --body-file .d/x"),
                "Exit code 1\nerror: bad token password=hunter2hunter2 for --body-file",
                True,
            ),
            ("Bash", bash("deploy.py --body 'x'"), "ok", False),
        )
        found = workaround_candidates(events)
        assert found
        assert "hunter2hunter2" not in found[0].error

    def test_fields_respect_length_caps(self) -> None:
        long_command = "post_reply.py --body-file .a/x.md " + "word " * 500
        long_error = "Exit code 1\nerror: " + "boom " * 500 + "\nsecond line\nthird line"
        events = calls(
            ("Bash", bash(long_command), long_error, True),
            ("Bash", bash("post_reply.py --body-file .a/x.md --body 'x'"), "ok", False),
        )
        found = workaround_candidates(events)
        assert found
        assert len(found[0].failed) <= wa.COMMAND_MAX_CHARS
        assert len(found[0].error) <= wa.ERROR_MAX_CHARS
        assert len(found[0].succeeded) <= wa.COMMAND_MAX_CHARS * wa.FIX_MAX_CALLS + 20


# ---------------------------------------------------------------------------
# redact_text
# ---------------------------------------------------------------------------


SECRET_CORPUS = (
    "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
    "github_pat_" + "11ABCDEFG0abcdefghij_KLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuv",
    "AKIA" + "IOSFODNN7EXAMPLE",
    "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc",
    "xoxb-" + "123456789012-abcdefghijklmnop",
    "Authorization: Bearer abcdefghijklmnop.qrstuvwx.yz0123456789",
    "https://user:s3cretpass@example.com/path",
)

# Shapes only the lib redactor hides. scripts.redact_secrets does not flag a
# credential flag or a KEY=value assignment, so the lib is stricter on purpose:
# a workaround command often carries one, and the report must not print it.
LIB_ONLY_CORPUS = (
    "--password hunter2hunter2",
    "API_KEY=abcd1234efgh5678",
)


class TestRedactText:
    @pytest.mark.parametrize("secret", SECRET_CORPUS)
    def test_secret_shapes_are_removed(self, secret: str) -> None:
        out = redact_text(f"run it with {secret} now")
        assert "[redacted]" in out
        for fragment in ("A1b2C3d4E5f6", "IOSFODNN7", "4eC39Hq", "123456789012-abc", "s3cretpass"):
            assert fragment not in out
        assert "hunter2hunter2" not in out
        assert "abcd1234efgh5678" not in out

    def test_plain_text_is_unchanged(self) -> None:
        text = "pytest tests/test_app.py -q --maxfail=1"
        assert redact_text(text) == text

    def test_empty_text_is_unchanged(self) -> None:
        assert redact_text("") == ""

    def test_long_hex_run_is_removed(self) -> None:
        digest = "0123456789abcdef" * 4
        assert digest not in redact_text(f"sha {digest}")

    def test_oversize_input_is_bounded(self) -> None:
        out = redact_text("word " * 100_000)
        assert len(out) <= wa._REDACT_INPUT_MAX_CHARS

    @pytest.mark.parametrize("secret", LIB_ONLY_CORPUS)
    def test_lib_hides_credential_flags_and_assignments(self, secret: str) -> None:
        out = redact_text(f"cmd {secret} end")
        assert "[redacted]" in out
        assert "hunter2hunter2" not in out
        assert "abcd1234efgh5678" not in out

    @pytest.mark.parametrize("secret", SECRET_CORPUS)
    def test_lib_hides_everything_the_repo_redactor_hides(self, secret: str) -> None:
        """The lib redactor must be at least as strict as scripts.redact_secrets.

        The plugin lib cannot import scripts.redact_secrets in an install, so
        the lib keeps its own redactor. This test fails when the repo redactor
        hides a corpus string that the lib redactor leaves alone. The lib is
        stricter, never looser: LIB_ONLY_CORPUS lists the extra shapes.
        """
        sample = f"cmd {secret} end"
        assert redact(sample, include_hex=True).redacted
        assert redact_text(sample) != sample


# ---------------------------------------------------------------------------
# inline_script_inventory
# ---------------------------------------------------------------------------


HEREDOC = "python3 - <<'PY'\nimport json\nprint(json.dumps({'a': 1, 'b': [1, 2, 3]}))\nPY"


class TestInlineInventory:
    def test_repeated_heredoc_program_is_grouped(self) -> None:
        events = calls(
            ("Bash", bash(HEREDOC), "{}", False),
            ("Bash", bash("echo between"), "between", False),
            ("Bash", bash(HEREDOC), "{}", False),
        )
        inventory = inline_script_inventory(events)
        assert len(inventory.inline) == 1
        group = inventory.inline[0]
        assert group.count == 2
        assert group.interpreter == "python"
        assert len(group.sample) <= wa.SAMPLE_MAX_CHARS

    def test_digits_do_not_split_a_group(self) -> None:
        first = "python3 -c \"print('item 1001 of 2000 done')\""
        second = "python3 -c \"print('item 2002 of 3000 done')\""
        inventory = inline_script_inventory(
            calls(("Bash", bash(first), "x", False), ("Bash", bash(second), "x", False))
        )
        assert len(inventory.inline) == 1
        assert inventory.inline[0].count == 2

    def test_single_use_program_is_not_reported(self) -> None:
        inventory = inline_script_inventory(calls(("Bash", bash(HEREDOC), "{}", False)))
        assert inventory.inline == ()

    def test_different_programs_are_separate_and_unreported(self) -> None:
        other = HEREDOC.replace("'a': 1", "'z': 99, 'y': 98")
        inventory = inline_script_inventory(
            calls(("Bash", bash(HEREDOC), "{}", False), ("Bash", bash(other), "{}", False))
        )
        assert inventory.inline == ()

    def test_short_body_is_ignored(self) -> None:
        tiny = "python3 -c 'print(1)'"
        inventory = inline_script_inventory(
            calls(("Bash", bash(tiny), "1", False), ("Bash", bash(tiny), "1", False))
        )
        assert inventory.inline == ()

    def test_node_flag_program_is_grouped(self) -> None:
        command = 'node -e "console.log(JSON.stringify(process.argv.slice(2)))"'
        inventory = inline_script_inventory(
            calls(("Bash", bash(command), "[]", False), ("Bash", bash(command), "[]", False))
        )
        assert [g.interpreter for g in inventory.inline] == ["node"]

    def test_code_tool_programs_are_counted(self) -> None:
        code = "import pathlib\nprint(sorted(p.name for p in pathlib.Path('.').iterdir()))"
        payload = {"language": "python", "code": code}
        inventory = inline_script_inventory(
            calls(
                ("mcp__plugin_x__ctx_execute", payload, "[]", False),
                ("mcp__plugin_x__ctx_execute", payload, "[]", False),
            )
        )
        assert len(inventory.inline) == 1
        assert inventory.inline[0].count == 2

    def test_secret_in_program_is_redacted_in_sample(self) -> None:
        token = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
        command = f"python3 -c \"print('{token}', 'padding to pass the length floor')\""
        inventory = inline_script_inventory(
            calls(("Bash", bash(command), "x", False), ("Bash", bash(command), "x", False))
        )
        assert inventory.inline
        assert token not in inventory.inline[0].sample

    def test_scratch_script_write_counts_references(self) -> None:
        events = calls(
            (
                "Write",
                {"file_path": "/r/.project-toolkit/scratch/probe.py", "content": "x"},
                "ok",
                False,
            ),
            ("Bash", bash("python3 /r/.project-toolkit/scratch/probe.py"), "ok", False),
            ("Bash", bash("python3 /r/.project-toolkit/scratch/probe.py --again"), "ok", False),
        )
        inventory = inline_script_inventory(events)
        assert len(inventory.scratch) == 1
        scratch = inventory.scratch[0]
        assert scratch.path.endswith("probe.py")
        assert scratch.writes == 1
        assert scratch.references == 2

    def test_script_outside_scratch_is_not_listed(self) -> None:
        events = calls(("Write", {"file_path": "/r/scripts/tool.py", "content": "x"}, "ok", False))
        assert inline_script_inventory(events).scratch == ()

    def test_non_script_scratch_file_is_not_listed(self) -> None:
        events = calls(("Write", {"file_path": "/r/scratch/notes.md", "content": "x"}, "ok", False))
        assert inline_script_inventory(events).scratch == ()

    def test_failed_scratch_write_is_not_listed(self) -> None:
        events = calls(("Write", {"file_path": "/r/scratch/p.py", "content": "x"}, "denied", True))
        assert inline_script_inventory(events).scratch == ()

    def test_empty_input_gives_empty_inventory(self) -> None:
        inventory = inline_script_inventory([])
        assert inventory.inline == ()
        assert inventory.scratch == ()


# ---------------------------------------------------------------------------
# validate_friction_block
# ---------------------------------------------------------------------------


GOOD_BLOCK = (
    "Hit: post_reply.py rejected --body-file for a dot directory\n"
    "Did instead: passed --body with the text\n"
    "Permanent fix: allow dot directories under the repo root in post_reply.py"
)


class TestValidateFrictionBlock:
    def test_valid_block_has_no_problems(self) -> None:
        assert validate_friction_block(GOOD_BLOCK) == []

    def test_two_valid_blocks_have_no_problems(self) -> None:
        assert validate_friction_block(GOOD_BLOCK + "\n\n" + GOOD_BLOCK) == []

    def test_text_with_no_friction_lines_has_no_problems(self) -> None:
        assert validate_friction_block("Nothing to report.\n") == []

    def test_empty_text_has_no_problems(self) -> None:
        assert validate_friction_block("") == []

    def test_bullets_and_bold_labels_are_accepted(self) -> None:
        text = (
            "- **Hit:** a tool failed\n"
            "- **Did instead:** ran another\n"
            "- **Permanent fix:** change the tool"
        )
        assert validate_friction_block(text) == []

    def test_continuation_lines_are_accepted(self) -> None:
        text = "Hit: a tool failed\n  and said why\nDid instead: ran another\nPermanent fix: fix it"
        assert validate_friction_block(text) == []

    def test_hit_without_did_instead_is_reported(self) -> None:
        problems = validate_friction_block("Hit: x failed\nPermanent fix: fix x")
        assert problems
        assert all(p.startswith("line ") for p in problems)

    def test_hit_alone_is_reported(self) -> None:
        assert validate_friction_block("Hit: x failed")

    def test_hit_followed_by_next_hit_is_reported(self) -> None:
        assert validate_friction_block("Hit: a\nHit: b\nDid instead: c\nPermanent fix: d")

    def test_permanent_fix_before_did_instead_is_reported(self) -> None:
        assert validate_friction_block("Hit: a\nPermanent fix: d\nDid instead: c")

    def test_duplicate_did_instead_is_reported(self) -> None:
        assert validate_friction_block("Hit: a\nDid instead: b\nDid instead: c\nPermanent fix: d")

    def test_did_instead_with_no_hit_is_reported(self) -> None:
        assert validate_friction_block("Did instead: b\nPermanent fix: d")

    def test_permanent_fix_with_no_hit_is_reported(self) -> None:
        assert validate_friction_block("Permanent fix: d")

    def test_empty_value_is_reported(self) -> None:
        assert validate_friction_block("Hit: a\nDid instead: b\nPermanent fix:   ")

    def test_placeholder_value_is_reported(self) -> None:
        text = "Hit: a\nDid instead: b\nPermanent fix: <model writes this>"
        problems = validate_friction_block(text)
        assert problems
        assert "line 3" in problems[0]

    def test_angle_brackets_inside_real_text_are_allowed(self) -> None:
        text = "Hit: a\nDid instead: b\nPermanent fix: accept <dir>/<file> paths in the tool"
        assert validate_friction_block(text) == []

    def test_problems_are_json_serializable_text(self) -> None:
        problems = validate_friction_block("Hit: a")
        assert json.loads(json.dumps(problems)) == problems


# ---------------------------------------------------------------------------
# unmarked_failures
# ---------------------------------------------------------------------------

SLOT_REFUSAL = "pushing\nERROR: semgrep: no free heavy-stage slot after 420.001s\ndone"


class TestUnmarkedFailures:
    def test_success_call_with_a_failure_line_is_reported(self) -> None:
        events = calls(("Bash", bash("git push 2>&1 | tail -4"), SLOT_REFUSAL, False))
        found = unmarked_failures(events)
        assert len(found) == 1
        assert found[0].command == "git push 2>&1 | tail -4"
        assert found[0].line == "ERROR: semgrep: no free heavy-stage slot after 420.001s"
        assert found[0].count == 1

    @pytest.mark.parametrize(
        "output",
        [
            "Traceback (most recent call last):\n  File x",
            "lefthook_runner: pre-push FAILED (exit 1)",
            "semgrep-core exited with -11!",
            "fatal: not a git repository",
            "Refusing to run semgrep uncapped",
            "bash: jq: command not found",
            "ModuleNotFoundError: No module named 'yaml'",
        ],
    )
    def test_each_failure_shape_matches(self, output: str) -> None:
        assert len(unmarked_failures(calls(("Bash", bash("tail log"), output, False)))) == 1

    @pytest.mark.parametrize(
        "output",
        ["all 12 passed", "0 errors, 0 warnings", "usage: tool [-h]", "exited with 0", ""],
    )
    def test_clean_output_is_not_reported(self, output: str) -> None:
        assert unmarked_failures(calls(("Bash", bash("tail log"), output, False))) == []

    def test_call_marked_failed_is_left_to_the_candidates(self) -> None:
        events = calls(("Bash", bash("git push"), "Exit code 1\n" + SLOT_REFUSAL, True))
        assert unmarked_failures(events) == []

    def test_check_command_and_non_shell_tool_are_skipped(self) -> None:
        events = calls(
            ("Bash", bash("pytest tests/a.py"), "ERROR: file not found", False),
            ("Read", {"file_path": "log.txt"}, "ERROR: semgrep refused", False),
        )
        assert unmarked_failures(events) == []

    def test_same_line_collapses_with_a_count(self) -> None:
        events = calls(
            ("Bash", bash("tail a.log"), "ERROR: slot wait 420s", False),
            ("Bash", bash("tail b.log"), "ERROR: slot wait 431s", False),
        )
        found = unmarked_failures(events)
        assert [(item.command, item.count, item.index) for item in found] == [("tail a.log", 2, 0)]

    def test_output_is_redacted_and_capped(self) -> None:
        secret = "ghp_" + "a1B2" * 9
        events = calls(
            (
                "Bash",
                bash(f"curl -H 'Authorization: Bearer {secret}' x"),
                "ERROR: " + "y" * 900,
                False,
            )
        )
        found = unmarked_failures(events)[0]
        assert secret not in found.command
        assert len(found.line) <= wa.ERROR_MAX_CHARS

    def test_entry_count_is_capped(self) -> None:
        steps = [
            ("Bash", bash(f"tail {n}.log"), f"ERROR: stage {chr(97 + n)} broke", False)
            for n in range(wa.UNMARKED_MAX + 3)
        ]
        assert len(unmarked_failures(calls(*steps))) == wa.UNMARKED_MAX
