"""Tests for the CLI exit-contract ratchet (issue #4068).

ADR-006 extraction turns a `set -e` shell failure into a Python sentinel that
no caller converts into a nonzero exit. Every test that missed this asserted on
a helper's return value and never on `main(argv)`. This gate counts extracted
scripts whose CLI is never proven to exit nonzero.

All git and filesystem I/O is against tmp_path with a stubbed `subprocess.run`,
so no test reads the live repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.ci import cli_exit_contract_ratchet as ratchet
from scripts.ci import merge_tree_ratchet_registry

_SCRIPT_WITH_MAIN = "def main(argv=None):\n    return 0\n"
_SCRIPT_WITHOUT_MAIN = "def helper():\n    return 0\n"


def _fake_git(scripts: tuple[str, ...], tests: tuple[str, ...], *, returncode: int = 0):
    """Stand in for `git ls-files -z`, answering per glob."""

    def _run(cmd, **_kwargs):
        paths = tests if any("tests/" in arg for arg in cmd) else scripts
        stdout = "\0".join(paths) + ("\0" if paths else "")
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    return _run


def _seed(root: Path, relative: str, content: str) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return relative


def _baseline(root: Path, value: str) -> Path:
    path = root / "baseline.txt"
    path.write_text(value, encoding="utf-8")
    return path


def _arrange(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str, test: str) -> None:
    scripts = (_seed(tmp_path, "scripts/ci/widget.py", script),)
    tests = (_seed(tmp_path, "tests/ci/test_widget.py", test),)
    monkeypatch.setattr(subprocess, "run", _fake_git(scripts, tests))


def _run(tmp_path: Path, baseline: str, *extra: str) -> int:
    return ratchet.main(
        [
            "--repo-root",
            str(tmp_path),
            "--baseline",
            str(_baseline(tmp_path, baseline)),
            *extra,
        ]
    )


def test_a_proven_cli_exit_counts_as_covered(tmp_path, monkeypatch):
    _arrange(
        tmp_path,
        monkeypatch,
        _SCRIPT_WITH_MAIN,
        "from scripts.ci import widget\n\n\ndef test_fails():\n    assert widget.main([]) == 1\n",
    )

    assert _run(tmp_path, "0") == ratchet.EXIT_OK


def test_a_helper_only_assertion_is_a_violation(tmp_path, monkeypatch, capsys):
    """The exact shape that let six silent passes ship."""
    _arrange(
        tmp_path,
        monkeypatch,
        _SCRIPT_WITH_MAIN,
        "from scripts.ci import widget\n\n\n"
        "def test_helper():\n    assert widget.helper() is None\n",
    )

    assert _run(tmp_path, "0") == ratchet.EXIT_REGRESSION
    assert "scripts/ci/widget.py" in capsys.readouterr().out


def test_a_helper_returncode_assertion_is_a_violation(tmp_path, monkeypatch, capsys):
    """End to end on the shape that shipped: main() swallows the failure, the
    test asserts the helper's nonzero return, and the gate used to go green."""
    _arrange(
        tmp_path,
        monkeypatch,
        _SCRIPT_WITH_MAIN,
        "from scripts.ci import widget\n\n\n"
        "def test_helper_reports_failure():\n"
        "    result = widget.run_gh([])\n"
        "    assert result.returncode == 1\n",
    )

    assert _run(tmp_path, "0") == ratchet.EXIT_REGRESSION
    assert "scripts/ci/widget.py" in capsys.readouterr().out


def test_a_script_without_main_is_ignored(tmp_path, monkeypatch):
    _arrange(tmp_path, monkeypatch, _SCRIPT_WITHOUT_MAIN, "def test_nothing():\n    assert True\n")

    assert _run(tmp_path, "0") == ratchet.EXIT_OK


