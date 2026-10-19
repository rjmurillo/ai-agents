"""Tests for the control-character branch of ``skill_distribution._yaml_where``.

A bad control character fails in the YAML reader before parsing, so the error
has no line mark. The message names the character offset and the parser's fixed
reason, and never echoes the character or the line around it. Split from
``test_skill_distribution.py`` to keep both files under the 500-line limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT / "build" / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "build" / "scripts"))

import skill_distribution  # noqa: E402


class TestControlCharacterFrontmatter:
    def test_control_character_error_names_the_offset_and_reason(self) -> None:
        text = "---\nname: x\x07\n---\n"

        with pytest.raises(skill_distribution.SkillDistributionError) as caught:
            skill_distribution.distribution_of_text(text, "x.tmpl")

        message = str(caught.value)
        assert message.startswith("x.tmpl: unparseable frontmatter")
        assert "character offset 7" in message
        assert "special characters are not allowed" in message
        assert "\x07" not in message

    def test_control_character_error_does_not_echo_the_surrounding_line(self) -> None:
        secret = "SECRET-LINE-FROM-ANOTHER-FILE"
        text = f"---\nname: {secret}\x00\n---\n"

        with pytest.raises(skill_distribution.SkillDistributionError) as caught:
            skill_distribution.distribution_of_text(text, "x.tmpl")

        assert secret not in str(caught.value)

    def test_control_character_error_is_bounded(self) -> None:
        text = "---\nname: " + "a" * 5000 + "\x07\n---\n"

        with pytest.raises(skill_distribution.SkillDistributionError) as caught:
            skill_distribution.distribution_of_text(text, "x.tmpl")

        assert "character offset 5006" in str(caught.value)
        assert len(str(caught.value)) < 300
