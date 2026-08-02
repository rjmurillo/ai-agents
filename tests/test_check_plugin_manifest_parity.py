"""Tests for build/scripts/check_plugin_manifest_parity.py.

Covers the one invariant the script still gates:

* no component count embedded in any published description (#2187, #3651)

The version-parity half was retired with ADR-092: the manifests carry no
``version`` field, so there is no value left to hold equal. That the field stays
absent is gated by ``build/scripts/validate_plugin_version_bump.py``.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "build" / "scripts" / "check_plugin_manifest_parity.py"

# The CLI contract tests shell out. Without a cap, a wedged validator or a
# stalled `git` hangs the job until the CI-level timeout kills the whole run,
# which reports as a suite-wide failure and hides which test was stuck. Thirty
# seconds is the repo's prevailing choice and is ~100x the observed runtime.
_SUBPROCESS_TIMEOUT = 30

def _load_module() -> Any:
    """Import the validator by path, fresh per test."""
    spec = importlib.util.spec_from_file_location("parity_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def parity() -> Any:
    return _load_module()


def _manifest(tmp_path: Path, description: str, name: str = "m.json") -> Path:
    """A plugin manifest carrying one description."""
    target = tmp_path / name
    target.write_text(json.dumps({"description": description}), encoding="utf-8")
    return target


def _marketplace(tmp_path: Path, entries: list[dict[str, object]], name: str = "mk.json") -> Path:
    """A marketplace file carrying the given plugin entries."""
    target = tmp_path / name
    target.write_text(json.dumps({"plugins": entries}), encoding="utf-8")
    return target


# --- Description counts: the regression this gate exists for ----------------

# The exact string PR #2187 left behind in src/claude/.claude-plugin/plugin.json.
_THE_REGRESSION = "25 specialized agent definitions with templates and governance for Claude Code"


def test_the_original_stale_count_is_caught(parity: Any, tmp_path: Path) -> None:
    """The #3651 string must fail. This is the whole reason the check exists."""
    assert parity.check_description_counts((_manifest(tmp_path, _THE_REGRESSION),)) == 1


def test_the_repaired_string_passes(parity: Any, tmp_path: Path) -> None:
    """The same sentence with the count removed is what the fix ships."""
    repaired = "Specialized agent definitions with templates and governance for Claude Code"
    assert parity.check_description_counts((_manifest(tmp_path, repaired),)) == 0


def test_every_shipped_description_is_count_free(parity: Any) -> None:
    """The checked-in repository must satisfy its own gate."""
    assert parity.check_description_counts() == 0


@pytest.mark.parametrize("index", range(len(_load_module()._DESCRIBED_FILES)))
def test_a_count_in_any_configured_file_is_caught(
    parity: Any, tmp_path: Path, index: int
) -> None:
    """Every configured file must be read.

    Parameterized over the real tuple so that skipping any single entry, by path
    or by position, fails here instead of passing silently.
    """
    files = list(parity._DESCRIBED_FILES)
    poisoned = tmp_path / f"poisoned-{index}.json"
    original = json.loads(files[index].read_text(encoding="utf-8"))
    original["description"] = _THE_REGRESSION
    poisoned.write_text(json.dumps(original), encoding="utf-8")
    files[index] = poisoned
    assert parity.check_description_counts(tuple(files)) == 1


# --- Description counts: what must be caught --------------------------------


@pytest.mark.parametrize(
    "description",
    [
        "25 specialized agent definitions",
        "Ships 12 skills for review",
        "Bundles seven hooks and a validator",
        "Includes twenty commands",
        "Provides 3 reusable lifecycle hooks",
        "PACKS 40 AGENTS",
        "9 plugins",
        "Includes 1 agent",
        "Ships one agent",
        "Includes 3 MCP servers",
        "Adds 2 mcp-servers",
        "A 25-agent toolkit",
        "Contains 12 production-ready specialized review agents",
    ],
)
def test_counted_descriptions_fail(parity: Any, tmp_path: Path, description: str) -> None:
    assert parity.check_description_counts((_manifest(tmp_path, description),)) == 1


def test_every_component_category_is_counted(parity: Any, tmp_path: Path) -> None:
    """Each category must be live.

    Without this, deleting any one noun from the pattern passes the whole suite,
    because a hand-written example list will not happen to exercise all of them.
    """
    for noun in ("agent", "skill", "command", "hook", "mcp server", "plugin"):
        for form in (noun, f"{noun}s"):
            text = f"Ships 7 {form}"
            assert parity.check_description_counts((_manifest(tmp_path, text),)) == 1, form


