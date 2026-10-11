"""Typed, validated entries of a duration snapshot.

History comes back from the Actions cache, so every field is checked on load.
A wrong type raises ``ValueError``, which ``load_history`` turns into an empty
history and a note in the report instead of a crash.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from typing import TypedDict


class ModuleEntry(TypedDict):
    seconds: float
    tests: int
    ids: str


class PartitionEntry(TypedDict):
    tests: int
    wall_seconds: float


def ids_digest(nodeids: Iterable[str]) -> str:
    """A short, order-independent identity for the set of tests a module ran.

    Two runs compare only when this matches, so replacing one test with another
    of the same count does not borrow the old test's baseline.
    """
    joined = "\n".join(sorted(nodeids)).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()[:16]


def _finite(raw: dict[str, object], key: str) -> float | int:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} is {type(value).__name__}, not a number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{key} is {value}, not a finite non-negative number")
    return value


def _seconds(raw: dict[str, object], key: str) -> float:
    return float(_finite(raw, key))


def _count(raw: dict[str, object], key: str) -> int:
    value = _finite(raw, key)
    if not isinstance(value, int):
        raise ValueError(f"{key} is {value}, not an integer")
    return value


def parse_module(raw: object) -> ModuleEntry:
    """Validate one module entry read from history."""
    if not isinstance(raw, dict) or not isinstance(raw.get("ids"), str):
        raise ValueError(f"module entry {raw!r} lacks a string ids field")
    return {"seconds": _seconds(raw, "seconds"), "tests": _count(raw, "tests"),
            "ids": raw["ids"]}


def parse_partition(raw: object) -> PartitionEntry:
    """Validate one partition entry read from history."""
    if not isinstance(raw, dict):
        raise ValueError(f"partition entry {raw!r} is not an object")
    return {"tests": _count(raw, "tests"), "wall_seconds": _seconds(raw, "wall_seconds")}
