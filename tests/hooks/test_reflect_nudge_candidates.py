"""Workaround candidate count on the friction nudge.

The count rides only on a friction nudge that already fires. It never fires a
nudge, and it never changes the score, the tier, the markers, or how often the
nudge shows. Each test runs the hook on a transcript and checks its output.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.hooks.friction_nudge_support import (
    THRESHOLD_ENV,
    friction_records,
    run_env,
    write_transcript,
)
from tests.hooks.reflect_nudge_support import nudge

fc = nudge.failure_classifier

STATE_DIR = "ai-agents-reflect-nudge"
SENTINEL = "SENTINEL-9b27e4-candidate-text"
# Different names and error lines: repeats of one failure fold into one candidate.
TOOLS = ("post_reply", "sync_labels", "render_page")
BASE_11 = (
    "reflect-trigger: this session shows friction (score 11, tier 1): "
    "4 permission denial(s), 1 Stop hook feedback message(s), and a longest "
    "error streak of 1. You can run /retrospective to review what went wrong."
)


def _bash(call_id: str, command: str, output: str, failed: bool) -> list[dict[str, Any]]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": call_id, "content": output}
    if failed:
        block["is_error"] = True
    use = {
        "type": "tool_use",
        "id": call_id,
        "name": "Bash",
        "input": {"command": command},
    }
    return [
        {"type": "assistant", "isSidechain": False, "message": {"content": [use]}},
        {"type": "user", "isSidechain": False, "message": {"content": [block]}},
    ]


def workaround(index: int = 0) -> list[dict[str, Any]]:
    """One failed call and the changed call that got past it."""
    tool = f"tools/{TOOLS[index]}.py"
    return [
        *_bash(
            f"w{index}a",
            f"{tool} --body-file {SENTINEL}-x.md",
            f"Exit code 2\nerror: {TOOLS[index]} rejected the body file {SENTINEL}",
            True,
        ),
        *_bash(f"w{index}b", f"{tool} --body-file {SENTINEL}-y.md", "posted", False),
    ]


def message(out: str) -> str:
    doc = json.loads(out)
    assert set(doc) == {"systemMessage"}
    return str(doc["systemMessage"])


def markers(state: Path) -> list[Path]:
    directory = state / STATE_DIR
    return sorted(directory.iterdir()) if directory.exists() else []


def base_message(records: list[Any]) -> str:
    return str(fc.build_friction_message(fc.compute_friction(records, 10), "reflect-trigger"))


class TestCountRidesOnAFiringNudge:
    def test_one_candidate_adds_an_integer_labeled_as_candidates(self, tmp_path: Path) -> None:
        records = [*friction_records(denials=4, feedback=1), *workaround()]
        code, out, _ = run_env(write_transcript(tmp_path / "t.jsonl", records), tmp_path / "s")
        text = message(out)
        assert code == 0
        assert text.startswith(base_message(records))
        tail = text[len(base_message(records)) :]
        assert re.fullmatch(r" Workaround candidates, not confirmed: 1\.", tail)

    def test_count_follows_the_number_of_candidates(self, tmp_path: Path) -> None:
        records = [*friction_records(denials=4, feedback=1), *workaround(0), *workaround(1)]
        _, out, _ = run_env(write_transcript(tmp_path / "t.jsonl", records), tmp_path / "s")
        assert message(out).endswith(" Workaround candidates, not confirmed: 2.")

    def test_no_candidates_keeps_the_message_byte_for_byte(self, tmp_path: Path) -> None:
        records = friction_records(denials=4, feedback=1)
        _, out, _ = run_env(write_transcript(tmp_path / "t.jsonl", records), tmp_path / "s")
        assert message(out) == BASE_11
        assert out == json.dumps({"systemMessage": BASE_11}) + "\n"


class TestCountChangesNothingElse:
    def test_candidates_below_the_threshold_fire_no_nudge(self, tmp_path: Path) -> None:
        records = [*workaround(0), *workaround(1), *workaround(2)]
        state = tmp_path / "s"
        code, out, err = run_env(write_transcript(tmp_path / "t.jsonl", records), state)
        assert (code, out) == (0, "")
        assert "silent" in err and "candidate" not in err
        assert markers(state) == []

    def test_score_tier_and_marker_body_ignore_candidates(self, tmp_path: Path) -> None:
        records = [*friction_records(denials=4, feedback=1), *workaround()]
        state = tmp_path / "s"
        _, _, err = run_env(write_transcript(tmp_path / "t.jsonl", records), state)
        friction = fc.compute_friction(records, 10)
        assert f"friction score {friction.score} tier {friction.tier}" in err
        (marker,) = markers(state)
        body = json.loads(marker.read_text(encoding="utf-8"))
        assert set(body) == {"v", "score", "tier", "denials", "stop_feedback", "streak"}

    def test_a_repeat_stop_in_the_same_tier_stays_silent(self, tmp_path: Path) -> None:
        state = tmp_path / "s"
        first = [*friction_records(denials=4, feedback=1), *workaround(0)]
        run_env(write_transcript(tmp_path / "t.jsonl", first), state)
        more = [*first, *workaround(1)]
        code, out, err = run_env(write_transcript(tmp_path / "t.jsonl", more), state)
        assert (code, out) == (0, "")
        assert "already nudged" in err

    @pytest.mark.parametrize("raw", ["0", "off"])
    def test_opt_out_still_silences_everything(self, raw: str, tmp_path: Path) -> None:
        records = [*friction_records(denials=4, feedback=1), *workaround()]
        transcript = write_transcript(tmp_path / "t.jsonl", records)
        assert run_env(transcript, tmp_path / "s", {THRESHOLD_ENV: raw}) == (0, "", "")


class TestCountFailsOpen:
    def test_a_raising_candidate_finder_keeps_the_plain_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_a: Any, **_k: Any) -> Any:
            raise RuntimeError("finder broke")

        monkeypatch.setattr(sys.modules[fc.__name__ + ".friction"], "workaround_candidates", boom)
        records = [*friction_records(denials=4, feedback=1), *workaround()]
        code, out, _ = run_env(write_transcript(tmp_path / "t.jsonl", records), tmp_path / "s")
        assert code == 0
        assert message(out) == base_message(records)

    def test_a_partial_event_budget_prints_no_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        records = [*friction_records(denials=4, feedback=1), *workaround()]
        monkeypatch.setattr(nudge, "MAX_FRICTION_RECORDS", len(records) - 2)
        code, out, err = run_env(write_transcript(tmp_path / "t.jsonl", records), tmp_path / "s")
        assert (code, out) == (0, "")
        assert "friction skipped: events budget" in err and "candidate" not in err


class TestMessageContract:
    def test_no_transcript_text_reaches_any_output_or_marker(self, tmp_path: Path) -> None:
        records = [*friction_records(denials=4, feedback=1), *workaround(0), *workaround(1)]
        transcript = write_transcript(tmp_path / "t.jsonl", records)
        assert transcript.read_text(encoding="utf-8").count(SENTINEL) >= 6
        state = tmp_path / "s"
        _, out, err = run_env(transcript, state)
        assert "candidates" in message(out)
        assert SENTINEL not in out + err
        assert "post_reply" not in out + err
        assert all(SENTINEL not in m.read_text(encoding="utf-8") for m in markers(state))

    def test_template_is_fixed_and_names_only_the_retrospective_skill(self, tmp_path: Path) -> None:
        shapes = []
        for name, count in (("a", 1), ("b", 3)):
            records = [*friction_records(denials=4, feedback=1)]
            for index in range(count):
                records += workaround(index)
            _, out, _ = run_env(
                write_transcript(tmp_path / f"{name}.jsonl", records), tmp_path / name
            )
            shapes.append(re.sub(r"\d+", "N", message(out)))
        assert shapes[0] == shapes[1]
        assert re.findall(r"/[a-z-]+", shapes[0]) == ["/retrospective"]

    def test_message_addresses_the_user_and_gives_the_agent_no_instruction(
        self, tmp_path: Path
    ) -> None:
        records = [*friction_records(denials=4, feedback=1), *workaround()]
        _, out, _ = run_env(write_transcript(tmp_path / "t.jsonl", records), tmp_path / "s")
        text = message(out)
        assert text.startswith("reflect-trigger: ")
        assert not re.search(r"\b(you must|do not|don't|claude|assistant|agent)\b", text, re.I)
        assert "decision" not in out and "block" not in out
