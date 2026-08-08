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
from collections.abc import Mapping
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

DEFAULT_CHECKOUT_DEPTH = 1
ROOT_CHECKOUT_PATHS = {None, "", ".", "./"}
SHALLOWING_FETCH_FLAGS = ("--depth", "--shallow-since", "--shallow-exclude")


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
    """Shell lines with backslash continuations joined and comments dropped.

    A fetch split as `git fetch origin main \\` / `  --depth=1` is one command
    to the shell and must be one line here, or the flag hides on a line that
    does not contain `git fetch`.
    """
    joined: list[str] = []
    pending = ""
    for raw_line in script.splitlines():
        line = raw_line.strip()
        if pending:
            line = f"{pending} {line}"
            pending = ""
        if line.endswith("\\"):
            pending = line[:-1].rstrip()
            continue
        joined.append(line)
    if pending:
        joined.append(pending)
    return [line for line in joined if line and not line.startswith("#")]


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
    if "${{" in path or "GITHUB_WORKSPACE" in path:
        return True
    return path in {".", "./"}


def _is_root_git_dir(raw: str) -> bool:
    """True when a `--git-dir` value names the ROOT repository's git directory.

    `--git-dir` takes a git directory, not a worktree, so it is not
    interchangeable with `-C`. The root repository's git directory is `.git`,
    which `_is_root_path` correctly calls non-root as a worktree path and which
    therefore let `git --git-dir=.git fetch --depth=1` through as if it were
    grafting somewhere else.
    """
    path = raw.strip().strip("\"'")
    if not path:
        return True
    if "${{" in path or "GITHUB_WORKSPACE" in path:
        return True
    return path.rstrip("/") in {".git", "./.git"}


def _targets_root_repository(command: str) -> bool:
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
            return _is_root_path(tokens[index + 1])
        if token.startswith("-C") and len(token) > 2:
            return _is_root_path(token[2:])
        if token == "--git-dir" and index + 1 < len(tokens):
            return _is_root_git_dir(tokens[index + 1])
        if token.startswith("--git-dir="):
            return _is_root_git_dir(token.split("=", 1)[1])
    return True


def _fetch_commands(line: str) -> list[str]:
    """The commands on one logical line that invoke `git fetch`.

    Splitting on shell operators keeps a flag belonging to a different command
    from being charged to the fetch, as in
    `git fetch origin main && tool --depth=1`.
    """
    # `||` before `|`, or the two-character operator would be split twice.
    normalized = line.replace("&&", "\n").replace("||", "\n")
    parts = normalized.replace("|", "\n").replace(";", "\n").split("\n")
    commands = [part.strip() for part in parts if part.strip()]
    return [
        command
        for command in commands
        if "fetch" in command and (command.startswith("git") or " git " in f" {command}")
    ]


def _shallowing_fetches(job: Mapping[str, object]) -> list[tuple[str, str]]:
    """Fetches in the job that would graft the root repository."""
    found: list[tuple[str, str]] = []
    for step in _steps(job):
        run = step.get("run")
        if not isinstance(run, str):
            continue
        working_directory = step.get("working-directory")
        if isinstance(working_directory, str) and not _is_root_path(working_directory):
            continue
        name = step.get("name")
        for line in _logical_lines(run):
            attributed = False
            for command in _fetch_commands(line):
                if not any(flag in command for flag in SHALLOWING_FETCH_FLAGS):
                    continue
                attributed = True
                if not _targets_root_repository(command):
                    continue
                found.append((str(name), command))
            if not attributed and _line_hides_a_shallowing_fetch(line):
                # The splitter is not a shell. A fetch inside `$( ... )`, or
                # downstream of a pipe, carries a shallowing flag that no
                # command it produced owns. Reporting the whole line is the
                # fail-loud answer: a prevention invariant that cannot attribute
                # a flag must say so rather than fall silent, and a human
                # reading the message can see in one glance whether it is real.
                found.append((str(name), line))
    return found


def _line_hides_a_shallowing_fetch(line: str) -> bool:
    """True when a construct the splitter cannot read hides a shallowing fetch.

    Restricted to command substitution, because that is the one shape where a
    real `git fetch --depth=1` survives with no command owning it. Firing on
    any unattributed flag instead would report `git fetch origin main && tool
    --depth=1`, where the flag belongs to a different program and there is no
    graft at all.
    """
    if "fetch" not in line:
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


