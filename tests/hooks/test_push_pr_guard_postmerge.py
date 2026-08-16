"""Post-merge regression tests for the push-pr identity guard (issue #4764).

Each test here preserves a failure that was independently reproduced against
the merged tree at commit ``5cd72a7dad`` ("fix(hooks): enforce push-pr script
identity (#4825)"). The measured behavior is recorded in the docstring of each
test so a future reader can tell what the test is defending, and so a reviewer
can replay the measurement rather than trust this file.

Every case ran through both dispatchers before issue #5013 retired the guard
from the generated Copilot shim tree (dispatch_groups.json now marks it
copilotExclude, so the generator omits it). These regressions are guard
POLICY, so they run on the Claude dispatcher only from here on;
invoke_dispatch_claude.py does not read copilotExclude and keeps running the
guard unchanged.
"""

from __future__ import annotations

import shutil

import pytest

from tests.hooks.push_pr_guard_harness import (
    CLAUDE_PLUGIN_ROOT,
    REPO_ROOT,
    SCRIPT_RELATIVE,
    body_file,
    repository,
    run_claude,
)

# Commands that Bash expands onto the real new_pr.py through extglob. Bash
# only performs this expansion when `extglob` is enabled, and the guard cannot
# see the shell option, so it must treat the pattern as capable of naming the
# target. Measured on the merged tree with `bash -O extglob -c 'echo ...'`:
#
#     $ bash -O extglob -c 'echo src/copilot-cli/skills/github/scripts/pr/@(new)_pr.py'
#     src/copilot-cli/skills/github/scripts/pr/new_pr.py
#
# Both dispatchers returned 0 (allow) for the `python3 ...@(new)_pr.py` form.
EXTGLOB_EXECUTIONS = (
    "python3 src/copilot-cli/skills/github/scripts/pr/@(new)_pr.py --help",
    "python3 .claude/skills/github/scripts/pr/@(new)_pr.py --help",
    "python3 .claude/skills/github/scripts/pr/?(new)_pr.py --help",
    "python3 .claude/skills/github/scripts/pr/*(new)_pr.py --help",
    "python3 .claude/skills/github/scripts/pr/+(new)_pr.py --help",
    "./.claude/skills/github/scripts/pr/@(new)_pr.py",
)

# Extglob commands that cannot reach new_pr.py. These must keep working; the
# fix for the bypass above must not turn every extglob command into a denial.
UNRELATED_EXTGLOB = (
    "ls @(foo|bar).txt",
    "rm -f build/@(a|b|c).o",
    "echo @(one|two)",
    "cp report@(2024|2025).csv /tmp/",
    "python3 tools/@(build|check).py --quiet",
)

# Data-only references to new_pr.py. The path is an operand of a command that
# reads or names the file; nothing here executes it. Measured on the merged
# tree: both dispatchers returned 2 (deny) for the first two entries.
DATA_ONLY_REFERENCES = (
    "git diff -- .claude/skills/github/scripts/pr/new_pr.py",
    "python3 -m pytest tests/test_new_pr.py",
    "git log --oneline -- .claude/skills/github/scripts/pr/new_pr.py",
    "git status --short .claude/skills/github/scripts/pr/new_pr.py",
    "cat .claude/skills/github/scripts/pr/new_pr.py",
    "wc -l .claude/skills/github/scripts/pr/new_pr.py",
    "grep -n def .claude/skills/github/scripts/pr/new_pr.py",
    "ruff check .claude/skills/github/scripts/pr/new_pr.py",
    "git add .claude/skills/github/scripts/pr/new_pr.py",
    "python3 -m pytest tests/test_new_pr.py -k description",
)

