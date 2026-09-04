"""The `dash-prohibition` pre-push job, from `lefthook.yml` down to git.

Issue #5086. The em/en-dash prohibition (`.claude/rules/universal.md` MUST NOT
4) is the repository's most-flagged defect class, and until this job existed the
branch-wide scan ran only inside `pre-pr-validation`, in the expensive pre-push
stage. A one-character violation was therefore reported after every fast gate
and most of the expensive ones had already run.

The tests drive the subcommand named by the job's own `run:` string, so a
change that keeps the job but points it somewhere else fails here rather than
passing on a name match. Git is the boundary being exercised and is not mocked;
only `_resolve_branch_base_ref` is, because base-ref resolution has its own
coverage and reaches the network through `gh pr view`.

Coverage:

- positive: an authored markdown file carrying U+2014 fails the job.
- negative: a clean branch passes, and the `tests/hooks/fixtures/` carve-out
  keeps passing even when those fixtures carry the prohibited bytes.
- edge: a violation in a vendored path does not fail the job.
- negative control: with the validator stubbed out, the file that fails above
  passes, so the exit code comes from the check rather than from anything else
  the job does.
- wiring: the job is unconditional, and `pre_pr.py` defers its own gate to
  exactly this job (issue #5317: a glob-skipped lefthook job is
  indistinguishable from a passed one, so a deferral target must not carry a
  glob).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.ci.count_ratchet_git_harness import commit_all, git_stdout, init_repo

REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = REPO_ROOT / "lefthook.yml"
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import checks_dash  # noqa: E402
import git_hook_policy  # noqa: E402
import pre_pr_sequence  # noqa: E402

JOB_NAME = "dash-prohibition"
GATE_NAME = "Em/en-dash Prohibition"

# Written as escapes so this file does not itself carry the prohibited bytes;
# `checks_dash.py` spells its own regex the same way (issue #1923, REQ-006).
EM_DASH = "\u2014"
EN_DASH = "\u2013"


def _flatten(entry: dict[str, Any]) -> list[dict[str, Any]]:
    group = entry.get("group")
    if not isinstance(group, dict):
        return [entry]
    out: list[dict[str, Any]] = []
    for job in group.get("jobs", []):
        if isinstance(job, dict):
            out.extend(_flatten(job))
    return out


def _pre_push_job(name: str) -> dict[str, Any]:
    config = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    for entry in config["pre-push"]["jobs"]:
        if not isinstance(entry, dict):
            continue
        for job in _flatten(entry):
            if job.get("name") == name:
                return job
    raise AssertionError(f"{name!r} is not a pre-push job in lefthook.yml.")


def _subcommand_from_the_job() -> str:
    """The subcommand `lefthook.yml` actually runs, not one this module names.

    Reading it from the config is what ties the behavior below to the shipped
    job. Asserting on a hardcoded string would still pass if someone repointed
    the job at a different command.
    """
    run = str(_pre_push_job(JOB_NAME).get("run", ""))
    tail = run.split("git_hook_policy.py", 1)
    assert len(tail) == 2, (
        f"{JOB_NAME!r} no longer runs git_hook_policy.py: run={run!r}. The "
        "container bound in tests/ci/test_lefthook_container_bound.py credits "
        "this job with that module's self-imposed watchdog."
    )
    words = tail[1].split()
    assert words, f"{JOB_NAME!r} passes git_hook_policy.py no subcommand: {run!r}"
    return words[0]


def _repo_with(tmp_path: Path, files: dict[str, str]) -> tuple[Path, str]:
    """A repo whose base commit is clean and whose branch adds ``files``."""
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    commit_all(repo, "base")
    base = git_stdout(repo, "rev-parse", "HEAD")
    for relpath, text in files.items():
        target = repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    commit_all(repo, "branch work")
    return repo, base


def _run_job(repo: Path) -> int:
    return git_hook_policy.main(["--repo-root", str(repo), _subcommand_from_the_job()])


@pytest.fixture
def pinned_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route the scan's base-ref resolution at the fixture repo's base commit.

    The real resolver consults `gh pr view` and the checkout's remotes, neither
    of which exists in a `tmp_path` repository.
    """

    def _resolve(repo_root: Path) -> str:
        return git_stdout(repo_root, "rev-parse", "HEAD~1")

    monkeypatch.setattr(checks_dash, "_resolve_branch_base_ref", _resolve)


