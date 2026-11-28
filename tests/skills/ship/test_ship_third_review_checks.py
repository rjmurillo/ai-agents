"""Third-review fixes: unsafe checkouts, pipeline limits, and the check text."""

from __future__ import annotations

import importlib.util
import json
from types import SimpleNamespace

import pytest

from tests.skills.ship.conftest import REAL_PREPARE_PR_BODY, git
from tests.skills.ship.ship_helpers import GITHUB, invoke, values
from tests.skills.ship.test_ship_preflight import (
    _ado,
    _checks,
    _head,
    _policies,
    _preflight,
    _show,
)


@pytest.fixture
def windows(scripts, monkeypatch):
    """A Windows host as far as ship_detect.unsafe_checkout can tell."""
    monkeypatch.setattr(scripts[0], "on_windows", lambda: True)
    monkeypatch.setenv("PATHEXT", ".exe;.cmd")


class TestUnsafeCheckout:
    @pytest.mark.parametrize("planted", ["git.exe", "gh.cmd", "az.exe"])
    def test_windows_stops_on_a_planted_program(
        self, make_repo, fakes, scripts, capsys, windows, planted
    ):
        repo = make_repo(GITHUB)
        (repo / planted).write_text("not the real program\n", encoding="utf-8")
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 2
        assert lines[-1].startswith("STOP: unsafe-checkout")
        assert planted in lines[-1]
        assert not fakes.calls()

    def test_windows_names_every_planted_file(self, make_repo, fakes, scripts, capsys, windows):
        repo = make_repo(GITHUB)
        (repo / "git.exe").write_text("x", encoding="utf-8")
        (repo / "az.cmd").write_text("x", encoding="utf-8")
        _code, lines = invoke(scripts[1], [], capsys)
        assert "git.exe" in lines[-1]
        assert "az.cmd" in lines[-1]

    def test_windows_checks_the_current_directory_too(
        self, make_repo, fakes, scripts, capsys, windows, monkeypatch
    ):
        repo = make_repo(GITHUB)
        sub = repo / "docs"
        sub.mkdir()
        (sub / "git.exe").write_text("not the real program\n", encoding="utf-8")
        monkeypatch.chdir(sub)
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 2
        assert lines[-1].startswith("STOP: unsafe-checkout")
        assert "docs" in lines[-1]
        assert "git.exe" in lines[-1]

    def test_windows_with_a_clean_root_passes(self, make_repo, fakes, scripts, capsys, windows):
        repo = make_repo(GITHUB)
        (repo / "notes.exe").write_text("not a spawned program\n", encoding="utf-8")
        (repo / "git").write_text("no suffix\n", encoding="utf-8")
        fakes.no_pr_github()
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 0, lines
        assert lines[-1] == "NEXT: preflight"

    def test_off_windows_the_same_file_is_not_refused(
        self, make_repo, fakes, scripts, capsys, monkeypatch
    ):
        repo = make_repo(GITHUB)
        monkeypatch.setenv("PATHEXT", ".exe;.cmd")
        (repo / "git.exe").write_text("not the real program\n", encoding="utf-8")
        fakes.no_pr_github()
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 0, lines
        assert lines[-1] == "NEXT: preflight"

    def test_preflight_inherits_the_stop(self, make_repo, fakes, scripts, capsys, windows):
        repo = make_repo(GITHUB)
        (repo / "gh.cmd").write_text("x", encoding="utf-8")
        code, lines = _preflight(scripts, capsys, "--check", "tree")
        assert code == 2
        assert lines[-1].startswith("STOP: unsafe-checkout")


