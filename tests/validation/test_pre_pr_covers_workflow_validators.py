"""Bind pre_pr's gate list to every validator a pull-request workflow runs (issue #5676).

Issue #5670 found four ``Validate Vendor Portability`` validators with no
``pre_pr.py`` gate and PR #5673 bound that one workflow. This test binds the
rest. Both sides are derived, never hand-listed:

- Workflow side: every ``.github/workflows/*.yml`` that runs on a pull request,
  scanned for ``scripts/validation/`` invocations with help text dropped
  (``workflow_validator_inventory.workflow_validators``).
- pre_pr side: every gate in ``_SEQUENCE`` executed with the process spawners
  replaced by recorders (``workflow_validator_inventory.observe_gates``). A name
  in a comment, a docstring, or an import nothing calls leaves no trace.

A validator a workflow runs must be run by a gate, or appear in ``EXEMPT`` with
the reason a local gate cannot or should not run it. Adding a validator to a
workflow fails ``test_every_workflow_validator_is_gated_or_exempt`` until one of
those is true.

Negative controls, each verified to fail before shipping:

- Add a validator step to any pull-request workflow with no gate:
  ``test_every_workflow_validator_is_gated_or_exempt`` fails.
- Delete a gate from ``_SEQUENCE``: the same test fails, naming the validator.
- Leave an ``EXEMPT`` entry after its validator gains a gate or leaves the
  workflows: ``test_exemptions_are_not_stale`` fails.
- Switch the model-pin gate to ``--mode enforce`` without removing its
  ``WARN_ONLY`` row: ``test_warn_only_rows_match_what_runs`` fails.
"""

from __future__ import annotations

import argparse
import io
import sys
import textwrap
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
_WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# Import the pre-PR runner modules the way production imports them: add
# ``scripts/validation`` to ``sys.path`` and import by bare name (issue #2223).
# Never restored; see test_pre_pr_model_pin_wiring.py for why.
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import pre_pr
import pre_pr_sequence
import workflow_validator_inventory as inventory

# Validators a pull-request workflow runs that no pre_pr gate runs, with the
# reason. One place, so a reader can see every gap and why it is allowed.
EXEMPT: dict[str, str] = {
    "check_zero_collection_tests": (
        "The unconditional lefthook pre-push job zero-collection-tests runs it on "
        "every push. It costs about 38 seconds, measured, and pre-pr-validation "
        "has a four minute timeout against a 192 second baseline."
    ),
    "report_rule_activation_states": (
        "Report writer, not a check. It only emits a JSON artifact for CI upload "
        "and has no pass or fail result of its own. The ratchet over the same "
        "inventory, check_rule_activation_coverage, is gated by pre_pr."
    ),
    "run_install_parity_ci": (
        "Thin CI wrapper that fetches the base ref and calls "
        "build/scripts/validate_install_parity.py, which pre_pr runs through "
        "checks_plugin. The wrapper adds nothing a local run can use."
    ),
    "run_plugin_version_bump_ci": (
        "Thin CI wrapper that fetches the base ref and calls "
        "build/scripts/validate_plugin_version_bump.py, which pre_pr runs "
        "through checks_plugin. The wrapper adds nothing a local run can use."
    ),
}

# Validators pre_pr runs in a weaker mode than CI, by design. Each row is
# (flag CI passes, flag pre_pr passes, reason). The row is checked against both
# sides, so it cannot outlive the difference it records.
WARN_ONLY: dict[str, tuple[str, str, str]] = {
    "check_model_pins": (
        "--mode enforce",
        "--mode warn",
        "ADR-080 wires the local gate in warn mode by design and enforces in CI. "
        "Warn mode exits 0 on a violation, so a new unjustified model pin clears "
        "pre_pr and fails Validate PR.",
    ),
}

_MIN_REASON_LENGTH = 40


@pytest.fixture(scope="module")
def workflow_map() -> dict[str, set[str]]:
    return inventory.workflow_validators(_WORKFLOWS_DIR)


@pytest.fixture(scope="module")
def observed() -> inventory.Observed:
    gates = [(gate.name, gate.run) for gate in pre_pr_sequence._SEQUENCE]
    args = pre_pr.build_parser().parse_args([])
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return inventory.observe_gates(gates, REPO_ROOT, args, _VALIDATION_DIR)


