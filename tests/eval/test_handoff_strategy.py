"""Tests for the stalled-investigation strategy comparison (issue #7350)."""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.eval._control_ablation_history_support import (
    FIXED,
    HistoryRepo,
    make_historical_task,
    make_history_repo,
)

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
REPO_ROOT = EVAL_DIR.parents[1]
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _control_ablation as ablation  # noqa: E402
import _control_ablation_claude as claude_run  # noqa: E402
import _control_ablation_tasks as ablation_tasks  # noqa: E402
import _handoff_strategy as hs  # noqa: E402
import eval_handoff_strategy as cli  # noqa: E402
from _runtime_harness import REAL_HOME_ENV  # noqa: E402

MODEL = "claude-sonnet-5-5"
REPRO = (
    "import unittest\n\nfrom calc import half\n\n\n"
    "class TestRepro(unittest.TestCase):\n"
    "    def test_odd(self):\n"
    "        self.assertIn(half(3), (1.5, 2))\n"
)
GREEN_REPRO = REPRO.replace("(1.5, 2)", "(1, 1.5, 2)")
BRIEF = {
    "symptom": "half(3) returns 1.",
    "rejected_hypotheses": "Rounding was tried and shipped.",
    "non_goals": "Do not change the tests.",
}


@pytest.fixture
def repo(tmp_path: Path) -> HistoryRepo:
    return make_history_repo(tmp_path / "history")


def v3_task(repo: HistoryRepo, **overrides: Any) -> dict[str, Any]:
    task = make_historical_task(repo, acceptance=["{python}", "-m", "unittest", "tests.test_repro"])
    task.pop("case")
    task.update(
        visible_files={"tests/test_repro.py": REPRO},
        withheld_edits=[],
        brief=copy.deepcopy(BRIEF),
        stall=True,
    )
    task.update(overrides)
    return task


def corpus(repo: HistoryRepo, *tasks: dict[str, Any]) -> hs.HandoffCorpus:
    doc = {"schema_version": 3, "tasks": list(tasks) or [v3_task(repo)]}
    return hs.load_tasks(doc, repo.root, sys.executable)


def _mask(call: list[str]) -> str:
    return re.sub(r"\d+\.\d+s", "Ns", " ".join(call))


class FakeRunner:
    """Investigator launches carry `--append-system-prompt`; producers do not."""

    def __init__(
        self,
        task: ablation_tasks.Task,
        *,
        fix_on_round: int | None = 0,
        kind: str = "known_good",
        investigator_writes: bool = False,
        read_path: str | None = None,
    ) -> None:
        self.task, self.fix_on_round, self.kind = task, fix_on_round, kind
        self.investigator_writes, self.read_path = investigator_writes, read_path
        self.calls: list[list[str]] = []
        self.producers = 0

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        args = [str(a) for a in argv]
        self.calls.append(args)
        workspace = Path(str(kwargs["cwd"]))
        model = args[args.index("--model") + 1]
        blocks: list[dict[str, object]] = []
        if self.read_path:
            blocks.append(
                {"type": "tool_use", "name": "Read", "input": {"file_path": self.read_path}}
            )
        if "--append-system-prompt" in args:
            reply = "findings"
            if self.investigator_writes:
                (workspace / "calc.py").write_text("# edited\n", encoding="utf-8")
        else:
            reply = "done"
            if self.fix_on_round is not None and self.producers >= self.fix_on_round:
                for rel, text in self.task.controls[self.kind].files.items():
                    (workspace / rel).write_text(text, encoding="utf-8")
            self.producers += 1
        events = [
            {"type": "system", "subtype": "init", "model": model},
            {"type": "assistant", "message": {"content": blocks}},
            {"type": "result", "subtype": "success", "result": reply, "total_cost_usd": 0.01},
        ]
        stdout = "\n".join(json.dumps(e) for e in events) + "\n"
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")


def run(
    repo: HistoryRepo,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arm: str = hs.ARM_HANDOFF,
    markers: tuple[str, ...] = (),
    **fake: Any,
) -> tuple[dict[str, Any], FakeRunner]:
    monkeypatch.setenv(REAL_HOME_ENV, "1")
    loaded = corpus(repo)
    task = loaded.tasks[0]
    runner = FakeRunner(task, **fake)
    control = ablation.ControlFiles(name="full", files={"AGENTS.md": "# a\n"}, context_bytes=4)
    entry, _record, _patch, _cell = cli.run_cell(
        task,
        loaded.briefs[task.id],
        arm,
        0,
        control,
        role="ROLE TEXT",
        model=MODEL,
        effort=None,
        harness_version="test",
        timeout=30.0,
        workspace_root=tmp_path / "ws",
        runner=runner,
        markers=markers,
    )
    return entry, runner