def test_every_count_token_is_live(parity: Any, tmp_path: Path) -> None:
    """Same argument, applied to the count vocabulary rather than the nouns.

    The expected list is written out rather than read from the module. Deriving it
    from the code under test would make the assertion tautological: deleting a token
    would delete the case that checks it, and the deletion would pass.
    """
    expected = [
        "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
        "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
        "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty",
        "sixty", "seventy", "eighty", "ninety", "hundred",
    ]
    for token in expected + ["1", "25", "100"]:
        text = f"Ships {token} agents"
        assert parity.check_description_counts((_manifest(tmp_path, text),)) == 1, token
    assert parity._COUNT.split("|") == [r"\d+", *expected], "count vocabulary drifted"


# --- Description counts: what must NOT be caught ----------------------------


@pytest.mark.parametrize(
    "description",
    [
        "Complete project development toolkit: agents, slash commands, lifecycle "
        "hooks, and reusable skills for Claude Code workflows",
        "Specialized agent definitions, reusable skills, and lifecycle hooks for "
        "GitHub Copilot CLI, generated from Claude canonical sources",
        "Use one of the skills to review a diff",
        "Two of the agents are optional",
        "Supports 3 output formats",
        "Targets Python 3.14 and Node 22",
        "Agents, skills, and hooks",
        "",
        "Three rules of thumb for safe deployments",
        "Supports two workflows: local and CI",
        "Two dozen different ways to think about agents",
    ],
)
def test_uncounted_descriptions_pass(parity: Any, tmp_path: Path, description: str) -> None:
    assert parity.check_description_counts((_manifest(tmp_path, description),)) == 0


def test_a_singular_category_is_still_a_count(parity: Any, tmp_path: Path) -> None:
    '''A count like "1 agent" goes stale the moment a second lands.'''
    assert parity.check_description_counts((_manifest(tmp_path, "2 agent"),)) == 1


def test_a_partitive_is_not_a_count(parity: Any, tmp_path: Path) -> None:
    """`of` marks a selection from a set, which names no inventory."""
    assert parity.check_description_counts((_manifest(tmp_path, "one of the skills"),)) == 0


def test_a_count_too_far_from_its_noun_does_not_match(parity: Any, tmp_path: Path) -> None:
    """Distance is what separates a quantified noun phrase from unrelated prose."""
    text = "12 is the number of the day and here are the skills"
    assert parity.check_description_counts((_manifest(tmp_path, text),)) == 0


def test_three_intervening_words_still_match(parity: Any, tmp_path: Path) -> None:
    """The upper bound of the window. Narrowing it past three must fail here."""
    text = "Contains 12 production-ready specialized review agents"
    assert parity.check_description_counts((_manifest(tmp_path, text),)) == 1


def test_four_intervening_words_do_not_match(parity: Any, tmp_path: Path) -> None:
    """The other side of the same bound. Widening it must fail here."""
    text = "4 brand new shiny lifecycle skills"
    assert parity.check_description_counts((_manifest(tmp_path, text),)) == 0


def test_a_hyphenated_count_is_a_count(parity: Any, tmp_path: Path) -> None:
    '''"25-agent" is the same claim as "25 agents" and goes stale identically.'''
    assert parity.check_description_counts((_manifest(tmp_path, "A 25-agent kit"),)) == 1


# --- Description counts: marketplace entries --------------------------------


def test_marketplace_entry_description_is_scanned(parity: Any, tmp_path: Path) -> None:
    market = _marketplace(tmp_path, [{"name": "a", "description": _THE_REGRESSION}])
    assert parity.check_description_counts((market,)) == 1


def test_marketplace_top_level_description_is_scanned(parity: Any, tmp_path: Path) -> None:
    target = tmp_path / "mk.json"
    target.write_text(
        json.dumps({"description": "Catalog of 30 agents", "plugins": []}), encoding="utf-8"
    )
    assert parity.check_description_counts((target,)) == 1