def uncovered(
    workflow_map: dict[str, set[str]],
    observed: inventory.Observed,
    exempt: dict[str, str],
) -> dict[str, set[str]]:
    """Validators a workflow runs that no gate ran and no exemption covers."""
    return {
        name: workflows
        for name, workflows in workflow_map.items()
        if name not in observed.by_validator and name not in exempt
    }


def test_every_workflow_validator_is_gated_or_exempt(
    workflow_map: dict[str, set[str]], observed: inventory.Observed
) -> None:
    missing = uncovered(workflow_map, observed, EXEMPT)
    detail = "; ".join(f"{name} ({', '.join(sorted(wf))})" for name, wf in sorted(missing.items()))
    assert not missing, (
        f"Pull-request workflows run validators no pre_pr gate runs: {detail}. Add a gate "
        "in scripts/validation/checks_ci_parity.py and a row in pre_pr_sequence._SEQUENCE, "
        "or add an EXEMPT entry with the reason."
    )


def test_the_workflow_scan_finds_the_known_validators(workflow_map: dict[str, set[str]]) -> None:
    """A scan that finds nothing would pass the test above for the wrong reason."""
    for known in ("agent_registry", "check_python3_entrypoints", "hook_contracts"):
        assert known in workflow_map


def test_the_gate_sweep_observes_gates_run(observed: inventory.Observed) -> None:
    assert "check_vendor_portability" in observed.by_validator
    assert len(observed.by_validator) > 20


def test_exemptions_are_not_stale(
    workflow_map: dict[str, set[str]], observed: inventory.Observed
) -> None:
    for name in EXEMPT:
        assert name in workflow_map, f"{name} is exempt but no pull-request workflow runs it"
        assert name not in observed.by_validator, (
            f"{name} is exempt but a pre_pr gate now runs it; delete the exemption"
        )


def test_every_exemption_and_warn_only_row_states_a_reason() -> None:
    reasons = [*EXEMPT.values(), *(row[2] for row in WARN_ONLY.values())]
    assert all(len(reason) >= _MIN_REASON_LENGTH for reason in reasons)


def test_warn_only_rows_match_what_runs(
    observed: inventory.Observed,
) -> None:
    commands = inventory.workflow_commands(_WORKFLOWS_DIR)
    for name, (ci_flag, local_flag, _reason) in WARN_ONLY.items():
        ci = [cmd for _wf, cmd in commands if name in inventory.validator_names(cmd)]
        assert ci, f"{name}: no pull-request workflow runs it"
        assert any(ci_flag in cmd for cmd in ci), f"{name}: CI no longer passes {ci_flag}"
        local = observed.argv.get(name, [])
        assert local, f"{name}: no pre_pr gate runs it"
        assert all(local_flag in argv for argv in local), (
            f"{name}: pre_pr no longer passes {local_flag}; delete the WARN_ONLY row"
        )


def test_uncovered_reports_a_validator_with_neither_gate_nor_exemption() -> None:
    seen = inventory.Observed(by_validator={"gated": {"Some Gate"}})
    mapping = {"gated": {"a.yml"}, "orphan": {"b.yml"}, "exempt": {"c.yml"}}
    assert uncovered(mapping, seen, {"exempt": "reason"}) == {"orphan": {"b.yml"}}


# --- scanner unit tests ------------------------------------------------------


def _write_workflow(directory: Path, name: str, body: str) -> None:
    (directory / name).write_text(textwrap.dedent(body), encoding="utf-8")


def test_scanner_ignores_echo_help_text_and_comments(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "w.yml",
        """
        on: pull_request
        jobs:
          j:
            steps:
              - run: python3 scripts/validation/real_one.py
              - run: |
                  # scripts/validation/commented_out.py
                  echo "run scripts/validation/only_help.py" \\
                       "and scripts/validation/more_help.py"
                  printf 'scripts/validation/printed.py'
                  python3 -m scripts.validation.module_form --ci
        """,
    )
    assert set(inventory.workflow_validators(tmp_path)) == {"real_one", "module_form"}


