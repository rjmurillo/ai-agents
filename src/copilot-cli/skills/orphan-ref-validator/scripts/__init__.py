#!/usr/bin/env python3
"""orphan-ref-validator scripts package.

Marks the ``scripts/`` directory as a Python package. The CLI entrypoint
lives in ``scan.py``; the curated kebab denylist lives in ``filters.py``.

The test suite at ``.claude/skills/orphan-ref-validator/tests/test_scan.py``
loads ``scan.py`` via ``importlib.util.spec_from_file_location`` with a
file-keyed module name to keep the canonical and Copilot CLI mirrored
suites isolated in ``sys.modules``. Do not change this contract without
updating the loader logic in both ``test_scan.py`` files and the
``__package__`` fallback at the top of ``scan.py``.
"""
