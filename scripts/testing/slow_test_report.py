"""Slow-test telemetry and report (issue #5382).

Recorder (a pytest plugin), records per test item the duration, the number of
subprocesses spawned, the number of filesystem traversals started, and the
distinct executable basenames and traversal roots so the report can name the
underlying scanner rather than only its cost::

    uv run --frozen --extra dev pytest tests/test_guard_diff.py \
        -p scripts.testing.slow_test_report --slow-report=telemetry.json

Reporter (a CLI), groups those records by module::

    uv run python scripts/testing/slow_test_report.py telemetry.json junit.xml

Inputs are matched by extension: ``.json`` is recorder output, ``.xml`` is a
pytest JUnit report. Records for the same node id merge, JUnit supplying
duration and the recorder supplying process and traversal counts, which is how
a CI run that publishes only JUnit still produces a report.

Exit codes: 0 ok, 1 logic, 2 config, 3 external.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps the CLI stdlib-only
    import pytest

SCHEMA_VERSION = 1

# Cap on distinct labels kept per test, and per module once they are unioned. A
# test that spawns 300 processes needs its count, not 300 copies of one basename.
_MAX_LABELS = 8
_MAX_GROUP_LABELS = 16

# Every pytest tmp_path lands under one of these, per-test, so literal roots
# would bury the repository roots that name the real scanner.
#
# `tempfile.gettempdir()` alone is not enough. This repository points pytest's
# basetemp somewhere else on CI: `.github/workflows/pytest.yml` sets
# `PYTEST_NON_TMP_ROOT: ${{ runner.temp }}/ai-agents-pytest`, which lives under
# the runner work directory and not under /tmp. Reading only the system temp
# dir made every CI tmp_path miss the prefix and enter the label set as a raw
# absolute path, which is exactly the burying this collapse exists to prevent.
# It passed locally, where the two agree, and failed on every CI partition.
#
# Computed on demand rather than at import so a runner, or a test, that sets the
# variable after this module loads still gets the right answer. Cached because
# `note_traversal` is on the hot path; tests that move the root call
# `_temp_roots.cache_clear()`.
_TMP_ROOT_ENV_VARS = ("PYTEST_NON_TMP_ROOT", "PYTEST_DEBUG_TEMPROOT", "TMPDIR")


@functools.cache
def _temp_roots() -> tuple[str, ...]:
    """Every prefix a pytest tmp_path can legitimately sit under."""
    candidates = [tempfile.gettempdir()]
    for name in _TMP_ROOT_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            candidates.append(value)
    resolved = {os.path.realpath(c) for c in candidates if c}
    # Longest first so a nested root is credited before its parent.
    return tuple(sorted(resolved, key=len, reverse=True))


def _is_temp_path(label: str) -> bool:
    """True when *label* sits under any known pytest temp root."""
    resolved = os.path.realpath(label)
    return any(resolved.startswith(root) for root in _temp_roots())


# ---------------------------------------------------------------------------
# Record model
# ---------------------------------------------------------------------------


@dataclass
class TestRecord:
    """One test item's measured cost."""

    nodeid: str
    module: str
    duration: float = 0.0
    subprocesses: int = 0
    traversals: int = 0
    commands: list[str] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodeid": self.nodeid,
            "module": self.module,
            "duration": round(self.duration, 4),
            "subprocesses": self.subprocesses,
            "traversals": self.traversals,
            "commands": sorted(self.commands),
            "roots": sorted(self.roots),
        }


def module_of(nodeid: str) -> str:
    """Return the test module path for a pytest node id.

    ``tests/test_x.py::TestY::test_z`` maps to ``tests/test_x.py``. A node id
    with no ``::`` separator is already a module path.
    """
    return nodeid.split("::", 1)[0]


def _merge(into: TestRecord, other: TestRecord) -> None:
    """Fold *other* into *into*, preferring the larger measurement.

    JUnit and recorder rows for one node id describe one execution from two
    vantage points, so the maximum keeps whichever source observed the field
    instead of letting a zero from the other source erase it.
    """
    into.duration = max(into.duration, other.duration)
    into.subprocesses = max(into.subprocesses, other.subprocesses)
    into.traversals = max(into.traversals, other.traversals)
    into.commands = sorted(set(into.commands) | set(other.commands))[:_MAX_LABELS]
    into.roots = sorted(set(into.roots) | set(other.roots))[:_MAX_LABELS]


