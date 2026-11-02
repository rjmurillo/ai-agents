"""Tests for scripts/ci/_flaky_state.py: the rerun state file contract."""

from __future__ import annotations

import json

import pytest

from scripts.ci import _flaky_state as fs
from scripts.ci._flaky_inputs import InputError
from tests.ci.flaky_test_helpers import make_state


def test_state_missing_is_none(tmp_path):
    assert fs.load_state(tmp_path / "state.json") is None


def test_state_round_trips_through_write_json(tmp_path):
    path = tmp_path / "nested" / "state.json"
    fs.write_json(path, make_state())
    assert fs.load_state(path) == make_state()


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ("{bad", InputError),
        (json.dumps({"version": 99}), fs.StateError),
        (json.dumps(make_state(status="weird")), fs.StateError),
        (json.dumps(make_state(first_failures="x")), fs.StateError),
        (json.dumps(make_state(rerun_failures=[1])), fs.StateError),
    ],
)
def test_state_invalid(tmp_path, payload, error):
    path = tmp_path / "state.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(error):
        fs.load_state(path)


def test_string_list_rejects_missing_key():
    with pytest.raises(fs.StateError, match="absent"):
        fs.string_list({}, "absent")
