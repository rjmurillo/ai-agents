"""Tests for ``check_skill_rewrite_evidence.py`` (ADR-127 decision 9).

Each test builds a throwaway git repository with a ``main`` branch and a
``feature`` branch, then runs the check against ``main``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_skill_rewrite_evidence as checker
import skill_rewrite_evidence as sre

RUNNER = sre.load_runner()
SKILL = "src/claude/skills/demo/SKILL.md"
REF = "src/claude/skills/demo/references/detail.md"
SCEN = "tests/evals/demo-scenarios.json"
EVID = "evals/skill-rewrites/demo"
MOVED = [f"Moved line number {i} carries enough text to count as a move." for i in range(4)]


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "commit.gpgsign=false", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    ).stdout.strip()


def skill_md(shape: str | None = None, body: str = "Body.", tools: str = "Read") -> str:
    meta = f"metadata:\n  shape: {shape}\n" if shape else ""
    return f"---\nname: demo\nallowed-tools: {tools}\n{meta}---\n\n# Demo\n\n{body}\n"


def scenario_doc(n: int = 8) -> str:
    rows = [
        {"id": f"S{i}", "desc": "d", "input": "i", "expected_verdict": "GO"}
        for i in range(1, n + 1)
    ]
    return json.dumps({"scenarios": rows}, indent=2)


def write(root: Path, rel: str, text: str | bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


def commit(root: Path, msg: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", msg)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    write(root, SKILL, skill_md(body="\n".join(MOVED)))
    write(root, REF, "Reference.\n")
    write(root, SCEN, scenario_doc())
    write(root, "tests/skills/demo/test_demo.py", "def test_replaces():\n    pass\n")
    commit(root, "base")
    git(root, "checkout", "-q", "-b", "feature")
    return root


def surface_sha(root: Path) -> str:
    """The sha the runner records, computed by the runner's own loader."""
    text = RUNNER.load_prompt_surface_from_file(str(root / SKILL))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def results(root: Path, table: dict[str, tuple[str, str]] | None = None, **over: Any) -> str:
    table = table or {}
    verdict = over.pop("verdict", "PASS")
    scenarios = json.loads((root / SCEN).read_text(encoding="utf-8"))["scenarios"]

    def per_run(pattern: str) -> list[dict[str, Any]]:
        return [{"verdict": "GO" if c == "P" else "STOP", "model_used": "m"} for c in pattern]

    rows = {"before": [], "after": []}
    for s in scenarios:
        b, a = table.get(s["id"], ("PPP", "PPP"))
        rows["before"].append({"scenario_id": s["id"], "per_run": per_run(b)})
        rows["after"].append({"scenario_id": s["id"], "per_run": per_run(a)})
    identity = {
        "prompt_path": SKILL,
        "prompt_surface_sha256": surface_sha(root),
        "scenarios_path": SCEN,
        "scenarios_sha256": hashlib.sha256((root / SCEN).read_bytes()).hexdigest(),
        "base_ref": "main",
        "base_commit": git(root, "rev-parse", "main"),
        "model": "m",
    }
    identity.update(over)
    doc = {
        "model": "m",
        "identity": identity,
        "runs_per_scenario": 3,
        "security_critical": False,
        "gate": {"verdict": verdict},
        "detail": rows,
    }
    return json.dumps(doc)


