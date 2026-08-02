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


# Ordering under the 40-line cap (adversarial review of issue #3902).
#
# Fixing the key names made the lister emit lines, but the ratchet caps the
# printed list at 40 and this repository carries 601 tracked violations. On
# #3902's own PR the single added violation sat at index 596, so the correct
# lister still printed 40 unrelated historical entries and hid the one line the
# contributor needed. Ordering branch-touched files first is what makes the
# diagnostic actionable; these tests pin that ordering and the wiring that
# feeds it.


def _batching_fake(reports: list[str], tracked: tuple[str, ...]):
    """Return a distinct report per linter batch, in call order.

    The single-report fake above cannot see a lister that returns only the
    first batch. The real tree needs 19 batches, so that gap is load bearing.
    """
    remaining = list(reports)

    def _run(cmd, **kwargs):
        if cmd[0] == "git":
            listing = "\0".join(tracked) + ("\0" if tracked else "")
            return subprocess.CompletedProcess(cmd, 0, stdout=listing, stderr="")
        return subprocess.CompletedProcess(cmd, 10, stdout=remaining.pop(0), stderr="")

    return _run


def test_a_touched_file_is_listed_before_untouched_ones(tmp_path, monkeypatch):
    """Positive: the branch's own violation leads, whatever its scan position."""
    items = [_error_item(file=f"old/f{index}.py") for index in range(50)]
    items.append(_error_item(file="mine.py", message="File exceeds 500 lines (900 lines)"))
    monkeypatch.setattr(subprocess, "run", _fake(_report(items)))

    lines = ratchet.list_violations(tmp_path, frozenset({"mine.py"}))

    assert lines[0].startswith("mine.py: "), "the touched file must not be buried"
    assert len(lines) == 51, "prioritising must reorder, never drop"
    assert lines[1] == "old/f0.py: [file-size] File exceeds 500 lines (1990 lines)"


def test_an_untouched_tree_keeps_scan_order(tmp_path, monkeypatch):
    """Negative: an empty priority set must not reshuffle anything."""
    items = [_error_item(file=f"old/f{index}.py") for index in range(3)]
    monkeypatch.setattr(subprocess, "run", _fake(_report(items)))

    lines = ratchet.list_violations(tmp_path, frozenset())

    assert [line.split(":", 1)[0] for line in lines] == ["old/f0.py", "old/f1.py", "old/f2.py"]


def test_a_priority_path_that_is_clean_changes_nothing(tmp_path, monkeypatch):
    """Edge: naming a file with no violations is not an error."""
    items = [_error_item(file="old/f0.py")]
    monkeypatch.setattr(subprocess, "run", _fake(_report(items)))

    assert ratchet.list_violations(tmp_path, frozenset({"untouched.py"})) == [
        "old/f0.py: [file-size] File exceeds 500 lines (1990 lines)"
    ]


def test_every_batch_contributes_violations(tmp_path, monkeypatch):
    """Edge: a lister that returned only the first batch would pass the rest."""
    big = "x" * 20000
    monkeypatch.setattr(
        subprocess,
        "run",
        _batching_fake(
            [
                _report([_error_item(file="first.py")]),
                _report([_error_item(file="second.py")]),
            ],
            tracked=(f"{big}/a.py", f"{big}/b.py"),
        ),
    )

    lines = ratchet.list_violations(tmp_path, frozenset())

    assert [line.split(":", 1)[0] for line in lines] == ["first.py", "second.py"]