# Execution paths the relevance narrowing MUST NOT weaken. Every entry either
# executes new_pr.py or hands it to something that can execute it.
PRESERVED_DENIALS = (
    # direct execution of a lookalike
    "python3 .claude/skills/github/scripts/pr/new_pr.py --title x --body-file b.md",
    # wrapped execution
    "env FOO=1 python3 .claude/skills/github/scripts/pr/new_pr.py",
    # shell evaluator payload
    "bash -c 'python3 .claude/skills/github/scripts/pr/new_pr.py'",
    # dynamic python launcher whose payload names the script
    "python3 -c \"import runpy; runpy.run_path('new_pr.py')\"",
    # loader environment pointed at the script
    "PYTHONSTARTUP=.claude/skills/github/scripts/pr/new_pr.py python3",
    # git execution delegation through the pager
    "git -c core.pager=.claude/skills/github/scripts/pr/new_pr.py log",
)


@pytest.mark.parametrize("command", EXTGLOB_EXECUTIONS)
def test_claude_denies_extglob_execution_of_new_pr(tmp_path, command) -> None:
    """Extglob patterns that Bash expands onto new_pr.py must be denied.

    Measured on the merged tree (both dispatchers returned 0):

        python3 src/copilot-cli/skills/github/scripts/pr/@(new)_pr.py --help

    ``@(...)`` and ``!(...)`` carry none of the ``? * [`` characters the guard
    treated as glob markers, so the pattern read as ordinary literal text that
    did not contain ``new_pr.py``. The command reached no relevance rule and
    the guard allowed it, while Bash with ``extglob`` enabled ran the real
    script.
    """
    root, _ = repository(tmp_path)

    claude = run_claude(command, root)

    assert claude.returncode == 2, f"claude allowed extglob bypass: {claude.stdout}"


@pytest.mark.parametrize("command", UNRELATED_EXTGLOB)
def test_claude_allows_extglob_unrelated_to_new_pr(tmp_path, command) -> None:
    """Ordinary extglob commands stay out of scope.

    The bypass fix widens what counts as a name for new_pr.py. It must not
    widen what counts as relevant: an extglob pattern that cannot expand onto
    new_pr.py is an ordinary command and the guard has no business denying it.
    """
    root, _ = repository(tmp_path)

    claude = run_claude(command, root)

    assert claude.returncode == 0, f"claude denied unrelated extglob: {claude.stderr}"


@pytest.mark.parametrize("command", DATA_ONLY_REFERENCES)
def test_claude_allows_data_only_references(tmp_path, command) -> None:
    """Naming new_pr.py in a data position is not an execution.

    Measured on the merged tree, both dispatchers returned 2:

        git diff -- .claude/skills/github/scripts/pr/new_pr.py
            -> "Python execution is limited to the approved new_pr.py"
        python3 -m pytest tests/test_new_pr.py
            -> "dynamic Python -c and -m launchers are not allowed"

    The first denial came from the interpreter search treating any operand
    whose shebang names Python as an interpreter, so a path handed to ``git``
    as data was classified as an execution. The second came from relevance
    matching ``new_pr.py`` as a substring of ``test_new_pr.py``.

    Both are false denials of routine developer commands, and a guard that
    blocks ``git diff`` and ``pytest`` is a guard that gets uninstalled.
    """
    root, _ = repository(tmp_path)

    claude = run_claude(command, root)

    assert claude.returncode == 0, f"claude falsely denied: {claude.stderr}"


@pytest.mark.parametrize("command", DATA_ONLY_REFERENCES)
def test_data_only_references_pass_against_the_real_repository(command) -> None:
    """The same commands, run against THIS repository rather than a fixture.

    The fixture in the test above writes a lookalike whose bytes differ from
    the shipped new_pr.py. That difference hid a live false denial: the
    renamed-copy rule compares operand CONTENT, and against the real tree the
    operand IS the trusted file byte for byte, so ``git diff --
    .../new_pr.py`` and ``ruff check .../new_pr.py`` were still denied while
    every fixture-based case reported success.

    A developer runs these commands in the real repository, so that is where
    the guard has to be measured. Keeping both parametrizations means a future
    change cannot satisfy one model of "execution position" while breaking the
    other.
    """
    claude = run_claude(command, REPO_ROOT)

    assert claude.returncode == 0, f"claude falsely denied in-repo: {claude.stderr}"


