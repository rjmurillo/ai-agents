"""The ratchets' Hermes mirror skip covers every package lib_mirror renders."""

from __future__ import annotations

from build.scripts import lib_mirror
from scripts.ci import hermes_mirror


def test_lib_mirror_packages_match_the_lib_mirror_registry() -> None:
    assert set(hermes_mirror.LIB_MIRROR_PACKAGES) == set(lib_mirror.PACKAGES)
