"""Drift-guard tests for constants ``new_pr.py`` re-exports from ``pr_validations``.

Issue #5368 deleted ``new_pr_validations.py``: its own ``run_validations`` and
everything it reached (session-log validation, skill-violation scanning,
description/dash checks run from that module) had no production caller.
``new_pr.py`` bound only four symbols from it, and three of those four were
already byte-identical duplicates of definitions in ``pr_validations.py``
(the module ``new_pr.py`` actually calls ``run_validations`` from). Those
symbols now live only in ``pr_validations.py``; see
``tests/test_new_pr_warning_reporting.py`` and
``tests/test_new_pr_content_checks.py`` for behavior coverage of the live
``run_validations`` path, and ``tests/test_new_pr_validation_base.py`` for
``_resolve_validation_base``, the fourth symbol, moved into
``pr_validations.py`` in the same change.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from tests.new_pr_test_support import _mod


class TestSkillScanExtensionsDriftGuard:
    def test_skill_scan_extensions_match_detector(self):
        """Keep the local extension set synchronized with the scanner."""
        detector_path = (
            Path(__file__).resolve().parents[1] / "scripts" / "detect_skill_violation.py"
        )
        mod_key = "detect_skill_violation_drift_guard"
        spec = importlib.util.spec_from_file_location(mod_key, detector_path)
        assert spec is not None and spec.loader is not None
        detector = importlib.util.module_from_spec(spec)
        previous = sys.modules.get(mod_key)
        sys.modules[mod_key] = detector
        sys_path_snapshot = list(sys.path)
        try:
            spec.loader.exec_module(detector)
            assert _mod._SKILL_SCAN_EXTENSIONS == detector.VALID_EXTENSIONS
        finally:
            if previous is not None:
                sys.modules[mod_key] = previous
            else:
                sys.modules.pop(mod_key, None)
            sys.path[:] = sys_path_snapshot
