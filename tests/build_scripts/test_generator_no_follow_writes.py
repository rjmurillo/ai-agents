"""Regression tests for issue #5522: generators never write through a redirect.

PR #5343 closed the snapshot and restore halves of CWE-367 in
``build_all.py``. The generators still wrote with ``Path.write_text``,
``shutil.copyfile`` and ``shutil.copy2``, which open the destination and so
follow a symlink raced in after strict snapshot validation. Every site named
in the issue now publishes through ``atomic_write``, which swaps the directory
entry instead of opening it.

Each site test plants a symlink at the destination, runs the real generator
function, then asserts two things: the external target is byte-for-byte
unchanged, and the destination is now a regular file holding the new bytes.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import atomic_write  # noqa: E402
import build_all  # noqa: E402
import generate_agent_catalog  # noqa: E402
import generate_dispatcher  # noqa: E402
import generate_hooks_emit  # noqa: E402
import generate_rules  # noqa: E402
import skill_support_mirror  # noqa: E402
from generate_hooks_transaction import HookGenerationTransaction  # noqa: E402

_EXTERNAL_BYTES = b"external file, must never change\n"
_POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")


def _external(tmp_path: Path) -> Path:
    outside = tmp_path / "outside" / "external.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(_EXTERNAL_BYTES)
    return outside


def _plant_symlink(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")


def _assert_replaced_not_followed(dest: Path, external: Path, expected: bytes | None) -> None:
    assert external.read_bytes() == _EXTERNAL_BYTES, "write followed the redirect"
    assert not dest.is_symlink()
    assert dest.is_file()
    if expected is not None:
        assert dest.read_bytes() == expected


# --- publish_bytes_preserving_mode ----------------------------------------


@_POSIX_ONLY
def test_preserving_mode_keeps_an_existing_executable_bit(tmp_path: Path) -> None:
    dest = tmp_path / "hook.py"
    dest.write_bytes(b"old\n")
    dest.chmod(0o755)

    atomic_write.publish_bytes_preserving_mode(dest, b"new\n")

    assert dest.read_bytes() == b"new\n"
    assert stat.S_IMODE(dest.stat().st_mode) == 0o755


@_POSIX_ONLY
def test_preserving_mode_keeps_a_non_executable_mode(tmp_path: Path) -> None:
    dest = tmp_path / "rule.md"
    dest.write_bytes(b"old\n")
    dest.chmod(0o640)

    atomic_write.publish_bytes_preserving_mode(dest, b"new\n")

    assert stat.S_IMODE(dest.stat().st_mode) == 0o640


@_POSIX_ONLY
def test_preserving_mode_defaults_restrictive_for_a_missing_destination(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "fresh.md"

    atomic_write.publish_bytes_preserving_mode(dest, b"new\n")

    assert dest.read_bytes() == b"new\n"
    assert stat.S_IMODE(dest.stat().st_mode) & 0o077 == 0


@_POSIX_ONLY
def test_preserving_mode_ignores_the_mode_a_symlink_target_carries(
    tmp_path: Path,
) -> None:
    """A planted link must not dictate the replacement's permissions."""
    external = _external(tmp_path)
    external.chmod(0o777)
    dest = tmp_path / "owned" / "file.md"
    _plant_symlink(dest, external)

    atomic_write.publish_bytes_preserving_mode(dest, b"new\n")

    _assert_replaced_not_followed(dest, external, b"new\n")
    assert stat.S_IMODE(dest.stat().st_mode) & 0o077 == 0
    assert stat.S_IMODE(external.stat().st_mode) == 0o777


def test_preserving_mode_replaces_a_dangling_symlink(tmp_path: Path) -> None:
    dest = tmp_path / "owned" / "file.md"
    _plant_symlink(dest, tmp_path / "does-not-exist")

    atomic_write.publish_bytes_preserving_mode(dest, b"new\n")

    assert not dest.is_symlink()
    assert dest.read_bytes() == b"new\n"
    assert not (tmp_path / "does-not-exist").exists()


def test_preserving_mode_leaves_no_temp_file_when_the_swap_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "file.md"
    dest.write_bytes(b"old\n")

    def failing_replace(source: Any, destination: Any) -> None:
        raise OSError("simulated swap failure")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError, match="simulated swap failure"):
        atomic_write.publish_bytes_preserving_mode(dest, b"new\n")

    assert dest.read_bytes() == b"old\n"
    assert [p.name for p in tmp_path.iterdir()] == ["file.md"]


