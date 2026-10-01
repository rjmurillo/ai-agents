"""The bypass allowlist loader accepts a well-formed file and refuses every other shape.

Issue #5636, decision D17. The loader is the trust boundary for the gate in
``check_bypass_allowlist.py``: an entry it accepts authorizes a bypass, so each
rule has a test that feeds it the input the rule exists to refuse.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.bypass_allowlist import (
    ALLOWLIST_RELATIVE_PATH,
    AllowlistError,
    load_allowlist,
    parse_allowlist,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _toggle(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "kind": "toggle",
        "toggle": "SKIP_EXAMPLE",
        "reason": "why",
        "owner": "rjmurillo",
        "expires": "2026-12-31",
    }
    entry.update(overrides)
    return entry


def _step(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "kind": "continue-on-error",
        "path": ".github/workflows/x.yml",
        "job": "job-id",
        "step": "Step name",
        "reason": "why",
        "owner": "rjmurillo",
        "expires": "2026-12-31",
    }
    entry.update(overrides)
    return entry


def _document(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "1", "entries": list(entries)}


def test_a_well_formed_document_loads_both_kinds() -> None:
    allowlist = parse_allowlist(_document(_toggle(), _step()))

    assert set(allowlist.toggles) == {"SKIP_EXAMPLE"}
    assert allowlist.toggles["SKIP_EXAMPLE"].expires == date(2026, 12, 31)
    assert set(allowlist.steps) == {(".github/workflows/x.yml", "job-id", "Step name")}


def test_an_empty_step_names_a_job_level_entry() -> None:
    allowlist = parse_allowlist(_document(_step(step="")))

    assert (".github/workflows/x.yml", "job-id", "") in allowlist.steps


def test_a_prefixed_toggle_name_is_accepted() -> None:
    allowlist = parse_allowlist(_document(_toggle(toggle="AI_AGENTS_SKIP_TESTS")))

    assert "AI_AGENTS_SKIP_TESTS" in allowlist.toggles


def test_the_reason_is_stripped() -> None:
    allowlist = parse_allowlist(_document(_toggle(reason="  padded  ")))

    assert allowlist.toggles["SKIP_EXAMPLE"].reason == "padded"


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ([], "must be a JSON object"),
        ({"entries": []}, "schema_version"),
        ({"schema_version": "2", "entries": []}, "schema_version"),
        ({"schema_version": "1"}, "'entries' must be a list"),
        ({"schema_version": "1", "entries": {}}, "'entries' must be a list"),
    ],
)
def test_a_malformed_document_is_refused(document: object, message: str) -> None:
    with pytest.raises(AllowlistError, match=message):
        parse_allowlist(document)


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ("text", "must be an object"),
        ({}, "'kind' must be one of"),
        (_toggle(kind="other"), "'kind' must be one of"),
        (_toggle(extra="x"), "unknown key"),
        (_toggle(path="a.yml"), "unknown key"),
        (_step(toggle="SKIP_X"), "unknown key"),
        (_toggle(toggle="EXAMPLE"), "'toggle' must be"),
        (_toggle(toggle="skip_example"), "'toggle' must be"),
        (_toggle(toggle=None), "'toggle' must be"),
        (_toggle(reason=""), "'reason' must be a non-empty"),
        (_toggle(reason="   "), "'reason' must be a non-empty"),
        (_toggle(reason=None), "'reason' must be a non-empty"),
        (_toggle(reason="line\nbreak"), "control character"),
        (_toggle(reason="::error::x\x7f"), "control character"),
        (_toggle(owner=""), "'owner' must be a non-empty"),
        (_toggle(owner="two words"), "'owner' must be a handle"),
        (_toggle(owner="-lead"), "'owner' must be a handle"),
        (_toggle(expires=None), "YYYY-MM-DD"),
        (_toggle(expires="2026-12-31T00:00"), "YYYY-MM-DD"),
        (_toggle(expires="20261231"), "YYYY-MM-DD"),
        (_toggle(expires="2026-13-01"), "real calendar date"),
        (_toggle(expires="2026-02-30"), "real calendar date"),
        (_step(path=""), "'path' must be a non-empty"),
        (_step(path="/abs/x.yml"), "repo-relative"),
        (_step(path="../x.yml"), "no '..'"),
        (_step(path=".github/workflows/../x.yml"), "no '..'"),
        (_step(path=".github\\workflows\\x.yml"), "forward slashes"),
        (_step(path=".github/workflows/*.yml"), "not a glob"),
        (_step(path=".github/workflows/"), "repo-relative"),
        (_step(path=" .github/workflows/x.yml"), "forward slashes"),
        (_step(job=""), "'job' must be a non-empty"),
        (_step(step=None), "'step' must be a string"),
        (_step(step="bad\nstep"), "'step' must be a string"),
    ],
)
def test_an_invalid_entry_is_refused(entry: Any, message: str) -> None:
    with pytest.raises(AllowlistError, match=message):
        parse_allowlist(_document(entry))


def test_a_duplicate_toggle_is_refused() -> None:
    with pytest.raises(AllowlistError, match="duplicate entry"):
        parse_allowlist(_document(_toggle(), _toggle(reason="again")))


def test_a_duplicate_step_key_is_refused() -> None:
    with pytest.raises(AllowlistError, match="duplicate entry"):
        parse_allowlist(_document(_step(), _step(reason="again")))


def test_the_same_toggle_and_step_names_do_not_collide_across_kinds() -> None:
    allowlist = parse_allowlist(_document(_toggle(), _step(step="SKIP_EXAMPLE")))

    assert len(allowlist.toggles) == 1
    assert len(allowlist.steps) == 1


def test_every_bad_entry_is_named_in_one_error() -> None:
    with pytest.raises(AllowlistError) as raised:
        parse_allowlist(_document(_toggle(reason=""), _toggle(toggle="bad")))

    assert "entries[0]" in str(raised.value)
    assert "entries[1]" in str(raised.value)


def _write(root: Path, text: str) -> None:
    target = root / ALLOWLIST_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    target.write_text(text, encoding="utf-8")


def test_a_missing_file_is_an_empty_allowlist(tmp_path: Path) -> None:
    allowlist = load_allowlist(tmp_path)

    assert allowlist.toggles == {}
    assert allowlist.steps == {}


def test_a_file_that_is_not_json_is_an_error_not_an_empty_allowlist(tmp_path: Path) -> None:
    _write(tmp_path, "{not json")

    with pytest.raises(AllowlistError, match="cannot parse"):
        load_allowlist(tmp_path)


def test_a_file_that_is_not_utf8_is_an_error(tmp_path: Path) -> None:
    target = tmp_path / ALLOWLIST_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(AllowlistError, match="cannot read"):
        load_allowlist(tmp_path)


def test_a_path_that_is_a_directory_is_an_error(tmp_path: Path) -> None:
    (tmp_path / ALLOWLIST_RELATIVE_PATH).mkdir(parents=True)

    with pytest.raises(AllowlistError, match="cannot read"):
        load_allowlist(tmp_path)


def test_a_valid_file_round_trips(tmp_path: Path) -> None:
    _write(tmp_path, json.dumps(_document(_toggle(), _step())))

    allowlist = load_allowlist(tmp_path)

    assert "SKIP_EXAMPLE" in allowlist.toggles
    assert len(allowlist.steps) == 1


def test_the_shipped_allowlist_loads() -> None:
    allowlist = load_allowlist(REPO_ROOT)

    assert len(allowlist.toggles) >= 1
    assert len(allowlist.steps) >= 1
