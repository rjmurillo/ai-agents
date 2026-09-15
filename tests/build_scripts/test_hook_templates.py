"""Tests for build/scripts/hook_templates.py.

Module docstring quotes the exit-code table from hook_templates.py:
  0 - no templates found, or every template renders clean (write mode) /
      matches the committed target (validate mode)
  1 - a rendered target drifted from the committed one (validate mode), or
      a NO-REGEN-skipped target
  2 - a discovered name resolves outside the repository, the template or a
      target is a symlink, a JSON-shaped template fails to parse as JSON,
      or templates/hooks/ itself is a symlink or resolves outside the
      repository

Covers positive byte-copy render (scripts, hooks.json at plugin root,
settings.tmpl direct to .claude/settings.json), drift detection, NO-REGEN,
what-if, and the malformed-JSON negative case. Symlink and containment
coverage (ancestor and leaf, source and target) lives in
tests/build_scripts/test_hook_templates_symlink_security.py, split out to
stay under the taste-lint 500-line file-size ceiling (same precedent as
test_rule_templates_symlink_security.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import hook_templates  # noqa: E402


def fake_repo(tmp_path: Path) -> Path:
    """Create a fake repository with git init."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def write_template(root: Path, rel: str, content: bytes, *, mode: int = 0o644) -> Path:
    """Write a hooks-class template file, return its path."""
    path = root / "templates" / "hooks" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(mode)
    return path


def test_positive_script_byte_copies_to_plugin_tree(tmp_path: Path) -> None:
    """Positive: a script template byte-copies to src/claude/hooks/<rel>."""
    root = fake_repo(tmp_path)
    write_template(root, "PreToolUse/guard.py", b"#!/usr/bin/env python3\nprint('ok')\n")

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code == 0
    target = root / "src" / "claude" / "hooks" / "PreToolUse" / "guard.py"
    assert str(target) in result.written
    assert target.read_bytes() == b"#!/usr/bin/env python3\nprint('ok')\n"


def test_positive_executable_bit_preserved(tmp_path: Path) -> None:
    """Positive: a template's executable bit survives the render."""
    root = fake_repo(tmp_path)
    write_template(root, "session-start.sh", b"#!/bin/sh\necho hi\n", mode=0o755)

    hook_templates.compile_all(root, validate=False)

    target = root / "src" / "claude" / "hooks" / "session-start.sh"
    assert target.stat().st_mode & 0o777 == 0o755


def test_positive_hooks_json_renders_at_plugin_root(tmp_path: Path) -> None:
    """Positive: hooks.json renders to src/claude/hooks.json, not under hooks/."""
    root = fake_repo(tmp_path)
    write_template(root, "hooks.json", b'{"hooks": {}, "version": 1}')

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code == 0
    target = root / "src" / "claude" / "hooks.json"
    assert str(target) in result.written
    assert not (root / "src" / "claude" / "hooks" / "hooks.json").exists()


def test_positive_settings_renders_direct_no_plugin_hop(tmp_path: Path) -> None:
    """Positive: settings.tmpl renders straight to .claude/settings.json."""
    root = fake_repo(tmp_path)
    write_template(root, "settings.tmpl", b'{"hooks": {}}')

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code == 0
    target = root / ".claude" / "settings.json"
    assert str(target) in result.written
    assert target.read_bytes() == b'{"hooks": {}}'
    assert not (root / "src" / "claude" / "settings.json").exists()
    assert not (root / "src" / "claude" / "hooks" / "settings.tmpl").exists()


def test_negative_malformed_json_exits_2(tmp_path: Path) -> None:
    """Negative: a malformed hooks.json template exits 2, writes nothing."""
    root = fake_repo(tmp_path)
    write_template(root, "hooks.json", b"{not valid json")

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert result.written == []
    assert not (root / "src" / "claude" / "hooks.json").exists()


def test_negative_malformed_settings_json_exits_2(tmp_path: Path) -> None:
    """Negative: a malformed settings.tmpl exits 2, writes nothing."""
    root = fake_repo(tmp_path)
    write_template(root, "settings.tmpl", b"{not valid json")

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert result.written == []
    assert not (root / ".claude" / "settings.json").exists()


def test_edge_untemplated_script_is_untouched(tmp_path: Path) -> None:
    """Edge: a hook script with no template is absent from discover(), untouched."""
    root = fake_repo(tmp_path)
    write_template(root, "PreToolUse/guard.py", b"print('ok')\n")
    existing = root / "src" / "claude" / "hooks" / "PreToolUse" / "unmanaged.py"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("hand written\n", encoding="utf-8")

    hook_templates.compile_all(root, validate=False)

    assert "PreToolUse/unmanaged.py" not in hook_templates.discover(root)
    assert existing.read_text(encoding="utf-8") == "hand written\n"


def test_drift_detected_without_writing(tmp_path: Path) -> None:
    """Validate mode: a stale target is reported as drift, never overwritten."""
    root = fake_repo(tmp_path)
    write_template(root, "dispatch_groups.json", b'{"groups": {}}')
    target = root / "src" / "claude" / "hooks" / "dispatch_groups.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'{"groups": {"stale": true}}')

    result = hook_templates.compile_all(root, validate=True)

    assert result.exit_code == 1
    assert str(target) in result.drifted
    assert target.read_bytes() == b'{"groups": {"stale": true}}'


def test_what_if_reports_without_writing(tmp_path: Path, capsys) -> None:
    """--what-if reports the write it would make without touching the filesystem."""
    root = fake_repo(tmp_path)
    write_template(root, "PreToolUse/guard.py", b"print('ok')\n")

    result = hook_templates.compile_all(root, validate=False, what_if=True)

    target = root / "src" / "claude" / "hooks" / "PreToolUse" / "guard.py"
    assert result.written == []
    assert not target.exists()
    out = capsys.readouterr().out
    assert "Would write" in out
    assert str(target) in out


def test_no_regen_sentinel_skips_write(tmp_path: Path) -> None:
    """A NO-REGEN sentinel on the target is skipped, never overwritten, exit >= 1."""
    root = fake_repo(tmp_path)
    write_template(root, "PreToolUse/guard.py", b"print('new')\n")
    target = root / "src" / "claude" / "hooks" / "PreToolUse" / "guard.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# NO-REGEN\nprint('hand-maintained')\n", encoding="utf-8")

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code >= 1
    assert str(target) in result.skipped
    assert target.read_text(encoding="utf-8") == "# NO-REGEN\nprint('hand-maintained')\n"


def test_absent_templates_dir_is_not_an_error(tmp_path: Path) -> None:
    """DR5: an absent templates/hooks/ directory yields a clean, empty result."""
    root = fake_repo(tmp_path)

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code == 0
    assert result.written == []


def test_owned_targets_includes_settings(tmp_path: Path) -> None:
    """owned_targets() includes .claude/settings.json when settings.tmpl exists."""
    root = fake_repo(tmp_path)
    write_template(root, "PreToolUse/guard.py", b"print('ok')\n")
    write_template(root, "settings.tmpl", b"{}")

    targets = hook_templates.owned_targets(root)

    assert root / ".claude" / "settings.json" in targets
    assert root / "src" / "claude" / "hooks" / "PreToolUse" / "guard.py" in targets
