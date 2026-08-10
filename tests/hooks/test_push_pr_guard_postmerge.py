"""Post-merge regression tests for the push-pr identity guard (issue #4764).

Each test here preserves a failure that was independently reproduced against
the merged tree at commit ``5cd72a7dad`` ("fix(hooks): enforce push-pr script
identity (#4825)"). The measured behavior is recorded in the docstring of each
test so a future reader can tell what the test is defending, and so a reviewer
can replay the measurement rather than trust this file.

Every case runs through BOTH dispatchers, because the guard ships twice: once
as the canonical Claude hook and once as the generated Copilot matcher shim.
A fix applied to only one surface is a half fix.
"""

from __future__ import annotations

import pytest

from tests.hooks.push_pr_guard_harness import body_file, repository, run_claude, run_copilot

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
def test_dispatchers_deny_extglob_execution_of_new_pr(tmp_path, command) -> None:
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
    copilot = run_copilot(command, root)

    assert claude.returncode == 2, f"claude allowed extglob bypass: {claude.stdout}"
    assert copilot.returncode == 2, f"copilot allowed extglob bypass: {copilot.stdout}"


@pytest.mark.parametrize("command", UNRELATED_EXTGLOB)
def test_dispatchers_allow_extglob_unrelated_to_new_pr(tmp_path, command) -> None:
    """Ordinary extglob commands stay out of scope.

    The bypass fix widens what counts as a name for new_pr.py. It must not
    widen what counts as relevant: an extglob pattern that cannot expand onto
    new_pr.py is an ordinary command and the guard has no business denying it.
    """
    root, _ = repository(tmp_path)

    claude = run_claude(command, root)
    copilot = run_copilot(command, root)

    assert claude.returncode == 0, f"claude denied unrelated extglob: {claude.stderr}"
    assert copilot.returncode == 0, f"copilot denied unrelated extglob: {copilot.stderr}"


@pytest.mark.parametrize("command", DATA_ONLY_REFERENCES)
def test_dispatchers_allow_data_only_references(tmp_path, command) -> None:
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
    copilot = run_copilot(command, root)

    assert claude.returncode == 0, f"claude falsely denied: {claude.stderr}"
    assert copilot.returncode == 0, f"copilot falsely denied: {copilot.stderr}"


@pytest.mark.parametrize("command", PRESERVED_DENIALS)
def test_dispatchers_still_deny_execution_paths(tmp_path, command) -> None:
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
    copilot = run_copilot(command, root)

    assert claude.returncode == 2, f"claude allowed an execution path: {claude.stdout}"
    assert copilot.returncode == 2, f"copilot allowed an execution path: {copilot.stdout}"
