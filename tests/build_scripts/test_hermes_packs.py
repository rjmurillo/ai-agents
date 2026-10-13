"""Tests for hermes_packs.py and its wiring (ADR-115 Decision 6).

Fixture tests build a tiny repository under ``tmp_path``. The conformance tests
at the bottom read the real repository: the committed ``src/hermes/`` tree must
equal what the generator renders from ``templates/platforms/hermes.yaml``, and
the per-pack lib copy must equal the committed ``src/claude/lib/`` tree.
"""

from __future__ import annotations

import json
import os
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

import generate_skills  # noqa: E402
import hermes_pack_checks as checks  # noqa: E402
import hermes_pack_config as cfg  # noqa: E402
import hermes_packs  # noqa: E402
import lib_render  # noqa: E402
import validate_templates_schema as schema  # noqa: E402
from frontmatter_key_drop import drop_keys_from_skill_md  # noqa: E402
from test_hermes_pack_checks import make_config, make_stanza, write_skill  # noqa: E402

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
HERMES_YAML = _REPO_ROOT / "templates" / "platforms" / "hermes.yaml"
NESTED_FRONTMATTER = (
    "---\nname: alpha\ndescription: d\nmodel: haiku\nmetadata:\n  domains:\n    - x\n---\nBody\n"
)


def make_repo(tmp_path: Path) -> Path:
    """A repository with skills alpha, beta, gamma, delta and a minimal lib source."""
    skills = tmp_path / "src" / "claude" / "skills"
    write_skill(skills, "alpha", {"scripts/run.py": "print('a')\n", "references/r.md": "r\n"})
    (skills / "alpha" / "SKILL.md").write_text(NESTED_FRONTMATTER, encoding="utf-8")
    write_skill(skills, "beta")
    write_skill(skills, "gamma")
    write_skill(skills, "delta")
    pkg = tmp_path / "scripts" / "hook_utilities"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "from scripts.hook_utilities.util import x\n", encoding="utf-8"
    )
    (pkg / "util.py").write_text("x = 1\n", encoding="utf-8")
    (pkg / "bootstrap.py").write_text("B = 1\n", encoding="utf-8")
    for name in ("github_core", "ai_review_common"):
        (tmp_path / "scripts" / name).mkdir()
        (tmp_path / "scripts" / name / "__init__.py").write_text("", encoding="utf-8")
    return tmp_path


# --- drop_keys_from_skill_md ---------------------------------------------------


def test_drop_keys_removes_nested_metadata_and_keeps_the_body() -> None:
    out = drop_keys_from_skill_md(NESTED_FRONTMATTER, frozenset({"metadata", "model"}))

    assert out == "---\nname: alpha\ndescription: d\n---\nBody\n"


def test_drop_keys_with_no_keys_is_identity() -> None:
    assert drop_keys_from_skill_md(NESTED_FRONTMATTER, frozenset()) == NESTED_FRONTMATTER


def test_drop_keys_rejects_a_file_without_frontmatter() -> None:
    with pytest.raises(ValueError, match="no fenced frontmatter"):
        drop_keys_from_skill_md("# Title\n", frozenset({"metadata"}))


# --- build_pack ------------------------------------------------------------------


def test_build_pack_lays_out_manifest_skills_and_lib(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = make_config()
    lib = lib_render.render_lib_files(repo)

    files = hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, lib)

    assert "plugin.json" in files
    assert "skills/alpha/scripts/run.py" in files
    assert "skills/alpha/references/r.md" in files
    assert "skills/beta/SKILL.md" in files
    assert "lib/hook_utilities/util.py" in files
    assert "lib/bootstrap.py" in files
    assert not any(rel.startswith("skills/gamma") for rel in files)


def test_build_pack_applies_the_frontmatter_drop_to_skill_md_only(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = make_config(frontmatterDrop=["metadata", "model"])

    files = hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, {})

    assert files["skills/alpha/SKILL.md"].data == b"---\nname: alpha\ndescription: d\n---\nBody\n"
    assert files["skills/alpha/scripts/run.py"].data == b"print('a')\n"


