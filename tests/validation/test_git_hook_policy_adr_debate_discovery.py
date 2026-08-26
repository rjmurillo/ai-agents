"""Every staged path matching the log pattern must reach a decision.

Split out of ``test_git_hook_policy_adr_debate_evidence.py`` when that module
crossed the 500-line file-size rule for the third time on issue #5205. The seam
is one invariant rather than an arbitrary line: the sibling asks whether a log
that the gate *read* counts as evidence, and every case here asks whether a
staged path reaches the reading at all.

That distinction is the whole reason this file exists. Four of the eight
fail-opens on issue #5205 were the same mistake in four places, each found only
after the previous one was closed, because each fix was written against the
shape in front of it rather than against the invariant:

* an unreadable log dropped from the contents map,
* a symlink dropped by the regular-file filter,
* a type change dropped by the discovery filter,
* a blob that is not UTF-8 repaired into a document nobody wrote.

Each case here stages a *valid covering sibling* alongside the bad path, and
asserts the sibling really is sufficient on its own first. Without that, the
commit would block for the unrelated reason that nothing covers the staged id,
and the test would pass while the fail-open it names walked straight through.
That is not hypothetical: the original unreadable-log test asserted only the
exit code and was green for months against the two-log shape.

Issue #5205.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validation import git_hook_policy as policy
from tests.validation._adr_debate_repo import ADR_42, GENUINE_LOG, _edit, _git, _stage_log


def test_a_staged_symlink_blocks_even_when_a_sibling_covers_every_id(
    adr_debate_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail-open regression: a covering sibling must not excuse a symlink.

    Non-regular candidates used to be filtered out of the staged set before any
    evidence check ran. With one valid covering log staged beside the symlink
    there was nothing left to fail on, so the gate returned 0 and a staged
    ``*debate*.md`` symlink rode through on its sibling's evidence.

    Exactly the shape as the unreadable-log fail-open, one filter earlier.
    """
    if os.name == "nt":
        pytest.skip("Symlink creation requires elevated Windows privileges")

    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    _stage_log(adr_debate_repo, "ADR-042-debate-log.md", GENUINE_LOG)

    link = adr_debate_repo / ".agents" / "critique" / "ADR-042-second-debate.md"
    link.symlink_to("ADR-042-debate-log.md")
    _git(adr_debate_repo, "add", "--", link.relative_to(adr_debate_repo).as_posix())

    # The sibling really is sufficient on its own, so this fails open unless
    # the symlink is reported rather than filtered away.
    assert policy.debate_log_evidence_gap(GENUINE_LOG) is None

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 1
    error = capsys.readouterr().err
    assert "not a regular file" in error
    assert "ADR-042-second-debate.md" in error


