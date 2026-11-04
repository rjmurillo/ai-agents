"""AC-05 and AC-06 across every fail-open path, plus the input limits.

REQ-048 TASK-004. Each scenario must exit 0 and never write a ``decision`` key.
The limit tests assert each cap fails open with its documented stderr status.
"""

from __future__ import annotations

import io
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.hooks.friction_nudge_support import THRESHOLD_ENV, friction_records
from tests.hooks.reflect_nudge_safety_support import (
    correction_records,
    isolated_home,  # noqa: F401  (pytest fixture)
    write_transcript,
)
from tests.hooks.reflect_nudge_support import human, nudge

pytestmark = pytest.mark.usefixtures("isolated_home")


@dataclass
class Scenario:
    """Inputs for one ``nudge.run`` call, plus whether a nudge is expected."""

    stdin: str
    env: dict[str, str] = field(default_factory=dict)
    state_root: Path | None = None
    nudges: bool = False


def _payload(transcript: Path | str | None, session_id: object = "sess-1") -> str:
    body: dict[str, object] = {"session_id": session_id}
    if transcript is not None:
        body["transcript_path"] = str(transcript)
    return json.dumps(body)


def _both(tmp_path: Path) -> Path:
    return write_transcript(tmp_path / "t.jsonl", [*correction_records(), *friction_records(4, 1)])


def _no_payload(tmp: Path) -> Scenario:
    return Scenario("", state_root=tmp / "s")


def _bad_session_id(tmp: Path) -> Scenario:
    return Scenario(_payload(_both(tmp), "../escape"), state_root=tmp / "s")


def _missing_transcript(tmp: Path) -> Scenario:
    return Scenario(_payload(tmp / "absent.jsonl"), state_root=tmp / "s")


def _unreadable_transcript(tmp: Path) -> Scenario:
    path = _both(tmp)
    path.chmod(0)
    return Scenario(_payload(path), state_root=tmp / "s")


def _oversized_stdin(tmp: Path) -> Scenario:
    padding = "x" * (nudge.MAX_STDIN_BYTES + 1)
    return Scenario(json.dumps({"session_id": "s", "pad": padding}), state_root=tmp / "s")


def _budget_stop(tmp: Path) -> Scenario:
    return Scenario(_payload(_both(tmp)), state_root=tmp / "s", nudges=True)


def _classifier_missing(tmp: Path) -> Scenario:
    return Scenario(_payload(_both(tmp)), state_root=tmp / "s", nudges=True)


def _off(tmp: Path) -> Scenario:
    return Scenario(_payload(_both(tmp)), {THRESHOLD_ENV: "off"}, tmp / "s")


def _inside_repository(tmp: Path) -> Scenario:
    (tmp / "repo" / ".git").mkdir(parents=True)
    return Scenario(_payload(_both(tmp)), state_root=tmp / "repo" / "state")


def _home_unset(tmp: Path) -> Scenario:
    return Scenario(_payload(_both(tmp)), {"XDG_STATE_HOME": str(tmp / "xdg")})


def _malformed_transcript(tmp: Path) -> Scenario:
    path = tmp / "bad.jsonl"
    path.write_bytes(b"\xff\xfe{not json\n[[[[\n" + b"\x00" * 64 + b"\n")
    return Scenario(_payload(path), state_root=tmp / "s")


def _correction_nudge(tmp: Path) -> Scenario:
    path = write_transcript(tmp / "c.jsonl", correction_records())
    return Scenario(_payload(path), state_root=tmp / "s", nudges=True)


def _friction_nudge(tmp: Path) -> Scenario:
    path = write_transcript(tmp / "f.jsonl", friction_records(4, 1))
    return Scenario(_payload(path), state_root=tmp / "s", nudges=True)


SCENARIOS: dict[str, Callable[[Path], Scenario]] = {
    "no payload": _no_payload,
    "bad session id": _bad_session_id,
    "missing transcript": _missing_transcript,
    "unreadable transcript": _unreadable_transcript,
    "oversized stdin": _oversized_stdin,
    "budget stop": _budget_stop,
    "classifier missing": _classifier_missing,
    "off": _off,
    "state root in repository": _inside_repository,
    "home unset": _home_unset,
    "malformed transcript": _malformed_transcript,
    "correction nudge": _correction_nudge,
    "friction nudge": _friction_nudge,
}
NEEDS_POSIX_USER = {"unreadable transcript", "home unset"}


