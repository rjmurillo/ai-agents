"""Guards for the shallow-graft class of CI defect (issue #4572).

A `git fetch --depth=1` does not merely limit one fetch. It writes
`.git/shallow`, which git shares across the whole repository and every
worktree, and it severs ancestry traversal for every later step in the same
job. A subsequent full fetch does not remove the graft; only `--unshallow`
does.

That makes the trap invisible at the step that pays for it. The step that
writes the graft succeeds, and a different step further down the job fails, or
worse, silently measures the wrong range. Two consumers in this repository were
corrupted this way:

* `git merge-tree` aborts with "refusing to merge unrelated histories" (rc 128).
* A two-dot diff range widens from the branch's own commits to everything that
  differs between the base tip and the branch.

Measured on a complete clone of this repository, before and after a single
`git fetch --depth=1 origin main`, with no other change:

    git rev-list base..head           0 commits  ->  2263 commits
    git diff --name-only base..head   0 paths    ->  290 paths
    git merge-tree --write-tree       rc 0       ->  rc 128
    git merge-base base head          rc 0       ->  rc 1

The tests here pin the two halves of the remedy: workflows must not write the
graft, and the CI entrypoints that resolve a range must refuse to answer when
the graft is present rather than answering wrongly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
POLICY = REPO_ROOT / "scripts" / "validation" / "git_hook_policy.py"

DEFAULT_CHECKOUT_DEPTH = 1


def _jobs(document: object) -> dict[str, dict[str, object]]:
    if not isinstance(document, dict):
        return {}
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return {}
    return {name: job for name, job in jobs.items() if isinstance(job, dict)}


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    steps = job.get("steps")
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict)]


def _checkout_depths(job: dict[str, object]) -> set[object]:
    """Every `fetch-depth` the job's checkout steps request.

    An absent `fetch-depth` is the action's default of 1, which is itself
    shallow, so it is reported as 1 rather than dropped.
    """
    depths: set[object] = set()
    for step in _steps(job):
        uses = step.get("uses")
        if not isinstance(uses, str) or "actions/checkout" not in uses:
            continue
        with_block = step.get("with")
        if not isinstance(with_block, dict):
            depths.add(DEFAULT_CHECKOUT_DEPTH)
            continue
        depths.add(with_block.get("fetch-depth", DEFAULT_CHECKOUT_DEPTH))
    return depths


def _depth_limited_fetches(job: dict[str, object]) -> list[tuple[str, str]]:
    """Uncommented `git fetch` lines in the job that pass a `--depth` flag."""
    found: list[tuple[str, str]] = []
    for step in _steps(job):
        run = step.get("run")
        if not isinstance(run, str):
            continue
        name = step.get("name")
        for raw_line in run.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "git fetch" in line and "--depth" in line:
                found.append((str(name), line))
    return found


def _workflow_documents() -> list[tuple[Path, object]]:
    documents: list[tuple[Path, object]] = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        documents.append((path, yaml.safe_load(path.read_text(encoding="utf-8"))))
    return documents


def test_workflow_directory_is_not_empty() -> None:
    """Scope control for the invariant below (testing rule 10).

    A zero-finding sweep proves nothing when the examined count is unknown, and
    a glob that stops matching would make the next test vacuous while still
    reporting green.
    """
    documents = _workflow_documents()
    assert len(documents) >= 10, (
        f"expected the workflow sweep to examine files, saw {len(documents)}"
    )
    assert sum(len(_jobs(doc)) for _, doc in documents) >= 10


def test_no_job_mixes_a_full_checkout_with_a_depth_limited_fetch() -> None:
    """Issue #4572: the graft is written by a step that does not pay for it.

    Scoped to jobs that already check out at `fetch-depth: 0`, because there a
    `--depth=1` fetch is pure downside: the history is present already, so the
    flag saves no bandwidth and its only observable effect is the graft. A job
    that deliberately checks out shallow is left alone; it has made a different
    trade knowingly.
    """
    offenders: list[str] = []
    examined = 0
    for path, document in _workflow_documents():
        for job_name, job in _jobs(document).items():
            examined += 1
            if 0 not in _checkout_depths(job):
                continue
            for step_name, line in _depth_limited_fetches(job):
                offenders.append(f"{path.name}::{job_name} step {step_name!r}: {line}")

    assert examined >= 10, f"sweep examined only {examined} jobs"
    assert not offenders, (
        "a job checks out at fetch-depth 0 and then fetches with --depth, which "
        "writes .git/shallow for the rest of the job and severs ancestry for "
        "every later step (issue #4572). Drop the --depth flag:\n  "
        + "\n  ".join(offenders)
    )


def _git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")


@pytest.fixture
def graftable_clone(tmp_path: Path) -> tuple[Path, Path]:
    """An origin with two commits on main and a full clone of it.

    The clone starts complete, so a test can graft it with one fetch and
    compare against its own ungrafted control rather than against an assumption.
    """
    origin = tmp_path / "origin"
    _init(origin)
    (origin / "seed.py").write_text("x = 1\n", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "seed")
    (origin / "later.py").write_text("y = 2\n", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "later")

    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    _git(clone, "config", "user.email", "t@example.com")
    _git(clone, "config", "user.name", "t")
    return origin, clone


def _run_policy(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Drive the real CLI entrypoint against ``repo`` and return the result.

    `--repo-root` defaults to the directory the script itself lives in, which in
    CI is the checkout under test but in a test is this repository. Passing it
    explicitly is what points the gate at the scratch clone; without it every
    assertion below would measure ai-agents and pass for the wrong reason.

    Testing rule 8: the workflow step runs this program under `set -e`, so the
    contract under test is the process exit status, not a helper's return value.
    """
    return subprocess.run(
        [sys.executable, str(POLICY), "--repo-root", str(repo), *argv],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_suppression_diff_answers_on_a_complete_clone(
    graftable_clone: tuple[Path, Path],
) -> None:
    """Negative control for the graft test below.

    Without this the graft assertion cannot distinguish "the guard fired" from
    "this command fails in a scratch repository for some unrelated reason".
    """
    _, clone = graftable_clone
    result = _run_policy(clone, "security-suppressions-diff", "--base-ref", "origin/main")
    assert result.returncode == 0, result.stderr


def test_suppression_diff_refuses_to_measure_a_grafted_clone(
    graftable_clone: tuple[Path, Path],
) -> None:
    """Issue #4572: a shallow clone must fail closed, not measure a wider range.

    The discriminating input is a clone that is complete and then grafted by a
    single depth-limited fetch, with nothing else changed. Restoring the defect,
    by removing the `_check_history_integrity` call from
    `check_suppression_diff`, turns this exit 2 back into an exit 0 computed
    over the wrong range.
    """
    origin, clone = graftable_clone
    assert _git(clone, "rev-parse", "--is-shallow-repository").stdout.strip() == "false"

    fetch = _git(clone, "fetch", "--depth=1", str(origin), "main")
    assert fetch.returncode == 0, fetch.stderr
    assert _git(clone, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"

    result = _run_policy(clone, "security-suppressions-diff", "--base-ref", "origin/main")
    assert result.returncode == 2, (
        f"expected exit 2 on a grafted clone, got {result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "complete Git history" in result.stderr


def test_suppression_range_refuses_to_measure_a_grafted_clone(
    graftable_clone: tuple[Path, Path],
) -> None:
    """The sibling range entrypoint shares the defect and the remedy.

    `check_range_suppressions` resolves its range through `git merge-base` and
    falls back to the base tip when that fails, which is exactly what a graft
    causes, so its range silently widened rather than erroring.
    """
    origin, clone = graftable_clone
    baseline = _run_policy(
        clone, "security-suppressions-range", "--base", "origin/main", "--head", "HEAD"
    )
    assert baseline.returncode == 0, baseline.stderr

    assert _git(clone, "fetch", "--depth=1", str(origin), "main").returncode == 0

    result = _run_policy(
        clone, "security-suppressions-range", "--base", "origin/main", "--head", "HEAD"
    )
    assert result.returncode == 2, (
        f"expected exit 2 on a grafted clone, got {result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "complete Git history" in result.stderr


def test_a_depth_limited_fetch_really_does_graft_a_complete_clone(
    graftable_clone: tuple[Path, Path],
) -> None:
    """Pins the premise the other tests and the workflow comments rest on.

    If a future git release stopped writing `.git/shallow` for this fetch, the
    guards above would still pass while guarding nothing, and the workflow
    comments would be wrong. This fails first and names why.
    """
    origin, clone = graftable_clone
    assert not (clone / ".git" / "shallow").exists()

    assert _git(clone, "fetch", "--depth=1", str(origin), "main").returncode == 0
    assert (clone / ".git" / "shallow").is_file()

    plain = _git(clone, "fetch", str(origin), "main")
    assert plain.returncode == 0, plain.stderr
    assert (clone / ".git" / "shallow").is_file(), (
        "a plain fetch removed the graft, so the workflow comments claiming a "
        "later full fetch cannot repair it are now wrong"
    )

    assert _git(clone, "fetch", "--unshallow", str(origin)).returncode == 0
    assert not (clone / ".git" / "shallow").exists()