def test_every_entry_is_scanned_not_just_the_first(parity: Any, tmp_path: Path) -> None:
    """A short-circuit after the first clean entry must fail here."""
    market = _marketplace(
        tmp_path,
        [
            {"name": "clean", "description": "Nothing to see"},
            {"name": "dirty", "description": _THE_REGRESSION},
        ],
    )
    assert parity.check_description_counts((market,)) == 1


def test_clean_marketplace_entries_pass(parity: Any, tmp_path: Path) -> None:
    market = _marketplace(
        tmp_path,
        [
            {"name": "a", "description": "Agent definitions and governance"},
            {"name": "b", "description": "Reusable skills and hooks"},
        ],
    )
    assert parity.check_description_counts((market,)) == 0


def test_every_configured_file_is_scanned_not_just_the_first(
    parity: Any, tmp_path: Path
) -> None:
    """A short-circuit after the first clean file must fail here."""
    clean = _manifest(tmp_path, "Nothing to see", name="clean.json")
    dirty = _manifest(tmp_path, _THE_REGRESSION, name="dirty.json")
    assert parity.check_description_counts((clean, dirty)) == 1


def test_scanned_count_covers_every_description(
    parity: Any, tmp_path: Path, capsys: Any
) -> None:
    """The reported total must reflect both files and both entries within one."""
    market = _marketplace(
        tmp_path,
        [{"name": "a", "description": "one"}, {"name": "b", "description": "two"}],
    )
    manifest = _manifest(tmp_path, "three", name="solo.json")
    assert parity.check_description_counts((market, manifest)) == 0
    assert "3 checked" in capsys.readouterr().out


# --- Description counts: malformed input ------------------------------------


def test_missing_file_is_a_config_error(parity: Any, tmp_path: Path) -> None:
    assert parity.check_description_counts((tmp_path / "absent.json",)) == 2


def test_unparseable_file_is_a_config_error(parity: Any, tmp_path: Path) -> None:
    target = tmp_path / "bad.json"
    target.write_text("{not json", encoding="utf-8")
    assert parity.check_description_counts((target,)) == 2


def test_non_object_file_is_a_config_error(parity: Any, tmp_path: Path) -> None:
    target = tmp_path / "list.json"
    target.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert parity.check_description_counts((target,)) == 2


def test_invalid_utf8_is_a_config_error(parity: Any, tmp_path: Path) -> None:
    target = tmp_path / "binary.json"
    target.write_bytes(b'{"description": "\xff\xfe"}')
    assert parity.check_description_counts((target,)) == 2


def test_oversized_integer_is_a_config_error(parity: Any, tmp_path: Path) -> None:
    """Syntactically valid JSON that Python refuses to parse must not crash.

    CPython caps integer-to-string conversion, so a long enough literal raises
    ValueError rather than JSONDecodeError.
    """
    target = tmp_path / "huge.json"
    target.write_text('{"x": ' + "1" * 5000 + "}", encoding="utf-8")
    assert parity.check_description_counts((target,)) == 2


def test_absent_description_is_not_a_failure(parity: Any, tmp_path: Path) -> None:
    """`description` is optional upstream; absent means nothing to check."""
    target = tmp_path / "nodesc.json"
    target.write_text(json.dumps({"name": "a", "version": "1.0.0"}), encoding="utf-8")
    assert parity.check_description_counts((target,)) == 0


def test_non_string_description_is_ignored(parity: Any, tmp_path: Path) -> None:
    target = tmp_path / "numeric.json"
    target.write_text(json.dumps({"description": 7}), encoding="utf-8")
    assert parity.check_description_counts((target,)) == 0


def test_non_object_entry_is_skipped(parity: Any, tmp_path: Path) -> None:
    target = tmp_path / "mixed.json"
    target.write_text(
        json.dumps({"plugins": ["not an object", {"description": _THE_REGRESSION}]}),
        encoding="utf-8",
    )
    assert parity.check_description_counts((target,)) == 1


def test_unnamed_entry_is_labelled_by_position(
    parity: Any, tmp_path: Path, capsys: Any
) -> None:
    market = _marketplace(tmp_path, [{"description": _THE_REGRESSION}])
    assert parity.check_description_counts((market,)) == 1
    assert "entry 0" in capsys.readouterr().err


def test_failure_names_the_offending_substring(
    parity: Any, tmp_path: Path, capsys: Any
) -> None:
    """The operator needs the exact text to delete, not just a file name."""
    assert parity.check_description_counts((_manifest(tmp_path, _THE_REGRESSION),)) == 1
    assert "25 specialized agent definitions" in capsys.readouterr().err


