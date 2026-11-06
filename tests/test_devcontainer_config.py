"""The dev container config and its lock file must agree.

The container references each feature as ``tag@sha256:...`` and the CLI verifies
that digest on every client, so the reference is what enforces integrity. The
committed ``devcontainer-lock.json`` records the same digest. Nothing in CI runs
the CLI, so this test is the only thing that notices when the two drift apart
after a hand edit or a Renovate bump that updates one file and not the other.

A mismatch is not cosmetic: ``devcontainer up --frozen-lockfile`` fails with
"Lockfile does not match." and the contributor cannot build the container.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.hooks.managed_image_marker_parsers import MARKER_NAME, _strip_jsonc

CONTAINER_DIR = Path(__file__).resolve().parents[1] / ".devcontainer"
CONFIG_PATH = CONTAINER_DIR / "devcontainer.json"
LOCK_PATH = CONTAINER_DIR / "devcontainer-lock.json"

_DIGEST = re.compile(r"@sha256:(?P<digest>[0-9a-f]{64})$")


def _config() -> dict:
    """Parse the config with the same JSONC reader the marker test uses.

    A local stripper would be a second, weaker copy of that rule: this file
    carries trailing comments and the marker parser already handles those and
    comments inside string literals.
    """
    return json.loads(_strip_jsonc(CONFIG_PATH.read_text(encoding="utf-8")))


def _lock() -> dict:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def test_config_and_lock_track_the_same_features() -> None:
    """The CLI keys each lock entry by the feature reference as written."""
    assert set(_config()["features"]) == set(_lock()["features"])


def test_every_feature_reference_carries_a_digest() -> None:
    """Integrity must not depend on a contributor passing --frozen-lockfile.

    A tag-only reference is mutable upstream. The digest in the reference is
    what the CLI verifies on every client, including plain `devcontainer up`.
    """
    for reference in _config()["features"]:
        assert _DIGEST.search(reference), f"{reference} carries no @sha256 digest"


def test_each_lock_entry_matches_its_reference_digest() -> None:
    """A digest edited in one file and not the other must fail here."""
    for reference, entry in _lock()["features"].items():
        digest = _DIGEST.search(reference)
        assert digest, f"lock key {reference} carries no digest"
        expected = digest.group("digest")
        assert entry["integrity"] == f"sha256:{expected}", reference
        assert entry["resolved"].endswith(f"@sha256:{expected}"), reference


def test_base_image_is_pinned_by_digest() -> None:
    """A mutable base image tag would defeat the feature pins below it."""
    image = _config()["image"]
    assert _DIGEST.search(image), f"base image {image} is not digest pinned"


def test_config_marks_the_container_as_a_managed_image() -> None:
    """ADR-104 rule 8 needs this marker for hook deadlines to clamp.

    ``tests/hooks/test_managed_image_marker.py`` enforces the same property over
    the tracked file. This asserts it where the container is defined, reading the
    marker name from that module so the two cannot drift.
    """
    assert _config()["containerEnv"][MARKER_NAME] == "1"
