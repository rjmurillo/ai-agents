"""Static parsing of workflow YAML for the shallow-graft invariant.

Shared by the two test modules that consume it, on the same footing as
`count_ratchet_git_harness.py`: the parsing is the boundary under test in one
module and a dependency in the other, so one copy is what keeps them from
drifting apart.

The rules encoded here are not arbitrary. `_normalized_depth` mirrors the
coercion in `actions/checkout`, and the ambiguity rules resolve toward "root",
so an unresolved expression makes the sweep ask rather than fall silent.
"""

from __future__ import annotations

import math
import re
import shlex
from collections.abc import Mapping
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

DEFAULT_CHECKOUT_DEPTH = 1
ROOT_CHECKOUT_PATHS = {None, "", ".", "./"}
SHALLOWING_FETCH_FLAGS = ("--depth", "--shallow-since", "--shallow-exclude")
GRAFTING_GIT_SUBCOMMAND = re.compile(r"\b(?:fetch|pull)\b")


def _jobs(document: object) -> dict[str, Mapping[str, object]]:
    if not isinstance(document, dict):
        return {}
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return {}
    return {name: job for name, job in jobs.items() if isinstance(job, dict)}


def _steps(job: Mapping[str, object]) -> list[Mapping[str, object]]:
    steps = job.get("steps")
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict)]


def _is_root_checkout(step: Mapping[str, object]) -> bool:
    """True when the step checks out into the workspace root.

    `actions/checkout` writes its own `.git` under `path:`, so a nested
    checkout has a separate `.git/shallow` and cannot graft the root
    repository. Aggregating both into one job-level depth would let a shallow
    helper checkout stand in for the root one. `pr-maintenance.yml` line 120
    is a live example: a `.trusted-helper` checkout at depth 1 sits in a job
    whose root checkout is depth 0.

    An UNRESOLVED path counts as root. The alternative, excluding it, would
    let `path: ${{ inputs.dir }}` silently remove a job from the sweep, and a
    prevention invariant that quietly stops looking is worse than one that
    occasionally asks a human to check.
    """
    with_block = step.get("with")
    if not isinstance(with_block, dict):
        return True
    path = with_block.get("path")
    if isinstance(path, str) and "${{" in path:
        return True
    return path in ROOT_CHECKOUT_PATHS


def _normalized_depth(value: object) -> object:
    """Depth as `actions/checkout` itself would resolve it.

    The action does, in `input-helper.ts`:

        result.fetchDepth = Math.floor(Number(core.getInput('fetch-depth') || '1'))
        if (isNaN(result.fetchDepth) || result.fetchDepth < 0) {
          result.fetchDepth = 0
        }

    So `true`, `false`, a negative number, and any non-numeric literal all
    resolve to 0, which is a COMPLETE checkout. Preserving them as-is is not
    neutral: it makes `fetch-depth: true` read as shallow, and a shallow
    reading skips the job, so the invariant would go blind on a job that is
    actually running with full history. Mirroring the coercion is the only
    reading that fails safe.

    A `${{ }}` expression is decided at run time and is deliberately left
    unresolved, guarded by its own test rather than guessed at.
    """
    if isinstance(value, str) and "${{" in value:
        return value.strip()
    if isinstance(value, bool):
        # bool is a subclass of int, so this must precede the int branch.
        # Number(true) is 1 and Number(false) is 0 in JavaScript, but the
        # action reads YAML through a string input, so both arrive as
        # "true"/"false", are NaN, and floor to 0.
        return 0
    if isinstance(value, int):
        return value if value >= 0 else 0
    if isinstance(value, float):
        floored = math.floor(value)
        return floored if floored >= 0 else 0
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            # `core.getInput(...) || '1'` makes an empty input the action's
            # default of 1, which is shallow. Folding it to 0 would call a
            # genuinely shallow checkout complete.
            return DEFAULT_CHECKOUT_DEPTH
        try:
            number = float(stripped)
        except ValueError:
            return 0
        floored = math.floor(number)
        return floored if floored >= 0 else 0
    if value is None:
        # YAML `~` or a bare key reaches the action as an empty string.
        return DEFAULT_CHECKOUT_DEPTH
    return 0


def _root_checkout_depths(job: Mapping[str, object]) -> set[object]:
    """Every `fetch-depth` the job's ROOT checkout steps request.

    An absent `fetch-depth` is the action's default of 1, which is itself
    shallow, so it is reported as 1 rather than dropped.
    """
    depths: set[object] = set()
    for step in _steps(job):
        uses = step.get("uses")
        if not isinstance(uses, str) or "actions/checkout" not in uses:
            continue
        if not _is_root_checkout(step):
            continue
        with_block = step.get("with")
        if not isinstance(with_block, dict):
            depths.add(DEFAULT_CHECKOUT_DEPTH)
            continue
        depths.add(_normalized_depth(with_block.get("fetch-depth", DEFAULT_CHECKOUT_DEPTH)))
    return depths


