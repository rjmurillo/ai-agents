"""Unit tests for the shallow-graft workflow parser.

Every case here is an evasion or a false accusation found by adversarial
review of the invariant in test_shallow_fetch_workflow_invariant.py. They are
kept as unit tests rather than folded into the sweep because the sweep can only
say "the repository is clean today", which is the one thing that stays true
while the parser quietly stops working.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from tests.ci.shallow_fetch_workflow_parsing import (
    _is_root_path,
    _normalized_depth,
    _root_checkout_depths,
    _shallowing_fetches,
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
def test_root_checkout_depth_parsing(job: Mapping[str, object], expected: set[object]) -> None:
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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(0, 0, id="integer zero"),
        pytest.param("0", 0, id="quoted zero"),
        pytest.param(1, 1, id="integer one"),
        pytest.param(True, 0, id="YAML true is NaN to the action and floors to full"),
        pytest.param(False, 0, id="YAML false is NaN to the action and floors to full"),
        pytest.param(-1, 0, id="negative is clamped to full"),
        pytest.param("-5", 0, id="quoted negative is clamped to full"),
        pytest.param("abc", 0, id="non-numeric is NaN and becomes full"),
        pytest.param("2.9", 2, id="fractional floors"),
        pytest.param("${{ inputs.d }}", "${{ inputs.d }}", id="expression stays unresolved"),
    ],
)
def test_normalized_depth_mirrors_the_action(raw: object, expected: object) -> None:
    """`actions/checkout` coerces the input; this must agree with it.

    From the action's `input-helper.ts`:

        result.fetchDepth = Math.floor(Number(core.getInput('fetch-depth') || '1'))
        if (isNaN(result.fetchDepth) || result.fetchDepth < 0) {
          result.fetchDepth = 0
        }

    The dangerous case is `true`. Preserved as a boolean it reads as shallow,
    a shallow reading skips the job, and the invariant would go blind on a job
    that is in fact running with complete history.
    """
    assert _normalized_depth(raw) == expected


@pytest.mark.parametrize(
    ("path", "is_root"),
    [
        pytest.param(".", True, id="dot"),
        pytest.param("./", True, id="dot slash"),
        pytest.param("", True, id="empty"),
        pytest.param(".trusted-helper", False, id="a nested checkout"),
        pytest.param("${{ inputs.dir }}", True, id="unresolved expression counts as root"),
        pytest.param("$GITHUB_WORKSPACE", True, id="the workspace variable is the root"),
        pytest.param("${{ github.workspace }}", True, id="the workspace expression is the root"),
        pytest.param('"."', True, id="quoted dot"),
    ],
)
def test_root_path_classification(path: str, is_root: bool) -> None:
    """Ambiguity resolves toward root, so the sweep never silently narrows."""
    assert _is_root_path(path) is is_root


@pytest.mark.parametrize(
    ("script", "detected"),
    [
        pytest.param(
            "git fetch --depth=1 origin main && git -C .trusted-helper status",
            True,
            id="a later nested command must not excuse a root graft",
        ),
        pytest.param(
            "git --git-dir=.trusted-helper/.git fetch --depth=1 origin main",
            False,
            id="git-dir anchors to the nested repo just as -C does",
        ),
        pytest.param(
            "git fetch origin main && tool --depth=1",
            False,
            id="a depth flag on a different command is not a shallow fetch",
        ),
        pytest.param(
            'git -C "$GITHUB_WORKSPACE" fetch --depth=1 origin main',
            True,
            id="the workspace variable is the root repository",
        ),
        pytest.param(
            "git fetch origin main; git fetch --depth=1 origin main",
            True,
            id="a fetch after a semicolon still counts",
        ),
    ],
)
def test_shallowing_fetch_command_anchoring(script: str, detected: bool) -> None:
    """Each case is a false negative or false positive found in review.

    The first is the one that mattered: the old whole-line scan suppressed a
    genuine root graft because an unrelated command later on the same line
    named a nested path.
    """
    job = {"steps": [{"name": "s", "run": script}]}
    assert bool(_shallowing_fetches(job)) is detected


@pytest.mark.parametrize(
    ("working_directory", "detected"),
    [
        pytest.param("vendor/thing", False, id="a real subdirectory is out of scope"),
        pytest.param("${{ inputs.dir }}", True, id="an unresolved directory counts as root"),
        pytest.param("${{ github.workspace }}", True, id="the workspace is the root"),
    ],
)
def test_working_directory_resolution(working_directory: str, detected: bool) -> None:
    """An unresolved `working-directory` must not remove a step from the sweep."""
    job = {
        "steps": [
            {
                "name": "s",
                "working-directory": working_directory,
                "run": "git fetch --depth=1 origin main",
            }
        ]
    }
    assert bool(_shallowing_fetches(job)) is detected


def test_the_sweep_reads_both_workflow_extensions(tmp_path) -> None:
    """GitHub Actions accepts `.yaml`, and globbing `*.yml` alone goes blind.

    This repository has already lost coverage that way once: a
    security-suppression gate dropped `**/*.yaml` on 2026-08-01. The three
    sibling sweeps under tests/ci all glob both extensions.
    """
    from tests.ci import shallow_fetch_workflow_parsing as parsing

    workflows = tmp_path / "workflows"
    workflows.mkdir()
    body = "jobs:\n  j:\n    steps:\n      - run: echo hi\n"
    (workflows / "a.yml").write_text(body, encoding="utf-8")
    (workflows / "b.yaml").write_text(body, encoding="utf-8")

    original = parsing.WORKFLOW_DIR
    try:
        parsing.WORKFLOW_DIR = workflows
        names = sorted(path.name for path, _ in parsing._workflow_documents())
    finally:
        parsing.WORKFLOW_DIR = original

    assert names == ["a.yml", "b.yaml"]


@pytest.mark.parametrize(
    "script",
    [
        pytest.param(
            'echo "$(git fetch --depth=1 origin main)"',
            id="a fetch inside a command substitution",
        ),
        pytest.param(
            "git -C .trusted-helper status | git fetch --depth=1 origin main",
            id="a fetch downstream of a pipe",
        ),
    ],
)
def test_an_unattributable_shallowing_flag_is_reported_not_dropped(script: str) -> None:
    """The splitter is not a shell, so it must fail loud where it cannot parse.

    Both of these carry a real shallowing flag that no command the splitter
    produces owns. Silently dropping them is the failure mode this whole module
    exists to prevent, so the line is reported instead. A human reading the
    message can tell in one glance whether it is real, which is not true of a
    guard that says nothing.
    """
    job = {"steps": [{"name": "s", "run": script}]}
    assert _shallowing_fetches(job) != []


def test_a_plain_full_fetch_is_still_not_reported() -> None:
    """Control for the rule above, which would otherwise be easy to make vacuous."""
    job = {"steps": [{"name": "s", "run": 'echo "$(git fetch origin main)"'}]}
    assert _shallowing_fetches(job) == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("", 1, id="an empty string is the action default of 1"),
        pytest.param("   ", 1, id="whitespace only is the action default of 1"),
        pytest.param(None, 1, id="YAML null reaches the action as an empty input"),
    ],
)
def test_empty_depth_is_the_shallow_default_not_full(raw: object, expected: object) -> None:
    """`core.getInput(...) || '1'` makes an empty input 1, which is shallow.

    Folding it to 0 would call a genuinely shallow checkout complete, and the
    invariant would then accuse a job that is allowed to fetch shallowly.
    """
    assert _normalized_depth(raw) == expected


@pytest.mark.parametrize(
    ("script", "detected"),
    [
        pytest.param(
            "git --git-dir=.git fetch --depth=1 origin main",
            True,
            id="dot git IS the root repository git directory",
        ),
        pytest.param(
            "git --git-dir=./.git fetch --depth=1 origin main",
            True,
            id="the same directory written relatively",
        ),
        pytest.param(
            "git --git-dir=.trusted-helper/.git fetch --depth=1 origin main",
            False,
            id="a nested git directory is still out of scope",
        ),
    ],
)
def test_git_dir_is_classified_as_a_git_directory_not_a_worktree(
    script: str, detected: bool
) -> None:
    """`--git-dir` takes a git directory, so `-C` path rules do not transfer.

    The root repository's git directory is `.git`, which reads as a non-root
    WORKTREE path. Reusing the worktree classifier therefore let a genuine root
    graft through.
    """
    job = {"steps": [{"name": "s", "run": script}]}
    assert bool(_shallowing_fetches(job)) is detected
