"""Tests for hermes_pack_config.py and hermes_pack_checks.py (ADR-115 Decision 6).

Each rule the Hermes pack build enforces has a positive case (a valid table
passes) and a negative case (the violation names the offending skill). The
build-fails-when list in ADR-115 Decision 6 maps to these tests:

- a shipped skill in no pack and not excluded, or in two: ``check_assignment``
- a pack over the file, byte, or per-file cap: ``check_pack_limits``
- a skill that refers to a skill in another pack or an excluded one:
  ``check_references``
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

import hermes_pack_checks as checks  # noqa: E402
import hermes_pack_config as cfg  # noqa: E402
from _hermes_pack_helpers import make_config, make_stanza, write_skill  # noqa: E402

# --- parse_stanza ------------------------------------------------------------


def test_parse_stanza_accepts_a_valid_table() -> None:
    config = make_config()

    assert [p.dir_name for p in config.packs] == ["project-toolkit-one", "project-toolkit-two"]
    assert config.packs[0].skills == ("alpha", "beta")
    assert config.excluded == {"delta": "plugin_guard returns dangerous."}
    assert config.frontmatter_drop == frozenset({"metadata"})
    assert config.pack_max_files == 380


def test_parse_stanza_allows_a_missing_excluded_table() -> None:
    stanza = make_stanza()
    del stanza["excluded"]

    assert cfg.parse_stanza(stanza).excluded == {}


@pytest.mark.parametrize(
    ("override", "needle"),
    [
        ({"packMaxFiles": 401}, "between 1 and 400"),
        ({"packMaxFiles": 0}, "between 1 and 400"),
        ({"packMaxFiles": True}, "must be an integer"),
        ({"packMaxFiles": "380"}, "must be an integer"),
        ({"hermesCommit": "main"}, "40-character"),
        ({"hermesCommit": ""}, "non-empty string"),
        ({"sourceDir": ""}, "sourceDir"),
        ({"frontmatterDrop": "metadata"}, "frontmatterDrop"),
        ({"packs": {}}, "non-empty mapping"),
        ({"packs": []}, "non-empty mapping"),
        ({"excluded": ["delta"]}, "mapping of skill name to reason"),
        ({"excluded": {"delta": "  "}}, "needs a non-empty reason"),
    ],
)
def test_parse_stanza_rejects_a_bad_value(override: dict[str, object], needle: str) -> None:
    with pytest.raises(cfg.HermesPackError) as raised:
        cfg.parse_stanza(make_stanza(**override))

    assert any(needle in problem for problem in raised.value.problems), raised.value.problems


@pytest.mark.parametrize(
    "body",
    [
        {"description": "d"},
        {"description": "d", "skills": [], "extra": 1},
        {"description": "", "skills": ["a"]},
        {"description": "x" * 1025, "skills": ["a"]},
        {"description": "d", "skills": []},
        {"description": "d", "skills": ["a", 3]},
        ["a"],
    ],
)
def test_parse_stanza_rejects_a_malformed_pack(body: object) -> None:
    with pytest.raises(cfg.HermesPackError):
        cfg.parse_stanza(make_stanza(packs={"one": body}))


@pytest.mark.parametrize("key", ["Bad", "has space", "double--hyphen", "-lead", "x" * 60, ""])
def test_parse_stanza_rejects_a_pack_key_that_breaks_the_hermes_name_rule(key: str) -> None:
    with pytest.raises(cfg.HermesPackError):
        cfg.parse_stanza(make_stanza(packs={key: {"description": "d", "skills": ["a"]}}))


def test_parse_stanza_reports_every_problem_at_once() -> None:
    with pytest.raises(cfg.HermesPackError) as raised:
        cfg.parse_stanza(make_stanza(packMaxFiles=999, hermesCommit="nope"))

    assert len(raised.value.problems) == 2


# --- check_assignment --------------------------------------------------------


def test_assignment_passes_when_every_skill_is_placed_once() -> None:
    assert checks.check_assignment(["alpha", "beta", "gamma", "delta"], make_config()) == []


def test_assignment_names_a_shipped_skill_in_no_pack() -> None:
    problems = checks.check_assignment(
        ["alpha", "beta", "gamma", "delta", "new-skill"], make_config()
    )

    assert problems == ["shipped skill 'new-skill' is in no pack and not in `excluded`"]


def test_assignment_names_a_skill_in_two_packs() -> None:
    config = make_config(
        packs={
            "one": {"description": "d", "skills": ["alpha", "beta"]},
            "two": {"description": "d", "skills": ["beta", "gamma"]},
        }
    )

    problems = checks.check_assignment(["alpha", "beta", "gamma", "delta"], config)

    assert problems == ["skill 'beta' is in two packs: 'one' and 'two'"]


def test_assignment_names_a_skill_listed_twice_in_one_pack() -> None:
    config = make_config(packs={"one": {"description": "d", "skills": ["alpha", "alpha"]}})

    problems = checks.check_assignment(["alpha", "delta"], config)

    assert any("alpha" in p and "two packs" in p for p in problems)


def test_assignment_names_a_skill_both_packed_and_excluded() -> None:
    config = make_config(excluded={"alpha": "dangerous"})

    problems = checks.check_assignment(["alpha", "beta", "gamma"], config)

    assert "skill 'alpha' is in pack 'one' and in `excluded`" in problems


def test_assignment_names_a_stale_entry() -> None:
    problems = checks.check_assignment(["alpha", "beta", "gamma"], make_config())

    assert any("'delta'" in p and "no shipped skill" in p for p in problems)


# --- references --------------------------------------------------------------


def test_find_references_reads_both_path_forms(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha", {"scripts/run.py": "# see skills/beta/scripts/x.py\n"})
    write_skill(tmp_path, "beta", {"references/doc.md": "[doc](../../gamma/references/y.md)\n"})
    write_skill(tmp_path, "gamma")

    refs = checks.find_references(tmp_path, ["alpha", "beta", "gamma"])

    assert set(refs["alpha"]) == {"beta"}
    assert set(refs["beta"]) == {"gamma"}
    assert "gamma" not in refs
    assert refs["alpha"]["beta"] == "scripts/run.py: skills/beta/scripts"


def test_find_references_ignores_self_unknown_and_bare_names(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        "alpha",
        {
            "SKILL.md": (
                "---\nname: alpha\n---\n"
                "own: skills/alpha/scripts/a.py\n"
                "unknown: skills/ghost/scripts/a.py\n"
                "bare: beta/scripts/a.py\n"
                "prefixed: my-skills/beta/scripts/a.py\n"
            )
        },
    )
    write_skill(tmp_path, "beta")

    assert checks.find_references(tmp_path, ["alpha", "beta"]) == {}


def test_find_references_reads_a_relative_link_to_a_skill_named_folder_as_a_reference(
    tmp_path: Path,
) -> None:
    # Conservative on purpose: a link into a repository folder that shares a skill's
    # name (here `build`) fails the build, and the author rewords the link.
    write_skill(tmp_path, "alpha", {"notes.md": "[x](../../build/scripts/x.py)"})
    write_skill(tmp_path, "build")

    assert set(checks.find_references(tmp_path, ["alpha", "build"])["alpha"]) == {"build"}


def test_find_references_requires_a_known_subfolder(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha", {"notes.md": "skills/beta/other/x and skills/beta/scripts"})
    write_skill(tmp_path, "beta")

    assert checks.find_references(tmp_path, ["alpha", "beta"]) == {
        "alpha": {"beta": "notes.md: skills/beta/scripts"}
    }


def test_find_references_skips_binary_files(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_skill(tmp_path, "beta")
    (tmp_path / "alpha" / "blob.bin").write_bytes(b"\xff\xfe skills/beta/scripts/x")

    assert checks.find_references(tmp_path, ["alpha", "beta"]) == {}


def test_skill_files_refuses_a_symlink(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "alpha" / "link.txt").symlink_to(outside)

    with pytest.raises(cfg.HermesPackError, match="symlink"):
        checks.skill_files(tmp_path / "alpha")


def test_skill_files_skips_bytecode(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha", {"scripts/__pycache__/m.pyc": "x", "scripts/m.py": "y"})

    names = [p.name for p in checks.skill_files(tmp_path / "alpha")]

    assert names == ["SKILL.md", "m.py"]


def test_discover_skills_lists_only_folders_with_a_skill_md(tmp_path: Path) -> None:
    write_skill(tmp_path, "beta")
    write_skill(tmp_path, "alpha")
    (tmp_path / "not-a-skill").mkdir()
    (tmp_path / "stray.md").write_text("x", encoding="utf-8")

    assert checks.discover_skills(tmp_path) == ["alpha", "beta"]


def test_discover_skills_fails_on_a_missing_source_dir(tmp_path: Path) -> None:
    with pytest.raises(cfg.HermesPackError, match="not found"):
        checks.discover_skills(tmp_path / "missing")


def test_exclusion_closure_follows_chains() -> None:
    refs = {"b": {"a": "x"}, "c": {"b": "x"}, "d": {"z": "x"}}

    assert checks.exclusion_closure(refs, {"a"}) == {"a", "b", "c"}


def test_exclusion_closure_with_no_seeds_is_empty() -> None:
    assert checks.exclusion_closure({"b": {"a": "x"}}, set()) == set()


def test_check_references_passes_inside_one_pack() -> None:
    refs = {"alpha": {"beta": "f: skills/beta/scripts"}}

    assert checks.check_references(make_config(), refs) == []


def test_check_references_fails_across_packs() -> None:
    refs = {"alpha": {"gamma": "f: skills/gamma/scripts"}}

    problems = checks.check_references(make_config(), refs)

    assert len(problems) == 1
    assert "'alpha' (pack 'one') refers to 'gamma' (pack 'two')" in problems[0]


def test_check_references_fails_on_an_excluded_target() -> None:
    refs = {"alpha": {"delta": "f: skills/delta/scripts"}}

    problems = checks.check_references(make_config(), refs)

    assert "refers to excluded skill 'delta'" in problems[0]
    assert any("closure also needs: alpha" in p for p in problems)


def test_check_references_ignores_references_made_by_excluded_skills() -> None:
    config = make_config(excluded={"delta": "dangerous", "eps": "refers to delta"})
    refs = {"eps": {"delta": "f: skills/delta/scripts"}}

    assert checks.check_references(config, refs) == []


# --- check_pack_limits -------------------------------------------------------


def pack_files(count: int, size: int = 10) -> dict[str, checks.PackFile]:
    return {f"f{i}.txt": checks.PackFile(b"x" * size, 0o644) for i in range(count)}


def test_limits_accept_a_pack_at_the_file_budget() -> None:
    assert checks.check_pack_limits("p", pack_files(380), make_config()) == []


def test_limits_reject_one_file_over_the_budget() -> None:
    problems = checks.check_pack_limits("p", pack_files(381), make_config())

    assert len(problems) == 1
    assert "381 files" in problems[0]
    assert "packMaxFiles is 380" in problems[0]


def test_limits_honor_a_smaller_configured_budget() -> None:
    problems = checks.check_pack_limits("p", pack_files(11), make_config(packMaxFiles=10))

    assert "packMaxFiles is 10" in problems[0]


def test_limits_reject_a_pack_over_ten_megabytes() -> None:
    files = pack_files(11, size=cfg.HERMES_MAX_FILE_BYTES)

    problems = checks.check_pack_limits("p", files, make_config())

    assert any("bytes; Hermes refuses more than 10485760" in p for p in problems)


def test_limits_accept_a_file_at_one_megabyte() -> None:
    files = {"big.txt": checks.PackFile(b"x" * cfg.HERMES_MAX_FILE_BYTES, 0o644)}

    assert checks.check_pack_limits("p", files, make_config()) == []


def test_limits_reject_a_file_over_one_megabyte() -> None:
    files = {"big.txt": checks.PackFile(b"x" * (cfg.HERMES_MAX_FILE_BYTES + 1), 0o644)}

    problems = checks.check_pack_limits("p", files, make_config())

    assert problems == [
        f"p/big.txt is {cfg.HERMES_MAX_FILE_BYTES + 1} bytes; "
        f"Hermes refuses a file over {cfg.HERMES_MAX_FILE_BYTES}"
    ]