def _logical_lines(script: str) -> list[str]:
    """Shell lines with continuations joined and comments dropped.

    A fetch split as `git fetch origin main \\` / `  --depth=1` is one command
    to the shell and must be one line here, or the flag hides on a line that
    does not contain `git fetch`. PowerShell uses a trailing backtick for the
    same purpose.
    """
    joined: list[str] = []
    pending = ""
    for raw_line in script.splitlines():
        line = raw_line.strip()
        if pending:
            line = f"{pending} {line}"
            pending = ""
        if line.endswith(("\\", "`")):
            pending = line[:-1].rstrip()
            continue
        joined.append(_strip_trailing_comment(line))
    if pending:
        joined.append(_strip_trailing_comment(pending))
    return [line for line in joined if line and not line.startswith("#")]


def _strip_trailing_comment(line: str) -> str:
    """Drop an unquoted Bash or PowerShell trailing comment."""
    quote = ""
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if character in {"\\", "`"}:
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = ""
            continue
        if character in {"'", '"'}:
            quote = character
            continue
        if character == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip()
    return line


def _is_unresolved_path(path: str) -> bool:
    """True when a path expression cannot be classified statically."""
    return "$" in path or "%CD%" in path.upper() or "(" in path or ")" in path


def _is_root_path(raw: str) -> bool:
    """True when the path names the workspace root, or cannot be resolved.

    An unresolved path counts as root on purpose. Excluding it would let
    `path: ${{ inputs.dir }}` or `working-directory: ${{ github.workspace }}`
    silently drop a step from the sweep, and a prevention invariant that
    quietly stops looking is worse than one that occasionally asks a human.
    """
    path = raw.strip().strip("\"'")
    if not path:
        return True
    if _is_unresolved_path(path):
        return True
    return path in {".", "./"}


def _normalized_literal_path(raw: str) -> str | None:
    """Return a normalized literal path, or None for an unresolved path."""
    path = raw.strip().strip("\"'")
    if not path:
        return "."
    if _is_unresolved_path(path):
        return None
    return path.replace("\\", "/").rstrip("/")


def _nested_checkout_paths(job: Mapping[str, object]) -> set[str]:
    """Literal paths where this job creates a separate checkout."""
    paths: set[str] = set()
    for step in _steps(job):
        uses = step.get("uses")
        if not isinstance(uses, str) or "actions/checkout" not in uses:
            continue
        with_block = step.get("with")
        if not isinstance(with_block, dict):
            continue
        raw_path = with_block.get("path")
        if not isinstance(raw_path, str) or _is_root_path(raw_path):
            continue
        path = _normalized_literal_path(raw_path)
        if path is not None:
            paths.add(path)
    return paths


def _targets_root_repository(command: str, nested_checkouts: set[str]) -> bool:
    """False only when THIS command is unambiguously anchored to a nested repo.

    Scanning the whole logical line fired in both wrong directions. It missed
    a real root graft in `git fetch --depth=1 origin main && git -C .helper
    status`, because a later unrelated command named a nested path. And it
    reported `git --git-dir=.helper/.git fetch --depth=1`, because `--git-dir`
    is not spelled `-C`. Reading only the tokens of the command that carries
    the fetch, and treating `--git-dir` as equivalent to `-C`, fixes both.
    """
    tokens = command.split()
    for index, token in enumerate(tokens):
        if token == "-C" and index + 1 < len(tokens):
            path = _normalized_literal_path(tokens[index + 1])
            return path is None or path not in nested_checkouts
        if token.startswith("-C") and len(token) > 2:
            path = _normalized_literal_path(token[2:])
            return path is None or path not in nested_checkouts
        if token == "--git-dir" and index + 1 < len(tokens):
            path = _normalized_literal_path(tokens[index + 1])
            return path is None or not any(
                path == f"{checkout}/.git" for checkout in nested_checkouts
            )
        if token.startswith("--git-dir="):
            path = _normalized_literal_path(token.split("=", 1)[1])
            return path is None or not any(
                path == f"{checkout}/.git" for checkout in nested_checkouts
            )
    return True


def _fetch_commands(line: str) -> list[str]:
    """The commands on one logical line that invoke `git fetch` or `git pull`.

    Splitting on shell operators keeps a flag belonging to a different command
    from being charged to the fetch, as in
    `git fetch origin main && tool --depth=1`.
    """
    return [
        command
        for command in _command_parts(line)
        if GRAFTING_GIT_SUBCOMMAND.search(command)
        and (_starts_with_git_executable(command) or " git " in f" {command}")
    ]


def _command_parts(line: str) -> list[str]:
    """Commands split on the shell separators this invariant understands."""
    # `||` before `|`, or the two-character operator would be split twice.
    normalized = line.replace("&&", "\n").replace("||", "\n")
    normalized = re.sub(r"(?<![>&])&(?![>&])", "\n", normalized)
    parts = normalized.replace("|", "\n").replace(";", "\n").split("\n")
    return [part.strip() for part in parts if part.strip()]


