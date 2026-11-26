"""Tests for the Hermes ``excludedFiles`` table in the pack build (issue #7357).

A file named there ships in no pack, the pack count drops by exactly that file,
and an entry that matches nothing fails the build. Parsing and the check itself
are in ``test_hermes_pack_checks.py``.
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

import hermes_pack_config as cfg  # noqa: E402
import hermes_packs  # noqa: E402
from _hermes_pack_helpers import make_config, make_repo  # noqa: E402


def test_build_pack_skips_an_excluded_file_and_keeps_its_siblings(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = make_config(excludedFiles={"alpha/scripts/run.py": "needs a missing skill"})

    files = hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, {})

    assert "skills/alpha/scripts/run.py" not in files
    assert "skills/alpha/references/r.md" in files
    assert "skills/alpha/SKILL.md" in files


def test_plan_tree_drops_one_file_per_excluded_file_from_the_pack_count(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    before = hermes_packs.plan_tree(repo, make_config())
    after = hermes_packs.plan_tree(
        repo, make_config(excludedFiles={"alpha/scripts/run.py": "needs a missing skill"})
    )

    assert set(before) - set(after) == {"project-toolkit-one/skills/alpha/scripts/run.py"}
    assert set(after) - set(before) == set()


def test_plan_tree_fails_when_an_excluded_file_matches_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = make_config(excludedFiles={"alpha/scripts/gone.py": "why"})

    with pytest.raises(cfg.HermesPackError, match="matches no file"):
        hermes_packs.plan_tree(repo, config)


def test_skill_md_drops_a_pointer_line_to_its_own_excluded_file() -> None:
    text = "intro\nRead [r](references/r.md) first.\nkeep me\n"

    out = hermes_packs.drop_excluded_pointer_lines(text, "alpha", ["alpha/references/r.md"])

    assert out == "intro\nkeep me\n"


def test_skill_md_keeps_lines_when_nothing_it_names_is_excluded() -> None:
    text = "intro\nRead [r](references/r.md) first.\n"

    out = hermes_packs.drop_excluded_pointer_lines(text, "alpha", ["alpha/scripts/run.py"])

    assert out == text


def test_skill_md_drops_a_cross_skill_pointer_only_when_it_names_the_owner() -> None:
    text = "Read the `beta` skill's `references/r.md`.\nOur own references/r.md stays.\n"

    out = hermes_packs.drop_excluded_pointer_lines(text, "alpha", ["beta/references/r.md"])

    assert out == "Our own references/r.md stays.\n"


def test_build_pack_strips_the_pointer_to_an_excluded_reference(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    skill_md = repo / "src/claude/skills/alpha/SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8") + "\nRead [r](references/r.md).\n",
        encoding="utf-8",
    )
    config = make_config(excludedFiles={"alpha/references/r.md": "pack cap"})

    files = hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, {})

    assert "skills/alpha/references/r.md" not in files
    assert b"references/r.md" not in files["skills/alpha/SKILL.md"].data


@pytest.mark.parametrize(
    "frontmatter",
    [
        pytest.param(
            "---\nname: alpha\ndescription: Holds references/r.md for authors.\n---\n",
            id="standard-fence",
        ),
        pytest.param(
            "---\nname: alpha\ndescription: |\n  section\n  ---\n  Holds references/r.md.\n---\n",
            id="indented-dashes-in-block-scalar",
        ),
        pytest.param(
            "----\nname: alpha\ndescription: Holds references/r.md.\n----\n",
            id="four-dash-fence",
        ),
    ],
)
def test_skill_md_keeps_frontmatter_that_names_an_excluded_file(frontmatter: str) -> None:
    text = f"{frontmatter}Read [r](references/r.md).\nbody\n"

    out = hermes_packs.drop_excluded_pointer_lines(text, "alpha", ["alpha/references/r.md"])

    assert out == f"{frontmatter}body\n"


def _setup_cross_pack_repo(
    tmp_path: Path, extra_refs: dict[str, str] | None = None
) -> tuple[Path, dict[str, dict[str, object]]]:
    repo = make_repo(tmp_path)
    refs_dir = repo / "src/claude/skills/alpha/references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "rule-cross.md").write_text(
        "See skills/beta/references/guide.md.\n", encoding="utf-8"
    )
    for name, content in (extra_refs or {}).items():
        (refs_dir / name).write_text(content, encoding="utf-8")
    packs: dict[str, dict[str, object]] = {
        "one": {"description": "Pack one.", "skills": ["alpha"]},
        "two": {"description": "Pack two.", "skills": ["beta", "gamma"]},
    }
    return repo, packs


def test_excluded_file_reference_does_not_fail_cross_pack_check(tmp_path: Path) -> None:
    repo, packs = _setup_cross_pack_repo(tmp_path)
    with pytest.raises(cfg.HermesPackError, match="beta"):
        hermes_packs.plan_tree(repo, make_config(packs=packs))

    with_exclusion = make_config(
        packs=packs,
        excludedFiles={"alpha/references/rule-cross.md": "References beta in pack two."},
    )
    tree = hermes_packs.plan_tree(repo, with_exclusion)
    assert "project-toolkit-one/skills/alpha/references/rule-cross.md" not in tree


def test_non_excluded_file_reference_still_fails_when_another_file_is_excluded(
    tmp_path: Path,
) -> None:
    repo, packs = _setup_cross_pack_repo(
        tmp_path, extra_refs={"other.md": "Also uses skills/beta/scripts/run.py.\n"}
    )
    config = make_config(
        packs=packs,
        excludedFiles={"alpha/references/rule-cross.md": "Excluded file."},
    )
    with pytest.raises(cfg.HermesPackError, match=r"other\.md.*beta"):
        hermes_packs.plan_tree(repo, config)
