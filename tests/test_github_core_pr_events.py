"""Tests for the PR event wait helper in scripts/github_core/api.py.

Every gh call is faked by a dispatcher keyed on argv; no test runs gh. The
waitlist stderr fixture is the text gh 2.105.0 printed live on 2026-11-19 for
an account without Event Streams access.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from scripts.github_core import api as pr_events

URL = "https://github.com/o/r/pull/7"
WAITLIST_STDERR = (
    "event subscriptions are in preview and not enabled for this account: "
    "HTTP 403: Event subscriptions are not enabled for this account "
    "(https://api.github.com/event-subscriptions)\n"
)


class FakeClock:
    """Monotonic clock and sleep seam. Sleeping advances the clock."""

    def __init__(self) -> None:
        self._now = 1000.0
        self._sleeps: list[float] = []

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def sleep(self, seconds: float) -> None:
        self._sleeps.append(seconds)
        self.advance(seconds)

    @property
    def sleeps(self) -> list[float]:
        return list(self._sleeps)


class FakeGh:
    """Answer ``gh --version`` and ``gh event listen`` by argv."""

    def __init__(
        self,
        clock: FakeClock,
        *,
        version: str = "gh version 2.105.0 (2026-11-17)\n",
        listen_rc: int = 0,
        listen_stderr: str = "",
        listen_takes: float = 3.0,
        listen_raises: BaseException | None = None,
        version_raises: BaseException | None = None,
    ) -> None:
        self._clock = clock
        self._version = version
        self._listen = (listen_rc, listen_stderr)
        self._listen_takes = listen_takes
        self._listen_raises = listen_raises
        self._version_raises = version_raises
        self._calls: list[list[str]] = []

    def set_listen_result(self, returncode: int, stderr: str = "") -> None:
        self._listen = (returncode, stderr)

    def __call__(self, argv: list[str], **kwargs: object) -> SimpleNamespace:
        self._calls.append(list(argv))
        assert kwargs.get("errors") == "replace"
        assert kwargs.get("capture_output") is True
        if argv == ["gh", "--version"]:
            if self._version_raises is not None:
                raise self._version_raises
            return SimpleNamespace(returncode=0, stdout=self._version, stderr="")
        if argv[:3] == ["gh", "event", "listen"]:
            if self._listen_raises is not None:
                raise self._listen_raises
            self._clock.advance(self._listen_takes)
            returncode, stderr = self._listen
            stdout = '{"type":"x"}\n' if returncode == 0 else ""
            return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
        raise AssertionError(f"unexpected command: {argv}")

    @property
    def calls(self) -> list[list[str]]:
        return [list(c) for c in self._calls]

    def listen_calls(self) -> list[list[str]]:
        return [c for c in self.calls if c[:3] == ["gh", "event", "listen"]]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(autouse=True)
def _listen_enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv(pr_events.DISABLE_ENV, raising=False)
    monkeypatch.delenv("GH_HOST", raising=False)
    pr_events.reset_listen_state()
    yield
    pr_events.reset_listen_state()


def _install(monkeypatch: pytest.MonkeyPatch, gh: FakeGh) -> FakeGh:
    monkeypatch.setattr(pr_events.subprocess, "run", gh)
    return gh


def _wait(clock: FakeClock, seconds: float = 30, **kw: float) -> str:
    return pr_events.wait_for_pr_event(
        URL, pr_events.ALL_PR_EVENTS, seconds, sleep=clock.sleep, clock=clock, **kw
    )


# Listen path


def test_event_returns_event_and_passes_documented_flags(monkeypatch, clock):
    gh = _install(monkeypatch, FakeGh(clock))

    outcome = _wait(clock, 30)

    assert outcome == "event"
    assert gh.listen_calls() == [
        [
            "gh",
            "event",
            "listen",
            "--resource",
            URL,
            "--event",
            ",".join(pr_events.ALL_PR_EVENTS),
            "--timeout",
            "30s",
        ]
    ]
    assert clock.sleeps == []


def test_event_wake_sleeps_up_to_min_seconds_floor(monkeypatch, clock):
    _install(monkeypatch, FakeGh(clock, listen_takes=3.0))

    outcome = _wait(clock, 30, min_seconds=10)

    assert outcome == "event"
    assert clock.sleeps == [pytest.approx(7.0)]


def test_event_after_floor_does_not_sleep(monkeypatch, clock):
    _install(monkeypatch, FakeGh(clock, listen_takes=12.0))

    assert _wait(clock, 30, min_seconds=10) == "event"
    assert clock.sleeps == []


def test_listen_timeout_exit_8_returns_timeout_without_extra_sleep(monkeypatch, clock):
    _install(monkeypatch, FakeGh(clock, listen_rc=8, listen_takes=30.0))

    assert _wait(clock, 30) == "timeout"
    assert clock.sleeps == []


def test_child_killed_after_grace_returns_timeout(monkeypatch, clock):
    gh = FakeGh(clock, listen_raises=subprocess.TimeoutExpired(["gh"], 45))
    _install(monkeypatch, gh)

    assert _wait(clock, 30) == "timeout"
    assert pr_events.listen_available() is True


def test_version_probe_runs_once_per_process(monkeypatch, clock):
    gh = _install(monkeypatch, FakeGh(clock))

    _wait(clock)
    _wait(clock)

    assert gh.calls.count(["gh", "--version"]) == 1
    assert len(gh.listen_calls()) == 2


# Fallback path


def test_waitlist_403_sleeps_rest_of_window_and_disables_listening(monkeypatch, clock):
    gh = _install(
        monkeypatch, FakeGh(clock, listen_rc=1, listen_stderr=WAITLIST_STDERR, listen_takes=1.0)
    )

    first = _wait(clock, 30)
    second = _wait(clock, 30)

    assert (first, second) == ("fallback", "fallback")
    assert clock.sleeps == [pytest.approx(29.0), 30]
    assert len(gh.listen_calls()) == 1


def test_transient_failure_falls_back_for_this_call_only(monkeypatch, clock):
    gh = FakeGh(
        clock,
        listen_rc=1,
        listen_stderr="HTTP 422: subscription limit reached\n",
        listen_takes=2.0,
    )
    _install(monkeypatch, gh)

    assert _wait(clock, 30) == "fallback"
    assert clock.sleeps == [pytest.approx(28.0)]
    gh.set_listen_result(0)
    assert _wait(clock, 30) == "event"
    assert len(gh.listen_calls()) == 2


@pytest.mark.parametrize(
    "version",
    ["gh version 2.104.0 (2026-11-12)\n", "gh version 1.99.9\n", "not a version\n"],
)
def test_old_or_unparseable_gh_sleeps_without_listening(monkeypatch, clock, version):
    gh = _install(monkeypatch, FakeGh(clock, version=version))

    assert _wait(clock, 30) == "fallback"
    assert clock.sleeps == [30]
    assert gh.listen_calls() == []


def test_gh_missing_sleeps(monkeypatch, clock):
    gh = _install(monkeypatch, FakeGh(clock, version_raises=FileNotFoundError("gh")))

    assert _wait(clock, 30) == "fallback"
    assert clock.sleeps == [30]
    assert gh.listen_calls() == []


def test_listen_binary_vanishing_disables_listening(monkeypatch, clock):
    _install(monkeypatch, FakeGh(clock, listen_raises=FileNotFoundError("gh")))

    assert _wait(clock, 30) == "fallback"
    assert clock.sleeps == [30]
    assert pr_events.listen_available() is False


def test_non_github_com_host_sleeps(monkeypatch, clock):
    monkeypatch.setenv("GH_HOST", "ghe.example.com")
    gh = _install(monkeypatch, FakeGh(clock))

    assert _wait(clock, 30) == "fallback"
    assert gh.calls == []


def test_off_switch_sleeps_even_after_support_was_cached(monkeypatch, clock):
    gh = _install(monkeypatch, FakeGh(clock))
    assert _wait(clock, 30) == "event"

    monkeypatch.setenv(pr_events.DISABLE_ENV, "0")

    assert _wait(clock, 30) == "fallback"
    assert clock.sleeps == [30]
    assert len(gh.listen_calls()) == 1


def test_sub_second_window_sleeps_without_spawning_gh(monkeypatch, clock):
    gh = _install(monkeypatch, FakeGh(clock))

    assert _wait(clock, 0.5) == "fallback"
    assert clock.sleeps == [0.5]
    assert gh.calls == []


def test_default_seams_use_time_module(monkeypatch):
    monkeypatch.setenv(pr_events.DISABLE_ENV, "0")
    slept: list[float] = []
    monkeypatch.setattr(pr_events.time, "sleep", slept.append)

    assert pr_events.wait_for_pr_event(URL, pr_events.CHECK_EVENTS, 10) == "fallback"
    assert slept == [10]


def test_pr_url_builds_github_com_resource():
    assert pr_events.pr_url("o", "r", 7) == URL
