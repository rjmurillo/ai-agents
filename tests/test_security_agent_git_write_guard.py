"""Enforcement for the read-only-git limit the security agent's prompt states.

Issue #4781 gave the `security` subagent Bash so it could enumerate a diff. A
read-only *subcommand* is not a read-only *command*: `git diff`, `git log`,
`git show`, and `git blame` all accept `--output=<path>`, which writes the
subcommand's output to any path the caller names. Probed on git 2.43.0 in this
repository, all four wrote the file and exited 0. `git -c diff.external=<cmd>`
is worse: it runs `<cmd>`, so a grant that stops at the subcommand name hands
out arbitrary command execution, not just an arbitrary file write.

The agent prompt states these limits as obligations. An obligation is not a
control, so this module pins the control: the `permissions.deny` rules in
`.claude/settings.json`. Deny is the right layer because Claude Code evaluates
deny rules ahead of everything else. From the permissions reference: "Hook
decisions don't bypass permission rules... a matching deny rule blocks the
call", which "preserves the deny-first precedence". It is also the placement
`.claude/rules/tool-use-hook-bar.md` MUST 2 requires be ruled out first, a
host-native declarative surface, before anyone proposes the `PreToolUse` hook
that ADR-097 gates behind an ADR review.

`_denied_by` below models the documented matcher rather than trusting the rule
strings to read correctly. Every production assertion runs through it, and the
control classes at the bottom feed it deliberately defective rule sets, so a
matcher that stops detecting fails its own control instead of passing silently.

Matcher contract, from https://code.claude.com/docs/en/permissions:

- "Bash rules match the whole command text, with `*` standing in for any text."
- "A `*` in a Bash rule matches any text, including spaces." It may appear "at
  the start, in the middle, or at the end."
- "A deny or ask rule matches past any leading assignment, so `Bash(rm *)` in
  deny still matches `FOO=bar rm -rf tmp/`."
- Compound commands split on `&&`, `||`, `;`, `|`, `|&`, `&`, and newlines, and
  a rule "must match each subcommand independently".
- A fixed wrapper set is stripped before matching: `timeout`, `time`, `nice`,
  `nohup`, `stdbuf`, `command`, `builtin`, `noglob`, and bare `xargs`.

The reference's own wildcard table lists `git log --output=<file> main` as a
command that `Bash(git log * main)` matches, so the write reach of these
subcommands is documented vendor behavior, not an inference drawn here.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SETTINGS = REPO_ROOT / ".claude" / "settings.json"

# Separators the reference lists for compound commands.
_SEPARATORS = re.compile(r"\|\&|\&\&|\|\||[;|&\n]")

# Wrappers Claude Code strips before matching, each of which runs its argument
# as the real command.
_WRAPPERS = frozenset(
    {"timeout", "time", "nice", "nohup", "stdbuf", "command", "builtin", "noglob"}
)

# `NAME=value` prefixes. Deny rules match past these.
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")

# Wrappers that take a positional argument of their own before the real
# command: `timeout 30 git ...`, `nice 10 git ...`. Stripping the wrapper alone
# would leave that argument at the head and defeat the anchored literal.
_WRAPPERS_WITH_OPERAND = frozenset({"timeout", "nice"})
_DURATION = re.compile(r"^-?\d+(\.\d+)?[smhd]?$")


def _rule_body(rule: str) -> str | None:
    """Return the pattern inside `Bash(...)`, or None for a non-Bash rule."""
    match = re.fullmatch(r"Bash\((.*)\)", rule, re.DOTALL)
    return match.group(1) if match else None


def _normalize(command: str) -> str:
    """Strip the wrappers and leading assignments the reference strips."""
    tokens = command.split()
    while tokens:
        head = tokens[0]
        if _ASSIGNMENT.fullmatch(head):
            tokens = tokens[1:]
            continue
        if head in _WRAPPERS:
            tokens = tokens[1:]
            # Drop the wrapper's own flags, then its operand where it takes one.
            while tokens and tokens[0].startswith("-"):
                tokens = tokens[1:]
            if head in _WRAPPERS_WITH_OPERAND:
                # `timeout -k 5 30s cmd` leaves two numeric operands once the
                # flags are gone, so consume every numeric token, not just one.
                while tokens and _DURATION.fullmatch(tokens[0]):
                    tokens = tokens[1:]
            continue
        # Bare `xargs` is stripped; `xargs` carrying flags is not.
        if head == "xargs" and len(tokens) > 1 and not tokens[1].startswith("-"):
            tokens = tokens[1:]
            continue
        break
    return " ".join(tokens)


def _pattern_matches(pattern: str, command: str) -> bool:
    """Apply one Bash rule pattern to one already-normalized subcommand."""
    regex = "".join(".*" if part == "*" else re.escape(part) for part in re.split(r"(\*)", pattern))
    if re.fullmatch(regex, command):
        return True
    # "A `*` at the end, with a space before it, also matches the bare command",
    # but only when that trailing `*` is the rule's only wildcard.
    if pattern.endswith(" *") and pattern.count("*") == 1:
        return command == pattern[:-2]
    return False


def _denied_by(command: str, rules: list[str]) -> list[str]:
    """Every rule in *rules* that blocks *command*.

    A deny rule matching any single subcommand blocks the whole compound
    command, so this checks each subcommand against each rule.
    """
    subcommands = [_normalize(part.strip()) for part in _SEPARATORS.split(command)]
    return [
        rule
        for rule in rules
        if (body := _rule_body(rule)) is not None
        and any(sub and _pattern_matches(body, sub) for sub in subcommands)
    ]


def _deny_rules() -> list[str]:
    return json.loads(SETTINGS.read_text(encoding="utf-8"))["permissions"]["deny"]


# Commands that write a file or run a program despite naming a read-only git
# subcommand. Every one of these was probed against git 2.43.0; the four
# `--output` forms wrote their target and the `diff.external` form executed.
ARBITRARY_WRITE_EXPLOITS = (
    "git diff HEAD~1 --output=/tmp/pwned.txt",
    "git diff HEAD~1 --output /tmp/pwned.txt",
    "git diff --output=/tmp/pwned.txt",
    "git log -1 --output=/tmp/pwned.txt",
    "git show HEAD --output=/tmp/pwned.txt",
    "git blame --output=/tmp/pwned.txt README.md",
    "git diff  HEAD~1  --output=/tmp/pwned.txt",
    "git format-patch -1 --output-directory=/tmp/pwned",
)

ARBITRARY_EXECUTION_EXPLOITS = (
    "git -c diff.external='touch /tmp/pwned' diff HEAD~1",
    "git -c core.pager=/tmp/evil.sh log -1",
    "git -c core.sshCommand=/tmp/evil.sh log -1",
    "git -c core.fsmonitor=/tmp/evil.sh diff",
    "git -c diff.evil.textconv=/tmp/evil.sh diff",
    "git -c uploadpack.packObjectsHook=/tmp/evil.sh log",
    "git --exec-path=/tmp/evil diff HEAD~1",
)

ALL_EXPLOITS = ARBITRARY_WRITE_EXPLOITS + ARBITRARY_EXECUTION_EXPLOITS

# Evasion shapes that must not slip past on a technicality: a leading
# assignment, a stripped wrapper, or a compound command that hides the exploit
# behind a benign first subcommand.
EVASION_EXPLOITS = (
    "FOO=bar git diff HEAD~1 --output=/tmp/pwned.txt",
    "timeout 30 git diff HEAD~1 --output=/tmp/pwned.txt",
    "git status --porcelain && git diff HEAD~1 --output=/tmp/pwned.txt",
    "git status; git log -1 --output=/tmp/pwned.txt",
)

# The seven read-only invocations the enumeration protocol actually needs. A
# rule set that blocks any of these reinstates issue #4781 by another route,
# and a wrong deny on Bash is the #5013 failure mode that
# `.claude/rules/tool-use-hook-bar.md` exists to prevent.
PROTOCOL_COMMANDS = (
    "git status --porcelain",
    "git diff",
    "git diff origin/main...HEAD",
    "git diff HEAD~1",
    "git log --oneline -20",
    "git show HEAD",
    "git rev-parse HEAD",
    "git ls-files",
    "git blame README.md",
    "git diff --stat",
    "git log --format=%H -1",
)

# Everyday git this repository's other agents run. `.claude/settings.json` is
# session-wide, not subagent-scoped, so these rules reach every agent and must
# not disturb normal work. `git -c core.hooksPath=...` is load-bearing in
# `tests/conftest.py` and `git -C <dir>` in the worktree workflows, which is
# why neither `git -c` nor `git -C` is denied wholesale.
NEIGHBOURING_COMMANDS = (
    "git commit -m 'fix: thing'",
    "git push origin HEAD",
    "git -C /root/src/scratch/worktrees/wt status",
    "git -c core.hooksPath=/abs push",
    "git worktree add --detach /tmp/wt HEAD",
    "ruff check --output-format=github -- src",
    "az repos pr list --output json",
)

# The four mutating subcommands issue #4781's acceptance criterion names, in
# the shapes this repository actually runs them. They are deliberately NOT in
# `permissions.deny`; the test below pins that absence so the next reader does
# not close the gap by breaking the repository.
#
# There is no narrower placement available. A subagent has no permission
# surface of its own: https://code.claude.com/docs/en/sub-agents lists every
# supported frontmatter field, and the only permission-adjacent three are
# `tools`, `disallowedTools`, and `permissionMode`. None carries a rule.
# `tools` and `disallowedTools` add or remove a whole tool, so the finest cut
# they can express is "the security agent gets no Bash at all", which is issue
# #4781's symptom. `permissionMode` selects how prompts are handled, not what
# is denied. Deny rules therefore live only in the settings files, which are
# scoped to a project or a user, never to one agent.
#
# Denying these session-wide would stop every other agent and this repository's
# own automation. `git commit` and `git push` are the `AGENTS.md` End gate.
# `git checkout` is emitted verbatim by `scripts/ci/mutation_harness_ciperms.py:113`
# and reached through the `_git` helper in `scripts/ci/prepare_conflict_context.py`
# and `scripts/ci/apply_ai_conflict_resolution.py`. That is the #5013 shape a wrong
# deny on `Bash` produces: 127 unrelated commands denied over 21 minutes, per
# the incident record in `.claude/rules/tool-use-hook-bar.md`.
MUTATING_GIT_THE_PROMPT_FORBIDS = (
    "git commit -m 'fix: thing'",
    "git commit --amend --no-edit",
    "git push origin HEAD",
    "git push --force-with-lease origin HEAD",
    "git checkout -- README.md",
    "git checkout -b feat/thing",
    "git reset --hard HEAD",
    "git reset HEAD~1",
)


@pytest.mark.parametrize("command", ALL_EXPLOITS)
def test_deny_rules_block_every_probed_exploit(command: str) -> None:
    """Each command that writes a file or runs a program is denied."""
    assert _denied_by(command, _deny_rules()), (
        f"{command!r} reaches the shell. It names a read-only git subcommand but "
        f"writes a file or executes a program (issue #4781). Add a "
        f"permissions.deny rule to .claude/settings.json that covers it."
    )


@pytest.mark.parametrize("command", EVASION_EXPLOITS)
def test_deny_rules_survive_the_documented_evasion_shapes(command: str) -> None:
    """Assignments, wrappers, and compound commands do not launder an exploit."""
    assert _denied_by(command, _deny_rules()), (
        f"{command!r} slips the denylist. Deny rules match past leading "
        f"assignments and stripped wrappers, and block a compound command when "
        f"any subcommand matches, so this shape must not be a way through."
    )


@pytest.mark.parametrize("command", PROTOCOL_COMMANDS)
def test_deny_rules_leave_the_enumeration_protocol_working(command: str) -> None:
    """The read-only git the protocol needs still runs."""
    assert not _denied_by(command, _deny_rules()), (
        f"{command!r} is denied. The Review Scope Enumeration protocol calls "
        f"this command, so denying it reinstates issue #4781's symptom."
    )


@pytest.mark.parametrize("command", NEIGHBOURING_COMMANDS)
def test_deny_rules_do_not_reach_unrelated_work(command: str) -> None:
    """No wrong deny on the git every other agent in the session runs."""
    assert not _denied_by(command, _deny_rules()), (
        f"{command!r} is denied. permissions.deny in .claude/settings.json is "
        f"session-wide, not scoped to the security subagent, so an overbroad "
        f"rule takes out unrelated work (the #5013 failure mode)."
    )


@pytest.mark.parametrize("command", MUTATING_GIT_THE_PROMPT_FORBIDS)
def test_mutating_git_stays_an_obligation_not_a_control(command: str) -> None:
    """`commit`, `push`, `checkout`, and `reset` are prose limits, not denials.

    Issue #4781's acceptance criterion reads "commit, push, and
    branch-mutation capabilities remain unavailable". On the Claude surfaces
    that is a prompt obligation the agent holds, not a control the harness
    enforces, and this test is the honest pin on that gap rather than a
    silence. See the comment on `MUTATING_GIT_THE_PROMPT_FORBIDS` for why the
    denial cannot be scoped to one subagent and what denying it session-wide
    would cost.

    If Claude Code ever gains a per-subagent permission surface, this test is
    the one to delete, and the deny rules move there rather than into
    `.claude/settings.json`.
    """
    assert not _denied_by(command, _deny_rules()), (
        f"{command!r} is denied in .claude/settings.json. That file has no "
        f"subagent scope, so this denies the command for every agent and for "
        f"the repository's own commit, push, and conflict-resolution "
        f"automation. Enforce the limit with a subagent-scoped PreToolUse "
        f"hook under ADR-097 review, not with a session-wide deny."
    )


def test_the_matcher_would_catch_a_session_wide_mutation_deny() -> None:
    """Negative control: the test above is not vacuous.

    It asserts an absence, so it would pass against a matcher that had stopped
    detecting anything. This proves the matcher still fires on the exact rules
    the test exists to keep out of `.claude/settings.json`.
    """
    hypothetical = [
        "Bash(git commit *)",
        "Bash(git push *)",
        "Bash(git checkout *)",
        "Bash(git reset *)",
    ]

    undetected = [
        command
        for command in MUTATING_GIT_THE_PROMPT_FORBIDS
        if not _denied_by(command, hypothetical)
    ]

    assert undetected == [], (
        f"The matcher does not detect a whole-subcommand deny for: {undetected}. "
        f"Until it does, the absence assertion above proves nothing."
    )


def test_every_deny_rule_is_a_wellformed_bash_rule() -> None:
    """A malformed rule silently enforces nothing."""
    malformed = [rule for rule in _deny_rules() if _rule_body(rule) is None]

    assert malformed == [], (
        f"Not parseable as Bash(...) rules: {malformed}. Claude Code warns at "
        f"startup for a deny rule whose tool name matches no known tool, and "
        f"such a rule enforces nothing."
    )


def test_output_flag_is_denied_for_every_granted_read_subcommand() -> None:
    """`--output` is closed on all seven subcommands the prompt grants."""
    granted = ("status", "diff", "show", "log", "rev-parse", "ls-files", "blame")
    rules = _deny_rules()
    reachable = [
        sub
        for sub in granted
        if not _denied_by(f"git {sub} --output=/tmp/pwned.txt", rules)
    ]

    assert reachable == [], (
        f"`--output` still reaches these granted subcommands: {reachable}. The "
        f"grant is by subcommand, so a flag denylist must cover all of them "
        f"rather than only the ones probed as exploitable today."
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_output_flag_really_writes_a_file(tmp_path: Path) -> None:
    """Live control: the hazard the deny rules exist for is real.

    This runs the exploit for real in a throwaway repository. If a future git
    stops honoring `--output` on `git diff`, this test fails and says the guard
    may be retired. Until then it is the evidence that the denylist guards
    something, not a hypothetical.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=False
        )

    run("init", "-q")
    run("config", "user.email", "test@example.invalid")
    run("config", "user.name", "Test")
    (repo / "file.txt").write_text("one\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-qm", "first")
    (repo / "file.txt").write_text("two\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-qm", "second")

    target = tmp_path / "outside" / "pwned.txt"
    target.parent.mkdir()
    exploit = ["diff", "HEAD~1", f"--output={target}"]
    result = run(*exploit)

    assert result.returncode == 0 and target.exists(), (
        "git diff --output did not write its target, so the hazard these deny "
        "rules guard may no longer exist. Re-probe before relaxing them."
    )
    assert _denied_by(f"git diff HEAD~1 --output={target}", _deny_rules()), (
        "The exact command just proven to write outside the repository is not "
        "covered by permissions.deny in .claude/settings.json."
    )