# --- CLI contract -----------------------------------------------------------


def test_cli_passes_on_the_checked_in_repository() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=_SUBPROCESS_TIMEOUT,
    )
    assert result.returncode == 0, result.stderr


def test_cli_reports_the_description_check() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=_SUBPROCESS_TIMEOUT,
    )
    assert "No component counts" in result.stdout
    # The retired half must not come back: nothing reports a version here.
    assert "versions match" not in result.stdout


def test_cli_scans_every_configured_description() -> None:
    """The reported total must equal what the checked-in files actually hold."""
    module = _load_module()
    expected = sum(
        len(module._descriptions(path, json.loads(path.read_text(encoding="utf-8"))))
        for path in module._DESCRIBED_FILES
    )
    assert expected >= 5, "configuration lost files; the gate would be near-empty"
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=_SUBPROCESS_TIMEOUT,
    )
    assert f"{expected} checked" in result.stdout


def test_configuration_covers_every_manifest_in_the_repository() -> None:
    """A new manifest must not be able to ship a count unnoticed.

    #2187 swept two of the three files that carried a count and the third kept
    a wrong number for 57 days. A hardcoded file list in the gate repeats that
    failure the moment someone adds a sixth manifest, so this test fails until
    the new file is registered.
    """
    module = _load_module()
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "*plugin.json", "*marketplace.json"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
        timeout=_SUBPROCESS_TIMEOUT,
    ).stdout
    found = {
        (REPO_ROOT / rel).resolve()
        for rel in tracked.split("\0")
        if rel and "node_modules/" not in rel and not rel.startswith("tests/")
    }
    assert found, "git ls-files matched nothing; the glob is wrong"
    configured = {path.resolve() for path in module._DESCRIBED_FILES}
    missing = sorted(str(p.relative_to(REPO_ROOT)) for p in found - configured)
    assert not missing, f"manifests not scanned for counts: {missing}"


# Review raised the concern that `_COUNT` lists `twenty` and `five` but not
# `twenty-five`, leaving hyphenated spelled-out numbers as a hole a drifting
# count could slip through. Measurement says the phrase matches. The reason is
# the optional intervening-word group: its separator is `[-\s]+`, so a hyphen
# is read the same way a space is and the tail of the compound is absorbed as an
# intervening word.
#
# The reviewer's own examples do not prove that, which is worth stating plainly
# rather than banking a green test. In "twenty-five agents" the second half is
# itself a count token, so the phrase still matches on the "five agents" tail
# even with the hyphen support removed. Same for "ninety-nine skills". They are
# kept because they are the cases that were asked about, and marked for what
# they are.
@pytest.mark.parametrize("text", ["twenty-five agents", "ninety-nine skills"])
def test_the_reviewed_hyphenated_examples_are_counts(
    parity: Any, tmp_path: Path, text: str
) -> None:
    """Answers the review directly. Does not isolate the hyphen; see below."""
    assert parity.check_description_counts((_manifest(tmp_path, text),)) == 1


# These do isolate it. In each one the token after the hyphen is not a count, so
# the only way the phrase can match is if `[-\s]+` let the hyphen act as a word
# separator. Narrowing that to `\s+` fails every case here and neither case
# above, which is the whole reason this second set exists.
@pytest.mark.parametrize(
    "text",
    [
        "twenty-odd agents",
        "hundred-plus commands",
        "five-star agents",
        "three-legged skills",
        "twenty-first agents",
    ],
)
def test_a_hyphen_separates_a_count_from_a_non_count_word(
    parity: Any, tmp_path: Path, text: str
) -> None:
    assert parity.check_description_counts((_manifest(tmp_path, text),)) == 1


def test_a_count_word_outside_the_token_set_is_not_a_count(
    parity: Any, tmp_path: Path
) -> None:
    """Pins the real edge of the pattern, which is the token list, not hyphens.

    "half-dozen hooks" is an inventory claim in English and this gate does not
    see it, because `dozen` is not in `_COUNT`. Recorded rather than fixed:
    widening the token set trades a miss for false positives on ordinary prose,
    and that trade needs a decision, not a quiet edit inside a review reply.
    """
    assert parity.check_description_counts((_manifest(tmp_path, "half-dozen hooks"),)) == 0