@pytest.mark.parametrize("command", PRESERVED_DENIALS)
def test_claude_still_denies_execution_paths(tmp_path, command) -> None:
    """Narrowing relevance to execution positions keeps every execution path denied.

    This is the inverse control for the false-denial fix. Each command reaches
    new_pr.py through a position that can execute it: directly, through a
    wrapper, through a shell evaluator, through a dynamic Python launcher,
    through a loader environment variable, or through Git's execution
    delegation. If narrowing relevance let any of these through, the fix
    traded a usability bug for a security hole.
    """
    root, _ = repository(tmp_path)
    body_file(root)

    claude = run_claude(command, root)

    assert claude.returncode == 2, f"claude allowed an execution path: {claude.stdout}"


# Pipelines whose reader prints an execution of new_pr.py into a program that
# runs it. Measured on this branch before the fix: every one returned 0 on both
# dispatchers, while the merged tree at 5cd72a7dad returned 2. The reader's
# operands are data TO THE READER and code to whatever consumes them, and
# narrowing relevance to execution positions dropped the pipe that connects
# the two.
#
#     $ bash -c 'echo /bin/echo EXECUTED-VIA-PIPE | sh'
#     EXECUTED-VIA-PIPE
PIPELINE_EXECUTIONS = (
    "echo python3 ./attacker/pr/new_pr.py | sh",
    "echo python3 ./attacker/pr/new_pr.py | bash",
    "echo ./attacker/pr/new_pr.py | xargs python3",
    "printf ./attacker/pr/new_pr.py | xargs python3",
    "ls ./attacker/pr/new_pr.py | xargs python3",
    # A pass-through reader in the middle still carries the text, so looking
    # only one segment ahead is not enough.
    "echo python3 ./attacker/pr/new_pr.py | tee /dev/null | sh",
    "echo python3 ./attacker/pr/new_pr.py | cat | cat | bash",
    "cat ./attacker/pr/new_pr.py | python3",
)


# Git subcommands that take a command line as an operand or an option value.
# Measured on this branch before the fix: 0 on both dispatchers, 2 on the
# merged tree. The relevance gate read only the per-subcommand OPTION table,
# so `bisect run` and `submodule foreach`, which carry no dash, never reached
# it, and the option table itself had no entry for the command-running options
# of rebase, filter-branch, difftool, or send-email.
GIT_COMMAND_RUNNER_EXECUTIONS = (
    'git submodule foreach "python3 ./attacker/pr/new_pr.py"',
    "git submodule foreach --recursive python3 ./attacker/pr/new_pr.py",
    "git bisect run python3 ./attacker/pr/new_pr.py",
    'git rebase -x "python3 ./attacker/pr/new_pr.py" main',
    'git filter-branch --tree-filter "python3 ./attacker/pr/new_pr.py" HEAD',
    'git difftool -x "python3 ./attacker/pr/new_pr.py"',
    'git send-email --smtp-server="python3 ./attacker/pr/new_pr.py" x',
)


# Pipelines that only read. Each names new_pr.py in an operand and ends in a
# reader, so the pipe rule must leave them alone. Without these the pipe fix
# could be satisfied by treating every pipeline as an execution, which would
# reintroduce the false denials the branch exists to fix.
PIPELINE_READS = (
    "git diff -- .claude/skills/github/scripts/pr/new_pr.py | cat",
    "git diff -- .claude/skills/github/scripts/pr/new_pr.py | cat | head -5",
    "cat .claude/skills/github/scripts/pr/new_pr.py | head -20",
    "grep -n import .claude/skills/github/scripts/pr/new_pr.py | wc -l",
)


@pytest.mark.parametrize("command", PIPELINE_EXECUTIONS + GIT_COMMAND_RUNNER_EXECUTIONS)
def test_claude_denies_delegated_execution_of_new_pr(tmp_path, command) -> None:
    """A path handed to a program runner is an execution, whatever segment it sits in.

    Both families reach new_pr.py without ever naming it in a command
    position of its own segment: a pipeline hands it to the next program's
    stdin, and Git hands it to the command runner behind `bisect run`,
    `submodule foreach`, `rebase -x`, `filter-branch --tree-filter`,
    `difftool -x`, or `send-email --smtp-server`.

    These are regressions this branch introduced, not defects of the merged
    tree: narrowing relevance to execution positions fixed the false denials
    and lost the delegation edges. The merged guard denied every command
    listed here, measured directly against its own file.
    """
    root, _ = repository(tmp_path)
    body_file(root)

    claude = run_claude(command, root)

    assert claude.returncode == 2, f"claude allowed delegated execution: {claude.stdout}"