# ---------------------------------------------------------------------------
# Recorder: probes
# ---------------------------------------------------------------------------


class _Telemetry:
    """Counters for the test item currently running."""

    def __init__(self) -> None:
        self.subprocesses = 0
        self.traversals = 0
        self.commands: set[str] = set()
        self.roots: set[str] = set()

    def note_subprocess(self, args: Any) -> None:
        self.subprocesses += 1
        if len(self.commands) < _MAX_LABELS:
            self.commands.add(_command_label(args))

    def note_traversal(self, root: Any, pattern: str = "") -> None:
        self.traversals += 1
        if len(self.roots) >= _MAX_LABELS:
            return
        label = str(root)
        if _is_temp_path(label):
            self.roots.add("<tmp>")
        else:
            self.roots.add(f"{label}:{pattern}" if pattern else label)


def _command_label(args: Any) -> str:
    """Basename of the executable in a Popen ``args`` value."""
    first = args[0] if isinstance(args, (list, tuple)) and args else args
    try:
        return Path(str(first)).name or str(first)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return "<unknown>"


_active: _Telemetry | None = None
_probes_installed = False


def install_probes() -> None:
    """Wrap subprocess spawn and directory traversal. Idempotent.

    ``Path.rglob`` delegates to ``Path.glob`` on the supported interpreters, so
    wrapping ``glob`` alone counts both without double counting.
    """
    global _probes_installed
    if _probes_installed:
        return
    _probes_installed = True

    original_popen_init = subprocess.Popen.__init__
    original_glob = Path.glob
    original_walk = os.walk

    def popen_init(self: Any, args: Any, *rest: Any, **kwargs: Any) -> Any:
        if _active is not None:
            _active.note_subprocess(args)
        return original_popen_init(self, args, *rest, **kwargs)

    def glob(self: Path, pattern: Any, *rest: Any, **kwargs: Any) -> Any:
        if _active is not None:
            _active.note_traversal(self, str(pattern))
        return original_glob(self, pattern, *rest, **kwargs)

    def walk(top: Any, *rest: Any, **kwargs: Any) -> Any:
        if _active is not None:
            _active.note_traversal(top)
        return original_walk(top, *rest, **kwargs)

    # A loop, not three assignments: mypy rejects each rebinding on sight.
    for target, name, wrapper in (
        (subprocess.Popen, "__init__", popen_init),
        (Path, "glob", glob),
        (os, "walk", walk),
    ):
        setattr(target, name, wrapper)


# ---------------------------------------------------------------------------
# Recorder: pytest plugin
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--slow-report",
        action="store",
        default=None,
        metavar="PATH",
        help="Write per-test duration, subprocess, and traversal telemetry to PATH.",
    )


# pytest's item location: (filesystem path, line number, test name).
_Location = tuple[str, "int | None", str]


class SlowReportPlugin:
    """Collects one :class:`TestRecord` per executed test item."""

    def __init__(self, destination: Path) -> None:
        self.destination = destination
        self.records: dict[str, TestRecord] = {}

    def pytest_runtest_logstart(self, nodeid: str, location: _Location) -> None:
        global _active
        _active = _Telemetry()

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        record = self.records.setdefault(
            report.nodeid, TestRecord(report.nodeid, module_of(report.nodeid))
        )
        record.duration += float(report.duration)

    def pytest_runtest_logfinish(self, nodeid: str, location: _Location) -> None:
        global _active
        counters, _active = _active, None
        if counters is None:
            return
        record = self.records.setdefault(nodeid, TestRecord(nodeid, module_of(nodeid)))
        record.subprocesses += counters.subprocesses
        record.traversals += counters.traversals
        record.commands = sorted(set(record.commands) | counters.commands)[:_MAX_LABELS]
        record.roots = sorted(set(record.roots) | counters.roots)[:_MAX_LABELS]

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        write_records(self.destination, self.records.values())


