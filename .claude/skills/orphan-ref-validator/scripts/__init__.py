#!/usr/bin/env python3
"""orphan-ref-validator scripts package.

Marks the ``scripts/`` directory as a Python package so tests can import
``from scripts.scan import ...``. The CLI entrypoint lives in ``scan.py``;
do not import it from other modules.
"""