# --- generate_rules ---------------------------------------------------------


def test_generate_rules_write_instruction_does_not_follow_a_symlink(
    tmp_path: Path,
) -> None:
    external = _external(tmp_path)
    target = tmp_path / "instructions" / "rule.instructions.md"
    _plant_symlink(target, external)

    written = generate_rules._write_instruction(
        target, {"applyTo": "**"}, "# Body\n", what_if=False
    )

    assert written is True
    _assert_replaced_not_followed(target, external, b"---\napplyTo: '**'\n---\n# Body\n")


# --- generate_hooks_emit._copy_script ---------------------------------------


def test_copy_script_verbatim_does_not_follow_a_symlink(tmp_path: Path) -> None:
    external = _external(tmp_path)
    source = tmp_path / "src" / "hook.py"
    source.parent.mkdir()
    source.write_bytes(b"print('hook')\n")
    target = tmp_path / "out" / "PreToolUse" / "hook.py"
    _plant_symlink(target, external)

    written, reason = generate_hooks_emit._copy_script(source, target, matcher=None, what_if=False)

    assert (written, reason) == (True, "")
    _assert_replaced_not_followed(target, external, b"print('hook')\n")


def test_copy_script_with_matcher_shim_does_not_follow_a_symlink(
    tmp_path: Path,
) -> None:
    external = _external(tmp_path)
    source = tmp_path / "src" / "hook.py"
    source.parent.mkdir()
    source.write_text("print('hook')\n", encoding="utf-8")
    target = tmp_path / "out" / "PreToolUse" / "hook.py"
    _plant_symlink(target, external)

    written, _ = generate_hooks_emit._copy_script(source, target, matcher="Bash", what_if=False)

    assert written is True
    assert external.read_bytes() == _EXTERNAL_BYTES
    assert not target.is_symlink()
    assert "print('hook')" in target.read_text(encoding="utf-8")


