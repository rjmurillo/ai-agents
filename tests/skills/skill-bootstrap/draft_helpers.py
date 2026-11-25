"""Shared fixtures for the ADR draft tests: a scan candidate, a scan file and a draft reader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _cand(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "c-1234567",
        "kind": "commit",
        "title": "Replace eo-inference with the per-copy engine",
        "reason": "the per-copy engine resolves each copy once, so inference stops repeating work",
        "excerpt": (
            "Replace eo-inference with the per-copy engine\n\nThe old engine re-read every copy."
        ),
        "date": "2026-11-02",
        "source": {
            "sha": "1234567" + "0" * 33,
            "url": "https://github.com/objectionary/eo/commit/9d90b52",
            "pr_number": None,
            "pr_url": None,
        },
        "signals": [],
    }
    return {**base, **over}


def _scan_file(tmp_path: Path, repo: Path, *candidates: dict[str, Any]) -> str:
    path = tmp_path / f"scan-{len(list(tmp_path.glob('scan-*.json')))}.json"
    path.write_text(
        json.dumps({"repo": str(repo), "candidates": list(candidates)}), encoding="utf-8"
    )
    return str(path)


def _text(result: dict[str, Any]) -> str:
    return Path(result["path"]).read_text(encoding="utf-8")