def test_a_main_nested_in_a_class_is_not_an_entry_point(tmp_path, monkeypatch):
    """Edge: only a module-level `main` carries a process exit contract."""
    _arrange(
        tmp_path,
        monkeypatch,
        "class Runner:\n    def main(self):\n        return 0\n",
        "def test_nothing():\n    assert True\n",
    )

    assert _run(tmp_path, "0") == ratchet.EXIT_OK


@pytest.mark.parametrize(
    "body",
    [
        "assert widget.main([]) == 1",
        "assert widget.main([]) == widget.EXIT_CONFIG",
        "assert widget.main([]) == widget.EXTERNAL_ERROR",
        "rc = widget.main([])\n    assert rc == 1",
        "code = widget.main([])\n    assert code == widget.EXIT_CONFIG",
        'result = subprocess.run([sys.executable, "scripts/ci/widget.py"])\n'
        "    assert result.returncode == 2",
        "with pytest.raises(SystemExit) as excinfo:\n"
        "        widget.main([])\n"
        "    assert excinfo.value.code != 0",
    ],
)
def test_each_accepted_shape_is_recognized(body):
    source = f"from scripts.ci import widget\n\n\ndef test_x():\n    {body}\n"

    assert ratchet.covered_stems(source, frozenset({"widget"})) == {"widget"}


@pytest.mark.parametrize(
    "body",
    [
        "assert widget.main([]) == 0",
        "assert widget.main([]) == widget.EXIT_OK",
        "rc = widget.main([])\n    assert rc == 0",
        'result = subprocess.run([sys.executable, "scripts/ci/widget.py"])\n'
        "    assert result.returncode == 0",
    ],
)
def test_a_success_only_assertion_proves_nothing(body):
    source = f"from scripts.ci import widget\n\n\ndef test_x():\n    {body}\n"

    assert ratchet.covered_stems(source, frozenset({"widget"})) == set()


@pytest.mark.parametrize(
    "body",
    [
        # tests/ci/test_ruff_ratchet.py: a helper returns the sentinel and the
        # test checks the sentinel. main() is never called.
        "assert widget.run_ruff([]) == widget.EXIT_VIOLATIONS",
        # tests/ci/test_invoke_copilot_cli.py: a stubbed CompletedProcess.
        "result = widget.invoke([])\n    assert result.returncode == 127",
        # tests/ci/test_show_generated_agent_diff.py: the helper raises, and
        # main() returns 0 on that same failure.
        "with pytest.raises(subprocess.CalledProcessError) as error:\n"
        "        widget.changed_files()\n"
        "    assert error.value.returncode == 128",
    ],
)
def test_a_helper_level_nonzero_assertion_credits_nothing(body):
    """Issue #4068: the defect shape must never satisfy the gate."""
    source = f"from scripts.ci import widget\n\n\ndef test_x():\n    {body}\n"

    assert ratchet.covered_stems(source, frozenset({"widget"})) == set()


def test_a_sibling_method_calling_main_does_not_lend_coverage():
    """The class-scoped over-credit: one method asserts a helper failure, another
    calls main and gets 0 back, and nothing proves the process reports failure."""
    source = (
        "from scripts.ci import widget\n"
        "\n\n"
        "class TestHelper:\n"
        "    def test_helper_reports_failure(self):\n"
        "        assert widget.changed_files() == widget.EXIT_EXTERNAL\n"
        "\n"
        "    def test_main_is_fine(self):\n"
        "        assert widget.main([]) == 0\n"
    )

    assert ratchet.covered_stems(source, frozenset({"widget"})) == set()


def test_a_workflow_wiring_string_is_not_a_cli_invocation():
    """A multi-subject wiring test is the first test an extraction PR writes."""
    source = (
        "from scripts.ci import gadget\n"
        "\n\n"
        "def test_the_step_is_wired():\n"
        "    workflow = _read_workflow()\n"
        '    assert "python3 scripts/ci/widget.py" in workflow\n'
        "    assert gadget.main([]) == 1\n"
    )

    assert ratchet.covered_stems(source, frozenset({"widget", "gadget"})) == {"gadget"}


