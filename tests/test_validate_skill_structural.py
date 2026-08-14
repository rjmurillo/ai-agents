"""Tests for SkillForge validate-skill.py structural validator.

Covers P0 remediation items from critique review (issue #1380):
- P0-2: Description word count validation
- P0-3: Trigger phrase character validation (CWE-94)
- P0-2 (threshold): Trigger count range alignment (1-5 not 3-5)
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Protocol

import pytest

_scripts_dir = os.path.join(
    os.path.dirname(__file__),
    "..",
    ".claude",
    "skills",
    "SkillForge",
    "scripts",
)

# Import uses hyphenated filename, so use importlib
_spec = importlib.util.spec_from_file_location(
    "validate_skill",
    os.path.join(os.path.abspath(_scripts_dir), "validate-skill.py"),
)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SkillValidator = _mod.SkillValidator


class _ValidatorLike(Protocol):
    """Structural view of SkillValidator used by this test suite.

    The validator is imported via importlib from a hyphenated filename, so its
    static type is ``Any``. Returning this Protocol from ``_make_skill`` keeps
    the test bodies type-checked against a fixed surface instead of ``Any``.
    """

    errors: list[str]

    def load_skill(self) -> bool: ...

    def parse_frontmatter(self) -> bool: ...

    def validate_frontmatter(self) -> None: ...

    def validate_triggers(self) -> None: ...


def _make_skill(tmp_path: Path, content: str) -> _ValidatorLike:
    """Create a skill directory with SKILL.md and return a validator."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    # Change to tmp_path so CWE-22 path check passes
    orig = os.getcwd()
    os.chdir(tmp_path)
    try:
        validator: _ValidatorLike = SkillValidator(str(skill_dir))
    finally:
        os.chdir(orig)
    return validator


# ---------------------------------------------------------------------------
# P0-2: Description word count validation
# ---------------------------------------------------------------------------


