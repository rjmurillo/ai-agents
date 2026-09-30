"""The bypass gate fails on an unlisted toggle, an unlisted continue-on-error, or an expired entry.

Issue #5636, decision D17. Every test builds a throwaway git repository, because
the gate reads the tracked tree at HEAD. The last test runs the gate on this
repository with today's date: an entry that expires is meant to fail the suite,
so the owner renews or removes it.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import check_bypass_allowlist as gate
from scripts.validation.bypass_allowlist import ALLOWLIST_RELATIVE_PATH, parse_allowlist
from scripts.validation.evidence import EvidenceState

REPO_ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 9, 30)
WORKFLOW = ".github/workflows/ci.yml"


def _git(root: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    _git(tmp_path, "init", "-q")
    for relpath, text in files.items():
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "init")
    return tmp_path


def _allow(*entries: dict[str, Any]) -> Any:
    return parse_allowlist({"schema_version": "1", "entries": list(entries)})


def _toggle(name: str, expires: str = "2026-12-31") -> dict[str, Any]:
    return {
        "kind": "toggle",
        "toggle": name,
        "reason": "r",
        "owner": "o",
        "expires": expires,
    }


def _step(job: str, step: str, expires: str = "2026-12-31") -> dict[str, Any]:
    return {
        "kind": "continue-on-error",
        "path": WORKFLOW,
        "job": job,
        "step": step,
        "reason": "r",
        "owner": "o",
        "expires": expires,
    }


def _workflow(*step_lines: str, job_lines: str = "") -> str:
    steps = "\n".join(step_lines)
    return f"on: push\njobs:\n  build:\n    runs-on: x\n{job_lines}    steps:\n{steps}\n"


def _run(root: Path, allowlist: Any) -> tuple[EvidenceState, str]:
    outcome, _ = gate.evaluate(root, allowlist, TODAY)
    return outcome.state, outcome.detail


# --- toggles ---------------------------------------------------------------


def test_a_listed_python_toggle_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"scripts/a.py": 'import os\nos.environ.get("SKIP_THING")\n'})

    state, detail = _run(root, _allow(_toggle("SKIP_THING")))

    assert state is EvidenceState.PASS
    assert "1 toggle(s)" in detail


def test_an_unlisted_python_toggle_fails_and_names_the_file(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"scripts/a.py": 'import os\nos.environ.get("SKIP_THING")\n'})

    state, detail = _run(root, _allow())

    assert state is EvidenceState.FAIL
    assert "unlisted toggle SKIP_THING used in scripts/a.py" in detail


def test_a_prefixed_toggle_is_found(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"x.sh": 'if [ "${AI_AGENTS_SKIP_X:-0}" = 1 ]; then :; fi\n'})

    state, detail = _run(root, _allow())

    assert state is EvidenceState.FAIL
    assert "AI_AGENTS_SKIP_X" in detail


@pytest.mark.parametrize(
    ("relpath", "text"),
    [
        ("lefthook.yml", 'skip:\n  - run: test "$SKIP_THING" = 1\n'),
        ("a.sh", "export SKIP_THING=0\n"),
        ("a.yml", "env:\n  SKIP_THING: '1'\n"),
        ("a.ps1", "$env:X = $SKIP_THING\n"),
    ],
)
def test_a_toggle_is_found_in_yaml_shell_and_powershell(
    tmp_path: Path, relpath: str, text: str
) -> None:
    root = _repo(tmp_path, {relpath: text})

    state, detail = _run(root, _allow())

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
    root = _repo(tmp_path, {relpath: text})

    state, detail = _run(root, _allow())

    assert state is EvidenceState.PASS, detail


def test_an_expired_toggle_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})

    state, detail = _run(root, _allow(_toggle("SKIP_THING", expires="2026-09-29")))

    assert state is EvidenceState.FAIL
    assert "toggle SKIP_THING expired 2026-09-29" in detail


def test_a_toggle_expiring_today_still_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})

    state, _ = _run(root, _allow(_toggle("SKIP_THING", expires="2026-09-30")))

    assert state is EvidenceState.PASS


# --- continue-on-error -----------------------------------------------------


def test_a_listed_step_passes(tmp_path: Path) -> None:
    body = _workflow(
        "      - name: Flaky\n        continue-on-error: true\n        run: x",
    )
    root = _repo(tmp_path, {WORKFLOW: body})

    state, detail = _run(root, _allow(_step("build", "Flaky")))

    assert state is EvidenceState.PASS
    assert "1 continue-on-error" in detail


def test_an_unlisted_step_fails_and_names_job_and_step(tmp_path: Path) -> None:
    body = _workflow("      - name: Flaky\n        continue-on-error: true\n        run: x")
    root = _repo(tmp_path, {WORKFLOW: body})

    state, detail = _run(root, _allow())

    assert state is EvidenceState.FAIL
    assert "unlisted continue-on-error" in detail
    assert "job 'build' step 'Flaky'" in detail


def test_an_expression_counts_as_enabled(tmp_path: Path) -> None:
    body = _workflow(
        "      - name: Maybe\n"
        "        continue-on-error: ${{ github.event_name == 'push' }}\n"
        "        run: x"
    )
    root = _repo(tmp_path, {WORKFLOW: body})

    state, _ = _run(root, _allow())

    assert state is EvidenceState.FAIL


@pytest.mark.parametrize("literal", ["false", "'false'", "False"])
def test_a_literal_false_is_not_an_exception(tmp_path: Path, literal: str) -> None:
    body = _workflow(f"      - name: Strict\n        continue-on-error: {literal}\n        run: x")
    root = _repo(tmp_path, {WORKFLOW: body})

    state, _ = _run(root, _allow())

    assert state is EvidenceState.PASS


def test_a_job_level_setting_is_keyed_with_an_empty_step(tmp_path: Path) -> None:
    body = _workflow("      - run: x", job_lines="    continue-on-error: true\n")
    root = _repo(tmp_path, {WORKFLOW: body})

    unlisted, detail = _run(root, _allow())
    listed, _ = _run(root, _allow(_step("build", "")))

    assert unlisted is EvidenceState.FAIL
    assert "job 'build' step ''" in detail
    assert listed is EvidenceState.PASS


def test_a_step_without_a_name_falls_back_to_its_id_then_its_index(tmp_path: Path) -> None:
    body = _workflow(
        "      - id: by-id\n        continue-on-error: true\n        run: x",
        "      - continue-on-error: true\n        run: y",
    )
    root = _repo(tmp_path, {WORKFLOW: body})

    state, detail = _run(root, _allow(_step("build", "by-id")))

    assert state is EvidenceState.FAIL
    assert "step '#1'" in detail
    assert "by-id" not in detail


def test_a_composite_action_step_is_found(tmp_path: Path) -> None:
    action = (
        "name: a\nruns:\n  using: composite\n  steps:\n"
        "    - name: Soft\n      continue-on-error: true\n      shell: bash\n      run: x\n"
    )
    root = _repo(tmp_path, {".github/actions/a/action.yml": action})

    state, detail = _run(root, _allow())

    assert state is EvidenceState.FAIL
    assert ".github/actions/a/action.yml job '(composite)' step 'Soft'" in detail


def test_a_nested_workflow_directory_is_not_a_workflow(tmp_path: Path) -> None:
    body = _workflow("      - name: X\n        continue-on-error: true\n        run: x")
    root = _repo(tmp_path, {".github/workflows/sub/ci.yml": body})

    state, _ = _run(root, _allow())

    assert state is EvidenceState.PASS


def test_an_expired_step_fails_closed(tmp_path: Path) -> None:
    body = _workflow("      - name: Flaky\n        continue-on-error: true\n        run: x")
    root = _repo(tmp_path, {WORKFLOW: body})

    state, detail = _run(root, _allow(_step("build", "Flaky", expires="2026-01-01")))

    assert state is EvidenceState.FAIL
    assert "expired 2026-01-01" in detail


# --- stale, unreadable, and configuration ----------------------------------


def test_a_stale_entry_is_reported_and_does_not_fail(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"a.py": "x = 1\n"})

    outcome, stale = gate.evaluate(root, _allow(_toggle("SKIP_GONE"), _step("j", "s")), TODAY)

    assert outcome.state is EvidenceState.PASS
    assert len(stale) == 2
    assert any("SKIP_GONE" in item for item in stale)


def test_a_python_file_that_does_not_parse_blocks_the_scan(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"a.py": "def broken(:\n"})

    outcome, _ = gate.evaluate(root, _allow(), TODAY)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == "entries.unreadable"
    assert "a.py does not parse" in outcome.detail


def test_a_workflow_that_is_not_yaml_blocks_the_scan(tmp_path: Path) -> None:
    root = _repo(tmp_path, {WORKFLOW: "jobs: [unclosed\n"})

    outcome, _ = gate.evaluate(root, _allow(), TODAY)

    assert outcome.state is EvidenceState.BLOCKED
    assert "is not YAML" in outcome.detail


def test_a_tracked_file_deleted_from_the_working_tree_is_skipped(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})
    (root / "a.sh").unlink()

    state, detail = _run(root, _allow())

    assert state is EvidenceState.PASS, detail


def test_a_tracked_file_that_cannot_be_read_blocks_the_scan(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"a.sh": "x\n"})
    (root / "a.sh").unlink()
    (root / "a.sh").mkdir()

    outcome, _ = gate.evaluate(root, _allow(), TODAY)

    assert outcome.state is EvidenceState.BLOCKED
    assert "a.sh unreadable" in outcome.detail


def test_a_directory_that_is_not_a_repository_blocks_the_scan(tmp_path: Path) -> None:
    outcome, _ = gate.evaluate(tmp_path, _allow(), TODAY)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == "listing.failed"


def test_a_missing_git_binary_blocks_the_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(gate.subprocess, "run", boom)

    outcome, _ = gate.evaluate(tmp_path, _allow(), TODAY)

    assert outcome.state is EvidenceState.BLOCKED
    assert "could not run" in outcome.detail


def test_a_git_timeout_blocks_the_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(gate.subprocess, "run", boom)

    outcome, _ = gate.evaluate(tmp_path, _allow(), TODAY)

    assert outcome.state is EvidenceState.BLOCKED


# --- the CLI: the process exit code is the contract ------------------------


def _write_allowlist(root: Path, *entries: dict[str, Any]) -> None:
    target = root / ALLOWLIST_RELATIVE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    document = {"schema_version": "1", "entries": list(entries)}
    target.write_text(json.dumps(document), encoding="utf-8")


def test_main_exits_zero_when_every_use_is_authorized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})
    _write_allowlist(root, _toggle("SKIP_THING"))

    rc = gate.main(["--repo-root", str(root), "--today", "2026-09-30"])

    assert rc == 0
    assert capsys.readouterr().out.startswith("[PASS] validate_bypass_allowlist")


def test_main_exits_one_on_an_unlisted_use(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})

    rc = gate.main(["--repo-root", str(root), "--today", "2026-09-30"])

    assert rc == 1
    out = capsys.readouterr().out
    assert out.startswith("[FAIL] validate_bypass_allowlist reason=violations.found")
    assert "findings=1" in out


def test_main_exits_one_on_an_expired_entry(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})
    _write_allowlist(root, _toggle("SKIP_THING", expires="2026-09-29"))

    assert gate.main(["--repo-root", str(root), "--today", "2026-09-30"]) == 1


def test_main_exits_two_on_an_invalid_allowlist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, {"a.sh": "x\n"})
    _write_allowlist(root, {"kind": "toggle", "toggle": "nope"})

    rc = gate.main(["--repo-root", str(root)])

    assert rc == 2
    assert "bypass allowlist is invalid" in capsys.readouterr().err


def test_main_exits_three_when_the_tree_cannot_be_read(tmp_path: Path) -> None:
    assert gate.main(["--repo-root", str(tmp_path)]) == 3


def test_main_prints_a_stale_notice_and_still_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, {"a.py": "x = 1\n"})
    _write_allowlist(root, _toggle("SKIP_GONE"))

    rc = gate.main(["--repo-root", str(root), "--today", "2026-09-30"])

    assert rc == 0
    assert "[NOTICE] stale allowlist entry" in capsys.readouterr().out


def test_main_keeps_a_newline_in_a_path_from_forging_a_second_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hostile = 'evil"\n::error::forged.sh'
    root = _repo(tmp_path, {hostile: "export SKIP_THING=0\n"})

    rc = gate.main(["--repo-root", str(root), "--today", "2026-09-30"])

    lines = capsys.readouterr().out.splitlines()
    assert rc == 1
    assert len(lines) == 1
    assert not any(line.startswith("::error::") for line in lines)


# --- this repository -------------------------------------------------------


def test_every_bypass_in_this_repository_is_authorized_and_unexpired() -> None:
    """Runs with the real date on purpose: an expired entry must fail the suite."""
    outcome = gate.validate_bypass_allowlist(REPO_ROOT)

    assert outcome.state is EvidenceState.PASS, outcome.report_line()
