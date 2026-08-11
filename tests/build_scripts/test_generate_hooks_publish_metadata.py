"""Publish-step metadata tests for the Copilot hook generator (issue #4764).

The generator republishes a hook by staging a replacement and swapping it in.
What metadata that swap carries decides whether the interpreter notices the
new bytes, so these tests sit apart from the injection and rollback suites
that exercise the swap's content.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPTS = REPO_ROOT / "build" / "scripts"
if str(BUILD_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(BUILD_SCRIPTS))

from generate_hooks_transaction import HookGenerationTransaction  # noqa: E402


def _published(root: Path, content: str) -> Path:
    """Publish ``content`` to a fresh hook target and return the target."""
    target = root / "PreToolUse" / "owner.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    transaction = HookGenerationTransaction(root)
    staged = transaction.new_stage_path(root)
    staged.write_text(content, encoding="utf-8")
    transaction.publish_many([(staged, target)])
    return target


def test_publish_does_not_restore_the_previous_modification_time(tmp_path: Path) -> None:
    """A rewritten hook must carry a new modification time, or bytecode goes stale.

    CPython invalidates ``__pycache__`` on modification time and size. The
    publish step used to copy the OLD target's stat onto its replacement, so a
    rewrite that also kept the size served the previous bytecode.

    Measured in issue #4764: repinning a SHA-256 constant in a guard module
    changes content without changing size, because the digest is fixed-width
    hex. The Copilot dispatcher imported the stale module and denied a valid
    push-pr invocation while the source on disk was already correct.

    The guard's own entrypoint runs as ``__main__``, which is never cached, so
    nothing in this tree exercised the hazard until the guard grew imported
    sibling modules.
    """
    root = tmp_path / "out"
    root.mkdir()
    target = root / "PreToolUse" / "owner.py"
    target.parent.mkdir(parents=True)
    target.write_text("ORIGINAL", encoding="utf-8")
    stale = 1_600_000_000
    os.utime(target, (stale, stale))

    _published(root, "REPLACED")

    assert target.read_text(encoding="utf-8") == "REPLACED"
    assert target.stat().st_mtime != stale, (
        "republished hook kept the previous modification time; __pycache__ goes stale"
    )


def test_publish_still_carries_the_previous_permission_bits(tmp_path: Path) -> None:
    """Inverse control: dropping the times must not drop the mode.

    The metadata step exists so a republished hook keeps the permissions and
    ownership its install gave it. Only the times were wrong, and a fix that
    threw the mode away with them would break an installed tree.
    """
    root = tmp_path / "out"
    root.mkdir()
    target = root / "PreToolUse" / "owner.py"
    target.parent.mkdir(parents=True)
    target.write_text("ORIGINAL", encoding="utf-8")
    os.chmod(target, 0o640)

    _published(root, "REPLACED")

    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_publish_to_a_new_path_needs_no_previous_metadata(tmp_path: Path) -> None:
    """Edge case: a first publish has no target to read metadata from.

    The metadata step returns early when the target does not exist yet, which
    is every newly added companion module.
    """
    root = tmp_path / "out"
    root.mkdir()

    target = _published(root, "FIRST")

    assert target.read_text(encoding="utf-8") == "FIRST"
