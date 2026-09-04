"""Report-persistence tests for the harness capability matrix (issue #5423).

Split from `test_harness_capability.py` to keep both files under the
500-line taste ceiling. These cover `write_report` only: atomicity, mode
carry-over, and the cleanup paths. They share no fixtures with the
classification tests, so nothing is duplicated across the two files.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from tests.eval._harness_capability_test_support import capability


def test_report_write_failure_leaves_the_previous_report_intact(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "report.json"
    output.write_text('{"previous": true}\n', encoding="utf-8")

    # Inject the failure at the replace, which is the only point that touches
    # the destination. A serialization failure would not discriminate: it
    # raises before a non-atomic implementation truncates anything, so the
    # naive version passes such a test too (verified by restoring the defect).
    def _fail_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(capability.os, "replace", _fail_replace)
    with pytest.raises(OSError):
        capability.write_report(output, {"schema_version": 1})

    assert output.read_text(encoding="utf-8") == '{"previous": true}\n'
    # No temporary file is left behind for the next reader to trip over.
    assert list(tmp_path.iterdir()) == [output]


def test_write_report_round_trips(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "report.json"
    capability.write_report(output, {"schema_version": capability.SCHEMA_VERSION})
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "schema_version": capability.SCHEMA_VERSION
    }


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_write_report_preserves_an_existing_report_mode(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    output.write_text("{}\n", encoding="utf-8")
    output.chmod(0o644)

    capability.write_report(output, {"schema_version": capability.SCHEMA_VERSION})

    # mkstemp creates 0600 and os.replace publishes the temporary file's mode,
    # so without the carry-over a re-run would narrow 0644 to 0600 and cut off
    # a reader that could open the previous report.
    assert stat.S_IMODE(output.stat().st_mode) == 0o644


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_write_report_keeps_the_restrictive_default_for_a_new_report(
    tmp_path: Path,
) -> None:
    output = tmp_path / "report.json"
    capability.write_report(output, {"schema_version": capability.SCHEMA_VERSION})
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_report_write_failure_before_replace_leaves_the_report_intact(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "report.json"
    output.write_text('{"previous": true}\n', encoding="utf-8")

    # Fails after the content reaches the temporary file and before the
    # replace, which is the window a mid-write error occupies. A close failure
    # unwinds through the same handler, so it is not tested separately.
    def _fail_fsync(*_args: object, **_kwargs: object) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr(capability.os, "fsync", _fail_fsync)
    with pytest.raises(OSError):
        capability.write_report(output, {"schema_version": 1})

    assert output.read_text(encoding="utf-8") == '{"previous": true}\n'
    assert list(tmp_path.iterdir()) == [output]
