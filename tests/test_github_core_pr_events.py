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
UNKNOWN_COMMAND_STDERR = 'unknown command "event" for "gh"\n'
RATE_LIMIT_STDERR = "HTTP 403: You have exceeded a secondary rate limit\n"
LIMIT_STDERR = "HTTP 422: subscription limit reached\n"


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
        version_rc: int = 0,
        version_takes: float = 0.0,
        version_raises: BaseException | None = None,
        listen_rc: int = 0,
        listen_stderr: str = "",
        listen_takes: float = 3.0,
        listen_hangs: bool = False,
        listen_raises: BaseException | None = None,
    ) -> None:
        self._clock = clock
        self._version = (version_rc, version, version_takes, version_raises)
        self._listen = (listen_rc, listen_stderr)
        self._listen_takes = listen_takes
        self._listen_hangs = listen_hangs
        self._listen_raises = listen_raises
        self._calls: list[tuple[list[str], object]] = []

    def set_listen_result(self, returncode: int, stderr: str = "") -> None:
        self._listen = (returncode, stderr)

    def __call__(self, argv: list[str], **kwargs: object) -> SimpleNamespace:
        self._calls.append((list(argv), kwargs.get("timeout")))
        assert kwargs.get("errors") == "replace"
        assert kwargs.get("capture_output") is True
        if argv == ["gh", "--version"]:
            return self._answer_version()
        if argv[:3] == ["gh", "event", "listen"]:
            return self._answer_listen(argv, kwargs.get("timeout"))
        raise AssertionError(f"unexpected command: {argv}")

    def _answer_version(self) -> SimpleNamespace:
        returncode, stdout, takes, raises = self._version
        self._clock.advance(takes)
        if raises is not None:
            raise raises
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")

    def _answer_listen(self, argv: list[str], kill_after: object) -> SimpleNamespace:
        if self._listen_raises is not None:
            raise self._listen_raises
        if self._listen_hangs:
            assert isinstance(kill_after, float | int)
            self._clock.advance(float(kill_after))
            raise subprocess.TimeoutExpired(argv, float(kill_after))
        self._clock.advance(self._listen_takes)
        returncode, stderr = self._listen
        stdout = '{"type":"x"}\n' if returncode == 0 else ""
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    @property
    def calls(self) -> list[list[str]]:
        return [list(argv) for argv, _ in self._calls]

    def listen_calls(self) -> list[list[str]]:
        return [c for c in self.calls if c[:3] == ["gh", "event", "listen"]]

    def listen_kill_after(self) -> list[object]:
        return [t for argv, t in self._calls if argv[:3] == ["gh", "event", "listen"]]


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


def _timed_wait(clock: FakeClock, seconds: float = 30) -> tuple[str, float]:
    before = clock()
    outcome = _wait(clock, seconds)
    return outcome, clock() - before


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
            "28s",
        ]
    ]
    assert gh.listen_kill_after() == [30]
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


def test_listen_timeout_exit_8_sleeps_out_the_window(monkeypatch, clock):
    _install(monkeypatch, FakeGh(clock, listen_rc=8, listen_takes=28.0))

    outcome, elapsed = _timed_wait(clock, 30)

    assert outcome == "timeout"
    assert elapsed == pytest.approx(30.0)
    assert clock.sleeps == [pytest.approx(2.0)]


def test_version_probe_time_counts_inside_the_window(monkeypatch, clock):
    gh = _install(monkeypatch, FakeGh(clock, version_takes=4.0, listen_rc=8, listen_takes=24.0))

    _, elapsed = _timed_wait(clock, 30)

    assert gh.listen_calls()[0][-1] == "24s"
    assert gh.listen_kill_after() == [pytest.approx(26.0)]
    assert elapsed == pytest.approx(30.0)


def test_version_probe_runs_once_per_process(monkeypatch, clock):
    gh = _install(monkeypatch, FakeGh(clock))

    _wait(clock)
    _wait(clock)

    assert gh.calls.count(["gh", "--version"]) == 1
    assert len(gh.listen_calls()) == 2


def test_first_listen_prints_one_mode_line_on_stderr(monkeypatch, clock, capsys):
    _install(monkeypatch, FakeGh(clock))

    _wait(clock)
    _wait(clock)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == ["pr-event-wait: waiting on gh event listen between polls"]


# Hard bound


def test_hung_gh_is_killed_at_the_window_end(monkeypatch, clock):
    _install(monkeypatch, FakeGh(clock, listen_hangs=True))

    outcome, elapsed = _timed_wait(clock, 10)

    assert outcome == "fallback"
    assert elapsed == pytest.approx(10.0)
    assert clock.sleeps == []


def test_three_hangs_in_a_row_stop_listening(monkeypatch, clock, capsys):
    gh = _install(monkeypatch, FakeGh(clock, listen_hangs=True))

    for _ in range(4):
        _wait(clock, 10)

    assert len(gh.listen_calls()) == 3
    assert pr_events.listen_available() is False
    assert "3 listen failures in a row" in capsys.readouterr().err


@pytest.mark.parametrize("seconds", [0.5, 1, 2])
def test_window_too_short_to_listen_sleeps_without_spawning_gh(monkeypatch, clock, seconds):
    gh = _install(monkeypatch, FakeGh(clock))

    assert _wait(clock, seconds) == "fallback"
    assert clock.sleeps == [seconds]
    assert gh.calls == []


