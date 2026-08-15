"""Generated mirrors must not consume the atomic-commit budget.

Universal rule 5 exempts hook-generated companions from the five-file limit,
but the counter only knew about episodes, mcp config, the agent catalog, and
the memory index. It did not know about the trees listed in
`.agents/governance/GENERATOR-FILES.md`, so editing one rule under
`.claude/rules/` staged three files and a four-file change became unshippable.

The exemption is deliberately keyed on the canonical source existing rather
than on the output prefix alone. Exempting by prefix would let anything written
into an output tree escape the limit, which is a larger hole than the friction
it removes. Refs #4671.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "validation"))

from git_hook_policy import (
    _COPILOT_SKILL_EXCLUDES,
    MAX_AUTHORED_FILES_PER_COMMIT,
    _is_generated,
    _mirror_source,
)


def _make_repo(tmp_path: Path, sources: tuple[str, ...]) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for rel in sources:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("content\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "--all"], check=True)
    return tmp_path


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
            ("src/copilot-cli/hooks/hooks.json", ".claude/hooks/hooks.json"),
            (
                ".github/prompts/pr-quality-gate-security.md",
                ".claude/skills/review/references/security.md",
            ),
        ],
    )
    def test_known_mirrors_resolve_to_their_source(
        self, output: str, expected: str
    ) -> None:
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
        assert (
            _mirror_source("src/copilot-cli/skills/merge-resolver/SKILL.md")
            is None
        )

    def test_skill_exclusions_match_platform_config(self) -> None:
        import yaml

        config = yaml.safe_load(
            (_REPO_ROOT / "templates/platforms/copilot-cli.yaml").read_text(
                encoding="utf-8"
            )
        )
        configured = set(config["artifacts"]["skills"]["excludeFilenames"])
        assert _COPILOT_SKILL_EXCLUDES == configured


class TestGeneratedExemption:
    """Exemption requires the canonical source to exist, not merely the prefix."""

    def test_mirror_with_a_real_source_is_exempt(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, (".claude/rules/universal.md",))
        assert _is_generated(".github/instructions/universal.instructions.md", root)

    def test_mirror_without_a_source_still_counts(self, tmp_path: Path) -> None:
        """Acceptance criterion 3: a generated-looking path with no canonical
        generator relationship is authored work and must still count."""
        root = _make_repo(tmp_path, ())
        assert not _is_generated("src/copilot-cli/lib/invented.py", root)
        assert not _is_generated(
            ".github/instructions/no_such_rule.instructions.md", root
        )

    def test_canonical_source_is_never_exempt(self, tmp_path: Path) -> None:
        """The source is the authored file. Exempting it would defeat the limit."""
        root = _make_repo(
            tmp_path,
            (".claude/rules/universal.md", ".claude/lib/ai_review_common/retry.py"),
        )
        assert not _is_generated(".claude/rules/universal.md", root)
        assert not _is_generated(".claude/lib/ai_review_common/retry.py", root)

    def test_ordinary_authored_files_are_never_exempt(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, ())
        for path in ("scripts/thing.py", "tests/test_thing.py", "docs/guide.md"):
            assert not _is_generated(path, root), path

    def test_pr_quality_gate_prompt_with_source_is_exempt(
        self, tmp_path: Path
    ) -> None:
        root = _make_repo(
            tmp_path, (".claude/skills/review/references/security.md",)
        )
        assert _is_generated(".github/prompts/pr-quality-gate-security.md", root)

    def test_pr_quality_gate_prompt_without_source_still_counts(
        self, tmp_path: Path
    ) -> None:
        root = _make_repo(tmp_path, ())
        assert not _is_generated(".github/prompts/pr-quality-gate-invented.md", root)
        assert not _is_generated(".github/prompts/security.md", root)

    @pytest.mark.parametrize(
        "path",
        [
            ".github/prompts/pr-quality-gate-.md",
            ".github/prompts/pr-quality-gate-Security.md",
            ".github/prompts/pr-quality-gate-security.txt",
            ".github/prompts/pr-quality-gate-nested/security.md",
        ],
    )
    def test_malformed_prompt_names_still_count(
        self, tmp_path: Path, path: str
    ) -> None:
        root = _make_repo(
            tmp_path, (".claude/skills/review/references/security.md",)
        )
        assert not _is_generated(path, root)

    def test_untracked_prompt_source_still_counts(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, ())
        source = root / ".claude/skills/review/references/security.md"
        source.parent.mkdir(parents=True)
        source.write_text("untracked\n", encoding="utf-8")
        assert not _is_generated(".github/prompts/pr-quality-gate-security.md", root)

    def test_deleted_prompt_source_still_counts(self, tmp_path: Path) -> None:
        root = _make_repo(
            tmp_path, (".claude/skills/review/references/security.md",)
        )
        source = root / ".claude/skills/review/references/security.md"
        source.unlink()
        subprocess.run(["git", "-C", str(root), "add", "-u"], check=True)
        assert not _is_generated(".github/prompts/pr-quality-gate-security.md", root)

    def test_renamed_prompt_source_still_counts(self, tmp_path: Path) -> None:
        root = _make_repo(
            tmp_path, (".claude/skills/review/references/security.md",)
        )
        source = root / ".claude/skills/review/references/security.md"
        source.rename(source.with_name("renamed.md"))
        subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)
        assert not _is_generated(".github/prompts/pr-quality-gate-security.md", root)

    def test_symlink_prompt_source_still_counts(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, ())
        target = root / "real.md"
        target.write_text("content\n", encoding="utf-8")
        source = root / ".claude/skills/review/references/security.md"
        source.parent.mkdir(parents=True)
        source.symlink_to(target)
        subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)
        assert not _is_generated(".github/prompts/pr-quality-gate-security.md", root)

    def test_directory_prompt_source_still_counts(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, ())
        source = root / ".claude/skills/review/references/security.md"
        source.mkdir(parents=True)
        assert not _is_generated(".github/prompts/pr-quality-gate-security.md", root)

    def test_excluded_skill_files_still_count(self, tmp_path: Path) -> None:
        root = _make_repo(
            tmp_path,
            tuple(
                f".claude/skills/merge-resolver/file-{index}.md"
                for index in range(6)
            ),
        )
        outputs = [
            f"src/copilot-cli/skills/merge-resolver/file-{index}.md"
            for index in range(6)
        ]
        assert [path for path in outputs if not _is_generated(path, root)] == outputs

    @pytest.mark.parametrize("excluded", ["AGENTS.md", "CLAUDE.md"])
    def test_excluded_top_level_skill_files_still_count(
        self, tmp_path: Path, excluded: str
    ) -> None:
        root = _make_repo(tmp_path, (f".claude/skills/{excluded}",))
        assert not _is_generated(f"src/copilot-cli/skills/{excluded}", root)


class TestFiveToSixBoundary:
    """The reported issue: four authored files plus two mirrors must commit."""

    def test_four_authored_plus_two_mirrors_is_within_the_limit(
        self, tmp_path: Path
    ) -> None:
        root = _make_repo(tmp_path, (".claude/lib/ai_review_common/retry.py",))
        staged = [
            "scripts/ai_review_common/retry.py",
            "scripts/eval/_eval_api_adapter.py",
            "tests/evals/test_eval_agent_vs_baseline.py",
            "tests/test_ai_review.py",
            ".claude/lib/ai_review_common/retry.py",
            "src/copilot-cli/lib/ai_review_common/retry.py",
        ]
        authored = [p for p in staged if not _is_generated(p, root)]
        # Five authored: the four ordinary files plus .claude/lib, which is the
        # canonical source for the copilot mirror and so is authored here.
        assert len(authored) == 5
        assert len(authored) <= MAX_AUTHORED_FILES_PER_COMMIT

    def test_six_authored_files_still_exceed_the_limit(self, tmp_path: Path) -> None:
        """The inverse control: the exemption must not defeat the limit."""
        root = _make_repo(tmp_path, ())
        staged = [f"scripts/module_{i}.py" for i in range(6)]
        authored = [p for p in staged if not _is_generated(p, root)]
        assert len(authored) == 6
        assert len(authored) > MAX_AUTHORED_FILES_PER_COMMIT


class TestMatcherShimSuffixStripping:
    """Issue #4857: matcher-shimmed hook paths must map to their unsuffixed source."""

    def test_sanitized_hex_suffix_stripped_for_hooks(self) -> None:
        """Positive: the reported case from #4857."""
        result = _mirror_source(
            "src/copilot-cli/hooks/PreToolUse/"
            "invoke_push_pr_script_identity_guard__Bash_f620ca.py"
        )
        assert result == (
            ".claude/hooks/PreToolUse/invoke_push_pr_script_identity_guard.py"
        )

    def test_bare_hex_suffix_stripped_for_hooks(self) -> None:
        """Edge: a pure-punctuation matcher produces only a hex digest suffix."""
        result = _mirror_source(
            "src/copilot-cli/hooks/PostToolUse/my_hook__a1b2c3.py"
        )
        assert result == ".claude/hooks/PostToolUse/my_hook.py"

    def test_source_with_double_underscore_preserves_stem(self) -> None:
        """Edge: canonical source named foo__bar.py survives suffix stripping."""
        result = _mirror_source(
            "src/copilot-cli/hooks/PreToolUse/foo__bar__Bash_f620ca.py"
        )
        assert result == ".claude/hooks/PreToolUse/foo__bar.py"

    def test_companion_without_suffix_is_unchanged(self) -> None:
        """Negative control: verbatim companions still resolve directly."""
        result = _mirror_source(
            "src/copilot-cli/hooks/PreToolUse/_push_pr_guard_lex.py"
        )
        assert result == ".claude/hooks/PreToolUse/_push_pr_guard_lex.py"

    def test_suffix_stripping_does_not_apply_to_lib(self) -> None:
        """Negative: lib paths with suffix-like names are not stripped."""
        result = _mirror_source("src/copilot-cli/lib/foo__bar_abc123.py")
        assert result == ".claude/lib/foo__bar_abc123.py"

    def test_suffix_stripping_does_not_apply_to_skills(self) -> None:
        """Negative: skills paths with suffix-like names are not stripped."""
        result = _mirror_source(
            "src/copilot-cli/skills/review/scripts/check__Bash_deadbe.py"
        )
        assert result == ".claude/skills/review/scripts/check__Bash_deadbe.py"

    def test_shimmed_hook_is_exempt_when_source_staged(
        self, tmp_path: Path
    ) -> None:
        """Integration: the full _is_generated path exempts the shim."""
        source = ".claude/hooks/PreToolUse/invoke_push_pr_script_identity_guard.py"
        root = _make_repo(tmp_path, (source,))
        shim = (
            "src/copilot-cli/hooks/PreToolUse/"
            "invoke_push_pr_script_identity_guard__Bash_f620ca.py"
        )
        assert _is_generated(shim, root) is True

    def test_shimmed_hook_not_exempt_when_source_missing(
        self, tmp_path: Path
    ) -> None:
        """Integration: shim without staged source is NOT exempt."""
        root = _make_repo(tmp_path, ())
        shim = (
            "src/copilot-cli/hooks/PreToolUse/"
            "invoke_push_pr_script_identity_guard__Bash_f620ca.py"
        )
        assert _is_generated(shim, root) is False