class TestPlantedPrograms:
    @pytest.fixture
    def planted(self, scripts):
        return scripts[0]._windows.planted_programs

    def test_default_pathext_finds_an_uppercase_suffix(self, planted, tmp_path, monkeypatch):
        monkeypatch.delenv("PATHEXT", raising=False)
        (tmp_path / "az.BAT").write_text("x", encoding="utf-8")
        assert planted(tmp_path) == ["az.BAT"]

    def test_an_empty_root_has_none(self, planted, tmp_path, monkeypatch):
        monkeypatch.delenv("PATHEXT", raising=False)
        assert planted(tmp_path) == []

    def test_a_directory_is_not_a_program(self, planted, tmp_path, monkeypatch):
        monkeypatch.setenv("PATHEXT", ".EXE")
        (tmp_path / "git.EXE").mkdir()
        assert planted(tmp_path) == []

    def test_other_names_are_ignored(self, planted, tmp_path, monkeypatch):
        monkeypatch.setenv("PATHEXT", ".EXE")
        (tmp_path / "python.EXE").write_text("x", encoding="utf-8")
        assert planted(tmp_path) == []


class TestAdoBuildIdIsAnInteger:
    @pytest.mark.parametrize(
        "build_id", ["5", "5; rm", "--output", True, 0, -3, 5.5, [5], {"a": 1}]
    )
    def test_a_non_integer_id_fails_the_row_without_reaching_az(
        self, make_repo, fakes, scripts, capsys, build_id
    ):
        _ado(make_repo, fakes)
        fakes.rule("az", ["repos", "pr", "policy", "list"], _policies(("approved", build_id)))
        _show(fakes)
        code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "0")
        assert code == 1
        assert values(lines, "CHECK")[0].startswith("pipeline=FAIL pr=77")
        builds = [c for c in fakes.calls("az") if c[1:4] == ["pipelines", "build", "show"]]
        assert builds == []

    def test_an_integer_id_reaches_az_as_text(self, make_repo, fakes, scripts, capsys):
        _ado(make_repo, fakes)
        fakes.rule("az", ["repos", "pr", "policy", "list"], _policies(("approved", 12)))
        _show(fakes)
        fakes.rule(
            "az",
            ["pipelines", "build", "show"],
            {"stdout": json.dumps({"result": "succeeded", "sourceVersion": "m" * 40})},
        )
        code, _lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "0")
        assert code == 0
        build = [c for c in fakes.calls("az") if c[1:4] == ["pipelines", "build", "show"]][0]
        assert build[build.index("--id") + 1] == "12"


class TestPipelineKeepsRoomForLaterCalls:
    @pytest.fixture
    def github_pr(self, make_repo, fakes):
        make_repo(GITHUB)
        pr = {
            "number": 9,
            "state": "OPEN",
            "author": {"login": "me"},
            "url": "u",
            "baseRefName": "main",
        }
        fakes.rule("gh", ["pr", "view"], {"stdout": json.dumps(pr)})
        fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})
        _head(fakes, 9)
        fakes.rule("get_pr_checks", [], _checks({"RequiredState": "SUCCESS", "AllPassing": True}))

    @pytest.mark.parametrize(
        ("remaining", "wait", "expected"),
        [
            (10_000.0, "480", "300"),
            (540.0, "480", "300"),
            (200.0, "480", "80"),
            (190.0, "30", "30"),
        ],
    )
    def test_github_wait_is_capped_by_the_run_budget(
        self, github_pr, fakes, scripts, capsys, monkeypatch, remaining, wait, expected
    ):
        monkeypatch.setattr(scripts[0], "remaining_seconds", lambda: remaining)
        _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", wait)
        argv = fakes.calls("get_pr_checks")[0]
        assert argv[argv.index("--timeout-seconds") + 1] == expected

    @pytest.mark.parametrize("remaining", [120.0, 100.0, 1.0])
    def test_github_reads_once_when_the_reserve_uses_the_whole_budget(
        self, github_pr, fakes, scripts, capsys, monkeypatch, remaining
    ):
        monkeypatch.setattr(scripts[0], "remaining_seconds", lambda: remaining)
        _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "480")
        argv = fakes.calls("get_pr_checks")[0]
        assert "--wait" not in argv
        assert "--timeout-seconds" not in argv

    def test_ado_wait_still_keeps_the_same_reserve(
        self, make_repo, fakes, scripts, capsys, monkeypatch
    ):
        pipeline = scripts[2].pipeline_mod
        now = [0.0]
        slept: list[float] = []

        def sleep(seconds: float) -> None:
            slept.append(seconds)
            now[0] += seconds

        # A fake clock for the pipeline module only: the wait ends when it advances.
        monkeypatch.setattr(
            pipeline, "time", SimpleNamespace(monotonic=lambda: now[0], sleep=sleep)
        )
        monkeypatch.setattr(scripts[0], "remaining_seconds", lambda: 150.0)
        _ado(make_repo, fakes)
        fakes.rule("az", ["repos", "pr", "policy", "list"], _policies(("queued", 5)))
        _show(fakes)
        code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "480")
        assert code == 0
        assert values(lines, "CHECK")[0] == "pipeline=PENDING pr=77 1 of 1 queued or running"
        # 150 left less the 120 reserve is a 30 second wait: one poll, not 480 seconds.
        assert slept == [30.0]


