"""Tests for how the Hermes pack mode plugs into the build (ADR-115 Decision 6).

Covers the ``generate_skills`` mode dispatch, the platform schema gate, and the
agents generator skipping a config that ships no agents.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import generate_skills  # noqa: E402
import validate_templates_schema as schema  # noqa: E402
from _hermes_pack_helpers import (  # noqa: E402
    HERMES_YAML,
    make_repo,
    make_stanza,
    write_config,
)

# --- wiring: generate_skills and the schema gate -------------------------------------


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


def test_the_agents_generator_skips_the_hermes_config(tmp_path: Path) -> None:
    """hermes.yaml has an artifacts mapping with no agents stanza, so no agents ship."""
    import shutil

    sys.path.insert(0, str(_REPO_ROOT / "build"))
    import generate_agents

    stage = tmp_path / "stage"
    (stage / "templates").mkdir(parents=True)
    for name in ("agents", "platforms"):
        shutil.copytree(_REPO_ROOT / "templates" / name, stage / "templates" / name)
    shutil.copy2(_REPO_ROOT / "templates" / "toolsets.yaml", stage / "templates" / "toolsets.yaml")
    assert (stage / "templates" / "platforms" / "hermes.yaml").is_file()

    rc = generate_agents.generate_agents(
        templates_path=stage / "templates", output_root=stage / "src", repo_root=stage
    )

    assert rc == 0
    assert not (stage / "src" / "hermes").exists()
