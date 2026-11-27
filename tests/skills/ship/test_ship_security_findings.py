"""Negative tests for the five security findings fixed in the ship scripts.

Each class names one finding from the 2026-11-25 security review of the ship
driver draft. The sixth finding (the paths validator ran checkout code) is
covered by test_ship_base_validator.py, after the owner's option A ruling.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import approved_ado_build, invoke, symlink_or_skip, values

GITHUB = "https://github.com/rjmurillo/ai-agents.git"
ADO = "https://dev.azure.com/contoso/p/_git/r"
TITLE = "feat(ship): add the driver"
MERGE = "m" * 40


def _open_pr(fakes, *, number=9, author="me", draft=None, me="me"):
    payload = {
        "number": number,
        "state": "OPEN",
        "author": {"login": author},
        "url": "u",
        "baseRefName": "main",
    }
    if draft is not None:
        payload["isDraft"] = draft
    fakes.rule("gh", ["pr", "view"], {"stdout": json.dumps(payload)})
    fakes.rule("gh", ["api", "user"], {"stdout": f"{me}\n"})


def _head(fakes, pr, *, branch=None, sha=None):
    repo = Path.cwd()
    fakes.rule(
        "gh",
        ["pr", "view", str(pr)],
        {
            "stdout": json.dumps(
                {
                    "headRefName": branch or git(repo, "branch", "--show-current"),
                    "headRefOid": sha or git(repo, "rev-parse", "HEAD"),
                    "url": f"https://github.com/o/r/pull/{pr}",
                }
            )
        },
    )


def _pushed(tmp_path: Path) -> bool:
    """Return whether the bare remote received the feature branch."""
    done = subprocess.run(
        [
            "git",
            f"--git-dir={tmp_path / 'remote.git'}",
            "rev-parse",
            "--verify",
            "--quiet",
            "refs/heads/feat/ship-change",
        ],
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


class TestSymlinkedScratch:
    """Finding: a symlinked scratch directory moved the confinement anchor."""

    @pytest.mark.parametrize("component", [".project-toolkit", ".project-toolkit/scratch"])
    def test_symlinked_component_rejects_the_body_file(self, scripts, tmp_path, component):
        common = scripts[0]
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside"
        (outside / "scratch").mkdir(parents=True)
        (outside / "scratch" / "pr-body.md").write_text("secret", encoding="utf-8")
        (outside / "pr-body.md").write_text("secret", encoding="utf-8")
        if component == ".project-toolkit":
            symlink_or_skip(root / ".project-toolkit", outside)
        else:
            (root / ".project-toolkit").mkdir()
            symlink_or_skip(root / ".project-toolkit" / "scratch", outside)
        target = root / ".project-toolkit" / "scratch" / "pr-body.md"
        assert target.exists(), "the link really reaches the outside file"
        assert common.scratch_dir(root) is None
        assert common.confine_body_file(str(target), root) is None

    def test_detail_file_refuses_a_symlinked_scratch(self, scripts, tmp_path):
        common = scripts[0]
        root = tmp_path / "root"
        (root / ".project-toolkit").mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        symlink_or_skip(root / ".project-toolkit" / "scratch", outside)
        assert common.write_detail_file(["a"], root) == "unavailable"
        assert list(outside.iterdir()) == []

    def test_scratch_that_is_a_file_is_refused(self, scripts, tmp_path):
        common = scripts[0]
        (tmp_path / ".project-toolkit").mkdir()
        (tmp_path / ".project-toolkit" / "scratch").write_text("x", encoding="utf-8")
        assert common.scratch_dir(tmp_path, create=True) is None
        assert common.write_private(tmp_path, "p", ".md", "x") is None

    def test_missing_root_is_refused(self, scripts, tmp_path):
        assert scripts[0].scratch_dir(tmp_path / "absent") is None

    def test_publish_stops_on_a_symlinked_scratch(
        self, make_repo, fakes, scripts, capsys, tmp_path
    ):
        repo = make_repo(GITHUB)
        fakes.no_pr_github()
        fakes.marker(0)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "pr-body.md").write_text("## Summary\n\nok\n", encoding="utf-8")
        (repo / ".project-toolkit").mkdir()
        symlink_or_skip(repo / ".project-toolkit" / "scratch", outside)
        code, lines = invoke(
            scripts[3],
            [
                "publish",
                "--paths-checked-by-hand",
                "--title",
                TITLE,
                "--body-file",
                ".project-toolkit/scratch/pr-body.md",
            ],
            capsys,
        )
        assert code == 2
        assert lines[-1].startswith("STOP: bad-body-file")
        assert not _pushed(tmp_path)

    def test_publish_cannot_snapshot_into_an_unsafe_scratch(
        self, make_repo, fakes, scripts, capsys, body_file, monkeypatch
    ):
        repo = make_repo(GITHUB)
        fakes.no_pr_github()
        fakes.marker(0)
        body = body_file(repo)
        monkeypatch.setattr(scripts[0], "write_private", lambda *args, **kwargs: None)
        code, lines = invoke(
            scripts[3],
            ["publish", "--paths-checked-by-hand", "--title", TITLE, "--body-file", str(body)],
            capsys,
        )
        assert code == 2
        assert lines[-1].startswith("STOP: bad-body-file could not write the body snapshot")


class TestDraftOnExistingPr:
    """Finding: --draft skipped review before a push to an existing non-draft PR."""

    @pytest.mark.parametrize("draft", [False, None])
    def test_publish_draft_on_non_draft_pr_still_needs_review(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path, draft
    ):
        repo = make_repo(GITHUB)
        _open_pr(fakes, draft=draft)
        fakes.marker(1)
        code, lines = invoke(
            scripts[3],
            [
                "publish",
                "--paths-checked-by-hand",
                "--title",
                TITLE,
                "--body-file",
                str(body_file(repo)),
                "--draft",
            ],
            capsys,
        )
        assert code == 1
        assert lines[-1].startswith("STOP: head-not-reviewed draft exemption refused: PR 9")
        assert fakes.calls("validate_review_marker")
        assert not _pushed(tmp_path)

    def test_publish_draft_on_verified_draft_pr_skips_review(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path
    ):
        repo = make_repo(GITHUB)
        _open_pr(fakes, draft=True)
        fakes.marker(1)
        code, lines = invoke(
            scripts[3],
            [
                "publish",
                "--paths-checked-by-hand",
                "--title",
                TITLE,
                "--body-file",
                str(body_file(repo)),
                "--draft",
            ],
            capsys,
        )
        assert code == 0, lines
        assert "CHECK: reviewed=SKIPPED draft" in lines
        assert not fakes.calls("validate_review_marker")
        assert values(lines, "PR")[0].endswith("existing")

    def test_preflight_draft_on_non_draft_pr_runs_the_validator(
        self, make_repo, fakes, scripts, capsys
    ):
        make_repo(GITHUB)
        _open_pr(fakes, draft=False)
        fakes.marker(0)
        code, lines = invoke(scripts[2], ["--check", "reviewed", "--draft"], capsys)
        assert code == 0
        assert values(lines, "CHECK") == [
            "reviewed=PASS axes=analyst,qa; draft exemption refused: PR 9 is not a verified draft"
        ]

    def test_detect_reports_the_draft_state(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        _open_pr(fakes, draft=True)
        _code, lines = invoke(scripts[1], [], capsys)
        assert values(lines, "PR_DRAFT") == ["true"]


class TestRequiredAxes:
    """Finding: draft and contributor modes ignored explicitly required axes."""

    def test_draft_with_required_axis_fails(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        fakes.no_pr_github()
        code, lines = invoke(
            scripts[2], ["--check", "reviewed", "--draft", "--require-axis", "security"], capsys
        )
        assert code == 1
        assert values(lines, "CHECK") == [
            "reviewed=FAIL required axes cannot be verified without a review marker: security"
        ]

    def test_contributor_with_required_axis_fails(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        _open_pr(fakes, author="alice", me="bob")
        code, lines = invoke(
            scripts[2], ["--check", "reviewed", "--require-axis", "security"], capsys
        )
        assert code == 1
        assert values(lines, "CHECK")[0].startswith("reviewed=FAIL required axes")
        assert not fakes.calls("validate_review_marker")

    def test_publish_draft_with_required_axis_stops(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path
    ):
        repo = make_repo(GITHUB)
        fakes.no_pr_github()
        code, lines = invoke(
            scripts[3],
            [
                "publish",
                "--paths-checked-by-hand",
                "--title",
                TITLE,
                "--body-file",
                str(body_file(repo)),
                "--draft",
                "--require-axis",
                "security",
            ],
            capsys,
        )
        assert code == 1
        assert lines[-1].startswith("STOP: head-not-reviewed required axes")
        assert not _pushed(tmp_path)


class TestCiBinding:
    """Finding: the CI verdict was not tied to the PR and the exact head SHA."""

    def test_github_stale_pr_head_defers_before_publish(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        _open_pr(fakes)
        _head(fakes, 9, sha="0" * 40)
        code, lines = invoke(scripts[2], ["--check", "pipeline"], capsys)
        assert code == 0
        assert values(lines, "CHECK")[0].startswith("pipeline=DEFERRED pr=9 head 000000000000")
        assert not fakes.calls("get_pr_checks")
        assert lines[-1] == "NEXT: publish-then-discharge"

    def test_github_stale_pr_head_waits_after_publish(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        fakes.no_pr_github()
        _head(fakes, 41, sha="0" * 40)
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--pr", "41"], capsys)
        assert code == 0
        assert "host has not seen the push yet" in values(lines, "CHECK")[0]
        assert not fakes.calls("get_pr_checks")
        assert lines[-1] == "NEXT: rerun-pipeline"

    def test_github_pr_for_another_branch_fails(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        fakes.no_pr_github()
        _head(fakes, 41, branch="someone/else")
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--pr", "41"], capsys)
        assert code == 1
        assert (
            values(lines, "CHECK")[0]
            == "pipeline=FAIL pr=41 head branch someone/else is not feat/ship-change"
        )
        assert not fakes.calls("get_pr_checks")

    def test_github_head_moving_during_the_check_is_pending(
        self, make_repo, fakes, scripts, capsys
    ):
        repo = make_repo(GITHUB)
        fakes.no_pr_github()
        head = git(repo, "rev-parse", "HEAD")
        fakes.rule(
            "gh",
            ["pr", "view", "41"],
            {
                "stdout": json.dumps(
                    {
                        "headRefName": "feat/ship-change",
                        "headRefOid": head,
                        "url": "https://github.com/o/r/pull/41",
                    }
                )
            },
            {
                "stdout": json.dumps(
                    {
                        "headRefName": "feat/ship-change",
                        "headRefOid": "1" * 40,
                        "url": "https://github.com/o/r/pull/41",
                    }
                )
            },
        )
        fakes.rule(
            "get_pr_checks",
            [],
            {
                "stdout": json.dumps({"Data": {"RequiredState": "SUCCESS", "AllPassing": True}})
                + "\n"
            },
        )
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--pr", "41"], capsys)
        assert code == 0
        assert values(lines, "CHECK") == ["pipeline=PENDING pr=41 head moved during the check"]

    @pytest.mark.parametrize(
        "response",
        [
            {"rc": 1, "stderr": "HTTP 502\n"},
            {"stdout": "not json"},
            {"stdout": json.dumps({"headRefName": "x"})},
        ],
    )
    def test_github_head_query_failure_stops(self, make_repo, fakes, scripts, capsys, response):
        make_repo(GITHUB)
        fakes.no_pr_github()
        fakes.rule("gh", ["pr", "view", "41"], response)
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--pr", "41"], capsys)
        assert code == 3
        assert lines[-1].startswith("STOP: checks-query-failed")

    def _ado(self, make_repo, fakes, *, source=None, head=None):
        repo = make_repo(ADO)
        fakes.rule(
            "az",
            ["repos", "pr", "list"],
            {
                "stdout": json.dumps(
                    [
                        {
                            "pullRequestId": 77,
                            "targetRefName": "refs/heads/main",
                            "createdBy": {"uniqueName": "me"},
                        }
                    ]
                )
            },
        )
        fakes.rule("az", ["account", "show"], {"stdout": "me\n"})
        state = {
            "source": source or "refs/heads/feat/ship-change",
            "head": head or git(repo, "rev-parse", "HEAD"),
            "merge": MERGE,
        }
        fakes.rule("az", ["repos", "pr", "show"], {"stdout": json.dumps(state)})
        return repo

    def test_ado_stale_pr_head_defers_without_reading_policies(
        self, make_repo, fakes, scripts, capsys
    ):
        self._ado(make_repo, fakes, head="0" * 40)
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--wait-seconds", "0"], capsys)
        assert code == 0
        assert values(lines, "CHECK")[0].startswith("pipeline=DEFERRED pr=77")
        assert not [
            call for call in fakes.calls("az") if call[1:5] == ["repos", "pr", "policy", "list"]
        ]

    def test_ado_pr_for_another_branch_fails(self, make_repo, fakes, scripts, capsys):
        self._ado(make_repo, fakes, source="refs/heads/other")
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--wait-seconds", "0"], capsys)
        assert code == 1
        assert (
            values(lines, "CHECK")[0]
            == "pipeline=FAIL pr=77 head branch other is not feat/ship-change"
        )

    def test_ado_head_moving_during_the_check_is_pending(self, make_repo, fakes, scripts, capsys):
        repo = self._ado(make_repo, fakes)
        head = git(repo, "rev-parse", "HEAD")
        first = {"source": "refs/heads/feat/ship-change", "head": head, "merge": MERGE}
        moved = dict(first, head="1" * 40)
        fakes.rule(
            "az",
            ["repos", "pr", "show"],
            {"stdout": json.dumps(first)},
            {"stdout": json.dumps(moved)},
        )
        approved_ado_build(fakes, MERGE)
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--wait-seconds", "0"], capsys)
        assert code == 0
        assert values(lines, "CHECK") == ["pipeline=PENDING pr=77 head moved during the check"]

    @pytest.mark.parametrize("response", [{"rc": 1, "stderr": "TF000\n"}, {"stdout": "not json"}])
    def test_ado_show_failure_stops(self, make_repo, fakes, scripts, capsys, response):
        self._ado(make_repo, fakes)
        fakes.rule("az", ["repos", "pr", "show"], response)
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--wait-seconds", "0"], capsys)
        assert code == 3
        assert lines[-1].startswith("STOP: pipeline-query-failed")


class TestMissingAuthor:
    """Finding: an open PR with no author left the mode at owner."""

    @pytest.mark.parametrize("author", [{}, {"login": None}, {"login": ""}, None, "not-an-object"])
    def test_github_open_pr_without_author_stops(self, make_repo, fakes, scripts, capsys, author):
        make_repo(GITHUB)
        payload = {"number": 9, "state": "OPEN", "url": "u", "baseRefName": "main"}
        if author is not None:
            payload["author"] = author
        fakes.rule("gh", ["pr", "view"], {"stdout": json.dumps(payload)})
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 3
        assert lines[-1].startswith("STOP: pr-author-unknown PR 9")
        assert not values(lines, "MODE")
        assert not fakes.calls("gh")[1:], "no user query once the author is unknown"

    @pytest.mark.parametrize("created_by", [None, {}, {"uniqueName": ""}])
    def test_ado_open_pr_without_author_stops(self, make_repo, fakes, scripts, capsys, created_by):
        make_repo(ADO)
        entry = {"pullRequestId": 77, "targetRefName": "refs/heads/main"}
        if created_by is not None:
            entry["createdBy"] = created_by
        fakes.rule("az", ["repos", "pr", "list"], {"stdout": json.dumps([entry])})
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 3
        assert lines[-1].startswith("STOP: pr-author-unknown PR 77")

    def test_publish_on_unknown_author_never_pushes(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path
    ):
        repo = make_repo(GITHUB)
        fakes.rule(
            "gh",
            ["pr", "view"],
            {
                "stdout": json.dumps(
                    {"number": 9, "state": "OPEN", "url": "u", "baseRefName": "main"}
                )
            },
        )
        code, lines = invoke(
            scripts[3],
            [
                "publish",
                "--paths-checked-by-hand",
                "--title",
                TITLE,
                "--body-file",
                str(body_file(repo)),
            ],
            capsys,
        )
        assert code == 3
        assert lines[-1].startswith("STOP: pr-author-unknown")
        assert not _pushed(tmp_path)
