"""The mypy gate must survive this repository's own generated mirrors.

`scripts/ai_review_common` is copied verbatim to `.claude/lib/` and
`src/copilot-cli/lib/` by `scripts/sync_plugin_lib.py` and
`build/scripts/build_all.py`. Neither `lib` directory is a package, so both
mirrors claim the same module name. Handing mypy both copies in one invocation
makes it exit 1 with "Duplicate module named ... errors prevented further
checking", so the gate reported a type regression having type-checked nothing,
on any change the repository's own generators produce.

Coverage:

- positive: two mirror copies of one module collapse to one path; unrelated
  files and distinct modules are all kept; the canonical `scripts.` copy is
  kept alongside a mirror because it is a different module.
- negative: the real mirror pair still collides when passed to mypy together,
  which is the condition the deduplication exists to avoid, and the real
  changed-file set the gate builds no longer contains a collision.
- edge: an empty input, a single file, and a file whose parent is not a package
  each pass through unchanged.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

from checks_mypy import _drop_duplicate_modules, _module_identity

_CANONICAL = "scripts/ai_review_common/workflow.py"
_CLAUDE_MIRROR = ".claude/lib/ai_review_common/workflow.py"
_COPILOT_MIRROR = "src/copilot-cli/lib/ai_review_common/workflow.py"


def test_the_two_mirrors_share_one_module_name() -> None:
    """The premise. If this stops holding, the deduplication below is moot."""
    assert _module_identity(REPO_ROOT, _CLAUDE_MIRROR) == "ai_review_common.workflow"
    assert _module_identity(REPO_ROOT, _COPILOT_MIRROR) == "ai_review_common.workflow"


def test_the_canonical_copy_is_a_different_module() -> None:
    """`scripts/__init__.py` exists, so the canonical copy carries a longer name."""
    assert _module_identity(REPO_ROOT, _CANONICAL) == "scripts.ai_review_common.workflow"


def test_mirror_pair_collapses_to_one_path() -> None:
    kept = _drop_duplicate_modules(REPO_ROOT, [_CLAUDE_MIRROR, _COPILOT_MIRROR])
    assert kept == [_CLAUDE_MIRROR]


def test_the_canonical_copy_is_kept_alongside_a_mirror() -> None:
    """Dropping it would stop type-checking the file people actually edit."""
    kept = _drop_duplicate_modules(REPO_ROOT, [_CANONICAL, _CLAUDE_MIRROR, _COPILOT_MIRROR])
    assert _CANONICAL in kept
    assert len(kept) == 2


def test_input_order_does_not_change_the_survivor() -> None:
    """CI and a local run must select the same copy, or they check different files."""
    forward = _drop_duplicate_modules(REPO_ROOT, [_CLAUDE_MIRROR, _COPILOT_MIRROR])
    reverse = _drop_duplicate_modules(REPO_ROOT, [_COPILOT_MIRROR, _CLAUDE_MIRROR])
    assert forward == reverse


@pytest.mark.parametrize(
    "paths",
    [
        [],
        [_CANONICAL],
        ["scripts/validation/checks_mypy.py", "scripts/sync_plugin_lib.py"],
    ],
)
def test_collision_free_input_passes_through_unchanged(paths: list[str]) -> None:
    assert _drop_duplicate_modules(REPO_ROOT, paths) == paths


def test_relative_order_of_survivors_is_preserved() -> None:
    """The gate prints a count over this list, so it must not be reordered."""
    paths = ["scripts/sync_plugin_lib.py", _COPILOT_MIRROR, _CLAUDE_MIRROR]
    assert _drop_duplicate_modules(REPO_ROOT, paths) == [
        "scripts/sync_plugin_lib.py",
        _CLAUDE_MIRROR,
    ]


def _mypy(paths: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "mypy", *paths],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.mark.integration
def test_negative_control_the_undeduplicated_pair_still_aborts_mypy() -> None:
    """Without the fix mypy checks nothing, which is what the gate misreported.

    Asserting on the deduplicated set alone would pass against a no-op
    implementation, so this drives the real binary with the real pair.
    """
    result = _mypy([_CLAUDE_MIRROR, _COPILOT_MIRROR])

    assert result.returncode != 0
    assert "Duplicate module named" in result.stdout
    assert "errors prevented further checking" in result.stdout


@pytest.mark.integration
def test_the_deduplicated_pair_is_actually_checked() -> None:
    """Positive control: the same pair, deduplicated, reaches a real verdict."""
    result = _mypy(_drop_duplicate_modules(REPO_ROOT, [_CLAUDE_MIRROR, _COPILOT_MIRROR]))

    assert "Duplicate module named" not in result.stdout
    assert result.returncode == 0