def test_a_type_changed_log_blocks_even_when_a_sibling_covers_every_id(
    adr_debate_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail-open regression: converting a tracked log to a symlink stages as T.

    The non-regular-file check above was written for the add-a-symlink shape.
    Replacing an already tracked regular log with a symlink is the same attack
    one filter earlier: git reports it as a type change, and the staged-path
    query asked for ``ACMR``, so the converted path never reached the check at
    all. With a valid sibling covering every staged id, the gate returned 0.

    The staged status is asserted before the behavior. Without that, a future
    git that reported this as ``M`` would leave the test green while it had
    stopped exercising the filter it exists to pin.
    """
    if os.name == "nt":
        pytest.skip("Symlink creation requires elevated Windows privileges")

    tracked = _stage_log(adr_debate_repo, "ADR-042-debate-log.md", GENUINE_LOG)
    _git(adr_debate_repo, "commit", "-m", "add a debate log")

    (adr_debate_repo / tracked).unlink()
    (adr_debate_repo / tracked).symlink_to("ADR-042-review-debate-log.md")
    _git(adr_debate_repo, "add", "--", tracked)

    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    sibling = _stage_log(adr_debate_repo, "ADR-042-review-debate-log.md", GENUINE_LOG)

    status = _git(adr_debate_repo, "diff", "--cached", "--name-status").stdout
    assert f"T\t{tracked}" in status, status

    # The sibling really is sufficient on its own, so this fails open unless
    # the converted path is discovered and reported.
    assert policy.debate_log_evidence_gap(GENUINE_LOG) is None
    assert sibling != tracked

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 1
    error = capsys.readouterr().err
    assert "not a regular file" in error
    assert tracked in error


def test_a_log_that_is_not_utf8_blocks_even_when_a_sibling_covers_every_id(
    adr_debate_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail-open regression: invalid bytes used to be decoded away, not reported.

    Decoding the staged blob with ``errors="replace"`` destroyed the evidence
    that the bytes were invalid, and every signal then read a document the
    committer had not written. The measured attack corrupted one byte inside
    each of the canonical template's ten placeholder literals: the literals
    stopped matching while the headings, the roster column and the outcome line
    survived, so the unfilled template cleared the gate. The decode is strict
    now, and the path is named rather than silently repaired.

    Uses raw bytes rather than the template, since the contract being pinned is
    about the decode and not about any one document; the template shape itself
    is pinned in the mirrors module beside the fence it comes from.
    """
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    _stage_log(adr_debate_repo, "ADR-042-debate-log.md", GENUINE_LOG)

    bad = ".agents/critique/ADR-042-second-debate.md"
    corrupted = GENUINE_LOG.encode("utf-8").replace(b"architect", b"archit\xffct")
    (adr_debate_repo / bad).write_bytes(corrupted)
    _git(adr_debate_repo, "add", bad)

    # The sibling is genuinely sufficient on its own, so this fails open unless
    # the undecodable log is reported.
    assert policy.debate_log_evidence_gap(GENUINE_LOG) is None

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 1
    error = capsys.readouterr().err
    assert "could not be read" in error
    assert bad in error, "the error must name the log that would not decode"


def test_a_failed_regular_file_query_is_not_reported_as_a_symlink(
    adr_debate_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A broken `ls-files` must not accuse the committer of staging a symlink.

    The per-path query returned a bare False both for "not a regular blob" and
    for "could not look", and the gate reports the first as "not a regular
    file: a symlink is not review evidence" with exit 1. So a broken git named
    the committer's genuine log as a symlink. Same swallow as the discovery
    query, one function over, found one review round later.

    Fails the `ls-files` call specifically, not the discovery call, so the two
    paths are pinned apart rather than together.
    """
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    _stage_log(adr_debate_repo, "ADR-042-debate-log.md", GENUINE_LOG)

    real_run = policy._run_git

    def fail_only_ls_files(root: Path, args: list[str]) -> object:
        if args and args[0] == "ls-files":
            return subprocess.CompletedProcess(
                args, policy.GIT_FATAL_RETURNCODE, "", "fatal: not a git repository\n"
            )
        return real_run(root, args)

    monkeypatch.setattr(policy, "_run_git", fail_only_ls_files)

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 3
    error = capsys.readouterr().err
    assert "the git query failed" in error
    assert "fatal: not a git repository" in error
    assert "symlink" not in error, (
        "a failed query must not be reported as a non-regular file; the "
        "committer staged a genuine log"
    )


def test_a_path_missing_from_the_index_is_still_not_a_regular_file(
    adr_debate_repo: Path,
) -> None:
    """Exit 1 from `ls-files --error-unmatch` is an answer, not a failure.

    The paired negative for the tri-state. Only git's fatal 128 means "could
    not look"; a path simply absent from the index exits 1 and is a genuine
    False. Without this, widening the failure branch to every non-zero code
    would turn every unstaged path into an external error and the distinction
    would be noise.
    """
    assert policy._staged_regular_file_state(adr_debate_repo, "no-such-file.md") is False


def test_evidence_failures_keep_the_logic_exit_code(
    adr_debate_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The external code is only for the external failure.

    Paired with the discovery-failure case above. If every block returned 3 the
    distinction would be decorative, so this pins that a staged log which fails
    on its own evidence still exits 1: a judgement about the committer's work,
    not a broken tool.
    """
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    _stage_log(adr_debate_repo, "ADR-042-debate-log.md", "ADR-042")

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 1
    assert "shorter than" in capsys.readouterr().err


def test_a_failed_discovery_query_is_reported_as_a_failure_not_an_absence(
    adr_debate_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A git error must not report as "you staged no debate log".

    Both outcomes block, so this is diagnosability rather than a fail-open. It
    still matters: the absence message tells a committer who has already staged
    a log to go stage the log, which sends them looking for a file that is
    sitting in front of them. Asserting the exit code alone cannot tell the two
    apart, so this asserts the message.
    """
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    _stage_log(adr_debate_repo, "ADR-042-debate-log.md", GENUINE_LOG)

    real_run = policy._run_git

    def fail_the_discovery_query(root: Path, args: list[str]) -> object:
        if args[:3] == ["diff", "--cached", "--name-only"] and args[-1] == ".agents/critique":
            return subprocess.CompletedProcess(args, 128, "", "fatal: not a git repository\n")
        return real_run(root, args)

    monkeypatch.setattr(policy, "_run_git", fail_the_discovery_query)

    # 3, not 1. This function's return value is the process exit code, and
    # AGENTS.md:50 reserves 1 for a logic violation and 3 for an external
    # failure. Reporting a broken git query as 1 tells automation the
    # committer's evidence was rejected when nothing was ever examined.
    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 3
    error = capsys.readouterr().err
    assert "the git query failed" in error
    assert "fatal: not a git repository" in error, "git's own output must survive"
    assert "requires a debate log" not in error, (
        "a failed query must not be reported as a missing log; the committer "
        "staged one and would be sent to look for it"
    )


def test_an_unreadable_staged_log_cannot_satisfy_coverage(
    adr_debate_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A log whose index blob will not read is named and blocks."""
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    _stage_log(adr_debate_repo, "ADR-042-debate-log.md", GENUINE_LOG)

    monkeypatch.setattr(policy, "_read_index_blob", lambda *_args, **_kwargs: None)

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 1
    # Assert the reason, not just the exit code. Before unreadable logs were
    # reported, this blocked only as a side effect of supplying no coverage,
    # so the same 1 came back for a different reason and the case below passed
    # through the gate entirely.
    assert "could not be read" in capsys.readouterr().err


def test_an_unreadable_log_blocks_even_when_a_sibling_covers_every_id(
    adr_debate_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail-open regression: a covering sibling must not excuse an unreadable log.

    ``_staged_debate_log_contents`` used to drop an unreadable log silently.
    With one valid log covering every staged id, the drop left nothing to
    fail on: both checks passed on the sibling and the gate returned 0.
    Reproduced against this exact shape before the fix.

    Distinct from the single-log case above, which blocked for the unrelated
    reason that the dropped log supplied no coverage.
    """
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    good = _stage_log(adr_debate_repo, "ADR-042-debate-log.md", GENUINE_LOG)
    bad = _stage_log(adr_debate_repo, "ADR-042-second-debate.md", GENUINE_LOG)

    real_read = policy._read_index_blob

    def only_the_second_log_fails(root: Path, relative: str) -> bytes | None:
        return None if relative == bad else real_read(root, relative)

    monkeypatch.setattr(policy, "_read_index_blob", only_the_second_log_fails)

    # The sibling is genuinely sufficient on its own, so this fails open unless
    # the unreadable log is reported rather than skipped.
    assert policy.debate_log_evidence_gap(GENUINE_LOG) is None
    assert good != bad

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 1
    error = capsys.readouterr().err
    assert "could not be read" in error
    assert bad in error, "the error must name the log that would not read"
