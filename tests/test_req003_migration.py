"""Tests for the REQ-003 inline-bootstrap migration script.

Covers the four ``migrate_file`` outcomes plus an idempotency check that
running the migration twice on the same input is a no-op the second time.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    REPO_ROOT / "scripts" / "migrations" / "req003_inline_plugin_root_bootstrap.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "req003_migration_under_test", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def migration_module():
    return _load_migration()


# -------- Source patterns -------------------------------------------------

# Hook with the OLD pattern that the migration matches and rewrites.
OLD_BOOTSTRAP_HOOK = '''#!/usr/bin/env python3
"""A fake hook that uses the pre-REQ-003 setup_hook_lib_path bootstrap."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Bootstrap: find lib directory and set up imports (see bootstrap.py for details)
_p = Path(__file__).resolve().parent
while _p.parent != _p and not (_p / ".claude-plugin" / "plugin.json").is_file():
    _p = _p.parent
sys.path.insert(0, str(_p / "lib"))
from bootstrap import setup_hook_lib_path  # noqa: E402
setup_hook_lib_path(__file__, fail_exit_code=2)

from hook_utilities import get_project_directory  # noqa: E402


def main() -> int:
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


# Hook that already has the new inline pattern.
NEW_BOOTSTRAP_HOOK = '''#!/usr/bin/env python3
"""A fake hook that already uses the post-REQ-003 inline bootstrap."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print("Plugin lib directory not found", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory  # noqa: E402


def main() -> int:
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


# Hook with neither the old nor the new pattern (no bootstrap to migrate).
NO_PATTERN_HOOK = '''#!/usr/bin/env python3
"""A fake hook that does not use any bootstrap pattern."""

from __future__ import annotations

import sys

from hook_utilities import get_project_directory


def main() -> int:
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


# -------- Tests -----------------------------------------------------------


def test_migrate_file_migrates_old_pattern(
    migration_module, tmp_path: Path
) -> None:
    hook_path = tmp_path / "old_hook.py"
    hook_path.write_text(OLD_BOOTSTRAP_HOOK, encoding="utf-8")

    outcome = migration_module.migrate_file(hook_path)

    assert outcome == "migrated"
    new_text = hook_path.read_text(encoding="utf-8")
    # The setup_hook_lib_path call must be gone (the docstring still mentions
    # the name as historical context, so we check the executable portion).
    assert "setup_hook_lib_path(__file__" not in new_text
    assert "from bootstrap import setup_hook_lib_path" not in new_text
    assert 'os.environ.get("CLAUDE_PLUGIN_ROOT")' in new_text
    # Exit code from the OLD_PATTERN's fail_exit_code=2 must be preserved.
    assert "sys.exit(2)" in new_text


def test_migrate_file_already_migrated(migration_module, tmp_path: Path) -> None:
    hook_path = tmp_path / "new_hook.py"
    hook_path.write_text(NEW_BOOTSTRAP_HOOK, encoding="utf-8")
    original = hook_path.read_text(encoding="utf-8")

    outcome = migration_module.migrate_file(hook_path)

    assert outcome == "already-migrated"
    assert hook_path.read_text(encoding="utf-8") == original


def test_migrate_file_skipped_no_pattern(migration_module, tmp_path: Path) -> None:
    hook_path = tmp_path / "no_pattern.py"
    hook_path.write_text(NO_PATTERN_HOOK, encoding="utf-8")
    original = hook_path.read_text(encoding="utf-8")

    outcome = migration_module.migrate_file(hook_path)

    assert outcome == "skipped-no-pattern"
    assert hook_path.read_text(encoding="utf-8") == original


def test_migrate_file_error_on_no_op_substitution(
    migration_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the substitution somehow yields the same text, migrate_file returns
    'error'. We force this by replacing NEW_TEMPLATE with the raw OLD_PATTERN
    string, which makes the rewrite a no-op."""
    hook_path = tmp_path / "old_hook.py"
    hook_path.write_text(OLD_BOOTSTRAP_HOOK, encoding="utf-8")

    # Build a replacement that, after .format(exit_code=...), reproduces the
    # exact pre-substitution text so that new_text == text.
    no_op_template = (
        "# Bootstrap: find lib directory and set up imports (see bootstrap.py for details)\n"
        "_p = Path(__file__).resolve().parent\n"
        "while _p.parent != _p and not (_p / \".claude-plugin\" / \"plugin.json\").is_file():\n"
        "    _p = _p.parent\n"
        "sys.path.insert(0, str(_p / \"lib\"))\n"
        "from bootstrap import setup_hook_lib_path  # noqa: E402\n"
        "setup_hook_lib_path(__file__, fail_exit_code={exit_code})"
    )
    monkeypatch.setattr(migration_module, "NEW_TEMPLATE", no_op_template)

    outcome = migration_module.migrate_file(hook_path)

    assert outcome == "error"


def test_migrate_file_is_idempotent(migration_module, tmp_path: Path) -> None:
    hook_path = tmp_path / "old_hook.py"
    hook_path.write_text(OLD_BOOTSTRAP_HOOK, encoding="utf-8")

    first = migration_module.migrate_file(hook_path)
    after_first = hook_path.read_text(encoding="utf-8")
    second = migration_module.migrate_file(hook_path)
    after_second = hook_path.read_text(encoding="utf-8")

    assert first == "migrated"
    assert second == "already-migrated"
    assert after_first == after_second