def test_build_pack_manifest_has_no_version(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = make_config()

    files = hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, {})
    manifest = json.loads(files["plugin.json"].data)

    assert manifest["$schema"] == cfg.PLUGIN_SCHEMA_URL
    assert manifest["name"] == "project-toolkit-one"
    assert manifest["description"] == "First pack."
    assert "version" not in manifest


def test_build_pack_keeps_the_execute_bit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    script = repo / "src/claude/skills/alpha/scripts/run.py"
    script.chmod(0o755)
    config = make_config()

    files = hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, {})

    assert files["skills/alpha/scripts/run.py"].mode == 0o755
    assert files["skills/beta/SKILL.md"].mode == 0o644


def test_build_pack_fails_loud_on_a_skill_md_without_frontmatter(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "src/claude/skills/beta/SKILL.md").write_text("# no frontmatter\n", encoding="utf-8")
    config = make_config()

    with pytest.raises(cfg.HermesPackError, match="beta/SKILL.md"):
        hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, {})


# --- plan_tree -------------------------------------------------------------------


def test_plan_tree_includes_every_pack_and_the_index(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    tree = hermes_packs.plan_tree(repo, make_config())

    assert "README.md" in tree
    assert "project-toolkit-one/plugin.json" in tree
    assert "project-toolkit-two/skills/gamma/SKILL.md" in tree
    assert "project-toolkit-two/lib/bootstrap.py" in tree
    assert not any("/skills/delta/" in rel for rel in tree)


def test_plan_tree_writes_one_lib_copy_per_pack(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    tree = hermes_packs.plan_tree(repo, make_config())

    for pack_dir in ("project-toolkit-one", "project-toolkit-two"):
        assert tree[f"{pack_dir}/lib/hook_utilities/util.py"].data == b"x = 1\n"
        assert tree[f"{pack_dir}/lib/hook_utilities/__init__.py"].data == (b"from .util import x\n")


def test_plan_tree_fails_when_a_skill_is_unassigned(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_skill(repo / "src/claude/skills", "newcomer")

    with pytest.raises(cfg.HermesPackError, match="newcomer"):
        hermes_packs.plan_tree(repo, make_config())


def test_plan_tree_fails_when_a_pack_exceeds_the_file_budget(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    with pytest.raises(cfg.HermesPackError, match="packMaxFiles is 5"):
        hermes_packs.plan_tree(repo, make_config(packMaxFiles=5))


def test_plan_tree_counts_lib_against_the_budget(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    lib = lib_render.render_lib_files(repo)
    config = make_config()
    biggest = max(
        len(hermes_packs.build_pack(repo / "src/claude/skills", pack, config, lib))
        for pack in config.packs
    )

    assert hermes_packs.plan_tree(repo, make_config(packMaxFiles=biggest))
    with pytest.raises(cfg.HermesPackError):
        hermes_packs.plan_tree(repo, make_config(packMaxFiles=biggest - 1))


def test_plan_tree_fails_when_a_file_exceeds_one_megabyte(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    big = repo / "src/claude/skills/gamma/references/big.md"
    big.parent.mkdir(parents=True)
    big.write_bytes(b"x" * (cfg.HERMES_MAX_FILE_BYTES + 1))

    with pytest.raises(cfg.HermesPackError, match="big.md"):
        hermes_packs.plan_tree(repo, make_config())


def test_plan_tree_fails_when_a_skill_refers_across_packs(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "src/claude/skills/alpha/references/r.md").write_text(
        "see skills/gamma/scripts/x.py\n", encoding="utf-8"
    )

    with pytest.raises(cfg.HermesPackError, match="refers to 'gamma'"):
        hermes_packs.plan_tree(repo, make_config())


def test_plan_tree_fails_when_a_skill_refers_to_an_excluded_skill(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "src/claude/skills/beta/SKILL.md").write_text(
        "---\nname: beta\n---\nUse ../delta/references/x.md\n", encoding="utf-8"
    )

    with pytest.raises(cfg.HermesPackError, match="excluded skill 'delta'"):
        hermes_packs.plan_tree(repo, make_config())


def test_plan_tree_reports_a_missing_lib_source(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "scripts" / "hook_utilities" / "bootstrap.py").unlink()

    with pytest.raises(cfg.HermesPackError, match="bootstrap.py"):
        hermes_packs.plan_tree(repo, make_config())


# --- render_index ----------------------------------------------------------------


def test_index_lists_packs_skills_and_excluded_reasons() -> None:
    text = hermes_packs.render_index(make_config()).decode("utf-8")

    assert "## project-toolkit-one" in text
    assert "- `alpha`" in text and "- `gamma`" in text
    assert "- `delta`: plugin_guard returns dangerous." in text


def test_index_says_so_when_nothing_is_excluded() -> None:
    config = make_config(excluded={})

    assert "No skill is excluded." in hermes_packs.render_index(config).decode("utf-8")


def test_index_has_no_dash_characters_or_generated_banner() -> None:
    text = hermes_packs.render_index(make_config()).decode("utf-8")

    assert EM_DASH not in text and EN_DASH not in text
    assert "generated" not in text.lower() and "do not edit" not in text.lower()


# --- apply_tree and generate_hermes_packs -----------------------------------------


def test_generate_writes_the_tree_then_check_finds_no_drift(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stanza = make_stanza()

    assert hermes_packs.generate_hermes_packs(stanza, repo) == 0
    assert (repo / "src/hermes/project-toolkit-one/plugin.json").is_file()
    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 0


def test_check_reports_a_hand_edit_without_writing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stanza = make_stanza()
    hermes_packs.generate_hermes_packs(stanza, repo)
    edited = repo / "src/hermes/project-toolkit-one/skills/beta/SKILL.md"
    edited.write_text("hand edit\n", encoding="utf-8")

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1
    assert edited.read_text(encoding="utf-8") == "hand edit\n"


def test_generate_repairs_a_hand_edit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stanza = make_stanza()
    hermes_packs.generate_hermes_packs(stanza, repo)
    edited = repo / "src/hermes/project-toolkit-one/skills/beta/SKILL.md"
    edited.write_text("hand edit\n", encoding="utf-8")

    assert hermes_packs.generate_hermes_packs(stanza, repo) == 0
    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 0


def test_check_reports_and_generate_removes_a_stale_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stanza = make_stanza()
    hermes_packs.generate_hermes_packs(stanza, repo)
    stale = repo / "src/hermes/project-toolkit-one/skills/old/SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("x", encoding="utf-8")

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1
    assert stale.exists()
    assert hermes_packs.generate_hermes_packs(stanza, repo) == 0
    assert not stale.exists()
    assert not stale.parent.exists()


def test_generate_removes_a_retired_pack_directory(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    hermes_packs.generate_hermes_packs(make_stanza(), repo)
    only_one = make_stanza(
        packs={"one": {"description": "First pack.", "skills": ["alpha", "beta", "gamma"]}}
    )

    assert hermes_packs.generate_hermes_packs(only_one, repo) == 0
    assert not (repo / "src/hermes/project-toolkit-two").exists()


def test_check_reports_a_missing_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stanza = make_stanza()
    hermes_packs.generate_hermes_packs(stanza, repo)
    (repo / "src/hermes/README.md").unlink()

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1


def test_check_reports_a_lost_execute_bit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "src/claude/skills/alpha/scripts/run.py").chmod(0o755)
    stanza = make_stanza()
    hermes_packs.generate_hermes_packs(stanza, repo)
    target = repo / "src/hermes/project-toolkit-one/skills/alpha/scripts/run.py"
    assert target.stat().st_mode & stat.S_IXUSR
    target.chmod(0o644)

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1


def test_generate_replaces_a_symlink_instead_of_writing_through_it(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stanza = make_stanza()
    hermes_packs.generate_hermes_packs(stanza, repo)
    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")
    readme = repo / "src/hermes/README.md"
    readme.unlink()
    readme.symlink_to(outside)

    assert hermes_packs.generate_hermes_packs(stanza, repo) == 0
    assert not readme.is_symlink()
    assert outside.read_text(encoding="utf-8") == "keep"


def test_what_if_writes_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    assert hermes_packs.generate_hermes_packs(make_stanza(), repo, what_if=True) == 0
    assert not (repo / "src" / "hermes").exists()


def test_a_failed_rule_writes_nothing_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    write_skill(repo / "src/claude/skills", "newcomer")

    code = hermes_packs.generate_hermes_packs(make_stanza(), repo)

    assert code == 2
    assert "newcomer" in capsys.readouterr().err
    assert not (repo / "src" / "hermes").exists()


def test_a_malformed_stanza_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = hermes_packs.generate_hermes_packs(make_stanza(packMaxFiles=999), make_repo(tmp_path))

    assert code == 2
    assert "packMaxFiles" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["/abs/out", "../escape"])
def test_an_output_dir_outside_the_repo_is_refused(tmp_path: Path, bad: str) -> None:
    assert hermes_packs.generate_hermes_packs(make_stanza(outputDir=bad), make_repo(tmp_path)) == 2


def test_an_unwritable_output_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path)
    (repo / "src").mkdir(exist_ok=True)
    blocker = repo / "src" / "hermes"
    blocker.write_text("a file where the directory should be", encoding="utf-8")

    assert hermes_packs.generate_hermes_packs(make_stanza(), repo) == 1
    assert "cannot write" in capsys.readouterr().err


# --- wiring: generate_skills and the schema gate -------------------------------------


def write_config(repo: Path, stanza: dict[str, object]) -> Path:
    path = repo / "hermes.yaml"
    path.write_text(
        yaml.safe_dump(
            {"schemaVersion": "1.0", "provider": "hermes", "artifacts": {"skills": stanza}}
        ),
        encoding="utf-8",
    )
    return path


def test_generate_skills_dispatches_the_hermes_packs_mode(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "templates" / "skills").mkdir(parents=True)
    config_path = write_config(repo, make_stanza())

    code = generate_skills.generate_skills(config_path, repo)

    assert code == 0
    assert (repo / "src/hermes/project-toolkit-one/plugin.json").is_file()


def test_generate_skills_still_rejects_an_unknown_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    config_path = write_config(repo, make_stanza(mode="rsync"))

    assert generate_skills.generate_skills(config_path, repo) == 2
    assert "hermes-packs" in capsys.readouterr().err


def test_schema_accepts_the_committed_hermes_config() -> None:
    errors, is_config_error = schema.validate_file(HERMES_YAML)

    assert errors == []
    assert is_config_error is False


def test_schema_rejects_pack_keys_on_the_directory_copy_mode() -> None:
    doc = {
        "schemaVersion": "1.0",
        "provider": "x",
        "artifacts": {
            "skills": {"sourceDir": "a", "outputDir": "b", "mode": "directory-copy", "packs": {}}
        },
    }

    errors, _ = schema.validate_yaml_doc(doc)

    assert any("need `mode: hermes-packs`" in e for e in errors)


def test_schema_rejects_an_unknown_skills_mode() -> None:
    doc = {
        "schemaVersion": "1.0",
        "provider": "x",
        "artifacts": {"skills": {"sourceDir": "a", "outputDir": "b", "mode": "symlink"}},
    }

    errors, _ = schema.validate_yaml_doc(doc)

    assert any("mode" in e and "symlink" in e for e in errors)


def test_schema_rejects_a_bad_pack_table_with_the_parser_message() -> None:
    doc = {
        "schemaVersion": "1.0",
        "provider": "x",
        "artifacts": {"skills": make_stanza(packMaxFiles=500)},
    }

    errors, _ = schema.validate_yaml_doc(doc)

    assert any("packMaxFiles" in e for e in errors)


def test_schema_rejects_a_pack_table_missing_its_commit() -> None:
    stanza = make_stanza()
    del stanza["hermesCommit"]
    doc = {"schemaVersion": "1.0", "provider": "x", "artifacts": {"skills": stanza}}

    errors, _ = schema.validate_yaml_doc(doc)

    assert any("hermesCommit" in e for e in errors)


def test_the_agents_generator_skips_a_config_with_no_agent_output() -> None:
    sys.path.insert(0, str(_REPO_ROOT / "build"))
    import generate_agents

    assert generate_agents._declares_agent_output({"provider": "hermes"}) is False
    assert generate_agents._declares_agent_output({"provider": "x", "legacy": {}}) is True
    assert generate_agents._declares_agent_output({"__agents_stanza__": {}}) is True
    assert generate_agents._declares_agent_output({"outputDir": "src/x"}) is True


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
    assert os.path.isfile(HERMES_YAML)
