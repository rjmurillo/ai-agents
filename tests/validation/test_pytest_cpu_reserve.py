"""The pre-push pytest job leaves CPUs for its sibling jobs (issue #5383).

``AI_AGENTS_PYTEST_WORKER_CAP`` bounds the xdist workers of one job. The
``python-tests`` job runs beside ``pre-pr-validation`` in one parallel Lefthook
group, so ``AI_AGENTS_PYTEST_CPU_RESERVE`` names the CPUs those siblings hold.
The worker count is ``min(cap, visible CPUs - reserve)``, never below one.
``AI_AGENTS_PYTEST_WORKERS`` still wins, and the reserve alone changes nothing.
"""

from __future__ import annotations

import pytest

from scripts.validation import git_hook_policy as policy


def _workers(argv: list[str]) -> str:
    """Return the value after ``-n`` in the flags the policy builds."""
    return argv[argv.index("-n") + 1]


@pytest.fixture(autouse=True)
def _clean_worker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(policy.PYTEST_WORKERS_ENV, raising=False)
    monkeypatch.delenv(policy.PYTEST_WORKER_CAP_ENV, raising=False)
    monkeypatch.delenv(policy.PYTEST_CPU_RESERVE_ENV, raising=False)


@pytest.mark.parametrize(
    ("cap", "visible_cpus", "reserve", "expected"),
    [
        (4, 4, 0, 4),
        (4, 4, 1, 3),
        (4, 8, 1, 4),
        (4, 2, 1, 1),
        (4, 1, 1, 1),
        (4, 1, 3, 1),
        (2, 64, 0, 2),
    ],
)
def test_local_worker_budget_is_cap_or_cpus_minus_reserve_floored_at_one(
    cap: int, visible_cpus: int, reserve: int, expected: int
) -> None:
    assert policy.local_worker_budget(cap, visible_cpus, reserve) == expected


@pytest.mark.parametrize("visible_cpus", range(1, 70))
@pytest.mark.parametrize("reserve", [0, 1, 2, 3])
def test_worker_budget_leaves_the_reserve_whenever_the_host_can_spare_it(
    visible_cpus: int, reserve: int
) -> None:
    workers = policy.local_worker_budget(4, visible_cpus, reserve)

    assert 1 <= workers <= 4
    assert workers <= max(1, visible_cpus - reserve)
    if visible_cpus > reserve:
        assert workers + reserve <= visible_cpus


@pytest.mark.parametrize(("visible_cpus", "expected"), [(1, "1"), (2, "1"), (4, "3"), (64, "4")])
def test_cpu_reserve_env_reduces_the_capped_worker_count(
    monkeypatch: pytest.MonkeyPatch, visible_cpus: int, expected: str
) -> None:
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, "4")
    monkeypatch.setenv(policy.PYTEST_CPU_RESERVE_ENV, "1")
    monkeypatch.setattr(policy, "_visible_cpu_count", lambda: visible_cpus)

    assert _workers(policy._pytest_parallel_flags()) == expected


def test_explicit_worker_override_wins_over_cpu_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(policy.PYTEST_WORKERS_ENV, "8")
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, "4")
    monkeypatch.setenv(policy.PYTEST_CPU_RESERVE_ENV, "3")

    assert _workers(policy._pytest_parallel_flags()) == "8"


def test_cpu_reserve_without_a_cap_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(policy.PYTEST_CPU_RESERVE_ENV, "2")

    assert _workers(policy._pytest_parallel_flags()) == "auto"


def test_blank_cpu_reserve_means_no_reservation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, "4")
    monkeypatch.setenv(policy.PYTEST_CPU_RESERVE_ENV, "  ")
    monkeypatch.setattr(policy, "_visible_cpu_count", lambda: 4)

    assert _workers(policy._pytest_parallel_flags()) == "4"


@pytest.mark.parametrize("raw", ["-1", "one", "1.5", "auto"])
def test_invalid_cpu_reserve_is_rejected(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, "4")
    monkeypatch.setenv(policy.PYTEST_CPU_RESERVE_ENV, raw)

    with pytest.raises(ValueError, match=policy.PYTEST_CPU_RESERVE_ENV):
        policy._pytest_parallel_flags()


def test_parse_pytest_cpu_reserve_accepts_zero_and_strips_space() -> None:
    assert policy.parse_pytest_cpu_reserve(" 0 ") == 0
    assert policy.parse_pytest_cpu_reserve("2") == 2
