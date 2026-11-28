"""Behavior tests for friction_report.py: candidate precision, shell-written
scratch scripts, and the script location. Each test runs the program on a
transcript and checks its output."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod: Any = import_skill_script(
    ".claude/skills/avoiding-manufactured-work/scripts/friction_report.py"
)

TOOL_FAIL = "Exit code 2\nerror: the input was rejected"
INLINE_FAIL = (
    "Exit code 1\nTraceback (most recent call last):\n"
    "  File \"<string>\", line 3, in <module>\nKeyError: 'Data'"
)
HEREDOC = "python3 - <<'PY'\nimport json\nprint(json.dumps({'a': 1, 'b': [1, 2, 3]}))\nPY"
Step = tuple[str, str, bool]


def _transcript(path: Path, steps: list[Step], cwd: str | None = None) -> Path:
    """A Claude Code transcript of Bash calls: (command, output, failed)."""
    lines: list[str] = []
    for number, (command, output, failed) in enumerate(steps):
        use: dict[str, Any] = {
            "type": "assistant",
            "isSidechain": False,
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": f"t{number}",
                        "name": "Bash",
                        "input": {"command": command},
                    }
                ]
            },
        }
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": f"t{number}",
            "content": output,
        }
        if failed:
            block["is_error"] = True
        result: dict[str, Any] = {
            "type": "user",
            "isSidechain": False,
            "message": {"content": [block]},
        }
        if cwd is not None:
            use["cwd"] = cwd
            result["cwd"] = cwd
        lines += [json.dumps(use), json.dumps(result)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run(
    capsys: pytest.CaptureFixture[str], command: str, transcript: Path, fmt: str = "text"
) -> str:
    assert mod.main([command, "--transcript", str(transcript), "--format", fmt]) == 0
    return capsys.readouterr().out


# ---------------------------------------------------------------------------
# candidates: precision
# ---------------------------------------------------------------------------


class TestCandidatePrecision:
    def test_shared_cd_prefix_alone_does_not_relate_two_calls(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        prefix = "cd /home/dev/worktrees/big-project/feature-branch-name && "
        steps = [
            (prefix + "frobnicate --all", TOOL_FAIL, True),
            (prefix + "quux --list", "ok", False),
        ]
        out = _run(capsys, "candidates", _transcript(tmp_path / "s.jsonl", steps))
        assert "Hit: " not in out

    def test_same_script_after_a_shared_cd_prefix_is_still_a_candidate(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        steps = [
            ("cd /a/b && post_reply.py --body-file x", TOOL_FAIL, True),
            ("cd /a/b && post_reply.py --body-file y", "posted", False),
        ]
        out = _run(capsys, "candidates", _transcript(tmp_path / "s.jsonl", steps))
        assert out.count("Hit: ") == 1
        assert "post_reply.py --body-file y" in out

    def test_a_later_call_that_only_views_output_is_not_a_workaround(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        steps = [
            ("python3 tools/build_report.py --out work/report.log --mode full", TOOL_FAIL, True),
            ("tail -n 20 work/report.log; grep -c full work/report.log", "0", False),
        ]
        out = _run(capsys, "candidates", _transcript(tmp_path / "s.jsonl", steps))
        assert "Hit: " not in out

    def test_a_crash_in_the_agents_own_inline_program_is_not_a_gap(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fetch = "python3 tools/get_item.py --item 7 | python3 -c "
        crash = "\"import json,sys\nd=json.load(sys.stdin)['Data']\nprint(d)\""
        fixed = '"import json,sys\nd=json.load(sys.stdin)\nprint(d)"'
        steps = [(fetch + crash, INLINE_FAIL, True), (fetch + fixed, "{}", False)]
        out = _run(capsys, "candidates", _transcript(tmp_path / "s.jsonl", steps))
        assert "Hit: " not in out

    def test_a_check_script_run_after_a_setup_command_is_a_verdict_not_a_gap(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        check = "export MODE=ci; python3 tools/check_layout.py --strict"
        steps = [
            (check + " > work/layout.log", "Exit code 1\nerror: 3 files break the layout", True),
            (check + " --only src > work/layout.log", "ok", False),
        ]
        out = _run(capsys, "candidates", _transcript(tmp_path / "s.jsonl", steps))
        assert "Hit: " not in out

    def test_a_shared_read_only_git_query_does_not_relate_two_calls(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        count = "git rev-list --count HEAD..origin/main"
        steps = [
            (f"git fetch -q origin main && {count} && git merge origin/main", TOOL_FAIL, True),
            (f"git log -1 --format=%h origin/main && {count}", "3", False),
        ]
        out = _run(capsys, "candidates", _transcript(tmp_path / "s.jsonl", steps))
        assert "Hit: " not in out

    def test_a_different_interpreter_for_the_same_script_is_a_candidate(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        steps = [
            ("python3 tools/assess.py --target . --format json", TOOL_FAIL, True),
            ("uv run python tools/assess.py --target . --format json", "{}", False),
        ]
        out = _run(capsys, "candidates", _transcript(tmp_path / "s.jsonl", steps))
        assert out.count("Hit: ") == 1


RUN = "python3 lib/ptk_run.py skills/demo/scripts/"
NOT_A_GAP: dict[str, tuple[str, str, str]] = {
    "verdict-line": (
        "python3 tools/why_blocked.py --item 7 --format human",
        "Exit code 1\n[FAIL] item 7 blocked: 2 open threads",
        "python3 tools/why_blocked.py --item 7",
    ),
    "launcher-hides-a-check": (
        RUN + "test_item_ready.py --item 7 > work/ready.json",
        "Exit code 1\nerror: item 7 is NOT ready",
        RUN + "test_item_ready.py --item 7 --wait > work/ready.json",
    ),
    "own-scratch-script-crash": (
        "D=/w/review/scratch && git show main:t.py > $D/t.py && python3 $D/probe.py",
        'Exit code 1\nTraceback (most recent call last):\n  File "/w/review/scratch/probe.py", '
        "line 9, in <module>\nValueError: bad",
        "D=/w/review/scratch && sed -i s/a/b/ $D/probe.py && python3 $D/probe.py",
    ),
    "file-the-command-just-wrote": (
        "cat > tests/ZzProbe.cs <<'EOF'\nclass A {}\nEOF\ndotnet build tests",
        "Exit code 1\ntests/ZzProbe.cs(15,13): error CS0103: no such name",
        "cat > tests/ZzProbe.cs <<'EOF'\nclass B {}\nEOF\ndotnet build tests",
    ),
    "missing-scratch-file": (
        "F=.project-toolkit/scratch/r.md && chmod 600 $F && tools/post.py --body-file $F",
        "Exit code 1\nchmod: cannot access '.project-toolkit/scratch/r.md': "
        "No such file or directory",
        "F=.project-toolkit/scratch/r.md && printf hi > $F && tools/post.py --body-file $F",
    ),
    "already-exists": (
        "git branch backup/x abc123 && git reset --keep origin/x && tools/verify.py",
        "Exit code 128\nfatal: a branch named 'backup/x' already exists",
        "git reset --keep origin/x && tools/verify.py",
    ),
    "safety-denial": (
        "tools/cleanup.py --purge work/",
        "Exit code 1\nerror: the removal safety check denied this command; it did not run",
        "tools/cleanup.py --purge work/old",
    ),
    "ordinary-output-with-no-error-line": (
        "tools/sync.py --branch x && git status -sb | head -n 5 && tools/verify.py",
        "Exit code 1\n## x...origin/x [ahead 3]\n"
        "6af7636 review: marker failed checks cleared\n M a.md",
        "tools/sync.py --branch x --force && tools/verify.py",
    ),
    "permission-request-aborted": (
        "tools/validate_marker.py --sha abc --dir work",
        "Exit code 1\nerror: Tool permission request aborted",
        "tools/validate_marker.py --sha abc --dir work/review",
    ),
    "commit-retry-after-content-change": (
        "git add src && git commit -q -m 'fix: x'",
        "Exit code 1\nerror: hook failed: index is stale",
        "git add src docs/index.md && git commit -q -m 'fix: x'",
    ),
}


class TestFailuresThatAreNotGaps:
    @pytest.mark.parametrize("case", sorted(NOT_A_GAP))
    def test_no_block_is_printed(
        self, case: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        failed, error, succeeded = NOT_A_GAP[case]
        steps = [(failed, error, True), (succeeded, "ok", False)]
        out = _run(capsys, "candidates", _transcript(tmp_path / "s.jsonl", steps))
        assert "Hit: " not in out

    def test_a_launched_script_rerun_with_other_input_is_still_a_candidate(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        steps = [
            (RUN + "post_note.py --item 7 --body-file /dev/stdin", TOOL_FAIL, True),
            (RUN + "post_note.py --item 7 --body-file work/note.md", "posted", False),
        ]
        out = _run(capsys, "candidates", _transcript(tmp_path / "s.jsonl", steps))
        assert out.count("Hit: ") == 1

    def test_a_lock_left_by_another_process_is_still_a_candidate(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        lock = "Exit code 128\nfatal: Unable to create '/r/.git/index.lock': File exists."
        steps = [
            ("git merge --no-edit origin/main > work/merge.log 2>&1", lock, True),
            ("tools/clear_lock.py && git merge --no-edit origin/main > work/merge.log", "", False),
        ]
        out = _run(capsys, "candidates", _transcript(tmp_path / "s.jsonl", steps))
        assert out.count("Hit: ") == 1


# ---------------------------------------------------------------------------
# scripts: scratch files written from the shell
# ---------------------------------------------------------------------------

SCRATCH = ".project-toolkit/scratch/foo.py"


class TestQuotedSecretsAreRedactedWhole:
    @pytest.mark.parametrize(
        "flag_value",
        [
            "--password 'tuna melt'",
            '--password "tuna melt"',
            "--token='tuna melt'",
            "--password 'tuna melt",
            '--password "tuna\\" melt"',
            "--password 'tuna'\\''s melt'",
            'TOKEN="tuna\\" melt"',
            "--password tuna\\ melt",
            '--password "authorization=tuna\\" melt"',
            'TOKEN="authorization: tuna\\" melt"',
        ],
        ids=[
            "single-quoted",
            "double-quoted",
            "equals-form",
            "unterminated-quote",
            "escaped-double-quote",
            "joined-single-quotes",
            "assignment-escaped-quote",
            "escaped-space",
            "flag-value-an-earlier-rule-matches",
            "assignment-value-an-earlier-rule-matches",
        ],
    )
    def test_a_quoted_credential_with_a_space_leaves_no_part_behind(
        self, flag_value: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        steps: list[Step] = [
            (f"tools/deploy.py --env x {flag_value}", TOOL_FAIL, True),
            (f"tools/deploy.py --env y {flag_value}", "deployed", False),
        ]
        out = _run(capsys, "candidates", _transcript(tmp_path / "t.jsonl", steps))
        assert "deploy.py" in out, "the pair must still be a candidate"
        assert "tuna" not in out and "melt" not in out

    def test_an_unquoted_credential_is_still_redacted_and_the_next_flag_kept(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        steps: list[Step] = [
            ("tools/deploy.py --password tunamelt --env x", TOOL_FAIL, True),
            ("tools/deploy.py --password tunamelt --env y", "deployed", False),
        ]
        out = _run(capsys, "candidates", _transcript(tmp_path / "t.jsonl", steps))
        assert "tunamelt" not in out and "--env" in out


class TestShellWrittenScratchScripts:
    @pytest.mark.parametrize(
        "command",
        [
            f"cat > {SCRATCH} <<'EOF'\nprint(1)\nEOF",
            f"echo 'print(1)' > {SCRATCH}",
            f"echo 'print(2)' >> {SCRATCH}",
            f"echo 'print(1)' | tee {SCRATCH}",
        ],
        ids=["heredoc", "truncate", "append", "tee"],
    )
    def test_each_shell_write_form_is_listed(
        self, command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        steps = [(command, "", False), (f"python3 {SCRATCH}", "1", False)]
        data = json.loads(_run(capsys, "scripts", _transcript(tmp_path / "s.jsonl", steps), "json"))
        assert [entry["path"] for entry in data["scratch"]] == [SCRATCH]
        assert data["scratch"][0]["references"] == 1

    @pytest.mark.parametrize(
        "command",
        [
            "echo 'print(1)' > tools/foo.py",
            "python3 tools/run.py > /dev/null 2>&1",
            f"python3 {SCRATCH} > /dev/null",
            "echo text | tee .project-toolkit/scratch/notes.md",
            "python3 tools/run.py 2>&1 | tee -a work/run.log",
        ],
        ids=["non-scratch", "dev-null", "runs-not-writes", "not-a-script", "tee-log"],
    )
    def test_other_shell_writes_are_not_listed(
        self, command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        steps = [(command, "", False)]
        data = json.loads(_run(capsys, "scripts", _transcript(tmp_path / "s.jsonl", steps), "json"))
        assert data["scratch"] == []


# ---------------------------------------------------------------------------
# scripts: the script location
# ---------------------------------------------------------------------------


def _repo(tmp_path: Path, *dirs: str) -> Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    for name in dirs:
        (root / name).mkdir()
    (root / "pkg" / "deep").mkdir(parents=True)
    return root


RECURRING: list[Step] = [(HEREDOC, "{}", False), (HEREDOC, "{}", False)]


class TestScriptLocation:
    def test_existing_scripts_directory_is_printed_beside_each_program(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path, "scripts")
        cwd = str(root / "pkg" / "deep")
        transcript = _transcript(tmp_path / "s.jsonl", RECURRING, cwd=cwd)
        text = _run(capsys, "scripts", transcript)
        program_lines = [line for line in text.splitlines() if line.startswith("- python")]
        assert len(program_lines) == 1
        assert str(root / "scripts") in program_lines[0]
        data = json.loads(_run(capsys, "scripts", transcript, "json"))
        assert data["script_location"] == str(root / "scripts")
        assert data["inline"][0]["script_location"] == str(root / "scripts")

    def test_git_worktree_file_marks_the_root(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = tmp_path / "wt"
        (root / "scripts").mkdir(parents=True)
        (root / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        transcript = _transcript(tmp_path / "s.jsonl", RECURRING, cwd=str(root))
        data = json.loads(_run(capsys, "scripts", transcript, "json"))
        assert data["script_location"] == str(root / "scripts")

    def test_missing_scripts_directory_prints_a_friction_block(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path, "tools")
        transcript = _transcript(tmp_path / "s.jsonl", RECURRING, cwd=str(root))
        text = _run(capsys, "scripts", transcript)
        assert f"Hit: no scripts/ directory under {root}" in text
        assert "Did instead: " in text
        assert "Permanent fix: <model writes this>" in text
        data = json.loads(_run(capsys, "scripts", transcript, "json"))
        assert data["script_location"] is None
        assert data["script_location_status"] == "missing"
        assert data["repository_root"] == str(root)

    def test_cwd_that_is_not_on_disk_claims_nothing_about_the_location(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        transcript = _transcript(tmp_path / "s.jsonl", RECURRING, cwd=str(tmp_path / "gone"))
        text = _run(capsys, "scripts", transcript)
        assert "Hit: " not in text
        data = json.loads(_run(capsys, "scripts", transcript, "json"))
        assert data["script_location_status"] == "unknown"

    def test_transcript_with_no_cwd_claims_nothing_about_the_location(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        transcript = _transcript(tmp_path / "s.jsonl", RECURRING)
        text = _run(capsys, "scripts", transcript)
        assert "Hit: " not in text
        assert json.loads(_run(capsys, "scripts", transcript, "json"))["script_location"] is None
