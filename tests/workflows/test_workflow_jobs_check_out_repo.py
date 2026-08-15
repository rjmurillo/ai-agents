"""Every job that runs a repo file must check the repository out first.

Found the hard way. ``nightly-cli-smoke.yml``'s reporter job ran
``python3 scripts/ci/require_job_results.py`` with no checkout step, so it died
with ``Errno 2 No such file or directory`` on six consecutive nightly runs and
masked the real smoke result behind a file-not-found.

The ADR-006 campaign moves shell out of ``run:`` blocks and into repo scripts,
which converts jobs that needed no checkout into jobs that do. Nothing else
catches the omission before it reaches a runner, and a job whose only purpose
is reporting can stay broken for a long time before anyone reads the log.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
import yaml

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github/workflows"
REPO_ROOT = Path(__file__).resolve().parents[2]

# Lines that only print a path do not need the file to exist.
_PRINTING = re.compile(r"^\s*(echo|printf|cat\s+<<|#)")
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SHELL_CONTROL_TOKENS = frozenset({"&&", "||", ";", "|"})
_WORKSPACE_PREFIX_FORMS = (
    '--prefix="$GITHUB_WORKSPACE/"',
    '--prefix="${GITHUB_WORKSPACE}/"',
    '--prefix "$GITHUB_WORKSPACE/"',
    '--prefix "${GITHUB_WORKSPACE}/"',
)

# A token is a repo reference when it looks like a relative path into one of
# these trees. Anchored so an unrelated argument cannot match.
_REPO_PATH = re.compile(r"^\.?/?(scripts|build|\.github/scripts|\.github/actions)/\S+")


def _workflows() -> list[Path]:
    return sorted(p for p in WORKFLOW_DIR.glob("*.y*ml"))


def _jobs(doc: object) -> dict[str, dict]:
    if not isinstance(doc, dict):
        return {}
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return {}
    return {name: job for name, job in jobs.items() if isinstance(job, dict)}


def _tokenize_command_line(line: str) -> list[str]:
    """Tokenize one shell line, skipping printing/comment lines entirely.

    Returns an empty token list for ``echo``/``printf``/comment lines so
    callers never mistake a documentation string for an executed command.
    """
    if _PRINTING.match(line):
        return []
    try:
        return shlex.split(line, comments=True)
    except ValueError:
        return line.split()


def _logical_shell_commands(run_text: str) -> list[str]:
    commands: list[str] = []
    current = ""
    for line in run_text.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            current += f"{stripped[:-1]} "
            continue
        commands.append(f"{current}{line}")
        current = ""
    if current:
        commands.append(current)
    return commands


def _shell_command_segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SHELL_CONTROL_TOKENS:
            if segments[-1]:
                segments.append([])
            continue
        segments[-1].append(token)
    return [segment for segment in segments if segment]


def _strip_environment_assignments(tokens: list[str]) -> list[str]:
    first_command = 0
    while first_command < len(tokens) and _ENV_ASSIGNMENT.match(tokens[first_command]):
        first_command += 1
    return tokens[first_command:]


def repo_paths_in_run(run: str) -> list[str]:
    """Return repo-relative paths the block actually executes or reads.

    Skips ``echo``/``printf``/comment lines, where a path is documentation
    rather than a dependency. That distinction is the whole reason this is a
    parser and not a substring search.
    """
    found: list[str] = []
    for line in run.splitlines():
        for token in _tokenize_command_line(line):
            if _REPO_PATH.match(token):
                found.append(token.lstrip("./"))
    return found


def _checkout_index_effect(line: str, in_workspace: bool) -> tuple[bool, bool]:
    """Return whether ``line`` checks out into the workspace and its final cwd state.

    Uses the same tokenizer as ``repo_paths_in_run`` so an ``echo`` or a
    comment that merely mentions ``git checkout-index`` is never mistaken
    for the command actually running. Requires ``checkout-index`` to be
    immediately preceded by a ``git`` token (as in ``git checkout-index``
    or ``GIT_INDEX_FILE=... git checkout-index``), not merely present
    anywhere in the token list: a line such as
    ``python3 -c '...' checkout-index`` passes the literal string
    ``checkout-index`` as an unrelated CLI argument and must not be
    mistaken for the git subcommand that actually materializes the repo
    (PR #4846 review, thread on this exact substring-vs-subcommand gap).
    """
    tokens = _tokenize_command_line(line)
    for segment in _shell_command_segments(tokens):
        assignments = {
            token.split("=", 1)[0]: token.split("=", 1)[1]
            for token in segment
            if _ENV_ASSIGNMENT.match(token)
        }
        command = _strip_environment_assignments(segment)
        if command[:1] == ["cd"] and len(command) > 1:
            in_workspace = command[1] in {
                ".",
                "./",
                "$GITHUB_WORKSPACE",
                "${GITHUB_WORKSPACE}",
            }
            continue
        if command[:2] != ["git", "checkout-index"]:
            continue
        work_tree = assignments.get("GIT_WORK_TREE")
        effective_workspace = in_workspace
        if work_tree is not None:
            effective_workspace = work_tree in {
                ".",
                "./",
                "$GITHUB_WORKSPACE",
                "${GITHUB_WORKSPACE}",
            }
        command_tokens = command[2:]
        for option_index, token in enumerate(command_tokens):
            if token.startswith("--prefix="):
                checks_out_workspace = effective_workspace and any(
                    form in line for form in _WORKSPACE_PREFIX_FORMS
                )
                return checks_out_workspace, in_workspace
            if token == "--prefix" and option_index + 1 < len(command_tokens):
                checks_out_workspace = effective_workspace and any(
                    form in line for form in _WORKSPACE_PREFIX_FORMS
                )
                return checks_out_workspace, in_workspace
        return False, in_workspace
    return False, in_workspace


def first_unmet_repo_dependency(job: dict) -> tuple[str, str] | None:
    """Return (step label, dependency) for the first step needing an absent checkout."""
    checked_out = False
    in_workspace = True
    for step in job.get("steps") or []:
        if not isinstance(step, dict):
            continue
        uses = str(step.get("uses") or "")
        if uses.startswith("actions/checkout"):
            checked_out = True
            continue
        label = str(step.get("name") or uses or "<unnamed>")
        if uses.startswith("./"):
            if not checked_out:
                return label, uses
            continue
        # Walk the run block in execution order so a dependency referenced
        # before an in-script checkout (git checkout-index also materializes
        # repo files, used by vendor-provenance) is still caught, and an
        # echo/comment mentioning "git checkout-index" never short-circuits
        # the check (issue found in PR #4846 review).
        run_text = str(step.get("run") or "")
        for line in _logical_shell_commands(run_text):
            tokens = _tokenize_command_line(line)
            if not checked_out:
                for token in tokens:
                    if _REPO_PATH.match(token):
                        return label, token.lstrip("./")
            materialized_workspace, in_workspace = _checkout_index_effect(
                line,
                in_workspace,
            )
            if materialized_workspace:
                checked_out = True
    return None


@pytest.mark.parametrize("workflow", _workflows(), ids=lambda p: p.name)
def test_jobs_running_repo_files_check_out_first(workflow: Path) -> None:
    doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    offenders = []
    for name, job in _jobs(doc).items():
        unmet = first_unmet_repo_dependency(job)
        if unmet:
            offenders.append(f"{name}: step {unmet[0]!r} needs {unmet[1]!r}")
    assert not offenders, (
        f"{workflow.name} has jobs that use a repo file without checking the "
        f"repository out first: {offenders}"
    )


@pytest.mark.parametrize("workflow", _workflows(), ids=lambda p: p.name)
def test_sparse_checkout_paths_exist(workflow: Path) -> None:
    """A sparse checkout naming a path that moved silently produces an empty tree."""
    doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    missing = []
    for name, job in _jobs(doc).items():
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            if not str(step.get("uses") or "").startswith("actions/checkout"):
                continue
            with_block = step.get("with")
            if not isinstance(with_block, dict):
                continue
            sparse = with_block.get("sparse-checkout")
            if not isinstance(sparse, str):
                continue
            for entry in sparse.split():
                if not (REPO_ROOT / entry).exists():
                    missing.append(f"{name}: {entry}")
    assert not missing, f"{workflow.name} sparse-checkout names paths that do not exist: {missing}"


class TestRepoPathsInRun:
    def test_finds_a_python_invocation(self) -> None:
        assert repo_paths_in_run("python3 scripts/ci/x.py --flag") == ["scripts/ci/x.py"]

    def test_finds_a_leading_dot_slash_path(self) -> None:
        assert repo_paths_in_run("uv run python ./scripts/ci/x.py") == ["scripts/ci/x.py"]

    def test_ignores_a_path_that_is_only_printed(self) -> None:
        """The false positive that made a substring search unusable."""
        assert repo_paths_in_run('echo "  - build/generate_agents.py"') == []

    def test_ignores_a_printf_path(self) -> None:
        assert repo_paths_in_run('printf "%s" scripts/ci/x.py') == []

    def test_ignores_a_commented_path(self) -> None:
        assert repo_paths_in_run("# scripts/ci/x.py is the old name") == []

    def test_ignores_an_unrelated_path(self) -> None:
        assert repo_paths_in_run("python3 /usr/bin/thing.py") == []
        assert repo_paths_in_run("cd tests && pytest") == []

    def test_finds_a_path_on_a_later_line(self) -> None:
        block = 'echo "starting"\npython3 scripts/ci/x.py\n'
        assert repo_paths_in_run(block) == ["scripts/ci/x.py"]

    def test_unbalanced_quotes_do_not_raise(self) -> None:
        assert repo_paths_in_run("python3 scripts/ci/x.py 'unclosed") == ["scripts/ci/x.py"]


class TestFirstUnmetRepoDependency:
    def test_a_job_with_checkout_first_is_clean(self) -> None:
        job = {
            "steps": [
                {"uses": "actions/checkout@abc"},
                {"name": "Run", "run": "python3 scripts/ci/x.py"},
            ]
        }
        assert first_unmet_repo_dependency(job) is None

    def test_a_job_without_checkout_is_flagged(self) -> None:
        job = {"steps": [{"name": "Run", "run": "python3 scripts/ci/x.py"}]}
        assert first_unmet_repo_dependency(job) == ("Run", "scripts/ci/x.py")

    def test_a_checkout_after_the_use_is_too_late(self) -> None:
        job = {
            "steps": [
                {"name": "Run", "run": "python3 scripts/ci/x.py"},
                {"uses": "actions/checkout@abc"},
            ]
        }
        assert first_unmet_repo_dependency(job) is not None

    def test_a_local_action_without_checkout_is_flagged(self) -> None:
        job = {"steps": [{"uses": "./.github/actions/setup-code-env"}]}
        assert first_unmet_repo_dependency(job) == (
            "./.github/actions/setup-code-env",
            "./.github/actions/setup-code-env",
        )

    def test_a_local_action_after_checkout_is_clean(self) -> None:
        job = {
            "steps": [
                {"uses": "actions/checkout@abc"},
                {"uses": "./.github/actions/setup-code-env"},
            ]
        }
        assert first_unmet_repo_dependency(job) is None

    def test_a_job_with_no_steps_is_clean(self) -> None:
        assert first_unmet_repo_dependency({}) is None

    def test_non_mapping_steps_are_skipped(self) -> None:
        assert first_unmet_repo_dependency({"steps": ["oops", None]}) is None

    def test_workspace_checkout_index_satisfies_a_later_dependency(self) -> None:
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": (
                        'git checkout-index -a -f --prefix="$GITHUB_WORKSPACE/"\n'
                        "python3 scripts/ci/x.py"
                    ),
                }
            ]
        }
        assert first_unmet_repo_dependency(job) is None

    def test_checkout_index_without_prefix_does_not_prove_workspace_checkout(self) -> None:
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": "cd /tmp && git checkout-index -a\npython3 scripts/ci/x.py",
                }
            ]
        }
        assert first_unmet_repo_dependency(job) == ("Materialize", "scripts/ci/x.py")

    def test_checkout_index_with_external_work_tree_does_not_satisfy_dependency(
        self,
    ) -> None:
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": (
                        "GIT_WORK_TREE=/tmp/tree git checkout-index -a\npython3 scripts/ci/x.py"
                    ),
                }
            ]
        }
        assert first_unmet_repo_dependency(job) == ("Materialize", "scripts/ci/x.py")

    def test_an_echoed_checkout_index_does_not_satisfy_a_dependency(self) -> None:
        """The false positive that made a substring search unusable (PR #4846)."""
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": 'echo "run: git checkout-index -a -f"\npython3 scripts/ci/x.py',
                }
            ]
        }
        assert first_unmet_repo_dependency(job) == ("Materialize", "scripts/ci/x.py")

    def test_a_commented_checkout_index_does_not_satisfy_a_dependency(self) -> None:
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": "# uses git checkout-index internally\npython3 scripts/ci/x.py",
                }
            ]
        }
        assert first_unmet_repo_dependency(job) == ("Materialize", "scripts/ci/x.py")

    def test_a_dependency_before_the_checkout_index_in_the_same_step_is_flagged(self) -> None:
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": "python3 scripts/ci/x.py\ngit checkout-index -a -f",
                }
            ]
        }
        assert first_unmet_repo_dependency(job) == ("Materialize", "scripts/ci/x.py")

    def test_checkout_index_as_an_unrelated_cli_argument_does_not_satisfy_a_dependency(
        self,
    ) -> None:
        """An exact-token substring match, not a real git subcommand (PR #4846 review)."""
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": (
                        "python3 -c \"print('checkout-index')\" checkout-index\n"
                        "python3 scripts/ci/x.py"
                    ),
                }
            ]
        }
        assert first_unmet_repo_dependency(job) == ("Materialize", "scripts/ci/x.py")

    def test_checkout_index_with_external_prefix_does_not_satisfy_a_dependency(self) -> None:
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": (
                        "GIT_INDEX_FILE=/tmp/idx-pr git checkout-index -a "
                        "--prefix=/tmp/candidate/\npython3 scripts/ci/x.py"
                    ),
                }
            ]
        }
        assert first_unmet_repo_dependency(job) == ("Materialize", "scripts/ci/x.py")

    def test_continued_external_prefix_does_not_satisfy_a_dependency(self) -> None:
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": (
                        "GIT_INDEX_FILE=/tmp/idx-pr git checkout-index -a \\\n"
                        "  --prefix=/tmp/candidate/\n"
                        "python3 scripts/ci/x.py"
                    ),
                }
            ]
        }
        assert first_unmet_repo_dependency(job) == ("Materialize", "scripts/ci/x.py")

    def test_compound_echo_does_not_satisfy_a_dependency(self) -> None:
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": "true && echo git checkout-index\npython3 scripts/ci/x.py",
                }
            ]
        }
        assert first_unmet_repo_dependency(job) == ("Materialize", "scripts/ci/x.py")

    def test_compound_real_checkout_satisfies_a_dependency(self) -> None:
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": (
                        "true && git checkout-index -a "
                        '--prefix="$GITHUB_WORKSPACE/"\npython3 scripts/ci/x.py'
                    ),
                }
            ]
        }
        assert first_unmet_repo_dependency(job) is None

    def test_empty_prefix_does_not_satisfy_a_dependency(self) -> None:
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": 'git checkout-index -a --prefix=""\npython3 scripts/ci/x.py',
                }
            ]
        }
        assert first_unmet_repo_dependency(job) == ("Materialize", "scripts/ci/x.py")

    def test_single_quoted_workspace_prefix_does_not_satisfy_a_dependency(self) -> None:
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": (
                        "git checkout-index -a --prefix='$GITHUB_WORKSPACE/'\n"
                        "python3 scripts/ci/x.py"
                    ),
                }
            ]
        }
        assert first_unmet_repo_dependency(job) == ("Materialize", "scripts/ci/x.py")

    def test_checkout_index_with_workspace_prefix_satisfies_a_dependency(self) -> None:
        job = {
            "steps": [
                {
                    "name": "Materialize",
                    "run": (
                        "GIT_INDEX_FILE=/tmp/idx-pr git checkout-index -a "
                        '--prefix="$GITHUB_WORKSPACE/"\npython3 scripts/ci/x.py'
                    ),
                }
            ]
        }
        assert first_unmet_repo_dependency(job) is None
