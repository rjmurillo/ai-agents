"""Acceptance test for issue #4299: Windows CI discovers files via marker.

Adding this file (with pytestmark = pytest.mark.windows_path) and running
pytest -m windows_path must collect it automatically, with no workflow edits.
That is the acceptance criterion: the job is driven by marker, not by a
hardcoded file list.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.windows_path


def test_new_windows_path_file_is_collected_by_marker() -> None:
    """Prove that a new file with the windows_path marker is auto-discovered.

    This test exists to satisfy the acceptance criterion in issue #4299:
    a new Windows-relevant test file must be picked up by the Windows CI job
    without editing pytest.yml.  The CI job runs 'pytest -m windows_path',
    which collects any module that sets pytestmark = pytest.mark.windows_path.
    """
    pass
