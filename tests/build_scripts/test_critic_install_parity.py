"""Regression test for issue #2641: critic install-copy parity.

ADR-109 B1: SHARED_AGENT groups delegated to build_all.py --check.
This test verifies that all critic member paths exist and find_violations
returns no errors for the critic shared-agent group.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_PATH = str(REPO_ROOT / "build" / "scripts")

sys.path.insert(0, _SCRIPTS_PATH)
try:
    import validate_install_parity as vip
except ImportError as e:
    raise ImportError("Failed to import validate_install_parity from build/scripts") from e
finally:
    if _SCRIPTS_PATH in sys.path:
        sys.path.remove(_SCRIPTS_PATH)


def test_critic_shared_agent_members_exist_and_delegated() -> None:
    """All critic SHARED_AGENT members exist on disk; drift delegated to build_all.py --check."""
    members = vip.group_for_anchor("SHARED_AGENT", "critic").members
    for member_path in members:
        full_path = REPO_ROOT / member_path
        assert full_path.exists(), (
            f"critic SHARED_AGENT member missing: {member_path}"
        )

    violations = vip.find_violations(members, repo_root=REPO_ROOT)
    assert violations == [], (
        f"critic SHARED_AGENT drift delegated to build_all.py --check; "
        f"find_violations returned: {violations}"
    )
