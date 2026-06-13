"""Tests for pull_request event payload generation in test_workflow_locally.py.

Issue #2573: local ``gh act pull_request`` runs had no event payload, so PR
workflows saw empty ``github.event.pull_request`` fields (empty PR_NUMBER,
missing PR_TITLE). The script now generates a minimal payload.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import test_workflow_locally as twl  # noqa: E402


class TestBuildPullRequestEvent:
    def test_populates_pull_request_fields(self) -> None:
        payload = twl.build_pull_request_event(
            pr_number=2561,
            pr_title="fix: something",
            pr_body="body text",
            head_ref="feat/x",
            base_ref="main",
            repo_full_name="rjmurillo/ai-agents",
        )
        pr = payload["pull_request"]
        assert pr["number"] == 2561
        assert pr["title"] == "fix: something"
        assert pr["body"] == "body text"
        assert pr["head"]["ref"] == "feat/x"
        assert pr["base"]["ref"] == "main"
        # Top-level number is read by some actions via github.event.number.
        assert payload["number"] == 2561

    def test_populates_repository_fields(self) -> None:
        payload = twl.build_pull_request_event(
            pr_number=1,
            pr_title="t",
            pr_body="",
            head_ref="b",
            base_ref="main",
            repo_full_name="owner/name",
        )
        repo = payload["repository"]
        assert repo["full_name"] == "owner/name"
        assert repo["name"] == "name"
        assert repo["owner"]["login"] == "owner"


class TestWriteEventPayload:
    def test_writes_valid_json_file(self) -> None:
        payload = {"pull_request": {"number": 7}}
        path = twl._write_event_payload(payload)
        try:
            loaded = json.loads(Path(path).read_text(encoding="utf-8"))
            assert loaded["pull_request"]["number"] == 7
        finally:
            Path(path).unlink(missing_ok=True)


class TestParserEventArgs:
    def test_pull_request_is_default_event(self) -> None:
        args = twl.build_parser().parse_args(["--workflow", "pr-validation"])
        assert args.event == "pull_request"
        assert args.pr_number == 1
        assert args.eventpath == ""

    def test_eventpath_override_accepted(self) -> None:
        args = twl.build_parser().parse_args(
            ["--workflow", "w", "--eventpath", "/tmp/e.json", "--pr-number", "42"]
        )
        assert args.eventpath == "/tmp/e.json"
        assert args.pr_number == 42