class TestMatcherDetectsAbsentCoverage:
    """Negative controls: `_denied_by` must fail an inadequate rule set."""

    def test_empty_rule_set_denies_nothing(self) -> None:
        assert _denied_by(ARBITRARY_WRITE_EXPLOITS[0], []) == []

    def test_subcommand_only_rule_misses_the_output_flag(self) -> None:
        """The shape the first repair shipped: scope by subcommand, not by flag."""
        assert _denied_by("git diff HEAD~1 --output=/tmp/pwned.txt", ["Bash(git diff *)"])
        assert _denied_by("git diff HEAD~1 --output=/tmp/pwned.txt", ["Bash(git log *)"]) == []

    def test_prefix_only_output_rule_misses_a_flag_placed_later(self) -> None:
        """`Bash(git --output*)` looks right and catches nothing real."""
        assert (
            _denied_by("git diff HEAD~1 --output=/tmp/pwned.txt", ["Bash(git --output*)"])
            == []
        )

    def test_non_bash_rule_is_ignored(self) -> None:
        assert _denied_by(ARBITRARY_WRITE_EXPLOITS[0], ["Read(./.env)"]) == []

    def test_matcher_accepts_a_covering_rule(self) -> None:
        assert _denied_by(
            "git diff HEAD~1 --output=/tmp/pwned.txt", ["Bash(git *--output*)"]
        )


