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
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/pytest.yml"
EPISODE_STORE = REPO_ROOT / ".agents/memory/episodes"


def _python_filter() -> list[str]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in workflow["jobs"]["check-paths"]["steps"]:
        with_block = step.get("with") or {}
        if "filters" in with_block:
            return yaml.safe_load(with_block["filters"])["python"]
    raise AssertionError("pytest.yml has no paths-filter step")


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
