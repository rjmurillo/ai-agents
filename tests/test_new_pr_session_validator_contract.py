"""What ``_validate_session_end`` hands the canonical session validator.

Split out of ``test_new_pr_validations.py`` so neither file crosses the
500-line taste ceiling. Two classes, two levels:

``TestSessionEndValidatorInvocation`` stubs the subprocess and pins the argv
and env the pipeline builds. ``TestRealSessionValidator`` spawns
``scripts/validate_session_json.py`` for real, so it fails when those flags
stop matching what the validator actually accepts.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.new_pr_test_support import _completed
from tests.test_new_pr_validations import (
    _HEAD_REF_SHA,
    _LOCAL_HEAD_SHA,
    _is_rev_parse,
    run_validations,
)


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
    (`.claude/rules/testing.md` MUST NOT 4). Its name is unique per call: the
    suite runs under xdist, and three cases build this fixture, so a fixed name
    would let one case's cleanup delete another case's report mid-run.
    """
    source, _ = _session_log_with_present_qa_report(repo_root)
    identity = source.relative_to(repo_root).as_posix()
    head = _head_commit(repo_root)
    data = json.loads(source.read_text(encoding="utf-8"))
    data["endingCommit"] = head

    qa_dir = repo_root / ".agents" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".md",
        prefix=".qa-report-test-",
        dir=qa_dir,
        delete=False,
    ) as report:
        report.write(
            "---\n"
            "qaVerdict: PASS\n"
            f"qaSessionLog: {identity}\n"
            f"qaCommit: {head}\n"
            "---\n\n"
            "# QA Report\n\nPASS\n"
        )
        qa_report = Path(report.name)

    evidence = qa_report.relative_to(repo_root).as_posix()
    data["protocolCompliance"]["sessionEnd"]["qaValidation"]["evidence"] = evidence
    if mutate is not None:
        mutate(data)
    try:
        yield identity, json.dumps(data), head
    finally:
        qa_report.unlink(missing_ok=True)


class TestSessionEndValidatorInvocation:
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


class TestRealSessionValidator:
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