class TestMatcherSemantics:
    """Negative controls on the documented matcher rules themselves."""

    def test_star_spans_spaces(self) -> None:
        assert _pattern_matches("git *--output*", "git diff HEAD~1 --output=/x")

    def test_literal_before_first_star_is_anchored(self) -> None:
        assert not _pattern_matches("git *--output*", "hg diff --output=/x")

    def test_trailing_star_also_matches_the_bare_command(self) -> None:
        assert _pattern_matches("ls *", "ls")

    def test_trailing_star_bare_match_needs_a_sole_wildcard(self) -> None:
        assert not _pattern_matches("* --help *", "npm --help")

    def test_leading_assignment_is_stripped(self) -> None:
        assert _normalize("FOO=bar rm -rf tmp/") == "rm -rf tmp/"

    def test_wrapper_is_stripped(self) -> None:
        assert _normalize("nohup git diff") == "git diff"

    def test_wrapper_operand_is_stripped_with_the_wrapper(self) -> None:
        """The reference's own example: `Bash(npm test *)` matches
        `timeout 30 npm test`, so the `30` cannot survive the strip."""
        assert _normalize("timeout 30 git diff") == "git diff"
        assert _normalize("timeout -k 5 30s git diff") == "git diff"

    def test_flagged_xargs_is_not_stripped(self) -> None:
        assert _normalize("xargs -n1 grep pattern") == "xargs -n1 grep pattern"

    def test_compound_command_splits_on_every_documented_separator(self) -> None:
        for separator in ("&&", "||", ";", "|", "&", "\n"):
            command = f"git status {separator} git diff --output=/x"
            assert _denied_by(command, ["Bash(git *--output*)"]), separator
