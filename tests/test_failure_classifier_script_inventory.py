"""Tests for the script inventory and the friction block check."""

from __future__ import annotations

import json

from scripts.failure_classifier import inline_script_inventory, validate_friction_block
from scripts.failure_classifier import workarounds as wa
from tests.test_failure_classifier_workarounds import bash, calls

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
