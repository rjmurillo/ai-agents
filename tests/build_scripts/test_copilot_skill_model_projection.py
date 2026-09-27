"""Copilot SKILL.md projection drops skill model pins (issue #5606, ADR-111).

Claude Code honors a skill's `model:` key. Copilot CLI skills have no
per-skill model field, so `templates/platforms/copilot-cli.yaml` lists
`model` and `model-rationale` under `artifacts.skills.frontmatterDrop`, and
the Copilot mirror omits both. The pin is dropped, never resolved to a
versioned id.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import generate_skills  # noqa: E402
from copilot_body_translation import (  # noqa: E402
    drop_frontmatter_keys,
    translate_skill_file,
)

_OUT = Path("/nonexistent/skills")
_KEYS = frozenset({"model", "model-rationale"})
_PINNED_SKILLS = {
    "fix-markdown-fences",
    "metrics",
    "observability",
    "pr-quality-all",
    "security-detection",
    "steering-matcher",
    "stuck-detection",
}


def _translate(src: str) -> str:
    return translate_skill_file(src, _OUT, _KEYS)


def _frontmatter_keys(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text.split("---", 2)[1])
    return set(parsed or {})


# Transform ------------------------------------------------------------------


def test_drops_model_and_rationale() -> None:
    src = (
        "---\nname: x\ndescription: d\nmodel: haiku\n"
        "model-rationale: cost. cheap tier.\nlicense: MIT\n---\n\nBody\n"
    )
    assert _translate(src) == "---\nname: x\ndescription: d\nlicense: MIT\n---\n\nBody\n"


def test_empty_drop_set_keeps_model_keys() -> None:
    src = "---\nname: x\nmodel: haiku\n---\nBody\n"
    assert translate_skill_file(src, _OUT) == src


def test_frontmatter_without_model_keys_is_unchanged() -> None:
    src = "---\nname: x\ndescription: d\n---\n\nBody\n"
    assert _translate(src) == src


def test_drops_folded_rationale_continuation_lines() -> None:
    src = (
        "---\nname: x\nmodel-rationale: >\n  cost. line one\n  line two\n"
        "model: haiku\ndescription: d\n---\nBody\n"
    )
    assert _translate(src) == "---\nname: x\ndescription: d\n---\nBody\n"


def test_block_scalar_with_blank_line_does_not_leak_into_next_key() -> None:
    src = "---\nname: x\nmodel-rationale: |\n  a\n\n  b\nlicense: MIT\n---\nBody\n"
    assert _translate(src) == "---\nname: x\nlicense: MIT\n---\nBody\n"


def test_blank_line_before_next_key_is_kept() -> None:
    src = "---\nmodel: haiku\n\nname: x\n---\nBody\n"
    assert _translate(src) == "---\n\nname: x\n---\nBody\n"


def test_unindented_list_value_is_dropped() -> None:
    src = "---\nname: x\nmodel:\n- haiku\nlicense: MIT\n---\nBody\n"
    assert _translate(src) == "---\nname: x\nlicense: MIT\n---\nBody\n"


@pytest.mark.parametrize("line", ["model : haiku", '"model": haiku', "'model-rationale': c"])
def test_spaced_and_quoted_keys_are_dropped(line: str) -> None:
    src = f"---\nname: x\n{line}\n---\nBody\n"
    assert _translate(src) == "---\nname: x\n---\nBody\n"


def test_model_as_last_frontmatter_key() -> None:
    assert _translate("---\nname: x\nmodel: haiku\n---\nBody\n") == "---\nname: x\n---\nBody\n"


def test_crlf_line_endings() -> None:
    src = "---\r\nname: x\r\nmodel: haiku\r\nlicense: MIT\r\n---\r\nBody\r\n"
    assert _translate(src) == "---\r\nname: x\r\nlicense: MIT\r\n---\r\nBody\r\n"


@pytest.mark.parametrize(
    "line",
    [
        "model_tier: haiku",
        "models: [a]",
        "description: set model: haiku here",
        "metadata:\n  model: haiku",
    ],
)
def test_other_keys_and_nested_model_are_kept(line: str) -> None:
    src = f"---\nname: x\n{line}\n---\nBody\n"
    assert _translate(src) == src


def test_body_model_lines_are_kept() -> None:
    src = "---\nname: x\n---\n\n```yaml\nmodel: haiku\n```\nmodel: prose\n"
    assert _translate(src) == src


def test_no_frontmatter_is_not_treated_as_frontmatter() -> None:
    src = "model: haiku\nBody\n"
    assert _translate(src) == src


def test_cut_that_breaks_other_keys_raises() -> None:
    # A flow mapping whose continuation sits at column 0 is legal YAML, but a
    # line-based cut cannot see it; the equivalence check must refuse.
    with pytest.raises(ValueError, match="frontmatter"):
        drop_frontmatter_keys("---\nmodel: {a: 1,\nb: 2}\nname: x\n---\n", _KEYS)


def test_non_yaml_source_frontmatter_skips_equivalence_check() -> None:
    src = "---\nname: [unclosed\nmodel: haiku\n---\n"
    assert drop_frontmatter_keys(src, _KEYS) == "---\nname: [unclosed\n---\n"


def test_non_mapping_frontmatter_skips_equivalence_check() -> None:
    assert drop_frontmatter_keys("---\n- a\n---\n", _KEYS) == "---\n- a\n---\n"


# Generator config -----------------------------------------------------------


def _config(tmp_path: Path, drop: str, provider: str = "copilot-cli") -> Path:
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        f'schemaVersion: "1.0"\nprovider: "{provider}"\nartifacts:\n  skills:\n'
        f'    sourceDir: "src_skills"\n    outputDir: "out_skills"\n{drop}'
    )
    return cfg


def _skill(tmp_path: Path) -> None:
    skill = tmp_path / "src_skills" / "alpha"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: alpha\nmodel: haiku\n---\nBody\n")


def test_generator_applies_configured_drop(tmp_path: Path) -> None:
    _skill(tmp_path)
    cfg = _config(tmp_path, "    frontmatterDrop: [model]\n")
    assert generate_skills.generate_skills(cfg, tmp_path) == 0
    out = (tmp_path / "out_skills" / "alpha" / "SKILL.md").read_text()
    assert out == "---\nname: alpha\n---\nBody\n"


def test_generator_without_drop_keeps_model(tmp_path: Path) -> None:
    _skill(tmp_path)
    cfg = _config(tmp_path, "")
    assert generate_skills.generate_skills(cfg, tmp_path) == 0
    out = (tmp_path / "out_skills" / "alpha" / "SKILL.md").read_text()
    assert "model: haiku" in out


@pytest.mark.parametrize("drop", ["    frontmatterDrop: model\n", "    frontmatterDrop: [1]\n"])
def test_generator_rejects_malformed_drop(tmp_path: Path, drop: str) -> None:
    _skill(tmp_path)
    assert generate_skills.generate_skills(_config(tmp_path, drop), tmp_path) == 2


# Committed tree -------------------------------------------------------------


def test_copilot_config_declares_the_drop() -> None:
    cfg = yaml.safe_load((REPO_ROOT / "templates/platforms/copilot-cli.yaml").read_text())
    assert set(cfg["artifacts"]["skills"]["frontmatterDrop"]) >= _KEYS


def test_committed_copilot_skill_mirrors_carry_no_model_pin() -> None:
    mirrors = sorted((REPO_ROOT / "src" / "copilot-cli" / "skills").glob("*/SKILL.md"))
    assert mirrors, "no Copilot skill mirrors found"
    offenders = [str(p.relative_to(REPO_ROOT)) for p in mirrors if _frontmatter_keys(p) & _KEYS]
    assert offenders == []


def test_claude_skill_sources_keep_their_haiku_pins() -> None:
    sources = sorted((REPO_ROOT / ".claude" / "skills").glob("*/SKILL.md"))
    pinned = {p.parent.name for p in sources if "model" in _frontmatter_keys(p)}
    assert pinned >= _PINNED_SKILLS
