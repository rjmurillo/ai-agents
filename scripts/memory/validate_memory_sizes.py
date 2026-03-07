#!/usr/bin/env python3
"""Validate Serena memory file sizes.

Thin entry point that delegates to the memory skill's validator.
Keeps SESSION-PROTOCOL references at the repo level rather than
reaching into skill internals.

Exit codes per ADR-035:
  0 - All files pass validation
  1 - Validation failures or errors
"""

import sys
from pathlib import Path

# Add skill scripts to path for import
_skill_scripts = (
    Path(__file__).resolve().parent.parent.parent
    / ".claude/skills/memory/scripts"
)
sys.path.insert(0, str(_skill_scripts))

from test_memory_size import main  # noqa: E402

if __name__ == "__main__":
    main()
