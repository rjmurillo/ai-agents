"""Tests for the taste ratchet's regression diagnostic (issue #3902).

``list_violations`` read ``report["findings"]`` and ``item["path"]`` while
``taste_lints.py`` emits ``report["violations"]`` with an ``item["file"]`` key,
and has never emitted either name the lister looked for. The lister therefore
returned an empty list on every input, so a tripped ratchet printed the new
count and named none of the violations behind it. The function shipped with no
test coverage at all, which is how the mismatch survived.

These tests pin both key names against the emitter's real shape. The fake below
is deliberately narrower than ``_fake_scan`` in ``test_taste_count_ratchet``:
``list_violations`` touches only the file listing and the linter, never the
baseline probes, so modelling those legs here would assert nothing.
"""

from __future__ import annotations

import json
import subprocess

from scripts.ci import taste_count_ratchet as ratchet


def _report(items: list[object], *, key: str = "violations") -> str:
    return json.dumps(
        {
            "files_scanned": 1,
            "files_by_category": {"authored": 1},
            "error_count": len(items),
            "warning_count": 0,
            key: items,
        }
    )


def _error_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "rule": "file-size",
        "severity": "error",
        "category": "authored",
        "file": "docs/big.md",
        "line": 1990,
        "message": "File exceeds 500 lines (1990 lines)",
    }
    item.update(overrides)
    return item


def _fake(stdout: str, *, returncode: int = 10, tracked: tuple[str, ...] = ("pkg/mod.py",)):
    """Stand in for the two subprocess legs ``list_violations`` actually uses."""

    def _run(cmd, **kwargs):
        if cmd[0] == "git":
            listing = "\0".join(tracked) + ("\0" if tracked else "")
            return subprocess.CompletedProcess(cmd, 0, stdout=listing, stderr="")
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    return _run


def test_an_error_severity_violation_is_rendered(tmp_path, monkeypatch):
    """Positive: file, rule, and message reach the contributor."""
    monkeypatch.setattr(subprocess, "run", _fake(_report([_error_item()])))
    assert ratchet.list_violations(tmp_path) == [
        "docs/big.md: [file-size] File exceeds 500 lines (1990 lines)"
    ]


def test_the_stale_findings_key_yields_nothing(tmp_path, monkeypatch):
    """Negative: a report keyed "findings" must not render.

    ``taste_lints.py`` has never emitted that key. If this ever returns a line,
    the lister has regressed onto the name that caused the empty diagnostic.
    """
    monkeypatch.setattr(subprocess, "run", _fake(_report([_error_item()], key="findings")))
    assert ratchet.list_violations(tmp_path) == []


def test_the_stale_path_key_renders_the_unknown_marker(tmp_path, monkeypatch):
    """Negative: an item keyed "path" proves we read "file" instead."""
    item = _error_item()
    item.pop("file")
    item["path"] = "docs/big.md"
    monkeypatch.setattr(subprocess, "run", _fake(_report([item])))
    assert ratchet.list_violations(tmp_path) == [
        "?: [file-size] File exceeds 500 lines (1990 lines)"
    ]


def test_warning_severity_is_not_listed(tmp_path, monkeypatch):
    """Negative: the ratchet counts errors, so the diagnostic lists only errors."""
    monkeypatch.setattr(subprocess, "run", _fake(_report([_error_item(severity="warning")])))
    assert ratchet.list_violations(tmp_path) == []


def test_a_non_mapping_entry_is_skipped(tmp_path, monkeypatch):
    """Edge: one malformed entry must not discard the rest of the batch."""
    monkeypatch.setattr(subprocess, "run", _fake(_report(["not-a-dict", _error_item()])))
    assert ratchet.list_violations(tmp_path) == [
        "docs/big.md: [file-size] File exceeds 500 lines (1990 lines)"
    ]


def test_absent_rule_and_message_fall_back(tmp_path, monkeypatch):
    """Edge: a sparse entry renders placeholders rather than raising KeyError."""
    monkeypatch.setattr(subprocess, "run", _fake(_report([{"severity": "error", "file": "a.md"}])))
    assert ratchet.list_violations(tmp_path) == ["a.md: [?] "]


def test_unparseable_output_is_none_not_empty(tmp_path, monkeypatch):
    """Edge: a broken linter must not read as a clean tree."""
    monkeypatch.setattr(subprocess, "run", _fake("{not json"))
    assert ratchet.list_violations(tmp_path) is None


def test_an_unexpected_exit_code_is_none_not_empty(tmp_path, monkeypatch):
    """Edge: only the clean and violations exit codes carry a usable report."""
    monkeypatch.setattr(subprocess, "run", _fake(_report([_error_item()]), returncode=1))
    assert ratchet.list_violations(tmp_path) is None


def test_an_empty_tracked_tree_lists_nothing(tmp_path, monkeypatch):
    """Edge: no tracked files means no violations, distinct from a scan failure."""
    monkeypatch.setattr(subprocess, "run", _fake(_report([_error_item()]), tracked=()))
    assert ratchet.list_violations(tmp_path) == []