class TestListsSayWhenTheyAreCut:
    def _failed(self, fakes, count: int) -> dict:
        names = [{"Name": f"check-{i}"} for i in range(count)]
        return _checks({"RequiredState": "FAILURE", "FailedRequiredChecks": names}, rc=1)

    @pytest.fixture
    def github_pr(self, make_repo, fakes):
        make_repo(GITHUB)
        pr = {
            "number": 9,
            "state": "OPEN",
            "author": {"login": "me"},
            "url": "u",
            "baseRefName": "main",
        }
        fakes.rule("gh", ["pr", "view"], {"stdout": json.dumps(pr)})
        fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})
        _head(fakes, 9)

    def test_github_names_beyond_ten_are_counted(self, github_pr, fakes, scripts, capsys):
        fakes.rule("get_pr_checks", [], self._failed(fakes, 12))
        _code, lines = _preflight(scripts, capsys, "--check", "pipeline")
        detail = values(lines, "CHECK")[0]
        assert "check-9" in detail
        assert "check-10" not in detail
        assert "failed=" in detail
        assert detail.count("(+2 more)") == 1

    def test_github_ten_names_are_not_marked(self, github_pr, fakes, scripts, capsys):
        fakes.rule("get_pr_checks", [], self._failed(fakes, 10))
        _code, lines = _preflight(scripts, capsys, "--check", "pipeline")
        assert "more)" not in values(lines, "CHECK")[0]

    def test_github_names_can_be_plain_strings(self, github_pr, fakes, scripts, capsys):
        data = {"RequiredState": "FAILURE", "FailedRequiredChecks": ["lint", "unit"]}
        fakes.rule("get_pr_checks", [], _checks(data, rc=1))
        _code, lines = _preflight(scripts, capsys, "--check", "pipeline")
        assert "failed=lint,unit" in values(lines, "CHECK")[0]

    def test_ado_failures_beyond_ten_are_counted(self, make_repo, fakes, scripts, capsys):
        _ado(make_repo, fakes)
        rows = [("rejected", None)] * 12
        fakes.rule("az", ["repos", "pr", "policy", "list"], _policies(*rows))
        _show(fakes)
        _code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "0")
        assert values(lines, "CHECK")[0].endswith("(+2 more)")

    def test_ado_three_failures_are_not_marked(self, make_repo, fakes, scripts, capsys):
        _ado(make_repo, fakes)
        fakes.rule("az", ["repos", "pr", "policy", "list"], _policies(*[("rejected", None)] * 3))
        _show(fakes)
        _code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "0")
        assert "more)" not in values(lines, "CHECK")[0]

    def test_ado_no_rows_after_publish_says_nothing_has_evaluated(
        self, make_repo, fakes, scripts, capsys
    ):
        _ado(make_repo, fakes, pr=None)
        _show(fakes)
        fakes.rule("az", ["repos", "pr", "policy", "list"], {"stdout": "[]"})
        _code, lines = _preflight(
            scripts, capsys, "--check", "pipeline", "--pr", "77", "--wait-seconds", "0"
        )
        assert values(lines, "CHECK")[0] == (
            "pipeline=PENDING pr=77 no blocking build policy has evaluated yet"
        )

    def test_ado_queued_rows_are_counted(self, make_repo, fakes, scripts, capsys):
        _ado(make_repo, fakes)
        fakes.rule(
            "az", ["repos", "pr", "policy", "list"], _policies(("queued", 5), ("running", 6))
        )
        _show(fakes)
        _code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "0")
        assert values(lines, "CHECK")[0] == "pipeline=PENDING pr=77 2 of 2 queued or running"