def _starts_with_git_executable(command: str) -> bool:
    """True when normal shell prefixes lead to git or a path to git."""
    stripped = command.lstrip("({ ")
    if not stripped:
        return False
    try:
        tokens = shlex.split(stripped, posix=False)
    except ValueError:
        return False
    index = 0
    if tokens and tokens[0] == "&":
        index += 1
    while index < len(tokens):
        token = tokens[index].strip("\"'")
        name = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if name in {"git", "git.exe"}:
            return True
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            index += 1
            continue
        if name == "command":
            index += 1
            while index < len(tokens) and tokens[index].startswith("-"):
                index += 1
            continue
        if name in {"env", "env.exe"}:
            index = _skip_env_prefix(tokens, index + 1)
            continue
        return False
    return False


def _skip_env_prefix(tokens: list[str], index: int) -> int:
    """Return the wrapped command index after env options and assignments."""
    options_with_operand = {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}
    while index < len(tokens):
        token = tokens[index].strip("\"'")
        if token in options_with_operand:
            index += 2
            continue
        if any(token.startswith(f"{option}=") for option in options_with_operand):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            index += 1
            continue
        return index
    return index


def _shallowing_fetches(job: Mapping[str, object]) -> list[tuple[str, str]]:
    """Fetches in the job that would graft the root repository."""
    found: list[tuple[str, str]] = []
    nested_checkouts = _nested_checkout_paths(job)
    for step in _steps(job):
        run = step.get("run")
        if not isinstance(run, str):
            continue
        name = step.get("name")
        variables: dict[str, str] = {}
        for line in _logical_lines(run):
            for part in _command_parts(line):
                assignment = _literal_assignment(part)
                if assignment is not None:
                    variable, value = assignment
                    variables[variable.lower()] = value
                    continue
                expanded = _expand_known_variables(part, variables)
                attributed = False
                for command in _fetch_commands(expanded):
                    if not any(flag in command for flag in SHALLOWING_FETCH_FLAGS):
                        continue
                    attributed = True
                    if not _targets_root_repository(command, nested_checkouts):
                        continue
                    found.append((str(name), command))
                if not attributed and _line_hides_a_shallowing_fetch(expanded):
                    # The splitter is not a shell. A fetch inside `$( ... )`
                    # carries a shallowing flag that no command it produced
                    # owns. Reporting the whole part is the fail-loud answer.
                    found.append((str(name), expanded))
    return found


def _literal_assignment(line: str) -> tuple[str, str] | None:
    """Return a simple Bash or PowerShell literal assignment."""
    match = re.fullmatch(
        r"\s*(?:(?:export|readonly|local)\s+|declare(?:\s+-[A-Za-z]+)*\s+)?"
        r"\$?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        r"(?:\"([^\"]*)\"|'([^']*)'|(\S+))\s*",
        line,
    )
    if match is None:
        return None
    value = next(value for value in match.groups()[1:] if value is not None)
    return match.group(1), value


def _expand_known_variables(line: str, variables: Mapping[str, str]) -> str:
    """Expand literal variables assigned earlier in the same run block."""
    expanded = line
    for name, value in variables.items():
        literal = f'"{value}"' if any(character.isspace() for character in value) else value
        escaped_name = re.escape(name)

        def replacement(_match: re.Match[str], literal: str = literal) -> str:
            return literal

        for pattern in (rf"\$\{{{escaped_name}\}}", rf"\${escaped_name}\b"):
            expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)
    return expanded


def _line_hides_a_shallowing_fetch(line: str) -> bool:
    """True when a construct the splitter cannot read hides a shallowing fetch.

    Restricted to command substitution, because that is the one shape where a
    real `git fetch --depth=1` survives with no command owning it. Firing on
    any unattributed flag instead would report `git fetch origin main && tool
    --depth=1`, where the flag belongs to a different program and there is no
    graft at all.
    """
    if GRAFTING_GIT_SUBCOMMAND.search(line) is None:
        return False
    if "$(" not in line and "`" not in line:
        return False
    return any(flag in line for flag in SHALLOWING_FETCH_FLAGS)


def _workflow_documents() -> list[tuple[Path, object]]:
    """Every workflow file, under both extensions GitHub Actions accepts.

    Globbing `*.yml` alone is a documented way to go silently blind in this
    repository: the security-suppression gate lost `**/*.yaml` coverage on
    2026-08-01 the same way. The three sibling sweeps in `tests/ci/` all glob
    both, and so does `scripts/ci/adr015_workflow_retention.py`.
    """
    documents: list[tuple[Path, object]] = []
    paths = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))
    for path in paths:
        documents.append((path, yaml.safe_load(path.read_text(encoding="utf-8"))))
    return documents