@pytest.mark.parametrize("command", PIPELINE_READS)
def test_claude_allows_pipelines_that_only_read(command) -> None:
    """Inverse control: a pipeline that ends in a reader stays out of scope.

    The pipe rule asks whether the text a segment prints reaches a program
    runner. Every command here ends in `cat`, `head`, or `wc`, so the answer
    is no and the reference stays data.
    """
    claude = run_claude(command, REPO_ROOT)

    assert claude.returncode == 0, f"claude falsely denied a read pipeline: {claude.stderr}"


# A consumer the lexer cannot tokenize still occupies its place in the
# pipeline. `(` and `)` are shell operators `_split_command` rejects, so the
# segment used to be dropped from the list, the index walk ran off the end,
# and the pipe relation read as "nothing consumes this". Measured allowed on
# both dispatchers here and denied by the merged guard; the pipeline does run:
#
#     $ bash -c 'echo python3 exectest/new_pr.py | (sh)'
#     EXECUTED new_pr
UNPARSEABLE_CONSUMER_EXECUTIONS = (
    "echo python3 ./attacker/pr/new_pr.py | (sh)",
    "echo python3 ./attacker/pr/new_pr.py | ( sh )",
    "echo python3 ./attacker/pr/new_pr.py | (cat; sh)",
    "echo python3 ./attacker/pr/new_pr.py | tee /dev/null | (sh)",
    "echo python3 ./attacker/pr/new_pr.py | (sh) | cat",
)


@pytest.mark.parametrize("command", UNPARSEABLE_CONSUMER_EXECUTIONS)
def test_claude_denies_pipelines_into_an_unparseable_consumer(tmp_path, command) -> None:
    """A pipeline consumer the guard cannot read must be assumed to execute.

    The guard has no parser for a subshell, so it cannot name what the segment
    runs. Reading that as "not an executor" sells an allow for one pair of
    parentheses.
    """
    root, _ = repository(tmp_path)
    body_file(root)

    claude = run_claude(command, root)

    assert claude.returncode == 2, f"claude allowed a subshell consumer: {claude.stdout}"


def test_claude_allows_a_subshell_that_reaches_nothing(tmp_path) -> None:
    """Inverse control: an unparseable segment is not itself a reason to deny.

    Failing closed on the pipe relation must not turn every subshell into a
    denial, or `(git status)` and `echo hi | (cat)` stop working.
    """
    root, _ = repository(tmp_path)
    body_file(root)

    for command in ("(git status)", "echo hi | (cat)", "(cd /tmp && ls)"):
        claude = run_claude(command, root)

        assert claude.returncode == 0, f"claude denied {command}: {claude.stderr}"


def test_claude_denies_a_renamed_copy_handed_to_a_pipeline(tmp_path) -> None:
    """Scope rule C must see the operands the pipe rule opened up.

    The pipe fix threaded the reader exemption into the path rule but not into
    the byte-identical-copy rule, so renaming the copy defeated it: the
    basename rule misses a different name and the copy rule was still looking
    only at execution positions of the reader's own segment. Measured allowed
    on both dispatchers and denied by the merged guard.
    """
    root, _ = repository(tmp_path)
    body_file(root)
    shutil.copy2(CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE, root / "tools_copy.py")

    for command in (
        "echo python3 tools_copy.py | sh",
        "echo python3 tools_copy.py | bash",
        "echo python3 tools_copy.py | tee /dev/null | sh",
    ):
        claude = run_claude(command, root)

        assert claude.returncode == 2, f"claude allowed a piped renamed copy: {claude.stdout}"
