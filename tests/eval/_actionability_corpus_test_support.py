"""Shared helpers for the actionability corpus tests (plan M1-T7 to M1-T10)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "actionability_corpus.py"
FROZEN_NOW = "2026-11-24T12:00:00+00:00"
SHA40 = "a" * 40


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("actionability_corpus", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cc = _load_module()


def make_node(
    node_id: str,
    body: str,
    login: str = "alice",
    created_at: str = "2026-11-20T00:00:00Z",
) -> dict[str, Any]:
    return {
        "id": node_id,
        "body": body,
        "author": {"login": login},
        "createdAt": created_at,
        "path": "src/a.py",
    }


def make_thread(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {"isResolved": False, "isOutdated": False, "comments": {"nodes": list(nodes)}}


def make_pr(number: int, *threads: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": number,
        "author": {"login": "owner"},
        "reviewThreads": {"nodes": list(threads)},
    }


BAND_BODY = "Consider a helper here"
OUTSIDE_BODY = "Critical security vulnerability: injection"


def corpus_prs(band: int = 6, outside: int = 6) -> list[dict[str, Any]]:
    """Reviewers alice, bob, carol; band rows score 0.5, outside rows score far from it."""
    logins = ["alice", "bob", "carol"]
    threads = []
    for i in range(band):
        node = make_node(f"B{i}", f"{BAND_BODY} {i}", login=logins[i % 3])
        threads.append(make_thread(node))
    for i in range(outside):
        node = make_node(f"O{i}", f"{OUTSIDE_BODY} {i}", login=logins[i % 3])
        threads.append(make_thread(node))
    return [make_pr(1, *threads)]


def write_prs(path: Path, prs: Any) -> Path:
    path.write_text(json.dumps(prs), encoding="utf-8")
    return path


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()
    ]


def sample_args(prs: Path, out: Path, **overrides: Any) -> list[str]:
    opts: dict[str, Any] = {"band-count": 4, "outside-count": 4, "dev-count": 2}
    opts.update(overrides)
    argv = ["sample", "--prs", str(prs), "--output", str(out)]
    for key, value in opts.items():
        argv += [f"--{key}", str(value)]
    return argv


def corpus_row(row_id: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": row_id,
        "pr_number": 1,
        "reviewer": "alice",
        "thread_position": 0,
        "path": "src/a.py",
        "body": f"body {row_id}",
        "created_at": "2026-11-20T00:00:00Z",
        "thread_replies": [],
        "heuristic_score": 0.5,
        "heuristic_reasons": [],
        "in_band": True,
        "split": "heldout",
        "diff_hunk": None,
        "label": None,
        "sampled_at": FROZEN_NOW,
    }
    row.update(overrides)
    return row


def write_corpus(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


class FakeGraphql:
    """Records calls and answers from a table of node id to hunk (or None for a null node)."""

    def __init__(self, hunks: dict[str, str | None], fail_on: str | None = None) -> None:
        self.hunks = hunks
        self.fail_on = fail_on
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = variables or {}
        self.calls.append((query, variables))
        node_id = variables["id"]
        if node_id == self.fail_on:
            raise RuntimeError("GraphQL transport failed")
        hunk = self.hunks.get(node_id)
        if hunk is None:
            return {"node": None}
        return {"node": {"diffHunk": hunk}}