def test_a_subprocess_helper_carries_the_invocation_to_its_callers():
    """tests/test_run_with_retry.py runs the script inside a module-level helper."""
    source = (
        'SCRIPT = ROOT / ".github" / "scripts" / "widget.py"\n'
        "\n\n"
        "def _run(code):\n"
        "    return subprocess.run([sys.executable, str(SCRIPT), str(code)])\n"
        "\n\n"
        "def test_it_passes_the_exit_code_through():\n"
        "    result = _run(1)\n"
        "    assert result.returncode == 1\n"
    )

    assert ratchet.covered_stems(source, frozenset({"widget"})) == {"widget"}


def test_a_multi_subject_file_does_not_lend_coverage_to_a_sibling():
    """The over-credit that file-wide matching would produce."""
    source = (
        "from scripts.ci import widget\n"
        "from scripts.ci import gadget\n"
        "\n\n"
        "def test_widget_fails():\n"
        "    assert widget.main([]) == 1\n"
        "\n\n"
        "def test_gadget_passes():\n"
        "    assert gadget.main([]) == 0\n"
    )

    assert ratchet.covered_stems(source, frozenset({"widget", "gadget"})) == {"widget"}


def test_a_hand_rolled_module_loader_still_counts():
    """A spec_from_file_location block binds no name an alias matcher sees."""
    source = (
        'spec = importlib.util.spec_from_file_location("widget", path)\n'
        "mod = importlib.util.module_from_spec(spec)\n"
        "\n\n"
        "def test_x():\n"
        "    assert mod.main([]) == 2\n"
    )

    assert ratchet.covered_stems(source, frozenset({"widget"})) == {"widget"}


def test_an_unrecognized_method_named_main_does_not_use_bare_credit():
    source = (
        "from require_job_results import main\n"
        "\n\n"
        "def test_helper_wrapper():\n"
        "    helper = object()\n"
        "    assert helper.main([]) == 1\n"
    )

    assert ratchet.covered_stems(source, frozenset({"require_job_results"})) == set()


def test_a_subprocess_driven_cli_counts_by_script_path():
    source = (
        "def test_x():\n"
        '    result = subprocess.run([sys.executable, "scripts/ci/widget.py"])\n'
        "    assert result.returncode == 2\n"
    )

    assert ratchet.covered_stems(source, frozenset({"widget"})) == {"widget"}


def test_the_github_scripts_tree_is_in_scope(tmp_path, monkeypatch, capsys):
    """Issue #4068 asks for a sweep of the merged extraction batches, and 22 of
    those scripts live under .github/scripts."""
    scripts = (_seed(tmp_path, ".github/scripts/widget.py", _SCRIPT_WITH_MAIN),)
    tests = (_seed(tmp_path, "tests/test_widget.py", "def test_x():\n    assert True\n"),)
    monkeypatch.setattr(subprocess, "run", _fake_git(scripts, tests))

    assert _run(tmp_path, "0") == ratchet.EXIT_REGRESSION
    assert ".github/scripts/widget.py" in capsys.readouterr().out


