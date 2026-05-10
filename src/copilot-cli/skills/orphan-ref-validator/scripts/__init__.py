#!/usr/bin/env python3
"""orphan-ref-validator scripts package.

Marks the ``scripts/`` directory as a Python package. The CLI entrypoint
lives in ``scan.py``; the curated kebab denylist lives in ``filters.py``.

The test suite at ``.claude/skills/orphan-ref-validator/tests/test_scan.py``
imports the modules by adding the ``scripts/`` directory to ``sys.path``
and using bare imports (``from scan import ...``, ``from filters import
...``). Do not change to package-style imports without updating the tests
and the ``__package__`` fallback in ``scan.py``.
"""
