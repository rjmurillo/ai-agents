"""Tests for scripts/validation/check_dual_priority_labels.py.

Covers the pure decision function ``find_priority_labels`` and the CLI
``main`` for the dual-priority-label gate (Issue #2623, part 1).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[1]
_script_path = (
    _project_root / "scripts" / "validation" / "check_dual_priority_labels.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_dual_priority_labels", _script_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()


class TestFindPriorityLabels:
    """Pure decision logic over a label name list."""

    def test_no_priority_labels_returns_empty(self):
        assert mod.find_priority_labels(["bug", "automation"]) == []

    def test_single_priority_label_returns_one(self):
        assert mod.find_priority_labels(["bug", "priority:P2"]) == ["priority:P2"]

    def test_two_priority_labels_returns_both_sorted(self):
        # Order is deterministic (sorted) so the message is stable.
        assert mod.find_priority_labels(
            ["priority:P2", "bug", "priority:P1"]
        ) == ["priority:P1", "priority:P2"]

    def test_case_insensitive_prefix_match(self):
        # GitHub label names are case-sensitive, but the prefix check must not
        # miss a "Priority:P1" stamped by a different tool.
        assert mod.find_priority_labels(["Priority:P1", "priority:P2"]) == [
            "Priority:P1",
            "priority:P2",
        ]

    def test_non_priority_prefixed_label_ignored(self):
        # "priority-board" is not a priority:* label.
        assert mod.find_priority_labels(["priority-board", "bug"]) == []

    def test_empty_list(self):
        assert mod.find_priority_labels([]) == []


class TestMainWithExplicitLabels:
    """CLI path that takes labels directly (no network)."""

    def test_clean_single_priority_exits_zero(self, capsys):
        rc = mod.main(["--labels", "bug", "priority:P1"])
        assert rc == 0

    def test_dual_priority_exits_one(self, capsys):
        rc = mod.main(["--labels", "priority:P1", "priority:P2"])
        assert rc == 1
        out = capsys.readouterr().out
        assert "priority:P1" in out
        assert "priority:P2" in out

    def test_no_labels_exits_zero(self):
        rc = mod.main(["--labels"])
        assert rc == 0