def test_a_missing_baseline_is_a_config_error(tmp_path, monkeypatch):
    _arrange(tmp_path, monkeypatch, _SCRIPT_WITH_MAIN, "def test_x():\n    assert True\n")

    code = ratchet.main(
        ["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "absent.txt")]
    )

    assert code == ratchet.EXIT_CONFIG


def test_a_malformed_baseline_is_a_config_error(tmp_path, monkeypatch):
    _arrange(tmp_path, monkeypatch, _SCRIPT_WITH_MAIN, "def test_x():\n    assert True\n")

    assert _run(tmp_path, "not-a-number") == ratchet.EXIT_CONFIG


def test_an_unrecorded_improvement_fails_and_update_records_it(tmp_path, monkeypatch):
    _arrange(
        tmp_path,
        monkeypatch,
        _SCRIPT_WITH_MAIN,
        "from scripts.ci import widget\n\n\ndef test_x():\n    assert widget.main([]) == 1\n",
    )

    assert _run(tmp_path, "3") == ratchet.EXIT_OK
    assert _run(tmp_path, "3", "--update") == ratchet.EXIT_OK
    assert (tmp_path / "baseline.txt").read_text(encoding="utf-8").strip() == "0"


def test_a_git_failure_is_an_external_error(tmp_path, monkeypatch):
    _seed(tmp_path, "scripts/ci/widget.py", _SCRIPT_WITH_MAIN)
    monkeypatch.setattr(subprocess, "run", _fake_git((), (), returncode=128))

    assert _run(tmp_path, "0") == ratchet.EXIT_EXTERNAL


def test_the_gate_is_wired_into_pr_validation():
    """Issue #3329: a guard nothing runs is not a guard."""
    workflow = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pr-validation.yml"
    ).read_text(encoding="utf-8")

    assert "scripts/ci/cli_exit_contract_ratchet.py" in workflow


def test_the_shipped_baseline_matches_the_tracked_tree() -> None:
    """The baseline must describe this repository, not a number typed by hand.

    This ratchet shipped in PR #4110 with a baseline of 14 against a tree that
    already held 33 violations, so it failed on the commit that introduced it
    and on every pull request after. Nothing in the suite compared the two, and
    the gate itself only runs on ``pull_request``, so no run against main ever
    contradicted it.

    The sibling taste ratchet has carried this assertion since it was added
    (``tests/ci/test_count_ratchet_against_real_git.py``). Every counting
    ratchet needs one: a baseline above the real count is dead allowance, and a
    baseline below it means every pull request is red for a reason that has
    nothing to do with its diff.

    Run ``python scripts/ci/cli_exit_contract_ratchet.py`` directly for the
    per-file detail rather than waiting on the suite.
    """
    repo_root = Path(__file__).resolve().parents[2]
    baseline_path = repo_root / "scripts" / "ci" / "cli_exit_contract_baseline.txt"
    baseline = int(baseline_path.read_text(encoding="utf-8").strip())
    actual = ratchet.current_count(repo_root)
    assert actual is not None, (
        "the scan returned None, which means it could not read the tree. A "
        "broken scan reports zero violations and would look like a clean "
        "repository, so it must fail here rather than pass quietly."
    )
    assert actual == baseline, (
        f"cli exit contract ratchet: baseline is {baseline} but the current "
        f"tree has {actual} violations. Run "
        f"'python scripts/ci/cli_exit_contract_ratchet.py' for per-file detail."
    )




class TestLocalMainScopeGateBehavior:
    """Regression: _has_local_main_definition scope-aware module binding.

    The sole-script fallback credits a bare ``main()`` call only when the test
    file does not define its own ``main``.  These tests use bare ``main()``
    (not ``widget.main()``) so that *sole* is the only credit path.

    ast.walk version:  class method main triggers True -> sole suppressed
    flat tree.body:    if-guarded def main returns False -> sole incorrectly enabled
    scope-aware:       class method skipped, if-guard descended -> correct
    """

    _SCRIPT = "def main(argv=None):\n    return 1\n"

    def test_class_method_main_does_not_suppress_sole_fallback(
        self, tmp_path, monkeypatch,
    ):
        """Class method ``main`` must not suppress sole; bare main() credits."""
        _arrange(
            tmp_path,
            monkeypatch,
            self._SCRIPT,
            # bare main() call, class method main should NOT suppress sole
            (
                "from scripts.ci import widget\n\n\n"
                "class Helpers:\n"
                "    def main(self):\n"
                "        pass\n\n\n"
                "def test_exit():\n"
                "    assert main([]) == 1\n"
            ),
        )
        assert _run(tmp_path, "0") == ratchet.EXIT_OK

    def test_if_guarded_def_main_suppresses_sole_fallback(
        self, tmp_path, monkeypatch,
    ):
        """``if __name__: def main`` at module scope binds main, suppressing sole."""
        _arrange(
            tmp_path,
            monkeypatch,
            self._SCRIPT,
            (
                "from scripts.ci import widget\n\n\n"
                "if __name__ == '__main__':\n"
                "    def main():\n"
                "        pass\n\n\n"
                "def test_exit():\n"
                "    assert main([]) == 1\n"
            ),
        )
        # sole suppressed: local main inside if-guard at module scope
        # bare main() is NOT attributed to widget because local main shadows it
        assert _run(tmp_path, "0") == ratchet.EXIT_REGRESSION

    def test_lambda_assignment_main_suppresses_sole_fallback(
        self, tmp_path, monkeypatch,
    ):
        """``main = lambda: 0`` creates a local binding, suppressing sole."""
        _arrange(
            tmp_path,
            monkeypatch,
            self._SCRIPT,
            (
                "from scripts.ci import widget\n\n\n"
                "main = lambda: 0\n\n\n"
                "def test_exit():\n"
                "    assert main([]) == 1\n"
            ),
        )
        assert _run(tmp_path, "0") == ratchet.EXIT_REGRESSION