class TestTextEdits:
    def test_an_exact_once_edit_applies(self) -> None:
        out = hs.apply_text_edits({"a": "x y"}, [{"path": "a", "old": "y", "new": "z"}], "e")
        assert out == {"a": "x z"}

    @pytest.mark.parametrize(
        ("files", "old"),
        [({"a": "x"}, "missing"), ({"a": "yy"}, "y"), ({"b": "y"}, "y")],
    )
    def test_a_missing_ambiguous_or_unknown_target_is_refused(
        self, files: dict[str, str], old: str
    ) -> None:
        with pytest.raises(ablation_tasks.ControlAblationConfigError):
            hs.apply_text_edits(files, [{"path": "a", "old": old, "new": "z"}], "e")

    def test_an_edit_missing_a_key_is_refused(self) -> None:
        with pytest.raises(ablation_tasks.ControlAblationConfigError):
            hs.apply_text_edits({"a": "x"}, [{"path": "a", "old": "x"}], "e")


class TestLoader:
    def test_visible_files_join_the_seed_and_the_brief_is_kept(self, repo: HistoryRepo) -> None:
        loaded = corpus(repo)
        task = loaded.tasks[0]
        assert task.setup_files["tests/test_repro.py"] == REPRO
        assert loaded.briefs[task.id].symptom == BRIEF["symptom"]
        assert loaded.stall[task.id] is True

    def test_withheld_text_edit_is_applied_to_the_withheld_file(self, repo: HistoryRepo) -> None:
        edit = [{"path": "tests/test_withheld.py", "old": "def test_odd", "new": "def test_odd2"}]
        task = corpus(repo, v3_task(repo, withheld_edits=edit)).tasks[0]
        assert "def test_odd2" in task.followup_files["tests/test_withheld.py"]

    def test_tasks_may_have_different_base_commits(self, repo: HistoryRepo) -> None:
        second = v3_task(repo, id="other")
        second["source"] = {**second["source"], "base_sha": repo.fix_sha}
        second["controls"] = copy.deepcopy(second["controls"])
        second["controls"]["known_bad"]["edits"][0]["old"] = "n / 2"
        loaded = corpus(repo, v3_task(repo), second)
        assert len({s.base_sha for s in loaded.sources.values()}) == 2

    @pytest.mark.parametrize("missing", ["visible_files", "withheld_edits", "brief", "stall"])
    def test_a_task_without_an_extra_key_is_refused(self, repo: HistoryRepo, missing: str) -> None:
        task = v3_task(repo)
        del task[missing]
        with pytest.raises(ablation_tasks.ControlAblationConfigError):
            corpus(repo, task)

    def test_a_non_boolean_stall_flag_is_refused(self, repo: HistoryRepo) -> None:
        with pytest.raises(ablation_tasks.ControlAblationConfigError):
            corpus(repo, v3_task(repo, stall="yes"))

    def test_a_brief_missing_a_field_is_refused(self, repo: HistoryRepo) -> None:
        with pytest.raises(ablation_tasks.ControlAblationConfigError):
            corpus(repo, v3_task(repo, brief={"symptom": "x"}))

    def test_a_wrong_schema_version_is_refused(self, repo: HistoryRepo) -> None:
        with pytest.raises(ablation_tasks.ControlAblationConfigError):
            hs.load_tasks({"schema_version": 2, "tasks": []}, repo.root, sys.executable)

    def test_the_shipped_task_file_loads_against_this_repository(self) -> None:
        path = EVAL_DIR / "examples" / "handoff-strategy-tasks.json"
        try:
            loaded = hs.load_tasks(json.loads(path.read_text("utf-8")), REPO_ROOT, sys.executable)
        except ablation_tasks.ControlAblationConfigError as exc:
            pytest.skip(f"base commits are not in this clone: {exc}")
        assert [t.id for t in loaded.tasks] == [
            "issue-7328-mypy-symlink-run-mypy",
            "issue-6169-codex-login-stderr",
        ]
        assert sorted(loaded.stall.values()) == [False, True]


