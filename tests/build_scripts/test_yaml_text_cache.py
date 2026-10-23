"""Tests for build/scripts/yaml_text_cache.py and its three callers (issue #6734).

The cache is keyed by YAML text, so it must change no verdict: a file rewritten
between two reads must be re-parsed, a parse error must surface every time with
the same message, and the repo-wide classification must match an uncached parse.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import frontmatter_key_drop  # noqa: E402
import rule_distribution  # noqa: E402
import skill_distribution  # noqa: E402
import yaml_text_cache  # noqa: E402

LOCAL = "---\nname: x\nmetadata:\n  distribution: repo-local\n---\n\nbody\n"
SHIPPED = "---\nname: x\nmetadata:\n  capability:\n    kind: y\n---\n\nbody\n"


@pytest.fixture(autouse=True)
def _fresh_cache():
    yaml_text_cache._parse.cache_clear()
    yield
    yaml_text_cache._parse.cache_clear()


def test_hit_returns_what_a_fresh_parse_returns() -> None:
    text = "a: 1\nb:\n  - x\n  - y\n"
    first = yaml_text_cache.load_yaml_text(text)
    second = yaml_text_cache.load_yaml_text(text)
    assert first == second == yaml.safe_load(text)
    info = yaml_text_cache._parse.cache_info()
    assert (info.hits, info.misses) == (1, 1)


def test_mutating_a_result_does_not_change_the_next_result() -> None:
    text = "a:\n  - 1\n"
    first = yaml_text_cache.load_yaml_text(text)
    assert isinstance(first, dict)
    first["a"].append(2)
    first["b"] = 3
    assert yaml_text_cache.load_yaml_text(text) == {"a": [1]}


def test_distinct_texts_are_parsed_separately() -> None:
    assert yaml_text_cache.load_yaml_text("a: 1\n") == {"a": 1}
    assert yaml_text_cache.load_yaml_text("a: 2\n") == {"a": 2}
    assert yaml_text_cache._parse.cache_info().misses == 2


def test_parse_error_raises_every_time_with_the_same_message() -> None:
    bad = "a: [unclosed\n"
    with pytest.raises(yaml.YAMLError) as first:
        yaml_text_cache.load_yaml_text(bad)
    with pytest.raises(yaml.YAMLError) as second:
        yaml_text_cache.load_yaml_text(bad)
    with pytest.raises(yaml.YAMLError) as direct:
        yaml.safe_load(bad)
    assert str(first.value) == str(second.value) == str(direct.value)
    info = yaml_text_cache._parse.cache_info()
    assert (info.hits, info.currsize) == (0, 0)


def test_is_repo_local_follows_a_file_rewritten_at_the_same_path(tmp_path: Path) -> None:
    """A path-keyed cache would return the first verdict twice; a text key must not."""
    skill_dir = tmp_path / ".claude" / "skills" / "x"
    skill_dir.mkdir(parents=True)
    skill = skill_dir / "SKILL.md"
    skill.write_text(SHIPPED, encoding="utf-8")
    assert skill_distribution.is_repo_local(tmp_path, "x") is False
    skill.write_text(LOCAL, encoding="utf-8")
    assert skill_distribution.is_repo_local(tmp_path, "x") is True
    skill.write_text(SHIPPED, encoding="utf-8")
    assert skill_distribution.is_repo_local(tmp_path, "x") is False


def test_bad_distribution_value_still_raises_on_repeat(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".claude" / "skills" / "x"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: x\nmetadata:\n  distribution: bogus\n---\nbody\n", encoding="utf-8"
    )
    for _ in range(2):
        with pytest.raises(skill_distribution.SkillDistributionError, match="bogus"):
            skill_distribution.is_repo_local(tmp_path, "x")


def test_unparseable_frontmatter_still_raises_on_repeat(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".claude" / "skills" / "x"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: [oops\n---\nbody\n", encoding="utf-8")
    messages = []
    for _ in range(2):
        with pytest.raises(skill_distribution.SkillDistributionError) as err:
            skill_distribution.is_repo_local(tmp_path, "x")
        messages.append(str(err.value))
    assert messages[0] == messages[1]
    assert "unparseable frontmatter" in messages[0]


def test_scope_globs_follow_changed_rule_text() -> None:
    internal = "---\npaths: ['.claude/**']\n---\n# R\n"
    shipped = "---\npaths: ['**']\n---\n# R\n"
    assert rule_distribution.is_repo_only(internal) is True
    assert rule_distribution.is_repo_only(shipped) is False
    assert rule_distribution.is_repo_only(internal) is True


def test_key_drop_guard_sees_each_distinct_frontmatter() -> None:
    """The same dropped key set on two different sources must each be checked."""
    one = "---\nname: a\nmodel: opus\nx: 1\n---\n"
    two = "---\nname: a\nmodel: opus\nx: 2\n---\n"
    for source, kept in ((one, "x: 1"), (two, "x: 2"), (one, "x: 1")):
        result = frontmatter_key_drop.drop_frontmatter_keys(source, frozenset({"model"}))
        assert kept in result
        assert "model" not in result


def test_key_drop_guard_still_rejects_a_cut_that_changes_other_keys() -> None:
    before = "---\nname: a\nmodel: opus\n---\n"
    broken = "---\nname: b\n---\n"
    for _ in range(2):
        with pytest.raises(ValueError, match="changed other SKILL.md frontmatter keys"):
            frontmatter_key_drop._check_only_keys_dropped(before, broken, frozenset({"model"}))


def test_repo_classification_matches_an_uncached_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every real skill and rule classifies the same with and without the cache."""
    cached_skills = skill_distribution.repo_local_names(_REPO_ROOT)
    cached_rules = rule_distribution.repo_only_rule_names(_REPO_ROOT)
    monkeypatch.setattr(skill_distribution, "load_yaml_text", yaml.safe_load)
    monkeypatch.setattr(rule_distribution, "load_yaml_text", yaml.safe_load)
    assert skill_distribution.repo_local_names(_REPO_ROOT) == cached_skills
    assert rule_distribution.repo_only_rule_names(_REPO_ROOT) == cached_rules
    assert cached_skills
    assert cached_rules
