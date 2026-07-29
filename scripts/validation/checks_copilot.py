#!/usr/bin/env python3
"""Copilot-specific validation wrappers for the pre-PR runner."""
from __future__ import annotations

import sys
from pathlib import Path

from check_copilot_routing_exclusions import validate_copilot_routing_exclusions as _validate_module  # noqa: E402


def validate_copilot_routing_exclusions(repo_root: Path) -> bool:
    try:
        return _validate_module(repo_root)
    except FileNotFoundError:
        print("[WARNING] copilot-cli template not found; skipping Copilot routing exclusion check")
        return True
    except Exception as exc:
        print(f"[ERROR] copilot routing exclusion check failed: {exc}", file=sys.stderr)
        return False
