"""The committed Hermes tree against the real repository (ADR-115 Decision 6).

The committed ``src/hermes/`` tree must equal what the generator renders from
``templates/platforms/hermes.yaml``, and the per-pack lib copy must equal the
committed ``src/claude/lib/`` tree. Each rule has a negative control further up
in ``test_hermes_packs.py``.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest
import yaml

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import hermes_pack_checks as checks  # noqa: E402
import hermes_pack_config as cfg  # noqa: E402
import hermes_packs  # noqa: E402
import lib_render  # noqa: E402
from _hermes_pack_helpers import EM_DASH, EN_DASH, HERMES_YAML  # noqa: E402

# --- conformance against the real repository -----------------------------------------


@pytest.fixture(scope="module")
def real_config() -> cfg.HermesConfig:
    data = yaml.safe_load(HERMES_YAML.read_text(encoding="utf-8"))
    return cfg.parse_stanza(data["artifacts"]["skills"])


def test_lib_render_equals_the_committed_claude_lib_tree() -> None:
    rendered = lib_render.render_lib_files(_REPO_ROOT)
    committed_root = _REPO_ROOT / "src" / "claude" / "lib"
    committed = {
        p.relative_to(committed_root).as_posix(): p.read_bytes()
        for p in committed_root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }

    assert rendered == committed


def test_committed_hermes_tree_equals_the_render(real_config: cfg.HermesConfig) -> None:
    tree = hermes_packs.plan_tree(_REPO_ROOT, real_config)
    out = _REPO_ROOT / real_config.output_dir

    on_disk = {
        p.relative_to(out).as_posix()
        for p in out.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }

    assert on_disk == set(tree)
    for rel, packed in tree.items():
        assert (out / rel).read_bytes() == packed.data, rel
        executable = bool((out / rel).stat().st_mode & stat.S_IXUSR)
        assert executable == bool(packed.mode & stat.S_IXUSR), rel


def test_every_shipped_skill_is_packed_or_excluded(real_config: cfg.HermesConfig) -> None:
    shipped = checks.discover_skills(_REPO_ROOT / real_config.source_dir)

    assert checks.check_assignment(shipped, real_config) == []


def test_the_seven_guard_dangerous_skills_are_excluded(real_config: cfg.HermesConfig) -> None:
    dangerous = {
        "adr-review",
        "cva-analysis",
        "memory-maintenance",
        "memory-search",
        "planner",
        "security-scan",
        "stuck-detection",
    }

    assert dangerous <= set(real_config.excluded)


def test_the_exclusion_table_is_closed_over_references(real_config: cfg.HermesConfig) -> None:
    source = _REPO_ROOT / real_config.source_dir
    refs = checks.find_references(source, checks.discover_skills(source))

    assert checks.exclusion_closure(refs, set(real_config.excluded)) == set(real_config.excluded)
    assert checks.check_references(real_config, refs) == []


def test_every_real_pack_fits_the_budget_with_lib(real_config: cfg.HermesConfig) -> None:
    tree = hermes_packs.plan_tree(_REPO_ROOT, real_config)

    for pack in real_config.packs:
        prefix = f"{pack.dir_name}/"
        files = {rel[len(prefix) :]: f for rel, f in tree.items() if rel.startswith(prefix)}
        assert len(files) <= real_config.pack_max_files, pack.key
        assert sum(len(f.data) for f in files.values()) < cfg.HERMES_MAX_PACK_BYTES
        assert sum(1 for rel in files if rel.startswith("lib/")) == len(
            lib_render.render_lib_files(_REPO_ROOT)
        )


def _flat_string_map(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    )


def test_every_packed_skill_md_passes_the_portable_frontmatter_rules(
    real_config: cfg.HermesConfig,
) -> None:
    # citation-freshness: ignore -- upstream hermes-agent file at the commit pinned in hermes.yaml
    # Rules copied from hermes_cli/agent_plugins.py:209-229 at the pinned commit:
    # name equals the folder, description 1..1024 chars, metadata a flat string map,
    # and allowed-tools, license, and compatibility strings.
    out = _REPO_ROOT / real_config.output_dir
    for pack in real_config.packs:
        for skill in pack.skills:
            text = (out / pack.dir_name / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            front = yaml.safe_load(text.split("---\n")[1])
            assert front["name"] == skill
            assert 1 <= len(front["description"]) <= 1024, skill
            assert "metadata" not in front or _flat_string_map(front["metadata"]), skill
            for key in ("allowed-tools", "license", "compatibility"):
                assert key not in front or isinstance(front[key], str), (skill, key)
            assert "model" not in front and "model-rationale" not in front, skill


def test_real_plugin_json_matches_the_pack_table(real_config: cfg.HermesConfig) -> None:
    out = _REPO_ROOT / real_config.output_dir
    for pack in real_config.packs:
        manifest = json.loads((out / pack.dir_name / "plugin.json").read_text(encoding="utf-8"))
        assert manifest["name"] == pack.dir_name
        assert manifest["description"] == pack.description
        assert "version" not in manifest


def test_the_real_index_lists_every_skill_and_every_exclusion(
    real_config: cfg.HermesConfig,
) -> None:
    text = (_REPO_ROOT / real_config.output_dir / "README.md").read_text(encoding="utf-8")

    for pack in real_config.packs:
        for skill in pack.skills:
            assert f"- `{skill}`" in text
    for name, reason in real_config.excluded.items():
        assert f"- `{name}`: {reason}" in text


def test_a_skill_without_a_pack_fails_the_real_config(real_config: cfg.HermesConfig) -> None:
    # Negative control for the two tests above: dropping one packed skill must fail.
    first = real_config.packs[0]
    trimmed = cfg.PackSpec(first.key, first.description, first.skills[1:])
    broken = cfg.HermesConfig(
        source_dir=real_config.source_dir,
        output_dir=real_config.output_dir,
        pack_max_files=real_config.pack_max_files,
        hermes_commit=real_config.hermes_commit,
        frontmatter_drop=real_config.frontmatter_drop,
        packs=(trimmed, *real_config.packs[1:]),
        excluded=real_config.excluded,
    )

    with pytest.raises(cfg.HermesPackError, match=first.skills[0]):
        hermes_packs.plan_tree(_REPO_ROOT, broken)


def test_the_real_tree_has_no_dash_characters() -> None:
    out = _REPO_ROOT / "src" / "hermes"
    for name in (
        "README.md",
        "project-toolkit-delivery/plugin.json",
        "project-toolkit-knowledge/plugin.json",
    ):
        text = (out / name).read_text(encoding="utf-8")
        assert EM_DASH not in text and EN_DASH not in text, name
    assert HERMES_YAML.is_file()
