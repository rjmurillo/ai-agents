#!/usr/bin/env python3
# taste-lint: ignore file-size, the shim template and the check that decides
# which shims are acceptable must stay in one file: they encode the same
# contract from two directions, and splitting them is how the two drift apart.
"""Install git hook shims that no single worktree can poison.

Git keeps one hooks directory per repository, in ``$GIT_COMMON_DIR/hooks``, and
every linked worktree reads that same directory. ``check_git_hook_health.py``
records the measurement verbatim in its module docstring:

    ``git rev-parse --git-path hooks`` returns the directory git will actually
    read: it honors ``core.hooksPath`` (absolute or relative), and in a linked
    worktree it resolves to the common directory's ``hooks/`` rather than
    ``.git/worktrees/<name>/hooks``

``lefthook install`` writes its shim into that shared directory, and the shim
lefthook 2.1.10 generates embeds an absolute path probed from whichever
environment ran the install. Measured in this repository on 2026-08-27, the
shared ``pre-commit`` held::

    elif /home/user/ai-agents/.claude/worktrees/wf_54440bac-347-6/.venv/[...]

where the elided tail is ``lib/python3.14/site-packages/lefthook/bin/`` plus
the platform binary, and the reader was worktree ``wf_54440bac-347-8``. Running
``lefthook install --reset-hooks-path`` from ``-8`` rewrote that same shared
line to ``-8``'s own ``.venv``. Worktrees are deleted routinely, so the shared
hook ends up naming an interpreter that no longer exists, for every other
checkout of the repository. ``.config/wt.toml`` ran that install on every new
worktree, so the churn was continuous (issue #4789).

This installer writes a shim that names no worktree-specific path at all. It
resolves lefthook through ``uv run --frozen`` at hook-run time, from the cwd
git sets, which is the top level of the worktree the hook fired in. One shared
file, correct for every checkout.

Stricter/looser/different than canonical
----------------------------------------
Different from ``lefthook install``: this writes a fixed template instead of
lefthook's environment-probed one, so it drops lefthook's fallback chain
(``node_modules``, ``swift``, ``mint``, ``mise``, ``devbox``, a bare ``lefthook``
on PATH). Those fallbacks are what carried the poisoned absolute path. This
repository resolves lefthook through ``uv`` (``lefthook.yml`` line 3 reads
``lefthook: uv run --frozen lefthook``), so the dropped rungs were unreachable
here anyway: lefthook templates that value into a constant-true ``test -n``
guard, so its first branch always won.

It still runs ``lefthook install --reset-hooks-path`` first, so lefthook clears
any ``core.hooksPath`` override and records its own
``$GIT_COMMON_DIR/info/lefthook.checksum`` state, then overwrites the shim files
lefthook just wrote. ``--check`` never runs the install and never mutates.

Looser than a byte comparison: ``--check`` accepts any shim that dispatches the
right hook to lefthook and names no machine-bound absolute path, not only the
one :func:`hook_shim` writes. Issue #4789's fourth acceptance criterion asks
that the gate pass "from both worktrees after either install", and an exact
comparison cannot deliver that. :func:`shim_defect` carries the incident.
``write_shims`` follows the same rule, so an already-safe shim written by
something else is left alone rather than fought over.

Stricter than reading the file as text: only lines a shell would execute count,
and only those a shell would still reach. ``# lefthook run pre-commit``
followed by ``exit 0`` mentions the dispatch and runs nothing; so does a bare
``exit 0`` placed above a real dispatch line. Either way a whole-file scan
reports an inert hook as a working shim and the gate then certifies a
repository no lefthook job protects. :func:`_executed_lines` is the single
definition both the dispatch check and the machine-bound-path scan read, and
:func:`_dispatches_to_lefthook` additionally stops at the first ``exit`` no
enclosing block guards.

Stricter than lefthook: a hook path that is a symlink is a defect, and
``write_shims`` replaces it by renaming a fresh regular file over it rather
than writing through it. ``Path.write_text`` opens the resolved target, so a
link in the shared hooks directory both aims git at another checkout's file and
turns this installer into a writer of arbitrary paths outside
``$GIT_COMMON_DIR/hooks``.

Stricter than lefthook: a config this parser cannot read hooks out of is a
defect rather than a pass. ``--check`` used to print ``0 of 0 examined hooks
are worktree-safe`` and exit 0 against a repository with no hooks installed at
all, because the parser reads top-level YAML mapping keys and the config was
JSON, TOML, or a YAML file whose hooks arrive through ``extends:``. A gate that
certifies an unprotected repository is worse than no gate.

Known limitation, not closed here
---------------------------------
``lefthook run`` re-syncs the hooks itself whenever the config checksum has
gone stale. Measured on lefthook 2.1.10: editing ``lefthook.yml`` after an
install and then running ``lefthook run pre-commit`` renamed the existing hook
to ``pre-commit.old`` and wrote a fresh environment-probed shim in its place.
So a ``lefthook.yml`` edit re-poisons the shared hook. The pre-PR gate
``Lefthook Installed`` detects that state and names this script as the repair;
closing it entirely would need lefthook to stop auto-syncing, which this change
does not attempt.

USAGE:
  # Install worktree-safe shims (mutates $GIT_COMMON_DIR/hooks):
  uv run python scripts/maintenance/install_lefthook_worktree_safe.py

  # Report only; exit non-zero when a shim diverges, mutate nothing:
  uv run python scripts/maintenance/install_lefthook_worktree_safe.py --check

EXIT CODES (ADR-035):
  0 - Shims are worktree-safe (or were just made so)
  1 - --check found a divergent, missing, or non-executable shim, or a config
      this parser cannot read a hook name out of
  2 - Configuration error: not a git worktree, no lefthook config present, or
      (install path) a config yielding no hook name to install
  3 - External error: `lefthook install` failed or git could not be queried

Refs Issue #4789.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_GIT_TIMEOUT_SECONDS = 30
_INSTALL_TIMEOUT_SECONDS = 300

# Kept byte-identical with check_git_hook_health.py's LEFTHOOK_CONFIG_NAMES so
# both agree on what "this repository uses lefthook" means.
LEFTHOOK_CONFIG_NAMES = tuple(
    f"{stem}{local}.{extension}"
    for stem in ("lefthook", ".lefthook", ".config/lefthook")
    for local in ("", "-local")
    for extension in ("yml", "yaml", "json", "jsonc", "toml")
)

# Client-side git hooks. Used as an allowlist over the config's top-level keys
# so non-hook settings (`lefthook:`, `colors:`, `templates:`) are never mistaken
# for a hook name. Server-side hooks are excluded: git never runs them here.
GIT_CLIENT_HOOKS = frozenset(
    {
        "applypatch-msg",
        "commit-msg",
        "post-applypatch",
        "post-checkout",
        "post-commit",
        "post-merge",
        "post-rewrite",
        "pre-applypatch",
        "pre-auto-gc",
        "pre-commit",
        "pre-merge-commit",
        "pre-push",
        "pre-rebase",
        "prepare-commit-msg",
        "push-to-checkout",
        "sendemail-validate",
    }
)

# A top-level YAML mapping key: no leading whitespace, no leading list dash.
_TOP_LEVEL_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):")

_HOOK_MODE = 0o755

# An absolute path token. The negative lookbehind keeps `$dir/node_modules` and
# `sed 's/a/b/'` out: a slash preceded by a word character or `$` continues an
# expression, it does not open an absolute path.
_ABSOLUTE_PATH = re.compile(r"(?<![\w$])/[A-Za-z0-9_.][^\s\"';|&)]*")

# Absolute paths every machine resolves identically, so they cannot bind the
# shared shim to one checkout. Everything else absolute is the defect.
_MACHINE_INDEPENDENT_PATHS = ("/bin/sh", "/dev/null", "/usr/bin/env")

# The measured signature of the defect: lefthook probes the uv virtual
# environment and writes its absolute path into the shim. Named separately from
# the general rule so the failure message can say what actually happened.
_VENV_PATH = re.compile(r"(?<![\w$])/\S*/\.venv/")

# Shell block structure, read only to decide whether an ``exit`` is guarded.
# Deliberately shallow: this counts nesting, it does not parse shell. An
# unguarded ``exit`` ends the script, so nothing after it can dispatch.
_BLOCK_OPEN = re.compile(r"^(if|case|while|until|for)\b")
_BLOCK_CLOSE = re.compile(r"^(fi|esac|done)\b")
_UNCONDITIONAL_EXIT = re.compile(r"^exit\b")

REPAIR_COMMAND = "uv run python scripts/maintenance/install_lefthook_worktree_safe.py"


class GitQueryError(RuntimeError):
    """Git was unavailable or refused to answer."""


def hook_shim(hook: str) -> str:
    """Return the shim body for ``hook``.

    Every line is environment-independent. ``uv`` and ``LEFTHOOK_BIN`` are
    resolved from PATH and the environment at hook-run time, never baked in, so
    the one shared copy of this file is correct in every worktree.

    ``LEFTHOOK=0``, ``LEFTHOOK_BIN``, and ``LEFTHOOK_VERBOSE`` keep the meanings
    lefthook's own shim gives them. Preserving them is deliberate: ADR-086 and
    ``.claude/rules/universal.md`` MUST NOT 2 name ``LEFTHOOK=0`` and
    ``LEFTHOOK_BIN`` as forbidden bypasses, and a rule against using a
    mechanism is not a reason to silently remove it from under the people the
    rule binds.
    """
    return f"""#!/bin/sh
