"""Tests for scripts/eval/eval_third_party_gap_replay.py.

The model and git seams are injected callables: no network, no repository.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.eval._third_party_gap_test_support import eval_path, load_script


def _load() -> Any:
    return load_script("eval_third_party_gap_replay")


replay = _load()

with eval_path():
    import _third_party_gap_report as report

BASE, HEAD, FIX = "a" * 40, "b" * 40, "c" * 40
PATCH = "+++ b/scripts/tool.py\n@@ -1,0 +1,2 @@\n+line one\n+line two\n"
CAUGHT = "FINDING: scripts/tool.py:2 | edge-case | drops it\nVERDICT: WARN"


def git(args: tuple[str, ...]) -> str | None:
    if args[0] == "show" and ":" in args[1]:
        return "---\nname: x\n---\nPROMPT"
    if args[:3] == ("diff", "--name-only", "-z"):
        return "scripts/tool.py\0"
    if args[0] == "diff":
        return PATCH
    raise AssertionError(f"unexpected git call {args}")


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    revs = [
        {
            "id": f"TG00{i}",
            "pr": i,
            "title": f"pr {i}",
            "base": BASE,
            "head": HEAD,
            "split": "heldout",
            "defects": [
                {
                    "thread": f"T000{i}",
                    "bot": "devin",
                    "path": "scripts/tool.py",
                    "line": 2,
                    "fix": FIX,
                    "theme": "fail-open",
                    "context": "diff-local",
                }
            ],
        }
        for i in (1, 2)
    ]
    path = tmp_path / "corpus.json"
    path.write_text(
        json.dumps({"schema_version": 1, "selection": {"rule": "r"}, "revisions": revs}),
        encoding="utf-8",
    )
    return path


def args(corpus: Path, *extra: str) -> list[str]:
    return ["--corpus", str(corpus), "--prompt-ref", "main", *extra]


class FakeCaller:
    """Model seam: returns one fixed answer and records every prompt it was sent."""

    def __init__(self, text: str = CAUGHT) -> None:
        self.text = text
        self.calls: list[str] = []

    def __call__(self, system: str, user: str) -> tuple[str, dict[str, Any]]:
        self.calls.append(user)
        return self.text, {"output_tokens": 7, "finish_reason": "stop"}


def caller(text: str = CAUGHT) -> FakeCaller:
    return FakeCaller(text)


class TestMain:
    def test_caught_defects_are_counted(
        self, corpus: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = replay.main(args(corpus), caller(), git)

        result = json.loads(capsys.readouterr().out)["result"]
        assert code == 0
        assert result["all"]["all"]["caught"]["hits"] == 2
        assert result["reviews"] == {
            "n": 2,
            "no_findings": 0,
            "mean_findings": 1.0,
            "cut_at_ceiling": 0,
            "output_tokens": 14,
        }

    def test_every_call_failing_exits_3(self, corpus: Path) -> None:
        def failing(system: str, user: str) -> tuple[str, dict[str, Any]]:
            raise RuntimeError("boom")

        assert replay.main(args(corpus), failing, git) == 3

    def test_checkpoint_resume_skips_finished_and_reruns_errored_rows(
        self, corpus: Path, tmp_path: Path
    ) -> None:
        checkpoint = tmp_path / "rows.jsonl"
        argv = args(corpus, "--checkpoint", str(checkpoint))
        assert replay.main(argv, caller(), git) == 0
        first, second = checkpoint.read_text(encoding="utf-8").splitlines()
        errored = json.loads(second) | {"error": "429"}
        checkpoint.write_text(
            f"{first}\n{json.dumps(errored)}\n" + '{"revision": "TG00', encoding="utf-8"
        )
        fake = caller()

        code = replay.main(argv, fake, git)

        assert code == 0
        assert len(fake.calls) == 1
        reloaded = replay.load_checkpoint(checkpoint)
        assert sorted(r["revision"] for r in reloaded) == ["TG001", "TG002"]

    def test_a_resume_of_a_subset_ignores_rows_outside_it(
        self, corpus: Path, tmp_path: Path
    ) -> None:
        checkpoint = tmp_path / "rows.jsonl"
        assert replay.main(args(corpus, "--checkpoint", str(checkpoint)), caller(), git) == 0
        fake = caller()

        code = replay.main(
            args(corpus, "--checkpoint", str(checkpoint), "--revisions", "TG001"), fake, git
        )

        assert code == 0
        assert fake.calls == []

    def test_checkpoint_answers_for_a_changed_prompt_are_refused(
        self, corpus: Path, tmp_path: Path
    ) -> None:
        checkpoint = tmp_path / "rows.jsonl"
        argv = args(corpus, "--checkpoint", str(checkpoint))
        assert replay.main(argv, caller(), git) == 0

        def edited_prompt(argv_: tuple[str, ...]) -> str | None:
            out = git(argv_)
            return out.replace("PROMPT", "EDITED PROMPT") if out else out

        fake = caller()

        code = replay.main(argv, fake, edited_prompt)

        assert code == 2
        assert fake.calls == []

    def test_checkpoint_from_another_arm_is_refused_before_any_call(
        self, corpus: Path, tmp_path: Path
    ) -> None:
        checkpoint = tmp_path / "rows.jsonl"
        argv = args(corpus, "--checkpoint", str(checkpoint))
        stamp = replay.run_stamp(replay.parse_args(argv)) | {"prompt_ref": "baseline"}
        checkpoint.write_text(
            json.dumps({"revision": "TG001", "trial": 0, "raw": CAUGHT, **stamp}) + "\n",
            encoding="utf-8",
        )
        fake = caller()

        code = replay.main(argv, fake, git)

        assert code == 2
        assert fake.calls == []

    def test_unstamped_checkpoint_rows_are_refused(self, corpus: Path, tmp_path: Path) -> None:
        checkpoint = tmp_path / "rows.jsonl"
        checkpoint.write_text(
            json.dumps({"revision": "TG001", "trial": 0, "raw": CAUGHT}) + "\n", encoding="utf-8"
        )
        fake = caller()

        assert replay.main(args(corpus, "--checkpoint", str(checkpoint)), fake, git) == 2
        assert fake.calls == []

    def test_duplicate_checkpoint_rows_count_once(
        self, corpus: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        checkpoint = tmp_path / "rows.jsonl"
        row = json.dumps({"revision": "TG001", "trial": 0, "raw": CAUGHT})
        checkpoint.write_text(f"{row}\n{row}\n", encoding="utf-8")

        code = replay.main(
            args(corpus, "--checkpoint", str(checkpoint), "--rescore", "--revisions", "TG001"),
            caller(),
            git,
        )

        result = json.loads(capsys.readouterr().out)["result"]
        assert code == 0
        assert result["all"]["all"]["caught"]["n"] == 1

    def test_rescore_without_checkpoint_exits_2(self, corpus: Path) -> None:
        assert replay.main(args(corpus, "--rescore"), caller(), git) == 2

    def test_unknown_revision_exits_2(self, corpus: Path) -> None:
        assert replay.main(args(corpus, "--revisions", "TG999"), caller(), git) == 2

    def test_dry_run_counts_calls_without_calling(
        self, corpus: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake = caller()

        code = replay.main(args(corpus, "--dry-run", "--trials", "2"), fake, git)

        assert code == 0
        assert json.loads(capsys.readouterr().out)["planned_calls"] == 4
        assert fake.calls == []


class TestOutputTokens:
    def test_reads_both_metadata_shapes(self) -> None:
        assert replay.output_tokens({"output_tokens": 3}) == 3
        assert replay.output_tokens({"usage": {"completion_tokens": 5}}) == 5
        assert replay.output_tokens({}) == 0


@pytest.fixture(autouse=True)
def _reset_rate_limit_breaker() -> Iterator[None]:
    replay.RATE_LIMIT_EXHAUSTED.clear()
    yield
    replay.RATE_LIMIT_EXHAUSTED.clear()


class TestRateLimitBackoff:
    def test_retries_429_then_returns(self) -> None:
        answers: Iterator[str | Exception] = iter([RuntimeError("HTTP 429: rate_limit"), "ok"])
        waits: list[float] = []

        def send() -> str:
            item = next(answers)
            if isinstance(item, Exception):
                raise item
            return item

        assert replay.call_with_rate_limit_backoff(send, waits.append) == "ok"
        assert waits == [replay.RATE_LIMIT_WAITS_SECONDS[0]]

    def test_timeout_is_not_retried(self) -> None:
        waits: list[float] = []
        sent: list[int] = []

        def send() -> str:
            sent.append(1)
            raise RuntimeError("request timed out")

        with pytest.raises(RuntimeError, match="timed out"):
            replay.call_with_rate_limit_backoff(send, waits.append)
        assert (sent, waits) == ([1], [])

    def test_persistent_429_raises_after_the_schedule_and_trips_the_breaker(self) -> None:
        waits: list[float] = []

        def send() -> str:
            raise RuntimeError("OpenAI API returned HTTP 429: error=rate_limit")

        with pytest.raises(RuntimeError, match="HTTP 429"):
            replay.call_with_rate_limit_backoff(send, waits.append)
        assert waits == list(replay.RATE_LIMIT_WAITS_SECONDS)
        assert replay.RATE_LIMIT_EXHAUSTED.is_set()

    def test_after_the_breaker_trips_a_job_fails_without_calling(self) -> None:
        replay.RATE_LIMIT_EXHAUSTED.set()
        sent: list[int] = []

        def send() -> str:
            sent.append(1)
            return "ok"

        with pytest.raises(RuntimeError, match="exhausted"):
            replay.call_with_rate_limit_backoff(send, lambda _w: None)
        assert sent == []

    def test_digits_429_inside_other_text_are_not_retried(self) -> None:
        waits: list[float] = []

        def send() -> str:
            raise RuntimeError("EVAL_HTTP_TIMEOUT_SECONDS must be in (0, 1800], got 4290")

        with pytest.raises(RuntimeError, match="4290"):
            replay.call_with_rate_limit_backoff(send, waits.append)
        assert waits == []


class TestMcNemar:
    def test_no_discordant_pairs_is_p_one(self) -> None:
        assert report.mcnemar_exact_p(0, 0) == 1.0

    def test_balanced_discordance_is_p_one(self) -> None:
        assert report.mcnemar_exact_p(4, 4) == 1.0

    def test_known_value_for_zero_versus_six(self) -> None:
        # Two-sided exact binomial for 0 of 6 at p = 0.5 is 2 / 64.
        assert report.mcnemar_exact_p(0, 6) == 2 / 64

    def test_is_symmetric(self) -> None:
        assert report.mcnemar_exact_p(2, 9) == report.mcnemar_exact_p(9, 2)


class TestCompare:
    def test_pairs_only_jobs_both_arms_finished(
        self, corpus: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        miss = "NO FINDINGS\nVERDICT: PASS"
        base = tmp_path / "base.jsonl"
        treat = tmp_path / "treat.jsonl"
        base.write_text(
            json.dumps({"revision": "TG001", "trial": 0, "raw": miss})
            + "\n"
            + json.dumps({"revision": "TG002", "trial": 0, "raw": miss})
            + "\n",
            encoding="utf-8",
        )
        treat.write_text(
            json.dumps({"revision": "TG001", "trial": 0, "raw": CAUGHT}) + "\n", encoding="utf-8"
        )

        code = replay.main(
            args(corpus, "--checkpoint", str(treat), "--compare", str(base)), caller(), git
        )

        paired = json.loads(capsys.readouterr().out)["result"]["paired"]
        assert code == 0
        assert paired["all"]["n"] == 1
        assert paired["all"]["treatment_only"] == 1
        assert paired["context:diff-local"]["treatment_only"] == 1

    def test_compare_without_checkpoint_exits_2(self, corpus: Path, tmp_path: Path) -> None:
        base = tmp_path / "base.jsonl"
        base.write_text("", encoding="utf-8")

        assert replay.main(args(corpus, "--compare", str(base)), caller(), git) == 2


class TestPartialFailure:
    def test_one_failed_call_exits_3_and_counts_the_error(
        self, corpus: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        failures = iter([True, False])

        def flaky(system: str, user: str) -> tuple[str, dict[str, Any]]:
            if next(failures):
                raise RuntimeError("HTTP 500")
            return CAUGHT, {"output_tokens": 1}

        code = replay.main(args(corpus, "--workers", "1"), flaky, git)

        captured = capsys.readouterr()
        assert code == 3
        assert json.loads(captured.out)["result"]["errors"] == 1
        assert "1 of 2 call(s) failed" in captured.err


def test_git_run_returns_none_when_git_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def stalled(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired("git", 60)

    monkeypatch.setattr(subprocess, "run", stalled)

    assert replay.git_run(("show", "HEAD:x")) is None


class TestOfflineModesNeedTheirFiles:
    @pytest.mark.parametrize("mode", ["--rescore", "--compare"])
    def test_a_missing_checkpoint_exits_2(self, corpus: Path, tmp_path: Path, mode: str) -> None:
        present = tmp_path / "present.jsonl"
        present.write_text("", encoding="utf-8")
        missing = str(tmp_path / "missing.jsonl")
        extra = ["--rescore"] if mode == "--rescore" else ["--compare", str(present)]

        code = replay.main(args(corpus, "--checkpoint", missing, *extra), caller(), git)

        assert code == 2

    def test_a_missing_compare_baseline_exits_2(self, corpus: Path, tmp_path: Path) -> None:
        present = tmp_path / "present.jsonl"
        present.write_text("", encoding="utf-8")
        argv = args(corpus, "--checkpoint", str(present), "--compare", str(tmp_path / "nope"))

        assert replay.main(argv, caller(), git) == 2


class TestFinishReason:
    @pytest.mark.parametrize(
        ("metadata", "expected"),
        [
            ({"stop_reason": "max_tokens"}, "length"),
            (
                {"stop_reason": "model_context_window_exceeded", "termination": "token_limit"},
                "length",
            ),
            ({"stop_reason": "end_turn"}, None),
            ({"finish_reason": "stop", "stop_reason": "max_tokens"}, "stop"),
            ({}, None),
        ],
    )
    def test_maps_the_default_provider_stop_reason(
        self, metadata: dict[str, object], expected: str | None
    ) -> None:
        assert replay.finish_reason(metadata) == expected

    def test_the_caller_reports_a_max_tokens_stop_as_length(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_call_api(*_a: object, metadata: dict[str, object], **_k: object) -> str:
            metadata.update(stop_reason="max_tokens", output_tokens=7)
            return "answer"

        monkeypatch.setattr(replay, "call_api", fake_call_api)
        monkeypatch.setattr(replay, "load_api_key_for_selected_provider", lambda: "k")
        usage = {"calls": 0, "output_tokens": 0}

        text, meta = replay.make_caller("m", usage)("system", "user")

        assert (text, meta["finish_reason"]) == ("answer", "length")
