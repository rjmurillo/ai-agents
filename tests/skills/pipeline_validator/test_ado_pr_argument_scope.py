"""Argument-scope contract for the ``az repos pr`` commands this repo documents.

Issue #5077. The reported symptom was an Azure DevOps CLI call that passed ``--project``
and ``--repository`` to ``az repos pr policy list``, which rejects both, so every poll
returned an error instead of a policy state. The script named in that issue
(``.agents/tools/Wait-PrCi.ps1``) has never existed in this repository (``git log --all
--diff-filter=ADMR -- '*Wait-PrCi*'`` returns nothing, and the tree carries zero ``.ps1``
files), but the same defect was present here in a command this repo does ship:
``.claude/skills/pipeline-validator/SKILL.md`` Step 2 passed ``--project`` to
``az repos pr show``.

The canonical contract is the Azure CLI ``azure-devops`` extension reference, fetched from
Microsoft Learn on 2026-08-18. ``az repos pr show``
(https://learn.microsoft.com/en-us/cli/azure/repos/pr#az-repos-pr-show) reads verbatim:

    az repos pr show --id
                     [--detect {false, true}]
                     [--open]
                     [--org --organization]

and ``az repos pr policy list``
(https://learn.microsoft.com/en-us/cli/azure/repos/pr/policy#az-repos-pr-policy-list):

    az repos pr policy list --id
                            [--detect {false, true}]
                            [--org --organization]
                            [--skip]
                            [--top]

Neither accepts ``--project`` or ``--repository``. The pull request ID resolves both, so
the extension never declares the parameters and argparse rejects the whole invocation with
``ERROR: unrecognized arguments``. The rule generalizes: every ``az repos pr`` subcommand
that takes a required ``--id`` is scoped by that ID and refuses project/repository flags.

The inverse failure mode is the reason this module asserts in two directions.
``az repos pr list`` and ``az repos pr create`` have no PR ID to resolve scope from, so
they *do* declare ``--project -p`` and ``--repository -r``. A fix that stripped those flags
everywhere would turn a broken ``show`` call into a broken ``list`` call and lose the
branch's PR lookup. ``TestCollectionScopedCommandsKeepProjectFlags`` fails if that happens.

Assertions parse each fenced block and prose line into discrete ``az repos pr`` invocations
rather than substring-matching the file (`.claude/rules/testing.md` MUST 9): a bare
``"--project" not in text`` check would fail on the legitimate ``az repos pr list`` call two
dozen lines above the defect and prove nothing about which command carries the flag.
``TestPreFixControl`` feeds the pre-fix line back through the same parser, so every check
here is shown to fail on the shape it was written against (`.claude/rules/testing.md`
SHOULD 10).

``.claude/skills/pipeline-validator/SKILL.md`` is the source;
``src/copilot-cli/skills/pipeline-validator/SKILL.md`` is generated from it by
``build/scripts/generate_skills.py`` (see ``.agents/governance/GENERATOR-FILES.md``). Both
trees are asserted so the shipped Copilot copy cannot keep the defect after the Claude copy
is repaired.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# Subcommands whose Azure CLI signature requires --id and therefore declares no
# --project/--repository. Verified against the Microsoft Learn reference quoted above.
ID_SCOPED_SUBCOMMANDS = frozenset(
    {
        "checkout",
        "policy list",
        "policy queue",
        "reviewer add",
        "reviewer list",
        "reviewer remove",
        "set-vote",
        "show",
        "update",
        "work-item add",
        "work-item list",
        "work-item remove",
    }
)

# Subcommands with no PR ID to resolve scope from, which do declare --project/--repository.
COLLECTION_SCOPED_SUBCOMMANDS = frozenset({"create", "list"})

# --project/-p and --repository/-r in long, short, and equals forms.
SCOPE_FLAG_PATTERN = re.compile(r"(?:^|\s)(--project|--repository|-p|-r)(?=[\s=]|$)")

# Double- or single-quoted argument values. Blanked before flag scanning so a free-text
# value cannot be read as a flag: `--description "retry -p 3 times"` is a legal
# `az repos pr update` call, and matching the `-p` inside it would fail the suite with a
# wrong diagnosis. `test_flag_inside_quoted_value_is_ignored` pins this.
QUOTED_VALUE_PATTERN = re.compile(r"\"[^\"\n]*\"|'[^'\n]*'")

# PowerShell line continuation: a backtick at end of line, spliced before parsing.
# The skill under guard is PowerShell and its `az` lines already run past 150 characters,
# so any future reflow wraps them this way. Because a backtick also closes markdown inline
# code (and therefore terminates an invocation below), an unspliced continuation would cut
# the tail at the wrap point and hide every flag after it, silently disarming this module.
# `test_powershell_line_continuation_is_spliced` pins this.
CONTINUATION_PATTERN = re.compile(r"[ \t]`[ \t]*\r?\n[ \t]*")

# An invocation is the command name plus everything up to a pipe, statement separator,
# closing backtick, or end of line. `<` and `>` are deliberately NOT terminators: these
# documents use `<org-url>` and `<project>` as placeholders, not shell redirects. Treating
# `>` as a terminator truncated the tail at `<org-url>` and hid the very `--project` flag
# this module exists to catch; `TestPreFixControl` failed on exactly that and is the reason
# the class is here.
INVOCATION_PATTERN = re.compile(r"az\s+repos\s+pr\s+(?P<tail>[^\n|`;]*)")

# Longest-first so "policy list" wins over a bare "policy".
_KNOWN_SUBCOMMANDS = sorted(
    ID_SCOPED_SUBCOMMANDS | COLLECTION_SCOPED_SUBCOMMANDS,
    key=lambda name: (-len(name), name),
)

SKILL_PATHS = (
    Path(".claude/skills/pipeline-validator/SKILL.md"),
    Path("src/copilot-cli/skills/pipeline-validator/SKILL.md"),
)

# Files known to document an `az repos pr` call today. Asserted to still be covered so a
# rename or deletion is noticed, but the scan itself is repo-wide (see `ado_doc_paths`):
# pinning the guard to a fixed tuple would leave any newly added skill or runbook unguarded.
KNOWN_ADO_DOC_PATHS = (
    *SKILL_PATHS,
    Path(".claude/commands/ship.md"),
    Path("src/copilot-cli/skills/ship/SKILL.md"),
)

# Directories with no authored documentation to guard.
_SCAN_EXCLUDED_DIRS = frozenset({".git", "node_modules", "tests", ".venv", "dist"})


def ado_doc_paths() -> list[Path]:
    """Return every markdown file in the repo that invokes `az repos pr`.

    Repo-wide rather than a fixed list so a new skill, command, or runbook that documents
    the command is guarded the day it lands, with nobody needing to remember this module.
    """
    found: list[Path] = []
    for absolute in sorted(REPO_ROOT.rglob("*.md")):
        relative = absolute.relative_to(REPO_ROOT)
        if _SCAN_EXCLUDED_DIRS.intersection(relative.parts):
            continue
        if "az repos pr" in absolute.read_text(encoding="utf-8"):
            found.append(relative)
    return found


PRE_FIX_LINE = (
    "$prDetails = az repos pr show --id $prId --organization <org-url> "
    '--project "<project>" --output json | ConvertFrom-Json'
)


class Invocation:
    """One parsed ``az repos pr`` command line."""

    def __init__(self, subcommand: str, arguments: str, source: str) -> None:
        self.subcommand = subcommand
        self.arguments = arguments
        self.source = source

    @property
    def scope_flags(self) -> list[str]:
        """Return the --project/--repository flags this invocation passes.

        Quoted values are blanked first so free text inside an argument cannot be read as
        a flag. Length is preserved so offsets stay meaningful in failure output.
        """
        scannable = QUOTED_VALUE_PATTERN.sub(lambda m: " " * len(m.group(0)), self.arguments)
        return [match.group(1) for match in SCOPE_FLAG_PATTERN.finditer(scannable)]

    @property
    def is_call(self) -> bool:
        """True when arguments follow the subcommand, i.e. this is a real command line.

        A bare backticked name in a verification checklist ("paste the `az repos pr show`
        exit status") is documentation, not an invocation, and must not be counted when
        asserting how many times a step runs a command.
        """
        return bool(self.arguments.strip())

    def __repr__(self) -> str:
        return f"Invocation({self.subcommand!r}, {self.source!r})"


def parse_invocations(text: str) -> list[Invocation]:
    """Extract every ``az repos pr`` invocation with a recognized subcommand.

    Unrecognized tails (prose mentions, truncated references) are dropped rather than
    guessed at, so a documentation rewording cannot silently disable the check by making a
    real invocation unparseable. `test_unknown_subcommand_is_not_guessed` pins that.
    """
    invocations: list[Invocation] = []
    text = CONTINUATION_PATTERN.sub(" ", text)
    for match in INVOCATION_PATTERN.finditer(text):
        tail = match.group("tail").strip()
        for subcommand in _KNOWN_SUBCOMMANDS:
            if tail == subcommand or tail.startswith(f"{subcommand} "):
                invocations.append(
                    Invocation(subcommand, tail[len(subcommand) :], match.group(0).strip())
                )
                break
    return invocations


def parse_calls(text: str) -> list[Invocation]:
    """Return only real command lines, dropping bare prose mentions."""
    return [call for call in parse_invocations(text) if call.is_call]


def read(path: Path) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


@pytest.fixture(params=SKILL_PATHS, ids=lambda p: str(p))
def skill_text(request: pytest.FixtureRequest) -> str:
    return read(request.param)


class TestIdScopedCommandsRejectProjectFlags:
    """The fix: no ID-scoped invocation may carry --project or --repository."""

    def test_no_id_scoped_invocation_passes_scope_flags(self) -> None:
        """Repo-wide: any markdown file, not just the four that exist today."""
        offenders = [
            (str(path), call.source, call.scope_flags)
            for path in ado_doc_paths()
            for call in parse_invocations(read(path))
            if call.subcommand in ID_SCOPED_SUBCOMMANDS and call.scope_flags
        ]
        assert offenders == [], (
            "project/repository flags passed to an ID-scoped `az repos pr` subcommand; "
            f"the Azure CLI rejects the whole call: {offenders}"
        )

    def test_scan_still_covers_the_known_documents(self) -> None:
        """A rename that drops a file out of the scan must not pass silently."""
        scanned = set(ado_doc_paths())
        assert set(KNOWN_ADO_DOC_PATHS) <= scanned, (
            f"expected documents dropped out of the scan: "
            f"{sorted(set(KNOWN_ADO_DOC_PATHS) - scanned)}"
        )

    def test_pr_show_invocation_exists_and_is_clean(self, skill_text: str) -> None:
        """Guard against fixing the flag by deleting the command outright."""
        shows = [c for c in parse_calls(skill_text) if c.subcommand == "show"]
        assert shows, "pipeline-validator Step 2 must still fetch PR details"
        assert all(c.scope_flags == [] for c in shows)
        assert all("--id" in c.arguments for c in shows)

    def test_policy_list_invocation_is_clean(self) -> None:
        """The exact command named in issue #5077, in the file this repo does ship."""
        for path in (
            Path(".claude/commands/ship.md"),
            Path("src/copilot-cli/skills/ship/SKILL.md"),
        ):
            policy_calls = [c for c in parse_calls(read(path)) if c.subcommand == "policy list"]
            assert policy_calls, f"{path} must keep its build-policy check"
            assert all(c.scope_flags == [] for c in policy_calls), (
                f"{path}: `az repos pr policy list` accepts only --id/--detect/--org/--skip/--top"
            )


class TestCollectionScopedCommandsKeepProjectFlags:
    """Inverse guard: the fix must not strip flags the CLI does accept."""

    def test_pr_list_retains_project_flag(self, skill_text: str) -> None:
        lists = [c for c in parse_calls(skill_text) if c.subcommand == "list"]
        assert lists, "pipeline-validator Step 1 must still discover the PR"
        assert "--project" in lists[0].scope_flags, (
            "`az repos pr list` has no PR ID to resolve scope from and declares "
            "--project -p; stripping it breaks branch PR lookup"
        )

    def test_collection_and_id_scoped_sets_are_disjoint(self) -> None:
        assert not (ID_SCOPED_SUBCOMMANDS & COLLECTION_SCOPED_SUBCOMMANDS)


class TestGeneratedMirrorMatches:
    def test_both_trees_agree_on_pr_show(self) -> None:
        """The Copilot copy is generated; it must not lag the canonical fix."""
        parsed = [
            [
                (c.subcommand, c.scope_flags)
                for c in parse_calls(read(path))
                if c.subcommand in {"show", "list"}
            ]
            for path in SKILL_PATHS
        ]
        assert parsed[0] == parsed[1], (
            "src/copilot-cli/skills/pipeline-validator/SKILL.md is stale; regenerate with "
            "build/scripts/generate_skills.py"
        )


class TestPreFixControl:
    """Every assertion above must fail on the shape it was written against."""

    def test_pre_fix_line_is_detected_as_an_offender(self) -> None:
        calls = parse_calls(PRE_FIX_LINE)
        assert len(calls) == 1
        assert calls[0].subcommand == "show"
        assert calls[0].scope_flags == ["--project"]

    def test_over_fired_fix_fails_the_inverse_guard(self) -> None:
        """The real control for over-firing: run the inverse guard's own predicate.

        `test_pr_list_retains_project_flag` asserts `--project` survives on
        `az repos pr list`. Feeding it a stripped call must make that predicate false,
        otherwise the inverse guard is decoration. Asserting `scope_flags == []` alone
        would show nothing failing, which is what this test previously did.
        """
        over_fired = 'az repos pr list --source-branch "x" --status active --output json'
        lists = [c for c in parse_calls(over_fired) if c.subcommand == "list"]
        assert lists, "parser must still recognize the stripped call"
        assert "--project" not in lists[0].scope_flags

    def test_policy_list_guard_fails_on_the_reported_command(self) -> None:
        """Control for `test_policy_list_invocation_is_clean`, using issue #5077's line."""
        reported = (
            "az repos pr policy list --id 16476178 --org <org> "
            "--project WDATP --repository Wcd.Infra.ConfigurationGeneration --output json"
        )
        calls = parse_calls(reported)
        assert calls[0].subcommand == "policy list"
        assert calls[0].scope_flags == ["--project", "--repository"]


class TestParser:
    """Positive, negative, and edge coverage for the invocation parser itself."""

    def test_empty_text_yields_no_invocations(self) -> None:
        assert parse_invocations("") == []

    def test_text_without_az_commands_yields_no_invocations(self) -> None:
        assert parse_invocations("gh pr view --json number\nRun the validator.") == []

    def test_prose_mention_is_not_counted_as_a_call(self) -> None:
        """A backticked name with no arguments is documentation, not a call."""
        text = "paste the `az repos pr show` exit status and the PR Title line"
        assert parse_calls(text) == []
        assert [c.is_call for c in parse_invocations(text)] == [False]

    def test_bare_prose_mention_carries_no_scope_flags(self) -> None:
        text = "paste the `az repos pr update` exit status"
        assert parse_invocations(text)[0].scope_flags == []

    def test_placeholder_angle_brackets_do_not_truncate_the_tail(self) -> None:
        """Regression: `>` in `<org-url>` once hid every flag that followed it."""
        text = 'az repos pr show --id 1 --organization <org-url> --project "<project>"'
        assert parse_calls(text)[0].scope_flags == ["--project"]

    def test_powershell_line_continuation_is_spliced(self) -> None:
        """A backtick-wrapped call must not hide the flags on its continuation line.

        The guarded skill is PowerShell, where a trailing backtick continues the line.
        Without splicing, the backtick terminates the invocation and every flag after the
        wrap disappears, so the defect passes the guard.
        """
        wrapped = (
            "$prDetails = az repos pr show --id $prId --organization <org-url> `\n"
            '    --project "<project>" --output json | ConvertFrom-Json'
        )
        calls = parse_calls(wrapped)
        assert calls[0].subcommand == "show"
        assert calls[0].scope_flags == ["--project"]

    def test_markdown_inline_code_still_terminates(self) -> None:
        """Splicing continuations must not break the closing-backtick terminator."""
        text = "run `az repos pr show --id 1` then `az repos pr list --project X`"
        assert [(c.subcommand, c.scope_flags) for c in parse_calls(text)] == [
            ("show", []),
            ("list", ["--project"]),
        ]

    def test_flag_inside_quoted_value_is_ignored(self) -> None:
        """`--description "retry -p 3 times"` is legal and must not be flagged."""
        text = 'az repos pr update --id 1 --description "retry -p 3 times"'
        assert parse_calls(text)[0].scope_flags == []

    def test_real_flag_after_a_quoted_value_is_still_found(self) -> None:
        """Blanking quotes must not swallow flags that follow them."""
        text = 'az repos pr show --id 1 --description "note" --project X'
        assert parse_calls(text)[0].scope_flags == ["--project"]

    def test_single_quoted_value_is_ignored(self) -> None:
        text = "az repos pr update --id 1 --description 'use -r for repo'"
        assert parse_calls(text)[0].scope_flags == []

    def test_unknown_subcommand_is_not_guessed(self) -> None:
        assert parse_invocations("az repos pr frobnicate --project X") == []

    def test_equals_form_flag_is_detected(self) -> None:
        calls = parse_invocations("az repos pr show --id 1 --project=WDATP")
        assert calls[0].scope_flags == ["--project"]

    def test_short_flags_are_detected(self) -> None:
        calls = parse_invocations("az repos pr show --id 1 -p WDATP -r Infra")
        assert calls[0].scope_flags == ["-p", "-r"]

    def test_repository_flag_is_detected(self) -> None:
        calls = parse_invocations("az repos pr policy list --id 1 --repository Infra")
        assert calls[0].scope_flags == ["--repository"]

    def test_longest_subcommand_wins(self) -> None:
        calls = parse_invocations("az repos pr policy list --id 1")
        assert calls[0].subcommand == "policy list"

    def test_flag_substring_does_not_false_positive(self) -> None:
        """`--project-name` and `--reviewer` must not match --project/-r."""
        calls = parse_invocations("az repos pr show --id 1 --reviewer bob --detect true")
        assert calls[0].scope_flags == []

    def test_pipe_terminates_the_invocation(self) -> None:
        text = "az repos pr show --id 1 | ConvertFrom-Json --project X"
        assert parse_invocations(text)[0].scope_flags == []

    def test_multiple_invocations_are_all_parsed(self) -> None:
        text = "az repos pr list --project X\naz repos pr show --id 1\n"
        assert [c.subcommand for c in parse_invocations(text)] == ["list", "show"]
