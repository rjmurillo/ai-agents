"""Tests for check_publication.py (issue #5403, scenarios 8, 9, 18)."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_SKILL = _ROOT / ".claude" / "skills" / "pr-comment-responder"
_SCRIPT = _SKILL / "scripts" / "check_publication.py"
_PROTOCOL = _SKILL / "references" / "review-conversation.md"

_spec = importlib.util.spec_from_file_location("check_publication", _SCRIPT)
assert _spec is not None and _spec.loader is not None
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)


def _data(disposition: str, body: Any, **extra: Any) -> dict[str, Any]:
    return {
        "findings": [{"id": "F1", "disposition": disposition}],
        "comments": [{"finding_id": "F1", "path": "a.py", "line": 3, "body": body, **extra}],
    }


def _kinds(data: dict[str, Any]) -> list[str]:
    return [v["kind"] for v in cp.check_publication(data)]


def test_prefix_table_matches_protocol_table() -> None:
    rows = re.findall(r"^\| `(\w+)` \| (`[^`]+`|none) \|", _PROTOCOL.read_text("utf-8"), re.M)
    documented = {name: ("" if cell == "none" else cell.strip("`")) for name, cell in rows}
    assert documented == cp.PREFIXES


@pytest.mark.parametrize(
    ("disposition", "body"),
    [
        ("BLOCKING", "Unbounded retry. Why: hangs CI."),
        ("OPTIONAL", "Optional: extract a helper."),
        ("NIT", "Nit: rename x."),
        ("FYI", "FYI: new API lands next release."),
        ("NIT", "  nit: lowercase and padded."),
    ],
)
def test_matching_disposition_is_clean(disposition: str, body: str) -> None:
    assert cp.check_publication(_data(disposition, body)) == []


def test_optional_rendered_as_blocking_is_flagged() -> None:
    assert _kinds(_data("OPTIONAL", "Fix this before merge.")) == ["severity_mutation"]


@pytest.mark.parametrize("prefix", ["Nit:", "FYI:", "Optional:"])
def test_blocking_rendered_with_soft_prefix_is_flagged(prefix: str) -> None:
    assert _kinds(_data("BLOCKING", f"{prefix} data loss on retry")) == ["severity_mutation"]


def test_nit_promoted_to_optional_is_flagged() -> None:
    assert _kinds(_data("NIT", "Optional: rename x.")) == ["severity_mutation"]


def test_same_finding_published_twice_is_duplicate() -> None:
    data = _data("NIT", "Nit: rename x.")
    data["comments"].append(
        {"finding_id": "F1", "path": "b.py", "line": 9, "body": "Nit: rename y."}
    )
    assert _kinds(data) == ["duplicate"]


def test_same_text_on_same_line_is_duplicate_across_findings() -> None:
    data = {
        "findings": [{"id": "F1", "disposition": "NIT"}, {"id": "F2", "disposition": "NIT"}],
        "comments": [
            {"finding_id": "F1", "path": "a.py", "line": 3, "body": "Nit:  Rename   x."},
            {"finding_id": "F2", "path": "a.py", "line": 3, "body": "nit: rename x."},
        ],
    }
    assert _kinds(data) == ["duplicate"]


def test_same_text_on_different_line_is_not_duplicate() -> None:
    data = {
        "findings": [{"id": "F1", "disposition": "NIT"}, {"id": "F2", "disposition": "NIT"}],
        "comments": [
            {"finding_id": "F1", "path": "a.py", "line": 3, "body": "Nit: rename x."},
            {"finding_id": "F2", "path": "a.py", "line": 4, "body": "Nit: rename x."},
        ],
    }
    assert cp.check_publication(data) == []


def test_comment_without_finding_is_flagged() -> None:
    data = _data("NIT", "Nit: a.")
    data["comments"][0]["finding_id"] = "F9"
    assert _kinds(data) == ["unknown_finding"]


@pytest.mark.parametrize(
    "data",
    [
        {"comments": []},
        {"findings": [], "comments": "x"},
        {"findings": [{"id": "", "disposition": "NIT"}], "comments": []},
        {"findings": [{"id": "F1", "disposition": "MAJOR"}], "comments": []},
        {"findings": [{"id": "F1", "disposition": "NIT"}] * 2, "comments": []},
        _data("NIT", "   "),
        _data("NIT", None),
    ],
)
def test_malformed_input_raises(data: dict[str, Any]) -> None:
    with pytest.raises(cp.InputError):
        cp.check_publication(data)


def _run(tmp_path: Path, data: dict[str, Any], capsys: Any) -> tuple[int, str]:
    path = tmp_path / "in.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    code = cp.main([str(path)])
    return code, capsys.readouterr().out


def test_main_exit_0_when_clean(tmp_path: Path, capsys) -> None:
    code, out = _run(tmp_path, _data("NIT", "Nit: a."), capsys)
    assert (code, json.loads(out)["count"]) == (0, 0)


def test_main_exit_1_on_violation(tmp_path: Path, capsys) -> None:
    code, out = _run(tmp_path, _data("OPTIONAL", "Do it."), capsys)
    assert (code, json.loads(out)["count"]) == (1, 1)


def test_main_exit_2_on_missing_file(capsys) -> None:
    assert cp.main(["/nonexistent/in.json"]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_main_exit_2_on_non_object(tmp_path: Path, capsys) -> None:
    path = tmp_path / "in.json"
    path.write_text("[]", encoding="utf-8")
    assert cp.main([str(path)]) == 2
    assert "top-level" in capsys.readouterr().err


def test_main_exit_2_on_non_utf8_file(tmp_path: Path, capsys) -> None:
    path = tmp_path / "in.json"
    path.write_bytes(b"\xff\xfe\x00bad")
    assert cp.main([str(path)]) == 2
    assert "cannot read" in capsys.readouterr().err


@pytest.mark.parametrize("bad", [["F1"], {"a": 1}, 7, None])
def test_unhashable_or_wrong_type_fields_do_not_crash(bad) -> None:
    data = _data("NIT", "Nit: a.")
    data["comments"][0]["finding_id"] = bad
    data["comments"][0]["path"] = bad
    data["comments"][0]["line"] = bad
    assert _kinds(data) == ["unknown_finding"]


def test_unhashable_disposition_raises_input_error() -> None:
    with pytest.raises(cp.InputError):
        cp.check_publication({"findings": [{"id": "F1", "disposition": ["NIT"]}], "comments": []})
