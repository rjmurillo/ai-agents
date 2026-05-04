"""Tests for invoke_session_log_field_guard.

Real session logs store markdownLintRun under
protocolCompliance.sessionEnd.markdownLintRun. They have no schemaVersion
field, and endingCommit may be absent for investigation-only sessions.

The guard validates:
- endingCommit is not the literal placeholder string "pending" (when present)
- markdownLintRun.Complete is true (when markdownLintRun is present)
- markdownLintRun.Evidence is non-placeholder, >= 20 chars (when present)
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOK_DIR))

import invoke_session_log_field_guard as guard  # noqa: E402


def _stdin(command: str) -> str:
    return json.dumps({"tool_input": {"command": command}})


def _diff(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout=stdout, stderr=""
    )


def _valid_log() -> dict:
    """Mirror the real session schema: markdownLintRun nested under protocolCompliance.sessionEnd."""
    return {
        "session": {"id": 1234, "date": "2026-05-04"},
        "protocolCompliance": {
            "sessionEnd": {
                "markdownLintRun": {
                    "level": "MUST",
                    "Complete": True,
                    "Evidence": (
                        "markdownlint-cli2 v0.21.0 ran clean on .agents/specs/**/*.md "
                        "prior to commit"
                    ),
                },
            },
        },
        "endingCommit": "abc123def456",
    }


@pytest.fixture(autouse=True)
def _no_consumer_repo_skip():
    with patch("push_guard_base.skip_if_consumer_repo", return_value=False):
        yield


@pytest.fixture
def push_command(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(_stdin("git push origin HEAD")))


def _write(tmp_path: Path, name: str, payload) -> str:
    sessions = tmp_path / ".agents" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    log_path = sessions / name
    if isinstance(payload, str):
        log_path.write_text(payload, encoding="utf-8")
    else:
        log_path.write_text(json.dumps(payload), encoding="utf-8")
    return f".agents/sessions/{name}"


def _run(diff_paths, tmp_path):
    diff_out = "".join(p + "\n" for p in diff_paths)
    with patch("push_guard_base.subprocess.run", return_value=_diff(diff_out)), \
         patch("push_guard_base.get_project_directory", return_value=str(tmp_path)), \
         patch("invoke_session_log_field_guard.get_project_directory", return_value=str(tmp_path)):
        return guard.main()


class TestAllValid:
    def test_all_fields_valid_returns_zero(self, push_command, tmp_path, capsys):
        rel = _write(tmp_path, "2026-05-04-session-01.json", _valid_log())
        rc = _run([rel], tmp_path)
        assert rc == 0
        assert "BLOCKED" not in capsys.readouterr().out

    def test_no_schema_version_field_is_tolerated(self, push_command, tmp_path):
        """Real schema has no schemaVersion. Absence must NOT block."""
        log = _valid_log()
        # Already absent in _valid_log; assert it stays out of the way.
        assert "schemaVersion" not in log
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 0

    def test_no_ending_commit_field_is_tolerated(self, push_command, tmp_path):
        """Investigation-only sessions may omit endingCommit. Absence must NOT block."""
        log = _valid_log()
        del log["endingCommit"]
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 0

    def test_missing_markdown_lint_run_blocks(self, push_command, tmp_path, capsys):
        """Canonical validator requires markdownLintRun; absence is a violation."""
        log = _valid_log()
        del log["protocolCompliance"]
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 2
        out = capsys.readouterr().out
        assert "markdownLintRun missing" in out


class TestEndingCommit:
    def test_ending_commit_pending_blocks(self, push_command, tmp_path, capsys):
        log = _valid_log()
        log["endingCommit"] = "pending"
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 2
        assert "endingCommit" in capsys.readouterr().out

    def test_ending_commit_real_sha_passes(self, push_command, tmp_path):
        log = _valid_log()
        log["endingCommit"] = "abc123def"
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 0


class TestMarkdownLintComplete:
    def test_markdown_lint_run_missing_blocks(self, push_command, tmp_path, capsys):
        """markdownLintRun is required by scripts/validate_session_json.py."""
        log = _valid_log()
        del log["protocolCompliance"]["sessionEnd"]["markdownLintRun"]
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 2
        assert "markdownLintRun missing" in capsys.readouterr().out

    def test_complete_false_blocks(self, push_command, tmp_path, capsys):
        log = _valid_log()
        log["protocolCompliance"]["sessionEnd"]["markdownLintRun"]["Complete"] = False
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 2
        assert "Complete" in capsys.readouterr().out

    def test_complete_lowercase_key_tolerated(self, push_command, tmp_path):
        """Schema permits lowercase complete; do not flag valid logs."""
        log = _valid_log()
        run = log["protocolCompliance"]["sessionEnd"]["markdownLintRun"]
        run.pop("Complete")
        run["complete"] = True
        run.pop("Evidence")
        run["evidence"] = (
            "markdownlint-cli2 v0.21.0 ran clean on changed files prior to commit"
        )
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 0


class TestMarkdownLintEvidence:
    def test_evidence_empty_blocks(self, push_command, tmp_path, capsys):
        log = _valid_log()
        log["protocolCompliance"]["sessionEnd"]["markdownLintRun"]["Evidence"] = ""
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 2
        assert "Evidence" in capsys.readouterr().out

    def test_evidence_short_blocks(self, push_command, tmp_path, capsys):
        log = _valid_log()
        log["protocolCompliance"]["sessionEnd"]["markdownLintRun"]["Evidence"] = "short"
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 2
        assert "Evidence" in capsys.readouterr().out

    def test_evidence_dot_blocks(self, push_command, tmp_path, capsys):
        log = _valid_log()
        log["protocolCompliance"]["sessionEnd"]["markdownLintRun"]["Evidence"] = "."
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 2
        assert "Evidence" in capsys.readouterr().out

    def test_evidence_pending_with_padding_blocks(self, push_command, tmp_path, capsys):
        log = _valid_log()
        log["protocolCompliance"]["sessionEnd"]["markdownLintRun"]["Evidence"] = (
            "                    pending                    "
        )
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 2
        assert "Evidence" in capsys.readouterr().out


class TestLegacyTopLevelFallback:
    """For older logs that stored markdownLintRun at the top level."""

    def test_legacy_top_level_complete_false_blocks(self, push_command, tmp_path, capsys):
        log = {"endingCommit": "abc123", "markdownLintRun": {"Complete": False}}
        rel = _write(tmp_path, "s.json", log)
        rc = _run([rel], tmp_path)
        assert rc == 2
        assert "Complete" in capsys.readouterr().out


class TestMalformedJson:
    def test_parse_error_blocks(self, push_command, tmp_path, capsys):
        rel = _write(tmp_path, "broken.json", "{not valid json")
        rc = _run([rel], tmp_path)
        assert rc == 2
        assert "JSON parse error" in capsys.readouterr().out


class TestEmptyChangeset:
    def test_no_session_files_returns_zero(self, push_command, tmp_path):
        rc = _run(["src/foo.py", "docs/readme.md"], tmp_path)
        assert rc == 0


class TestHooksJsonRegistration:
    def test_hooks_json_includes_session_log_field_guard(self):
        hooks_path = (
            Path(__file__).resolve().parents[2]
            / ".claude"
            / "hooks"
            / "hooks.json"
        )
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
        push_block = next(
            block
            for block in data["hooks"]["PreToolUse"]
            if block.get("matcher") == "Bash(git push*)"
        )
        commands = [hook.get("command", "") for hook in push_block["hooks"]]
        assert any("invoke_session_log_field_guard.py" in cmd for cmd in commands)