def test_scanner_ignores_workflows_that_do_not_run_on_pull_requests(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "push_only.yml",
        """
        on:
          push:
            branches: [main]
        jobs:
          j:
            steps:
              - run: python3 scripts/validation/push_only.py
        """,
    )
    _write_workflow(
        tmp_path,
        "pr.yml",
        """
        on:
          pull_request:
            branches: [main]
        jobs:
          j:
            steps:
              - run: python3 scripts/validation/on_pr.py
        """,
    )
    assert set(inventory.workflow_validators(tmp_path)) == {"on_pr"}


def test_scanner_reports_each_dispatcher_subcommand_separately() -> None:
    names = inventory.validator_names(
        "python3 scripts/validation/git_hook_policy.py tracked-conflict-markers"
    )
    assert names == {"git_hook_policy:tracked-conflict-markers"}


# --- recorder unit tests -----------------------------------------------------


def _fake_validation_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "scripts" / "validation"
    directory.mkdir(parents=True)
    (directory / "called_validator.py").write_text("def run():\n    return 0\n", encoding="utf-8")
    (directory / "imported_only.py").write_text("def run():\n    return 0\n", encoding="utf-8")
    (directory / "docstring_only.py").write_text(
        '"""Only a docstring names this validator."""\n', encoding="utf-8"
    )
    return directory


def test_recorder_counts_a_call_a_spawn_and_ignores_an_uncalled_import(tmp_path: Path) -> None:
    import importlib
    import subprocess

    directory = _fake_validation_dir(tmp_path)
    sys.path.insert(0, str(directory))
    try:

        def calls(_root: Path, _args: argparse.Namespace) -> None:
            importlib.import_module("called_validator").run()

        def imports(_root: Path, _args: argparse.Namespace) -> None:
            importlib.import_module("imported_only")

        def spawns(_root: Path, _args: argparse.Namespace) -> None:
            subprocess.run(["python3", "scripts/validation/spawned_validator.py"], check=False)

        def mentions(_root: Path, _args: argparse.Namespace) -> None:
            # scripts/validation/docstring_only.py appears only in this comment.
            importlib.import_module("docstring_only")

        seen = inventory.observe_gates(
            [("calls", calls), ("imports", imports), ("spawns", spawns), ("mentions", mentions)],
            tmp_path,
            argparse.Namespace(),
            directory,
        )
    finally:
        sys.path.remove(str(directory))
        for module in ("called_validator", "imported_only", "docstring_only"):
            sys.modules.pop(module, None)

    assert seen.by_validator["called_validator"] == {"calls"}
    assert seen.by_validator["spawned_validator"] == {"spawns"}
    assert "imported_only" not in seen.by_validator
    assert "docstring_only" not in seen.by_validator


def test_recorder_records_a_gate_that_raises_and_keeps_going(tmp_path: Path) -> None:
    def boom(_root: Path, _args: argparse.Namespace) -> None:
        raise SystemExit(2)

    seen = inventory.observe_gates([("boom", boom)], tmp_path, argparse.Namespace(), tmp_path)
    assert seen.errors["boom"].startswith("SystemExit")


# --- per-gate negative controls (acceptance criterion 4) ---------------------

# Gate name -> the text its command carries, for each gate this change added.
_NEW_GATES: dict[str, str] = {
    "Agent Registry": "agent_registry.py",
    "Plugin Frontmatter Self-Containment": "check_plugin_frontmatter_self_containment.py",
    "Python3 Entrypoints": "check_python3_entrypoints.py",
    "GitHub Actions SHA Pinning": "sha_pinning.py",
    "ADR Number Uniqueness": "check_adr_uniqueness.py",
    "Agent-Skill Discriminator": "check_agent_skill_discriminator.py",
    "Hook Contracts": "hook_contracts.py",
    "Passive Context Budget": "passive_context_budget",
    "Skillbook Validation": "validate_skillbook.py",
    "Placeholder Identity": "check_placeholder_identity.py",
    "Tracked Conflict Markers": "tracked-conflict-markers",
    "Security Suppressions Diff": "security-suppressions-diff",
}


