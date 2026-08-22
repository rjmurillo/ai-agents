"""The pytest gate must run whenever the episode store it pins changes.

``tests/skills/memory/test_extract_session_episode.py`` asserts the committed
episode store has usable event ids (issue #3633). That pin only protects the
store if the job carrying it actually runs, and ``pytest.yml`` gates its test
job behind a ``dorny/paths-filter`` entry. A hand edit or merge-conflict
resolution touching only ``.agents/memory/episodes/*.json`` matches no
``**/*.py`` pattern, so without an explicit entry the gate skips and the pin
never fires against the one population the issue names.

The filter already carries non-Python inputs (``uv.lock``, ``lefthook.yml``,
``.config/wt.toml``), so it is the set of inputs that change Python test
outcomes, not the set of Python files.

The ``.github`` YAML tree is the second such population (issue #3964). The gates
under ``tests/workflows/`` read those files, so a PR touching only them is the
change class those gates exist for.

The canonical rule tree and both generated instruction trees are a third
population (issue #4408). Contract tests read their tracked Markdown directly,
so all three roots must trigger pytest without widening the filter to unrelated
Markdown such as historical session logs.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/pytest.yml"
EPISODE_STORE = REPO_ROOT / ".agents/memory/episodes"
GITHUB_DIR = REPO_ROOT / ".github"
RULE_INPUT_ROOTS = (
    ".claude/rules",
    ".github/instructions",
    "src/copilot-cli/instructions",
)

PATHS_FILTER_ACTION = "dorny/paths-filter"
# The action version ``_selected`` models. Re-read ``src/filter.ts`` at this
# commit before changing the pin: ``MatchOptions`` is where ``dot`` is set.
PATHS_FILTER_PIN = f"{PATHS_FILTER_ACTION}@ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d"


def _select_paths_filter(steps: Iterable[dict]) -> dict:
    """The step that runs the action, not the first step shaped like it.

    Selecting on ``with.filters`` alone hands every assertion below whichever
    other step grows that key first. The pin assertion would then report a SHA
    mismatch, or raise ``KeyError`` on a step carrying no ``uses``, about a step
    that was never the subject. Matching on the action name rather than on the
    pin keeps that assertion able to report a version bump.
    """
    for step in steps:
        if str(step.get("uses", "")).startswith(f"{PATHS_FILTER_ACTION}@"):
            return step
    raise AssertionError(f"pytest.yml check-paths has no {PATHS_FILTER_ACTION} step")


def _paths_filter_step() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return _select_paths_filter(workflow["jobs"]["check-paths"]["steps"])


def _python_filter() -> list[str]:
    return yaml.safe_load(_paths_filter_step()["with"]["filters"])["python"]


def test_the_filter_covers_the_episode_store():
    assert ".agents/memory/episodes/**" in _python_filter()


def test_the_entry_matches_the_directory_the_pin_reads():
    """A filter naming a path the pin does not read protects nothing."""
    source = (
        REPO_ROOT / "tests/skills/memory/test_extract_session_episode.py"
    ).read_text(encoding="utf-8")
    assert '"memory" / "episodes"' in source
    assert EPISODE_STORE.is_dir()


def test_the_gate_still_covers_plain_python_sources():
    """Guard against a narrowing that trades one population for another."""
    entries = _python_filter()
    assert "**/*.py" in entries
    assert "tests/conftest.py" in entries


def _selected(path: str, patterns: Iterable[str]) -> bool:
    """Whether ``dorny/paths-filter`` selects a repo-relative path.

    The action compiles every entry as ``picomatch(pattern, MatchOptions)`` with
    ``const MatchOptions = {dot: true}`` (``src/filter.ts`` at the pinned SHA).
    ``dot: true`` is why a leading-wildcard entry such as ``**/*.yml`` reaches a
    path under ``.github/``; picomatch's own default would not.

    ``PurePosixPath.full_match`` has no dot rule either, which is what makes it
    a usable stand-in. Checked rather than assumed: every entry in this filter
    paired with every tracked file, 172,986 pairs on the tree at 5e69d3558,
    produced zero disagreements against picomatch under ``{dot: true}``.
    """
    return any(PurePosixPath(path).full_match(str(pattern)) for pattern in patterns)


def _github_yaml_files() -> list[str]:
    return sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in GITHUB_DIR.rglob("*.y*ml")
        if path.is_file()
    )


def _tracked_files(*roots: str) -> list[str]:
    """Return tracked files from HEAD, never untracked working-tree residue."""
    result = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--name-only", "HEAD", "--", *roots],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return sorted(path.decode("utf-8") for path in result.stdout.split(b"\0") if path)


def test_the_matcher_model_matches_the_pinned_action_version():
    """``_selected`` is only right while the action still passes ``dot: true``."""
    assert _paths_filter_step()["uses"] == PATHS_FILTER_PIN, (
        "pytest.yml pins a different dorny/paths-filter build than _selected was "
        "modelled from. Read src/filter.ts at the new SHA, confirm MatchOptions "
        "still sets dot: true, then update PATHS_FILTER_PIN."
    )


def test_the_filter_covers_every_github_yaml_file():
    """Issue #3964: the workflow gates must run on workflow-only pull requests.

    ``tests/workflows/test_workflow_job_permissions.py`` freezes the set of jobs
    that inherit a workflow-level write scope. It catches a new offender only if
    pytest runs on the PR that adds one, and such a PR often changes nothing but
    ``.github`` YAML.

    That once did not hold. On 2026-07-30 this filter carried no YAML entry at
    all: run 30586314576 echoes the filter it received (``**/*.py``,
    ``**/*.pyi``, ``**/*.ipynb``, then literals), PR #4053's single changed file
    ``.github/workflows/nightly-cli-smoke.yml`` matched none of them, and the
    ``Run pytest`` step reported ``skipped``. PR #4141 added ``**/*.yml`` and
    ``**/*.yaml`` on 2026-08-01 for the security-suppression gate, which closed
    it as a side effect. Nothing recorded that the workflow gates depend on those
    two entries. This does.

    Asserting per file rather than on a literal entry keeps it honest when the
    filter is rewritten and when a workflow or composite action is added later.
    """
    patterns = _python_filter()
    inputs = _github_yaml_files()
    assert inputs, "no .github YAML found, so this assertion would be vacuous"

    unselected = [path for path in inputs if not _selected(path, patterns)]

    assert not unselected, (
        "These files match no entry in pytest.yml's `python` filter, so a PR "
        "touching only them skips pytest and every gate that reads them "
        f"(issue #3964): {unselected}\nFilter entries: {patterns}"
    )


@pytest.mark.parametrize("root", RULE_INPUT_ROOTS)
def test_the_filter_names_each_rule_input_root(root: str):
    """Keep the three contract trees explicit instead of matching all Markdown."""
    assert f"{root}/**" in _python_filter()


@pytest.mark.parametrize("root", RULE_INPUT_ROOTS)
@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_filter_covers_every_tracked_rule_input(root: str):
    """Issue #4408: every tracked rule source and mirror must trigger pytest."""
    patterns = _python_filter()
    inputs = _tracked_files(root)
    assert inputs, f"{root} has no tracked files, so this assertion would be vacuous"

    unselected = [path for path in inputs if not _selected(path, patterns)]

    assert not unselected, (
        "These tracked Python-test inputs match no entry in pytest.yml's "
        f"`python` filter: {unselected}\nFilter entries: {patterns}"
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_filter_still_skips_tracked_session_markdown():
    """The fix must not widen the filter to unrelated Markdown."""
    patterns = _python_filter()
    inputs = [
        path
        for path in _tracked_files(".agents/sessions")
        if path.endswith(".md")
    ]
    assert inputs, "no tracked Markdown session logs, so this control is vacuous"

    selected = [path for path in inputs if _selected(path, patterns)]

    assert not selected, (
        "Unrelated session Markdown now triggers pytest; keep the filter scoped "
        f"to direct test inputs: {selected}"
    )


def test_the_filter_covers_a_nested_pyproject_toml():
    """A ruff-config-only edit to a nested pyproject.toml can move the whole-tree
    ruff count ratchet (packages/semantic-hooks/pyproject.toml declares its own
    [tool.ruff]), so the CI gate must trigger on it, not only the repo-root file.
    """
    nested = "packages/semantic-hooks/pyproject.toml"
    assert (REPO_ROOT / nested).is_file(), f"{nested} moved; update this test's target"
    assert _selected(nested, _python_filter()), (
        f"{nested} matches no entry in pytest.yml's `python` filter, so a push "
        "touching only that nested ruff config skips the whole-tree count ratchet."
    )


def test_the_filter_covers_alternate_ruff_config_filenames():
    """Ruff resolves config from pyproject.toml, ruff.toml, or .ruff.toml, checked
    per directory. Neither alternate name exists in this repo today, but ruff
    accepts either anywhere in the tree, so a future ruff.toml/.ruff.toml-only
    push must still trigger the whole-tree count ratchet.
    """
    patterns = _python_filter()
    for candidate in ("ruff.toml", ".ruff.toml", "packages/semantic-hooks/ruff.toml"):
        assert _selected(candidate, patterns), (
            f"{candidate} matches no entry in pytest.yml's `python` filter, so a "
            "push touching only that ruff config skips the whole-tree count ratchet."
        )


class TestSelectPathsFilter:
    def test_a_decoy_step_carrying_filters_is_not_selected(self):
        decoy = {"name": "some later step", "with": {"filters": "python:\n  - '**/*.md'\n"}}
        action = {"uses": PATHS_FILTER_PIN, "with": {"filters": "python:\n  - '**/*.py'\n"}}

        assert _select_paths_filter([decoy, action]) is action

    def test_a_different_pin_of_the_same_action_is_still_selected(self):
        """So the pin assertion reports a SHA bump, not a missing step."""
        bumped = {"uses": f"{PATHS_FILTER_ACTION}@" + "0" * 40, "with": {"filters": "python:\n"}}

        assert _select_paths_filter([bumped]) is bumped

    def test_no_action_step_raises(self):
        with pytest.raises(AssertionError, match=PATHS_FILTER_ACTION):
            _select_paths_filter([{"uses": "actions/checkout@v7"}])


class TestSelected:
    def test_a_leading_wildcard_reaches_a_dot_directory(self):
        assert _selected(".github/workflows/pytest.yml", ["**/*.yml"])

    def test_a_leading_wildcard_matches_a_root_level_file(self):
        assert _selected("lefthook.yml", ["**/*.yml"])

    def test_a_directory_entry_selects_a_file_beneath_it(self):
        assert _selected(".agents/memory/episodes/e.json", [".agents/memory/episodes/**"])

    def test_an_extension_mismatch_is_not_selected(self):
        assert not _selected(".github/workflows/a.yaml", ["**/*.yml"])

    def test_a_sibling_dot_directory_is_not_selected(self):
        assert not _selected(".github/workflows/a.yml", [".agents/memory/episodes/**"])

    def test_no_entries_select_nothing(self):
        assert not _selected("scripts/ci/ruff_ratchet.py", [])
