"""Guards complete git history in CI jobs that need a merge base.

The trap is counter-intuitive. Depth-limited history reads as a harmless
bandwidth saving. On a runner it is not a saving at all when the checkout
already has the history, and it writes `.git/shallow`, grafting the fetched
tip parentless. `git merge-base` then returns nothing for the rest of the job.

Two consumers depend on a merge base, in two severity classes. The one that
broke is `scripts/ci/merge_tree_ratchet_check.py`: it runs `git merge-tree`,
which exits 128 with "refusing to merge unrelated histories", so the step
fails closed. That step is unconditional (issue #4151), so it runs on every
leg of `validate-pr`, including the bot-actor leg whose checkout took the
depth-1 default. Renovate PR #4552 is the recorded failure. The quieter one is
`scripts/ci/count_ratchet.py`, whose `changed_files` diffs `base_ref...HEAD`
to sort branch-touched files first; that leg fails open, so a graft silently
degrades the regression diagnostic rather than reddening the check. Both are
guarded, because a silent degradation is what buries a real violation.

Two independent ways to arrive at the graft, which is why the guard checks
both. A `git fetch --depth=<n>` inside a `run:` body writes one. So does an
`actions/checkout` that omits `fetch-depth: 0`. Fixing only the fetch leaves
the checkout path broken, because a plain undepthed fetch does not clear an
existing graft; only `--unshallow` does. `test_a_plain_fetch_does_not_repair_a_graft`
below measures that.

The failure fires only when the checkout predates the fetched tip, so it reads
as a flake while being deterministic for any branch behind main.

The behavioral tests exercise real git rather than asserting on strings alone,
and include a negative control so a passing suite cannot be explained by some
mechanism other than the shallow graft.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# Substrings that mark a step as needing a merge base. Keep in sync with the
# consumers named in the module docstring. Two severity classes, both guarded:
# `merge_tree_ratchet_check.py` fails closed on a graft (exit 3, red check),
# while `count_ratchet.py` fails open, degrading the regression diagnostic's
# ordering because `changed_files` diffs `base_ref...HEAD`. The substring also
# covers the `ruff_`, `taste_` and `type_ignore_` variants, which all import
# `run` from `count_ratchet` and so reach the same three-dot leg.
# `security-suppressions-diff` is deliberately absent: it diffs a two-dot range
# (`git_hook_policy.py`, `check_suppression_diff`), which compares two
# endpoints and needs no base.
MERGE_BASE_CONSUMERS = ("merge_tree_ratchet_check.py", "count_ratchet.py")


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _strip_comments(script: str) -> str:
    """Drop shell comment lines so prose about depth is not a match."""
    return "\n".join(
        line for line in script.splitlines() if not line.lstrip().startswith("#")
    )


def _steps(job: Any) -> list[dict[str, Any]]:
    if not isinstance(job, dict):
        return []
    return [step for step in (job.get("steps") or []) if isinstance(step, dict)]


def _shallow_history_offenders(label: str, data: Any) -> tuple[list[str], list[str]]:
    """Return (offenders, jobs_checked) for one parsed workflow document.

    A job qualifies when any `run:` body names a merge-base consumer. Both
    routes to a graft are then checked: a depth flag in any `run:` body of
    that job, and any `actions/checkout` in it that does not pin
    `fetch-depth: 0`. Job-scoped rather than step-scoped because the graft is
    sticky: once any step writes `.git/shallow`, every later step sees it.
    """
    offenders: list[str] = []
    checked: list[str] = []
    jobs = data.get("jobs") if isinstance(data, dict) else None
    for job_id, job in (jobs or {}).items():
        steps = _steps(job)
        code = [
            _strip_comments(step["run"])
            for step in steps
            if isinstance(step.get("run"), str)
        ]
        if not any(marker in body for body in code for marker in MERGE_BASE_CONSUMERS):
            continue
        checked.append(f"{label}:{job_id}")
        if any("--depth" in body for body in code):
            offenders.append(f"{label}:{job_id}: depth-limited fetch in a run block")
        for step in steps:
            uses = step.get("uses")
            if not isinstance(uses, str) or not uses.startswith("actions/checkout"):
                continue
            with_block = step.get("with")
            depth = (with_block or {}).get("fetch-depth")
            if str(depth) != "0":
                name = step.get("name") or uses
                shown = "<default, depth 1>" if depth is None else repr(depth)
                offenders.append(
                    f"{label}:{job_id}: checkout {name!r} has fetch-depth {shown}"
                )
    return offenders, checked


def _workflow_files(directory: Path) -> list[Path]:
    """Every workflow file in ``directory``.

    GitHub Actions accepts both ``.yml`` and ``.yaml``. Globbing only ``.yml``
    would let a ``.yaml`` workflow carry a depth-limited fetch past this guard
    while the test below still reports that it scanned every workflow.
    """
    return sorted(
        p for p in directory.iterdir() if p.suffix in {".yml", ".yaml"} and p.is_file()
    )


def test_the_workflow_scan_covers_both_yaml_extensions(tmp_path):
    """The enumeration must not miss a ``.yaml`` workflow.

    Negative control: a ``.yml`` sibling proves the helper is not simply
    returning everything, and a ``.yml.disabled`` file proves suffix matching
    is exact rather than a substring test.
    """
    (tmp_path / "a.yml").write_text("on: push\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("on: push\n", encoding="utf-8")
    (tmp_path / "c.txt").write_text("not a workflow\n", encoding="utf-8")
    (tmp_path / "d.yml.disabled").write_text("on: push\n", encoding="utf-8")

    assert [p.name for p in _workflow_files(tmp_path)] == ["a.yml", "b.yaml"]


def test_every_job_needing_a_merge_base_keeps_complete_history():
    """No workflow job may reach a merge-base consumer with grafted history.

    Scans every workflow rather than a fixed list, so a consumer moved or
    copied into another workflow is covered without editing this test.
    """
    offenders: list[str] = []
    checked: list[str] = []
    for workflow in _workflow_files(WORKFLOW_DIR):
        data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        found, seen = _shallow_history_offenders(workflow.name, data)
        offenders.extend(found)
        checked.extend(seen)

    assert checked, (
        "no workflow job runs any of "
        f"{MERGE_BASE_CONSUMERS}; this guard is now vacuous and must be "
        "repointed or deleted."
    )
    assert not offenders, (
        "grafted history reaches a merge-base consumer: "
        f"{sorted(set(offenders))}. git merge-base returns nothing under a "
        "graft. Where that reaches merge_tree_ratchet_check.py the step dies "
        "with 'refusing to merge unrelated histories'; where it reaches "
        "count_ratchet.py the three-dot leg fails open and silently degrades "
        "the regression diagnostic's ordering. Pin fetch-depth: 0 on the "
        "checkout and drop --depth from the fetches. A later plain fetch does "
        "not repair it."
    )


def test_the_guard_catches_a_depth_flag_and_a_shallow_checkout():
    """Negative control: feed the real matcher a job with both defects.

    Without this, a passing guard could mean the matcher never matches. Both
    routes are asserted separately so neither can carry the other.
    """
    data = yaml.safe_load(
        "jobs:\n"
        "  validate:\n"
        "    steps:\n"
        "      - uses: actions/checkout@v7\n"
        '      - run: git fetch --depth=1 origin "$BASE_REF"\n'
        "      - run: python scripts/ci/merge_tree_ratchet_check.py\n"
    )
    offenders, checked = _shallow_history_offenders("bad.yml", data)
    assert checked == ["bad.yml:validate"]
    assert any("depth-limited fetch" in item for item in offenders), offenders
    assert any("fetch-depth <default, depth 1>" in item for item in offenders), offenders


def test_the_guard_catches_a_non_zero_explicit_fetch_depth():
    """Edge case: `fetch-depth: 1` is spelled out rather than defaulted.

    A truncated trunk still reads as a trunk, so any non-zero depth is a
    defect here, not just the implicit default.
    """
    data = yaml.safe_load(
        "jobs:\n"
        "  validate:\n"
        "    steps:\n"
        "      - uses: actions/checkout@v7\n"
        "        with:\n"
        "          fetch-depth: 50\n"
        "      - run: python scripts/ci/merge_tree_ratchet_check.py\n"
    )
    offenders, _ = _shallow_history_offenders("bad.yml", data)
    assert any("fetch-depth 50" in item for item in offenders), offenders


def test_the_guard_passes_a_correct_job_and_ignores_depth_in_comments():
    """Positive control: the shape the fixed workflows use must pass.

    The fixed workflows explain the trap in comments that contain the literal
    `--depth`. Prose about the flag must not read as a use of the flag, or the
    guard would fail the very change that fixes it.
    """
    data = yaml.safe_load(
        "jobs:\n"
        "  validate:\n"
        "    steps:\n"
        "      - uses: actions/checkout@v7\n"
        "        with:\n"
        "          fetch-depth: 0\n"
        "      - run: |\n"
        "          # No --depth=1: this step needs a merge base.\n"
        '          git fetch origin "$BASE_REF"\n'
        "      - run: python scripts/ci/merge_tree_ratchet_check.py\n"
    )
    offenders, checked = _shallow_history_offenders("ok.yml", data)
    assert checked == ["ok.yml:validate"]
    assert offenders == []


def test_a_job_without_a_merge_base_consumer_is_out_of_scope():
    """A shallow checkout is only a defect where a merge base is needed.

    Guards against the matcher widening into every workflow in the repo,
    which would turn an unrelated depth choice into a failure here. The job
    below is deliberately at its worst on both routes, a default-depth
    checkout and a depth-limited fetch, and must still be ignored.
    """
    data = yaml.safe_load(
        "jobs:\n"
        "  lint:\n"
        "    steps:\n"
        "      - uses: actions/checkout@v7\n"
        '      - run: git fetch --depth=1 origin "$BASE_REF"\n'
        "      - run: uv run --frozen ruff check .\n"
    )
    offenders, checked = _shallow_history_offenders("lint.yml", data)
    assert checked == []
    assert offenders == []


def test_a_count_ratchet_variant_is_in_scope():
    """The `count_ratchet.py` substring has to reach the prefixed variants.

    `ruff_`, `taste_` and `type_ignore_` each import `run` from
    `count_ratchet`, so each reaches the three-dot `changed_files` leg. That
    leg fails open, so a graft degrades the regression diagnostic silently
    instead of reddening the check, which is precisely why a test has to hold
    it: nothing else would report the loss.
    """
    for script in (
        "ruff_count_ratchet.py",
        "taste_count_ratchet.py",
        "type_ignore_count_ratchet.py",
    ):
        data = yaml.safe_load(
            "jobs:\n"
            "  ratchet:\n"
            "    steps:\n"
            "      - uses: actions/checkout@v7\n"
            '      - run: git fetch --depth=1 origin "$BASE_REF"\n'
            f"      - run: python scripts/ci/{script} --base-ref FETCH_HEAD\n"
        )
        offenders, checked = _shallow_history_offenders("ratchet.yml", data)
        assert checked == ["ratchet.yml:ratchet"], script
        assert len(offenders) == 2, f"{script}: {offenders}"
        assert any("depth-limited fetch" in o for o in offenders), script
        assert any("fetch-depth" in o for o in offenders), script


@pytest.fixture
def upstream_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    """A complete clone of an upstream whose main advanced past the branch.

    Mirrors CI: the PR checkout is complete (`fetch-depth: 0`) but predates
    main's current tip, which is exactly when the graft is written.
    """
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _run(upstream, "init", "-q", "-b", "main")
    _run(upstream, "config", "user.email", "test@example.com")
    _run(upstream, "config", "user.name", "test")
    (upstream / "base.txt").write_text("base\n", encoding="utf-8")
    _run(upstream, "add", "base.txt")
    _run(upstream, "commit", "-qm", "base")

    _run(upstream, "checkout", "-qb", "feature")
    (upstream / "feature.txt").write_text("feature\n", encoding="utf-8")
    _run(upstream, "add", "feature.txt")
    _run(upstream, "commit", "-qm", "feature work")

    _run(upstream, "checkout", "-q", "main")
    for index in range(3):
        name = f"main{index}.txt"
        (upstream / name).write_text("main\n", encoding="utf-8")
        _run(upstream, "add", name)
        _run(upstream, "commit", "-qm", f"main advances {index}")

    clone = tmp_path / "clone"
    _run(tmp_path, "clone", "-q", str(upstream), str(clone))
    _run(clone, "fetch", "-q", "origin", "feature:feature")
    return upstream, clone


def test_a_complete_clone_resolves_a_merge_base(upstream_and_clone: tuple[Path, Path]):
    """Negative control: without the shallow fetch, everything works.

    If this ever fails, the fixture is broken and the two failure tests below
    prove nothing.
    """
    _, clone = upstream_and_clone
    assert not (clone / ".git" / "shallow").exists()
    merge_base = _run(clone, "merge-base", "feature", "origin/main")
    assert merge_base.returncode == 0
    assert merge_base.stdout.strip()
    merge_tree = _run(clone, "merge-tree", "--write-tree", "origin/main", "feature")
    assert merge_tree.returncode == 0, merge_tree.stderr
    three_dot = _run(clone, "diff", "--name-only", "origin/main...feature")
    assert three_dot.returncode == 0, three_dot.stderr


def test_depth_one_fetch_grafts_a_complete_clone_and_kills_merge_base(
    upstream_and_clone: tuple[Path, Path],
):
    """The mechanism, reproduced end to end against real git."""
    _, clone = upstream_and_clone
    fetch = _run(clone, "fetch", "--depth=1", "origin", "main")
    assert fetch.returncode == 0, fetch.stderr

    assert (clone / ".git" / "shallow").exists(), (
        "expected a depth-limited fetch to write .git/shallow on a clone that "
        "already had complete history"
    )
    assert not _run(clone, "merge-base", "feature", "FETCH_HEAD").stdout.strip()

    merge_tree = _run(clone, "merge-tree", "--write-tree", "FETCH_HEAD", "feature")
    assert merge_tree.returncode != 0
    assert "unrelated histories" in merge_tree.stderr

    three_dot = _run(clone, "diff", "--name-only", "FETCH_HEAD...feature")
    assert three_dot.returncode != 0
    assert "no merge base" in three_dot.stderr


def test_a_later_undepthed_fetch_does_not_repair_the_graft(
    upstream_and_clone: tuple[Path, Path],
):
    """Why every fetch in the job must drop the flag, not just the last one.

    Fixing only the merge-base consumer's own fetch would leave the graft an
    earlier step wrote still in place.
    """
    _, clone = upstream_and_clone
    _run(clone, "fetch", "--depth=1", "origin", "main")
    assert (clone / ".git" / "shallow").exists()

    repair = _run(clone, "fetch", "-q", "origin", "main")
    assert repair.returncode == 0, repair.stderr
    assert (clone / ".git" / "shallow").exists(), (
        "a plain fetch unexpectedly repaired the graft; if git changed this, "
        "the all-sites fix in pr-validation.yml and pytest.yml can be relaxed"
    )
    assert not _run(clone, "merge-base", "feature", "FETCH_HEAD").stdout.strip()

    unshallow = _run(clone, "fetch", "-q", "--unshallow", "origin", "main")
    assert unshallow.returncode == 0, unshallow.stderr
    assert not (clone / ".git" / "shallow").exists()
    assert _run(clone, "merge-base", "feature", "FETCH_HEAD").stdout.strip()


# Each case is the depth flag for the three sequential fetches a single job
# performs, paired with the expected `git merge-tree` return code afterwards.
# `True` means that step fetched with `--depth=1`.
_JOB_SHAPES = [
    pytest.param([True, True, True], 128, id="unchanged-control"),
    pytest.param([True, True, False], 128, id="merge-tree-step-only"),
    pytest.param([False, True, True], 128, id="first-step-only"),
    pytest.param([False, False, False], 0, id="every-step"),
]


@pytest.mark.parametrize(("depths", "expected_rc"), _JOB_SHAPES)
def test_only_dropping_the_flag_everywhere_repairs_the_job(
    upstream_and_clone: tuple[Path, Path],
    depths: list[bool],
    expected_rc: int,
):
    """Scoping the fix to the merge-base consumer's own fetch does not work.

    Issue #4518 diagnosed this failure correctly and then prescribed a remedy
    scoped to the merge-tree step, on the reasoning that the two sibling
    ratchets read a blob and need no history walk. That reasoning is right about
    the siblings and wrong about the remedy: whichever step fetches first writes
    the graft, and every later step in the job inherits it.

    The `unchanged-control` case must fail, or the other three prove nothing.
    """
    _, clone = upstream_and_clone
    for shallow in depths:
        args = ["fetch", "-q", "--depth=1"] if shallow else ["fetch", "-q"]
        assert _run(clone, *args, "origin", "main").returncode == 0

    grafted = (clone / ".git" / "shallow").exists()
    assert grafted == any(depths)

    merge_tree = _run(clone, "merge-tree", "--write-tree", "FETCH_HEAD", "feature")
    assert merge_tree.returncode == expected_rc, merge_tree.stderr
    if expected_rc != 0:
        assert "unrelated histories" in merge_tree.stderr