class TestPipelineArgumentsAreKeywordOnly:
    def test_a_positional_call_is_refused(self, make_repo, fakes, scripts):
        repo = make_repo(GITHUB)
        fakes.no_pr_github()
        ctx = scripts[1].detect(repo)
        pipeline = scripts[2].pipeline_mod
        with pytest.raises(TypeError):
            pipeline._github_pipeline(ctx, 9, False, 0)
        with pytest.raises(TypeError):
            pipeline._ado_pipeline(ctx, 9, 0, False)


class TestReviewedNoteOrder:
    @pytest.fixture
    def non_draft_pr(self, make_repo, fakes):
        make_repo(GITHUB)
        pr = {
            "number": 9,
            "state": "OPEN",
            "author": {"login": "me"},
            "url": "u",
            "baseRefName": "main",
        }
        fakes.rule("gh", ["pr", "view"], {"stdout": json.dumps(pr)})
        fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})

    def test_pass_leads_with_the_axes_then_the_refusal(self, non_draft_pr, fakes, scripts, capsys):
        fakes.marker(0, axes="analyst,qa")
        _code, lines = _preflight(scripts, capsys, "--check", "reviewed", "--draft")
        assert values(lines, "CHECK") == [
            "reviewed=PASS axes=analyst,qa; draft exemption refused: PR 9 is not a verified draft"
        ]

    def test_pass_without_draft_has_no_note(self, non_draft_pr, fakes, scripts, capsys):
        fakes.marker(0, axes="analyst,qa")
        _code, lines = _preflight(scripts, capsys, "--check", "reviewed")
        assert values(lines, "CHECK") == ["reviewed=PASS axes=analyst,qa"]

    def test_fail_keeps_the_refusal_first(self, non_draft_pr, fakes, scripts, capsys):
        fakes.marker(1)
        _code, lines = _preflight(scripts, capsys, "--check", "reviewed", "--draft")
        assert values(lines, "CHECK") == [
            "reviewed=FAIL draft exemption refused: PR 9 is not a verified draft; "
            "[FAIL] HEAD is not a review marker commit"
        ]

    def test_fail_without_draft_has_only_the_cause(self, non_draft_pr, fakes, scripts, capsys):
        fakes.marker(1)
        _code, lines = _preflight(scripts, capsys, "--check", "reviewed")
        assert values(lines, "CHECK") == ["reviewed=FAIL [FAIL] HEAD is not a review marker commit"]


class TestRunChecksReadsTheContextBase:
    def test_paths_check_uses_ctx_base(self, make_repo, fakes, scripts):
        repo = make_repo(GITHUB)
        git(repo, "update-ref", "refs/remotes/origin/release", "HEAD")
        fakes.no_pr_github()
        ctx = scripts[1].detect(repo, base="release")
        body = repo / "body.md"
        body.write_text("## Summary\n\nChanges the ship skill.\n", encoding="utf-8")
        result = scripts[0].Result("ship_pr.py", scripts[3].REASONS)
        scripts[3].run_checks(ctx, "feat(ship): add the driver", body, result)
        paths = [
            value for key, value in result.lines if key == "CHECK" and value.startswith("paths=")
        ]
        assert len(paths) == 1
        assert paths[0].startswith("paths=NOT-RUN origin/release has no path validator")

    def test_run_checks_takes_no_base_argument(self, scripts):
        import inspect

        names = list(inspect.signature(scripts[3].run_checks).parameters)
        assert names == ["ctx", "title", "body_file", "result"]


class TestBodyMarkerDrift:
    def test_marker_matches_the_prepare_helper_placeholder(self, scripts):
        spec = importlib.util.spec_from_file_location("prepare_pr_body_drift", REAL_PREPARE_PR_BODY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert scripts[3].checks_mod.BODY_MARKER == module._BODY_PLACEHOLDER.strip()
