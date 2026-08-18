"""Worktree destinations in tracked prescriptions (issue #5111).

`.claude/rules/universal.md` MUST NOT 7 says worktrees must be external. The
rule, a Serena memory, and a documented prior incident all existed while six
worktrees accumulated under `/tmp` and filled a 16G tmpfs. Nothing read the
recipes, so nothing caught them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_worktree_recipes as checker

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- extract_destination: which token is the path -------------------------


@pytest.mark.parametrize(
    ("rest", "expected"),
    [
        (" ../wt-foo feature/xyz", "../wt-foo"),
        (" -b feature/xyz ../wt-foo origin/main", "../wt-foo"),
        (" -B feature/xyz ../wt-foo", "../wt-foo"),
        (" --detach ../wt-foo origin/main", "../wt-foo"),
        (" --lock --reason 'holding' ../wt-foo", "../wt-foo"),
        (' "../wt-foo" "$branch"', "../wt-foo"),
        (" --force -b b ../wt-foo", "../wt-foo"),
    ],
)
def test_extract_destination_skips_flags_and_their_values(rest: str, expected: str) -> None:
    assert checker.extract_destination(rest) == expected


def test_extract_destination_returns_none_when_only_flags_follow() -> None:
    assert checker.extract_destination(" --detach") is None


def test_extract_destination_returns_none_on_empty_rest() -> None:
    assert checker.extract_destination("") is None


# --- classify: positive (bad destinations) --------------------------------


@pytest.mark.parametrize(
    "destination",
    ["/tmp/wt_4003", "/tmp", "/tmp/", "/var/tmp/wt", "/private/tmp/wt", "/dev/shm/wt"],
)
def test_temp_destinations_are_rejected(destination: str) -> None:
    assert checker.classify(destination) == checker.REASON_TEMP


@pytest.mark.parametrize(
    "destination",
    [
        "./.worktrees/pr-1",
        ".worktrees/pr-1",
        ".claude/worktrees/agent-a",
        "sub/dir/wt",
        "./a/../b",
    ],
)
def test_in_checkout_destinations_are_rejected(destination: str) -> None:
    assert checker.classify(destination) == checker.REASON_IN_CHECKOUT


def test_placeholder_segment_is_counted_not_skipped() -> None:
    # The real pr-review recipe. The placeholder is one directory level, which
    # is enough to settle that the path stays inside the checkout.
    assert checker.classify("./.worktrees/pr-{number}") == checker.REASON_IN_CHECKOUT


# --- classify: negative (acceptable destinations) -------------------------


@pytest.mark.parametrize(
    "destination",
    [
        "../wt-feature-xyz",
        "../ai-agents-worktrees/pr-1",
        "../wt-<slug>",
        "/home/richard/src/GitHub/rjmurillo/ai-agents-slug",
        "~/worktrees/myapp-hotfix",
        # Rises above the checkout and descends into a sibling, so it lands
        # outside even though it holds a descending segment.
        "../wt/../back-inside",
    ],
)
def test_external_destinations_are_accepted(destination: str) -> None:
    assert checker.classify(destination) is None


def test_reentering_the_checkout_by_name_is_a_known_miss() -> None:
    """Documents the one in-checkout shape ``classify`` cannot see.

    Once a path rises above the checkout root the checker calls it external,
    because a recipe's text does not carry the checkout's own directory name
    and nothing else can tell ``../ai-agents/x`` (back inside) from
    ``../wt-x`` (a sibling). No tracked prescription uses the re-entering form;
    this test pins the behavior so a future change to it is deliberate.
    """
    assert checker.classify("../ai-agents/.worktrees/pr-1") is None


@pytest.mark.parametrize("destination", ["${dir}", "$HOME/wt", "`pwd`/wt", "../$slug"])
def test_shell_expansions_are_not_judged(destination: str) -> None:
    assert checker.classify(destination) is None


@pytest.mark.parametrize("destination", ["a", "and", "failed", "<path>", "checkout"])
def test_non_path_shaped_tokens_are_not_judged(destination: str) -> None:
    assert checker.classify(destination) is None


# --- classify: edge cases -------------------------------------------------


def test_empty_destination_is_not_judged() -> None:
    assert checker.classify("") is None


def test_bare_slash_is_not_judged_as_temp() -> None:
    assert checker.classify("/") is None


# --- scan_text ------------------------------------------------------------


def test_scan_text_reports_file_line_and_destination() -> None:
    text = "intro\ngit worktree add /tmp/wt_4003 main\ntrailer\n"

    findings = checker.scan_text("docs/x.md", text)

    assert len(findings) == 1
    assert findings[0].line_number == 2
    assert findings[0].destination == "/tmp/wt_4003"
    assert "docs/x.md:2" in findings[0].render()


def test_scan_text_returns_empty_for_a_clean_recipe() -> None:
    assert checker.scan_text("docs/x.md", "git worktree add ../wt-foo main\n") == []


def test_scan_text_returns_empty_when_no_recipe_is_present() -> None:
    assert checker.scan_text("docs/x.md", "no recipes here\n") == []


def test_scan_text_handles_empty_input() -> None:
    assert checker.scan_text("docs/x.md", "") == []


def test_historical_marker_opts_a_line_out() -> None:
    text = f"git worktree add /tmp/wt main  # {checker.HISTORICAL_MARKER}\n"

    assert checker.scan_text("docs/x.md", text) == []


def test_a_recipe_with_no_destination_at_all_is_not_a_finding() -> None:
    # `extract_destination` returns None; the line must be skipped, not guessed.
    assert checker.scan_text("docs/x.md", "git worktree add --detach\n") == []


def test_prose_mentioning_the_command_is_not_a_finding() -> None:
    # The exact GOTCHAS.md sentence that a naive token scan misreads.
    text = "The direct cost is that `git bisect`, `git worktree add --detach`, a CI checkout\n"

    assert checker.scan_text(".agents/governance/GOTCHAS.md", text) == []


# --- is_scanned -----------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [".claude/commands/pr-review.md", "scripts/x.py", ".github/prompts/y.prompt.md"],
)
def test_prescriptive_surfaces_are_scanned(path: str) -> None:
    assert checker.is_scanned(path) is True


@pytest.mark.parametrize(
    "path",
    [
        ".agents/retrospective/2025-12-24-parallel-pr-review-session.md",
        ".agents/archive/planning/v0.3.0/PLAN.md",
        ".agents/sessions/x.json",
        ".agents/memory/episodes/e.json",
        ".claude/worktrees/nested/x.md",
        "README.md",
        "scripts/x.bin",
    ],
)
def test_history_and_out_of_scope_paths_are_skipped(path: str) -> None:
    assert checker.is_scanned(path) is False


# --- repository-wide gate -------------------------------------------------


def test_the_tracked_corpus_has_no_bad_worktree_recipes() -> None:
    violations, examined = checker.check_repository(REPO_ROOT)

    assert violations == [], "\n".join(v.render() for v in violations)
    assert examined > 0, "scanned nothing; the inventory or the prefixes are wrong"


def test_validate_returns_true_on_the_real_repository() -> None:
    assert checker.validate_worktree_recipes(REPO_ROOT) is True


def test_an_unreadable_tracked_file_is_skipped_not_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> str:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", explode)

    violations, examined = checker.check_repository(REPO_ROOT)

    assert violations == []
    assert examined == 0, "an unreadable file must not count as examined"


def test_validate_returns_false_when_the_inventory_cannot_be_read(tmp_path: Path) -> None:
    # Not a git repository, so git ls-files fails and the gate must fail closed.
    assert checker.validate_worktree_recipes(tmp_path) is False


# --- CLI exit codes -------------------------------------------------------


def test_main_exits_zero_on_the_real_repository() -> None:
    assert checker.main(["--repo-root", str(REPO_ROOT)]) == 0


def test_main_exits_two_when_the_root_is_not_a_repository(tmp_path: Path) -> None:
    assert checker.main(["--repo-root", str(tmp_path)]) == 2


def test_main_exits_one_when_a_tracked_prescription_is_bad(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    doc = tmp_path / "scripts" / "recipe.md"
    doc.parent.mkdir()
    doc.write_text("git worktree add /tmp/wt-bad main\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)

    assert checker.main(["--repo-root", str(tmp_path)]) == 1


def test_module_runs_as_a_script_and_exits_zero() -> None:
    result = subprocess.run(
        ["python3", str(REPO_ROOT / "scripts" / "validation" / "check_worktree_recipes.py")],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "examined files" in result.stdout
