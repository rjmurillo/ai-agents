"""Require repository materialization before workflow steps use repo files."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
import yaml

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github/workflows"
REPO_ROOT = Path(__file__).resolve().parents[2]

_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SHELL_CONTROL_TOKENS = frozenset({"&&", "||", ";", "|"})
_WORKSPACE_PREFIX_FORMS = (
    '--prefix="$GITHUB_WORKSPACE/"',
    '--prefix="${GITHUB_WORKSPACE}/"',
    '--prefix "$GITHUB_WORKSPACE/"',
    '--prefix "${GITHUB_WORKSPACE}/"',
)
_WORKSPACE_PREFIX_VALUES = frozenset({"$GITHUB_WORKSPACE/", "${GITHUB_WORKSPACE}/"})
_WORKSPACE_REFERENCES = frozenset(
    {".", "./", "$GITHUB_WORKSPACE", "${GITHUB_WORKSPACE}", "${{ github.workspace }}"}
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
    """Tokenize one shell line while preserving compound command segments."""
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


def _is_printing_segment(tokens: list[str]) -> bool:
    command = _strip_environment_assignments(tokens)
    if command[:1] in (["echo"], ["printf"]):
        return True
    return command[:1] == ["cat"] and len(command) > 1 and command[1].startswith("<<")


def _raw_shell_segments(line: str) -> list[str]:
    return [
        segment.strip()
        for segment in re.split(r"\s*(?:&&|\|\||;|\|)\s*", line)
        if segment.strip()
    ]


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
        segments = _shell_command_segments(_tokenize_command_line(line))
        for segment in segments:
            if _is_printing_segment(segment):
                continue
            for token in segment:
                if _REPO_PATH.match(token):
                    found.append(token.lstrip("./"))
    return found


def _is_workspace_reference(value: str) -> bool:
    """True when *value* (a ``cd`` target or ``GIT_WORK_TREE``) names the workspace."""
    return value in _WORKSPACE_REFERENCES


def _step_starts_in_workspace(step: dict) -> bool:
    working_directory = str(step.get("working-directory") or "$GITHUB_WORKSPACE")
    return _is_workspace_reference(working_directory)


def _segment_assignments(segment: list[str]) -> dict[str, str]:
    """Return the leading ``VAR=value`` environment assignments in *segment*."""
    assignments: dict[str, str] = {}
    for token in segment:
        if not _ENV_ASSIGNMENT.match(token):
            break
        name, value = token.split("=", 1)
        assignments[name] = value
    return assignments


def _without_shell_comment(raw_segment: str) -> str:
    quote = ""
    escaped = False
    for index, character in enumerate(raw_segment):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote != "'":
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = ""
            continue
        if character in {"'", '"'}:
            quote = character
            continue
        if character == "#":
            return raw_segment[:index]
    return raw_segment


def _prefixes_into_workspace(command_tokens: list[str], raw_segment: str) -> bool:
    """True when *command_tokens* passes checkout-index a workspace-rooted ``--prefix``."""
    command_source = _without_shell_comment(raw_segment)
    if command_source.count("--prefix") != 1:
        return False
    for index, token in enumerate(command_tokens):
        if token.startswith("--prefix="):
            value = token.split("=", 1)[1]
            return (
                value in _WORKSPACE_PREFIX_VALUES
                and any(form in command_source for form in _WORKSPACE_PREFIX_FORMS)
            )
        if token == "--prefix" and index + 1 < len(command_tokens):
            value = command_tokens[index + 1]
            return (
                value in _WORKSPACE_PREFIX_VALUES
                and any(form in command_source for form in _WORKSPACE_PREFIX_FORMS)
            )
    return False


def _checkout_index_effect(line: str, in_workspace: bool) -> tuple[bool, bool]:
    """Return whether *line* checks out into the workspace and the resulting cwd state.

    Uses the same tokenizer as ``repo_paths_in_run`` so an ``echo`` line or a
    comment that merely mentions ``git checkout-index`` is never mistaken for
    the command actually running. ``checkout-index`` only counts when a
    ``git`` token immediately precedes it (as in ``git checkout-index`` or
    ``GIT_INDEX_FILE=... git checkout-index``), never merely present anywhere
    in the token list: a line such as ``python3 -c '...' checkout-index``
    passes the literal string ``checkout-index`` as an unrelated CLI
    argument, which must not be mistaken for the git subcommand that
    actually materializes the repo (PR #4846 review, thread on this exact
    substring-vs-subcommand gap).
    """
    tokens = _tokenize_command_line(line)
    token_segments = _shell_command_segments(tokens)
    raw_segments = _raw_shell_segments(line)
    if len(token_segments) != 1 or len(raw_segments) != 1:
        return False, in_workspace
    for segment, raw_segment in zip(token_segments, raw_segments, strict=False):
        assignments = _segment_assignments(segment)
        command = _strip_environment_assignments(segment)
        if command[:1] == ["cd"] and len(command) > 1:
            in_workspace = _is_workspace_reference(command[1])
            continue
        if command[:2] != ["git", "checkout-index"]:
            continue
        if "-a" not in command[2:] and "--all" not in command[2:]:
            return False, in_workspace
        work_tree = assignments.get("GIT_WORK_TREE")
        effective_workspace = (
            in_workspace if work_tree is None else _is_workspace_reference(work_tree)
        )
        checks_out_workspace = effective_workspace and _prefixes_into_workspace(
            command[2:], raw_segment
        )
        return checks_out_workspace, in_workspace
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
        in_workspace = _step_starts_in_workspace(step)
        for line in _logical_shell_commands(run_text):
            tokens = _tokenize_command_line(line)
            if not checked_out:
                for segment in _shell_command_segments(tokens):
                    if _is_printing_segment(segment):
                        continue
                    for token in segment:
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

    def test_finds_a_path_after_echo_in_a_compound_line(self) -> None:
        assert repo_paths_in_run(
            "echo ready && python3 scripts/ci/x.py"
        ) == ["scripts/ci/x.py"]

    def test_unbalanced_quotes_do_not_raise(self) -> None:
        assert repo_paths_in_run("python3 scripts/ci/x.py 'unclosed") == ["scripts/ci/x.py"]


_MATERIALIZE_DEP = ("Materialize", "scripts/ci/x.py")
_PY_DEPENDENCY = "python3 scripts/ci/x.py"


def _case(
    shell_prefix: str,
    expected: tuple[str, str] | None = _MATERIALIZE_DEP,
) -> tuple[str, tuple[str, str] | None]:
    """Build a (run_text, expected) pair: *shell_prefix* then the python dependency line.

    Every scenario below probes the same dependency line, so only the prefix
    that may-or-may-not materialize the workspace varies; ``expected`` defaults
    to the unmet dependency and is overridden for the cases that do check out.
    """
    return f"{shell_prefix}\n{_PY_DEPENDENCY}", expected


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

    def test_a_dependency_after_echo_on_the_same_line_is_flagged(self) -> None:
        job = {
            "steps": [
                {"name": "Run", "run": "echo ready && python3 scripts/ci/x.py"}
            ]
        }
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

    def test_cd_state_does_not_cross_step_boundaries(self) -> None:
        job = {"steps": [
            {"run": "cd /tmp"},
            {"run": 'git checkout-index -a --prefix="$GITHUB_WORKSPACE/"\npython3 scripts/x.py'},
        ]}
        assert first_unmet_repo_dependency(job) is None

    def test_external_working_directory_starts_outside_workspace(self) -> None:
        job = {"steps": [{
            "working-directory": "/tmp",
            "run": 'git checkout-index -a --prefix="$GITHUB_WORKSPACE/"\npython3 scripts/x.py',
        }]}
        assert first_unmet_repo_dependency(job) == ("<unnamed>", "scripts/x.py")

    @pytest.mark.parametrize(
        ("run_text", "expected"),
        [
            _case('git checkout-index -a -f --prefix="$GITHUB_WORKSPACE/"', None),
            _case("cd /tmp && git checkout-index -a"),
            _case("GIT_WORK_TREE=/tmp/tree git checkout-index -a"),
            # The false positive that made a substring search unusable (PR #4846).
            _case('echo "run: git checkout-index -a -f"'),
            _case("# uses git checkout-index internally"),
            ("python3 scripts/ci/x.py\ngit checkout-index -a -f", _MATERIALIZE_DEP),
            # An exact-token substring match, not a real git subcommand (PR #4846 review).
            _case("python3 -c \"print('checkout-index')\" checkout-index"),
            _case("GIT_INDEX_FILE=/tmp/idx-pr git checkout-index -a --prefix=/tmp/candidate/"),
            _case(
                "GIT_INDEX_FILE=/tmp/idx-pr git checkout-index -a \\\n  --prefix=/tmp/candidate/"
            ),
            _case("true && echo git checkout-index"),
            _case('true && git checkout-index -a --prefix="$GITHUB_WORKSPACE/"'),
            _case('git checkout-index -a --prefix=""'),
            _case("git checkout-index -a --prefix='$GITHUB_WORKSPACE/'"),
            _case(
                'GIT_INDEX_FILE=/tmp/idx-pr git checkout-index -a --prefix="$GITHUB_WORKSPACE/"',
                None,
            ),
            _case(
                "git checkout-index -a --prefix=/tmp/candidate/ && "
                "printf '%s' '--prefix=\"$GITHUB_WORKSPACE/\"'"
            ),
            _case(
                'cd /tmp\ngit checkout-index GIT_WORK_TREE="$GITHUB_WORKSPACE" '
                '--prefix="$GITHUB_WORKSPACE/"'
            ),
            _case(
                "true 'x|--prefix=\"$GITHUB_WORKSPACE/\"' && "
                "git checkout-index -a --prefix='$GITHUB_WORKSPACE/'"
            ),
            _case('git checkout-index --prefix="$GITHUB_WORKSPACE/" docs/one.txt'),
            _case(
                "git checkout-index -a --prefix='$GITHUB_WORKSPACE/' "
                '# --prefix="$GITHUB_WORKSPACE/"'
            ),
            _case('git checkout-index -a --prefix="$GITHUB_WORKSPACE/" || true'),
            _case('false && git checkout-index -a --prefix="$GITHUB_WORKSPACE/"'),
        ],
        ids=[
            "workspace_checkout_index_satisfies_a_later_dependency",
            "checkout_index_without_prefix_does_not_prove_workspace_checkout",
            "checkout_index_with_external_work_tree_does_not_satisfy_dependency",
            "an_echoed_checkout_index_does_not_satisfy_a_dependency",
            "a_commented_checkout_index_does_not_satisfy_a_dependency",
            "a_dependency_before_the_checkout_index_in_the_same_step_is_flagged",
            "checkout_index_as_an_unrelated_cli_argument_does_not_satisfy_a_dependency",
            "checkout_index_with_external_prefix_does_not_satisfy_a_dependency",
            "continued_external_prefix_does_not_satisfy_a_dependency",
            "compound_echo_does_not_satisfy_a_dependency",
            "compound_real_checkout_fails_closed",
            "empty_prefix_does_not_satisfy_a_dependency",
            "single_quoted_workspace_prefix_does_not_satisfy_a_dependency",
            "checkout_index_with_workspace_prefix_satisfies_a_dependency",
            "later_print_segment_cannot_supply_workspace_prefix",
            "nonleading_work_tree_assignment_is_not_environment",
            "quoted_pipe_segment_mismatch_fails_closed",
            "selective_checkout_does_not_satisfy_repo_dependency",
            "comment_cannot_supply_prefix_quote_evidence",
            "error_swallowed_checkout_fails_closed",
            "skipped_checkout_fails_closed",
        ],
    )
    def test_materialize_step_dependency_scenarios(
        self,
        run_text: str,
        expected: tuple[str, str] | None,
    ) -> None:
        job = {"steps": [{"name": "Materialize", "run": run_text}]}
        assert first_unmet_repo_dependency(job) == expected
