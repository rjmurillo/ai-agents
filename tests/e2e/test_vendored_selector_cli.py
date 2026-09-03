"""Unconditional CLI contract for the shipped `/review` axis selector.

`select_axes.py` ships to consumers twice: copied into the vendored plugin tree
and generated into `src/copilot-cli/`. Both copies resolve their axis prompts
from `references/` next to the script, never from the working directory, so a
consumer running `/review` from their own repo root gets the shipped axis set.

The existing vendored `/review` run in ``test_vendored_review_e2e.py`` is gated
behind ``RUN_CLI_E2E=1`` and a real ``claude`` binary, so it is skipped in CI.
Nothing else executed a shipped selector: the other tests import the canonical
module from the source checkout, where the working directory happens to be the
repo root and a cwd-relative resolution bug would not show. These tests run
unconditionally, as a subprocess, from a foreign working directory.

Kept out of ``test_vendored_review_e2e.py`` because that module is already over
the 500-line taste limit.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.lib.vendored_copy import copy_vendored_entry

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_SKILL = REPO_ROOT / ".claude" / "skills" / "review"
COPILOT_SKILL = REPO_ROOT / "src" / "copilot-cli" / "skills" / "review"

# A path that matches ci-deploy-artifacts and executable-code, so a correct run
# selects a known, non-trivial set rather than only the always-on axes. The
# sets are exact, not a subset: a generated selector that dropped one of these
# routes would still satisfy a containment check on the others.
CLASSIFIED_PATH = "scripts/deploy.py"
EXPECTED_CANONICAL = {"analyst", "code-quality", "devops", "security"}
EXPECTED_LOCAL = {"code-qualities-assessment", "taste-lints"}

_TIMEOUT_S = 60


def _run(skill_dir: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the shipped selector as a consumer would, from `cwd`."""
    return subprocess.run(
        [sys.executable, str(skill_dir / "scripts" / "select_axes.py"), *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_S,
        check=False,
    )


@pytest.fixture
def foreign_cwd(tmp_path: Path) -> Path:
    """A working directory with no `references/`, so cwd resolution would fail."""
    cwd = tmp_path / "consumer-repo"
    cwd.mkdir()
    assert not (cwd / "references").exists()
    return cwd


@pytest.fixture(params=["vendored-copy", "copilot-generated"])
def shipped_skill(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """Each tree a consumer can end up with: a byte-for-byte copy, and the
    generated Copilot tree."""
    if request.param == "copilot-generated":
        assert COPILOT_SKILL.is_dir(), f"generated skill tree missing: {COPILOT_SKILL}"
        return COPILOT_SKILL
    target = tmp_path / "plugin" / "review"
    target.parent.mkdir(parents=True, exist_ok=True)
    copy_vendored_entry(CLAUDE_SKILL, target)
    return target


def test_selector_resolves_references_beside_the_script(
    shipped_skill: Path, foreign_cwd: Path
) -> None:
    """`--deep` selects every discovered axis, so the count proves which
    directory the script read."""
    shipped_axes = {p.stem for p in (shipped_skill / "references").glob("*.md")}
    assert shipped_axes, f"no axis prompts shipped in {shipped_skill}/references"

    result = _run(shipped_skill, foreign_cwd, "--changed-path", CLASSIFIED_PATH, "--deep")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    # spec-compliance is the Stage-1 gate and is excluded from Stage-2.
    selected = set(payload["canonical_selected"])
    assert selected == shipped_axes - {payload["stage1_axis"]}


def test_selector_emits_parseable_json_on_stdout(
    shipped_skill: Path, foreign_cwd: Path
) -> None:
    """Exit 0 and a JSON object carrying the documented fields."""
    result = _run(shipped_skill, foreign_cwd, "--changed-path", CLASSIFIED_PATH)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    for field in ("canonical_selected", "local_selected", "skipped", "fail_closed"):
        assert field in payload, f"{field} missing from selector output"
    assert set(payload["canonical_selected"]) == EXPECTED_CANONICAL
    # local_selected is asserted too: it carries the scanner-capability
    # narrowing, so a generated selector that lost it would route
    # code-qualities-assessment and taste-lints at files neither scanner reads.
    assert set(payload["local_selected"]) == EXPECTED_LOCAL
    assert payload["fail_closed"] is False
    assert payload["skipped"], "a risk-mode run skipped nothing, so nothing was classified"


def test_missing_references_dir_is_a_config_error(
    shipped_skill: Path, foreign_cwd: Path
) -> None:
    """Negative control for the resolution test above.

    Without it, a selector that silently emitted an empty set from a wrong
    directory would still pass. Exit 2 is the documented config-error code.
    """
    empty = foreign_cwd / "no-axes"
    empty.mkdir()

    result = _run(
        shipped_skill,
        foreign_cwd,
        "--changed-path",
        CLASSIFIED_PATH,
        "--references-dir",
        str(empty),
    )

    assert result.returncode == 2
    assert result.stdout.strip() == ""


def test_unknown_pinned_axis_is_a_config_error(
    shipped_skill: Path, foreign_cwd: Path
) -> None:
    """A typo in a pin fails closed rather than selecting a phantom axis."""
    result = _run(
        shipped_skill,
        foreign_cwd,
        "--changed-path",
        CLASSIFIED_PATH,
        "--pin",
        "not-a-real-axis",
    )

    assert result.returncode == 2
    assert result.stdout.strip() == ""
