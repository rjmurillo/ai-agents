"""Relocation-evidence checks for ``validation_record.py`` (issue #6214).

Split out so the record validator stays under the repository file-size limit.
The shape checks are pure: they read the record fragment they are given and
return defect strings. The one exception is ``collect_tests``, which the CLI
passes in as a ``collector`` so the claimed test ids are checked against what
pytest really collects (issue #6506, review-gates-03).
"""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

RELOCATION = "relocation-no-semantic-change"
_RELOCATION_DIFF_LIMIT = 5
_COLLECT_TIMEOUT_SECONDS = 300

# A collector takes the moved_to module paths and returns the collected test
# ids, or raises CollectionError when collection cannot be trusted.
Collector = Callable[[Sequence[str]], list[str]]


class CollectionError(RuntimeError):
    """Real test collection failed, so the relocation claim cannot be verified."""


def collect_tests(paths: Sequence[str], repo_root: Path) -> list[str]:
    """Collect test ids from ``paths`` with a fixed pytest command in ``repo_root``.

    The validator never runs the record's own ``collect_command``: that string
    is agent-supplied, and executing it would let the record run arbitrary
    commands. The argv here is fixed, so only the module paths vary, and they
    are checked to sit under ``tests/`` with no ``..`` before this runs.
    """
    argv = [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
    try:
        result = subprocess.run(
            [*argv, "--", *paths],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=_COLLECT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CollectionError(f"pytest collection could not run: {exc}") from exc
    if result.returncode != 0:
        tail = (result.stdout + result.stderr).strip().splitlines()[-1:] or ["no output"]
        raise CollectionError(f"pytest collection exited {result.returncode}: {tail[0]}")
    return [line.strip() for line in result.stdout.splitlines() if "::" in line]


def is_text(value: object) -> bool:
    """Return True when value is a string with non-space content."""
    return isinstance(value, str) and bool(value.strip())


def path_key(path: object) -> str:
    """Return one spelling for a path: forward slashes, no empty or ``.`` segments.

    Matches ``normalize_path`` in the sibling trigger, so ``./a/b.py`` and
    ``a\\b.py`` name the same target here and there.
    """
    parts = str(path).replace("\\", "/").strip().split("/")
    return "/".join(part for part in parts if part and part != ".")


def test_names(where: str, key: str, ids: object) -> tuple[Counter[str], list[str]]:
    """Return the module-path-free test names in ``ids`` and any shape defects.

    A collected id looks like ``tests/validation/test_a.py::Class::test_x[p]``.
    A move changes the file path, so only the part after the first ``::``
    is compared; an id with no ``::`` is compared whole.
    """
    label = f"{where}: relocation_evidence.{key}"
    if not isinstance(ids, list) or not ids:
        return Counter(), [f"{label} must be a non-empty list of collected test ids"]
    if not all(is_text(item) for item in ids):
        return Counter(), [f"{label} must contain only non-empty strings"]
    names = (item.strip().split("::", 1)[-1] for item in ids)
    return Counter(names), []


def name_diff(before: Counter[str], after: Counter[str]) -> str:
    """Summarize which test names a relocation lost or gained, capped for readability."""
    parts: list[str] = []
    for label, delta in (("lost", before - after), ("gained", after - before)):
        shown = sorted(delta.elements())[:_RELOCATION_DIFF_LIMIT]
        if shown:
            parts.append(f"{label} {sum(delta.values())}: {', '.join(shown)}")
    return "; ".join(parts)


def _id_paths(ids: Iterable[str] | None) -> set[str]:
    """Return the normalized module paths named by valid collected ids."""
    return {path_key(str(item).strip().split("::", 1)[0]) for item in ids} if ids else set()


def _path_list(where: str, key: str, value: object) -> tuple[set[str], list[str]]:
    """Return the normalized paths in a ``relocation_evidence`` path list and shape defects."""
    label = f"{where}: relocation_evidence.{key}"
    if not isinstance(value, list) or not value or not all(is_text(item) for item in value):
        return set(), [f"{label} must be a non-empty list of test module paths"]
    return {path_key(item) for item in value}, []


def _relocation_path_defects(
    where: str, target: dict[str, Any], evidence: dict[str, Any], moved: tuple[set[str], set[str]]
) -> list[str]:
    """The ids must cover the recorded source and destination files, and the target."""
    source, destination = moved
    defects: list[str] = []
    if path_key(target.get("target")) not in destination:
        defects.append(f"{where}: relocation_evidence.moved_to must list the target")
    for key, expected, label in (
        ("tests_before", source, "moved_from"),
        ("tests_after", destination, "moved_to"),
    ):
        found = _id_paths(evidence.get(key))
        if found != expected:
            defects.append(
                f"{where}: relocation_evidence.{key} must come from exactly the {label} "
                f"files (listed {sorted(expected)}, ids name {sorted(found)})"
            )
    return defects


def _collected_defects(
    where: str, evidence: dict[str, Any], after: Counter[str], collector: Collector
) -> list[str]:
    """Compare the claimed ids with real collection of the moved_to modules."""
    destination = sorted({path_key(item) for item in evidence["moved_to"]})
    try:
        real, shape = test_names(where, "collected", collector(destination))
    except CollectionError as exc:
        return [f"{where}: relocation_evidence could not be verified by real collection: {exc}"]
    if shape:
        return [f"{where}: real collection of the moved_to files found no tests"]
    if real != after:
        return [
            f"{where}: relocation_evidence.tests_after does not match real collection of the "
            f"moved_to files ({sum(after.values())} claimed, {sum(real.values())} collected); "
            f"{name_diff(after, real)}"
        ]
    return []


def relocation_defects(
    where: str, target: dict[str, Any], collector: Collector | None = None
) -> list[str]:
    """Check the `relocation_evidence` block required for a relocation diagnosis.

    With a ``collector``, ``tests_after`` is also compared with what the
    collector reports for the ``moved_to`` files. Because ``tests_before`` must
    equal ``tests_after`` by name, the comparison covers both lists.
    """
    evidence = target.get("relocation_evidence")
    if not isinstance(evidence, dict):
        return [f"{where}: {RELOCATION} diagnosis needs a `relocation_evidence` object"]
    defects: list[str] = []
    if not is_text(evidence.get("collect_command")):
        defects.append(f"{where}: relocation_evidence.collect_command must be a non-empty string")
    before, before_defects = test_names(where, "tests_before", evidence.get("tests_before"))
    after, after_defects = test_names(where, "tests_after", evidence.get("tests_after"))
    source, source_defects = _path_list(where, "moved_from", evidence.get("moved_from"))
    destination, destination_defects = _path_list(where, "moved_to", evidence.get("moved_to"))
    shape = before_defects + after_defects + source_defects + destination_defects
    defects += shape
    if shape:
        return defects
    defects += _relocation_path_defects(where, target, evidence, (source, destination))
    if before != after:
        defects.append(
            f"{where}: relocation changed the collected tests "
            f"({sum(before.values())} before, {sum(after.values())} after); "
            f"{name_diff(before, after)}; use a defect diagnosis"
        )
    if collector is not None and not defects:
        defects += _collected_defects(where, evidence, after, collector)
    return defects


def _is_test_module(segments: list[str]) -> bool:
    """Return True for a ``.py`` file pytest collects by name: ``test_*.py`` or ``*_test.py``."""
    name = segments[-1]
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def relocation_scope_defects(where: str, target: dict[str, Any]) -> list[str]:
    """A relocation claim is limited to LOCAL test modules under ``tests/``."""
    defects: list[str] = []
    if target["provenance"].get("category") != "LOCAL":
        defects.append(f"{where}: {RELOCATION} applies only to LOCAL provenance")
    defects += _tests_path_defects(where, "a target", target.get("target"))
    evidence = target.get("relocation_evidence")
    if isinstance(evidence, dict):
        for key in ("moved_from", "moved_to"):
            listed = evidence.get(key)
            if isinstance(listed, list):
                for item in listed:
                    if is_text(item):
                        defects += _tests_path_defects(
                            where, f"a relocation_evidence.{key} path", item
                        )
    return defects


def _tests_path_defects(where: str, label: str, path: object) -> list[str]:
    """One path must sit under ``tests/``, hold no ``..``, and name a test module."""
    segments = path_key(path).split("/")
    if segments[0] != "tests" or ".." in segments:
        return [f"{where}: {RELOCATION} applies only to {label} under tests/ ({path_key(path)!r})"]
    if not _is_test_module(segments):
        return [
            f"{where}: {RELOCATION} applies only to a test module (test_*.py or *_test.py) "
            f"in {label} ({path_key(path)!r}); "
            "conftest.py and other support files need a defect diagnosis"
        ]
    return []


def is_text_list(value: object) -> bool:
    """Return True when ``value`` is a list of non-empty strings."""
    return isinstance(value, list) and all(is_text(item) for item in value)
