"""Cursor and Muse skill copies keep the `version` and `license` keys GP-003 requires.

The generator reads each platform's real `frontmatterKeep` list from
`templates/platforms/<platform>.yaml`. Before ADR-115's 2026-11-15 amendment,
both lists dropped `version` and `license`, so the copies broke the GP-003
text while the Claude copy met it (PR #7391 review thread). The GP-003
scanner only checks `.claude/skills/`, so nothing caught the gap. A skill
may keep `version` under `metadata`, as the agentskills.io spec does, so
Muse keeps `metadata` too. The committed-copy tests check parity with the
Claude source and that every copy carries a version and a license.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import generate_skills  # noqa: E402

PLATFORMS = ("cursor", "muse")
GP003_KEYS = ("version", "license")
# The frontmatter block: from the opening `---` line to the next `---` line.
_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def _frontmatter(text: str) -> dict[str, object]:
    match = _FRONTMATTER.match(text)
    assert match, "no frontmatter block"
    loaded = yaml.safe_load(match.group(1))
    assert isinstance(loaded, dict)
    return loaded


def _gp003_values(fm: dict[str, object]) -> tuple[object, object, object]:
    """Return (top-level version, metadata.version, license); GP-003 accepts either version."""
    metadata = fm.get("metadata")
    nested = metadata.get("version") if isinstance(metadata, dict) else None
    return fm.get("version"), nested, fm.get("license")


def _platform_keep(platform: str) -> list[str]:
    config = yaml.safe_load(
        (REPO_ROOT / "templates" / "platforms" / f"{platform}.yaml").read_text(encoding="utf-8")
    )
    keep = config["artifacts"]["skills"]["frontmatterKeep"]
    assert isinstance(keep, list)
    return keep


def _render(tmp_path: Path, platform: str, skill_md: str) -> dict[str, object]:
    """Render one fixture skill through the generator with the platform's real keep list."""
    source = tmp_path / "src_skills" / "demo"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(skill_md, encoding="utf-8")
    config = {
        "schemaVersion": "1.0",
        "provider": "test",
        "artifacts": {
            "skills": {
                "sourceDir": "src_skills",
                "outputDir": "out_skills",
                "mode": "directory-copy",
                "frontmatterKeep": _platform_keep(platform),
            }
        },
    }
    config_path = tmp_path / "platform.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    assert generate_skills.generate_skills(config_path, tmp_path) == 0

    out = tmp_path / "out_skills" / "demo" / "SKILL.md"
    return _frontmatter(out.read_text(encoding="utf-8"))


@pytest.mark.parametrize("platform", PLATFORMS)
def test_version_and_license_survive_generation(tmp_path: Path, platform: str) -> None:
    skill_md = (
        "---\nname: demo\nversion: 2.3.0\ndescription: d\nlicense: MIT\n"
        "allowed-tools: Bash\nmodel: haiku\n---\n# Demo\n"
    )

    fm = _render(tmp_path, platform, skill_md)

    assert fm["version"] == "2.3.0"
    assert fm["license"] == "MIT"


@pytest.mark.parametrize("platform", PLATFORMS)
def test_undocumented_keys_are_still_dropped(tmp_path: Path, platform: str) -> None:
    skill_md = (
        "---\nname: demo\nversion: 1.0.0\ndescription: d\nlicense: MIT\n"
        "allowed-tools: Bash\nmodel: haiku\nuser-invocable: true\n---\n# Demo\n"
    )

    fm = _render(tmp_path, platform, skill_md)

    assert not {"allowed-tools", "model", "user-invocable"} & fm.keys()


@pytest.mark.parametrize("platform", PLATFORMS)
def test_absent_version_and_license_are_not_invented(tmp_path: Path, platform: str) -> None:
    fm = _render(tmp_path, platform, "---\nname: demo\ndescription: d\n---\n# Demo\n")

    assert not set(GP003_KEYS) & fm.keys()
    assert fm == {"name": "demo", "description": "d"}


@pytest.mark.parametrize("platform", PLATFORMS)
def test_version_nested_under_metadata_survives(tmp_path: Path, platform: str) -> None:
    skill_md = (
        "---\nname: demo\ndescription: d\nlicense: MIT\n"
        "metadata:\n  version: 4.1.0\n  routing:\n    role: front-door\n---\n# Demo\n"
    )

    fm = _render(tmp_path, platform, skill_md)

    assert fm["metadata"] == {"version": "4.1.0", "routing": {"role": "front-door"}}
    assert fm["license"] == "MIT"


@pytest.mark.parametrize("platform", PLATFORMS)
def test_committed_copies_match_claude_version_and_license(platform: str) -> None:
    claude_skills = sorted((REPO_ROOT / "src" / "claude" / "skills").glob("*/SKILL.md"))
    assert claude_skills, "no Claude skills found"

    mismatches = []
    for claude_md in claude_skills:
        copy_md = REPO_ROOT / "src" / platform / "skills" / claude_md.parent.name / "SKILL.md"
        source = _gp003_values(_frontmatter(claude_md.read_text(encoding="utf-8")))
        copy = _gp003_values(_frontmatter(copy_md.read_text(encoding="utf-8")))
        if source != copy:
            mismatches.append(f"{claude_md.parent.name}: claude={source} {platform}={copy}")

    assert mismatches == [], f"checked {len(claude_skills)} skills"


@pytest.mark.parametrize("platform", PLATFORMS)
def test_every_committed_copy_carries_a_version_and_license(platform: str) -> None:
    """Guard the case the parity test cannot: a source that lacks a key."""
    copies = sorted((REPO_ROOT / "src" / platform / "skills").glob("*/SKILL.md"))
    assert copies, f"no {platform} skills found"

    missing = []
    for copy_md in copies:
        top_version, nested_version, license_value = _gp003_values(
            _frontmatter(copy_md.read_text(encoding="utf-8"))
        )
        if (top_version is None and nested_version is None) or license_value is None:
            missing.append(copy_md.parent.name)

    assert missing == [], f"checked {len(copies)} copies"


@pytest.mark.parametrize("platform", PLATFORMS)
def test_committed_copies_carry_only_keep_list_keys(platform: str) -> None:
    keep = set(_platform_keep(platform))
    assert not {"allowed-tools", "model"} & keep, "keep-list must not widen tool or model scope"
    copies = sorted((REPO_ROOT / "src" / platform / "skills").glob("*/SKILL.md"))
    assert copies, f"no {platform} skills found"

    extra = {
        copy_md.parent.name: sorted(set(_frontmatter(copy_md.read_text(encoding="utf-8"))) - keep)
        for copy_md in copies
    }

    assert {name: keys for name, keys in extra.items() if keys} == {}, f"checked {len(copies)}"
