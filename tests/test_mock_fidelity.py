"""Tests for the mock fidelity validation helpers."""

from __future__ import annotations

import pytest

from tests.mock_fidelity import (
    assert_mock_keys_match,
    assert_mock_types_match,
    get_fixture_keys,
    load_fixture,
)


class TestLoadFixture:
    def test_loads_issue_fixture(self):
        fixture = load_fixture("issue")
        assert isinstance(fixture, dict)
        assert "number" in fixture
        assert "title" in fixture

    def test_loads_pull_request_fixture(self):
        fixture = load_fixture("pull_request")
        assert isinstance(fixture, dict)
        assert "number" in fixture
        assert "headRefName" in fixture

    def test_loads_review_thread_fixture(self):
        fixture = load_fixture("review_thread")
        assert isinstance(fixture, dict)
        assert "id" in fixture
        assert "isResolved" in fixture

    def test_missing_fixture_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_fixture("nonexistent_fixture")


class TestGetFixtureKeys:
    def test_excludes_metadata_keys(self):
        keys = get_fixture_keys("issue")
        assert "_description" not in keys

    def test_includes_data_keys(self):
        keys = get_fixture_keys("issue")
        assert "number" in keys
        assert "title" in keys
        assert "state" in keys


class TestAssertMockKeysMatch:
    def test_matching_keys_pass(self):
        fixture = load_fixture("issue")
        mock = {k: v for k, v in fixture.items() if not k.startswith("_")}
        assert_mock_keys_match(mock, "issue")

    def test_missing_key_fails(self):
        fixture = load_fixture("issue")
        mock = {k: v for k, v in fixture.items() if not k.startswith("_")}
        del mock["title"]
        with pytest.raises(AssertionError, match="Missing keys"):
            assert_mock_keys_match(mock, "issue")

    def test_extra_key_fails(self):
        fixture = load_fixture("issue")
        mock = {k: v for k, v in fixture.items() if not k.startswith("_")}
        mock["extraField"] = "value"
        with pytest.raises(AssertionError, match="Extra keys"):
            assert_mock_keys_match(mock, "issue")

    def test_allow_extra_skips_extra_check(self):
        fixture = load_fixture("issue")
        mock = {k: v for k, v in fixture.items() if not k.startswith("_")}
        mock["extraField"] = "value"
        assert_mock_keys_match(mock, "issue", allow_extra=True)

    def test_allow_missing_skips_missing_check(self):
        fixture = load_fixture("issue")
        mock = {k: v for k, v in fixture.items() if not k.startswith("_")}
        del mock["title"]
        assert_mock_keys_match(mock, "issue", allow_missing=True)


class TestAssertMockTypesMatch:
    def test_matching_types_pass(self):
        fixture = load_fixture("issue")
        mock = {k: v for k, v in fixture.items() if not k.startswith("_")}
        assert_mock_types_match(mock, "issue")

    def test_wrong_type_fails(self):
        fixture = load_fixture("issue")
        mock = {k: v for k, v in fixture.items() if not k.startswith("_")}
        mock["number"] = "not_a_number"
        with pytest.raises(AssertionError, match="Mock type mismatch"):
            assert_mock_types_match(mock, "issue")

    def test_none_values_skipped(self):
        mock = {
            "number": 1,
            "title": "test",
            "body": None,
            "state": "OPEN",
            "author": {"login": "u"},
            "labels": [],
            "milestone": None,
            "assignees": [],
            "createdAt": "2025-01-01T00:00:00Z",
            "updatedAt": "2025-01-01T00:00:00Z",
        }
        assert_mock_types_match(mock, "issue")
