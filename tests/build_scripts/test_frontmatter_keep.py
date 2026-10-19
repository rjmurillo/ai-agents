"""Allow-list cut of SKILL.md frontmatter and the generator path that uses it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import generate_skills  # noqa: E402
from frontmatter_key_drop import keep_frontmatter_keys, keep_skill_frontmatter  # noqa: E402
from skill_support_mirror import GenerateSkillsError  # noqa: E402

KEEP = frozenset({"name", "description", "metadata"})


def _fm(text: str) -> object:
    return yaml.safe_load(text.split("---")[1])


def test_keeps_only_listed_keys() -> None:
    src = "---\nname: a\ndescription: d\nversion: 1.0.0\nlicense: MIT\nmodel: haiku\n---\n"
    assert keep_frontmatter_keys(src, KEEP) == "---\nname: a\ndescription: d\n---\n"


def test_keeps_nested_metadata_block_whole() -> None:
    src = (
        "---\nname: a\nmetadata:\n  routing:\n    role: x\n  tags: [a, b]\n"
        "allowed-tools:\n  - Bash\n  - Read\nversion: 1\n---\n"
    )
    out = keep_frontmatter_keys(src, KEEP)
    assert out == "---\nname: a\nmetadata:\n  routing:\n    role: x\n  tags: [a, b]\n---\n"


def test_drops_a_block_scalar_and_its_continuation_lines() -> None:
    src = "---\nname: a\nargument-hint: >\n  one\n\n  two\ndescription: d\n---\n"
    assert keep_frontmatter_keys(src, KEEP) == "---\nname: a\ndescription: d\n---\n"


def test_top_level_comments_are_cut_so_none_dangle() -> None:
    src = "---\n# about the version\nversion: 1\nname: a\n---\n"
    assert keep_frontmatter_keys(src, KEEP) == "---\nname: a\n---\n"


def test_comment_inside_a_kept_block_survives() -> None:
    src = "---\nmetadata:\n  # note\n  a: 1\n---\n"
    assert keep_frontmatter_keys(src, KEEP) == "---\nmetadata:\n  # note\n  a: 1\n---\n"


def test_quoted_key_is_matched() -> None:
    src = "---\n\"name\": a\n'version': 2\n---\n"
    assert keep_frontmatter_keys(src, KEEP) == '---\n"name": a\n---\n'


def test_absent_listed_key_is_not_invented() -> None:
    assert keep_frontmatter_keys("---\nversion: 1\n---\n", KEEP) == "---\n---\n"


def test_key_prefix_is_not_a_match() -> None:
    src = "---\nname-extra: x\nname: a\n---\n"
    assert keep_frontmatter_keys(src, KEEP) == "---\nname: a\n---\n"


def test_whole_file_body_is_untouched() -> None:
    body = "# Title\n\n```yaml\nversion: 1\n---\nname: x\n```\n"
    content = f"---\nname: a\nversion: 1\n---\n{body}"
    assert keep_skill_frontmatter(content, KEEP) == f"---\nname: a\n---\n{body}"


def test_content_without_frontmatter_is_returned_unchanged() -> None:
    assert keep_skill_frontmatter("# Just a body\n", KEEP) == "# Just a body\n"


def test_crlf_frontmatter_is_cut() -> None:
    out = keep_skill_frontmatter("---\r\nname: a\r\nversion: 1\r\n---\r\nBody\r\n", KEEP)
    assert out == "---\r\nname: a\r\n---\r\nBody\r\n"


def test_guard_raises_when_the_cut_changes_a_kept_value() -> None:
    from frontmatter_key_drop import _check_only_keys_kept

    before = "---\nname: a\nversion: 1\n---\n"
    with pytest.raises(ValueError, match="changed the kept"):
        _check_only_keys_kept(before, "---\nname: b\n---\n", KEEP)


def test_guard_raises_when_the_cut_breaks_yaml() -> None:
    from frontmatter_key_drop import _check_only_keys_kept

    before = "---\nname: a\nversion: 1\n---\n"
    with pytest.raises(ValueError, match="broke SKILL.md frontmatter"):
        _check_only_keys_kept(before, "---\nname: [a\n---\n", KEEP)


def test_guard_skips_frontmatter_that_is_not_a_mapping() -> None:
    from frontmatter_key_drop import _check_only_keys_kept

    _check_only_keys_kept("---\n- a\n- b\n---\n", "---\n---\n", KEEP)


# Generator wiring ------------------------------------------------------------


def _config(tmp_path: Path, keep_yaml: str) -> Path:
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        f"""\
schemaVersion: "1.0"
provider: "test"
artifacts:
  skills:
    sourceDir: "src_skills"
    outputDir: "out_skills"
    mode: "directory-copy"
{keep_yaml}""",
        encoding="utf-8",
    )
    return cfg


def _skill(tmp_path: Path) -> None:
    skill = tmp_path / "src_skills" / "demo"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: d\nversion: 1\nallowed-tools: Bash\n---\n"
        "# Demo\n\nUse `${CLAUDE_PLUGIN_ROOT}/skills/demo/scripts/run.py`. Task tool.\n",
        encoding="utf-8",
    )
    (skill / "scripts" / "run.py").write_text("print('hi')\n", encoding="utf-8")


def test_generator_applies_keep_and_copies_body_and_support_files_verbatim(tmp_path: Path) -> None:
    _skill(tmp_path)
    cfg = _config(tmp_path, "    frontmatterKeep: [name, description]\n")
    assert generate_skills.generate_skills(cfg, tmp_path) == 0
    out = (tmp_path / "out_skills" / "demo" / "SKILL.md").read_text(encoding="utf-8")
    assert out == (
        "---\nname: demo\ndescription: d\n---\n"
        "# Demo\n\nUse `${CLAUDE_PLUGIN_ROOT}/skills/demo/scripts/run.py`. Task tool.\n"
    )
    assert (tmp_path / "out_skills" / "demo" / "scripts" / "run.py").read_text() == "print('hi')\n"


def test_generator_without_keep_copies_skill_md_byte_for_byte(tmp_path: Path) -> None:
    _skill(tmp_path)
    assert generate_skills.generate_skills(_config(tmp_path, ""), tmp_path) == 0
    src = (tmp_path / "src_skills" / "demo" / "SKILL.md").read_bytes()
    assert (tmp_path / "out_skills" / "demo" / "SKILL.md").read_bytes() == src


@pytest.mark.parametrize("value", ["name", "null", "[1]"])
def test_generator_rejects_bad_keep(tmp_path: Path, value: str) -> None:
    _skill(tmp_path)
    cfg = _config(tmp_path, f"    frontmatterKeep: {value}\n")
    assert generate_skills.generate_skills(cfg, tmp_path) == 2
    assert not (tmp_path / "out_skills").exists()


def test_keep_helper_distinguishes_absent_from_empty() -> None:
    assert generate_skills._frontmatter_keep({}) is None
    assert generate_skills._frontmatter_keep({"frontmatterKeep": []}) == frozenset()
    with pytest.raises(GenerateSkillsError):
        generate_skills._frontmatter_keep({"frontmatterKeep": None})


def test_committed_cursor_skills_carry_only_documented_keys() -> None:
    documented = {
        "name",
        "description",
        "paths",
        "disable-model-invocation",
        "icon",
        "color",
        "metadata",
    }
    skills = sorted((REPO_ROOT / "src" / "cursor" / "skills").glob("*/SKILL.md"))
    assert len(skills) == len(list((REPO_ROOT / "src" / "claude" / "skills").glob("*/SKILL.md")))
    for skill in skills:
        keys = set(yaml.safe_load(skill.read_text(encoding="utf-8").split("---")[1]))
        assert keys <= documented, skill
        assert {"name", "description"} <= keys, skill
        assert skill.parent.name == yaml.safe_load(skill.read_text().split("---")[1])["name"]
