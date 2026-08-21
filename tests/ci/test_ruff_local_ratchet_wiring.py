"""Pre-push wiring tests for the ruff ratchets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]


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
        "pyproject.toml",
        "scripts/ci/ruff_count_baseline.txt",
    ]


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