class TestRolesAndPrompts:
    @pytest.mark.parametrize("arm", hs.ARMS)
    def test_role_text_is_the_existing_definition_without_frontmatter(self, arm: str) -> None:
        text = hs.role_text(REPO_ROOT, arm)
        assert not text.startswith("---")
        assert text.lstrip().startswith("# ")

    def test_the_two_arms_differ_only_in_the_instruction(self, repo: HistoryRepo) -> None:
        loaded = corpus(repo)
        task = loaded.tasks[0]
        facts = hs.facts_block(task, loaded.briefs[task.id], "red output")
        a = hs.investigator_prompt(hs.ARM_CONTINUE, facts, "", "")
        b = hs.investigator_prompt(hs.ARM_HANDOFF, facts, "", "")
        assert a.replace(hs.INSTRUCTION_CONTINUE, "") == b.replace(hs.INSTRUCTION_HANDOFF, "")
        assert hs.producer_prompt(facts, "f", "") == hs.producer_prompt(facts, "f", "")

    def test_facts_carry_no_withheld_text_or_fix_reference(self, repo: HistoryRepo) -> None:
        loaded = corpus(repo)
        task = loaded.tasks[0]
        facts = hs.facts_block(task, loaded.briefs[task.id], "red output")
        assert "test_withheld" not in facts
        assert repo.fix_sha[:7] not in facts
        assert "python3 -m unittest tests.test_repro" in facts

    def test_repair_prompts_add_prior_findings_and_feedback(self) -> None:
        text = hs.investigator_prompt(hs.ARM_HANDOFF, "F", "earlier", "still red")
        assert "YOUR PRIOR FINDINGS:\nearlier" in text
        assert "still red" in text
        assert "still red" in hs.producer_prompt("F", "x", "still red")


