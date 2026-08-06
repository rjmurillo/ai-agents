"""Static invariant against the shallow-graft class of CI defect (issue #4572).

A `git fetch --depth=1` does not merely limit one fetch. It writes
`.git/shallow`, which git shares across the whole repository and every
worktree, and it severs ancestry traversal for every later step in the same
job. A plain `git fetch` afterwards does not repair it.

That makes the trap invisible at the step that pays for it. The step that
writes the graft succeeds, and a different step further down the job fails, or
worse, silently measures the wrong range.

This module is the prevention half: no workflow job may write the graft. The
runtime half, which proves the graft's effect against real git and pins the CI
entrypoints that must refuse to answer under it, lives in
test_shallow_fetch_graft_guards.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
POLICY = REPO_ROOT / "scripts" / "validation" / "git_hook_policy.py"

DEFAULT_CHECKOUT_DEPTH = 1
ROOT_CHECKOUT_PATHS = {None, "", ".", "./"}
SHALLOWING_FETCH_FLAGS = ("--depth", "--shallow-since", "--shallow-exclude")


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


def _is_root_checkout(step: dict[str, object]) -> bool:
    """True when the step checks out into the workspace root.

    `actions/checkout` writes its own `.git` under `path:`, so a nested
    checkout has a separate `.git/shallow` and cannot graft the root
    repository. Aggregating both into one job-level depth would let a shallow
    helper checkout stand in for the root one. `pr-maintenance.yml` line 120
    is a live example: a `.trusted-helper` checkout at depth 1 sits in a job
    whose root checkout is depth 0.
    """
    with_block = step.get("with")
    if not isinstance(with_block, dict):
        return True
    return with_block.get("path") in ROOT_CHECKOUT_PATHS


def _normalized_depth(value: object) -> object:
    """Depth as an int where it is a literal, else the raw value.

    YAML gives `fetch-depth: 0` as int 0 and `fetch-depth: "0"` as str "0";
    both mean a complete checkout. A `${{ }}` expression is not resolvable
    here and is returned untouched, which `test_no_workflow_computes_its_
    checkout_depth` exists to keep from becoming a silent blind spot.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return int(stripped)
        except ValueError:
            return stripped
    return value


def _root_checkout_depths(job: dict[str, object]) -> set[object]:
    """Every `fetch-depth` the job's ROOT checkout steps request.

    An absent `fetch-depth` is the action's default of 1, which is itself
    shallow, so it is reported as 1 rather than dropped.
    """
    depths: set[object] = set()
    for step in _steps(job):
        uses = step.get("uses")
        if not isinstance(uses, str) or "actions/checkout" not in uses:
            continue
        if not _is_root_checkout(step):
            continue
        with_block = step.get("with")
        if not isinstance(with_block, dict):
            depths.add(DEFAULT_CHECKOUT_DEPTH)
            continue
        depths.add(_normalized_depth(with_block.get("fetch-depth", DEFAULT_CHECKOUT_DEPTH)))
    return depths


def _logical_lines(script: str) -> list[str]:
    """Shell lines with backslash continuations joined and comments dropped.

    A fetch split as `git fetch origin main \\` / `  --depth=1` is one command
    to the shell and must be one line here, or the flag hides on a line that
    does not contain `git fetch`.
    """
    joined: list[str] = []
    pending = ""
    for raw_line in script.splitlines():
        line = raw_line.strip()
        if pending:
            line = f"{pending} {line}"
            pending = ""
        if line.endswith("\\"):
            pending = line[:-1].rstrip()
            continue
        joined.append(line)
    if pending:
        joined.append(pending)
    return [line for line in joined if line and not line.startswith("#")]


def _targets_root_repository(line: str) -> bool:
    """False when the command explicitly operates on a nested repository.

    `git -C .trusted-helper fetch --depth=1` grafts that nested clone, not the
    workspace root, so it is out of scope for this invariant.
    """
    tokens = line.split()
    for index, token in enumerate(tokens):
        if token == "-C" and index + 1 < len(tokens):
            return tokens[index + 1] in {".", "./"}
        if token.startswith("-C") and len(token) > 2:
            return token[2:] in {".", "./"}
    return True


