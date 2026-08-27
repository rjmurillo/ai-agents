"""Sweep every committed QA-linked session log through the identity flag.

``test_new_pr_session_validator_contract.py`` proves the fix on one log: the
first committed log it finds that pairs with a QA report on disk. That is
enough to show the wiring works and not enough to answer "does it work on the
logs this repository actually has", which is the question a reviewer asks when
the fix claims to close issue #4783.

The distinction matters because the obvious whole-corpus metric is misleading.
Measured on this branch at 09a8e9ae0, exit code 0 is reached by 0 of the 12
QA-linked logs both with the flag and without it, so a reviewer reading exit
code alone concludes the fix is inert. It is not. Those logs fail on an
unrelated precondition: their ``endingCommit`` names a squash-merged or
rebased SHA that no longer resolves, which the validator reports against issue
#3618. That failure sits upstream of QA binding and masks it.

The signal that is not masked is the QA-binding mismatch itself, and it
separates cleanly:

    QA-binding mismatch WITHOUT the flag: 12 of 12
    QA-binding mismatch WITH the flag:     0 of 12

This module pins both halves. The without-flag half is the negative control:
if it stops firing, the corpus no longer reproduces issue #4783 and the
with-flag half proves nothing on its own.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests.test_new_pr_session_validator_contract import _qa_evidence

# scripts/validate_session_json.py, validate_qa_report_evidence, verbatim:
#     "QA report session log does not match current session"
# This is the defect issue #4783 reports: the scratch copy carries no logical
# identity, so the report's recorded session is compared against a temp
# filename. Matching on the message rather than the exit code is deliberate
# per the module docstring; the exit code carries unrelated failures too.
_QA_BINDING_MISMATCH = "QA report session log does not match current session"


def _qa_linked_logs(repo_root: Path) -> list[Path]:
    """Return committed session logs whose named QA report is on disk.

    The QA-binding branch runs only when the evidence pointer resolves to a
    real file, so a log naming a report that was never committed cannot
    exercise the path and is not part of the corpus under test.
    """
    sessions_dir = repo_root / ".agents" / "sessions"
    if not sessions_dir.is_dir():
        return []
    linked: list[Path] = []
    for log in sorted(sessions_dir.glob("*.json")):
        evidence = _qa_evidence(log)
        if evidence is None:
            continue
        if (repo_root / evidence).is_file():
            linked.append(log)
    return linked


def _validate_scratch_copy(
    repo_root: Path,
    log: Path,
    *,
    with_identity: bool,
    head: str,
) -> str:
    """Run the canonical validator over a scratch copy of ``log``.

    Mirrors what ``_validate_session_end`` does in
    ``.claude/skills/github/scripts/pr/new_pr_validations.py``: the log is
    copied under a ``.session-log-`` prefixed temporary name inside the
    configured scratch directory, because the validator rejects a path outside
    the repository and configured sessions root. The name is unique per call so
    the suite stays safe under xdist.
    """
    scratch_dir = repo_root / ".agents" / "scratch" / "session-log-validation"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix=".session-log-corpus-",
        dir=scratch_dir,
        delete=False,
    ) as tmp:
        tmp.write(log.read_text(encoding="utf-8"))
        scratch_copy = tmp.name

    argv = [sys.executable, str(repo_root / "scripts" / "validate_session_json.py")]
    if with_identity:
        argv += ["--session-log-identity", log.relative_to(repo_root).as_posix()]
    argv += ["--validation-head", head, scratch_copy]
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=repo_root,
            timeout=180,
            check=False,
        )
    finally:
        os.unlink(scratch_copy)
    return completed.stdout + completed.stderr


@pytest.fixture(scope="module")
def _corpus() -> tuple[Path, list[Path], str]:
    """Yield ``(repo_root, qa_linked_logs, head)`` or skip when unavailable."""
    repo_root = Path(__file__).resolve().parents[1]
    if not (repo_root / "scripts" / "validate_session_json.py").is_file():
        pytest.skip("canonical validator not present in this checkout")
    logs = _qa_linked_logs(repo_root)
    if not logs:
        pytest.skip("no committed session log pairs with a present QA report")
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
    return repo_root, logs, completed.stdout.strip()


class TestQaBindingAcrossTheCommittedCorpus:
    def test_every_qa_linked_log_reproduces_the_defect_without_the_flag(self, _corpus) -> None:
        """Negative control: the corpus must still exhibit issue #4783.

        Without this half, the with-flag assertion below is satisfied by any
        change that stops QA binding from running at all, including deleting
        it. A guard that cannot fail is not a guard
        (`.claude/rules/ci-scripts.md` MUST 12).
        """
        repo_root, logs, head = _corpus
        unaffected = [
            log.name
            for log in logs
            if _QA_BINDING_MISMATCH
            not in _validate_scratch_copy(repo_root, log, with_identity=False, head=head)
        ]
        assert not unaffected, (
            "negative control did not fire for "
            f"{len(unaffected)} of {len(logs)} QA-linked logs: {unaffected}. "
            "The corpus no longer reproduces issue #4783, so the with-flag "
            "assertion proves nothing."
        )

    def test_no_qa_linked_log_mismatches_with_the_flag(self, _corpus) -> None:
        """The fix must clear the mismatch on every log, not just the first."""
        repo_root, logs, head = _corpus
        still_mismatching = [
            log.name
            for log in logs
            if _QA_BINDING_MISMATCH
            in _validate_scratch_copy(repo_root, log, with_identity=True, head=head)
        ]
        assert not still_mismatching, (
            f"{len(still_mismatching)} of {len(logs)} QA-linked logs still "
            f"report the QA-binding mismatch with --session-log-identity: "
            f"{still_mismatching}"
        )
