"""Shared writer for the duration split merge tests."""

from __future__ import annotations

import json
from pathlib import Path


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