def test_ratchet_registered_with_base_ref_via_merge_tree_backstop() -> None:
    """The cli-exit-contract ratchet gets a one-directional guard.

    Issue #4528 comment: the gate accepted only ``--update`` (decrease) with no
    one-directional guard. Issue #5441 moved this ratchet's registration out of
    ``checks_ratchet.RATCHETS`` (which used to run it a second time against a
    materialized merge tree) and into
    ``scripts/ci/merge_tree_ratchet_registry.py``, whose entries
    ``validate_count_ratchets`` always evaluates with a resolved base ref
    through the merge-tree backstop (see
    ``scripts/ci/merge_tree_ratchet_check.py::_evaluate_merged_tree``), so a
    raised baseline still fails locally before a push, not only on CI.
    """
    labels = {r.label for r in merge_tree_ratchet_registry.RATCHETS}
    assert "cli exit contract ratchet" in labels, (
        "cli exit contract ratchet is missing from RATCHETS in "
        "scripts/ci/merge_tree_ratchet_registry.py. Add it so the merge-tree "
        "backstop enforces the one-directional guard."
    )
    assert ratchet.MERGE_TREE_BACKED is True, (
        "cli_exit_contract_ratchet.MERGE_TREE_BACKED must stay True: it "
        "declares that scripts/ci/merge_tree_ratchet_check.py, not this "
        "ratchet's own --base-ref comparison, is what catches a branch behind "
        "a base ref that lowered the baseline."
    )


def test_ci_invocation_passes_base_ref() -> None:
    """The CI step must pass --base-ref so a raised baseline fails the gate.

    Issue #4528: pr-validation.yml invoked the ratchet without --base-ref, so
    a contributor could raise the baseline, satisfy 'count == baseline', and
    merge. Only the --base-ref comparison can distinguish a genuine decrease
    from a raised allowance.
    """
    workflow_path = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "pr-validation.yml"
    )
    with workflow_path.open(encoding="utf-8") as handle:
        workflow = yaml.safe_load(handle)

    runs = [
        step["run"]
        for job in (workflow.get("jobs") or {}).values()
        for step in (job.get("steps") or [])
        if "cli_exit_contract_ratchet.py" in (step.get("run") or "")
    ]

    assert runs, (
        "pr-validation.yml has no step that runs cli_exit_contract_ratchet.py. "
        "The gate cannot catch a raised baseline if it never runs. "
        "See issue #4528."
    )
    for run in runs:
        assert "--base-ref" in run, (
            "The CI step for cli_exit_contract_ratchet.py in pr-validation.yml "
            f"must pass --base-ref so a raised baseline is caught. Got: {run!r}. "
            "See issue #4528."
        )
