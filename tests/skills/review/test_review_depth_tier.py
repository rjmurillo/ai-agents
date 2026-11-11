"""Boundary tests for the review depth tier script (issue #7150).

Each signal gets a pair of fixtures: one just below its elevated threshold and
one at it, then the same pair for the high threshold.  The fixtures isolate one
signal at a time so a wrong comparison operator or a swapped constant fails
exactly one test.  The CLI tests run the script as a subprocess and assert the
exit code.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/review/scripts/review_depth_tier.py",
    module_name="review_depth_tier",
)

SCRIPT_PATH = PROJECT_ROOT / ".claude" / "skills" / "review" / "scripts" / "review_depth_tier.py"
CONTRACT = PROJECT_ROOT / ".claude" / "skills" / "review" / "resources" / "technical-review.md"


def _file_diff(path: str, added: list[str], removed: list[str] | None = None) -> str:
    removed = removed or []
    body = [f"-{line}" for line in removed] + [f"+{line}" for line in added]
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,{len(removed)} +1,{len(added)} @@\n" + "\n".join(body) + "\n"
    )


def _lines_diff(count: int) -> str:
    return _file_diff("pkg/one.py", ["x = 1"] * count)


def _files_diff(count: int) -> str:
    return "".join(_file_diff(f"pkg/f{i}.py", ["x = 1"]) for i in range(count))


def _dirs_diff(count: int) -> str:
    return "".join(_file_diff(f"d{i}/f.py", ["x = 1"]) for i in range(count))


def _symbols_diff(count: int) -> str:
    return _file_diff("pkg/api.py", [f"def public_{i}():" for i in range(count)])


def _tier(diff: str, excludes: tuple[str, ...] = ()) -> str:
    return str(mod.compute(diff, excludes)["tier"])


@pytest.mark.parametrize(
    ("builder", "below", "elevated", "high_below", "high"),
    [
        (_lines_diff, 200, 201, 1000, 1001),
        (_files_diff, 10, 11, 30, 31),
        (_dirs_diff, 3, 4, 8, 9),
        (_symbols_diff, 2, 3, 9, 10),
    ],
    ids=["lines", "files", "dirs", "public_symbols"],
)
def test_each_signal_changes_tier_exactly_at_its_threshold(
    builder, below, elevated, high_below, high
):
    assert _tier(builder(below)) == "standard"
    assert _tier(builder(elevated)) == "elevated"
    assert _tier(builder(high_below)) == "elevated"
    assert _tier(builder(high)) == "high"


def test_thresholds_in_tests_match_script_constants():
    """Guards the parametrized boundaries above against a silent constant edit."""
    expected = {
        "lines": (201, 1001),
        "files": (11, 31),
        "dirs": (4, 9),
        "public_symbols": (3, 10),
    }
    assert expected == mod.THRESHOLDS


def test_small_change_is_standard_with_one_caller_floor():
    result = mod.compute(_file_diff("pkg/a.py", ["y = 2"], ["y = 1"]))
    assert result["tier"] == "standard"
    assert result["signals"] == {"lines": 2, "files": 1, "dirs": 1, "public_symbols": 0}
    assert result["caller_trace_floor"] == {"callers": 1, "files": 1}
    assert result["selected_by"] == []


def test_highest_signal_wins_and_names_every_signal_at_that_tier():
    diff = _files_diff(11) + _symbols_diff(10)
    result = mod.compute(diff)
    assert result["tier"] == "high"
    assert result["selected_by"] == ["public_symbols"]


def test_tier_floor_rises_monotonically():
    floors = [mod.CALLER_TRACE_FLOOR[t] for t in mod.TIERS]
    callers = [f["callers"] for f in floors]
    assert callers == sorted(set(callers)), "each tier must read strictly more callers"
    assert callers[0] == 1, "standard must stay at today's one-caller floor"
    assert [f["files"] for f in floors] == sorted(f["files"] for f in floors)


def test_removed_public_symbol_counts_like_an_added_one():
    removed = _file_diff("pkg/api.py", [], [f"def public_{i}():" for i in range(3)])
    assert mod.compute(removed)["signals"]["public_symbols"] == 3


@pytest.mark.parametrize(
    "declaration",
    [
        "def _private():",
        "    def _private_method(self):",
        "class _Hidden:",
        "x = 1",
        "# def commented_out():",
    ],
)
def test_private_or_non_declaration_lines_are_not_public_symbols(declaration):
    diff = _file_diff("pkg/api.py", [declaration])
    assert mod.compute(diff)["signals"]["public_symbols"] == 0


@pytest.mark.parametrize(
    ("path", "line"),
    [
        ("pkg/api.py", "def public():"),
        ("pkg/api.py", "async def public():"),
        ("pkg/api.py", "class Public:"),
        ("web/api.ts", "export function publicFn() {"),
        ("web/api.ts", "export default class Thing {"),
        ("src/Api.cs", "    public Task<int> Run(int x)"),
        ("tools/x.ps1", "function Get-Thing {"),
        ("svc/api.go", "func Public(x int) int {"),
        ("lib/api.rs", "pub fn public() {"),
    ],
)
def test_public_symbol_patterns_match_each_supported_language(path, line):
    assert mod.compute(_file_diff(path, [line]))["signals"]["public_symbols"] == 1


def test_symbol_pattern_ignored_in_non_source_file():
    diff = _file_diff("docs/guide.md", ["def public():"])
    assert mod.compute(diff)["signals"]["public_symbols"] == 0


def test_exclude_glob_removes_generated_files_from_every_signal():
    diff = _lines_diff(50) + _file_diff("gen/out.py", ["x = 1"] * 5000)
    assert _tier(diff) == "high"
    result = mod.compute(diff, ("gen/*",))
    assert result["tier"] == "standard"
    assert result["signals"]["files"] == 1
    assert result["excluded_globs"][-1] == "gen/*"


def test_file_headers_do_not_count_as_changed_lines():
    result = mod.compute(_file_diff("pkg/a.py", ["x = 1"]))
    assert result["signals"]["lines"] == 1


def test_rename_without_hunks_counts_as_one_file():
    diff = (
        "diff --git a/old.py b/new.py\n"
        "similarity index 100%\nrename from old.py\nrename to new.py\n"
    )
    result = mod.compute(diff)
    assert result["signals"]["files"] == 1
    assert result["signals"]["lines"] == 0


def test_same_input_gives_same_output():
    diff = _files_diff(12)
    assert mod.compute(diff) == mod.compute(diff)


def _run(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_cli_emits_json_and_exits_zero():
    proc = _run(_files_diff(11))
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["tier"] == "elevated"


def test_cli_exclude_flag_is_honored():
    proc = _run(_files_diff(11), "--exclude", "pkg/f1*.py", "--exclude", "pkg/f0.py")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    # f1*.py matches f1 and f10, f0.py matches itself: 11 files - 3 excluded.
    assert payload["signals"]["files"] == 8
    assert payload["tier"] == "standard"


@pytest.mark.parametrize("stdin", ["", "\n", "not a diff\n+++ b/x\n"])
def test_cli_exits_two_when_stdin_holds_no_diff(stdin):
    proc = _run(stdin)
    assert proc.returncode == 2
    assert "no 'diff --git' headers" in proc.stderr
    assert proc.stdout == ""


def test_contract_states_every_tier_and_threshold_from_the_script():
    text = CONTRACT.read_text(encoding="utf-8")
    for tier in mod.TIERS:
        assert f"`{tier}`" in text, f"contract does not name tier {tier}"
    for signal, (elevated_at, high_at) in mod.THRESHOLDS.items():
        row = next((ln for ln in text.splitlines() if ln.startswith(f"| `{signal}`")), None)
        assert row is not None, f"contract has no threshold row for {signal}"
        numbers = [int(n) for n in re.findall(r"\d+", row)]
        assert numbers == [elevated_at, high_at], f"{signal} row drifted from script: {row}"


def test_header_line_matches_the_contract_format():
    result = mod.compute(_files_diff(11))
    assert result["header"] == "REVIEW_DEPTH: elevated lines=11 files=11 dirs=1 public_symbols=0"


def _quoted_diff(a_path: str, b_path: str, body: list[str]) -> str:
    return (
        f"diff --git {a_path} {b_path}\n--- {a_path}\n+++ {b_path}\n"
        f"@@ -0,0 +1,{len(body)} @@\n" + "\n".join(f"+{line}" for line in body) + "\n"
    )


def test_quoted_non_ascii_path_counts_as_a_file():
    diff = _quoted_diff('"a/caf\\303\\251.py"', '"b/caf\\303\\251.py"', ["x = 1"])
    result = mod.compute(diff)
    assert result["signals"]["files"] == 1
    assert result["signals"]["lines"] == 1
    assert result["tier"] == "standard"


def test_quoted_path_is_unquoted_before_exclude_matching():
    diff = _quoted_diff('"a/gen/caf\\303\\251.py"', '"b/gen/caf\\303\\251.py"', ["x = 1"] * 400)
    assert _tier(diff) == "elevated"
    assert mod.compute(diff, ("gen/caf\u00e9.py",))["signals"]["files"] == 0


def test_mixed_quoted_and_plain_headers_both_count():
    diff = _file_diff("pkg/plain.py", ["x = 1"]) + _quoted_diff(
        '"a/pkg/q\\"uote.py"', '"b/pkg/q\\"uote.py"', ["y = 2"]
    )
    signals = mod.parse_diff(diff)
    assert signals.files == 2
    assert 'pkg/q"uote.py' in signals.paths


def test_cli_accepts_a_diff_whose_every_path_is_quoted():
    diff = _quoted_diff('"a/caf\\303\\251.py"', '"b/caf\\303\\251.py"', ["x = 1"])
    proc = _run(diff)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["signals"]["files"] == 1


@pytest.mark.parametrize("content", ["-- sql comment", "--i;", "---", "++i;", "++ x"])
def test_hunk_body_lines_that_start_like_file_headers_are_counted(content):
    removed = _file_diff("pkg/a.sql", [], [content])
    added = _file_diff("pkg/a.sql", [content])
    assert mod.compute(removed)["signals"]["lines"] == 1
    assert mod.compute(added)["signals"]["lines"] == 1


def test_file_headers_still_excluded_across_multiple_files():
    diff = _file_diff("pkg/a.py", ["x = 1"]) + _file_diff("pkg/b.py", ["y = 2"], ["y = 1"])
    assert mod.compute(diff)["signals"]["lines"] == 3


def test_contract_floor_table_matches_the_script():
    text = CONTRACT.read_text(encoding="utf-8")
    for tier, floor in mod.CALLER_TRACE_FLOOR.items():
        row = next((ln for ln in text.splitlines() if ln.startswith(f"| `{tier}` | ")), None)
        assert row is not None, f"contract has no floor row for {tier}"
        numbers = [int(n) for n in re.findall(r"\d+", row)]
        assert numbers == [floor["callers"], floor["files"]], f"{tier} floor drifted: {row}"


def test_contract_keeps_context_mode_first_line():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "first line after the `CONTEXT_MODE:` header" in text
    assert "ahead of the `CONTEXT_MODE:` header" not in text


@pytest.mark.parametrize(
    "lockfile",
    [
        "uv.lock",
        "Cargo.lock",
        "bun.lockb",
        "web/package-lock.json",
        "src/App/packages.lock.json",
        "pnpm-lock.yaml",
        "svc/go.sum",
    ],
)
def test_lockfiles_are_excluded_by_default(lockfile):
    diff = _file_diff("pkg/a.py", ["x = 1"]) + _file_diff(lockfile, ["dep"] * 5000)
    result = mod.compute(diff)
    assert result["tier"] == "standard"
    assert result["signals"] == {"lines": 1, "files": 1, "dirs": 1, "public_symbols": 0}


def test_default_exclusion_does_not_hide_a_source_file_named_like_a_lockfile():
    diff = _file_diff("pkg/lockfile.py", ["x = 1"] * 300)
    assert _tier(diff) == "elevated"


def test_default_excludes_are_reported_alongside_caller_excludes():
    result = mod.compute(_lines_diff(3), ("gen/*",))
    assert result["excluded_globs"] == [*mod.DEFAULT_EXCLUDES, "gen/*"]


def test_contract_tells_the_reviewer_to_recount_when_it_excludes_more():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "recount without them and use the lower tier" in text
