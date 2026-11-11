"""Committed ``src/muse/agents`` files (issue #7226, ADR-115 Decision 8 amendment).

Muse Code starts with an invalid agent definition but the lead cannot spawn it
(https://dev.meta.ai/docs/muse-code/agents). An unrecognized frontmatter key,
a missing description, or a missing prompt makes a definition invalid, so every
shipped file is checked here against the documented shape and against the
generator's own render of its Claude source.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import agent_tree_copy as atc  # noqa: E402

MUSE_AGENTS = REPO_ROOT / "src" / "muse" / "agents"
MUSE_CONFIG = REPO_ROOT / "templates" / "platforms" / "muse.yaml"
ALLOWED_KEYS = {"name", "description"}


def validate_muse_agent(stem: str, text: str, expected: str) -> list[str]:
    """Return every reason ``text`` is not a valid, current Muse Code agent file."""
    try:
        frontmatter, body = atc.parse_agent(text, stem)
    except atc.AgentCopyError as exc:
        return [str(exc)]
    errors: list[str] = []
    extra = sorted(set(frontmatter) - ALLOWED_KEYS)
    if extra:
        errors.append(f"{stem}: unrecognized frontmatter keys {extra}")
    for key in sorted(ALLOWED_KEYS):
        value = frontmatter.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{stem}: `{key}` must be a non-empty string")
    if frontmatter.get("name") != stem:
        errors.append(f"{stem}: name {frontmatter.get('name')!r} differs from the file stem")
    if not body.strip():
        errors.append(f"{stem}: prompt body is empty")
    if text != expected:
        errors.append(f"{stem}: differs from the generator's render of its source")
    return errors


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """Run the real generator for the Muse stanza into a scratch root; return stem -> text."""
    root = tmp_path_factory.mktemp("muse-render")
    (root / "src" / "claude").mkdir(parents=True)
    (root / "src" / "claude" / "agents").symlink_to(REPO_ROOT / "src" / "claude" / "agents")
    config = root / "muse.yaml"
    shutil.copyfile(MUSE_CONFIG, config)
    result = atc.generate_agent_copies(root, config)
    assert result is not None, "templates/platforms/muse.yaml has no artifacts.agents stanza"
    out = root / "src" / "muse" / "agents"
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(out.glob("*.md"))}


def _committed() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(MUSE_AGENTS.glob("*.md"))}


def test_generator_renders_agents(rendered: dict[str, str]) -> None:
    assert len(rendered) >= 20, f"generator rendered only {len(rendered)} agents"


def test_committed_set_equals_generated_set(rendered: dict[str, str]) -> None:
    assert sorted(_committed()) == sorted(rendered)


def test_every_committed_agent_is_valid_and_current(rendered: dict[str, str]) -> None:
    committed = _committed()
    assert committed, "no committed src/muse/agents/*.md"
    failures = [
        error
        for stem, text in committed.items()
        for error in validate_muse_agent(stem, text, rendered.get(stem, ""))
    ]
    assert failures == []


def test_tool_restricted_agents_are_not_shipped() -> None:
    shipped = _committed()
    for source in sorted((REPO_ROOT / "src" / "claude" / "agents").glob("*.md")):
        if source.name in ("AGENTS.md", "CLAUDE.md"):
            continue
        frontmatter, _ = atc.parse_agent(source.read_text(encoding="utf-8"), source.name)
        restricted = atc.declared_tools(frontmatter) is not None
        assert (source.stem in shipped) is not restricted, source.name


# Negative controls: the validator must reject each defect. -----------------------

_GOOD = "---\nname: demo\ndescription: Does demo things\n---\n# Demo\n\nBody.\n"


def test_validator_accepts_a_good_file() -> None:
    assert validate_muse_agent("demo", _GOOD, _GOOD) == []


def test_validator_rejects_an_unrecognized_key() -> None:
    text = _GOOD.replace("---\n# Demo", "readonly: true\n---\n# Demo")
    errors = validate_muse_agent("demo", text, text)
    assert any("unrecognized frontmatter keys ['readonly']" in e for e in errors)


def test_validator_rejects_a_missing_description() -> None:
    text = "---\nname: demo\n---\n# Demo\n\nBody.\n"
    errors = validate_muse_agent("demo", text, text)
    assert any("`description` must be a non-empty string" in e for e in errors)


def test_validator_rejects_an_empty_body() -> None:
    text = "---\nname: demo\ndescription: Does demo things\n---\n\n"
    errors = validate_muse_agent("demo", text, text)
    assert any("prompt body is empty" in e for e in errors)


def test_validator_rejects_a_name_that_differs_from_the_stem() -> None:
    errors = validate_muse_agent("other", _GOOD, _GOOD)
    assert any("differs from the file stem" in e for e in errors)


def test_validator_rejects_text_that_differs_from_the_render() -> None:
    errors = validate_muse_agent("demo", _GOOD, _GOOD + "extra\n")
    assert any("differs from the generator's render" in e for e in errors)


def test_validator_rejects_a_file_with_no_frontmatter() -> None:
    assert validate_muse_agent("demo", "# Demo\n", "# Demo\n")
