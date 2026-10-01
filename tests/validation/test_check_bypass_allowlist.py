"""The bypass gate fails on an unlisted toggle, an unlisted continue-on-error, or an expired entry.

Issue #5636, decision D17. Every test builds a throwaway git repository, because
the gate reads the tracked tree at HEAD.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pytest

from scripts.validation import check_bypass_allowlist as gate
from scripts.validation.evidence import EvidenceState
from tests.validation.bypass_gate_helpers import (
    TODAY,
    WORKFLOW,
    allow,
    git,
    make_repo,
    run_gate,
    step,
    toggle,
    workflow,
)

# --- toggles ---------------------------------------------------------------


def test_a_listed_python_toggle_passes(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"scripts/a.py": 'import os\nos.environ.get("SKIP_THING")\n'})

    state, detail = run_gate(root, allow(toggle("SKIP_THING")))

    assert state is EvidenceState.PASS
    assert "1 toggle(s)" in detail


def test_an_unlisted_python_toggle_fails_and_names_the_file(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"scripts/a.py": 'import os\nos.environ.get("SKIP_THING")\n'})

    state, detail = run_gate(root, allow())

    assert state is EvidenceState.FAIL
    assert "unlisted toggle SKIP_THING used in scripts/a.py" in detail


def test_a_prefixed_toggle_is_found(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"x.sh": 'if [ "${AI_AGENTS_SKIP_X:-0}" = 1 ]; then :; fi\n'})

    state, detail = run_gate(root, allow())

    assert state is EvidenceState.FAIL
    assert "AI_AGENTS_SKIP_X" in detail


@pytest.mark.parametrize(
    ("relpath", "text"),
    [
        ("lefthook.yml", 'skip:\n  - run: test "$SKIP_THING" = 1\n'),
        ("a.sh", "export SKIP_THING=0\n"),
        ("a.yml", "env:\n  SKIP_THING: '1'\n"),
        ("a.ps1", "$env:X = $SKIP_THING\n"),
        ("a.ps1", '$env:SKIP_THING = "1"\n'),
        ("a.yml", "if: env.SKIP_THING == '1'\n"),
        ("a.yml", "run: echo ${{ env.SKIP_THING }}\n"),
        ("a.json", '{"SKIP_THING": "1"}\n'),
        ("a.yml", "env: {SKIP_THING: 1}\n"),
        ("a.sh", "SKIP_THING = 1\n"),
        ("a.sh", "printenv SKIP_THING\n"),
    ],
)
def test_a_toggle_is_found_in_yaml_shell_and_powershell(
    tmp_path: Path, relpath: str, text: str
) -> None:
    root = make_repo(tmp_path, {relpath: text})

    state, detail = run_gate(root, allow())

    assert state is EvidenceState.FAIL
    assert "SKIP_THING" in detail


@pytest.mark.parametrize(
    ("relpath", "text"),
    [
        ("scripts/a.py", '"""Set SKIP_THING to skip the check."""\nSKIP_DIRS = {"x"}\n'),
        ("scripts/a.py", "# SKIP_THING in a comment\nx = 1\n"),
        ("a.sh", "# export SKIP_THING=1\n"),
        ("a.yml", "# SKIP_THING: 1\nkey: value\n"),
        ("README.md", "export SKIP_THING=1\n"),
        ("tests/test_a.py", 'x = "SKIP_THING"\n'),
        ("docs/a.yml", "SKIP_THING: 1\n"),
        ("src/a.py", 'x = "SKIP_THING"\n'),
        ("templates/a.yml", "SKIP_THING: 1\n"),
        ("a.txt", "SKIP_THING=1\n"),
    ],
)
def test_prose_comments_constants_and_skipped_paths_are_not_toggles(
    tmp_path: Path, relpath: str, text: str
) -> None:
    root = make_repo(tmp_path, {relpath: text})

    state, detail = run_gate(root, allow())

    assert state is EvidenceState.PASS, detail


def test_an_expired_toggle_fails_closed(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})

    state, detail = run_gate(root, allow(toggle("SKIP_THING", expires="2026-09-29")))

    assert state is EvidenceState.FAIL
    assert "toggle SKIP_THING expired 2026-09-29" in detail


def test_a_toggle_expiring_today_still_passes(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})

    state, _ = run_gate(root, allow(toggle("SKIP_THING", expires="2026-09-30")))

    assert state is EvidenceState.PASS


# --- continue-on-error -----------------------------------------------------


def test_a_listed_step_passes(tmp_path: Path) -> None:
    body = workflow(
        "      - name: Flaky\n        continue-on-error: true\n        run: x",
    )
    root = make_repo(tmp_path, {WORKFLOW: body})

    state, detail = run_gate(root, allow(step("build", "Flaky")))

    assert state is EvidenceState.PASS
    assert "1 continue-on-error" in detail


def test_an_unlisted_step_fails_and_names_job_and_step(tmp_path: Path) -> None:
    body = workflow("      - name: Flaky\n        continue-on-error: true\n        run: x")
    root = make_repo(tmp_path, {WORKFLOW: body})

    state, detail = run_gate(root, allow())

    assert state is EvidenceState.FAIL
    assert "unlisted continue-on-error" in detail
    assert "job 'build' step 'Flaky'" in detail


def test_an_expression_counts_as_enabled(tmp_path: Path) -> None:
    body = workflow(
        "      - name: Maybe\n"
        "        continue-on-error: ${{ github.event_name == 'push' }}\n"
        "        run: x"
    )
    root = make_repo(tmp_path, {WORKFLOW: body})

    state, _ = run_gate(root, allow())

    assert state is EvidenceState.FAIL


@pytest.mark.parametrize("literal", ["false", "'false'", "False"])
def test_a_literal_false_is_not_an_exception(tmp_path: Path, literal: str) -> None:
    body = workflow(f"      - name: Strict\n        continue-on-error: {literal}\n        run: x")
    root = make_repo(tmp_path, {WORKFLOW: body})

    state, _ = run_gate(root, allow())

    assert state is EvidenceState.PASS


def test_a_job_level_setting_is_keyed_with_an_empty_step(tmp_path: Path) -> None:
    body = workflow("      - run: x", job_lines="    continue-on-error: true\n")
    root = make_repo(tmp_path, {WORKFLOW: body})

    unlisted, detail = run_gate(root, allow())
    listed, _ = run_gate(root, allow(step("build", "")))

    assert unlisted is EvidenceState.FAIL
    assert "job 'build' step ''" in detail
    assert listed is EvidenceState.PASS


def test_a_step_without_a_name_falls_back_to_its_id_then_its_index(tmp_path: Path) -> None:
    body = workflow(
        "      - id: by-id\n        continue-on-error: true\n        run: x",
        "      - continue-on-error: true\n        run: y",
    )
    root = make_repo(tmp_path, {WORKFLOW: body})

    state, detail = run_gate(root, allow(step("build", "by-id")))

    assert state is EvidenceState.FAIL
    assert "step '#1'" in detail
    assert "by-id" not in detail


def test_a_composite_action_step_is_found(tmp_path: Path) -> None:
    action = (
        "name: a\nruns:\n  using: composite\n  steps:\n"
        "    - name: Soft\n      continue-on-error: true\n      shell: bash\n      run: x\n"
    )
    root = make_repo(tmp_path, {".github/actions/a/action.yml": action})

    state, detail = run_gate(root, allow())

    assert state is EvidenceState.FAIL
    assert ".github/actions/a/action.yml job '(composite)' step 'Soft'" in detail


def test_a_nested_workflow_directory_is_not_a_workflow(tmp_path: Path) -> None:
    body = workflow("      - name: X\n        continue-on-error: true\n        run: x")
    root = make_repo(tmp_path, {".github/workflows/sub/ci.yml": body})

    state, _ = run_gate(root, allow())

    assert state is EvidenceState.PASS


def test_an_expired_step_fails_closed(tmp_path: Path) -> None:
    body = workflow("      - name: Flaky\n        continue-on-error: true\n        run: x")
    root = make_repo(tmp_path, {WORKFLOW: body})

    state, detail = run_gate(root, allow(step("build", "Flaky", expires="2026-01-01")))

    assert state is EvidenceState.FAIL
    assert "expired 2026-01-01" in detail


def test_two_same_named_advisory_steps_in_one_job_are_flagged(tmp_path: Path) -> None:
    same = "      - name: Same\n        continue-on-error: true\n        run: x"
    root = make_repo(tmp_path, {WORKFLOW: workflow(same, same)})

    state, detail = run_gate(root, allow(step("build", "Same")))

    assert state is EvidenceState.FAIL
    assert "2 continue-on-error steps share" in detail


def test_a_far_future_expiry_is_refused(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})

    state, detail = run_gate(root, allow(toggle("SKIP_THING", expires="9999-12-31")))

    assert state is EvidenceState.FAIL
    assert "more than 370 days out (SKIP_THING)" in detail


def test_an_expiry_at_the_horizon_is_accepted(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})
    limit = date.fromordinal(TODAY.toordinal() + gate.MAX_EXPIRY_DAYS).isoformat()

    state, _ = run_gate(root, allow(toggle("SKIP_THING", expires=limit)))

    assert state is EvidenceState.PASS


def test_a_far_future_step_expiry_is_refused(tmp_path: Path) -> None:
    body = workflow("      - name: Flaky\n        continue-on-error: true\n        run: x")
    root = make_repo(tmp_path, {WORKFLOW: body})

    state, detail = run_gate(root, allow(step("build", "Flaky", expires="9999-12-31")))

    assert state is EvidenceState.FAIL
    assert "days out" in detail


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks")
def test_a_tracked_symlink_is_skipped_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside.sh"
    outside.write_text("export SKIP_THING=0\n", encoding="utf-8")
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "link.sh").symlink_to(outside)
    git(repo_dir, "init", "-q")
    git(repo_dir, "add", "-A")
    git(repo_dir, "commit", "-q", "-m", "init")

    state, detail = run_gate(repo_dir, allow())

    assert state is EvidenceState.PASS, detail


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file names")
def test_a_file_name_that_is_not_utf8_is_still_scanned(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    name = os.fsdecode(b"bad\xffname.sh")
    (tmp_path / name).write_text("export SKIP_THING=0\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")

    state, detail = run_gate(tmp_path, allow())

    assert state is EvidenceState.FAIL
    assert "SKIP_THING" in detail


def test_the_result_names_the_working_tree_as_its_revision(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"a.py": "x = 1\n"})

    outcome, _ = gate.evaluate(root, allow(), TODAY)

    assert outcome.revision == "WORKING_TREE"
