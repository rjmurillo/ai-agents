#!/usr/bin/env python3
"""orphan-ref-validator scripts package.

Marks the ``scripts/`` directory as a Python package. The CLI entrypoint
lives in ``scan.py``; the curated kebab denylist lives in ``filters.py``.

The test suite at ``tests/skills/orphan-ref-validator/test_scan.py``
loads ``scan.py`` via ``importlib.util.spec_from_file_location`` with a
file-keyed module name to keep it isolated in ``sys.modules`` from other
bare-name imports of ``scan``. Do not change this contract without
updating the loader logic in ``test_scan.py`` and the
``__package__`` fallback at the top of ``scan.py``.
"""