@_POSIX_ONLY
def test_copy_script_keeps_the_executable_bit_of_an_existing_target(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "hook.py"
    source.parent.mkdir()
    source.write_bytes(b"print('new')\n")
    target = tmp_path / "out" / "hook.py"
    target.parent.mkdir()
    target.write_bytes(b"print('old')\n")
    target.chmod(0o755)

    generate_hooks_emit._copy_script(source, target, matcher=None, what_if=False)

    assert target.read_bytes() == b"print('new')\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o755


# --- generate_dispatcher ----------------------------------------------------


def test_write_manifest_does_not_follow_a_symlink(tmp_path: Path) -> None:
    external = _external(tmp_path)
    event_dir = tmp_path / "out" / "PreToolUse"
    _plant_symlink(event_dir / "_manifest.json", external)

    manifest_path = generate_dispatcher.write_manifest(event_dir, "PreToolUse", ["a.py"], None)

    _assert_replaced_not_followed(manifest_path, external, None)
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["shims"] == ["a.py"]


def test_copy_bootstrap_does_not_follow_a_symlink(tmp_path: Path) -> None:
    external = _external(tmp_path)
    event_dir = tmp_path / "out" / "PreToolUse"
    _plant_symlink(event_dir / "_bootstrap.py", external)

    dest = generate_dispatcher._copy_bootstrap(event_dir)

    _assert_replaced_not_followed(
        dest, external, generate_dispatcher._CANONICAL_BOOTSTRAP.read_bytes()
    )


def test_write_entrypoint_does_not_follow_a_symlink(tmp_path: Path) -> None:
    external = _external(tmp_path)
    event_dir = tmp_path / "out" / "PreToolUse"
    _plant_symlink(event_dir / "_dispatch.py", external)

    entry = generate_dispatcher.write_entrypoint(event_dir, "PreToolUse")

    _assert_replaced_not_followed(entry, external, None)
    assert "PreToolUse" in entry.read_text(encoding="utf-8")


# --- skill_support_mirror._copy_skill_tree ----------------------------------


def _skill_source(tmp_path: Path) -> Path:
    source = tmp_path / "src" / "demo"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: demo\n---\n# Demo\n", encoding="utf-8")
    (source / "scripts" / "run.py").write_bytes(b"print('run')\n")
    return source


def test_skill_support_copy_does_not_follow_a_symlink(tmp_path: Path) -> None:
    external = _external(tmp_path)
    source = _skill_source(tmp_path)
    target = tmp_path / "out" / "demo"
    _plant_symlink(target / "scripts" / "run.py", external)

    written, _ = skill_support_mirror._copy_skill_tree(source, target, what_if=False)

    assert written >= 1
    _assert_replaced_not_followed(target / "scripts" / "run.py", external, b"print('run')\n")


@_POSIX_ONLY
def test_skill_support_copy_carries_the_source_mode(tmp_path: Path) -> None:
    source = _skill_source(tmp_path)
    (source / "scripts" / "run.py").chmod(0o755)
    target = tmp_path / "out" / "demo"

    skill_support_mirror._copy_skill_tree(source, target, what_if=False)

    assert stat.S_IMODE((target / "scripts" / "run.py").stat().st_mode) == 0o755


def test_skill_support_translated_skill_md_does_not_follow_a_symlink(
    tmp_path: Path,
) -> None:
    external = _external(tmp_path)
    source = _skill_source(tmp_path)
    target = tmp_path / "out" / "demo"
    _plant_symlink(target / "SKILL.md", external)

    skill_support_mirror._copy_skill_tree(
        source, target, what_if=False, skills_output_dir=tmp_path / "out"
    )

    assert external.read_bytes() == _EXTERNAL_BYTES
    assert not (target / "SKILL.md").is_symlink()
    assert "# Demo" in (target / "SKILL.md").read_text(encoding="utf-8")


# --- build_all.write_audit --------------------------------------------------


def test_write_audit_does_not_follow_a_symlink(tmp_path: Path) -> None:
    external = _external(tmp_path)
    audit_path = tmp_path / "build" / "audit" / "GENERATION-AUDIT.md"
    _plant_symlink(audit_path, external)

    violations = build_all.write_audit(build_all.BuildAudit(started_at=0.0), audit_path, [])

    assert violations == []
    _assert_replaced_not_followed(audit_path, external, None)


# --- generate_agent_catalog.generate ---------------------------------------


def test_agent_catalog_generate_does_not_follow_a_symlink(tmp_path: Path) -> None:
    external = _external(tmp_path)
    templates = tmp_path / "templates" / "agents"
    templates.mkdir(parents=True)
    (templates / "demo.shared.md").write_text(
        "---\ndescription: Demo agent\nrole: executor\n---\nbody\n", encoding="utf-8"
    )
    output = tmp_path / "docs" / "agent-catalog.md"
    _plant_symlink(output, external)

    content = generate_agent_catalog.generate(templates, output)

    _assert_replaced_not_followed(output, external, content.encode("utf-8"))


# --- HookGenerationTransaction backup fallback ------------------------------


def test_backup_copy_fallback_does_not_follow_a_symlink_raced_into_the_backup_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``os.link`` failing sends the backup down the copy path.

    The backup name was just unlinked, so a link planted there in that gap is
    the race. The old ``shutil.copy2`` followed it; the exclusive no-follow
    create refuses it, and the external file keeps its bytes either way.
    """
    external = _external(tmp_path)
    target = tmp_path / "out" / "hooks.json"
    target.parent.mkdir()
    target.write_bytes(b"{}\n")

    def racing_link(source: Any, destination: Any) -> None:
        _plant_symlink(Path(destination), external)
        raise OSError("simulated hard-link failure")

    monkeypatch.setattr(os, "link", racing_link)
    transaction = HookGenerationTransaction(tmp_path / "out" / ".lock-target")
    try:
        with pytest.raises(FileExistsError):
            transaction._backup_target(target)
    finally:
        transaction.commit()

    assert external.read_bytes() == _EXTERNAL_BYTES


@_POSIX_ONLY
def test_backup_copy_fallback_preserves_content_and_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out" / "hook.py"
    target.parent.mkdir()
    target.write_bytes(b"original\n")
    target.chmod(0o755)

    def failing_link(source: Any, destination: Any) -> None:
        raise OSError("simulated hard-link failure")

    monkeypatch.setattr(os, "link", failing_link)
    transaction = HookGenerationTransaction(tmp_path / "out" / ".lock-target")
    try:
        transaction._backup_target(target)
        backup = transaction._backups[target]
        assert backup is not None
        assert backup.read_bytes() == b"original\n"
        assert stat.S_IMODE(backup.stat().st_mode) == 0o755
    finally:
        transaction.commit()