class TestDescriptionWordCount:
    """Verify minimum word count check on description field."""

    def test_short_description_fails(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: Too short\n---\n"
            "# Title\n## Triggers\n`one` `two` `three`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_frontmatter()
        assert any("too short" in e.lower() for e in v.errors), (
            f"Expected word count error, got: {v.errors}"
        )

    def test_adequate_description_passes(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\n"
            "description: This is a valid description with enough words\n"
            "---\n# Title\n## Triggers\n`one` `two` `three`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_frontmatter()
        word_errors = [e for e in v.errors if "word" in e.lower()]
        assert not word_errors, f"Unexpected word count error: {word_errors}"

    def test_exactly_five_words_passes(self, tmp_path: Path) -> None:
        content = "---\nname: test-skill\ndescription: One two three four five\n---\n# Title\n"
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_frontmatter()
        word_errors = [e for e in v.errors if "word" in e.lower()]
        assert not word_errors

    def test_four_words_fails(self, tmp_path: Path) -> None:
        content = "---\nname: test-skill\ndescription: One two three four\n---\n# Title\n"
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_frontmatter()
        assert any("4 words" in e for e in v.errors)


# ---------------------------------------------------------------------------
# P0-3: Trigger phrase character validation (CWE-94)
# ---------------------------------------------------------------------------


class TestTriggerCharacterValidation:
    """Verify unsafe characters in trigger phrases are rejected."""

    def test_safe_triggers_pass(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`run tests` `check quality` `validate code`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        char_errors = [e for e in v.errors if "unsafe characters" in e]
        assert not char_errors, f"Unexpected error: {char_errors}"

    def test_injection_backtick_content_rejected(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`safe phrase` `; rm -rf /` `another safe`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        assert any("unsafe characters" in e for e in v.errors), (
            f"Expected unsafe character error, got: {v.errors}"
        )

    def test_shell_metacharacters_rejected(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`run && exploit` `pipe | attack` `$(command)`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        assert any("unsafe characters" in e for e in v.errors)


# ---------------------------------------------------------------------------
# Trigger count threshold alignment (1-5 instead of 3-5)
# ---------------------------------------------------------------------------


class TestTriggerCountThreshold:
    """Verify trigger count accepts 1-5 range per standard alignment."""

    def test_single_trigger_passes(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`single trigger phrase`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        count_errors = [e for e in v.errors if "trigger phrases" in e]
        assert not count_errors, f"Single trigger should pass: {count_errors}"

    def test_two_triggers_pass(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`first trigger` `second trigger`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        count_errors = [e for e in v.errors if "trigger phrases" in e]
        assert not count_errors

    def test_five_triggers_pass(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`a` `b` `c` `d` `e`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        count_errors = [e for e in v.errors if "trigger phrases" in e]
        assert not count_errors

    def test_six_triggers_fail(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`a` `b` `c` `d` `e` `f`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        assert any("1-5" in e for e in v.errors)

    def test_zero_triggers_fail(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\nNo backtick phrases here.\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        assert any("1-5" in e for e in v.errors)


# ---------------------------------------------------------------------------
# size-exception frontmatter property acceptance (skill_size escape hatch)
# ---------------------------------------------------------------------------


class TestSizeExceptionProperty:
    """The `size-exception` escape hatch must pass frontmatter allow-listing.

    The blocking `scripts/validation/skill_size.py` gate requires a top-level
    `size-exception: true` to exempt a >500-line SKILL.md, so the structural
    validator must accept that key. Otherwise the two blocking gates deadlock
    and no oversized skill can be committed.
    """

    def test_size_exception_true_is_allowed(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\n"
            "description: A valid skill declaring a justified size exception\n"
            "size-exception: true\n---\n"
            "# Title\n## Process\nSteps.\n## Verification\n- [ ] a\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_frontmatter()
        unexpected = [e for e in v.errors if "Unexpected frontmatter" in e]
        assert not unexpected, f"size-exception should be allowed, got: {v.errors}"

    def test_unknown_property_still_rejected(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\n"
            "description: A valid skill with an unknown frontmatter property\n"
            "not-a-real-key: true\n---\n"
            "# Title\n## Process\nSteps.\n## Verification\n- [ ] a\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_frontmatter()
        assert any("Unexpected frontmatter" in e for e in v.errors), (
            f"unknown key must still be rejected, got: {v.errors}"
        )


# ---------------------------------------------------------------------------
# Issue #3233: repo-wide latent trigger-phrase detection (decoupled from staging)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _trigger_safety_errors(errors: list[str]) -> list[str]:
    """Filter validator errors down to the trigger-phrase safe-character check.

    Isolating this one check keeps the repo-wide guard scoped to issue #3233 and
    immune to unrelated latent failures (a missing Process section, a bad
    frontmatter field) in other shipped skills.
    """
    return [e for e in errors if "unsafe characters" in e]


def _iter_canonical_skill_dirs() -> list[Path]:
    """Every shipped canonical skill directory (``.claude/skills/*/``).

    SkillValidator._find_skill_md accepts both ``SKILL.md`` and ``skill.md``, and
    the glob is case-sensitive on Linux and macOS, so a lowercase-named skill
    would be silently skipped by an uppercase-only glob. Match both names and
    dedupe by parent directory so the repo-wide claim actually covers every
    shipped skill.
    """
    base = _REPO_ROOT / ".claude" / "skills"
    dirs: set[Path] = set()
    for name in ("SKILL.md", "skill.md"):
        dirs.update(p.parent for p in base.glob(f"*/{name}"))
    return sorted(dirs)


def _scan_skill_dir(skill_dir: Path) -> list[str]:
    """Return offender messages for one skill dir, empty when it is clean.

    The caller must have chdir'd to an ancestor of ``skill_dir`` first, because
    SkillValidator's CWE-22 guard rejects paths outside the current working
    directory. A load failure (unreadable or missing SKILL.md) is reported as an
    offender rather than filtered away, so a file that was never scanned cannot
    let the repo-wide guarantee pass hollow.
    """
    validator: _ValidatorLike = SkillValidator(str(skill_dir))
    if not validator.load_skill():
        return [e for e in validator.errors if "read" in e.lower() or "not found" in e.lower()] or [
            "load_skill() returned False"
        ]
    validator.validate_triggers()
    return _trigger_safety_errors(validator.errors)


class TestTriggerPhraseRepoWideGuard:
    """Issue #3233: surface latent trigger-phrase violations repo-wide.

    The pre-commit hook runs SkillForge validation only on *staged* SKILL.md
    files, so a pre-existing unsafe trigger phrase stays latent until the file
    is next staged for an unrelated reason, then blocks that unrelated commit
    (the same class as the mypy latent-error pattern, #2949). This guard scans
    every shipped skill on every test run, so a violation surfaces as its own
    failure naming the offending file, decoupled from whoever next stages it.
    """

    def test_no_latent_trigger_phrase_violations_repo_wide(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Positive: no shipped skill carries an unsafe trigger phrase today."""
        skill_dirs = _iter_canonical_skill_dirs()
        assert skill_dirs, "No canonical skills found; the glob or path is wrong"
        # monkeypatch.chdir auto-restores cwd on teardown, which is safer than a
        # bare os.chdir under parallel runners (pytest-xdist). The chdir is
        # required by SkillValidator's CWE-22 guard, which only accepts paths
        # under the current working directory.
        monkeypatch.chdir(_REPO_ROOT)
        offenders: dict[str, list[str]] = {}
        for skill_dir in skill_dirs:
            msgs = _scan_skill_dir(skill_dir)
            if msgs:
                offenders[skill_dir.relative_to(_REPO_ROOT).as_posix()] = msgs
        assert not offenders, (
            "Latent SkillForge trigger-phrase violations found repo-wide "
            "(issue #3233). Each file below has an unsafe trigger phrase that "
            "would block the next unrelated commit that stages it:\n"
            + "\n".join(
                f"  {name}: {'; '.join(msgs)}" for name, msgs in offenders.items()
            )
        )

    def test_guard_detects_injected_unsafe_trigger(self, tmp_path: Path) -> None:
        """Negative: the guard's check flags a bracketed trigger phrase.

        Proves the repo-wide assertion is not hollow: the same check it relies
        on catches the exact defect from the #3233 reproduction (a ``[marker]``
        trigger), which the safe_pattern allow-list rejects.
        """
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`what does [skip-drift-check] do` `safe phrase`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.validate_triggers()
        assert _trigger_safety_errors(v.errors), (
            f"Guard failed to flag a bracketed trigger; errors: {v.errors}"
        )

    def test_guard_ignores_other_latent_failures(self, tmp_path: Path) -> None:
        """Edge: a skill invalid for unrelated reasons but with safe triggers is not flagged.

        The guard isolates the trigger-safety concern, so a skill missing its
        Process/Verification sections does not trip the repo-wide trigger-phrase
        guard as long as its trigger phrases use allow-listed characters. This is
        what lets the guard run across every shipped skill without coupling to
        their other latent state.
        """
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`run tests` `check {template}` `ref #123`\n"
            # Deliberately no Process or Verification section.
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.validate_triggers()
        assert not _trigger_safety_errors(v.errors), (
            f"Guard wrongly flagged safe triggers: {v.errors}"
        )

    def test_scan_reports_unreadable_skill(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Edge: a skill dir whose SKILL.md cannot be loaded is reported, not skipped.

        Without this, a file that ``load_skill()`` fails to read would have its
        error filtered out by ``_trigger_safety_errors`` and the repo-wide guard
        would pass while never scanning that skill. ``_scan_skill_dir`` treats the
        load failure as an offender so the "repo-wide scanned" claim stays honest.
        """
        skill_dir = tmp_path / "broken-skill"
        skill_dir.mkdir()
        # No SKILL.md written: _find_skill_md defaults to <dir>/SKILL.md, which
        # does not exist, so load_skill() returns False.
        monkeypatch.chdir(tmp_path)
        msgs = _scan_skill_dir(skill_dir)
        assert msgs, "A skill dir with no readable SKILL.md must be reported as an offender"
        assert any("not found" in m.lower() or "returned False" in m for m in msgs), (
            f"Offender message should name the load failure, got: {msgs}"
        )
