"""`_mirror_source` maps each generated mirror path back to its canonical source.

The mapping keys the generated-file exemption on a real source rather than on
the output prefix alone. Refs #4671.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "validation"))

from git_hook_policy import (
    _COPILOT_SKILL_EXCLUDES,
    _mirror_source,
)


class TestMirrorSourceMapping:
    """The output-to-source rewrite must be exact, including the suffix."""

    @pytest.mark.parametrize(
        ("output", "expected"),
        [
            (
                ".github/instructions/universal.instructions.md",
                ".claude/rules/universal.md",
            ),
            (
                "src/copilot-cli/instructions/voice.instructions.md",
                ".claude/rules/voice.md",
            ),
            (
                "src/copilot-cli/lib/ai_review_common/retry.py",
                ".claude/lib/ai_review_common/retry.py",
            ),
            ("src/copilot-cli/skills/review/SKILL.md", ".claude/skills/review/SKILL.md"),
            ("src/claude/skills/review/SKILL.md", ".claude/skills/review/SKILL.md"),
            (
                "src/claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py",
                ".claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py",
            ),
            ("src/copilot-cli/hooks/hooks.json", ".claude/hooks/hooks.json"),
            (
                ".github/prompts/pr-quality-gate-security.md",
                ".claude/skills/review/references/security.md",
            ),
        ],
    )
    def test_known_mirrors_resolve_to_their_source(self, output: str, expected: str) -> None:
        assert _mirror_source(output) == expected

    @pytest.mark.parametrize(
        "path",
        [
            ".claude/rules/universal.md",
            ".claude/lib/ai_review_common/retry.py",
            "scripts/ai_review_common/retry.py",
            "tests/test_ai_review.py",
            "docs/README.md",
        ],
    )
    def test_non_mirror_paths_have_no_source(self, path: str) -> None:
        assert _mirror_source(path) is None

    def test_instruction_suffix_must_match(self) -> None:
        """A file under the instructions tree without the suffix is not a mirror."""
        assert _mirror_source(".github/instructions/README.md") is None

    def test_excluded_skill_tree_has_no_source_mapping(self) -> None:
        assert _mirror_source("src/copilot-cli/skills/merge-resolver/SKILL.md") is None

    def test_skill_exclusions_match_platform_config(self) -> None:
        import yaml

        config = yaml.safe_load(
            (_REPO_ROOT / "templates/platforms/copilot-cli.yaml").read_text(encoding="utf-8")
        )
        configured = set(config["artifacts"]["skills"]["excludeFilenames"])
        assert _COPILOT_SKILL_EXCLUDES == configured


class TestMatcherShimSuffixStripping:
    """Issue #4857: matcher-shimmed hook paths must map to their unsuffixed source."""

    def test_sanitized_hex_suffix_stripped_for_hooks(self) -> None:
        """Positive: the reported case from #4857."""
        result = _mirror_source(
            "src/copilot-cli/hooks/PreToolUse/invoke_push_pr_script_identity_guard__Bash_f620ca.py"
        )
        assert result == (".claude/hooks/PreToolUse/invoke_push_pr_script_identity_guard.py")

    def test_bare_hex_suffix_stripped_for_hooks(self) -> None:
        """Edge: a pure-punctuation matcher produces only a hex digest suffix."""
        result = _mirror_source("src/copilot-cli/hooks/PostToolUse/my_hook__a1b2c3.py")
        assert result == ".claude/hooks/PostToolUse/my_hook.py"

    def test_source_with_double_underscore_preserves_stem(self) -> None:
        """Edge: canonical source named foo__bar.py survives suffix stripping."""
        result = _mirror_source("src/copilot-cli/hooks/PreToolUse/foo__bar__Bash_f620ca.py")
        assert result == ".claude/hooks/PreToolUse/foo__bar.py"

    def test_companion_without_suffix_is_unchanged(self) -> None:
        """Negative control: verbatim companions still resolve directly."""
        result = _mirror_source("src/copilot-cli/hooks/PreToolUse/_push_pr_guard_lex.py")
        assert result == ".claude/hooks/PreToolUse/_push_pr_guard_lex.py"

    def test_suffix_stripping_does_not_apply_to_lib(self) -> None:
        """Negative: lib paths with suffix-like names are not stripped."""
        result = _mirror_source("src/copilot-cli/lib/foo__bar_abc123.py")
        assert result == ".claude/lib/foo__bar_abc123.py"

    def test_suffix_stripping_does_not_apply_to_skills(self) -> None:
        """Negative: skills paths with suffix-like names are not stripped."""
        result = _mirror_source("src/copilot-cli/skills/review/scripts/check__Bash_deadbe.py")
        assert result == ".claude/skills/review/scripts/check__Bash_deadbe.py"
