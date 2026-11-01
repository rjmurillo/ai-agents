"""The ratchets' Hermes mirror skip covers every package lib_mirror renders."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILD_SCRIPTS = str(_REPO_ROOT / "build" / "scripts")
if _BUILD_SCRIPTS not in sys.path:
    sys.path.insert(0, _BUILD_SCRIPTS)

import lib_mirror  # noqa: E402

from scripts.ci import hermes_mirror  # noqa: E402


def test_lib_mirror_packages_match_the_lib_mirror_registry() -> None:
    assert set(hermes_mirror.LIB_MIRROR_PACKAGES) == set(lib_mirror.PACKAGES)