class TestTheJobCatchesWhatItIsFor:
    def test_an_authored_markdown_dash_fails_the_job(
        self, tmp_path: Path, pinned_base: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo, _ = _repo_with(tmp_path, {"docs/guide.md": f"one{EM_DASH}two\n"})
        assert _run_job(repo) == 1
        assert "docs/guide.md:1" in capsys.readouterr().out

    def test_an_en_dash_fails_too(self, tmp_path: Path, pinned_base: None) -> None:
        repo, _ = _repo_with(tmp_path, {"docs/guide.md": f"pages 1{EN_DASH}9\n"})
        assert _run_job(repo) == 1

    def test_a_clean_branch_passes(self, tmp_path: Path, pinned_base: None) -> None:
        repo, _ = _repo_with(tmp_path, {"docs/guide.md": "no prohibited bytes\n"})
        assert _run_job(repo) == 0


class TestTheCarveOutsSurvive:
    """`tests/hooks/fixtures/` carries the prohibited bytes on purpose."""

    def test_the_fixture_prefix_stays_exempt(
        self, tmp_path: Path, pinned_base: None
    ) -> None:
        repo, _ = _repo_with(
            tmp_path,
            {"tests/hooks/fixtures/dashy.md": f"fixture{EM_DASH}content\n"},
        )
        assert _run_job(repo) == 0, (
            "tests/hooks/fixtures/ must stay exempt: those files carry U+2014 "
            "and U+2013 to exercise the detection logic, and flagging them "
            "would fail every push that touches the dash-guard test suite "
            "(.claude/rules/universal.md MUST NOT 4 carve-out)."
        )

    def test_a_vendored_path_stays_exempt(
        self, tmp_path: Path, pinned_base: None
    ) -> None:
        repo, _ = _repo_with(
            tmp_path, {"node_modules/pkg/README.md": f"vendor{EM_DASH}text\n"}
        )
        assert _run_job(repo) == 0

    def test_the_carve_out_does_not_swallow_a_sibling_path(
        self, tmp_path: Path, pinned_base: None
    ) -> None:
        """Control for the two above: the prefix match must not be a substring.

        A file whose path merely contains the fixture directory's name is
        authored content and must still fail, or the exemptions above would be
        passing for the wrong reason.
        """
        repo, _ = _repo_with(
            tmp_path, {"docs/tests/hooks/fixtures/note.md": f"a{EM_DASH}b\n"}
        )
        assert _run_job(repo) == 1


class TestTheFailureComesFromTheCheck:
    def test_stubbing_the_validator_out_makes_the_failing_case_pass(
        self, tmp_path: Path, pinned_base: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: remove the check and the job stops failing.

        Without this, every assertion above would hold just as well if the job
        exited non-zero for some unrelated reason.
        """
        repo, _ = _repo_with(tmp_path, {"docs/guide.md": f"one{EM_DASH}two\n"})
        assert _run_job(repo) == 1
        monkeypatch.setattr(
            checks_dash, "validate_dash_prohibition", lambda _root: True
        )
        assert _run_job(repo) == 0


class TestTheDeferralIsSound:
    """Issue #5317: `pre_pr.py` may skip a gate only for an unconditional job."""

    def test_the_pre_pr_gate_defers_to_this_job(self) -> None:
        gates = {
            gate.name: gate.already_run_by
            for gate in pre_pr_sequence._SEQUENCE
            if gate.already_run_by
        }
        assert gates.get(GATE_NAME) == JOB_NAME, (
            f"{GATE_NAME!r} must defer to {JOB_NAME!r}, or the branch-wide "
            "scan runs twice on every push."
        )

    def test_the_job_is_unconditional(self) -> None:
        job = _pre_push_job(JOB_NAME)
        assert job.get("glob") is None and job.get("exclude") is None, (
            f"{JOB_NAME!r} carries a path filter, so it can be skipped on a "
            "push. A skipped lefthook job is indistinguishable from a passed "
            f"one, so {GATE_NAME!r} in pre_pr_sequence must stop deferring to "
            "it (issue #5317). The fixture and vendored carve-outs belong in "
            "checks_dash._VENDORED_PREFIXES, which is where they are."
        )

    def test_the_lookup_rejects_a_job_that_is_not_there(self) -> None:
        with pytest.raises(AssertionError, match="no-such-job"):
            _pre_push_job("no-such-job")
