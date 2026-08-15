"""Relevance-gate tests: which commands the guard decides to police.

Split from the former single ``tests/hooks/test_push_pr_script_identity_guard.py``
(issue #4764), which had grown to 2,077 lines and carried the whole policy
matrix for both harnesses in one module. Dispatcher runners, the payload shape,
and the temporary repository layout live in
``tests/hooks/push_pr_guard_harness.py`` so no module re-derives them.

Issue #5013 retired the guard from the generated Copilot shim tree
(dispatch_groups.json marks it copilotExclude, so the generator omits it).
Every case here now runs through the Claude dispatcher only, which is where
the guard still runs; invoke_dispatch_claude.py does not read
copilotExclude.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.hooks.push_pr_guard_harness import (
    RUNNERS as _RUNNERS,
)
from tests.hooks.push_pr_guard_harness import (
    repository as _repository,
)
from tests.hooks.push_pr_guard_harness import (
    write_script as _write_script,
)

IN_SCOPE_ASSIGNMENT = "PUSH_PR_SCRIPT=new_pr.py "


def _in_scope(command: str) -> str:
    """Return ``command`` placed inside the guard's relevance scope."""
    if "new_pr.py" in command:
        return command
    return IN_SCOPE_ASSIGNMENT + command


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git status && git diff",
        "git log --oneline -5",
        "git commit --allow-empty -m test",
        "git fetch origin",
        "git push origin HEAD",
        'bash -c "echo hello"',
        "sh -c 'ls'",
        'node -e "console.log(1)"',
        "perl -e 'print 1'",
        "python3 scripts/validation/pre_pr.py",
        "python3 -m pytest tests/",
        "uv run pytest tests/ -x",
        "uv run python -c 'print(1)'",
        "rg --files | head",
        "make build",
        "npm run lint",
        "eval 'echo hi'",
        "env LD_PRELOAD=/tmp/x.so ls",
        "echo *.py",
        "cat README.md",
        "ls -la",
    ],
)
def test_dispatchers_allow_commands_outside_guard_scope(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    """The relevance gate is non-blocking for every unrelated Bash command.

    The guard is registered on the plugin-wide `Bash` matcher. Before the gate
    it applied its deny policy first, so installing the plugin denied 15 of
    these 22 commands and disabled normal Bash workflows outside `/push-pr`
    (issue #4825, Copilot review 4894113215).
    """
    repository, _ = _repository(tmp_path)

    result = runner(command, repository)

    assert result.returncode == 0, f"{command}: {result.stderr}"


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize(
    "command",
    [
        "./attacker/pr/n{e..e..1}w_pr.py",
        "./attacker/pr/n{e..e}w_pr.py",
        # Leading-wildcard globs. A literal-prefix heuristic skipped these
        # because the prefix is empty, and a direct launch misses scope rules
        # B and C, so the guard returned 0 (issue #4825).
        "./attacker/pr/?ew_pr.py",
        "./attacker/pr/[!x]ew_pr.py",
        "./attacker/pr/n?w_pr.py",
        "./attacker/pr/*_pr.py",
        # ANSI-C quoting. Bash runs these as ./attacker/pr/new_pr.py while the
        # compaction stripped the backslash without decoding the escape,
        # producing newx5fpr.py (issue #4825).
        "./attacker/pr/$'new\\x5fpr.py'",
        # Compound commands. The relevance tokenizer rejects shell operators as
        # policy, and returning nothing on that rejection failed open: the
        # execution-position rules never ran (issue #4825).
        "./attacker/pr/?ew_pr.py && true",
        "true && ./attacker/pr/?ew_pr.py",
        "bash -c './attacker/pr/?ew_pr.py'",
        "./attacker/pr/new_pr.py; echo done",
        "echo x | ./attacker/pr/?ew_pr.py",
        # Redirections and quoted operators. The relevance splitter was neither
        # quote-aware nor redirection-aware, so both shapes skipped the only
        # segment and returned allow (issue #4825).
        "./attacker/pr/?ew_pr.py >out",
        "./attacker/pr/?ew_pr.py 2>/dev/null",
        "./attacker/pr/?ew_pr.py <in",
        "./attacker/pr/?ew_pr.py >out 2>&1",
        './attacker/pr/?ew_pr.py "x && y"',
        "./attacker/pr/new_pr.py >/dev/null",
        "./attacker/pr/$'new\\137pr.py'",
        "./attacker/pr/$'\\156ew_pr.py'",
        "./attacker/pr/new_pr{.py,.txt}",
        "./attacker/pr/n[e]w_pr.py",
        "./attacker/pr/new_pr.py",
    ],
)
def test_dispatchers_deny_direct_lookalike_execution(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    """A repository executable named new_pr.py is in scope however it is spelled.

    Scope rules B and C do not apply to a direct launch: there is no Python
    operand to resolve, and the lookalike's bytes differ from the trusted
    script. Only the naming rule catches it, so every expansion form that
    deterministically produces the name has to reach the policy.
    """
    repository, _ = _repository(tmp_path)
    lookalike = repository / "attacker" / "pr" / "new_pr.py"
    lookalike.parent.mkdir(parents=True)
    lookalike.write_text("#!/bin/sh\necho pwned\n", encoding="utf-8")
    lookalike.chmod(0o755)

    result = runner(command, repository)

    assert result.returncode == 2, f"{command}: allowed"
    assert "push-pr script identity denied" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize(
    "command",
    [
        "cp file{1..1000}.txt dir/",
        "echo {1..10000..7}",
        "seq 1 10 | xargs -I{} echo {}",
        # Data globs stay out of scope: an argument is not an execution
        # position, however closely it resembles the protected name.
        "ls src/*.py",
        "cat n?w_pr.py",
        # Benign ANSI-C quoting outside an execution position stays allowed.
        "echo $'hello\\x20world'",
        # Compound commands that cannot reach the script stay out of scope,
        # including an operator inside a quoted argument.
        "echo *.py && ls",
        'git commit -m "fix: a && b"',
        "cat README.md; git status",
        "make build && npm run lint",
        # Ordinary redirection must survive the redirection stripping.
        "ls > out.txt",
        "cat a.txt > b.txt",
        "make build 2>&1 | tee log",
        "echo hi > /dev/null",
        "cat n?w_pr.py > out",
        "mkdir -p build/{a,b,c}",
        "mv report{1..200}.csv archive/",
        "ls src/{lib,bin}/*.rs",
        "git checkout -- {a,b}.txt",
        "touch log{0..99}.txt",
        "echo {1..10000}",
    ],
)
def test_dispatchers_allow_legitimate_brace_expansion(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    """Ordinary brace usage stays out of scope, whatever the range size.

    Materializing ranges made a large one exceed the expansion budget, and the
    budget fails closed, so `touch log{0..99}.txt` and `cp file{1..1000}.txt`
    were denied. A probe measured 4 of these 7 denied before
    `_brace_alternatives` stopped materializing ranges.
    """
    repository, _ = _repository(tmp_path)

    result = runner(command, repository)

    assert result.returncode == 0, f"{command}: {result.stderr}"


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize(
    "command",
    [
        "python3 -I attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}",
        "python3 -I attacker/pr/n{a..z}w_pr.py",
        "python3 -I attacker/pr/n{d..f}w_pr.py",
        "python3 -I attacker/pr/ne{v..x}_pr.py",
        "python3 -I attacker/{n..n}ew_pr.py",
        "python3 -I attacker/pr/new_pr{.,.}py",
        "pypy3 attacker/pr/n[e]w_[p]r.[p][y]",
        "python3 -I attacker/{new_,old_}pr.py",
        # Bash's stepped range. Missing the step made _brace_alternatives read
        # "e..e..1" as literal text, so ./attacker/pr/n{e..e..1}w_pr.py, which
        # bash expands to the lookalike, skipped the guard entirely (#4825).
        "python3 -I attacker/pr/n{e..e..1}w_pr.py",
        "python3 -I attacker/pr/n{a..z..1}w_pr.py",
        "python3 -I attacker/pr/n{1..3..1}ew_pr.py",
    ],
)
def test_dispatchers_deny_range_obfuscated_new_pr(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    """Collapsing ranges must not lose a range that spells the target.

    A character range can supply a character new_pr.py needs, so the collapse
    keeps every character the target contains. `n{a..z}w_pr.py` and
    `n{d..f}w_pr.py` both still resolve to new_pr.py through 'e'.
    """
    repository, _ = _repository(tmp_path)

    result = runner(command, repository)

    assert result.returncode == 2, f"{command}: allowed"
    assert "push-pr script identity denied" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize(
    "command",
    [
        "python3 attacker/pr/new_pr.py --title fix",
        "python3 -I attacker/pr/new_pr.py --title fix",
        "bash -c 'python3 -I attacker/pr/new_pr.py'",
        "env -S 'python3 -I attacker/pr/new_pr.py'",
        "env --split-string='python3 -I attacker/pr/new_pr.py'",
        "sh -xc 'python3 -I attacker/pr/new_pr.py'",
        "python3 -I attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}",
        "python3 -I attacker/{new_,old_}pr.py --title fix",
        "pypy3 attacker/pr/n[e]w_[p]r.[p][y]",
        "python3 -I \"attacker/n$(printf ew_pr).py\"",
        "GIT_ALLOW_PROTOCOL=ext git ls-remote 'ext::./new_pr.py'",
        "git -c core.pager='python3 attacker/pr/new_pr.py' log",
        "python3 -c \"exec(open('attacker/pr/new_pr.py').read())\"",
    ],
)
def test_dispatchers_deny_commands_inside_guard_scope(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    """Every preserved bypass vector still fails closed once it names the script.

    Brace expansion, single-character glob classes, evaluator wrappers,
    `env -S` and `--split-string`, shell flag clusters, Git pager forms,
    `GIT_ALLOW_PROTOCOL=ext` and `ext::` transports each reach the deny policy
    through the relevance gate.
    """
    repository, _ = _repository(tmp_path)

    result = runner(command, repository)

    assert result.returncode == 2, f"{command}: allowed"
    assert "push-pr script identity denied" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_allow_dynamic_launcher_that_never_names_the_script(
    tmp_path: Path,
    runner,
) -> None:
    """Documented residual: a reconstructed path is outside the detection surface.

    See the guard module docstring, section "Residual risk". The guard bounds
    the identity of named push-pr invocations; it is not a Python sandbox. An
    actor able to run arbitrary Python does not need new_pr.py to open a pull
    request, and widening scope to cover this case is what denied every
    unrelated Bash command.
    """
    repository, _ = _repository(tmp_path)

    result = runner(
        "python3 -I -c '__import__(\"runpy\").run_path("
        'bytes.fromhex("61747461636b65722f70722f6e65775f70722e7079").decode(), '
        "run_name=\"__main__\")'",
        repository,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_allow_unrelated_compound_bash(
    tmp_path: Path,
    runner,
) -> None:
    """A compound command that cannot reach new_pr.py is out of scope.

    The parser rejects shell operators as policy, but policy only applies to
    commands this guard owns. Before the relevance gate the guard denied
    `git status && git diff` on the plugin-wide Bash matcher, which disabled
    normal Bash workflows for every plugin user (issue #4825 review
    4894113215).
    """
    repository, _ = _repository(tmp_path)

    result = runner("git status && git diff", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_deny_compound_bash_reaching_new_pr(
    tmp_path: Path,
    runner,
) -> None:
    """The same parser policy still fires once the command names new_pr.py."""
    repository, _ = _repository(tmp_path)

    result = runner(
        "python3 -I .claude/skills/github/scripts/pr/new_pr.py && git diff",
        repository,
    )

    assert result.returncode == 2
    assert "shell operators are not allowed" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_allow_unrelated_shell_expansion(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner("printf '%s\\n' file{1,2}.txt", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_allow_single_quoted_substitution_text(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner("printf '%s\\n' '$(not-a-command)'", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_allow_active_parameter_expansion_in_printf(
    tmp_path: Path,
    runner,
) -> None:
    """Parameter expansion in an unrelated command is out of scope."""
    repository, _ = _repository(tmp_path)

    result = runner("printf '%s\\n' \"${HOME}\"", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_deny_active_parameter_expansion_in_scope(
    tmp_path: Path,
    runner,
) -> None:
    """Expansion outside the allowlist still fails closed when in scope."""
    repository, _ = _repository(tmp_path)

    result = runner(_in_scope("printf '%s\\n' \"${HOME}\""), repository)

    assert result.returncode == 2
    assert "exact allowlist" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_allow_other_python_scripts(
    tmp_path: Path,
    runner,
) -> None:
    """An unrelated Python script with a resolvable operand is out of scope.

    The operand `tools/report.py` resolves to a file whose bytes are not
    new_pr.py, so scope rules A, B and C all miss and the command passes. The
    `$REPORT_NAME` expansion sits in a later argument, not the script operand,
    so it does not make the target unresolvable.
    """
    repository, _ = _repository(tmp_path)
    _write_script(repository / "tools" / "report.py")

    result = runner('python3 tools/report.py "$REPORT_NAME"', repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_deny_unresolvable_python_script_operand(
    tmp_path: Path,
    runner,
) -> None:
    """Scope rule B: an expanded script operand cannot be proven benign."""
    repository, _ = _repository(tmp_path)
    _write_script(repository / "tools" / "report.py")

    result = runner('python3 "$SCRIPT_PATH"', repository)

    assert result.returncode == 2
    assert "Python script paths cannot use shell expansion" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_allow_many_operands_without_hanging(
    tmp_path: Path,
    runner,
) -> None:
    """A large out-of-scope command must stay fast and stay allowed.

    Two earlier shapes of the fix above traded the leak for a hang or a false
    denial: scanning every token cost 5.6s, and failing closed on an exhausted
    budget denied ordinary commands and cost 10.2s on an 87 KiB input, past the
    host's 10s timeout where a Copilot timeout fails open.
    """
    repository, _ = _repository(tmp_path)
    command = "echo " + " ".join(f"f{index}.py" for index in range(2000))

    start = time.monotonic()
    result = runner(command, repository)
    elapsed = time.monotonic() - start

    assert result.returncode == 0, result.stderr
    assert elapsed < 5, f"took {elapsed:.1f}s, host timeout is 10s"
