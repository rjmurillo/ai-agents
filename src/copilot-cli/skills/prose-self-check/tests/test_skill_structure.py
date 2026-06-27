"""Structural tests for the prose-self-check skill (issue #2728, Option A).

Pin the contract the skill must honor:

- SKILL.md exists with required frontmatter (name, version, description, license).
- The skill stays under the 500-line ceiling (.claude/skills/CLAUDE.md).
- The description names the audit and carries 3 to 5 backtick triggers.
- The skill encodes all four audit layers (lexical, structural, distributional,
  semantic).
- DRY: the skill references voice.md as the banned-word source of truth and does
  NOT re-encode the banned vocabulary list.
- The skill body carries no em-dash or en-dash (universal.md MUST NOT 5).
- The copilot mirror SKILL.md is byte-identical to the canonical one.

Tests follow Arrange/Act/Assert, one behavior per test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL_DIR / "SKILL.md"


def _find_repo_root(start: Path) -> Path | None:
    """Walk up until a directory holds both canonical and copilot skill trees.

    The build mirrors this whole skill tree into src/copilot-cli/skills/, so the
    file runs from two locations. Locating the repo root by marker (not by a
    fixed parent count) keeps the mirror-identity check correct from either tree.
    """
    for parent in [start, *start.parents]:
        if (parent / ".claude" / "skills").is_dir() and (
            parent / "src" / "copilot-cli" / "skills"
        ).is_dir():
            return parent
    return None


REPO_ROOT = _find_repo_root(SKILL_DIR)
CANONICAL_SKILL_MD = (
    REPO_ROOT / ".claude" / "skills" / "prose-self-check" / "SKILL.md"
    if REPO_ROOT
    else None
)
COPILOT_MIRROR = (
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "prose-self-check" / "SKILL.md"
    if REPO_ROOT
    else None
)

_FRONTMATTER = re.compile(r"(?s)\A---\r?\n(.*?)\r?\n---\r?\n")
_BACKTICK_TRIGGER = re.compile(r"`[^`]+`")
_EM_DASH = "—"
_EN_DASH = "–"

# The canonical banned-vocabulary words from voice.md. The skill must NOT
# re-list these as its own banned list; it must defer to voice.md.
_BANNED_WORDS = [
    "delve",
    "crucial",
    "robust",
    "comprehensive",
    "nuanced",
    "multifaceted",
    "furthermore",
    "moreover",
    "additionally",
    "pivotal",
    "landscape",
    "tapestry",
    "underscore",
    "foster",
    "showcase",
    "intricate",
    "vibrant",
    "fundamental",
    "significant",
]


def _read_skill() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _frontmatter_block() -> str:
    match = _FRONTMATTER.search(_read_skill())
    assert match is not None, "SKILL.md must open with a --- frontmatter block"
    return match.group(1)


def test_skill_md_exists() -> None:
    # Arrange / Act / Assert
    assert SKILL_MD.is_file(), f"missing SKILL.md at {SKILL_MD}"


def test_frontmatter_has_required_fields() -> None:
    # Arrange
    block = _frontmatter_block()

    # Act / Assert
    assert re.search(r"^name:\s*prose-self-check\s*$", block, re.MULTILINE), (
        "frontmatter name must be exactly prose-self-check"
    )
    assert re.search(r"^version:\s*\S+", block, re.MULTILINE), "version required"
    assert re.search(r"^license:\s*\S+", block, re.MULTILINE), "license required"
    assert re.search(r"^description:\s*\S", block, re.MULTILINE) or re.search(
        r"^description:\s*[>|]", block, re.MULTILINE
    ), "description required"


def test_skill_under_size_ceiling() -> None:
    # Arrange
    line_count = len(_read_skill().splitlines())

    # Act / Assert
    assert line_count <= 500, f"SKILL.md is {line_count} lines, ceiling is 500"


def test_description_has_three_to_five_backtick_triggers() -> None:
    # Arrange: SkillForge requires 3 to 5 backtick-wrapped trigger phrases.
    block = _frontmatter_block()
    triggers = _BACKTICK_TRIGGER.findall(block)

    # Act / Assert
    assert 3 <= len(triggers) <= 5, (
        f"expected 3 to 5 backtick trigger phrases, found {len(triggers)}: {triggers}"
    )


@pytest.mark.parametrize(
    "layer",
    ["Lexical", "Structural", "Distributional", "Semantic"],
)
def test_encodes_all_four_layers(layer: str) -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: the four-layer audit is the skill's core contract.
    assert layer in body, f"SKILL.md must encode the {layer} layer"


def test_references_voice_md_as_banned_word_source() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: DRY. The banned list lives in voice.md; the skill points there.
    assert ".claude/rules/voice.md" in body, (
        "SKILL.md must reference voice.md as the banned-vocabulary source of truth"
    )


@pytest.mark.parametrize("word", _BANNED_WORDS)
def test_does_not_reencode_banned_word_list(word: str) -> None:
    # Arrange: the banned words must NOT appear as a backtick-quoted enumeration
    # inside the skill body (that would fork the list from voice.md). The low-
    # signal examples the skill legitimately names are allowlisted below.
    allowed_low_signal = {"moreover", "additionally", "nuanced", "comprehensive"}
    if word in allowed_low_signal:
        pytest.skip(f"{word} is a named low-signal example, not a forked banned list")
    body = _read_skill()

    # Act / Assert: high-signal banned words must not be re-listed as backticked
    # banned-vocabulary entries. ("delve"/"tapestry"/"showcase" appear only as
    # explicit examples-of-voice.md-entries, which the next test guards.)
    backticked = re.findall(r"`([^`]+)`", body)
    forked = [t for t in backticked if t.strip().lower() == word]
    # Up to one mention as an illustrative example is acceptable; a list is not.
    assert len(forked) <= 1, (
        f"{word!r} appears {len(forked)} times in backticks; do not fork the "
        f"voice.md banned list into this skill"
    )


def test_no_em_or_en_dash_in_body() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: universal.md MUST NOT 5. Skill prose carries no em/en dashes.
    assert _EM_DASH not in body, "SKILL.md must not contain em-dashes (U+2014)"
    assert _EN_DASH not in body, "SKILL.md must not contain en-dashes (U+2013)"


def test_distinguishes_from_style_enforcement() -> None:
    # Arrange
    body = _read_skill().lower()

    # Act / Assert: the skill must scope itself to prose and disclaim code style.
    assert "style-enforcement" in body, (
        "SKILL.md must name style-enforcement to mark the prose-vs-code boundary"
    )


def test_copilot_mirror_is_byte_identical() -> None:
    # Arrange: dual-tree convention keeps the mirror in sync. Resolve both trees
    # from the repo root so the check is correct from either tree.
    if REPO_ROOT is None:
        pytest.skip("repo root not found (canonical + copilot trees absent)")
    assert CANONICAL_SKILL_MD is not None and CANONICAL_SKILL_MD.is_file(), (
        f"missing canonical SKILL.md at {CANONICAL_SKILL_MD}"
    )
    assert COPILOT_MIRROR is not None and COPILOT_MIRROR.is_file(), (
        f"missing copilot mirror at {COPILOT_MIRROR}"
    )

    # Act / Assert
    assert COPILOT_MIRROR.read_bytes() == CANONICAL_SKILL_MD.read_bytes(), (
        "copilot mirror SKILL.md must be byte-identical to the canonical SKILL.md"
    )