def _execute(
    name: str, scenario: Scenario, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, str, str]:
    kwargs: dict[str, object] = {}
    if name == "budget stop":
        ticks = iter([0.0, 0.0, 99.0, 99.0, 99.0])
        kwargs["clock"] = lambda: next(ticks)
    if name == "classifier missing":
        monkeypatch.setattr(nudge, "failure_classifier", None)
    out, err = io.StringIO(), io.StringIO()
    code = nudge.run(
        io.StringIO(scenario.stdin),
        out,
        err,
        scenario.env,
        state_root=scenario.state_root,
        **kwargs,
    )
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_path_exits_zero_and_never_emits_a_decision(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if name in NEEDS_POSIX_USER and os.name != "posix":
        pytest.skip("POSIX-only scenario")
    if name == "unreadable transcript" and hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root reads mode 0 files")
    scenario = SCENARIOS[name](tmp_path)
    code, out, err = _execute(name, scenario, monkeypatch)
    assert code == 0
    assert "decision" not in out
    assert ("systemMessage" in out) is scenario.nudges
    if out:
        document = json.loads(out)
        assert set(document) == {"systemMessage"}
    assert err.count("\n") == (0 if name == "off" else 1)


class TestFailOpenStatus:
    """Each refusal says why on one stderr line; the table above checks exit and shape."""

    @pytest.mark.parametrize(
        ("name", "fragment"),
        [
            ("no payload", "stop payload missing or malformed"),
            ("bad session id", "session_id missing or invalid"),
            ("missing transcript", "transcript_path missing, unreadable, or too large"),
            ("oversized stdin", "stop payload missing or malformed"),
            ("malformed transcript", "silent"),
        ],
    )
    def test_documented_status(
        self, name: str, fragment: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, out, err = _execute(name, SCENARIOS[name](tmp_path), monkeypatch)
        assert out == ""
        assert fragment in err


class TestInputLimits:
    def test_stdin_at_the_cap_is_read_and_one_byte_over_is_rejected(self) -> None:
        cap = nudge.MAX_STDIN_BYTES
        body = '{"k": "' + "x" * (cap - len('{"k": ""}')) + '"}'
        assert len(body.encode()) == cap
        assert nudge.read_payload(io.StringIO(body)) == {"k": "x" * (cap - len('{"k": ""}'))}
        assert nudge.read_payload(io.StringIO(body + " ")) is None

    def test_transcript_at_the_cap_is_read_and_one_byte_over_fails_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = write_transcript(tmp_path / "t.jsonl", correction_records())
        size = path.stat().st_size
        monkeypatch.setattr(nudge, "MAX_TRANSCRIPT_BYTES", size)
        out, err = io.StringIO(), io.StringIO()
        nudge.run(io.StringIO(_payload(path)), out, err, {}, state_root=tmp_path / "s")
        assert "systemMessage" in out.getvalue()
        monkeypatch.setattr(nudge, "MAX_TRANSCRIPT_BYTES", size - 1)
        out, err = io.StringIO(), io.StringIO()
        code = nudge.run(io.StringIO(_payload(path)), out, err, {}, state_root=tmp_path / "s2")
        assert (code, out.getvalue()) == (0, "")
        assert "too large" in err.getvalue()

    def test_over_long_line_is_skipped_and_its_correction_is_not_counted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "MAX_LINE_CHARS", 400)
        path = tmp_path / "t.jsonl"
        path.write_text(json.dumps(human("no, " + "x" * 2000)) + "\n", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        code = nudge.run(io.StringIO(_payload(path)), out, err, {}, state_root=tmp_path / "s")
        assert (code, out.getvalue()) == (0, "")
        assert "1 skipped lines" in err.getvalue() and "silent" in err.getvalue()
        assert not (tmp_path / "s").exists()

    def test_record_cap_skips_friction_and_emits_no_nudge(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "MAX_FRICTION_RECORDS", 5)
        path = write_transcript(tmp_path / "t.jsonl", friction_records(4, 1))
        out, err = io.StringIO(), io.StringIO()
        code = nudge.run(io.StringIO(_payload(path)), out, err, {}, state_root=tmp_path / "s")
        assert (code, out.getvalue()) == (0, "")
        assert "records over event cap" in err.getvalue()
        assert "friction skipped: events budget" in err.getvalue()
