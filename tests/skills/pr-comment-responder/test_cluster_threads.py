#!/usr/bin/env python3
"""CI-collected wrapper for the pr-comment-responder cluster tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SKILL_TEST = (
    _REPO_ROOT
    / ".claude"
    / "skills"
    / "pr-comment-responder"
    / "tests"
    / "test_cluster_threads.py"
)

spec = importlib.util.spec_from_file_location("pr_comment_responder_cluster_tests", _SKILL_TEST)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

for name, value in vars(module).items():
    if name.startswith("Test") or name.startswith("test_"):
        globals()[name] = value
