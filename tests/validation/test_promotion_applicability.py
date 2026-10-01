"""The applicability table: strict loading, path matching, and ruleset drift.

ADR-113 decision 3, issue #5636. The drift test is the one the ADR asks for:
every required status check on the default branch ruleset has a row.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS
from scripts.validation.promotion_applicability import (
    APPLICABILITY_RELATIVE_PATH,
    MAX_FILE_BYTES,
    Applicability,
    ApplicabilityError,
    build_tier_validators,
    load_applicability,
    parse_applicability,
    required_validators,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "validator": "run_python_tests",
        "tier": "commit",
        "job": "Run Python Tests",
        "when": "always",
        "rationale": "Required status check.",
    }
    entry.update(overrides)
    return entry


def _doc(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "1", "entries": list(entries)}


def _write(root: Path, text: str) -> Path:
    path = root / APPLICABILITY_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestParse:
    def test_valid_entry(self) -> None:
        (entry,) = parse_applicability(_doc(_entry()))
        assert entry.validator == "run_python_tests"
        assert entry.always
        assert entry.tier == "commit"

    def test_path_list_entry(self) -> None:
        (entry,) = parse_applicability(_doc(_entry(when=[".github/workflows/*.yml"])))
        assert not entry.always
        assert entry.when == (".github/workflows/*.yml",)

    def test_empty_table_is_valid(self) -> None:
        assert parse_applicability(_doc()) == ()

    @pytest.mark.parametrize("field", ["validator", "tier", "job", "when", "rationale"])
    def test_each_field_is_required(self, field: str) -> None:
        entry = _entry()
        del entry[field]
        with pytest.raises(ApplicabilityError, match="missing"):
            parse_applicability(_doc(entry))

    def test_unknown_key_is_refused(self) -> None:
        with pytest.raises(ApplicabilityError, match="unknown key"):
            parse_applicability(_doc(_entry(extra=1)))

    @pytest.mark.parametrize("bad", ["", "Run Tests", "1abc", "a b", 5, None])
    def test_validator_must_be_a_slug(self, bad: Any) -> None:
        with pytest.raises(ApplicabilityError, match="slug"):
            parse_applicability(_doc(_entry(validator=bad)))

    @pytest.mark.parametrize("bad", ["", "release", "COMMIT", None])
    def test_tier_must_be_commit_or_build(self, bad: Any) -> None:
        with pytest.raises(ApplicabilityError, match="tier"):
            parse_applicability(_doc(_entry(tier=bad)))

    @pytest.mark.parametrize("field", ["job", "rationale"])
    @pytest.mark.parametrize("bad", ["", "  ", 5, "a\nb"])
    def test_text_fields_are_checked(self, field: str, bad: Any) -> None:
        with pytest.raises(ApplicabilityError, match=field):
            parse_applicability(_doc(_entry(**{field: bad})))

    @pytest.mark.parametrize(
        "bad",
        [
            "sometimes",
            [],
            [""],
            [5],
            ["a\nb"],
            ["/abs/*"],
            ["../x/*"],
            "ALWAYS",
            None,
            [".github/workflows/"],
            ["./x/*"],
            ["a/*", "docs/"],
        ],  # fmt: skip
    )
    def test_when_is_always_or_a_pattern_list(self, bad: Any) -> None:
        with pytest.raises(ApplicabilityError, match="when"):
            parse_applicability(_doc(_entry(when=bad)))

    def test_duplicate_validator_is_refused(self) -> None:
        with pytest.raises(ApplicabilityError, match="same validator"):
            parse_applicability(_doc(_entry(), _entry(job="Other")))

    def test_non_object_entry_is_refused(self) -> None:
        with pytest.raises(ApplicabilityError, match="JSON object"):
            parse_applicability({"schema_version": "1", "entries": ["x"]})

    @pytest.mark.parametrize(
        "document",
        [[], None, {"schema_version": "2", "entries": []}, {"schema_version": "1"},
         {"schema_version": "1", "entries": {}}],
    )  # fmt: skip
    def test_bad_document_is_refused(self, document: Any) -> None:
        with pytest.raises(ApplicabilityError):
            parse_applicability(document)


class TestLoad:
    def test_missing_file_is_an_empty_table(self, tmp_path: Path) -> None:
        assert load_applicability(tmp_path) == ()

    def test_valid_file_loads(self, tmp_path: Path) -> None:
        _write(tmp_path, json.dumps(_doc(_entry())))
        assert len(load_applicability(tmp_path)) == 1

    def test_bad_json_fails(self, tmp_path: Path) -> None:
        _write(tmp_path, "{nope")
        with pytest.raises(ApplicabilityError, match="cannot parse"):
            load_applicability(tmp_path)

    def test_duplicate_keys_fail(self, tmp_path: Path) -> None:
        _write(tmp_path, '{"schema_version": "1", "entries": [], "entries": []}')
        with pytest.raises(ApplicabilityError, match="duplicate key"):
            load_applicability(tmp_path)

    def test_undecodable_bytes_fail(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "")
        path.write_bytes(b"\xff\xfe\x00")
        with pytest.raises(ApplicabilityError, match="cannot read"):
            load_applicability(tmp_path)

    def test_oversized_file_fails(self, tmp_path: Path) -> None:
        _write(tmp_path, " " * (MAX_FILE_BYTES + 1))
        with pytest.raises(ApplicabilityError, match="larger than"):
            load_applicability(tmp_path)

    def test_directory_in_place_of_the_file_fails(self, tmp_path: Path) -> None:
        (tmp_path / APPLICABILITY_RELATIVE_PATH).mkdir(parents=True)
        with pytest.raises(ApplicabilityError, match="cannot read"):
            load_applicability(tmp_path)

    def test_symlink_fails_with_and_without_the_nofollow_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "real.json"
        target.write_text(json.dumps(_doc()), encoding="utf-8")
        link = tmp_path / APPLICABILITY_RELATIVE_PATH
        link.parent.mkdir(parents=True)
        link.symlink_to(target)
        with pytest.raises(ApplicabilityError, match="cannot read"):
            load_applicability(tmp_path)
        monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
        with pytest.raises(ApplicabilityError, match="cannot read"):
            load_applicability(tmp_path)

    def test_loads_without_the_platform_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
        monkeypatch.delattr(os, "O_BINARY", raising=False)
        _write(tmp_path, json.dumps(_doc(_entry())))
        assert len(load_applicability(tmp_path)) == 1


class TestMatching:
    def _table(self) -> tuple[Applicability, ...]:
        return parse_applicability(
            _doc(
                _entry(),
                _entry(validator="actionlint", job="actionlint", when=[".github/workflows/*"]),
                _entry(validator="pack", tier="build", job="Validate Package", when="always"),
            )
        )

    def test_always_rows_apply_to_any_candidate(self) -> None:
        assert required_validators(self._table(), []) == ("pack", "run_python_tests")

    def test_path_rows_apply_when_the_candidate_holds_a_matching_file(self) -> None:
        names = required_validators(self._table(), [".github/workflows/ci.yml", "README.md"])
        assert names == ("actionlint", "pack", "run_python_tests")

    def test_path_rows_do_not_apply_without_a_matching_file(self) -> None:
        assert "actionlint" not in required_validators(self._table(), ["src/app.py"])

    def test_star_crosses_directories_so_matching_only_widens(self) -> None:
        table = parse_applicability(_doc(_entry(when=["scripts/*.py"])))
        assert required_validators(table, ["scripts/deep/nested/tool.py"]) == ("run_python_tests",)

    def test_matching_is_case_sensitive(self) -> None:
        table = parse_applicability(_doc(_entry(when=["Docs/*"])))
        assert required_validators(table, ["docs/a.md"]) == ()

    def test_paths_may_be_a_generator(self) -> None:
        table = parse_applicability(_doc(_entry(when=["a/*"]), _entry(validator="b", when=["b/*"])))
        paths = (name for name in ["a/x", "b/y"])
        assert required_validators(table, paths) == ("b", "run_python_tests")

    def test_build_tier_set(self) -> None:
        assert build_tier_validators(self._table()) == frozenset({"pack"})


class TestShippedTable:
    def test_the_shipped_table_loads(self) -> None:
        assert len(load_applicability(REPO_ROOT)) > 0

    def test_every_required_status_check_has_a_row(self) -> None:
        """Gate coverage equals table coverage (decision 3): fail on drift."""
        jobs = {entry.job for entry in load_applicability(REPO_ROOT)}
        assert REQUIRED_CONTEXTS <= jobs, sorted(REQUIRED_CONTEXTS - jobs)

    def test_every_required_check_applies_to_every_candidate(self) -> None:
        """A required check scoped to some paths would not be required for the rest."""
        rows = [e for e in load_applicability(REPO_ROOT) if e.job in REQUIRED_CONTEXTS]
        assert rows
        assert all(row.always for row in rows), [r.validator for r in rows if not r.always]

    def test_the_package_checks_bind_on_the_tarball_digest(self) -> None:
        build = build_tier_validators(load_applicability(REPO_ROOT))
        assert {"npm_package_metadata", "npm_pack_size"} <= build

    def test_every_validator_name_is_a_slug(self) -> None:
        slug = re.compile(r"[a-z][a-z0-9_.-]*")
        assert all(slug.fullmatch(e.validator) for e in load_applicability(REPO_ROOT))
