from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FORBIDDEN_PATHS = [
    "/" + "tmp" + "/PR-123-BODY.md",
    "/" + "tmp" + "/push.log",
]
_GUIDANCE_FILES = [
    Path(".claude/commands/push-pr.md"),
    Path("src/copilot-cli/skills/push-pr/SKILL.md"),
    Path(".serena/memories/git/git-stale-branch-fails-repo-state-tests.md"),
]


def test_guidance_does_not_reintroduce_fixed_tmp_paths():
    offenders = []
    for relative_path in _GUIDANCE_FILES:
        text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for forbidden_path in _FORBIDDEN_PATHS:
            if forbidden_path in text:
                offenders.append(f"{relative_path}: {forbidden_path}")

    assert offenders == []


def test_guidance_uses_unique_per_run_paths():
    for relative_path in _GUIDANCE_FILES[:-1]:
        text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert any(
            strategy in text
            for strategy in (
                "tempfile.NamedTemporaryFile",
                "tempfile.mktemp",
                "tempfile.mkstemp",
                "tempfile.TemporaryDirectory",
                "new_pr.py\" --prepare-body-file",
            )
        )


def test_push_pr_body_path_is_confined_by_its_tool_allowlist():
    for relative_path in (
        Path(".claude/commands/push-pr.md"),
        Path("src/copilot-cli/skills/push-pr/SKILL.md"),
    ):
        text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert 'new_pr.py" --prepare-body-file' in text
        frontmatter = text.split("---", maxsplit=2)[1]
        assert "Edit(.agents/scratch/pr-body-*.md)" in frontmatter
        assert ", Write" not in frontmatter
        assert "python3 -c" not in text