def _worker_suffixed(destination: Path, worker: str | None) -> Path:
    """Give each xdist worker its own file so parallel writes cannot collide."""
    if not worker:
        return destination
    return destination.with_name(f"{destination.stem}.{worker}{destination.suffix}")


def pytest_configure(config: pytest.Config) -> None:
    raw = config.getoption("--slow-report")
    if not raw:
        return
    worker = getattr(config, "workerinput", {}).get("workerid")
    destination = _worker_suffixed(Path(raw), worker)
    install_probes()
    config.pluginmanager.register(SlowReportPlugin(destination), "slow-report-collector")


def write_records(destination: Path, records: Iterable[TestRecord]) -> None:
    payload = {
        "schema": SCHEMA_VERSION,
        "records": [r.to_dict() for r in sorted(records, key=lambda r: r.nodeid)],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Reporter: input loading
# ---------------------------------------------------------------------------


def load_telemetry(path: Path) -> list[TestRecord]:
    """Read a recorder JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "records" not in data:
        raise ValueError(f"{path}: not a slow-report telemetry file")
    out: list[TestRecord] = []
    for row in data["records"]:
        nodeid = str(row["nodeid"])
        out.append(
            TestRecord(
                nodeid=nodeid,
                module=str(row.get("module") or module_of(nodeid)),
                duration=float(row.get("duration", 0.0)),
                subprocesses=int(row.get("subprocesses", 0)),
                traversals=int(row.get("traversals", 0)),
                commands=list(row.get("commands", [])),
                roots=list(row.get("roots", [])),
            )
        )
    return out


def junit_nodeid(classname: str, name: str) -> str:
    """Rebuild a pytest node id from JUnit ``classname`` and ``name``.

    pytest writes the module's dotted path then any enclosing class names, so
    the module ends at the last part naming a test file (``python_files`` is
    ``test_*.py``). Treating later parts as classes collapsed the 602 of 998
    test files that live in a package into one bogus ``tests.py`` group.
    """
    parts = [p for p in classname.split(".") if p]
    split = 0
    for index, part in enumerate(parts):
        if part.startswith("test_"):
            split = index + 1
    if split == 0:
        # Nothing names a test file: fall back to the class-naming convention.
        split = next((i for i, p in enumerate(parts) if p[:1].isupper()), len(parts))
    module = "/".join(parts[:split]) + ".py" if split else ""
    tail = "::".join([*parts[split:], name])
    return f"{module}::{tail}" if module else tail


def load_junit(path: Path) -> list[TestRecord]:
    """Read durations from a pytest JUnit XML report.

    ``defusedxml`` is not a project dependency, so a report declaring a DTD or an
    entity is rejected before the stdlib parser can expand it (CWE-611, CWE-776).
    pytest's JUnit writer emits neither, so such a report is corrupt or tampered.
    Same fail-closed guard as ``scripts/validation/assert_smoke_ran.py``.
    """
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError(
            f"{path}: report declares a DTD or entity, which a pytest JUnit "
            "report never does; refusing to parse it"
        )
    root = ET.fromstring(text)
    out: list[TestRecord] = []
    for case in root.iter("testcase"):
        nodeid = junit_nodeid(case.get("classname", ""), case.get("name", ""))
        out.append(
            TestRecord(
                nodeid=nodeid,
                module=module_of(nodeid),
                duration=float(case.get("time", "0") or 0.0),
            )
        )
    return out


def load_inputs(paths: Sequence[Path]) -> dict[str, TestRecord]:
    """Load and merge every input file, keyed by node id."""
    merged: dict[str, TestRecord] = {}
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        loader = load_junit if path.suffix.lower() == ".xml" else load_telemetry
        for record in loader(path):
            existing = merged.get(record.nodeid)
            if existing is None:
                merged[record.nodeid] = record
            else:
                _merge(existing, record)
    return merged


# ---------------------------------------------------------------------------
# Reporter: aggregation and rendering
# ---------------------------------------------------------------------------


@dataclass
class ModuleGroup:
    module: str
    seconds: float = 0.0
    tests: int = 0
    slow_tests: int = 0
    subprocesses: int = 0
    traversals: int = 0
    scanners: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "seconds": round(self.seconds, 3),
            "tests": self.tests,
            "slow_tests": self.slow_tests,
            "subprocesses": self.subprocesses,
            "traversals": self.traversals,
            "scanners": sorted(self.scanners),
        }


def group_by_module(records: Iterable[TestRecord], min_seconds: float) -> list[ModuleGroup]:
    """Aggregate records per module, ranked by total seconds."""
    groups: dict[str, ModuleGroup] = {}
    for record in records:
        group = groups.setdefault(record.module, ModuleGroup(record.module))
        group.seconds += record.duration
        group.tests += 1
        group.subprocesses += record.subprocesses
        group.traversals += record.traversals
        if len(group.scanners) < _MAX_GROUP_LABELS:
            group.scanners.update(record.commands)
            group.scanners.update(record.roots)
        if record.duration >= min_seconds:
            group.slow_tests += 1
    return sorted(groups.values(), key=lambda g: (-g.seconds, g.module))


def render_text(
    groups: Sequence[ModuleGroup],
    slowest: Sequence[TestRecord],
    total_seconds: float,
    min_seconds: float,
) -> str:
    lines = [
        f"Recorded test-seconds: {total_seconds:.2f}",
        f"Slow threshold: {min_seconds:.2f}s",
        "",
        "Module totals (seconds, tests, slow, subprocesses, traversals):",
    ]
    for group in groups:
        share = (group.seconds / total_seconds * 100.0) if total_seconds else 0.0
        lines.append(
            f"  {group.seconds:8.2f}s {share:5.1f}%  {group.tests:5d} tests"
            f"  {group.slow_tests:3d} slow"
            f"  {group.subprocesses:5d} proc  {group.traversals:6d} trav"
            f"  {group.module}"
        )
        if group.scanners:
            lines.append(f"           scanners: {', '.join(sorted(group.scanners))}")
    lines.extend(("", f"Tests at or above {min_seconds:.2f}s:"))
    for record in slowest:
        lines.append(
            f"  {record.duration:8.2f}s  {record.subprocesses:4d} proc"
            f"  {record.traversals:5d} trav  {record.nodeid}"
        )
    if not slowest:
        lines.append("  (none)")
    return "\n".join(lines)


def build_report(records: dict[str, TestRecord], min_seconds: float, top: int) -> dict[str, Any]:
    groups = group_by_module(records.values(), min_seconds)
    slowest = sorted(
        (r for r in records.values() if r.duration >= min_seconds),
        key=lambda r: -r.duration,
    )[:top]
    total = sum(r.duration for r in records.values())
    return {
        "total_seconds": round(total, 3),
        "min_seconds": min_seconds,
        "modules": [g.to_dict() for g in groups],
        "slowest": [r.to_dict() for r in slowest],
        "text": render_text(groups, slowest, total, min_seconds),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report slow pytest items grouped by module, scanner, "
        "subprocess count, and traversal count (issue #5382)."
    )
    parser.add_argument(
        "inputs", nargs="+", type=Path, help="Recorder JSON and/or JUnit XML files."
    )
    parser.add_argument(
        "--min-seconds",
        type=float,
        default=5.0,
        help="Duration at or above which a test counts as slow (default: 5.0).",
    )
    parser.add_argument(
        "--top", type=int, default=30, help="How many slow tests to list (default: 30)."
    )
    parser.add_argument(
        "--output-format", choices=("text", "json"), default="text", help="Report format."
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.min_seconds < 0 or args.top < 1:
        print("--min-seconds must be >= 0 and --top must be >= 1", file=sys.stderr)
        return 2
    try:
        records = load_inputs(args.inputs)
    except FileNotFoundError as exc:
        print(f"input not found: {exc}", file=sys.stderr)
        return 3
    except (OSError, ET.ParseError) as exc:
        print(f"could not read input: {exc}", file=sys.stderr)
        return 3
    except (ValueError, KeyError, TypeError) as exc:
        print(f"malformed input: {exc}", file=sys.stderr)
        return 2
    if not records:
        print("no test records in the given inputs", file=sys.stderr)
        return 1
    report = build_report(records, args.min_seconds, args.top)
    if args.output_format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(report["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
