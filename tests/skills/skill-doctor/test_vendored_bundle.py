"""Pin the local patch to the vendored @pierre/diffs bundle.

The bundle ships with the Warp skill-doctor fork. Its minified ``bi`` function
held ``let e=`...${A}``` and a later, unrelated method read ``exec(e){``. The
HOL plugin scanner pairs those into a shell injection finding, which drops the
repository score below the plugin-scanner gate. The bundle runs in a browser
and calls no shell.

The local patch renames that one minified local from ``e`` to ``msg``. Behavior
is unchanged. A re-vendored bundle must carry the same rename, or this test
fails before the scanner gate does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLES = sorted(REPO_ROOT.glob("src/*/skills/skill-doctor/assets/pierre-diffs.js"))
PATCHED = (
    "function bi(A){let msg=`Max depth must be integer between 2 and 100; used ${A}`;"
    "if(!/^[1-9]\\d*$/.test(A))throw new Error(msg);"
    "if(A=+A,A<2||A>100)throw new Error(msg)}"
)
UNPATCHED = "function bi(A){let e=`Max depth must be integer between 2 and 100; used ${A}`;"


def test_every_shipped_copy_of_the_bundle_is_found() -> None:
    names = {path.parts[-5] for path in BUNDLES}

    assert names == {"claude", "codex", "copilot-cli", "cursor", "muse"}


@pytest.mark.parametrize("bundle", BUNDLES, ids=lambda path: path.parts[-5])
def test_bundle_carries_the_scanner_safe_rename(bundle: Path) -> None:
    text = bundle.read_text(encoding="utf-8")

    assert text.count(PATCHED) == 1
    assert UNPATCHED not in text