# Worktree-safe lefthook shim for the "{hook}" hook.
#
# This file lives in $GIT_COMMON_DIR/hooks, which the primary checkout and every
# linked worktree share. It therefore names no path belonging to any one
# worktree: `uv run --frozen` resolves lefthook from the cwd git sets, which is
# the top level of the worktree whose hook fired. Refs issue #4789.
#
# Rewrite it with: {REPAIR_COMMAND}

if [ "$LEFTHOOK" = "0" ]; then
  exit 0
fi

if [ "$LEFTHOOK_VERBOSE" = "1" ] || [ "$LEFTHOOK_VERBOSE" = "true" ]; then
  set -x
fi

if [ -n "$LEFTHOOK_BIN" ]; then
  exec "$LEFTHOOK_BIN" run "{hook}" "$@"
fi

exec uv run --frozen lefthook run "{hook}" "$@"
"""


def _git(repo_root: Path, *args: str) -> str:
    """Return stdout for a git command, raising :class:`GitQueryError` on failure."""
    git = shutil.which("git")
    if git is None:
        raise GitQueryError("git executable not found")
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            [git, *args],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitQueryError(f"git {' '.join(args)} failed to execute: {exc}") from exc
    if result.returncode != 0:
        raise GitQueryError(
            f"git {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def config_paths(repo_root: Path) -> list[Path]:
    """Return every lefthook config present, in :data:`LEFTHOOK_CONFIG_NAMES` order.

    Every one of them, not the first match: lefthook merges ``lefthook.yml``
    with ``lefthook-local.yml``, so a hook declared only in the local file is a
    hook git will run. Returning the first match alone left such a hook
    unexamined while the check still reported a clean pass.
    """
    return [
        candidate
        for name in LEFTHOOK_CONFIG_NAMES
        if (candidate := repo_root / name).is_file()
    ]


def config_path(repo_root: Path) -> Path | None:
    """Return the first lefthook config present, or None when this repo uses none."""
    return next(iter(config_paths(repo_root)), None)


def declared_hooks(config: Path) -> list[str]:
    """Return the git hook names the lefthook config declares, in file order.

    Reads top-level mapping keys and keeps only those that name a client-side
    git hook. A key-shaped line inside a block scalar cannot reach this: block
    scalars are indented, and the pattern requires column zero.
    """
    hooks: list[str] = []
    for line in config.read_text(encoding="utf-8").splitlines():
        match = _TOP_LEVEL_KEY.match(line)
        if match is None:
            continue
        key = match.group(1)
        if key in GIT_CLIENT_HOOKS and key not in hooks:
            hooks.append(key)
    return hooks


def declared_hook_names(repo_root: Path) -> list[str]:
    """Return every hook name declared across every lefthook config present."""
    hooks: list[str] = []
    for config in config_paths(repo_root):
        for hook in declared_hooks(config):
            if hook not in hooks:
                hooks.append(hook)
    return hooks


def unreadable_config_defect(configs: list[Path]) -> str:
    """Return why a present config yielded no hook to examine."""
    named = ", ".join(str(config) for config in configs)
    return (
        f"{named} declares no client-side git hooks; this parser reads only "
        "top-level YAML mapping keys, so a JSON, JSONC, or TOML config, or one "
        "whose hooks arrive through extends: or remotes:, yields nothing to "
        "verify and nothing here can vouch for the hooks git will run"
    )


def hooks_dir(repo_root: Path) -> Path:
    """Return the directory git reads hooks from.

    ``--git-path hooks`` yields a path relative to git's working directory when
    the repository is addressed relatively, so resolve it against ``repo_root``
    rather than the interpreter's cwd.
    """
    raw = _git(repo_root, "rev-parse", "--git-path", "hooks")
    if not raw:
        raise GitQueryError("git returned an empty hooks path")
    path = Path(raw)
    return path if path.is_absolute() else repo_root / path


def _dispatch_pattern(hook: str) -> re.Pattern[str]:
    """Match a line that hands ``hook`` to lefthook, quoted or bare."""
    return re.compile(rf"lefthook\s+run\s+[\"']?{re.escape(hook)}[\"']?(?![\w-])")


def _executed_lines(content: str) -> list[str]:
    """Return the lines of ``content`` a shell would execute.

    A ``#`` comment is documentation, not something ``/bin/sh`` runs, so no
    claim about what a shim does may be read from one. The shebang is a comment
    by this rule and carries no dispatch anyway.

    Single source of what "executed" means for this module: both the
    machine-bound-path scan and the dispatch check read it, so the two cannot
    disagree about whether a commented line counts.
    """
    return [line for line in content.splitlines() if not line.lstrip().startswith("#")]


def _dispatches_to_lefthook(hook: str, content: str) -> bool:
    """Return whether ``content`` actually hands ``hook`` to lefthook.

    Scanning the whole file would accept a hook whose only mention of the
    dispatch sits in a comment. A file holding ``# lefthook run pre-commit``
    and an ``exit 0`` runs nothing, so reading that as a working shim is a
    false negative in the detector: the gate would pass an inert hook and
    report the repository as protected while no lefthook job ever fires.

    Reading every executed line has the same hole one step further in. A bare
    ``exit 0`` above a real dispatch line is executed text, so it survives
    :func:`_executed_lines`, and the dispatch below it never runs. The scan
    therefore stops at the first ``exit`` no enclosing block guards, tracking
    ``if``/``case``/``while``/``until``/``for`` against ``fi``/``esac``/``done``
    so the shim's own ``LEFTHOOK=0`` early return, which sits inside an ``if``,
    keeps counting as conditional.
    """
    pattern = _dispatch_pattern(hook)
    depth = 0
    for line in _executed_lines(content):
        if pattern.search(line) is not None:
            return True
        stripped = line.strip()
        if _BLOCK_OPEN.match(stripped):
            depth += 1
        elif _BLOCK_CLOSE.match(stripped):
            depth = max(depth - 1, 0)
        elif depth == 0 and _UNCONDITIONAL_EXIT.match(stripped):
            return False
    return False


def _machine_bound_paths(content: str) -> list[str]:
    """Return absolute paths in ``content`` that do not resolve the same everywhere.

    Comment lines are exempt: a path named in a comment is documentation, not
    something the shell will execute. The shebang is a comment by this rule and
    is machine-independent anyway.
    """
    found: list[str] = []
    for line in _executed_lines(content):
        for match in _ABSOLUTE_PATH.finditer(line):
            token = match.group(0)
            if token.startswith(_MACHINE_INDEPENDENT_PATHS):
                continue
            if token not in found:
                found.append(token)
    return found


def shim_defect(hook: str, path: Path) -> str | None:
    """Return why ``path`` is not a usable worktree-safe shim, or None.

    The test is semantic, not a byte comparison against :func:`hook_shim`. Two
    reasons, and the second is not hypothetical. Issue #4789's fourth acceptance
    criterion is that the gate "passes from both worktrees after either
    install", which a byte comparison cannot deliver: any two installers writing
    equally safe but differently worded shims would each fail the other's check,
    and whichever ran last would win. That happened during this change, when a
    second agent installed a near-identical shim into the shared hooks directory
    and an exact comparison rejected it. A shim that dispatches to the right
    hook and binds to no machine is correct, however it is spelled.
    """
    if path.is_symlink():
        return (
            f"{path} is a symlink, not a regular file, so git runs whatever it "
            "points at and one checkout can aim the shared hook at its own tree"
        )
    if not path.is_file():
        return f"{path} is missing"
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"{path} could not be read as text: {exc}"
    if not os.access(path, os.X_OK):
        return f"{path} is not executable, so git will ignore it"
    if _VENV_PATH.search(content) is not None:
        return (
            f"{path} bakes in an absolute '/.venv/' path, so it names one "
            "checkout's virtual environment and breaks for every other worktree"
        )
    bound = _machine_bound_paths(content)
    if bound:
        return (
            f"{path} runs the absolute path '{bound[0]}', which belongs to one "
            "machine or checkout rather than to every worktree sharing this hook"
        )
    if not _dispatches_to_lefthook(hook, content):
        return f"{path} never hands the '{hook}' hook to lefthook"
    return None


def find_defects(repo_root: Path) -> tuple[list[str], int]:
    """Return the shim defects and how many hooks were examined.

    A present config that yields no hook is itself a defect, never a pass. The
    zero-hook case used to reach ``_report_check`` as ``0 of 0`` and exit 0,
    which is the shape of a gate that examined nothing reported as a gate that
    found nothing wrong (``.claude/rules/ci-scripts.md`` MUST 12).
    """
    configs = config_paths(repo_root)
    if not configs:
        return [], 0
    hooks = declared_hook_names(repo_root)
    if not hooks:
        return [unreadable_config_defect(configs)], 0
    directory = hooks_dir(repo_root)
    defects = [
        defect
        for hook in hooks
        if (defect := shim_defect(hook, directory / hook)) is not None
    ]
    return defects, len(hooks)


def run_lefthook_install(repo_root: Path) -> None:
    """Run ``lefthook install --reset-hooks-path`` so lefthook records its state.

    Clears any ``core.hooksPath`` override and writes lefthook's config checksum
    to ``$GIT_COMMON_DIR/info/lefthook.checksum``. The shim files it writes here
    are overwritten immediately afterwards; only the bookkeeping is wanted.
    """
    argv = ["uv", "run", "--frozen", "lefthook", "install", "--reset-hooks-path"]
    try:
        result = subprocess.run(
            argv,
            cwd=str(repo_root),
            check=False,
            timeout=_INSTALL_TIMEOUT_SECONDS,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitQueryError(f"{' '.join(argv)} failed to execute: {exc}") from exc
    if result.stdout:
        print(result.stdout, file=sys.stderr, end="")
    if result.returncode != 0:
        raise GitQueryError(f"{' '.join(argv)} exited {result.returncode}")


def _replace_with_shim(path: Path, body: str) -> None:
    """Put ``body`` at ``path`` as an executable regular file, in one step.

    Several worktrees run this installer against the one shared hooks
    directory, so every intermediate state a concurrent reader can observe has
    to be a valid one. ``Path.write_text`` gives two bad ones: it truncates in
    place, so a reader can exec a zero-length or half-written script, and the
    ``chmod`` that follows leaves a newly created hook at the umask default
    until it lands. Git skips a non-executable hook and prints no warning, so
    that window is silent.

    Writing a sibling temporary file and renaming it over the destination
    closes both. ``os.replace`` is atomic within a directory, and it also
    removes the need to unlink a symlink first: the rename replaces the link
    itself rather than writing through to whatever it points at, which keeps
    every write inside ``$GIT_COMMON_DIR/hooks``. The pid in the temporary name
    keeps two concurrent installers off each other's scratch file.
    """
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    replaced = False
    try:
        tmp.write_text(body, encoding="utf-8")
        tmp.chmod(_HOOK_MODE)
        os.replace(tmp, path)
        replaced = True
    finally:
        if not replaced:
            tmp.unlink(missing_ok=True)


def write_shims(repo_root: Path, hooks: list[str]) -> list[Path]:
    """Overwrite each defective hook file with its worktree-safe shim.

    Returns the paths that changed. A hook :func:`shim_defect` already accepts
    is left byte-for-byte alone, so two safe installers do not fight over it.
    """
    directory = hooks_dir(repo_root)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for hook in hooks:
        path = directory / hook
        if shim_defect(hook, path) is None:
            continue
        _replace_with_shim(path, hook_shim(hook))
        written.append(path)
    return written


def _report_check(defects: list[str], examined: int) -> int:
    """Print the --check verdict and return its ADR-035 exit code."""
    if not defects:
        print(f"lefthook shims: OK, {examined} of {examined} examined hooks are worktree-safe")
        return 0
    print(
        f"[FAIL] {len(defects)} lefthook shim problem(s) found across "
        f"{examined} examined hooks:",
        file=sys.stderr,
    )
    for defect in defects:
        print(f"    - {defect}", file=sys.stderr)
    print(f"Fix: {REPAIR_COMMAND}", file=sys.stderr)
    return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Install lefthook hook shims that every worktree can share."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report only: exit non-zero on a divergent shim and mutate nothing.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Worktree to operate on (default: the current worktree).",
    )
    return parser.parse_args(argv)


def _resolve_root(explicit: str | None) -> Path:
    """Return the worktree root to operate on."""
    start = Path(explicit).resolve() if explicit else Path.cwd()
    return Path(_git(start, "rev-parse", "--show-toplevel")).resolve()


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = parse_args(argv)
    try:
        repo_root = _resolve_root(args.repo_root)
    except GitQueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    configs = config_paths(repo_root)
    if not configs:
        print(f"error: no lefthook config under {repo_root}", file=sys.stderr)
        return 2

    try:
        if args.check:
            defects, examined = find_defects(repo_root)
            return _report_check(defects, examined)

        hooks = declared_hook_names(repo_root)
        if not hooks:
            print(f"error: {unreadable_config_defect(configs)}", file=sys.stderr)
            return 2
        run_lefthook_install(repo_root)
        written = write_shims(repo_root, hooks)
        defects, examined = find_defects(repo_root)
    except GitQueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    print(
        f"lefthook shims: rewrote {len(written)} of {examined} examined hooks in "
        f"{hooks_dir(repo_root)}"
    )
    if defects:
        for defect in defects:
            print(f"    - {defect}", file=sys.stderr)
        print("error: shims are still not worktree-safe after the rewrite", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
