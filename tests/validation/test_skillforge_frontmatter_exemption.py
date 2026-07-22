"""Tests for the skillforge frontmatter-only exemption (Refs #2840).

SkillForge structural validation inspects a skill's body (Triggers, Process,
Verification, Scripts sections). A frontmatter-only edit (for example the
ADR-080 model-pin migration) leaves the body byte-identical, so the structural
verdict cannot regress. ``_is_skill_frontmatter_only_change`` lets
``run_skillforge`` skip those edits instead of forcing unrelated structural
debt to be paid down. These tests pin that behavior:

- positive: frontmatter changed, body unchanged -> exempt (skip);
- negative: body changed -> not exempt (validate); new skill (no HEAD) ->
  not exempt (validate); and ``run_skillforge`` actually invokes the validator
  and propagates its failure when not exempt;
- edge: a file without frontmatter, and a no-op (identical) blob, are both not
  exempt.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validation import git_hook_policy as ghp  # noqa: E402

_SKILL = ".claude/skills/example/SKILL.md"
_BODY = "## Overview\n\nDo the thing.\n\n## Verification\n\n- [ ] works\n"


def _doc(frontmatter: str, body: str) -> bytes:
    return f"---\n{frontmatter}---\n{body}".encode("utf-8")


def _patch_blobs(
    monkeypatch, old: bytes | None, new: bytes | None
) -> None:
    monkeypatch.setattr(ghp, "_read_head_blob", lambda repo, path: old)
    monkeypatch.setattr(ghp, "_read_index_blob", lambda repo, path: new)


def test_frontmatter_only_change_is_exempt(monkeypatch, tmp_path):
    # A real skill keeps name/description; only the model pin is removed.
    old = _doc("name: example\nmodel: claude-sonnet-4-6\ndescription: x\n", _BODY)
    new = _doc("name: example\ndescription: x\n", _BODY)
    _patch_blobs(monkeypatch, old, new)
    assert ghp._is_skill_frontmatter_only_change(_SKILL, tmp_path) is True


def test_frontmatter_add_field_body_unchanged_is_exempt(monkeypatch, tmp_path):
    old = _doc("model: claude-haiku-4-5\n", _BODY)
    new = _doc("model: haiku\nmodel-rationale: cost.\n", _BODY)
    _patch_blobs(monkeypatch, old, new)
    assert ghp._is_skill_frontmatter_only_change(_SKILL, tmp_path) is True


def test_body_change_is_not_exempt(monkeypatch, tmp_path):
    old = _doc("model: claude-sonnet-4-6\n", _BODY)
    new = _doc("model: claude-sonnet-4-6\n", _BODY + "\nextra paragraph\n")
    _patch_blobs(monkeypatch, old, new)
    assert ghp._is_skill_frontmatter_only_change(_SKILL, tmp_path) is False


def test_new_skill_without_head_is_not_exempt(monkeypatch, tmp_path):
    new = _doc("model: haiku\n", _BODY)
    _patch_blobs(monkeypatch, None, new)
    assert ghp._is_skill_frontmatter_only_change(_SKILL, tmp_path) is False


def test_missing_frontmatter_is_not_exempt(monkeypatch, tmp_path):
    old = b"## Overview\n\nNo frontmatter here.\n"
    new = b"## Overview\n\nNo frontmatter here, edited.\n"
    _patch_blobs(monkeypatch, old, new)
    assert ghp._is_skill_frontmatter_only_change(_SKILL, tmp_path) is False


def test_removing_only_field_leaving_empty_frontmatter_is_not_exempt(
    monkeypatch, tmp_path
):
    # Degenerate: the removed pin was the sole frontmatter field, leaving empty
    # frontmatter. Conservatively validate rather than skip.
    old = _doc("model: claude-sonnet-4-6\n", _BODY)
    new = _doc("", _BODY)
    _patch_blobs(monkeypatch, old, new)
    assert ghp._is_skill_frontmatter_only_change(_SKILL, tmp_path) is False


def test_identical_blob_is_not_exempt(monkeypatch, tmp_path):
    doc = _doc("model: haiku\n", _BODY)
    _patch_blobs(monkeypatch, doc, doc)
    assert ghp._is_skill_frontmatter_only_change(_SKILL, tmp_path) is False


def test_run_skillforge_skips_exempt_paths_without_validating(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def _fake_run_command(cmd, repo_root):
        calls.append(cmd)
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(ghp, "_run_command", _fake_run_command)
    monkeypatch.setattr(ghp, "_print_process_output", lambda result: None)
    monkeypatch.setattr(
        ghp, "_is_skill_frontmatter_only_change", lambda path, repo_root: True
    )
    rc = ghp.run_skillforge([_SKILL], tmp_path)
    assert rc == 0
    assert calls == []  # validator never invoked for exempt paths


def test_run_skillforge_validates_and_propagates_failure_when_not_exempt(
    monkeypatch, tmp_path
):
    calls: list[list[str]] = []

    def _fake_run_command(cmd, repo_root):
        calls.append(cmd)
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(ghp, "_run_command", _fake_run_command)
    monkeypatch.setattr(ghp, "_print_process_output", lambda result: None)
    monkeypatch.setattr(
        ghp, "_is_skill_frontmatter_only_change", lambda path, repo_root: False
    )
    rc = ghp.run_skillforge([_SKILL], tmp_path)
    assert rc == 1
    assert len(calls) == 1  # validator invoked exactly once
    assert calls[0][1].endswith("validate-skill.py")
