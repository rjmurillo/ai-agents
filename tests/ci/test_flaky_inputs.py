"""Tests for scripts/ci/_flaky_inputs.py: JUnit and pytest cache reading."""

from __future__ import annotations

import json

import pytest

from scripts.ci import _flaky_inputs as fi
from tests.ci.flaky_test_helpers import write_junit


def test_junit_counts_failures_and_errors(tmp_path):
    counts = fi.load_junit_counts(write_junit(tmp_path / "r.xml", [None, "failure", "error", None]))
    assert counts == fi.JunitCounts(tests=4, failed=2, passed=2)


def test_junit_counts_a_skipped_test_as_not_run(tmp_path):
    """A skip is not a pass, so it must not reach the passed count.

    The classifier proves a rerun passed by counting named testcases with no
    outcome child. Drop the skip counting and a test skipped on the rerun reads
    as a pass, which is the false-flaky route this report exists to avoid.
    """
    counts = fi.load_junit_counts(write_junit(tmp_path / "r.xml", [None, "skipped"]))
    assert counts.tests == 2
    assert counts.skipped == 1
    assert counts.passed == 1


def test_junit_nameless_testcase_is_not_a_pass(tmp_path):
    """A session abort writes a testcase with no name that proves nothing."""
    path = tmp_path / "r.xml"
    path.write_text(
        "<testsuites><testsuite><testcase classname='tests.test_a'>"
        "<error message='x'/></testcase><testcase/></testsuite></testsuites>",
        encoding="utf-8",
    )
    counts = fi.load_junit_counts(path)
    assert counts.tests == 2
    assert counts.failed == 1
    assert counts.passed == 0


def test_junit_single_testsuite_root_is_accepted(tmp_path):
    path = tmp_path / "r.xml"
    path.write_text("<testsuite><testcase name='a'/></testsuite>", encoding="utf-8")
    assert fi.load_junit_counts(path) == fi.JunitCounts(tests=1, failed=0, passed=1)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("<testsuites><testcase>", "malformed"),
        ("<!DOCTYPE x [<!ENTITY a 'b'>]><testsuites/>", "DTD"),
        ("<html/>", "not a JUnit report"),
    ],
)
def test_junit_bad_content_fails_closed(tmp_path, payload, message):
    path = tmp_path / "r.xml"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(fi.InputError, match=message):
        fi.load_junit_counts(path)


def test_junit_missing_fails_closed(tmp_path):
    with pytest.raises(fi.InputError, match="not found"):
        fi.load_junit_counts(tmp_path / "absent.xml")


def test_junit_undecodable_fails_closed(tmp_path):
    path = tmp_path / "r.xml"
    path.write_bytes(b"\xff\xfe\xfa")
    with pytest.raises(fi.InputError, match="could not read"):
        fi.load_junit_counts(path)


def test_lastfailed_missing_is_empty(tmp_path):
    assert fi.load_lastfailed(tmp_path / "lastfailed") == []


def test_lastfailed_sorted_and_false_entries_dropped(tmp_path):
    path = tmp_path / "lastfailed"
    path.write_text(json.dumps({"b": True, "a": True, "c": False}), encoding="utf-8")
    assert fi.load_lastfailed(path) == ["a", "b"]


@pytest.mark.parametrize("payload", ["{not json", "[1, 2]"])
def test_lastfailed_malformed_fails_closed(tmp_path, payload):
    path = tmp_path / "lastfailed"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(fi.InputError):
        fi.load_lastfailed(path)
