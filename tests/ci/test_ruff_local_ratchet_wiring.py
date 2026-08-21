"""Pre-push wiring tests for the ruff ratchets."""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUFF_COUNT_RATCHET = _REPO_ROOT / "scripts" / "ci" / "ruff_count_ratchet.py"


def _parse_scan_globs() -> tuple[str, ...]:
    """Extract _SCAN_GLOBS from ruff_count_ratchet.py via AST parsing."""
    module = ast.parse(_RUFF_COUNT_RATCHET.read_text(encoding="utf-8"))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(t, ast.Name) and t.id == "_SCAN_GLOBS" for t in node.targets):
            value = ast.literal_eval(node.value)
            assert isinstance(value, tuple) and all(isinstance(v, str) for v in value)
            return value
    raise AssertionError("_SCAN_GLOBS not found in ruff_count_ratchet.py")


def _pre_push_jobs() -> list[dict[str, Any]]:
    config = yaml.safe_load((_REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    jobs: list[dict[str, Any]] = []

    def collect(items: list[dict[str, Any]]) -> None:
        for item in items:
            group = item.get("group")
            if isinstance(group, dict):
                collect(group.get("jobs", []))
            else:
                jobs.append(item)

    collect(config["pre-push"]["jobs"])
    return jobs


def _job(name: str) -> dict[str, Any]:
    matches = [job for job in _pre_push_jobs() if job.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def test_changed_file_ruff_ratchet_blocks_in_pre_push() -> None:
    job = _job("python-lint-ratchet")

    assert job["run"] == "uv run --frozen --extra dev python scripts/ci/ruff_ratchet.py"
    assert "--exit-zero" not in job["run"]
    assert job["env"] == {"RUFF_RATCHET_BASE_REF": "origin/main"}
    assert job["glob"] == "**/*.py"


def test_whole_tree_ruff_count_ratchet_blocks_in_pre_push() -> None:
    job = _job("python-lint-count-ratchet")

    assert job["run"] == (
        "uv run --frozen --extra dev python scripts/ci/ruff_count_ratchet.py --base-ref origin/main"
    )
    assert "--exit-zero" not in job["run"]
    assert "--update" not in job["run"]
    assert job["glob"] == [
        "**/*.py",
        "**/*.pyi",
        "**/*.ipynb",
        "**/pyproject.toml",
        "**/ruff.toml",
        "**/.ruff.toml",
        "uv.lock",
        "scripts/ci/ruff_count_baseline.txt",
    ]


def test_count_ratchet_globs_cover_scan_globs() -> None:
    """Converse guard: every extension in _SCAN_GLOBS must have a corresponding glob."""
    job = _job("python-lint-count-ratchet")
    configured_globs = set(job["glob"])

    for pattern in _parse_scan_globs():
        expected_glob = f"**/{pattern}"
        assert expected_glob in configured_globs, (
            f"_SCAN_GLOBS has {pattern!r} but lefthook is missing {expected_glob!r}"
        )


def test_count_ratchet_glob_covers_nested_pyproject_toml() -> None:
    """A ruff-config-only edit to a nested pyproject.toml can move the whole-tree
    count (packages/semantic-hooks/pyproject.toml declares its own [tool.ruff]),
    so the trigger glob must reach it, not only the repo-root file.
    """
    job = _job("python-lint-count-ratchet")

    nested = "packages/semantic-hooks/pyproject.toml"
    assert (_REPO_ROOT / nested).is_file(), f"{nested} moved; update this test's target"
    assert any(
        PurePosixPath(nested).full_match(pattern) for pattern in job["glob"]
    ), f"{nested} matches no entry in {job['glob']!r}"


def test_count_ratchet_glob_covers_lockfile_only_ruff_upgrades() -> None:
    """The ratchet job runs ruff from the frozen uv environment, so a
    lockfile-only Ruff version bump can move the whole-tree count without
    touching any .py, .pyi, .ipynb, or pyproject.toml file. The trigger glob
    must reach uv.lock, matching pytest.yml's CI path filter.
    """
    job = _job("python-lint-count-ratchet")

    assert (_REPO_ROOT / "uv.lock").is_file(), "uv.lock moved; update this test's target"
    assert any(
        PurePosixPath("uv.lock").full_match(pattern) for pattern in job["glob"]
    ), f"uv.lock matches no entry in {job['glob']!r}"


def test_count_ratchet_glob_covers_alternate_ruff_config_filenames() -> None:
    """Ruff resolves config from pyproject.toml, ruff.toml, or .ruff.toml,
    checked per directory in that precedence order. A push touching only a
    ruff.toml or .ruff.toml (none exist in this repo today, but ruff accepts
    either anywhere in the tree) could move the whole-tree count without
    matching any *.py/*.pyi/*.ipynb/pyproject.toml entry.
    """
    job = _job("python-lint-count-ratchet")
    patterns = job["glob"]

    for candidate in ("ruff.toml", ".ruff.toml", "packages/semantic-hooks/ruff.toml"):
        assert any(
            PurePosixPath(candidate).full_match(pattern) for pattern in patterns
        ), f"{candidate} matches no entry in {patterns!r}"


def test_ruff_ratchets_have_distinct_local_blocking_jobs() -> None:
    ratchet_jobs = [
        job
        for job in _pre_push_jobs()
        if "scripts/ci/ruff_ratchet.py" in str(job.get("run", ""))
        or "scripts/ci/ruff_count_ratchet.py" in str(job.get("run", ""))
    ]

    assert {job["name"] for job in ratchet_jobs} == {
        "python-lint-ratchet",
        "python-lint-count-ratchet",
    }
    assert all("--exit-zero" not in job["run"] for job in ratchet_jobs)
