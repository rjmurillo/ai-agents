"""Validation pipeline tests for ``new_pr.py``."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.new_pr_test_support import _completed, _mod

# Distinct SHAs so a test can tell the resolved head ref apart from local HEAD.
_HEAD_REF_SHA = "a" * 40
_LOCAL_HEAD_SHA = "b" * 40


def _is_rev_parse(cmd: list[str]) -> bool:
    """True when ``cmd`` resolves a ref to a commit."""
    return cmd[:2] == ["git", "rev-parse"]

# Import run_validations from new_pr_validations directly: these tests
# exercise the validation pipeline implementation, not the security
# boundary. Main's pr_validations.run_validations (exported by new_pr)
# deliberately skips repo-local validators at the push-pr boundary.
_val_path = (
    Path(__file__).resolve().parents[1]
    / '.claude' / 'skills' / 'github' / 'scripts' / 'pr'
    / 'new_pr_validations.py'
)
_val_spec = importlib.util.spec_from_file_location(
    '_test_new_pr_validations_mod', _val_path,
)
assert _val_spec is not None and _val_spec.loader is not None
_val_mod = importlib.util.module_from_spec(_val_spec)
_val_spec.loader.exec_module(_val_mod)
run_validations = _val_mod.run_validations


def _qa_evidence(log: Path) -> str | None:
    """Return the QA evidence path a session log names, when it names one."""
    try:
        data = json.loads(log.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    node: object = data
    for key in ("protocolCompliance", "sessionEnd", "qaValidation", "evidence"):
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, str) else None


def _session_log_with_present_qa_report(repo_root: Path) -> tuple[Path, str]:
    """Find a committed session log whose QA report is on disk, or skip.

    The QA-binding path only runs when the log names an existing report, so a
    test that exercises it needs a real pair rather than a synthetic log: the
    session schema is large and a hand-built fixture would drift from it.
    """
    sessions = sorted((repo_root / ".agents" / "sessions").glob("*.json"))
    for log in reversed(sessions):
        evidence = _qa_evidence(log)
        if evidence is None:
            continue
        report = repo_root / evidence
        if report.is_file():
            return log, evidence
    pytest.skip("no committed session log pairs with a present QA report")


def _head_commit(repo_root: Path) -> str:
    """Return this checkout's HEAD SHA."""
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("git rev-parse HEAD failed in this checkout")
    return completed.stdout.strip()


@contextlib.contextmanager
def _qa_bound_log(
    repo_root: Path,
    *,
    mutate: Callable[[dict], None] | None = None,
) -> Iterator[tuple[str, str, str]]:
    """Yield ``(identity, log_text, head)`` for a log the validator accepts.

    The body comes from a committed log that already pairs with a QA report,
    so the schema-heavy content is real rather than hand-written. Only the two
    things a committed log cannot carry are rewritten: ``endingCommit``, whose
    recorded SHA names a commit on the branch the log was written on and need
    not be an ancestor of this checkout's HEAD, and the QA evidence pointer,
    which is re-aimed at a throwaway report bound to the same commit.

    The report is written under the configured QA artifact root because
    ``validate_qa_report_evidence`` rejects evidence outside it, and removed
    again on exit so nothing is left in the working tree
    (`.claude/rules/testing.md` MUST NOT 4).
    """
    source, _ = _session_log_with_present_qa_report(repo_root)
    identity = source.relative_to(repo_root).as_posix()
    head = _head_commit(repo_root)
    data = json.loads(source.read_text(encoding="utf-8"))
    data["endingCommit"] = head
    qa_relative = ".agents/qa/.qa-report-new-pr-validations-test.md"
    data["protocolCompliance"]["sessionEnd"]["qaValidation"]["evidence"] = qa_relative
    if mutate is not None:
        mutate(data)

    qa_report = repo_root / qa_relative
    qa_report.parent.mkdir(parents=True, exist_ok=True)
    qa_report.write_text(
        "---\n"
        "qaVerdict: PASS\n"
        f"qaSessionLog: {identity}\n"
        f"qaCommit: {head}\n"
        "---\n\n"
        "# QA Report\n\nPASS\n",
        encoding="utf-8",
    )
    try:
        yield identity, json.dumps(data), head
    finally:
        qa_report.unlink(missing_ok=True)


