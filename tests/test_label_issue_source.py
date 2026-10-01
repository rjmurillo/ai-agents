"""Tests for .github/scripts/label_issue_source.py (epic #5698, AC-3)."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / ".github" / "scripts" / "label_issue_source.py"
_WORKFLOW = ROOT / ".github" / "workflows" / "label-issue-source.yml"
_PROVENANCE = ROOT / ".claude" / "skills" / "github" / "scripts" / "issue" / "issue_provenance.py"


def _load(path: Path, alias: str):
    spec = importlib.util.spec_from_file_location(alias, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def _import_script(name: str, alias: str):
    return _load(_SCRIPT.with_name(f"{name}.py"), alias)


mod = _import_script("label_issue_source", "label_issue_source_under_test")
OWNER = "rjmurillo"
MARKER = "<!-- source:human -->"
NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


def _iso(delta_minutes: float) -> str:
    return (NOW - timedelta(minutes=delta_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestClassify:
    def test_bot_login_is_agent(self):
        assert mod.classify("dependabot[bot]", "Bot", OWNER, "", False)[0] == mod.LABEL_AGENT

    def test_github_actions_login_is_agent(self):
        assert mod.classify("github-actions", "User", OWNER, "", False)[0] == mod.LABEL_AGENT

    def test_bot_user_type_is_agent_even_without_bot_suffix(self):
        assert mod.classify("app-name", "Bot", OWNER, MARKER, False)[0] == mod.LABEL_AGENT

    def test_bot_with_marker_stays_agent(self):
        assert mod.classify("x[bot]", "Bot", OWNER, MARKER, False)[0] == mod.LABEL_AGENT

    def test_other_person_is_human(self):
        assert mod.classify("alice", "User", OWNER, "", False)[0] == mod.LABEL_HUMAN

    def test_owner_without_marker_defaults_to_agent(self):
        label, reason = mod.classify(OWNER, "User", OWNER, "plain body", False)
        assert label == mod.LABEL_AGENT
        assert "defaults to agent" in reason

    def test_owner_match_is_case_insensitive(self):
        assert mod.classify("RJMurillo", "User", OWNER, "b", False)[0] == mod.LABEL_AGENT

    def test_owner_with_marker_outside_burst_is_human(self):
        assert mod.classify(OWNER, "User", OWNER, f"x\n{MARKER}", False)[0] == mod.LABEL_HUMAN

    def test_owner_with_marker_inside_burst_is_agent(self):
        label, reason = mod.classify(OWNER, "User", OWNER, MARKER, True)
        assert label == mod.LABEL_AGENT
        assert "burst" in reason

    def test_marker_must_be_the_last_non_blank_line(self):
        assert mod.has_human_marker(f"text\n{MARKER}\n\n  \n")
        assert not mod.has_human_marker(f"{MARKER}\ntext after")
        assert not mod.has_human_marker(f"quoted `{MARKER}` in prose")
        assert not mod.has_human_marker(f"```\n{MARKER}\n```")
        assert not mod.has_human_marker("")

    def test_missing_author_is_agent(self):
        assert mod.classify("", "", OWNER, MARKER, False)[0] == mod.LABEL_AGENT

    def test_marker_lookalike_is_not_a_marker(self):
        for body in ("source:human", "<!-- source:humans -->", "<!-- source:agent -->", None):
            assert mod.classify(OWNER, "User", OWNER, body, False)[0] == mod.LABEL_AGENT

    def test_marker_tolerates_spacing_and_case(self):
        assert mod.has_human_marker("<!--SOURCE:HUMAN-->")
        assert mod.has_human_marker("<!--   source:human\t-->")


class TestBurst:
    current = {"number": 10, "created_at": _iso(0)}

    def test_issue_inside_window_is_a_burst(self):
        assert mod.is_in_burst(self.current, [{"number": 9, "created_at": _iso(9)}])

    def test_issue_at_window_edge_is_a_burst(self):
        assert mod.is_in_burst(self.current, [{"number": 9, "created_at": _iso(10)}])

    def test_issue_outside_window_is_not_a_burst(self):
        assert not mod.is_in_burst(self.current, [{"number": 9, "created_at": _iso(11)}])

    def test_later_issue_is_not_a_burst(self):
        assert not mod.is_in_burst(self.current, [{"number": 11, "created_at": _iso(-1)}])

    def test_the_issue_itself_is_ignored(self):
        assert not mod.is_in_burst(self.current, [{"number": 10, "created_at": _iso(0)}])

    def test_pull_requests_are_ignored(self):
        other = {"number": 9, "created_at": _iso(1), "pull_request": {}}
        assert not mod.is_in_burst(self.current, [other])

    def test_empty_list_is_not_a_burst(self):
        assert not mod.is_in_burst(self.current, [])


class FakeGh:
    """Route gh api calls and record them."""

    def __init__(self, issue: dict, recent: list[dict] | None = None, fail: str = ""):
        self.issue = issue
        self.recent = recent or []
        self.fail = fail
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **_kwargs):
        self.calls.append(cmd)
        joined = " ".join(cmd)
        if self.fail and self.fail in joined:
            return subprocess.CompletedProcess(cmd, 1, "", "boom")
        if "creator=" in joined:
            assert "--paginate" in cmd and "--slurp" in cmd
            pages = [self.recent[:1], self.recent[1:]] if len(self.recent) > 1 else [self.recent]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(pages), "")
        if "-X" not in cmd:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(self.issue), "")
        return subprocess.CompletedProcess(cmd, 0, "{}", "")

    def mutations(self) -> list[str]:
        return [" ".join(c) for c in self.calls if "-X" in c]


def _issue(login=OWNER, body="", labels=(), user_type="User", number=10) -> dict:
    return {
        "number": number,
        "created_at": _iso(0),
        "body": body,
        "user": {"login": login, "type": user_type},
        "labels": [{"name": n} for n in labels],
    }


def _run(gh: FakeGh) -> tuple[str, str]:
    with patch("subprocess.run", side_effect=gh):
        return mod.label_issue(OWNER, "r", 10)


class TestLabelIssue:
    def test_owner_issue_without_marker_gets_agent_label(self):
        gh = FakeGh(_issue())
        assert _run(gh)[0] == mod.LABEL_AGENT
        assert any("labels[]=source:agent" in m for m in gh.mutations())

    def test_owner_marker_issue_outside_burst_gets_human_label(self):
        gh = FakeGh(_issue(body=MARKER), recent=[{"number": 3, "created_at": _iso(30)}])
        assert _run(gh)[0] == mod.LABEL_HUMAN

    def test_owner_marker_issue_inside_burst_is_forced_to_agent(self):
        gh = FakeGh(
            _issue(body=MARKER, labels=["source:human"]),
            recent=[{"number": 3, "created_at": _iso(2)}],
        )
        assert _run(gh)[0] == mod.LABEL_AGENT
        assert any("DELETE" in m and "source%3Ahuman" in m for m in gh.mutations())

    def test_burst_found_on_a_later_page_still_counts(self):
        recent = [
            {"number": 11, "created_at": _iso(-1)},
            {"number": 3, "created_at": _iso(2)},
        ]
        gh = FakeGh(_issue(body=MARKER), recent=recent)
        assert _run(gh)[0] == mod.LABEL_AGENT

    def test_burst_lookup_failure_fails_toward_agent(self, capsys):
        gh = FakeGh(_issue(body=MARKER), fail="creator=")
        assert _run(gh)[0] == mod.LABEL_AGENT
        assert "burst lookup failed" in capsys.readouterr().out

    def test_burst_lookup_is_skipped_without_a_marker(self):
        gh = FakeGh(_issue(body="no marker"))
        _run(gh)
        assert not any("creator=" in " ".join(c) for c in gh.calls)

    def test_other_person_gets_human_label_without_burst_lookup(self):
        gh = FakeGh(_issue(login="alice"))
        assert _run(gh)[0] == mod.LABEL_HUMAN
        assert not any("creator=" in " ".join(c) for c in gh.calls)

    def test_correct_existing_label_is_not_added_twice(self):
        gh = FakeGh(_issue(labels=["source:agent"]))
        _run(gh)
        assert not any("labels[]=" in m for m in gh.mutations())

    def test_conflicting_existing_label_is_removed(self):
        gh = FakeGh(_issue(labels=["source:human"]))
        _run(gh)
        assert any("DELETE" in m and "source%3Ahuman" in m for m in gh.mutations())

    def test_null_body_is_treated_as_empty(self):
        issue = _issue()
        issue["body"] = None
        assert _run(FakeGh(issue))[0] == mod.LABEL_AGENT


class TestEnsureLabel:
    def test_already_exists_is_not_an_error(self):
        def fake(cmd, **_kw):
            return subprocess.CompletedProcess(cmd, 1, "", "Validation Failed: already_exists")

        with patch("subprocess.run", side_effect=fake):
            mod.ensure_label("o", "r", mod.LABEL_AGENT)

    def test_already_exists_in_stdout_is_not_an_error(self):
        def fake(cmd, **_kw):
            return subprocess.CompletedProcess(
                cmd, 1, '{"errors":[{"code":"already_exists"}]}', "gh: Validation Failed (HTTP 422)"
            )

        with patch("subprocess.run", side_effect=fake):
            mod.ensure_label("o", "r", mod.LABEL_AGENT)

    def test_error_text_cannot_forge_a_workflow_command(self):
        def fake(cmd, **_kw):
            return subprocess.CompletedProcess(cmd, 1, "", "line\n::error::forged")

        with patch("subprocess.run", side_effect=fake), pytest.raises(mod.GhError) as caught:
            mod.fetch_issue("o", "r", 1)
        assert "\n" not in str(caught.value)
        assert "::" not in str(caught.value)

    def test_other_failure_raises(self):
        def fake(cmd, **_kw):
            return subprocess.CompletedProcess(cmd, 1, "", "HTTP 403")

        with patch("subprocess.run", side_effect=fake), pytest.raises(mod.GhError):
            mod.ensure_label("o", "r", mod.LABEL_AGENT)

    def test_gh_missing_raises_gherror(self):
        with patch("subprocess.run", side_effect=OSError("no gh")), pytest.raises(mod.GhError):
            mod.ensure_label("o", "r", mod.LABEL_AGENT)


class TestMain:
    def test_success_exits_0_and_reports(self, capsys):
        with patch("subprocess.run", side_effect=FakeGh(_issue())):
            rc = mod.main(["--issue", "10", "--owner", OWNER, "--repo", "r"])
        assert rc == 0
        assert "labeled source:agent" in capsys.readouterr().out

    def test_api_failure_exits_3(self, capsys):
        with patch("subprocess.run", side_effect=FakeGh(_issue(), fail="issues/10")):
            assert mod.main(["--issue", "10", "--owner", OWNER, "--repo", "r"]) == 3
        assert "Could not label issue #10" in capsys.readouterr().err

    def test_ghost_author_issue_is_labeled_agent(self):
        issue = _issue()
        issue["user"] = None
        assert _run(FakeGh(issue))[0] == mod.LABEL_AGENT

    def test_add_happens_before_delete(self):
        gh = FakeGh(_issue(labels=["source:human"]))
        _run(gh)
        kinds = [
            "POST" if "labels[]" in m else "DELETE"
            for m in gh.mutations()
            if "labels" in m and "/labels" in m and "repos/rjmurillo/r/labels " not in m
        ]
        assert kinds.index("POST") < kinds.index("DELETE")

    def test_bad_json_exits_3(self):
        def fake(cmd, **_kw):
            return subprocess.CompletedProcess(cmd, 0, "not json", "")

        with patch("subprocess.run", side_effect=fake):
            assert mod.main(["--issue", "10", "--owner", OWNER, "--repo", "r"]) == 3

    @pytest.mark.parametrize(
        "argv",
        [
            ["--issue", "0", "--owner", "o", "--repo", "r"],
            ["--issue", "1", "--owner", "o;rm", "--repo", "r"],
            ["--issue", "1", "--owner", "o", "--repo", "r/../x"],
            ["--issue", "1", "--owner", "o", "--repo", ".."],
            ["--issue", "1", "--owner=-o", "--repo", "r"],
            ["--issue", "1", "--owner", "o", "--repo", "r\n"],
            ["--issue", "1", "--owner", "", "--repo", "r"],
        ],
    )
    def test_invalid_arguments_exit_2_before_any_gh_call(self, argv):
        with patch("subprocess.run") as run:
            assert mod.main(argv) == 2
        run.assert_not_called()


class TestContracts:
    def test_marker_matches_the_one_new_issue_writes(self):
        provenance = _load(_PROVENANCE, "issue_provenance_marker_probe")
        assert mod.HUMAN_MARKER_PATTERN.search(provenance.HUMAN_MARKER)
        assert provenance.HUMAN_MARKER == MARKER

    def test_source_labels_match_the_script_gate(self):
        provenance = _load(_PROVENANCE, "issue_provenance_labels_probe")
        assert set(mod.SOURCE_LABELS) == set(provenance.SOURCE_LABELS)

    def test_workflow_triggers_only_on_issues_opened(self):
        wf = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
        assert wf[True] == {"issues": {"types": ["opened"]}}

    def test_workflow_uses_least_privilege_permissions(self):
        wf = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
        assert wf["permissions"] == {}
        assert wf["jobs"]["label"]["permissions"] == {"contents": "read", "issues": "write"}

    def test_workflow_pins_every_action_to_a_40_hex_sha(self):
        text = _WORKFLOW.read_text(encoding="utf-8")
        uses = re.findall(r"^\s*uses:\s*(\S+)", text, re.MULTILINE)
        assert uses
        assert all(re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", ref) for ref in uses)

    def test_workflow_never_expands_untrusted_issue_text(self):
        text = _WORKFLOW.read_text(encoding="utf-8")
        for field in ("issue.body", "issue.title", "issue.user", "comment.body"):
            assert f"github.event.{field}" not in text

    def test_workflow_run_step_is_a_single_script_call(self):
        wf = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
        runs = [s["run"] for s in wf["jobs"]["label"]["steps"] if "run" in s]
        assert len(runs) == 1
        assert runs[0].startswith("python3 .github/scripts/label_issue_source.py")
        assert "\n" not in runs[0].strip()


class TestSubprocessTimeout:
    def test_timeout_raises_gherror(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 30)):
            with pytest.raises(mod.GhError):
                mod.fetch_issue("o", "r", 1)
