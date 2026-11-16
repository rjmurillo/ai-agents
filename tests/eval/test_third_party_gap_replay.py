"""Tests for scripts/eval/eval_third_party_gap_replay.py.

The model and git seams are injected callables: no network, no repository.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))


def _load() -> Any:
    spec = importlib.util.spec_from_file_location(
        "eval_third_party_gap_replay", EVAL_DIR / "eval_third_party_gap_replay.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


replay = _load()

import _third_party_gap_report as report  # noqa: E402

BASE, HEAD, FIX = "a" * 40, "b" * 40, "c" * 40
PATCH = "+++ b/scripts/tool.py\n@@ -1,0 +1,2 @@\n+line one\n+line two\n"
CAUGHT = "FINDING: scripts/tool.py:2 | edge-case | drops it\nVERDICT: WARN"


def git(args: tuple[str, ...]) -> str | None:
    if args[0] == "show" and ":" in args[1]:
        return "---\nname: x\n---\nPROMPT"
    if args[:2] == ("diff", "--name-only"):
        return "scripts/tool.py\n"
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
        checkpoint.write_text(
            json.dumps({"revision": "TG001", "trial": 0, "raw": CAUGHT, "findings": 1})
            + "\n"
            + json.dumps({"revision": "TG002", "trial": 0, "error": "429"})
            + "\n"
            + '{"revision": "TG00',
            encoding="utf-8",
        )
        fake = caller()

        code = replay.main(args(corpus, "--checkpoint", str(checkpoint)), fake, git)

        assert code == 0
        assert len(fake.calls) == 1

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
