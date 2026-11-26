"""Triggers, evidence, and entry points of ``check_skill_rewrite_evidence.py``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.validation.skill_rewrite_helpers import (
    _VALIDATION,
    EVID,
    MOVED,
    REF,
    SKILL,
    checker,
    commit,
    commit_evidence,
    driver_change,
    git,
    on_main,
    repo,
    results,
    run,
    skill_md,
    write,
)

__all__ = ["repo"]

import skill_rewrite_skills as skills


def _base_results(
    repo: Path,
    name: str,
    table: dict[str, tuple[str, str]] | None = None,
    **over: Any,
) -> None:
    """Commit a results file for the head surface on main, then rebuild feature."""
    write(repo, SKILL, skill_md("driver", body="\n".join(MOVED)))
    text = results(repo, table, **over)
    git(repo, "checkout", "--", SKILL)
    on_main(repo, {f"{EVID}/{name}": text}, "base evidence")


class TestNotGated:
    def test_no_skill_change(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, "README.md", "x\n")
        commit(repo, "readme")
        code, out = run(repo, capsys)
        assert code == 0
        assert "0 findings; 0 changed skills examined, 0 gated" in out

    def test_prose_edit_to_untagged_skill(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SKILL, skill_md(body="\n".join(MOVED) + "\nMore."))
        commit(repo, "prose")
        code, out = run(repo, capsys)
        assert code == 0
        assert "1 changed skills examined, 0 gated" in out

    def test_adding_reference_tag_alone(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SKILL, skill_md("reference", body="\n".join(MOVED)))
        commit(repo, "tag")
        code, out = run(repo, capsys)
        assert code == 0
        assert "1 changed skills examined, 0 gated" in out

    def test_new_script_with_doc_edit_is_not_a_move(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, "src/claude/skills/demo/scripts/tool.py", "print(1)\n")
        write(repo, SKILL, skill_md(body="Run tool.py."))
        commit(repo, "script")
        code, out = run(repo, capsys)
        assert code == 0
        assert "0 gated" in out


class TestTriggers:
    def test_driver_tag_without_evidence_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "metadata.shape changes from None to driver" in out
        assert "no results file under evals/skill-rewrites/demo/" in out

    def test_shape_change_from_reference_is_gated(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        git(repo, "checkout", "-q", "main")
        write(repo, SKILL, skill_md("reference", body="\n".join(MOVED)))
        commit(repo, "tag on main")
        git(repo, "checkout", "-q", "-B", "feature")
        write(repo, SKILL, skill_md(None, body="\n".join(MOVED)))
        commit(repo, "untag")
        code, out = run(repo, capsys)
        assert code == 1
        assert "changes from reference to None" in out

    def test_driver_reference_edit_is_gated(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        git(repo, "checkout", "-q", "main")
        write(repo, SKILL, skill_md("driver", body="\n".join(MOVED)))
        commit(repo, "driver on main")
        git(repo, "checkout", "-q", "-B", "feature")
        write(repo, REF, "Changed reference.\n")
        commit(repo, "ref edit")
        code, out = run(repo, capsys)
        assert code == 1
        assert "the prompt surface of a driver skill changes" in out

    def test_evidence_dir_declares_a_gated_change(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, f"{EVID}/notes.txt", "audit row G-1\n")
        commit(repo, "declare")
        code, out = run(repo, capsys)
        assert code == 1
        assert f"the branch changes {EVID}/" in out

    def test_moving_lines_into_references_is_gated(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SKILL, skill_md(body="See references."))
        write(repo, REF, "Reference.\n" + "\n".join(MOVED) + "\n")
        commit(repo, "move")
        code, out = run(repo, capsys)
        assert code == 1
        assert "4 lines move from SKILL.md into references/" in out

    def test_two_moved_lines_are_below_the_floor(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SKILL, skill_md(body="\n".join(MOVED[2:])))
        write(repo, REF, "Reference.\n" + "\n".join(MOVED[:2]) + "\n")
        commit(repo, "small move")
        assert run(repo, capsys)[0] == 0

    def test_deleted_driver_is_not_gated(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        git(repo, "checkout", "-q", "main")
        write(repo, SKILL, skill_md("driver"))
        commit(repo, "driver on main")
        git(repo, "checkout", "-q", "-B", "feature")
        git(repo, "rm", "-q", "-r", "src/claude/skills/demo")
        commit(repo, "delete")
        code, out = run(repo, capsys)
        assert code == 0, out
        assert "demo is deleted; nothing to evaluate" in out

    def test_deleting_a_skill_with_invalid_base_metadata_passes(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        on_main(repo, {SKILL: skill_md("drivr")}, "a typo on main")
        git(repo, "rm", "-q", "-r", "src/claude/skills/demo")
        commit(repo, "delete")
        code, out = run(repo, capsys)
        assert code == 0, out
        assert "demo is deleted; nothing to evaluate" in out

    def test_invalid_metadata_on_a_kept_skill_still_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        on_main(repo, {SKILL: skill_md("drivr")}, "a typo on main")
        write(repo, REF, "Reference, edited.\n")
        commit(repo, "edit the kept skill")
        code, out = run(repo, capsys)
        assert code == 1, out
        assert "metadata.shape is 'drivr'" in out

    def test_new_driver_is_not_gated(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, ".claude/skills/local/SKILL.md", skill_md("driver"))
        commit(repo, "new driver")
        code, out = run(repo, capsys)
        assert code == 0, out
        assert "local is new; it has no base to hold against" in out

    def test_rename_is_gated(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        git(repo, "mv", "src/claude/skills/demo", "src/claude/skills/renamed")
        commit(repo, "rename")
        code, out = run(repo, capsys)
        assert code == 1
        assert "renamed is gated: a new skill lands beside a deleted one" in out
        assert "tests/evals/renamed-scenarios.json does not exist" in out

    def test_repo_local_skill_dir(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        git(repo, "checkout", "-q", "main")
        write(repo, ".claude/skills/local/SKILL.md", skill_md())
        commit(repo, "local on main")
        git(repo, "checkout", "-q", "-B", "feature")
        write(repo, ".claude/skills/local/SKILL.md", skill_md("driver"))
        commit(repo, "local driver")
        code, out = run(repo, capsys)
        assert code == 1
        assert "local is gated" in out
        assert "tests/evals/local-scenarios.json does not exist" in out


class TestEvidence:
    def test_valid_evidence_passes(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 0, out
        assert "0 findings; 1 changed skills examined, 1 gated" in out

    def test_unreadable_json_blocks(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", "{not json")
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert "is not readable JSON" in out

    def test_missing_identity_field_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, base_commit=None))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert "identity.base_commit is missing" in out

    def test_hand_edited_pass_blocks(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Negative control: verdict PASS, per-scenario runs regress."""
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, {"S1": ("PPP", "FFF")}))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert "gate.verdict says 'PASS' but the recorded runs recompute to 'FAIL'" in out

    def test_stale_surface_blocks(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        write(repo, SKILL, skill_md("driver", body="Edited after the run."))
        commit(repo, "late edit")
        code, out = run(repo, capsys)
        assert code == 1
        assert "records the HEAD prompt surface sha256" in out

    def test_base_commit_on_branch_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        branch_sha = git(repo, "rev-parse", "HEAD")
        write(repo, f"{EVID}/run-1.json", results(repo, base_commit=branch_sha))
        commit(repo, "evidence")
        main_sha = git(repo, "rev-parse", "main")
        code, out = run(repo, capsys)
        assert code == 1
        assert f"identity.base_commit {branch_sha} is not an ancestor of {main_sha}" in out

    def test_first_run_sets_the_verdict(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, {"S1": ("PPP", "FFF")}, verdict="FAIL"))
        commit(repo, "first run")
        write(repo, f"{EVID}/run-2.json", results(repo))
        commit(repo, "second run")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json: recomputed gate is FAIL" in out
        assert "run-2.json" not in out

    def test_base_run_from_an_earlier_suite_is_not_the_first_run(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A base file for the same prompt but another scenario file must not decide."""
        _base_results(repo, "run-0.json", scenarios_sha256="1" * 64)
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "run for the new suite")
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_failed_base_run_for_this_suite_still_sets_the_verdict(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _base_results(repo, "run-0.json", verdict="FAIL", table={"S1": ("PPP", "FFF")})
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "later pass")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-0.json: recomputed gate is FAIL" in out
        assert "run-1.json" not in out

    def test_prompt_match_without_a_suite_match_reports_the_mismatch(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, scenarios_sha256="2" * 64))
        commit(repo, "run for another suite")
        code, out = run(repo, capsys)
        assert code == 1
        assert f"run-1.json: identity.scenarios_sha256 is '{'2' * 64}'" in out

    def test_retired_file_is_not_a_results_file(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/retired.json", json.dumps({"retired": []}))
        commit(repo, "only retired")
        code, out = run(repo, capsys)
        assert code == 1
        assert "no results file under" in out


class TestEntryPoints:
    def test_runner_load_failure_is_a_config_error(
        self, repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken() -> None:
            raise ImportError("no runner")

        monkeypatch.setattr(checker, "load_runner", broken)
        code, out = run(repo, capsys)
        assert code == 2
        assert "cannot load the eval runner: no runner" in out

    def test_unknown_base_commit_is_named(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, base_commit="f" * 40))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert f"identity.base_commit {'f' * 40} is not a commit in this clone" in out

    def test_not_gated_skill_is_logged(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SKILL, skill_md(body="\n".join(MOVED) + "\nMore."))
        commit(repo, "prose")
        assert "demo is not gated: no ADR-127 decision 7 trigger fired" in run(repo, capsys)[1]

    def test_gated_branch_may_not_edit_the_workflow(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, ".github/workflows/pr-validation.yml", "name: x\n")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence and workflow")
        assert "may not also change ['.github/workflows/pr-validation.yml']" in run(repo, capsys)[1]

    def test_gated_branch_may_not_edit_the_frontmatter_parser(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The parser decides metadata.shape, so it judges the change too."""
        driver_change(repo)
        write(repo, "scripts/hook_utilities/frontmatter_block.py", "# loosened\n")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence and parser")
        out = run(repo, capsys)[1]
        assert "may not also change ['scripts/hook_utilities/frontmatter_block.py']" in out

    def test_judge_paths_cover_every_imported_module(self) -> None:
        """Every repo module the check and the runner load is a judge path."""
        root = Path(checker.__file__).resolve().parents[2]
        probe = (
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, 'scripts/validation')\n"
            "import check_skill_rewrite_evidence as c, checks_common\n"
            "from skill_rewrite_evidence import load_runner\n"
            "load_runner()\n"
            "scripts = (Path.cwd() / 'scripts').resolve()\n"
            "for m in list(sys.modules.values()):\n"
            "    f = getattr(m, '__file__', None)\n"
            "    if f and Path(f).resolve().is_relative_to(scripts):\n"
            "        print(Path(f).resolve().relative_to(scripts.parent).as_posix())\n"
        )
        out = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=120,
        ).stdout.split()
        assert out, "the probe found no repo modules"
        missing = sorted(p for p in out if not p.startswith(checker._JUDGE_PATHS))
        assert missing == []

    def test_bad_base_ref_is_a_config_error(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The base is pinned to a commit before the diff, like the head."""
        code, out = run(repo, capsys, base="no-such-ref")
        assert code == 2
        assert "rev-parse --verify no-such-ref^{commit}" in out

    def test_base_ref_is_read_once(
        self, repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every later git read gets the pinned base commit, never the symbolic name."""
        pinned = git(repo, "rev-parse", "main")
        seen: list[tuple[str, ...]] = []
        real = checker.Git._run

        def spy(self: checker.Git, *args: str, **kwargs: Any) -> Any:
            seen.append(args)
            return real(self, *args, **kwargs)

        driver_change(repo)
        commit_evidence(repo)
        monkeypatch.setattr(checker.Git, "_run", spy)
        code, out = run(repo, capsys)
        assert code == 0, out
        names_main = [a for a in seen if any(x.split(":")[0].startswith("main") for x in a)]
        assert names_main == [("rev-parse", "--verify", "main^{commit}")], names_main
        assert any(pinned in a for a in seen)

    def test_bad_head_ref_is_a_config_error(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The head is pinned to a commit first, so a bad head fails before any read."""
        code = checker.main(["--repo-root", str(repo), "--base-ref", "main", "--head-ref", "nope"])
        assert code == 2
        assert "rev-parse --verify nope^{commit}" in capsys.readouterr().err

    def test_git_unavailable_is_a_config_error(
        self, repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class NoGit:
            TimeoutExpired = subprocess.TimeoutExpired

            @staticmethod
            def run(*_a: Any, **_k: Any) -> None:
                raise OSError("no git")

        monkeypatch.setattr(skills, "subprocess", NoGit)
        code, out = run(repo, capsys)
        assert code == 2
        assert "no git" in out

    def test_no_base_ref_is_a_config_error(
        self, repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import checks_common

        monkeypatch.setattr(checks_common, "_resolve_default_base_ref", lambda _r: None)
        assert checker.main(["--repo-root", str(repo)]) == 2
        assert "no base ref resolved" in capsys.readouterr().err

    def test_resolved_base_ref_is_used(
        self, repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import checks_common

        monkeypatch.setattr(checks_common, "_resolve_default_base_ref", lambda _r: "main")
        assert checker.main(["--repo-root", str(repo)]) == 0
        driver_change(repo)
        assert checker.main(["--repo-root", str(repo)]) == 1

    def test_script_entry_point_exits_nonzero_on_findings(self, repo: Path) -> None:
        driver_change(repo)
        script = _VALIDATION / "check_skill_rewrite_evidence.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--repo-root", str(repo), "--base-ref", "main"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "no results file under" in proc.stdout

    def test_abbreviated_flag_is_rejected(self) -> None:
        with pytest.raises(SystemExit) as exc:
            checker.main(["--base", "main"])
        assert exc.value.code == 2
