"""Shared JUnit-report builders for the smoke-ran gate tests.

``scripts/validation/assert_smoke_ran.py`` is stdlib-only and is run by path
(``python -I``), so tests load it by path too instead of importing a package.
"""

from __future__ import annotations

import importlib.util
from functools import partial
from pathlib import Path
from types import ModuleType

GATE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "validation" / "assert_smoke_ran.py"
SMOKE_CLASS = "tests.e2e.test_cli_hook_e2e"
MARKER = "QUOTA_SKIP:"


def load_gate() -> ModuleType:
    """Load the gate script as a module without putting scripts/ on sys.path."""
    spec = importlib.util.spec_from_file_location("assert_smoke_ran", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_report(tmp_path: Path, cases_xml: str, *, wrap: bool = False) -> Path:
    suite = f'<testsuite name="pytest" tests="1">{cases_xml}</testsuite>'
    body = f"<testsuites>{suite}</testsuites>" if wrap else suite
    report = tmp_path / "report.xml"
    report.write_text(f'<?xml version="1.0" encoding="utf-8"?>{body}', encoding="utf-8")
    return report


def write_cases(tmp_path: Path, *cases: str) -> Path:
    """Write a report holding every case in ``cases``, in order."""
    return write_report(tmp_path, "".join(cases))


def passed_case(classname: str, name: str) -> str:
    return f'<testcase classname="{classname}" name="{name}" time="0.1"></testcase>'


def skipped_case(classname: str, name: str) -> str:
    return (
        f'<testcase classname="{classname}" name="{name}" time="0.0">'
        '<skipped type="pytest.skip" message="needs RUN_CLI_E2E=1"></skipped>'
        "</testcase>"
    )


def failed_case(classname: str, name: str) -> str:
    return (
        f'<testcase classname="{classname}" name="{name}" time="0.2">'
        '<failure message="assert">hook never ran</failure>'
        "</testcase>"
    )


def marker_skipped_case(classname: str, name: str, marker: str = MARKER) -> str:
    return (
        f'<testcase classname="{classname}" name="{name}" time="0.0">'
        f'<skipped type="pytest.skip" message="{marker} Copilot quota exhausted"></skipped>'
        "</testcase>"
    )


# The same builders bound to the hook smoke class, for tests that do not care
# which class a case came from.
smoke_passed = partial(passed_case, SMOKE_CLASS)
smoke_skipped = partial(skipped_case, SMOKE_CLASS)
smoke_failed = partial(failed_case, SMOKE_CLASS)
smoke_marker_skipped = partial(marker_skipped_case, SMOKE_CLASS)
