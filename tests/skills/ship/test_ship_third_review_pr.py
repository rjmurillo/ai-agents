"""Third-review fixes for ship_pr.py: strict body decoding and the run budget for publish."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.skills.ship.ship_helpers import (
    ADO,
    TITLE,
    ado_created,
    publish,
    run_pr,
    values,
)

BAD_BODY = b"\x93quote\x94"
RERUN = "rerun publish; it detects an existing PR"


def _pushed(tmp_path: Path) -> bool:
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


class TestBodyFileIsStrictUtf8:
    def test_check_refuses_a_non_utf8_body(self, owner, scripts, capsys):
        _repo, body = owner
        body.write_bytes(BAD_BODY)
        code, lines = run_pr(scripts, capsys, "check", "--title", TITLE, "--body-file", str(body))
        assert code == 2
        assert lines[-1] == "STOP: bad-body-file body file is not UTF-8"
        assert not any(line.startswith("CHECK: body=") for line in lines)

    def test_publish_refuses_a_non_utf8_body_before_any_push(
        self, owner, fakes, scripts, capsys, tmp_path
    ):
        _repo, body = owner
        body.write_bytes(BAD_BODY)
        code, lines = publish(scripts, capsys, body)
        assert code == 2
        assert lines[-1] == "STOP: bad-body-file body file is not UTF-8"
        assert not _pushed(tmp_path)
        assert not fakes.calls("new_pr")
        assert not list(body.parent.glob("pr-body-publish-*"))

    def test_a_body_that_turns_non_utf8_after_the_first_read_is_refused_at_the_snapshot(
        self, owner, fakes, scripts, capsys, tmp_path, monkeypatch
    ):
        _repo, body = owner
        pr = scripts[3]
        real = pr._read_body
        reads: list[int] = []

        def flaky(path, result):
            if reads:
                path.write_bytes(BAD_BODY)
            reads.append(1)
            return real(path, result)

        monkeypatch.setattr(pr, "_read_body", flaky)
        code, lines = publish(scripts, capsys, body)
        assert len(reads) == 2
        assert code == 2
        assert lines[-1] == "STOP: bad-body-file body file is not UTF-8"
        assert not _pushed(tmp_path)

    def test_a_valid_non_ascii_body_publishes_unchanged(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        text = "## Summary\n\nCafé “quoted” text.\n"
        body.write_text(text, encoding="utf-8")
        code, lines = publish(scripts, capsys, body)
        assert code == 0, lines
        snapshots = list(body.parent.glob("pr-body-publish-*"))
        assert [path.read_text(encoding="utf-8") for path in snapshots] == [text]


class TestPushLeavesTimeForThePrCreate:
    @pytest.mark.parametrize(
        ("remaining", "expected"),
        [(10_000.0, 540), (540.0, 420), (300.0, 180), (121.0, 1), (100.0, 1), (1.0, 1)],
    )
    def test_push_timeout_is_capped_by_the_run_budget(
        self, owner, scripts, capsys, monkeypatch, remaining, expected
    ):
        _repo, body = owner
        common = scripts[0]
        real_git = common.git
        seen: list[float] = []

        def spy(args, cwd=None, timeout=60, **kw):
            if args[:1] == ["push"]:
                seen.append(timeout)
            return real_git(args, cwd=cwd, timeout=timeout, **kw)

        monkeypatch.setattr(common, "remaining_seconds", lambda: remaining)
        monkeypatch.setattr(common, "git", spy)
        code, lines = publish(scripts, capsys, body)
        assert code == 0, lines
        assert seen == [expected]


class TestCreateTimeoutSaysRerun:
    def test_github_create_timeout_says_the_pr_may_exist(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        fakes.rule(
            "new_pr", ["--title"], {"rc": 124, "stderr": "new_pr.py: timed out after 180s\n"}
        )
        code, lines = publish(scripts, capsys, body)
        assert code == 3
        assert lines[-1].startswith("STOP: pr-create-failed")
        assert RERUN in lines[-1]

    def test_github_create_failure_does_not_say_rerun(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        fakes.rule("new_pr", ["--title"], {"rc": 1, "stderr": "gh: boom\n"})
        code, lines = publish(scripts, capsys, body)
        assert code == 3
        assert lines[-1].startswith("STOP: pr-create-failed")
        assert RERUN not in lines[-1]

    @pytest.fixture
    def ado(self, make_repo, fakes, body_file):
        repo = make_repo(ADO)
        fakes.no_pr_ado()
        fakes.marker(0)
        fakes.rule(
            "validate_pr_description",
            [],
            {"stdout": json.dumps({"ErrorCount": 0, "WarningCount": 0, "Validations": {}})},
        )
        return body_file(repo)

    def test_ado_create_timeout_says_the_pr_may_exist(self, ado, fakes, scripts, capsys):
        fakes.rule("az", ["repos", "pr", "create"], {"rc": 124, "stderr": "az: timed out\n"})
        code, lines = publish(scripts, capsys, ado)
        assert code == 3
        assert lines[-1].startswith("STOP: pr-create-failed")
        assert RERUN in lines[-1]

    def test_ado_create_failure_does_not_say_rerun(self, ado, fakes, scripts, capsys):
        fakes.rule("az", ["repos", "pr", "create"], {"rc": 1, "stderr": "az: boom\n"})
        code, lines = publish(scripts, capsys, ado)
        assert code == 3
        assert RERUN not in lines[-1]

    def test_ado_create_success_is_unchanged(self, ado, fakes, scripts, capsys):
        fakes.rule("az", ["repos", "pr", "create"], ado_created())
        code, lines = publish(scripts, capsys, ado)
        assert code == 0, lines
        assert values(lines, "PR")[0].startswith("host=ado number=88")
