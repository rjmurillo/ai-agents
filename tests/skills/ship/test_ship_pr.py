"""Behavior tests for ship_pr.py: branch, prepare, check, and argument handling."""

from __future__ import annotations

import json

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import (
    ADO,
    EM_DASH,
    EN_DASH,
    GITHUB,
    TITLE,
    VALIDATOR_CRITICAL,
    VALIDATOR_PASS,
    run_pr,
    values,
)


class TestBranch:
    def test_creates_and_switches(self, make_repo, fakes, scripts, capsys):
        repo = make_repo(GITHUB, branch="main")
        code, lines = run_pr(scripts, capsys, "branch", "--name", "fix/parser-log-enrichment")
        assert code == 0
        assert values(lines, "BRANCH") == ["fix/parser-log-enrichment"]
        assert git(repo, "branch", "--show-current") == "fix/parser-log-enrichment"
        assert lines[-1] == "NEXT: commit-then-review"

    @pytest.mark.parametrize(
        "name", ["main", "feature/x", "fix/UPPER", "fix/-x", "--force", "fix/a", "fix/x y"]
    )
    def test_bad_names_rejected(self, make_repo, fakes, scripts, capsys, name):
        make_repo(GITHUB, branch="main")
        code, lines = run_pr(scripts, capsys, "branch", "--name", name)
        assert code in (1, 2)
        assert lines[-1].startswith(("STOP: bad-branch-name", "STOP: bad-arguments"))

    def test_existing_branch_fails(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB, branch="fix/parser-log")
        code, lines = run_pr(scripts, capsys, "branch", "--name", "fix/parser-log")
        assert code == 1
        assert lines[-1].startswith("STOP: branch-create-failed")