def _shallowing_fetches(job: dict[str, object]) -> list[tuple[str, str]]:
    """Fetches in the job that would graft the root repository."""
    found: list[tuple[str, str]] = []
    for step in _steps(job):
        run = step.get("run")
        if not isinstance(run, str):
            continue
        working_directory = step.get("working-directory")
        if isinstance(working_directory, str) and working_directory.strip() not in {".", "./", ""}:
            continue
        name = step.get("name")
        for line in _logical_lines(run):
            if "git fetch" not in line and " fetch " not in line:
                continue
            if not any(flag in line for flag in SHALLOWING_FETCH_FLAGS):
                continue
            if not _targets_root_repository(line):
                continue
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

    Scoped to jobs whose ROOT checkout is already `fetch-depth: 0`, because
    there a shallowing fetch is pure downside: the history is present already,
    so the flag saves no bandwidth and its only observable effect is the graft.
    A job that deliberately checks out shallow is left alone; it has made a
    different trade knowingly.

    Known limit of a static scan, deliberately not papered over: a shallowing
    fetch reached through a composite action, a reusable workflow, or a script
    the step invokes is not resolved here. A sweep for the script case was
    written and then removed, because every candidate it found was prose in a
    docstring or an unrelated argparse `--depth` for graph traversal, and a
    guard that cannot tell those from a real fetch would fail the next
    contributor who adds a depth option to a CLI. The expression case, which
    IS decidable, is pinned by the sibling test below.
    """
    offenders: list[str] = []
    examined = 0
    for path, document in _workflow_documents():
        for job_name, job in _jobs(document).items():
            examined += 1
            if 0 not in _root_checkout_depths(job):
                continue
            for step_name, line in _shallowing_fetches(job):
                offenders.append(f"{path.name}::{job_name} step {step_name!r}: {line}")

    assert examined >= 10, f"sweep examined only {examined} jobs"
    assert not offenders, (
        "a job checks out at fetch-depth 0 and then fetches shallowly, which "
        "writes .git/shallow for the rest of the job and severs ancestry for "
        "every later step (issue #4572). Drop the depth flag:\n  "
        + "\n  ".join(offenders)
    )


def test_no_workflow_computes_its_checkout_depth_from_an_expression() -> None:
    """Pins the one blind spot the depth parser cannot resolve.

    `_normalized_depth` turns `0` and `"0"` into the same integer, but a
    `${{ }}` expression is decided at run time and cannot be classified here.
    Rather than guess, this asserts none exists, so the day one appears this
    fails and names it instead of the invariant above going quietly blind.
    """
    computed: list[str] = []
    for path, document in _workflow_documents():
        for job_name, job in _jobs(document).items():
            for depth in _root_checkout_depths(job):
                if isinstance(depth, str) and "${{" in depth:
                    computed.append(f"{path.name}::{job_name} fetch-depth: {depth}")

    assert not computed, (
        "a root checkout computes fetch-depth from an expression, which the "
        "shallow-graft invariant cannot classify statically. Either pin the "
        "depth to a literal or teach the invariant this case:\n  "
        + "\n  ".join(computed)
    )



@pytest.mark.parametrize(
    ("job", "expected"),
    [
        pytest.param(
            {"steps": [{"uses": "actions/checkout@v7", "with": {"fetch-depth": 0}}]},
            {0},
            id="integer zero is a full checkout",
        ),
        pytest.param(
            {"steps": [{"uses": "actions/checkout@v7", "with": {"fetch-depth": "0"}}]},
            {0},
            id="quoted zero is the same full checkout",
        ),
        pytest.param(
            {"steps": [{"uses": "actions/checkout@v7"}]},
            {1},
            id="absent depth is the shallow action default",
        ),
        pytest.param(
            {
                "steps": [
                    {"uses": "actions/checkout@v7", "with": {"fetch-depth": 0}},
                    {
                        "uses": "actions/checkout@v7",
                        "with": {"path": ".trusted-helper", "fetch-depth": 1},
                    },
                ]
            },
            {0},
            id="a nested checkout has its own git dir and is not the root",
        ),
        pytest.param(
            {
                "steps": [
                    {"uses": "actions/checkout@v7", "with": {"fetch-depth": "${{ inputs.d }}"}}
                ]
            },
            {"${{ inputs.d }}"},
            id="an expression is kept raw rather than guessed",
        ),
    ],
)
def test_root_checkout_depth_parsing(job: dict[str, object], expected: set[object]) -> None:
    """Each case is an evasion the first draft of this parser fell for.

    The quoted-zero case is the one that mattered: `fetch-depth: "0"` is a
    complete checkout that YAML hands over as a string, so an identity
    comparison against integer 0 skipped the job and the invariant went blind
    on it.
    """
    assert _root_checkout_depths(job) == expected


@pytest.mark.parametrize(
    ("script", "detected"),
    [
        pytest.param('git fetch --depth=1 origin "$BASE_REF"', True, id="equals form"),
        pytest.param('git fetch --depth 1 origin "$BASE_REF"', True, id="space form"),
        pytest.param(
            'git fetch origin "$BASE_REF" \\\n  --depth=1',
            True,
            id="flag hidden behind a line continuation",
        ),
        pytest.param(
            'git fetch --shallow-since=2020-01-01 origin "$BASE_REF"',
            True,
            id="shallow-since grafts without the word depth",
        ),
        pytest.param(
            'git fetch --shallow-exclude=v1.0 origin "$BASE_REF"',
            True,
            id="shallow-exclude grafts without the word depth",
        ),
        pytest.param('git -C . fetch --depth=1 origin main', True, id="explicit root via -C"),
        pytest.param(
            'git -C .trusted-helper fetch --depth=1 origin main',
            False,
            id="a nested repository is out of scope",
        ),
        pytest.param('# git fetch --depth=1 origin main', False, id="a comment is not a command"),
        pytest.param('git fetch origin "$BASE_REF"', False, id="a full fetch is fine"),
        pytest.param('git fetch --unshallow origin', False, id="unshallow repairs, never grafts"),
    ],
)
def test_shallowing_fetch_detection(script: str, detected: bool) -> None:
    """Line-continuation and shallow-since were both live evasions.

    A fetch split across a backslash continuation is one command to the shell,
    so scanning raw lines put the flag on a line with no `git fetch` in it. And
    `--shallow-since` grafts exactly as `--depth` does while containing none of
    its letters, so a substring match for "--depth" let it through.
    """
    job = {"steps": [{"name": "s", "run": script}]}
    assert bool(_shallowing_fetches(job)) is detected


def test_a_working_directory_step_is_not_charged_to_the_root_repository() -> None:
    """A step that runs elsewhere cannot graft the workspace root."""
    job = {
        "steps": [
            {
                "name": "s",
                "working-directory": "vendor/thing",
                "run": "git fetch --depth=1 origin main",
            }
        ]
    }
    assert _shallowing_fetches(job) == []
