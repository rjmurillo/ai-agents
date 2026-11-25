"""Behavior tests for ship_pr.py: branch, prepare, check, publish.

Pushes go to a real bare repository through ``pushInsteadOf``. ``gh``, ``az``,
and the helper scripts are fakes.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import invoke, values

GITHUB = "https://github.com/rjmurillo/ai-agents.git"
ADO = "https://dev.azure.com/contoso/p/_git/r"
TITLE = "feat(ship): add the driver"
PR_URL = "https://github.com/rjmurillo/ai-agents/pull/501"
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)


def _pr(scripts, capsys, *argv):
    return invoke(scripts[3], list(argv), capsys)


def _ado_created(description: str = "## Summary") -> dict:
    return {
        "stdout": json.dumps(
            {
                "pullRequestId": 88,
                "description": description,
                "repository": {"webUrl": "https://dev.azure.com/c/p/_git/r"},
            }
        )
    }


@pytest.fixture
def owner(make_repo, fakes, body_file):
    repo = make_repo(GITHUB)
    fakes.no_pr_github()
    fakes.marker(0)
    fakes.rule(
        "new_pr", ["--title"], {"stdout": f"Creating PR...\n{PR_URL}\nPR created successfully!\n"}
    )
    return repo, body_file(repo)


class TestBranch:
    def test_creates_and_switches(self, make_repo, fakes, scripts, capsys):
        repo = make_repo(GITHUB, branch="main")
        code, lines = _pr(scripts, capsys, "branch", "--name", "fix/parser-log-enrichment")
        assert code == 0
        assert values(lines, "BRANCH") == ["fix/parser-log-enrichment"]
        assert git(repo, "branch", "--show-current") == "fix/parser-log-enrichment"
        assert lines[-1] == "NEXT: commit-then-review"

    @pytest.mark.parametrize(
        "name", ["main", "feature/x", "fix/UPPER", "fix/-x", "--force", "fix/a", "fix/x y"]
    )
    def test_bad_names_rejected(self, make_repo, fakes, scripts, capsys, name):
        make_repo(GITHUB, branch="main")
        code, lines = _pr(scripts, capsys, "branch", "--name", name)
        assert code in (1, 2)
        assert lines[-1].startswith(("STOP: bad-branch-name", "STOP: bad-arguments"))

    def test_existing_branch_fails(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB, branch="fix/parser-log")
        code, lines = _pr(scripts, capsys, "branch", "--name", "fix/parser-log")
        assert code == 1
        assert lines[-1].startswith("STOP: branch-create-failed")


class TestPrepare:
    def test_prints_the_allocated_body_file(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        fakes.rule(
            "new_pr", ["--prepare-body-file"], {"stdout": ".project-toolkit/scratch/pr-body-1.md\n"}
        )
        code, lines = _pr(scripts, capsys, "prepare", "--base", "main")
        assert code == 0
        assert values(lines, "BODY_FILE") == [".project-toolkit/scratch/pr-body-1.md"]
        assert fakes.calls("new_pr")[0][1:] == ["--prepare-body-file", "--base", "main"]
        assert lines[-1] == "NEXT: write-body"

    def test_allocator_failure_stops(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        fakes.rule("new_pr", ["--prepare-body-file"], {"rc": 2, "stderr": "ERROR: no template\n"})
        code, lines = _pr(scripts, capsys, "prepare")
        assert code == 2
        assert lines[-1].startswith("STOP: prepare-failed")

    def test_missing_helper_stops(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        (fakes.skills / "github" / "scripts" / "pr" / "new_pr.py").unlink()
        code, lines = _pr(scripts, capsys, "prepare")
        assert code == 2
        assert lines[-1].startswith("STOP: prepare-failed")

    def test_windows_seeds_a_scratch_file_without_the_allocator(
        self, make_repo, fakes, scripts, capsys, monkeypatch
    ):
        repo = make_repo(GITHUB)
        (repo / ".github").mkdir()
        (repo / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text("## Summary\n", encoding="utf-8")
        monkeypatch.setattr(scripts[3], "_IS_WINDOWS", True)
        code, lines = _pr(scripts, capsys, "prepare")
        assert code == 0
        path = repo / values(lines, "BODY_FILE")[0]
        assert path.read_text(encoding="utf-8") == "<!-- replace with PR body -->\n## Summary\n"
        assert not fakes.calls("new_pr")


class TestCheck:
    def test_clean_title_and_body_pass(self, owner, scripts, capsys):
        _repo, body = owner
        code, lines = _pr(scripts, capsys, "check", "--title", TITLE, "--body-file", str(body))
        assert code == 0
        checks = values(lines, "CHECK")
        assert checks[:2] == ["title=PASS", "body=PASS"]
        assert checks[2].startswith("paths=NOT-RUN")
        assert lines[-1] == "NEXT: publish"

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
        code, lines = _pr(scripts, capsys, "check", f"--title={title}", "--body-file", str(body))
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
        code, lines = _pr(
            scripts, capsys, "check", "--title", TITLE, "--body-file", str(body_file(repo, text))
        )
        assert code == 1
        assert values(lines, "CHECK")[1].startswith("body=FAIL")

    @pytest.mark.parametrize(
        "raw", ["README.md", "-x", "@.project-toolkit/scratch/pr-body-test.md", "/etc/passwd"]
    )
    def test_body_file_outside_scratch_stops(self, owner, scripts, capsys, raw):
        code, lines = _pr(scripts, capsys, "check", "--title", TITLE, "--body-file", raw)
        assert code == 2
        assert lines[-1].startswith(("STOP: bad-body-file", "STOP: bad-arguments"))

    def test_local_path_validator_runs_when_present(
        self, owner, fakes, scripts, capsys, monkeypatch
    ):
        repo, body = owner
        validator = repo / "scripts" / "validation" / "pr_description.py"
        validator.parent.mkdir(parents=True)
        validator.write_text("", encoding="utf-8")
        fakes.rule(
            "uv",
            [],
            {"rc": 1, "stdout": "CRITICAL: File mentioned but not in diff: old.py\nother line\n"},
        )
        uv = fakes.root / "bin" / "uv"
        uv.write_text((fakes.root / "bin" / "gh").read_text(encoding="utf-8"), encoding="utf-8")
        uv.chmod(0o755)
        code, lines = _pr(scripts, capsys, "check", "--title", TITLE, "--body-file", str(body))
        assert code == 1
        assert "paths=FAIL exit=1" in values(lines, "CHECK")
        assert values(lines, "FINDING") == ["CRITICAL: File mentioned but not in diff: old.py"]
        call = fakes.calls("uv")[0]
        assert call[1:6] == [
            "run",
            "--frozen",
            "python",
            "-I",
            "scripts/validation/pr_description.py",
        ]
        assert call[-2:] == ["--base", "origin/main"]

    def test_local_path_validator_pass(self, owner, fakes, scripts, capsys):
        repo, body = owner
        validator = repo / "scripts" / "validation" / "pr_description.py"
        validator.parent.mkdir(parents=True)
        validator.write_text("", encoding="utf-8")
        fakes.rule("uv", [], {"rc": 0})
        uv = fakes.root / "bin" / "uv"
        uv.write_text((fakes.root / "bin" / "gh").read_text(encoding="utf-8"), encoding="utf-8")
        uv.chmod(0o755)
        code, lines = _pr(scripts, capsys, "check", "--title", TITLE, "--body-file", str(body))
        assert code == 0
        assert "paths=PASS" in values(lines, "CHECK")

    @pytest.mark.parametrize(
        ("response", "verdict"),
        [
            ({"stdout": "Warnings:\n  no Closes keyword\n"}, "description=PASS"),
            ({"stdout": "Errors:\n  bad title\n"}, "description=FAIL exit=0"),
            ({"rc": 1}, "description=FAIL exit=1"),
        ],
    )
    def test_ado_runs_the_description_validator(
        self, make_repo, fakes, scripts, capsys, body_file, response, verdict
    ):
        repo = make_repo(ADO)
        fakes.no_pr_ado()
        fakes.rule("validate_pr_description", [], response)
        _code, lines = _pr(
            scripts, capsys, "check", "--title", TITLE, "--body-file", str(body_file(repo))
        )
        assert verdict in values(lines, "CHECK")

    def test_ado_missing_description_validator_fails(
        self, make_repo, fakes, scripts, capsys, body_file
    ):
        repo = make_repo(ADO)
        fakes.no_pr_ado()
        (fakes.skills / "github" / "scripts" / "pr" / "validate_pr_description.py").unlink()
        code, lines = _pr(
            scripts, capsys, "check", "--title", TITLE, "--body-file", str(body_file(repo))
        )
        assert code == 1
        assert values(lines, "CHECK")[-1].startswith("description=FAIL")

    def test_detect_stop_propagates(self, make_repo, fakes, scripts, capsys):
        make_repo(None)
        code, lines = _pr(scripts, capsys, "check", "--title", TITLE, "--body-file", "x")
        assert code == 2
        assert lines[-1].startswith("STOP: no-origin")


class TestPublishGitHub:
    def test_pushes_then_creates_the_pr(self, owner, fakes, scripts, capsys, tmp_path):
        repo, body = owner
        code, lines = _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 0, lines
        assert values(lines, "PUSH") == ["pushed"]
        assert values(lines, "PR") == [f"host=github number=501 url={PR_URL}"]
        assert lines[-1] == "NEXT: discharge"
        remote_head = git(tmp_path / "remote.git", "rev-parse", "refs/heads/feat/ship-change")
        assert remote_head == git(repo, "rev-parse", "HEAD")
        create = fakes.calls("new_pr")[0]
        assert create[1:] == [
            "--title",
            TITLE,
            "--base",
            "main",
            "--body-file",
            str(body.resolve()),
        ]

    def test_never_creates_a_commit(self, owner, scripts, capsys):
        repo, body = owner
        before = git(repo, "rev-parse", "HEAD")
        _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert git(repo, "rev-parse", "HEAD") == before

    def test_draft_skips_the_marker_and_opens_a_draft(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        fakes.marker(1)
        code, lines = _pr(
            scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body), "--draft"
        )
        assert code == 0
        assert not fakes.calls("validate_review_marker")
        assert fakes.calls("new_pr")[0][-1] == "--draft"

    def test_unreviewed_head_stops_before_push(self, owner, fakes, scripts, capsys, tmp_path):
        _repo, body = owner
        fakes.marker(1)
        code, lines = _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 1
        assert lines[-1].startswith("STOP: head-not-reviewed")
        assert "PUSH: pushed" not in lines
        assert not fakes.calls("new_pr")
        done = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "refs/heads/feat/ship-change"],
            cwd=tmp_path / "remote.git",
            capture_output=True,
            check=False,
        )
        assert done.returncode != 0

    def test_validator_config_error_stops(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        fakes.marker(2)
        code, lines = _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 2
        assert lines[-1].startswith("STOP: validator-config")

    def test_dirty_tree_stops(self, owner, scripts, capsys):
        repo, body = owner
        (repo / "README.md").write_text("changed\n", encoding="utf-8")
        code, lines = _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 1
        assert lines[-1].startswith("STOP: tree-dirty")

    def test_failed_check_stops_before_push(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        code, lines = _pr(
            scripts, capsys, "publish", "--title", "bad title", "--body-file", str(body)
        )
        assert code == 1
        assert lines[-1].startswith("STOP: check-failed title")
        assert "PUSH: pushed" not in lines

    def test_contributor_mode_stops(self, make_repo, fakes, scripts, capsys, body_file):
        repo = make_repo(GITHUB)
        fakes.rule(
            "gh",
            ["pr", "view"],
            {
                "stdout": json.dumps(
                    {"number": 3, "state": "OPEN", "author": {"login": "alice"}, "url": "u"}
                )
            },
        )
        fakes.rule("gh", ["api", "user"], {"stdout": "bob\n"})
        code, lines = _pr(
            scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body_file(repo))
        )
        assert code == 1
        assert lines[-1].startswith("STOP: contributor-mode")

    def test_existing_pr_pushes_without_creating(
        self, make_repo, fakes, scripts, capsys, body_file
    ):
        repo = make_repo(GITHUB)
        fakes.rule(
            "gh",
            ["pr", "view"],
            {
                "stdout": json.dumps(
                    {
                        "number": 7,
                        "state": "OPEN",
                        "author": {"login": "me"},
                        "url": "https://x/pull/7",
                    }
                )
            },
        )
        fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})
        fakes.marker(0)
        code, lines = _pr(
            scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body_file(repo))
        )
        assert code == 0
        assert values(lines, "PR") == ["host=github number=7 url=https://x/pull/7 existing"]
        assert not fakes.calls("new_pr")

    def test_rejected_push_stops_for_a_human_and_never_forces(
        self, owner, fakes, scripts, capsys, tmp_path
    ):
        repo, body = owner
        other = tmp_path / "other"
        subprocess.run(["git", "clone", "-q", str(tmp_path / "remote.git"), str(other)], check=True)
        git(other, "switch", "-q", "-c", "feat/ship-change")
        (other / "remote.txt").write_text("remote\n", encoding="utf-8")
        git(other, "add", ".")
        git(other, "commit", "-q", "-m", "chore: remote change")
        git(other, "commit", "--allow-empty", "-q", "-m", "chore: second remote change")
        (repo / "local.txt").write_text("local\n", encoding="utf-8")
        git(repo, "add", "local.txt")
        git(repo, "commit", "-q", "-m", "chore: local change")
        git(other, "push", "-q", "origin", "feat/ship-change")
        remote_before = git(tmp_path / "remote.git", "rev-parse", "refs/heads/feat/ship-change")
        code, lines = _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 1
        assert lines[-1].startswith("STOP: push-rejected")
        assert "force push is a human action" in lines[-1]
        assert (
            git(tmp_path / "remote.git", "rev-parse", "refs/heads/feat/ship-change")
            == remote_before
        )
        assert not fakes.calls("new_pr")

    def test_push_argv_is_fixed_and_never_forced(self, owner, scripts, capsys, monkeypatch):
        repo, body = owner
        common = scripts[0]
        seen: list[list[str]] = []
        real_git = common.git

        def spy(args, cwd=None, timeout=60):
            seen.append(list(args))
            return real_git(args, cwd=cwd, timeout=timeout)

        monkeypatch.setattr(common, "git", spy)
        _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        pushes = [args for args in seen if args[:1] == ["push"]]
        assert pushes == [
            [
                "push",
                "--set-upstream",
                "origin",
                "refs/heads/feat/ship-change:refs/heads/feat/ship-change",
            ]
        ]
        assert not any(arg.startswith(("+", "--force", "-f")) for arg in pushes[0])

    @pytest.mark.parametrize(
        ("stderr", "reason", "code"),
        [
            ("fatal: Authentication failed for 'https://github.com/'\n", "auth-failed", 4),
            ("fatal: unable to access: Could not resolve host\n", "push-failed", 3),
            ("", "push-failed", 3),
        ],
    )
    def test_push_failures_are_classified(
        self, owner, scripts, capsys, monkeypatch, stderr, reason, code
    ):
        _repo, body = owner
        common = scripts[0]
        real_git = common.git

        def failing(args, cwd=None, timeout=60):
            if args[:1] == ["push"]:
                return common.Completed(128, "", stderr)
            return real_git(args, cwd=cwd, timeout=timeout)

        monkeypatch.setattr(common, "git", failing)
        exit_code, lines = _pr(
            scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body)
        )
        assert exit_code == code
        assert lines[-1].startswith(f"STOP: {reason}")

    @pytest.mark.parametrize(
        "response",
        [{"rc": 1, "stderr": "gh: GraphQL error\n"}, {"rc": 0, "stdout": "no url here\n"}],
    )
    def test_create_failure_stops_exit_3(self, owner, fakes, scripts, capsys, response):
        _repo, body = owner
        fakes.rule("new_pr", ["--title"], response)
        code, lines = _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 3
        assert values(lines, "PUSH") == ["pushed"]
        assert lines[-1].startswith("STOP: pr-create-failed")

    def test_missing_new_pr_stops(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        (fakes.skills / "github" / "scripts" / "pr" / "new_pr.py").unlink()
        code, lines = _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 2
        assert lines[-1].startswith("STOP: pr-create-failed")

    def test_windows_passes_the_body_text(self, owner, fakes, scripts, capsys, monkeypatch):
        _repo, body = owner
        monkeypatch.setattr(scripts[3], "_IS_WINDOWS", True)
        code, _lines = _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 0
        create = fakes.calls("new_pr")[0]
        assert create[create.index("--body") + 1] == body.read_text(encoding="utf-8")
        assert "--body-file" not in create


class TestPublishAdo:
    @pytest.fixture
    def ado(self, make_repo, fakes, body_file):
        repo = make_repo(ADO)
        fakes.no_pr_ado()
        fakes.marker(0)
        fakes.rule("validate_pr_description", [], {"stdout": ""})
        return repo, body_file(repo)

    def test_create_uses_the_fixed_argument_list(self, ado, fakes, scripts, capsys):
        _repo, body = ado
        fakes.rule("az", ["repos", "pr", "create"], _ado_created())
        code, lines = _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 0, lines
        assert values(lines, "PR") == [
            "host=ado number=88 url=https://dev.azure.com/c/p/_git/r/pullrequest/88"
        ]
        create = [call for call in fakes.calls("az") if call[1:4] == ["repos", "pr", "create"]][0]
        assert create[1:] == [
            "repos",
            "pr",
            "create",
            "--output",
            "json",
            "--title",
            TITLE,
            "--description",
            f"@{body.resolve()}",
            "--target-branch",
            "main",
            "--draft",
            "false",
        ]
        assert sum(arg.startswith("@") for arg in create) == 1

    def test_draft_flag_reaches_az(self, ado, fakes, scripts, capsys):
        _repo, body = ado
        fakes.marker(1)
        fakes.rule("az", ["repos", "pr", "create"], _ado_created())
        code, _lines = _pr(
            scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body), "--draft"
        )
        assert code == 0
        create = [call for call in fakes.calls("az") if call[1:4] == ["repos", "pr", "create"]][0]
        assert create[-2:] == ["--draft", "true"]

    def test_at_fallback_description_stops_exit_3_and_names_the_pr(
        self, ado, fakes, scripts, capsys
    ):
        _repo, body = ado
        fakes.rule("az", ["repos", "pr", "create"], _ado_created(description=f"@{body}"))
        code, lines = _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 3
        assert values(lines, "PR")[0].startswith("host=ado number=88")
        assert lines[-1].startswith("STOP: description-upload-failed PR 88 is open")

    @pytest.mark.parametrize(
        ("response", "reason", "code"),
        [
            ({"rc": 1, "stderr": "TF401019\n"}, "pr-create-failed", 3),
            ({"rc": 1, "stderr": "Please run 'az login'\n"}, "auth-failed", 4),
            ({"stdout": "{}"}, "pr-create-failed", 3),
        ],
    )
    def test_create_failures(self, ado, fakes, scripts, capsys, response, reason, code):
        _repo, body = ado
        fakes.rule("az", ["repos", "pr", "create"], response)
        exit_code, lines = _pr(
            scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body)
        )
        assert exit_code == code
        assert lines[-1].startswith(f"STOP: {reason}")

    def test_missing_web_url_reports_unknown(self, ado, fakes, scripts, capsys):
        _repo, body = ado
        fakes.rule(
            "az",
            ["repos", "pr", "create"],
            {"stdout": json.dumps({"pullRequestId": 4, "description": "ok"})},
        )
        code, lines = _pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 0
        assert values(lines, "PR") == ["host=ado number=4 url=unknown"]


class TestArguments:
    @pytest.mark.parametrize(
        "argv",
        [
            [],
            ["bogus"],
            ["check", "--title", TITLE],
            ["publish", "--title", TITLE, "--body-file", "x", "--forc"],
            ["publish", "--title", TITLE, "--body-file", "x", "--base", "-main"],
            ["publish", "--title", TITLE, "--body-file", "x", "--require-axis", "Bad"],
            ["check", "--titl", TITLE, "--body-file", "x"],
        ],
    )
    def test_bad_arguments_stop_exit_2(self, owner, scripts, capsys, argv):
        code, lines = _pr(scripts, capsys, *argv)
        assert code == 2
        assert lines[-1].startswith("STOP: bad-arguments")

    def test_outside_a_repo_stops(self, fakes, scripts, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        code, lines = _pr(scripts, capsys, "prepare")
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