class TestRunCell:
    def test_a_first_attempt_fix_uses_no_repair_turn(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry, runner = run(repo, tmp_path, monkeypatch, fix_on_round=0)
        assert entry["accepted"] is True
        assert entry["repair_turns"] == 0
        assert entry["base_acceptance_exit"] != 0
        assert len(runner.calls) == 2
        assert entry["human_correction_minutes"] is None

    def test_a_fix_on_the_second_round_counts_one_repair_turn(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry, runner = run(repo, tmp_path, monkeypatch, fix_on_round=1)
        assert entry["accepted"] is True
        assert entry["repair_turns"] == 1
        assert len(runner.calls) == 4

    def test_a_task_never_fixed_spends_the_whole_budget_and_fails(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry, runner = run(repo, tmp_path, monkeypatch, fix_on_round=None)
        assert entry["accepted"] is False
        assert entry["repair_turns"] == hs.REPAIR_ROUNDS
        assert len(runner.calls) == 2 * (hs.REPAIR_ROUNDS + 1)
        assert entry["cost_usd"] == pytest.approx(0.06)

    def test_a_visible_pass_that_fails_the_held_out_check_is_a_regression(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry, _ = run(repo, tmp_path, monkeypatch, kind="known_bad")
        assert entry["acceptance_exit"] == 0
        assert entry["heldout_exit"] != 0
        assert entry["regression"] is True
        assert entry["accepted"] is False

    def test_an_investigator_that_writes_invalidates_the_cell(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry, _ = run(repo, tmp_path, monkeypatch, investigator_writes=True)
        assert entry["valid"] is False
        assert entry["invalid_reason"] == "investigator changed the workspace"
        assert entry["accepted"] is False

    def test_a_tool_call_naming_withheld_evidence_invalidates_the_cell(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry, _ = run(
            repo,
            tmp_path,
            monkeypatch,
            markers=("tests/test_withheld.py",),
            read_path="/x/tests/test_withheld.py",
        )
        assert entry["valid"] is False
        assert entry["accepted"] is False

    def test_a_green_reproduction_on_the_base_is_refused(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        green = v3_task(repo, visible_files={"tests/test_repro.py": GREEN_REPRO})
        monkeypatch.setenv(REAL_HOME_ENV, "1")
        loaded = corpus(repo, green)
        task = loaded.tasks[0]
        control = ablation.ControlFiles(name="full", files={}, context_bytes=0)
        with pytest.raises(claude_run.HarnessFailureError, match="green on the base"):
            cli.run_cell(
                task,
                loaded.briefs[task.id],
                hs.ARM_HANDOFF,
                0,
                control,
                role="R",
                model=MODEL,
                effort=None,
                harness_version="t",
                timeout=5.0,
                workspace_root=tmp_path / "ws",
                runner=FakeRunner(task),
                markers=(),
            )

    def test_the_arms_differ_in_role_text_and_instruction_only(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, a = run(repo, tmp_path, monkeypatch, arm=hs.ARM_CONTINUE)
        cli.batch.remove_cell(cli.cell_dir(tmp_path / "ws", "half-odd", 0))
        _, b = run(repo, tmp_path, monkeypatch, arm=hs.ARM_HANDOFF)
        # Producer argv is identical, prompt included: the traceback path names no arm.
        # The reproduction's timing line varies per run, so compare with it masked.
        assert _mask(a.calls[1]) == _mask(b.calls[1])
        assert hs.ARM_CONTINUE not in str(cli.cell_dir(tmp_path, "half-odd", 0))
        assert hs.ARM_HANDOFF not in str(cli.cell_dir(tmp_path, "half-odd", 0))
        inv_a, inv_b = a.calls[0], b.calls[0]
        tools = inv_a[inv_a.index("--tools") + 1]
        assert tools == hs.INVESTIGATOR_TOOLS and "Edit" not in tools and "Write" not in tools
        assert inv_a[inv_a.index("--allowedTools") + 1] == hs.INVESTIGATOR_ALLOWED
        assert inv_a[inv_a.index("--print") + 1] != inv_b[inv_b.index("--print") + 1]

    def test_effort_is_passed_to_every_launch_when_set(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(REAL_HOME_ENV, "1")
        loaded = corpus(repo)
        task = loaded.tasks[0]
        runner = FakeRunner(task)
        cli.run_cell(
            task,
            loaded.briefs[task.id],
            hs.ARM_HANDOFF,
            0,
            ablation.ControlFiles(name="full", files={}, context_bytes=0),
            role="R",
            model=MODEL,
            effort="medium",
            harness_version="t",
            timeout=5.0,
            workspace_root=tmp_path / "ws",
            runner=runner,
            markers=(),
        )
        assert all(c[c.index("--effort") + 1] == "medium" for c in runner.calls)

    def test_the_report_hashes_prompts_instead_of_embedding_them(self) -> None:
        argv = [
            "claude",
            "--print",
            "SECRET PROMPT",
            "--append-system-prompt",
            "ROLE",
            "--model",
            "m",
        ]
        shown = cli._argv_summary(argv)
        assert "SECRET PROMPT" not in shown and "ROLE" not in shown
        assert shown[-1] == "m"


class TestClaudeArgvSeam:
    def test_extra_args_default_leaves_the_frozen_argv_unchanged(self) -> None:
        assert claude_run.claude_argv("m", "p") == claude_run.claude_argv("m", "p", extra_args=())

    def test_extra_args_append_after_the_fixed_flags(self) -> None:
        argv = claude_run.claude_argv("m", "p", extra_args=["--effort", "low"])
        assert argv[-2:] == ["--effort", "low"]


class TestCli:
    def test_dry_run_passes_on_a_real_fix_and_a_plausible_wrong_fix(
        self, repo: HistoryRepo, tmp_path: Path
    ) -> None:
        tasks = tmp_path / "tasks.json"
        tasks.write_text(json.dumps({"schema_version": 3, "tasks": [v3_task(repo)]}), "utf-8")
        # The loader reads commits from the runner's repository, so point it at the fixture.
        original = cli.REPO_ROOT
        cli.REPO_ROOT = repo.root
        try:
            code = cli.main(
                [
                    "--dry-run",
                    "--tasks",
                    str(tasks),
                    "--workspace-root",
                    str(tmp_path / "w"),
                    "--output-dir",
                    str(tmp_path / "out"),
                ]
            )
        finally:
            cli.REPO_ROOT = original
        report = json.loads((tmp_path / "out" / "report.json").read_text("utf-8"))
        assert code == 0
        assert report["base_red"] is True
        assert report["known_good_accepted_durable"] == 1
        assert report["known_bad_accepted_durable"] == 0

    def test_dry_run_fails_when_the_reproduction_is_green_on_the_base(
        self, repo: HistoryRepo, tmp_path: Path
    ) -> None:
        green = v3_task(repo, visible_files={"tests/test_repro.py": GREEN_REPRO})
        tasks = tmp_path / "tasks.json"
        tasks.write_text(json.dumps({"schema_version": 3, "tasks": [green]}), "utf-8")
        original = cli.REPO_ROOT
        cli.REPO_ROOT = repo.root
        try:
            code = cli.main(
                [
                    "--dry-run",
                    "--tasks",
                    str(tasks),
                    "--workspace-root",
                    str(tmp_path / "w"),
                    "--output-dir",
                    str(tmp_path / "out"),
                ]
            )
        finally:
            cli.REPO_ROOT = original
        assert code == cli.EXIT_LOGIC

    def test_a_malformed_task_file_exits_2(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"schema_version": 2, "tasks": []}), "utf-8")
        code = cli.main(
            [
                "--dry-run",
                "--tasks",
                str(bad),
                "--workspace-root",
                str(tmp_path / "w"),
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
        assert code == cli.EXIT_CONFIG

    def test_more_than_three_repeats_is_refused_before_any_launch(
        self, repo: HistoryRepo, tmp_path: Path
    ) -> None:
        tasks = tmp_path / "tasks.json"
        tasks.write_text(json.dumps({"schema_version": 3, "tasks": [v3_task(repo)]}), "utf-8")
        code = cli.main(
            [
                "--tasks",
                str(tasks),
                "--repeats",
                "4",
                "--real-home",
                "--workspace-root",
                str(tmp_path / "w"),
                "--output-dir",
                str(tmp_path / "out"),
            ],
            runner=lambda *a, **k: pytest.fail("a launch happened"),
        )
        assert code == cli.EXIT_CONFIG


def test_fixed_source_is_what_the_fake_installs(repo: HistoryRepo) -> None:
    task = corpus(repo).tasks[0]
    assert task.controls["known_good"].files["calc.py"] == FIXED