def run(root: Path, capsys: pytest.CaptureFixture[str], base: str = "main") -> tuple[int, str]:
    code = checker.main(["--repo-root", str(root), "--base-ref", base])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def driver_change(root: Path) -> None:
    """Make the skill a driver in its own commit, after the scenario commit."""
    write(root, SKILL, skill_md("driver", body="\n".join(MOVED)))
    commit(root, "driver")


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
        code, out = run(repo, capsys)
        assert code == 1
        assert f"identity.base_commit {branch_sha} is not an ancestor of main" in out

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

    def test_retired_file_is_not_a_results_file(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/retired.json", json.dumps({"retired": []}))
        commit(repo, "only retired")
        code, out = run(repo, capsys)
        assert code == 1
        assert "no results file under" in out


class TestAppendOnly:
    def test_editing_a_results_file_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, {"S1": ("PPP", "FFF")}, verdict="FAIL"))
        commit(repo, "failed run")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "overwrite")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json is edited or deleted in" in out

    def test_deleting_a_results_file_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, {"S1": ("PPP", "FFF")}, verdict="FAIL"))
        commit(repo, "failed run")
        git(repo, "rm", "-q", f"{EVID}/run-1.json")
        write(repo, f"{EVID}/run-2.json", results(repo))
        commit(repo, "swap")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json is edited or deleted in" in out

    def test_retired_file_may_change(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/retired.json", json.dumps({"retired": []}))
        commit(repo, "retired")
        write(repo, f"{EVID}/retired.json", json.dumps({"retired": [], "note": "x"}))
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_merge_resolution_edit_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, {"S1": ("PPP", "FFF")}, verdict="FAIL"))
        commit(repo, "failed run")
        git(repo, "checkout", "-q", "-b", "side", "HEAD~1")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "side run")
        git(repo, "checkout", "-q", "feature")
        subprocess.run(
            ["git", "-C", str(repo), "-c", "commit.gpgsign=false", "merge", "-q", "side"],
            capture_output=True,
            check=False,
            timeout=60,
        )
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "resolve")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json is added again in" in out

    def test_runner_edit_in_a_gated_branch_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, "scripts/eval/eval-prompt-change.py", "# lenient\n")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence and runner")
        code, out = run(repo, capsys)
        assert code == 1
        assert "a gated change may not also change ['scripts/eval/eval-prompt-change.py']" in out

    def test_runner_edit_alone_is_not_gated(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, "scripts/eval/eval-prompt-change.py", "# change\n")
        commit(repo, "runner")
        assert run(repo, capsys)[0] == 0

    def test_label_flip_blocks(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        doc = json.loads(scenario_doc())
        doc["scenarios"][0]["expected_verdict"] = "STOP"
        write(repo, SCEN, json.dumps(doc))
        commit(repo, "scenario commit")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert "scenario S1 changes expected_verdict from 'GO' to 'STOP'" in out

    def test_head_ref_reads_the_named_commit(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        tip = commit(repo, "evidence")
        write(repo, SKILL, skill_md("driver", body="after the run"))
        commit(repo, "late edit")
        code = checker.main(["--repo-root", str(repo), "--base-ref", "main", "--head-ref", tip])
        assert code == 0, capsys.readouterr().out
        assert run(repo, capsys)[0] == 1


class TestScenarioFile:
    def test_missing_scenario_file(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        git(repo, "rm", "-q", SCEN)
        commit(repo, "drop scenarios")
        driver_change(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert f"{SCEN} does not exist" in out

    def test_invalid_scenario_json(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, SCEN, "{")
        commit(repo, "break")
        driver_change(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "is not valid scenario JSON" in out

    def test_scenario_without_expected_verdict(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SCEN, json.dumps({"scenarios": [{"id": "S1"}]}))
        commit(repo, "thin")
        driver_change(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "has a scenario with no id or expected_verdict" in out

    def test_scenario_edit_after_surface_commit_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        doc = json.loads(scenario_doc())
        doc["scenarios"][0]["desc"] = "changed"
        write(repo, SCEN, json.dumps(doc))
        commit(repo, "late scenario edit")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert "changes in or after the first prompt-surface commit" in out

    def test_scenario_commit_before_surface_is_allowed(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SCEN, scenario_doc(9))
        commit(repo, "scenario commit")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_dropped_scenario_without_retired_file(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._base_with_nine(repo)
        write(repo, SCEN, scenario_doc(8))
        commit(repo, "drop S9")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert "scenarios ['S9'] were dropped" in out

    @pytest.mark.parametrize(
        ("retired", "message"),
        [
            ("[1]", "is not valid JSON with a 'retired' list"),
            ("{", "is not valid JSON with a 'retired' list"),
            (json.dumps({"retired": [{"scenario": "S9"}]}), "has no replacing test"),
            (
                json.dumps({"retired": [{"scenario": "S9", "test": "tests/nope.py::test_x"}]}),
                "does not exist at HEAD",
            ),
            (
                json.dumps(
                    {"retired": [{"scenario": "S9", "test": "tests/skills/demo/test_demo.py::t"}]}
                ),
                "does not exist at HEAD",
            ),
        ],
    )
    def test_retired_file_errors(
        self, repo: Path, capsys: pytest.CaptureFixture[str], retired: str, message: str
    ) -> None:
        self._base_with_nine(repo)
        write(repo, SCEN, scenario_doc(8))
        write(repo, f"{EVID}/retired.json", retired)
        commit(repo, "drop S9")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert message in out

    def test_retired_with_real_test_passes(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._base_with_nine(repo)
        write(repo, SCEN, scenario_doc(8))
        test = "tests/skills/demo/test_demo.py::TestX::test_replaces"
        write(
            repo,
            f"{EVID}/retired.json",
            json.dumps({"retired": [{"scenario": "S9", "test": test}]}),
        )
        commit(repo, "drop S9")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 0, out

    @pytest.mark.parametrize("broken", ["{", json.dumps({"scenarios": 3})])
    def test_unreadable_base_scenarios_drop_nothing(
        self, repo: Path, capsys: pytest.CaptureFixture[str], broken: str
    ) -> None:
        git(repo, "checkout", "-q", "main")
        write(repo, SCEN, broken)
        commit(repo, "broken on main")
        git(repo, "checkout", "-q", "-B", "feature")
        write(repo, SCEN, scenario_doc())
        commit(repo, "scenario commit")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_scenario_file_new_on_branch(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        git(repo, "checkout", "-q", "main")
        git(repo, "rm", "-q", SCEN)
        commit(repo, "no scenarios on main")
        git(repo, "checkout", "-q", "-B", "feature")
        write(repo, SCEN, scenario_doc())
        commit(repo, "scenario commit")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 0, out

    @staticmethod
    def _base_with_nine(repo: Path) -> None:
        git(repo, "checkout", "-q", "main")
        write(repo, SCEN, scenario_doc(9))
        commit(repo, "nine on main")
        git(repo, "checkout", "-q", "-B", "feature")


class TestFrontmatter:
    def test_invalid_shape_value(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, SKILL, skill_md("drivr"))
        commit(repo, "typo")
        code, out = run(repo, capsys)
        assert code == 1
        assert "metadata.shape is 'drivr'; it must be driver or reference" in out

    def test_invalid_yaml(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, SKILL, "---\nname: [unclosed\n---\n\nBody\n")
        commit(repo, "bad yaml")
        code, out = run(repo, capsys)
        assert code == 1
        assert "frontmatter is not valid YAML" in out

    def test_no_frontmatter_is_untagged(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SKILL, "# Demo\n\nNo frontmatter.\n")
        commit(repo, "plain")
        assert run(repo, capsys)[0] == 0

    def test_non_utf8_surface(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, REF, b"\xff\xfe bad bytes\n")
        commit(repo, "binary")
        code, out = run(repo, capsys)
        assert code == 1
        assert "prompt surface is not UTF-8" in out

    def test_unknown_evidence_dir(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, "evals/skill-rewrites/ghost/run.json", "{}")
        commit(repo, "ghost")
        code, out = run(repo, capsys)
        assert code == 1
        assert "evals/skill-rewrites/ghost/ names no skill" in out

    def test_unknown_scenario_name_is_ignored(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, "tests/evals/critic-scenarios.json", scenario_doc())
        commit(repo, "agent scenarios")
        code, out = run(repo, capsys)
        assert code == 0
        assert "0 changed skills examined" in out


class TestReferenceGrants:
    @pytest.mark.parametrize(
        "tools",
        [
            "Read, Bash",
            "Read, Bash(*)",
            "Bash(git push:*)",
            "Bash(git -C . push:*)",
            "Bash(git commit:*)",
            "Bash(git:*)",
            "Bash(git branch:*)",
            "Bash(gh:*)",
            "Bash(gh pr create:*)",
            "Bash(python3:*)",
            "Bash(python3.14:*)",
            "Bash(uv:*)",
            "Bash(uv run:*)",
            "Bash(env gh:*)",
            "Bash(python3 -c:*)",
            "Bash(python3:*/skills/github/scripts/*)",
            "Bash(python3 .claude/skills/github/scripts/pr/*)",
            "Bash(python3:*/skills/demo/scripts/* && git push)",
            "Bash(python3:-I */pr/new_pr.py*)",
            "mcp__github__create_pull_request",
            "Bash(python3 .claude/skills/demo/scripts/../../github/scripts/pr/merge_pr.py)",
            "Bash(ls && git push:*)",
            "Bash(ls;git push)",
            "Bash(date | sh)",
            "Bash(ls $(git push))",
            "Bash(git grep:*)",
            "Bash(git diff --output=/tmp/x:*)",
            "Bash(git log --ext-diff:*)",
            "mcp__serena__find_and_replace",
            "Write, Bash(python3:*/skills/demo/scripts/*)",
            "Edit, Bash(git diff:*)",
            "Read(secrets/*)",
        ],
    )
    def test_reference_skill_may_not_write(
        self, repo: Path, capsys: pytest.CaptureFixture[str], tools: str
    ) -> None:
        write(repo, SKILL, skill_md("reference", body="\n".join(MOVED), tools=tools))
        commit(repo, "tag")
        code, out = run(repo, capsys)
        assert code == 1
        assert "shape is reference but allowed-tools grants" in out

    @pytest.mark.parametrize(
        "tools",
        [
            "Read, Grep, Glob, Skill, Task, Write",
            "Bash(git diff:*), Bash(git merge-base:*), Bash(git branch --show-current)",
            "Bash(python3:*/skills/demo/scripts/*)",
            "Bash(uv run --frozen python -I */skills/demo/scripts/check.py*)",
            "Bash(mkdir:-p .project-toolkit/scratch)",
            "mcp__serena__find_symbol, mcp__github__get_file_contents",
        ],
    )
    def test_read_only_grants_pass(
        self, repo: Path, capsys: pytest.CaptureFixture[str], tools: str
    ) -> None:
        write(repo, SKILL, skill_md("reference", body="\n".join(MOVED), tools=tools))
        commit(repo, "tag")
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_list_form_grants_are_read(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        text = (
            "---\nname: demo\nallowed-tools:\n  - Read\n  - Bash(*)\n"
            "metadata:\n  shape: reference\n---\n\n" + "\n".join(MOVED) + "\n"
        )
        write(repo, SKILL, text)
        commit(repo, "list form")
        code, out = run(repo, capsys)
        assert code == 1
        assert "grants Bash(*)" in out

    def test_non_string_grants_fail_closed(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        text = "---\nname: demo\nallowed-tools: {Bash: yes}\n---\n\nBody\n"
        write(repo, SKILL, text)
        commit(repo, "mapping")
        code, out = run(repo, capsys)
        assert code == 1
        assert "allowed-tools is a dict, not a string or list" in out

    def test_other_skill_script_fails(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        tools = "Bash(python3:*/skills/other/scripts/*)"
        write(repo, SKILL, skill_md("reference", body="\n".join(MOVED), tools=tools))
        commit(repo, "tag")
        assert run(repo, capsys)[0] == 1

    def test_grants_on_driver_are_not_checked_here(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SKILL, skill_md("driver", body="\n".join(MOVED), tools="Bash(*)"))
        commit(repo, "driver")
        assert "shape is reference" not in run(repo, capsys)[1]


class TestEntryPoints:
    def test_bad_base_ref_is_a_config_error(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out = run(repo, capsys, base="no-such-ref")
        assert code == 2
        assert "git merge-base no-such-ref HEAD exited" in out

    def test_git_unavailable_is_a_config_error(
        self, repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class NoGit:
            TimeoutExpired = subprocess.TimeoutExpired

            @staticmethod
            def run(*_a: Any, **_k: Any) -> None:
                raise OSError("no git")

        monkeypatch.setattr(checker, "subprocess", NoGit)
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


def test_surface_matches_runner_loader(repo: Path) -> None:
    """The check hashes the same text the runner feeds the model."""
    write(repo, "src/claude/skills/demo/references/a.md", "First.\r\nCRLF line.\n")
    commit(repo, "refs")
    side = checker.read_skill(checker.Git(repo), "HEAD", "demo")
    assert side.surface == RUNNER.load_prompt_surface_from_file(str(repo / SKILL))