class TestRunValidations:
    def test_no_agents_changes_skips(self, tmp_path):
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            run_validations(str(tmp_path), "main", "feat/branch")

    def test_skill_violation_scan_skipped_when_git_diff_fails(self, tmp_path, capsys):
        """A failed git diff must not trigger an unscoped skill scan."""
        skill_script = tmp_path / "scripts" / "detect_skill_violation.py"
        skill_script.parent.mkdir(parents=True)
        skill_script.write_text("# mock")
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(rc=128, stderr="fatal: bad revision")
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        assert not any(
            len(cmd) >= 2 and cmd[1] == str(skill_script) for cmd in calls
        )
        captured = capsys.readouterr()
        assert "git diff" in captured.err and "failed" in captured.err
        assert "Skipped: git diff failed" in captured.out
        assert "No .agents/ changes, skipping" not in captured.out

    def test_skill_violation_detection_scopes_to_changed_files(self, tmp_path):
        skill_script = tmp_path / "scripts" / "detect_skill_violation.py"
        skill_script.parent.mkdir(parents=True)
        skill_script.write_text("# mock")
        changed = "scripts/changed.py\ndocs/guide.md\n"
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        skill_calls = [
            call for call in calls if len(call) >= 2 and call[1] == str(skill_script)
        ]
        assert skill_calls == [
            [
                sys.executable,
                str(skill_script),
                "--file",
                "scripts/changed.py",
                "--file",
                "docs/guide.md",
            ]
        ]

    def test_skill_violation_scan_skipped_when_no_scannable_extension(
        self, tmp_path, capsys
    ):
        """Skip the scanner when every changed file is unscannable."""
        skill_script = tmp_path / "scripts" / "detect_skill_violation.py"
        skill_script.parent.mkdir(parents=True)
        skill_script.write_text("# mock")
        changed = "assets/logo.png\ndata/table.json\nMakefile\n"
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        assert not any(
            len(cmd) >= 2 and cmd[1] == str(skill_script) for cmd in calls
        )
        captured = capsys.readouterr()
        assert "No changed files with a scannable extension" in captured.out

    def test_skill_violation_scan_filters_unscannable_extensions(self, tmp_path):
        """Pass only scannable changed files to the skill scanner."""
        skill_script = tmp_path / "scripts" / "detect_skill_violation.py"
        skill_script.parent.mkdir(parents=True)
        skill_script.write_text("# mock")
        changed = (
            "scripts/mod.py\nassets/logo.png\ndocs/guide.md\n"
            "hooks/setup.ps1\ndata/x.json\n"
        )
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        skill_calls = [
            call for call in calls if len(call) >= 2 and call[1] == str(skill_script)
        ]
        assert skill_calls == [
            [
                sys.executable,
                str(skill_script),
                "--file",
                "scripts/mod.py",
                "--file",
                "docs/guide.md",
                "--file",
                "hooks/setup.ps1",
            ]
        ]

    def test_skill_scan_extensions_match_detector(self):
        """Keep the local extension set synchronized with the scanner."""
        detector_path = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "detect_skill_violation.py"
        )
        mod_key = "detect_skill_violation_drift_guard"
        spec = importlib.util.spec_from_file_location(mod_key, detector_path)
        assert spec is not None and spec.loader is not None
        detector = importlib.util.module_from_spec(spec)
        previous = sys.modules.get(mod_key)
        sys.modules[mod_key] = detector
        sys_path_snapshot = list(sys.path)
        try:
            spec.loader.exec_module(detector)
            assert _mod._SKILL_SCAN_EXTENSIONS == detector.VALID_EXTENSIONS
        finally:
            if previous is not None:
                sys.modules[mod_key] = previous
            else:
                sys.modules.pop(mod_key, None)
            sys.path[:] = sys_path_snapshot

    def test_agents_changed_with_session_log_runs_validator(self, tmp_path):
        changed = ".agents/sessions/2025-01-01-session-01.json\n"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")
        validator_ran = False

        # Dispatch on argv, not on call order: a positional side_effect list
        # silently shifts when a branch adds or skips one call
        # (`.claude/rules/testing.md` SHOULD 11).
        def fake_run(cmd, **kwargs):
            nonlocal validator_ran
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=0)
            if _is_rev_parse(cmd):
                return _completed(stdout=_HEAD_REF_SHA + "\n", rc=0)
            if cmd[:2] == ["git", "show"]:
                return _completed(stdout='{"ok": true}\n', rc=0)
            if "validate_session_json.py" in " ".join(cmd):
                validator_ran = True
                return _completed(rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        assert validator_ran

    def test_agents_changed_session_validation_fails_exits_1(self, tmp_path):
        changed = ".agents/sessions/2025-01-01-session-01.json\n"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=0)
            if _is_rev_parse(cmd):
                return _completed(stdout=_HEAD_REF_SHA + "\n", rc=0)
            if cmd[:2] == ["git", "show"]:
                return _completed(stdout='{"ok": false}\n', rc=0)
            if "validate_session_json.py" in " ".join(cmd):
                return _completed(rc=1, stderr="validation failed")
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            with pytest.raises(SystemExit) as exc:
                run_validations(str(tmp_path), "main", "feat/branch")
            assert exc.value.code == 1

    def test_session_log_read_from_branch_ref_not_working_tree(self, tmp_path):
        """Validate a branch session log even when it is not in the worktree."""
        changed = ".agents/sessions/2025-01-01-session-01.json\n"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")
        validated_paths: list[str] = []

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=0)
            if _is_rev_parse(cmd):
                return _completed(stdout=_HEAD_REF_SHA + "\n", rc=0)
            if cmd[:2] == ["git", "show"]:
                return _completed(stdout='{"session": 1}\n', rc=0)
            if cmd[0].endswith("python") or "validate_session_json.py" in " ".join(cmd):
                validated_paths.append(cmd[-1])
                return _completed(rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/not-checked-out")

        assert len(validated_paths) == 1
        assert Path(validated_paths[0]).parent == (
            tmp_path / ".agents" / "scratch" / "session-log-validation"
        )
        assert not Path(validated_paths[0]).name.endswith("session-01.json")

    def test_scratch_copy_carries_the_logical_session_identity(self, tmp_path):
        """The validator must learn the real path the scratch copy stands for.

        Without ``--session-log-identity`` the validator derives the session
        identity from the scratch filename, so ``session_qa_binding`` compares
        the QA report's recorded session against a random temp name and every
        QA-linked log is rejected (issue #4783).
        """
        session_log = ".agents/sessions/2025-01-01-session-01.json"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")
        validator_argv: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=f"{session_log}\n", rc=0)
            if _is_rev_parse(cmd):
                return _completed(stdout=_HEAD_REF_SHA + "\n", rc=0)
            if cmd[:2] == ["git", "show"]:
                return _completed(stdout='{"session": 1}\n', rc=0)
            if "validate_session_json.py" in " ".join(cmd):
                validator_argv.append(list(cmd))
                return _completed(rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/not-checked-out")

        assert len(validator_argv) == 1
        argv = validator_argv[0]
        assert "--session-log-identity" in argv
        assert argv[argv.index("--session-log-identity") + 1] == session_log
        # The scratch copy is still what gets read, and it stays last so the
        # positional argument is unambiguous.
        assert Path(argv[-1]).parent == (
            tmp_path / ".agents" / "scratch" / "session-log-validation"
        )

    def test_identity_is_the_newest_session_log_when_several_changed(self, tmp_path):
        """The identity must name the log actually copied, not the first match."""
        older = ".agents/sessions/2025-01-01-session-01.json"
        newer = ".agents/sessions/2025-01-02-session-10.json"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")
        shown: list[str] = []
        identities: list[str] = []

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=f"{newer}\n{older}\n", rc=0)
            if _is_rev_parse(cmd):
                return _completed(stdout=_HEAD_REF_SHA + "\n", rc=0)
            if cmd[:2] == ["git", "show"]:
                shown.append(cmd[2])
                return _completed(stdout='{"session": 10}\n', rc=0)
            if "validate_session_json.py" in " ".join(cmd):
                identities.append(cmd[cmd.index("--session-log-identity") + 1])
                return _completed(rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        assert identities == [newer]
        assert shown == [f"feat/branch:{newer}"]

    def test_session_validation_failure_prints_validator_output(
        self, tmp_path, capsys
    ):
        """A genuine mismatch still fails, and says what the validator found."""
        session_log = ".agents/sessions/2025-01-01-session-01.json"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")
        detail = (
            "QA report session log does not match current session: "
            ".agents/sessions/2025-01-02-session-02.json != " + session_log
        )

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=f"{session_log}\n", rc=0)
            if _is_rev_parse(cmd):
                return _completed(stdout=_HEAD_REF_SHA + "\n", rc=0)
            if cmd[:2] == ["git", "show"]:
                return _completed(stdout='{"session": 1}\n', rc=0)
            if "validate_session_json.py" in " ".join(cmd):
                return _completed(
                    stdout="NON_COMPLIANT: 1 error\n",
                    stderr=detail + "\n",
                    rc=1,
                )
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            with pytest.raises(SystemExit) as exc:
                run_validations(str(tmp_path), "main", "feat/branch")

        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "NON_COMPLIANT: 1 error" in captured.out
        assert detail in captured.err
        assert "Session End validation failed" in captured.err

    def test_identity_flag_changes_what_the_real_validator_binds_qa_against(self):
        """Run the canonical validator both ways over one scratch copy.

        The without-flag run is the negative control: it must produce the
        QA-binding mismatch that issue #4783 reports. The with-flag run over
        the identical bytes must not. Asserting only that the flag appears in
        the validator's source would pin the wiring to itself and prove
        nothing about behavior (`.claude/rules/canonical-source-mirror.md`).
        """
        repo_root = Path(__file__).resolve().parents[1]
        validator = repo_root / "scripts" / "validate_session_json.py"
        if not validator.is_file():
            pytest.skip("canonical validator not present in this checkout")

        source, evidence = _session_log_with_present_qa_report(repo_root)
        scratch_dir = repo_root / ".agents" / "scratch" / "session-log-validation"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        identity = source.relative_to(repo_root).as_posix()
        mismatch = "QA report session log does not match current session"

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix=".session-log-test-",
            dir=scratch_dir,
            delete=False,
        ) as tmp:
            tmp.write(source.read_text(encoding="utf-8"))
            scratch_copy = tmp.name

        def _validate(*extra: str) -> str:
            completed = subprocess.run(
                [sys.executable, str(validator), *extra, scratch_copy],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=repo_root,
                timeout=180,
            )
            return completed.stdout + completed.stderr

        try:
            without_flag = _validate()
            with_flag = _validate("--session-log-identity", identity)
        finally:
            Path(scratch_copy).unlink(missing_ok=True)

        assert "unrecognized arguments" not in with_flag
        assert mismatch in without_flag, (
            "negative control did not fire; the scratch copy no longer "
            f"triggers QA binding for {identity} (evidence {evidence})"
        )
        assert mismatch not in with_flag

    def test_validator_env_strips_the_git_hook_override_variables(
        self, tmp_path, monkeypatch
    ):
        """The validator shells out to git; an inherited GIT_DIR misaims it.

        Under lefthook, or in any shell that exported one of these, git inside
        the validator would read another repository: ``git rev-parse HEAD``
        returns the decoy commit and ``git merge-base --is-ancestor`` exits 128,
        which ``post_qa_code_changes`` turns into "Could not verify QA commit
        ancestry" and a rejected log.
        """
        overrides = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
        for name in overrides:
            monkeypatch.setenv(name, str(tmp_path / f"decoy-{name}"))
        session_log = ".agents/sessions/2025-01-01-session-01.json"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")
        validator_env: list[dict[str, str]] = []

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=f"{session_log}\n", rc=0)
            if _is_rev_parse(cmd):
                return _completed(stdout=_HEAD_REF_SHA + "\n", rc=0)
            if cmd[:2] == ["git", "show"]:
                return _completed(stdout='{"session": 1}\n', rc=0)
            if "validate_session_json.py" in " ".join(cmd):
                validator_env.append(kwargs["env"])
                return _completed(rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/not-checked-out")

        assert len(validator_env) == 1
        assert [name for name in overrides if name in validator_env[0]] == []
        # Control: the variables really were set, so an empty result above
        # cannot come from an environment that never carried them.
        assert all(name in os.environ for name in overrides)

    def test_validation_head_names_the_head_ref_not_local_head(self, tmp_path):
        """QA staleness must be checked against the branch the log came from.

        ``new_pr.py`` accepts an explicit ``--head <branch>`` that need not be
        checked out, and the log is read from that ref. Left to itself the
        validator resolves its validation head from local HEAD, so QA ancestry
        is compared against the wrong commit.
        """
        session_log = ".agents/sessions/2025-01-01-session-01.json"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")
        validator_argv: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=f"{session_log}\n", rc=0)
            if _is_rev_parse(cmd):
                if cmd[3].startswith("HEAD"):
                    return _completed(stdout=_LOCAL_HEAD_SHA + "\n", rc=0)
                return _completed(stdout=_HEAD_REF_SHA + "\n", rc=0)
            if cmd[:2] == ["git", "show"]:
                return _completed(stdout='{"session": 1}\n', rc=0)
            if "validate_session_json.py" in " ".join(cmd):
                validator_argv.append(list(cmd))
                return _completed(rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/not-checked-out")

        assert len(validator_argv) == 1
        argv = validator_argv[0]
        assert argv[argv.index("--validation-head") + 1] == _HEAD_REF_SHA
        assert _LOCAL_HEAD_SHA not in argv

    def test_unresolvable_head_skips_rather_than_binding_to_local_head(
        self, tmp_path, capsys
    ):
        """A head ref that will not resolve must not fall back to local HEAD."""
        session_log = ".agents/sessions/2025-01-01-session-01.json"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")
        validator_ran = False

        def fake_run(cmd, **kwargs):
            nonlocal validator_ran
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=f"{session_log}\n", rc=0)
            if _is_rev_parse(cmd):
                return _completed(rc=128, stderr="fatal: Needed a single revision")
            if cmd[:2] == ["git", "show"]:
                return _completed(stdout='{"session": 1}\n', rc=0)
            if "validate_session_json.py" in " ".join(cmd):
                validator_ran = True
                return _completed(rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/gone")

        assert validator_ran is False
        assert "could not resolve feat/gone" in capsys.readouterr().err

    def test_validator_output_reaches_the_author_on_a_passing_run(
        self, tmp_path, capsys
    ):
        """A COMPLIANT-with-warnings log must not validate silently.

        ``_run_warning_validator`` prints both streams before branching on the
        return code. Printing only on failure swallowed every warning the
        validator emits on this path, for example the ADR-102 comparison-head
        diagnostic and the branch-naming warning.
        """
        session_log = ".agents/sessions/2025-01-01-session-01.json"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")
        warning = "[WARN] Warnings:\n  - Branch 'x' doesn't follow conventional naming"

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=f"{session_log}\n", rc=0)
            if _is_rev_parse(cmd):
                return _completed(stdout=_HEAD_REF_SHA + "\n", rc=0)
            if cmd[:2] == ["git", "show"]:
                return _completed(stdout='{"session": 1}\n', rc=0)
            if "validate_session_json.py" in " ".join(cmd):
                return _completed(
                    stdout=f"[PASS] Session log is valid\n{warning}\n",
                    stderr="advisory detail\n",
                    rc=0,
                )
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        captured = capsys.readouterr()
        assert warning in captured.out
        assert "advisory detail" in captured.err
        assert "Session End validation failed" not in captured.err

    def test_real_validator_accepts_a_qa_linked_session_log(self):
        """The canonical validator returns 0 for a QA-bound log with the flag.

        The sibling flag test asserts a mismatch string is absent, which a
        run that fails for some other reason also satisfies. This one pins the
        outcome the fix exists to produce: exit code 0.
        """
        repo_root = Path(__file__).resolve().parents[1]
        validator = repo_root / "scripts" / "validate_session_json.py"
        if not validator.is_file():
            pytest.skip("canonical validator not present in this checkout")

        scratch_dir = repo_root / ".agents" / "scratch" / "session-log-validation"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        with _qa_bound_log(repo_root) as (identity, log_text, head):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                prefix=".session-log-accept-",
                dir=scratch_dir,
                delete=False,
            ) as tmp:
                tmp.write(log_text)
                scratch_copy = tmp.name
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(validator),
                        "--session-log-identity",
                        identity,
                        "--validation-head",
                        head,
                        scratch_copy,
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=repo_root,
                    timeout=180,
                )
            finally:
                Path(scratch_copy).unlink(missing_ok=True)

        assert completed.returncode == 0, completed.stdout + completed.stderr

    def test_real_validator_still_rejects_a_filename_number_mismatch(self):
        """The scratch copy must not disable the session-number check.

        ``validate_filename_number`` reads the number out of a filename. On a
        ref-backed copy the physical name is ``.session-log-<random>.json``,
        which carries none, so the check reported nothing and a run that
        examined nothing looked exactly like a run that passed.
        """
        repo_root = Path(__file__).resolve().parents[1]
        validator = repo_root / "scripts" / "validate_session_json.py"
        if not validator.is_file():
            pytest.skip("canonical validator not present in this checkout")

        def wrong_number(data: dict) -> None:
            data["session"]["number"] = data["session"]["number"] + 1

        scratch_dir = repo_root / ".agents" / "scratch" / "session-log-validation"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        with _qa_bound_log(repo_root, mutate=wrong_number) as (
            identity,
            log_text,
            head,
        ):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                prefix=".session-log-mismatch-",
                dir=scratch_dir,
                delete=False,
            ) as tmp:
                tmp.write(log_text)
                scratch_copy = tmp.name
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(validator),
                        "--session-log-identity",
                        identity,
                        "--validation-head",
                        head,
                        scratch_copy,
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=repo_root,
                    timeout=180,
                )
            finally:
                Path(scratch_copy).unlink(missing_ok=True)

        output = completed.stdout + completed.stderr
        assert completed.returncode == 1, output
        assert "filename" in output

    def test_run_validations_accepts_a_qa_linked_session_log(self):
        """End to end: the pipeline stops rejecting a QA-linked log.

        Only the git reads are faked. The validator subprocess runs for real,
        so this fails if the identity flag, the validation head, or the env
        stripping regress.
        """
        repo_root = Path(__file__).resolve().parents[1]
        if not (repo_root / "scripts" / "validate_session_json.py").is_file():
            pytest.skip("canonical validator not present in this checkout")

        real_run = subprocess.run
        with _qa_bound_log(repo_root) as (identity, log_text, head):

            def fake_run(cmd, **kwargs):
                if cmd[:3] == ["git", "diff", "--name-only"]:
                    return _completed(stdout=f"{identity}\n", rc=0)
                if _is_rev_parse(cmd):
                    return _completed(stdout=head + "\n", rc=0)
                if cmd[:2] == ["git", "show"]:
                    return _completed(stdout=log_text, rc=0)
                if "validate_session_json.py" in " ".join(str(part) for part in cmd):
                    return real_run(cmd, **kwargs)
                return _completed(rc=0)

            with patch("subprocess.run", side_effect=fake_run):
                run_validations(str(repo_root), "main", head)

    def test_session_log_missing_from_head_skips_validation(self, tmp_path, capsys):
        """Do not validate a stale worktree copy when the head lacks the log."""
        changed = ".agents/sessions/2025-01-01-session-01.json\n"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")
        stale = tmp_path / ".agents" / "sessions" / "2025-01-01-session-01.json"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text('{"stale": true}\n', encoding="utf-8")
        validator_ran = False

        def fake_run(cmd, **kwargs):
            nonlocal validator_ran
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=0)
            if _is_rev_parse(cmd):
                return _completed(stdout=_HEAD_REF_SHA + "\n", rc=0)
            if cmd[:2] == ["git", "show"]:
                return _completed(rc=128, stderr="path does not exist")
            if "validate_session_json.py" in " ".join(cmd):
                validator_ran = True
                return _completed(rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        assert validator_ran is False
        assert "not found at feat/branch" in capsys.readouterr().err

    def test_agents_changed_no_session_log_does_not_warn(self, tmp_path, capsys):
        """Session log creation is discontinued; absence is expected, not a warning."""
        changed = ".agents/HANDOFF.md\n"
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=changed, rc=0),
        ):
            run_validations(str(tmp_path), "main", "feat/branch")
        stderr = capsys.readouterr().err
        assert "No session log found" not in stderr

    def test_agents_changed_legacy_md_session_log_only_warns_once(
        self, tmp_path, capsys
    ):
        """A legacy log warning must not be followed by a missing-log warning."""
        changed = ".agents/sessions/2026-05-10-session-1830.md\n"
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=changed, rc=0),
        ):
            run_validations(str(tmp_path), "main", "feat/branch")
        stderr = capsys.readouterr().err
        assert "legacy .md session log" in stderr
        assert "No session log found" not in stderr

    def test_permission_error_on_mkdir_warns(self, tmp_path, capsys):
        with patch("os.makedirs", side_effect=PermissionError("denied")), patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            run_validations(str(tmp_path), "main", "feat/branch")
        stderr = capsys.readouterr().err
        assert "Could not create .agents directory" in stderr