# Fallback path


def test_waitlist_403_sleeps_rest_of_window_and_disables_listening(monkeypatch, clock, capsys):
    gh = _install(
        monkeypatch, FakeGh(clock, listen_rc=1, listen_stderr=WAITLIST_STDERR, listen_takes=1.0)
    )

    first = _wait(clock, 30)
    second = _wait(clock, 30)

    assert (first, second) == ("fallback", "fallback")
    assert clock.sleeps == [pytest.approx(29.0), 30]
    assert len(gh.listen_calls()) == 1
    err = capsys.readouterr().err
    assert "pr-event-wait: sleeping between polls for the rest of this run: exit 1:" in err
    assert "not enabled for this account" in err


def test_unknown_event_command_disables_listening(monkeypatch, clock):
    gh = _install(monkeypatch, FakeGh(clock, listen_rc=1, listen_stderr=UNKNOWN_COMMAND_STDERR))

    _wait(clock, 30)
    _wait(clock, 30)

    assert len(gh.listen_calls()) == 1
    assert pr_events.listen_available() is False


@pytest.mark.parametrize("stderr", [LIMIT_STDERR, RATE_LIMIT_STDERR, "HTTP 404: Not Found\n"])
def test_other_failure_falls_back_for_this_call_only(monkeypatch, clock, capsys, stderr):
    gh = _install(monkeypatch, FakeGh(clock, listen_rc=1, listen_stderr=stderr, listen_takes=2.0))

    assert _wait(clock, 30) == "fallback"
    assert clock.sleeps == [pytest.approx(28.0)]
    gh.set_listen_result(0)
    assert _wait(clock, 30) == "event"
    assert len(gh.listen_calls()) == 2
    assert "gh event listen failed, sleeping this window: exit 1:" in capsys.readouterr().err


def test_a_success_resets_the_failure_count(monkeypatch, clock):
    gh = _install(monkeypatch, FakeGh(clock, listen_rc=1, listen_stderr=LIMIT_STDERR))

    _wait(clock)
    _wait(clock)
    gh.set_listen_result(0)
    _wait(clock)
    gh.set_listen_result(1, LIMIT_STDERR)
    _wait(clock)
    _wait(clock)

    assert pr_events.listen_available() is True
    assert len(gh.listen_calls()) == 5


def test_three_transient_failures_in_a_row_stop_listening(monkeypatch, clock):
    gh = _install(monkeypatch, FakeGh(clock, listen_rc=1, listen_stderr=LIMIT_STDERR))

    for _ in range(5):
        assert _wait(clock) == "fallback"

    assert len(gh.listen_calls()) == 3


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"version": "gh version 2.104.0 (2026-11-12)\n"}, "gh 2.104.0 is older than 2.105.0"),
        ({"version": "gh version 1.99.9\n"}, "gh 1.99.9 is older than 2.105.0"),
        ({"version": "not a version\n"}, "could not read the gh version"),
        ({"version_rc": 1}, "could not read the gh version"),
        ({"version_raises": FileNotFoundError("gh")}, "could not run gh: gh"),
        (
            {"version_raises": subprocess.TimeoutExpired(["gh"], 10)},
            "gh --version timed out",
        ),
    ],
)
def test_unusable_gh_sleeps_without_listening(monkeypatch, clock, capsys, kwargs, reason):
    gh = _install(monkeypatch, FakeGh(clock, **kwargs))

    assert _wait(clock, 30) == "fallback"
    assert sum(clock.sleeps) == pytest.approx(30)
    assert gh.listen_calls() == []
    assert capsys.readouterr().err.strip() == (
        f"pr-event-wait: sleeping between polls for the rest of this run: {reason}"
    )


def test_listen_binary_vanishing_disables_listening(monkeypatch, clock):
    _install(monkeypatch, FakeGh(clock, listen_raises=FileNotFoundError("gh")))

    assert _wait(clock, 30) == "fallback"
    assert clock.sleeps == [30]
    assert pr_events.listen_available() is False


def test_non_github_com_host_sleeps(monkeypatch, clock, capsys):
    monkeypatch.setenv("GH_HOST", "ghe.example.com")
    gh = _install(monkeypatch, FakeGh(clock))

    assert _wait(clock, 30) == "fallback"
    assert gh.calls == []
    assert "GH_HOST is ghe.example.com" in capsys.readouterr().err


def test_off_switch_sleeps_silently_even_after_support_was_cached(monkeypatch, clock, capsys):
    gh = _install(monkeypatch, FakeGh(clock))
    assert _wait(clock, 30) == "event"
    capsys.readouterr()

    monkeypatch.setenv(pr_events.DISABLE_ENV, "0")

    assert _wait(clock, 30) == "fallback"
    assert clock.sleeps == [30]
    assert len(gh.listen_calls()) == 1
    assert capsys.readouterr().err == ""


def test_default_seams_use_time_module(monkeypatch):
    monkeypatch.setenv(pr_events.DISABLE_ENV, "0")
    slept: list[float] = []
    monkeypatch.setattr(pr_events.time, "sleep", slept.append)

    assert pr_events.wait_for_pr_event(URL, pr_events.CHECK_EVENTS, 10) == "fallback"
    assert slept == [pytest.approx(10)]


def test_pr_url_builds_github_com_resource():
    assert pr_events.pr_url("o", "r", 7) == URL
