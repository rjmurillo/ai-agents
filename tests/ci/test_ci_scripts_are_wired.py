"""Every guard under scripts/ci must be called by a live workflow step.

Issue #3329: `ruff_count_ratchet.py` and `adr006_run_block_scanner.py` both
shipped with passing test suites and no caller. Their tests exercised the
interface, so they were green, and the guards protected nothing for weeks. The
count ratchet was also wrong in a way only a real run would surface: it scoped
itself with a directory walk and counted 767 violations where the tracked-file
number was 361.

A unit test cannot catch that class of defect, because the thing that is missing
is the call site. This checks the call site.

"Live" is doing real work here. An earlier version of this file asserted only
that the script path appeared somewhere in the concatenated workflow text, which
a comment, a disabled step, a heredoc, or a similarly-named file all satisfy.
This version parses the YAML and looks at `run:` bodies of steps that are not
statically disabled.

What this does not do: evaluate GitHub expressions. A step guarded by
`if: ${{ needs.x.outputs.y == 'true' }}` counts as live, because deciding
otherwise would mean interpreting the whole expression language. Only the
literal `if: false` form is treated as dead.
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_SCRIPTS_DIR = _REPO_ROOT / "scripts" / "ci"
_WORKFLOW_DIRS = (
    _REPO_ROOT / ".github" / "workflows",
    _REPO_ROOT / ".github" / "actions",
)

# Guards that are deliberately not invoked from a workflow. Each needs a
# non-empty reason, so that adding one is a decision rather than a way to
# silence this test.
_NOT_WORKFLOW_INVOKED: dict[str, str] = {
    "cli_exit_contract_coverage.py": (
        "Library holding the test-coverage analysis for "
        "cli_exit_contract_ratchet.py, which is workflow-invoked from "
        "pr-validation.yml. It has no main() and no shebang; "
        "tests/ci/test_cli_exit_contract_ratchet.py drives it directly through "
        "covered_stems (issue #4068)."
    ),
    "diff_line_scope.py": (
        "Library holding the unified-diff line-scope parsing shared by "
        "ruff_ratchet.py, which pytest.yml invokes, and the pre-push mypy gate "
        "in scripts/validation/git_hook_policy.py. It has no main() and no "
        "shebang; tests/ci/test_diff_line_scope.py covers it directly "
        "(issue #2993)."
    ),
    "count_ratchet.py": (
        "Library holding the ratchet policy shared by ruff_count_ratchet.py and "
        "taste_count_ratchet.py, both of which are workflow-invoked. It has no "
        "main() and no shebang; tests/ci/test_count_ratchet.py covers it "
        "directly (issue #3779)."
    ),
    "failure_classification.py": (
        "Library holding PR-fetch failure classification for "
        "build_ai_review_context.py, which ai-review.yml invokes. It has no "
        "main() and no shebang; tests/ci/test_failure_classification.py covers "
        "its policy while tests/test_build_ai_review_context.py covers the "
        "workflow-invoked integration (issue #4597)."
    ),
    "merge_tree_materialization.py": (
        "Library holding the exact-tree materialization and isolated Git helpers "
        "for merge_tree_ratchet_check.py, which pr-validation.yml invokes. It has "
        "no main() and no shebang; tests/ci/test_merge_tree_materialization.py "
        "drives it directly."
    ),
    "merge_tree_ratchet_registry.py": (
        "Library holding the single ownership registry of ratchets that "
        "merge_tree_ratchet_check.py evaluates, and pr-validation.yml invokes "
        "that checker. It has no main() and no shebang; "
        "tests/test_lefthook_gate_config.py asserts the registry matches the "
        "Lefthook jobs."
    ),
    "mutation_harness_ciperms.py": (
        "Developer tool for verifying CI security tests (issues #3964 and #4151). "
        "Run manually with `uv run --frozen python3 scripts/ci/mutation_harness_ciperms.py`. "
        "It orchestrates pytest sub-processes and is not wired into CI itself."
    ),
    "parse_drift_results.py": (
        "Subprocess helper called by drift_collect_details.py (ADR-006 extraction "
        "batch 6). drift_collect_details.py is the workflow-invoked entry point; "
        "parse_drift_results.py is its implementation detail."
    ),
    "run_pytest_non_tmp.py": (
        "Library entry invoked by run_pytest_selected.py, which pytest.yml runs "
        "for every partition (issue #5050). It keeps the repo-isolated temp root; "
        "tests/ci/test_pytest_non_tmp_policy.py covers it directly and asserts the "
        "workflow routes through the selection runner that calls it."
    ),
    "spec_nonexecutable_criteria.py": (
        "Library holding the acceptance-criteria classifier for "
        "spec_prepare_context.py, which ai-spec-validation.yml invokes. It has "
        "no main() and no shebang; tests/ci/test_spec_nonexecutable_criteria.py "
        "drives it directly and tests/ci/test_spec_prepare_context.py covers "
        "the workflow-invoked integration (issue #5366)."
    ),
    "ruleset_required_contexts.py": (
        "Library holding the required-context contract shared by "
        "ruleset_context_drift.py and test_merge_group_readiness.py. The "
        "scheduled workflow invokes the detector, while both test files verify "
        "the shared contract."
    ),
}


def _yaml_files() -> list[Path]:
    paths: list[Path] = []
    for directory in _WORKFLOW_DIRS:
        if not directory.is_dir():
            continue
        paths.extend(directory.rglob("*.yml"))
        paths.extend(directory.rglob("*.yaml"))
    return sorted(paths)


def _is_disabled(step: dict[str, Any]) -> bool:
    """True only for the literal `if: false` form. See the module docstring."""
    condition = step.get("if")
    if condition is False:
        return True
    return isinstance(condition, str) and condition.strip().lower() in {
        "false",
        "${{ false }}",
    }


def _steps_of(document: Any) -> list[dict[str, Any]]:
    """Every step in a workflow (jobs.*.steps) or composite action (runs.steps)."""
    steps: list[dict[str, Any]] = []
    if not isinstance(document, dict):
        return steps

    jobs = document.get("jobs")
    if isinstance(jobs, dict):
        for job in jobs.values():
            if isinstance(job, dict) and isinstance(job.get("steps"), list):
                steps.extend(s for s in job["steps"] if isinstance(s, dict))

    runs = document.get("runs")
    if isinstance(runs, dict) and isinstance(runs.get("steps"), list):
        steps.extend(s for s in runs["steps"] if isinstance(s, dict))

    return steps


@functools.lru_cache(maxsize=1)
def _live_run_blocks() -> tuple[tuple[str, str], ...]:
    """`run:` bodies of every step that is not statically disabled.

    Returns a tuple of (path-as-string, body) pairs so the result is hashable
    and cacheable.  Re-parsing every YAML file per parametrized case is wasteful
    because the file set does not change within a test session.
    """
    blocks: list[tuple[str, str]] = []
    for path in _yaml_files():
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # validate_workflows.py owns reporting this
            continue
        for step in _steps_of(document):
            body = step.get("run")
            if isinstance(body, str) and not _is_disabled(step):
                blocks.append((str(path), body))
    return tuple(blocks)


def _strip_commented_lines(body: str) -> str:
    """Drop whole-line shell comments from a `run:` body.

    A step that reads::

        # python scripts/ci/foo.py   # disabled, see #1234
        echo skipping

    used to count as wiring, so commenting a script out left the probe green
    and the guard asleep.  Only leading-`#` lines are removed: a trailing `#`
    can sit inside single quotes, a double-quoted string, or a `${VAR#pat}`
    expansion, and stripping from there mangles live commands.
    """
    kept = [line for line in body.splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(kept)


def _invoking_files(script_path: str) -> list[Path]:
    return sorted(
        {
            Path(path)
            for path, body in _live_run_blocks()
            if script_path in _strip_commented_lines(body)
        }
    )


def _ci_scripts() -> list[Path]:
    if not _CI_SCRIPTS_DIR.is_dir():
        return []
    return [p for p in sorted(_CI_SCRIPTS_DIR.glob("*.py")) if not p.name.startswith("_")]


@pytest.mark.parametrize("script", _ci_scripts(), ids=lambda p: p.name)
def test_ci_script_is_invoked_by_a_workflow(script: Path) -> None:
    if script.name in _NOT_WORKFLOW_INVOKED:
        pytest.skip(_NOT_WORKFLOW_INVOKED[script.name])
    rel = script.relative_to(_REPO_ROOT).as_posix()
    assert _invoking_files(rel), (
        f"{rel} is not run by any enabled step in .github/workflows or "
        f".github/actions. A guard nothing runs is not a guard, and its own "
        f"tests will stay green while it protects nothing (issue #3329). Wire "
        f"it into a workflow, or add it to _NOT_WORKFLOW_INVOKED with a reason."
    )


def test_every_allowlist_entry_carries_a_reason() -> None:
    """An empty reason turns the allowlist into a silent opt-out."""
    for name, reason in _NOT_WORKFLOW_INVOKED.items():
        assert reason.strip(), f"_NOT_WORKFLOW_INVOKED[{name!r}] needs a reason"


def test_workflow_yaml_validator_runs_in_ci() -> None:
    """Issue #3330: workflow schema had no required CI gate.

    Named separately from the parametrized case above because the validator does
    not live under scripts/ci, and because the specific requirement is that it
    runs on a path-independent job: a workflow-only PR changes no Python, so
    every path-filtered gate skips it.
    """
    assert _invoking_files("scripts/validate_workflows.py"), (
        "scripts/validate_workflows.py is run by no enabled workflow step, so "
        "workflow schema lands unvalidated from Renovate, Dependabot, the web "
        "editor, the API, and any clone without hooks installed (issue #3330)."
    )


def test_workflow_validation_is_not_gated_on_the_bot_exclusion() -> None:
    """Renovate and Dependabot are the traffic this gate exists to cover.

    pr-validation.yml skips most steps for bot actors. Workflow-only PRs are
    overwhelmingly bot-authored action-pin bumps, so a workflow-validation step
    carrying that guard would exempt exactly the case it was added for.
    """
    document = yaml.safe_load(
        (_REPO_ROOT / ".github" / "workflows" / "pr-validation.yml").read_text(encoding="utf-8")
    )
    validating = [
        step
        for step in _steps_of(document)
        if isinstance(step.get("run"), str) and "scripts/validate_workflows.py" in step["run"]
    ]
    assert validating, "pr-validation.yml no longer runs the workflow validator"
    for step in validating:
        condition = str(step.get("if", ""))
        assert "should-run" not in condition, (
            f"step {step.get('name')!r} is gated on the bot exclusion, so "
            f"dependabot, renovate, and github-actions bypass it"
        )


def test_the_wiring_probe_reads_real_workflow_files() -> None:
    """Guard the guard: an empty corpus would make every case above vacuous.

    Assert only what makes the cases above non-vacuous: the corpus is
    non-empty and it was gathered by walking the workflow tree rather than
    reading one file. A floor on the block count, or a requirement that some
    step shell out to a particular tool, would fail on workflow refactors that
    leave this guard working perfectly, which is noise rather than signal.
    """
    blocks = _live_run_blocks()
    assert blocks, "no run: blocks found, so every wiring assertion is vacuous"
    assert len({path for path, _ in blocks}) > 1, (
        "every run: block came from one file, so the probe is not walking the tree"
    )


def test_a_disabled_step_does_not_count_as_a_call_site() -> None:
    """The substring form this replaced accepted `if: false` steps."""
    assert _is_disabled({"if": False, "run": "x"})
    assert _is_disabled({"if": "false", "run": "x"})
    assert not _is_disabled({"run": "x"})
    assert not _is_disabled({"if": "${{ github.event_name == 'push' }}", "run": "x"})


def test_a_comment_mention_does_not_count_as_a_call_site() -> None:
    """Parsed YAML drops comments, so a mentioned-but-never-run script fails."""
    document = yaml.safe_load(
        "name: X\non: [push]\njobs:\n"
        "  j:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      # scripts/ci/ghost.py used to run here\n"
        "      - run: echo hi\n"
    )
    bodies = [s.get("run", "") for s in _steps_of(document)]
    assert not any("ghost.py" in b for b in bodies)


def test_composite_action_steps_are_searched() -> None:
    """.github/actions bodies use runs.steps, not jobs.*.steps."""
    document = yaml.safe_load(
        "name: A\nruns:\n  using: composite\n  steps:\n"
        "    - run: python3 scripts/ci/example.py\n      shell: bash\n"
    )
    assert [s["run"] for s in _steps_of(document)] == ["python3 scripts/ci/example.py"]


_this = sys.modules[__name__]


class TestCommentedOutInvocationsDoNotCount:
    """A commented-out call is not wiring, and the probe must say so.

    The whole point of this module is to catch a script that ships with tests
    and is wired into nothing.  Substring matching over the raw `run:` body
    scored a `#`-prefixed mention as a live call, so the cheapest way to
    silence a red guard was to comment the invocation out.

    These exercise ``_invoking_files``, not the stripper it calls: testing the
    helper alone passes even when nothing routes through it.
    """

    @staticmethod
    def _with_corpus(monkeypatch, *bodies: str) -> None:
        blocks = tuple((f".github/workflows/w{i}.yml", b) for i, b in enumerate(bodies))
        monkeypatch.setattr(_this, "_live_run_blocks", lambda: blocks)

    def test_a_commented_line_does_not_count_as_wiring(self, monkeypatch):
        self._with_corpus(monkeypatch, "# python scripts/ci/foo.py\necho hi")
        assert _invoking_files("scripts/ci/foo.py") == []

    def test_an_indented_comment_does_not_count_as_wiring(self, monkeypatch):
        self._with_corpus(monkeypatch, "if true; then\n    # python scripts/ci/foo.py\nfi")
        assert _invoking_files("scripts/ci/foo.py") == []

    def test_a_live_call_still_counts(self, monkeypatch):
        self._with_corpus(monkeypatch, "# set up\npython scripts/ci/foo.py --max 87")
        assert _invoking_files("scripts/ci/foo.py") == [Path(".github/workflows/w0.yml")]

    def test_a_trailing_comment_does_not_truncate_the_command(self, monkeypatch):
        """Mid-line `#` is left alone: it appears inside quotes and expansions."""
        self._with_corpus(monkeypatch, "python scripts/ci/foo.py  # ratchet, see ADR-006")
        assert _invoking_files("scripts/ci/foo.py") == [Path(".github/workflows/w0.yml")]

    def test_a_hash_inside_a_parameter_expansion_survives(self, monkeypatch):
        self._with_corpus(monkeypatch, 'python scripts/ci/foo.py --tag "${REF#refs/heads/}"')
        assert _invoking_files("scripts/ci/foo.py") == [Path(".github/workflows/w0.yml")]

    def test_a_live_call_beside_a_commented_one_still_counts(self, monkeypatch):
        """Stripping must not throw away the rest of a multi-line body."""
        self._with_corpus(monkeypatch, "# python scripts/ci/foo.py --old\npython scripts/ci/foo.py")
        assert _invoking_files("scripts/ci/foo.py") == [Path(".github/workflows/w0.yml")]
