"""Shared helpers for the actionability arms tests (plan M1-T13 to M1-T15)."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "actionability_arms.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("actionability_arms", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


aa = _load_module()
sc = importlib.import_module("scripts.eval.actionability_score")
pm = importlib.import_module("scripts.eval.actionability_predict")
vm = importlib.import_module("scripts.eval.actionability_verdict")


def make_row(
    row_id: str,
    *,
    score: float = 0.5,
    in_band: bool = True,
    split: str = "heldout",
    label: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """A corpus row as `actionability_corpus.py sample` writes it.

    Each id gets its own `pr_number`, so the PR-clustered bootstrap treats rows as
    independent unless a test sets `pr_number` to group them.
    """
    row: dict[str, Any] = {
        "id": row_id,
        "pr_number": zlib.crc32(row_id.encode("utf-8")) % 1_000_000 + 1,
        "reviewer": "alice",
        "thread_position": 0,
        "path": "src/a.py",
        "body": f"body of {row_id}",
        "created_at": "2026-11-20T00:00:00Z",
        "thread_replies": [],
        "heuristic_score": score,
        "heuristic_reasons": [],
        "in_band": in_band,
        "split": split,
        "diff_hunk": "@@ -1 +1 @@",
        "label": label,
        "sampled_at": "2026-11-24T12:00:00+00:00",
    }
    row.update(overrides)
    return row


def make_prediction(
    row_id: str,
    *,
    is_actionable: bool | None = True,
    confidence: float | None = 0.9,
    status: str = "ok",
    **overrides: Any,
) -> dict[str, Any]:
    """A prediction record as `actionability_arms.py predict` writes it."""
    record: dict[str, Any] = {
        "id": row_id,
        "status": status,
        "is_actionable": is_actionable,
        "confidence": confidence,
        "reason": "because",
        "latency_s": 0.25,
        "provider": "fake",
        "model": "fake-model",
        "prompt_sha256": "p" * 64,
    }
    record.update(overrides)
    return record


def write_jsonl_file(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def read_jsonl_file(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()
    ]


API_KEY = "sk-test-SECRET-123456"
GOOD = '{"is_actionable": true, "confidence": 0.9, "reason": "names a change"}'


class FakeCallApi:
    """Stands in for `_anthropic_api.call_api`. Replies come from a callable or a fixed string."""

    def __init__(self, reply: str | Callable[[str], str] = GOOD) -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    def __call__(self, api_key: str, messages: list[dict[str, str]], **kwargs: Any) -> str:
        self.calls.append({"api_key": api_key, "messages": messages, **kwargs})
        content = messages[0]["content"]
        return self.reply(content) if callable(self.reply) else self.reply


def install_call_api(monkeypatch: pytest.MonkeyPatch, fake: FakeCallApi) -> FakeCallApi:
    monkeypatch.setattr(pm, "_load_call_api", lambda: fake)
    return fake


def write_corpus_file(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    return write_jsonl_file(tmp_path / "corpus.jsonl", rows)


def predict_argv(corpus: Path, out: Path, *extra: str, model: str = "fake-model") -> list[str]:
    return [
        "predict",
        "--corpus",
        str(corpus),
        "--split",
        "heldout",
        "--model",
        model,
        "--output",
        str(out),
        *extra,
    ]


def heldout_rows(count: int) -> list[dict[str, Any]]:
    return [make_row(f"H{i}") for i in range(count)]


def provider_argv(corpus: Path, out: Path, *extra: str) -> list[str]:
    """predict argv for the fake provider, which needs no Anthropic key."""
    return predict_argv(corpus, out, "--provider", "fake", *extra)


def ok_record(row_id: str, **overrides: Any) -> dict[str, Any]:
    """An ok prediction carrying the provenance the CLI writes for `--provider fake`."""
    record = make_prediction(
        row_id, provider="fake", model="fake-model", prompt_sha256=pm.load_prompt()[1]
    )
    record.update(overrides)
    return record


def failed_record(row_id: str, status: str) -> dict[str, Any]:
    return ok_record(row_id, status=status, is_actionable=None, confidence=None)


def row_id_of(message: str) -> str:
    """The `H<n>` id a FakeCallApi message was built for (make_row bodies name their id)."""
    match = re.search(r"body of (H\d+)", message)
    assert match is not None
    return match.group(1)


def token_of(message: str) -> str:
    match = re.search(r"Delimiter token: ([0-9a-f]{16})", message)
    assert match is not None
    return match.group(1)