def _new_gate_results(monkeypatch: pytest.MonkeyPatch, failing: str) -> dict[str, bool]:
    """Run each new gate with one validator's command forced to exit 1."""
    import checks_ci_parity

    def fake(argv: list[str], **_kwargs: object) -> tuple[int, str, str]:
        return (1 if failing in " ".join(argv) else 0), "", ""

    monkeypatch.setattr(checks_ci_parity, "_run_subprocess", fake)
    monkeypatch.setattr(checks_ci_parity, "_resolve_default_base_ref", lambda _root: "origin/main")
    # Change-triggered gates pass the branch's changed files as arguments. Pin
    # that list so a branch that edits a validator does not put its name into
    # another gate's argv and turn that gate red too.
    monkeypatch.setattr(
        checks_ci_parity,
        "_changed_paths_since_base",
        lambda _root, _label: ["templates/agents/analyst.shared.md"],
    )
    gates = {gate.name: gate for gate in pre_pr_sequence._SEQUENCE}
    with redirect_stdout(io.StringIO()):
        return {name: bool(gates[name].run(REPO_ROOT, argparse.Namespace())) for name in _NEW_GATES}


@pytest.mark.parametrize(("gate_name", "token"), sorted(_NEW_GATES.items()))
def test_each_new_gate_goes_red_for_its_own_validator_only(
    gate_name: str, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = _new_gate_results(monkeypatch, token)
    assert results[gate_name] is False
    assert [name for name, passed in results.items() if not passed] == [gate_name]


def test_new_gates_are_never_skipped_in_quick_mode() -> None:
    gates = {gate.name: gate for gate in pre_pr_sequence._SEQUENCE}
    assert not [name for name in _NEW_GATES if gates[name].skip_when_quick]


def test_a_missing_base_ref_skips_the_two_diff_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    import checks_ci_parity
    from checks_common import MissingScriptSkip

    monkeypatch.setattr(checks_ci_parity, "_resolve_default_base_ref", lambda _root: None)
    for validate in (
        checks_ci_parity.validate_placeholder_identity,
        checks_ci_parity.validate_security_suppressions_diff,
    ):
        with pytest.raises(MissingScriptSkip):
            validate(REPO_ROOT)


def test_a_missing_script_skips_where_no_workflows_exist(tmp_path: Path) -> None:
    import checks_ci_parity
    from checks_common import MissingScriptSkip

    with pytest.raises(MissingScriptSkip):
        checks_ci_parity.validate_agent_registry(tmp_path)


def test_a_missing_script_fails_where_workflows_still_run_it(tmp_path: Path) -> None:
    import checks_ci_parity

    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    with redirect_stdout(io.StringIO()) as captured:
        assert checks_ci_parity.validate_agent_registry(tmp_path) is False
    assert "agent_registry.py is missing" in captured.getvalue()


def test_the_diff_gates_refresh_the_base_and_warn_when_the_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import checks_ci_parity

    refreshed: list[str] = []

    def refresh(base_ref: str, _root: Path) -> str:
        refreshed.append(base_ref)
        return "offline"

    monkeypatch.setattr(checks_ci_parity, "_resolve_default_base_ref", lambda _root: "origin/main")
    monkeypatch.setattr(checks_ci_parity, "_refresh_remote_base", refresh)
    with redirect_stdout(io.StringIO()) as captured:
        base = checks_ci_parity._base_ref_or_skip(REPO_ROOT, "test gate")
    assert base == "origin/main"
    assert refreshed == ["origin/main"]
    assert "could not refresh origin/main (offline)" in captured.getvalue()


def test_the_discriminator_scores_changed_files_including_untracked_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import checks_ci_parity

    argv: list[list[str]] = []

    def fake(command: list[str], **_kwargs: object) -> tuple[int, str, str]:
        argv.append(command)
        return 0, "", ""

    monkeypatch.setattr(checks_ci_parity, "_run_subprocess", fake)
    monkeypatch.setattr(
        checks_ci_parity,
        "_changed_paths_since_base",
        lambda _root, _label: ["templates/agents/new.md"],
    )
    assert checks_ci_parity.validate_agent_skill_discriminator(REPO_ROOT) is True
    assert "--changed-files" in argv[0]
    assert "templates/agents/new.md" in argv[0]
    assert "--all" not in argv[0]

    argv.clear()
    monkeypatch.setattr(checks_ci_parity, "_changed_paths_since_base", lambda _root, _label: None)
    assert checks_ci_parity.validate_agent_skill_discriminator(REPO_ROOT) is True
    assert "--all" in argv[0]
