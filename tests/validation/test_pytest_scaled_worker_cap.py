"""Issue #6199: the pre-push pytest worker cap scales to the host.

A fixed cap of 4 left most cores idle on a workstation. The scaled cap is half
the visible CPUs, at least 4 and at most 16, and never above the CPU count. A
positive integer cap keeps its fixed meaning, and `AI_AGENTS_PYTEST_WORKERS`
still wins over both.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy

_WORKER_FLAGS = ("-n", "--numprocesses")


def _bulk_workers(root: Path) -> str | None:
    """Return the `-n` value on the bulk (first) pre-push pytest command."""
    command = policy._pytest_commands(root)[0]
    for index, token in enumerate(command):
        if token in _WORKER_FLAGS:
            return command[index + 1]
    return None


@pytest.mark.parametrize(
    ("visible_cpus", "expected"),
    [
        (1, 1),
        (2, 2),
        (3, 3),
        (4, 4),
        (7, 4),
        (8, 4),
        (9, 4),
        (10, 5),
        (16, 8),
        (32, 16),
        (33, 16),
        (48, 16),
        (128, 16),
    ],
)
def test_scaled_worker_cap_table(visible_cpus: int, expected: int) -> None:
    assert policy.scaled_worker_cap(visible_cpus) == expected


@pytest.mark.parametrize("visible_cpus", range(1, 257))
def test_scaled_worker_cap_invariants(visible_cpus: int) -> None:
    workers = policy.scaled_worker_cap(visible_cpus)

    assert 1 <= workers <= visible_cpus
    assert workers <= policy.PYTEST_SCALED_WORKERS_MAX
    assert workers >= min(visible_cpus, policy.PYTEST_SCALED_WORKERS_MIN)


def test_scaled_worker_cap_never_shrinks_when_cpus_grow() -> None:
    caps = [policy.scaled_worker_cap(cpus) for cpus in range(1, 257)]

    assert caps == sorted(caps)


@pytest.mark.parametrize(
    ("visible_cpus", "expected"),
    [(1, "1"), (4, "4"), (8, "4"), (48, "16"), (128, "16")],
)
def test_scaled_cap_env_reaches_bulk_and_mutation_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    visible_cpus: int,
    expected: str,
) -> None:
    monkeypatch.delenv(policy.PYTEST_WORKERS_ENV, raising=False)
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, policy.PYTEST_WORKER_CAP_SCALED)
    monkeypatch.setattr(policy, "_visible_cpu_count", lambda: visible_cpus)

    commands = policy._pytest_commands(tmp_path)

    assert _bulk_workers(tmp_path) == expected
    assert [c[c.index("-n") + 1] for c in commands if "-n" in c] == [expected, expected]


@pytest.mark.parametrize("raw", ["scaled", "SCALED", "  Scaled  "])
def test_scaled_spelling_is_case_and_space_insensitive(raw: str) -> None:
    assert policy.parse_pytest_worker_cap(raw) is None


@pytest.mark.parametrize(("raw", "expected"), [("4", 4), (" 12 ", 12), ("1", 1)])
def test_integer_cap_stays_a_fixed_cap(raw: str, expected: int) -> None:
    assert policy.parse_pytest_worker_cap(raw) == expected


@pytest.mark.parametrize(("visible_cpus", "expected"), [(2, "2"), (48, "6"), (128, "6")])
def test_integer_cap_ignores_the_scaled_range(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    visible_cpus: int,
    expected: str,
) -> None:
    monkeypatch.delenv(policy.PYTEST_WORKERS_ENV, raising=False)
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, "6")
    monkeypatch.setattr(policy, "_visible_cpu_count", lambda: visible_cpus)

    assert _bulk_workers(tmp_path) == expected


def test_explicit_worker_override_wins_over_the_scaled_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(policy.PYTEST_WORKERS_ENV, "3")
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, policy.PYTEST_WORKER_CAP_SCALED)
    monkeypatch.setattr(policy, "_visible_cpu_count", lambda: 128)

    assert _bulk_workers(tmp_path) == "3"


@pytest.mark.parametrize("raw", ["0", "-1", "auto", "half", "scaled4"])
def test_invalid_cap_error_names_the_scaled_word(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: str
) -> None:
    monkeypatch.delenv(policy.PYTEST_WORKERS_ENV, raising=False)
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, raw)

    with pytest.raises(ValueError, match="'scaled'"):
        policy._pytest_commands(tmp_path)


def test_blank_cap_keeps_the_ci_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(policy.PYTEST_WORKERS_ENV, raising=False)
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, "  ")
    monkeypatch.setattr(policy, "_visible_cpu_count", lambda: 128)

    assert _bulk_workers(tmp_path) == "auto"