class TestPrepare:
    def test_prints_the_allocated_body_file(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        fakes.rule(
            "new_pr", ["--prepare-body-file"], {"stdout": ".project-toolkit/scratch/pr-body-1.md\n"}
        )
        code, lines = run_pr(scripts, capsys, "prepare", "--base", "main")
        assert code == 0
        assert values(lines, "BODY_FILE") == [".project-toolkit/scratch/pr-body-1.md"]
        assert fakes.calls("new_pr")[0][1:] == ["--prepare-body-file", "--base", "main"]
        assert lines[-1] == "NEXT: write-body"

    def test_allocator_failure_stops(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        fakes.rule("new_pr", ["--prepare-body-file"], {"rc": 2, "stderr": "ERROR: no template\n"})
        code, lines = run_pr(scripts, capsys, "prepare")
        assert code == 2
        assert lines[-1].startswith("STOP: prepare-failed")

    def test_missing_helper_stops(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        (fakes.skills / "github" / "scripts" / "pr" / "new_pr.py").unlink()
        code, lines = run_pr(scripts, capsys, "prepare")
        assert code == 2
        assert lines[-1].startswith("STOP: prepare-failed")

    def test_windows_seeds_a_scratch_file_without_the_allocator(
        self, make_repo, fakes, scripts, capsys, monkeypatch
    ):
        repo = make_repo(GITHUB)
        (repo / ".github").mkdir()
        (repo / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text("## Summary\n", encoding="utf-8")
        monkeypatch.setattr(scripts[0], "on_windows", lambda: True)
        code, lines = run_pr(scripts, capsys, "prepare")
        assert code == 0
        path = repo / values(lines, "BODY_FILE")[0]
        assert path.read_text(encoding="utf-8") == "<!-- replace with PR body -->\n## Summary\n"
        assert not fakes.calls("new_pr")


class TestCheck:
    def test_clean_title_and_body_pass(self, owner, scripts, capsys):
        _repo, body = owner
        code, lines = run_pr(scripts, capsys, "check", "--title", TITLE, "--body-file", str(body))
        assert code == 0
        checks = values(lines, "CHECK")
        assert checks[:2] == ["title=PASS", "body=PASS"]
        assert checks[2].startswith("paths=NOT-RUN")
        assert lines[-1] == "NEXT: compare-paths-by-hand"

    @pytest.mark.parametrize(
        "title",
        [
            "Updated the ship skill",
            f"feat(ship): add the driver {EM_DASH} now",
            "@feat: add",
            "-feat: add",
            'feat: add "quotes"',
            "feat: add $HOME",
            "feat: add `code`",
            " feat: padded",
            "",
        ],
    )
    def test_bad_titles_fail(self, owner, scripts, capsys, title):
        _repo, body = owner
        code, lines = run_pr(scripts, capsys, "check", f"--title={title}", "--body-file", str(body))
        assert code == 1
        assert values(lines, "CHECK")[0].startswith("title=FAIL")
        assert lines[-1].startswith("STOP: check-failed title")

    @pytest.mark.parametrize(
        "text",
        [
            "<!-- replace with PR body -->\n## Summary\n",
            f"## Summary\n\nUses an en dash {EN_DASH} here.\n",
            "## Summary\\n\\nescaped\n",
            "   \n",
        ],
    )
    def test_bad_bodies_fail(self, owner, scripts, capsys, body_file, text):
        repo, _body = owner
        code, lines = run_pr(
            scripts, capsys, "check", "--title", TITLE, "--body-file", str(body_file(repo, text))
        )
        assert code == 1
        assert values(lines, "CHECK")[1].startswith("body=FAIL")

    @pytest.mark.parametrize(
        "raw", ["README.md", "-x", "@.project-toolkit/scratch/pr-body-test.md", "/etc/passwd"]
    )
    def test_body_file_outside_scratch_stops(self, owner, scripts, capsys, raw):
        code, lines = run_pr(scripts, capsys, "check", "--title", TITLE, "--body-file", raw)
        assert code == 2
        assert lines[-1].startswith(("STOP: bad-body-file", "STOP: bad-arguments"))

    def test_base_validator_findings_fail_the_check(self, owner, base_validator, scripts, capsys):
        repo, body = owner
        base_validator(repo, VALIDATOR_CRITICAL, closure=False)
        code, lines = run_pr(scripts, capsys, "check", "--title", TITLE, "--body-file", str(body))
        assert code == 1
        assert "paths=FAIL exit=1" in values(lines, "CHECK")
        assert values(lines, "FINDING") == ["File mentioned but not in diff: old.py"]

    def test_base_validator_pass(self, owner, base_validator, scripts, capsys):
        repo, body = owner
        base_validator(repo, VALIDATOR_PASS)
        code, lines = run_pr(scripts, capsys, "check", "--title", TITLE, "--body-file", str(body))
        assert code == 0
        assert "paths=PASS" in values(lines, "CHECK")
        assert lines[-1] == "NEXT: publish"

    @pytest.mark.parametrize(
        ("response", "verdict"),
        [
            (
                {"stdout": json.dumps({"ErrorCount": 0, "WarningCount": 2, "Validations": {}})},
                "description=PASS",
            ),
            (
                {
                    "stdout": json.dumps(
                        {
                            "ErrorCount": 1,
                            "Validations": {
                                "IssueKeywords": {"Status": "WARN", "Message": "no keyword"},
                                "ConventionalCommit": {"Status": "FAIL", "Message": "bad title"},
                            },
                        }
                    )
                },
                "description=FAIL ConventionalCommit: bad title",
            ),
            (
                {"stdout": json.dumps({"ErrorCount": 2, "Validations": {}})},
                "description=FAIL errors=2",
            ),
            ({"stdout": "not a report"}, "description=FAIL the validator report did not parse"),
            ({"rc": 1}, "description=FAIL exit=1"),
        ],
    )
    def test_ado_runs_the_description_validator(
        self, make_repo, fakes, scripts, capsys, body_file, response, verdict
    ):
        repo = make_repo(ADO)
        fakes.no_pr_ado()
        fakes.rule("validate_pr_description", [], response)
        _code, lines = run_pr(
            scripts, capsys, "check", "--title", TITLE, "--body-file", str(body_file(repo))
        )
        assert verdict in values(lines, "CHECK")

    def test_ado_missing_description_validator_fails(
        self, make_repo, fakes, scripts, capsys, body_file
    ):
        repo = make_repo(ADO)
        fakes.no_pr_ado()
        (fakes.skills / "github" / "scripts" / "pr" / "validate_pr_description.py").unlink()
        code, lines = run_pr(
            scripts, capsys, "check", "--title", TITLE, "--body-file", str(body_file(repo))
        )
        assert code == 1
        assert values(lines, "CHECK")[-1].startswith("description=FAIL")

    def test_detect_stop_propagates(self, make_repo, fakes, scripts, capsys):
        make_repo(None)
        code, lines = run_pr(scripts, capsys, "check", "--title", TITLE, "--body-file", "x")
        assert code == 2
        assert lines[-1].startswith("STOP: no-origin")


class TestArguments:
    @pytest.mark.parametrize(
        "argv",
        [
            [],
            ["bogus"],
            ["check", "--title", TITLE],
            ["publish", "--paths-checked-by-hand", "--title", TITLE, "--body-file", "x", "--forc"],
            [
                "publish",
                "--paths-checked-by-hand",
                "--title",
                TITLE,
                "--body-file",
                "x",
                "--base",
                "-main",
            ],
            [
                "publish",
                "--paths-checked-by-hand",
                "--title",
                TITLE,
                "--body-file",
                "x",
                "--require-axis",
                "Bad",
            ],
            ["check", "--titl", TITLE, "--body-file", "x"],
        ],
    )
    def test_bad_arguments_stop_exit_2(self, owner, scripts, capsys, argv):
        code, lines = run_pr(scripts, capsys, *argv)
        assert code == 2
        assert lines[-1].startswith("STOP: bad-arguments")

    def test_outside_a_repo_stops(self, fakes, scripts, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        code, lines = run_pr(scripts, capsys, "prepare")
        assert code == 2
        assert lines[-1].startswith("STOP: no-repo")

    def test_json_envelope_on_stop(self, owner, scripts, capsys):
        _repo, body = owner
        code = scripts[3].main(
            ["check", "--title", "bad", "--body-file", str(body), "--output-format", "json"]
        )
        envelope = json.loads(capsys.readouterr().out)
        assert code == 1
        assert envelope["Success"] is False
        assert envelope["Error"]["Code"] == 1
        assert envelope["Data"]["STOP"].startswith("check-failed")
        assert envelope["Data"]["CHECK"][0].startswith("title=FAIL")
