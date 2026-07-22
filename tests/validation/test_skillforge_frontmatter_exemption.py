"""Tests for the skillforge frontmatter-only exemption (Refs #2840).

SkillForge validation (``validate-skill.py``) checks both the body (Triggers,
Process, Verification, Scripts sections) and the frontmatter (required and
allowed keys). The exemption is deliberately narrow: it skips validation only
when the body text is unchanged (bodies decoded as UTF-8 with
``errors="replace"`` and compared as strings, not raw bytes) AND the sole
changed frontmatter keys are the
ADR-080 model-pin fields (``model``, ``model-rationale``), so a pin migration
is not forced to pay down unrelated pre-existing structural debt while any other
frontmatter change still reaches the validator. These tests pin that behavior:

- positive: only the model pin changes, body unchanged -> exempt (skip);
- negative: body changed; a non-pin field changes; a required field is deleted;
  an unexpected key is added; a pin change is bundled with a non-pin change; a
  new skill (no HEAD); each is not exempt (validate). ``run_skillforge`` also
  invokes the validator and propagates its failure when not exempt;
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
    return f"---\n{frontmatter}---\n{body}".encode()


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


def test_non_pin_field_change_is_not_exempt(monkeypatch, tmp_path):
    # Editing description (a body-independent but validator-checked field) with
    # an unchanged body must still validate: the narrowed exemption only covers
    # the ADR-080 model-pin fields.
    old = _doc("name: example\nmodel: haiku\ndescription: old\n", _BODY)
    new = _doc("name: example\nmodel: haiku\ndescription: new\n", _BODY)
    _patch_blobs(monkeypatch, old, new)
    assert ghp._is_skill_frontmatter_only_change(_SKILL, tmp_path) is False


def test_deleting_required_field_is_not_exempt(monkeypatch, tmp_path):
    # Accidentally dropping name must not slip past validation.
    old = _doc("name: example\nmodel: haiku\ndescription: x\n", _BODY)
    new = _doc("model: haiku\ndescription: x\n", _BODY)
    _patch_blobs(monkeypatch, old, new)
    assert ghp._is_skill_frontmatter_only_change(_SKILL, tmp_path) is False


def test_adding_unexpected_field_is_not_exempt(monkeypatch, tmp_path):
    # Introducing an unexpected key must reach the validator's allowed-key check.
    old = _doc("name: example\nmodel: haiku\ndescription: x\n", _BODY)
    new = _doc("name: example\nmodel: haiku\ndescription: x\nbogus: 1\n", _BODY)
    _patch_blobs(monkeypatch, old, new)
    assert ghp._is_skill_frontmatter_only_change(_SKILL, tmp_path) is False


def test_pin_change_mixed_with_other_field_is_not_exempt(monkeypatch, tmp_path):
    # A model-pin edit bundled with a non-pin change is not exempt: the whole
    # frontmatter change set must be a subset of the model-pin fields.
    old = _doc("name: example\nmodel: claude-sonnet-4-6\ndescription: old\n", _BODY)
    new = _doc("name: example\ndescription: new\n", _BODY)
    _patch_blobs(monkeypatch, old, new)
    assert ghp._is_skill_frontmatter_only_change(_SKILL, tmp_path) is False
