"""CLI tests for avoiding-manufactured-work friction_report.py (candidates, scripts, check)."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import PROJECT_ROOT, import_skill_script

SCRIPT_REL = ".claude/skills/avoiding-manufactured-work/scripts/friction_report.py"
mod: Any = import_skill_script(SCRIPT_REL)

BODY_FILE_FAIL = "Exit code 2\nerror: --body-file rejected: path is inside a dot directory"
HEREDOC = "python3 - <<'PY'\nimport json\nprint(json.dumps({'a': 1, 'b': [1, 2, 3]}))\nPY"


def _use(use_id: str, name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    block = {"type": "tool_use", "id": use_id, "name": name, "input": tool_input}
    return {"type": "assistant", "isSidechain": False, "message": {"content": [block]}}


def _result(use_id: str, content: str, failed: bool) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": use_id, "content": content}
    if failed:
        block["is_error"] = True
    return {"type": "user", "isSidechain": False, "message": {"content": [block]}}


def _records(*steps: tuple[str, dict[str, Any], str, bool]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for number, (tool, tool_input, output, failed) in enumerate(steps):
        out.append(_use(f"t{number}", tool, tool_input))
        out.append(_result(f"t{number}", output, failed))
    return out


def _write(path: Path, records: list[dict[str, Any]], extra_lines: tuple[str, ...] = ()) -> Path:
    lines = [json.dumps(record) for record in records] + list(extra_lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _workaround_records(token: str = "") -> list[dict[str, Any]]:
    failed = f"post_reply.py --pr 5 --body-file .notes/r.md {token}".strip()
    return _records(
        ("Bash", {"command": failed}, BODY_FILE_FAIL, True),
        ("Bash", {"command": "post_reply.py --pr 5 --body 'text'"}, "posted", False),
    )


@pytest.fixture
def transcript(tmp_path: Path) -> Path:
    return _write(tmp_path / "session.jsonl", _workaround_records())


# ---------------------------------------------------------------------------
# candidates
# ---------------------------------------------------------------------------


class TestCandidates:
    def test_prints_one_block_per_candidate_with_placeholder(
        self, transcript: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert mod.main(["candidates", "--transcript", str(transcript)]) == 0
        out = capsys.readouterr().out
        assert out.count("Hit: ") == 1
        assert "Did instead: ran post_reply.py --pr 5 --body 'text'" in out
        assert f"Permanent fix: {mod.PERMANENT_FIX_PLACEHOLDER}" in out

    def test_printed_blocks_fail_the_validator_until_the_fix_is_written(
        self, transcript: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        mod.main(["candidates", "--transcript", str(transcript)])
        block = capsys.readouterr().out
        draft = tmp_path / "draft.txt"
        draft.write_text(block, encoding="utf-8")
        assert mod.main(["check", "--file", str(draft)]) == 1
        draft.write_text(block.replace(mod.PERMANENT_FIX_PLACEHOLDER, "allow dot dirs"), "utf-8")
        assert mod.main(["check", "--file", str(draft)]) == 0

    def test_no_candidates_exits_zero_with_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = _write(tmp_path / "s.jsonl", _records(("Bash", {"command": "ls"}, "a", False)))
        assert mod.main(["candidates", "--transcript", str(path)]) == 0
        assert "No workaround candidates: 1 tool calls, 0 marked failed." in capsys.readouterr().out

    def test_json_format_shape(self, transcript: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert mod.main(["candidates", "--transcript", str(transcript), "--format", "json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["events"] == 2
        assert payload["failed"] == 1
        assert len(payload["candidates"]) == 1
        assert set(payload["candidates"][0]) >= {"tool", "failed", "error", "succeeded", "kind"}

    def test_bad_json_lines_are_skipped(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = _write(tmp_path / "s.jsonl", _workaround_records(), ("{not json", "[1,", ""))
        assert mod.main(["candidates", "--transcript", str(path)]) == 0
        assert "Hit: " in capsys.readouterr().out

    def test_oversize_line_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        huge = json.dumps({"type": "system", "note": "x" * 5000})
        path = _write(tmp_path / "s.jsonl", _workaround_records(), (huge,))
        monkeypatch.setattr(mod, "MAX_LINE_CHARS", 3000)
        assert mod.main(["candidates", "--transcript", str(path)]) == 0
        assert "Hit: " in capsys.readouterr().out

    def test_secret_in_a_command_never_reaches_the_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        token = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
        path = _write(tmp_path / "s.jsonl", _workaround_records(f"--token {token}"))
        assert mod.main(["candidates", "--transcript", str(path)]) == 0
        assert token not in capsys.readouterr().out

    def test_missing_transcript_exits_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert mod.main(["candidates", "--transcript", "/nonexistent/none.jsonl"]) == 2
        captured = capsys.readouterr()
        assert "transcript not found" in captured.err
        assert captured.out == ""

    def test_directory_as_transcript_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert mod.main(["candidates", "--transcript", str(tmp_path)]) == 2
        assert "friction_report:" in capsys.readouterr().err

    def test_transcript_over_the_cap_exits_two(
        self, monkeypatch: pytest.MonkeyPatch, transcript: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(mod, "MAX_TRANSCRIPT_BYTES", 10)
        assert mod.main(["candidates", "--transcript", str(transcript)]) == 2
        assert "cap" in capsys.readouterr().err

    def test_read_error_after_open_exits_three(
        self, monkeypatch: pytest.MonkeyPatch, transcript: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def boom(_records: object) -> list[Any]:
            raise OSError(5, "Input/output error")

        monkeypatch.setattr(mod, "events_from_records", boom)
        assert mod.main(["candidates", "--transcript", str(transcript)]) == 3
        assert "read failed" in capsys.readouterr().err

    def test_bad_format_value_exits_two(self, transcript: Path) -> None:
        assert mod.main(["candidates", "--transcript", str(transcript), "--format", "xml"]) == 2


# ---------------------------------------------------------------------------
# transcript resolution
# ---------------------------------------------------------------------------


class TestUnmarkedLeads:
    def test_text_lists_calls_marked_success_that_state_a_failure(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        records = _records(
            (
                "Bash",
                {"command": "tail push.log"},
                "lefthook_runner: pre-push FAILED (exit 1)",
                False,
            )
        )
        path = _write(tmp_path / "s.jsonl", records)
        assert mod.main(["candidates", "--transcript", str(path)]) == 0
        out = capsys.readouterr().out
        assert "No workaround candidates: 1 tool calls, 0 marked failed." in out
        assert (
            "- tail push.log | output: lefthook_runner: pre-push FAILED (exit 1) (seen 1 times)"
            in out
        )

    def test_json_carries_the_unmarked_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        records = _records(("Bash", {"command": "tail push.log"}, "fatal: no remote", False))
        path = _write(tmp_path / "s.jsonl", records)
        assert mod.main(["candidates", "--transcript", str(path), "--format", "json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["unmarked"] == [
            {"command": "tail push.log", "line": "fatal: no remote", "count": 1, "index": 0}
        ]


class TestResolveTranscript:
    def test_slug_replaces_slashes_and_dots(self) -> None:
        assert mod.project_slug("/home/a/src/x.y/z") == "-home-a-src-x-y-z"

    def test_explicit_path_wins(self, tmp_path: Path) -> None:
        explicit = str(tmp_path / "x.jsonl")
        assert mod.resolve_transcript(explicit, "/any", {}) == Path(explicit)

    def test_newest_transcript_for_the_cwd_is_used(self, tmp_path: Path) -> None:
        cwd = "/work/proj.one"
        directory = tmp_path / "projects" / mod.project_slug(cwd)
        old = _write(directory / "old.jsonl", [])
        new = _write(directory / "new.jsonl", [])
        os.utime(old, (1_000, 1_000))
        os.utime(new, (2_000, 2_000))
        env = {"CLAUDE_CONFIG_DIR": str(tmp_path)}
        assert mod.resolve_transcript(None, cwd, env) == new

    def test_equal_mtime_breaks_ties_by_name(self, tmp_path: Path) -> None:
        cwd = "/work/proj"
        directory = tmp_path / "projects" / mod.project_slug(cwd)
        first = _write(directory / "a.jsonl", [])
        second = _write(directory / "b.jsonl", [])
        os.utime(first, (5_000, 5_000))
        os.utime(second, (5_000, 5_000))
        assert mod.resolve_transcript(None, cwd, {"CLAUDE_CONFIG_DIR": str(tmp_path)}) == second

    def test_default_run_reads_the_newest_transcript(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        workdir = tmp_path / "work"
        workdir.mkdir()
        monkeypatch.chdir(workdir)
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
        directory = tmp_path / "cfg" / "projects" / mod.project_slug(os.getcwd())
        _write(directory / "s.jsonl", _workaround_records())
        assert mod.main(["candidates"]) == 0
        assert "Hit: " in capsys.readouterr().out

    def test_no_transcript_for_the_cwd_exits_two(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        workdir = tmp_path / "work"
        workdir.mkdir()
        monkeypatch.chdir(workdir)
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty-cfg"))
        assert mod.main(["scripts"]) == 2
        assert "pass --transcript" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# scripts
# ---------------------------------------------------------------------------


class TestScripts:
    def test_lists_a_repeated_inline_program(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = _write(
            tmp_path / "s.jsonl",
            _records(
                ("Bash", {"command": HEREDOC}, "{}", False),
                ("Bash", {"command": HEREDOC}, "{}", False),
            ),
        )
        assert mod.main(["scripts", "--transcript", str(path)]) == 0
        out = capsys.readouterr().out
        assert "Inline programs seen 2 or more times:" in out
        assert "- python x2" in out

    def test_lists_scratch_scripts_with_reference_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scratch = "/r/.project-toolkit/scratch/probe.py"
        path = _write(
            tmp_path / "s.jsonl",
            _records(
                ("Write", {"file_path": scratch, "content": "x"}, "ok", False),
                ("Bash", {"command": f"python3 {scratch}"}, "ok", False),
            ),
        )
        assert mod.main(["scripts", "--transcript", str(path)]) == 0
        assert f"- {scratch}: written 1 times, named by 1 later commands" in capsys.readouterr().out

    def test_nothing_to_report_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = _write(tmp_path / "s.jsonl", _records(("Bash", {"command": "ls"}, "a", False)))
        assert mod.main(["scripts", "--transcript", str(path)]) == 0
        assert "No recurring inline programs and no scratch scripts" in capsys.readouterr().out

    def test_json_format_shape(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = _write(
            tmp_path / "s.jsonl",
            _records(
                ("Bash", {"command": HEREDOC}, "{}", False),
                ("Bash", {"command": HEREDOC}, "{}", False),
            ),
        )
        assert mod.main(["scripts", "--transcript", str(path), "--format", "json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["events"] == 2
        assert payload["inline"][0]["count"] == 2
        assert payload["scratch"] == []

    def test_missing_transcript_exits_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert mod.main(["scripts", "--transcript", "/nonexistent/none.jsonl"]) == 2
        assert "transcript not found" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

VALID = "Hit: a tool failed\nDid instead: ran another\nPermanent fix: change the tool\n"


class TestCheck:
    def test_valid_file_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "r.txt"
        path.write_text(VALID, encoding="utf-8")
        assert mod.main(["check", "--file", str(path)]) == 0
        assert capsys.readouterr().out.strip() == "friction block valid"

    def test_invalid_file_exits_one_and_lists_problems(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "r.txt"
        path.write_text("Hit: a tool failed\n", encoding="utf-8")
        assert mod.main(["check", "--file", str(path)]) == 1
        assert capsys.readouterr().out.startswith("line ")

    def test_stdin_input_is_read_when_no_file_is_given(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(VALID))
        assert mod.main(["check"]) == 0
        assert "friction block valid" in capsys.readouterr().out

    def test_terminal_stdin_without_a_file_exits_two(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        class Tty(io.StringIO):
            def isatty(self) -> bool:
                return True

        monkeypatch.setattr(sys, "stdin", Tty(""))
        assert mod.main(["check"]) == 2
        assert "stdin is a terminal" in capsys.readouterr().err

    def test_missing_file_exits_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert mod.main(["check", "--file", "/nonexistent/r.txt"]) == 2
        assert "file not found" in capsys.readouterr().err

    def test_input_over_the_cap_exits_two(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "r.txt"
        path.write_text(VALID, encoding="utf-8")
        monkeypatch.setattr(mod, "MAX_CHECK_CHARS", 10)
        assert mod.main(["check", "--file", str(path)]) == 2
        assert "cap" in capsys.readouterr().err

    def test_text_with_no_friction_lines_exits_zero(self, tmp_path: Path) -> None:
        path = tmp_path / "r.txt"
        path.write_text("Nothing to report.\n", encoding="utf-8")
        assert mod.main(["check", "--file", str(path)]) == 0


class TestUsage:
    def test_no_subcommand_exits_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert mod.main([]) == 2
        assert "friction_report:" in capsys.readouterr().err

    def test_unknown_subcommand_exits_two(self) -> None:
        assert mod.main(["frobnicate"]) == 2


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------


class TestBootstrapWithForeignPluginRoot:
    """A plugin-root variable that names another plugin must not break the import."""

    def _run(self, transcript: Path, root: Path | None) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if not k.endswith("PLUGIN_ROOT")}
        if root is not None:
            env["CLAUDE_PLUGIN_ROOT"] = str(root)
        script = PROJECT_ROOT / SCRIPT_REL
        return subprocess.run(
            [sys.executable, "-I", str(script), "candidates", "--transcript", str(transcript)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=transcript.parent,
            timeout=60,
            check=False,
        )

    def test_foreign_root_falls_back_to_the_plugin_lib(
        self, transcript: Path, tmp_path: Path
    ) -> None:
        foreign = tmp_path / "foreign-plugin"
        (foreign / "lib").mkdir(parents=True)
        done = self._run(transcript, foreign)
        assert done.returncode == 0, done.stderr
        assert "Hit: " in done.stdout

    def test_unset_root_runs_from_the_file_location(self, transcript: Path) -> None:
        done = self._run(transcript, None)
        assert done.returncode == 0, done.stderr
        assert "Hit: " in done.stdout
