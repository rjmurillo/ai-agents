#!/usr/bin/env python3
"""Hook: session_end - Reflection pass after session completion.

Runs a reflection pass on the completed session log:
1. Reinforce memories accessed with successful outcomes.
2. Generate skill candidates from repeated failures (governed, not auto-promoted).
3. Auto-capture novel facts with citations back to this session.
4. Apply confidence decay to accessed but unverified memories.

Usage:
    python3 scripts/hooks/session_end.py <session-log-path>

Exit codes:
    0: Success
    1: Error (invalid arguments, missing file, parse failure)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path for imports
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.memory_enhancement.reflection import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
