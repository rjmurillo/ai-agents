#!/usr/bin/env python3
"""Run the /pr-review completion gate against a pull request.

Reads completion_criteria from a config YAML, dispatches each criterion's
verification command, parses the resulting JSON, and evaluates the
``pass_when`` expression. Prints a per-criterion result table. Exits 0 if
every criterion passes, 1 if any criterion fails.

This replaces the prior narrative completion gate where the agent claimed
verdicts like "0 unresolved threads". Each verdict is now produced by an
external command whose JSON output IS the source of truth. The script
dispatches; it does not narrate.

The ``pass_when`` mini-DSL supports:

  * dotted path access:        ``stdout-json.unresolved_count``
  * literals:                  integers, ``true``, ``false``, ``null``,
                               and double-quoted strings
  * comparison operators:      ``==``, ``!=``
  * boolean composition:       ``AND``, ``OR`` (left-to-right; no parens)

The ``stdout-json`` prefix denotes the parsed JSON object on the
command's stdout. Any other dotted prefix is treated as a literal lookup
into the same object (so ``stdout-json.x`` and ``x`` are equivalent).

Each criterion may set ``fail_open: true`` to treat dispatch errors
(non-zero exit, non-JSON stdout) as a pass. Default is ``fail_open:
false``: if the command misbehaves, the criterion fails closed. This
matches the retrospective's "Reporting-Without-Acting Anti-Pattern"
guidance: a verifier that cannot verify must not be silently treated as
having verified.

If the DSL is insufficient, a criterion may instead specify
``pass_when_python: "lambda d: <expr>"``. The expression receives the
parsed stdout-json dict and must return a truthy/falsy value. The
lambda is parsed with ``ast`` and evaluated through a safe subset
(boolean composition, comparisons, constants, and ``d.get(...)``
lookups); arbitrary Python does NOT run. Prefer ``pass_when`` where
possible.

Trust model
-----------

This dispatcher executes ``command`` strings read from the YAML config,
so the config must come from an origin the checked-out PR cannot write.
There are exactly TWO such origins, and conflating them is what earlier
revisions of this paragraph did:

  * A **repository** config, the default. ``--config`` is canonicalised
    and rejected unless it lives under the repository root via
    ``scripts.utils.path_validation.validate_safe_path``, and its bytes
    are then verified against the trusted ref, because the repository
    root is exactly the tree the PR CAN write.
  * An **install-trusted** config (issue #5112, Option 1). It lives in a
    host-declared plugin root whose tree is DISJOINT from both the
    consumer's git work tree and ``_PROJECT_ROOT``, checked in both
    containment directions. Byte verification is skipped because there
    is nothing in the consumer repository to compare against; the origin
    carries the trust. See :func:`_install_trusted_root` for the four
    conditions and for what this does not close. The trust ANCHOR is
    still validated on this path, including the ``refs/remotes/*``
    requirement.

"Disjoint" is not "outside": a root of ``$HOME`` with the repository at
``$HOME/repo`` is outside the repository while containing every file the
PR wrote, and a one-way test admitted exactly that (CWE-829). The
``pass_when_python`` evaluator no longer calls ``eval``: it parses the
lambda with ``ast`` and walks a whitelisted node set, so a config
expression cannot reach Python's class hierarchy or any builtin. This
closes the arbitrary-code-execution surface the prior ``eval``-based
evaluator carried on PR-branch configs (see below).

PR-branch trust boundary (CWE-829)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When the dispatcher is invoked by ``/pr-review`` after checking out a
PR branch (via ``gh pr checkout``), the config it reads is the PR
branch's copy of ``pr-review-config.yaml`` -- NOT the trusted version
on the base branch. A malicious PR could edit
``completion_criteria.command`` and the dispatcher would execute it on
the reviewer's machine (CWE-829: inclusion of functionality from
untrusted control sphere). ``validate_safe_path`` keeps the file
inside the repo; it does NOT make the file trusted.

The dispatcher therefore verifies the CONFIG FILE itself, before any
criterion is dispatched: :func:`_verify_config_trust` compares the
working-tree config byte for byte against the copy at ``--trusted-ref``
(default ``origin/main``; must resolve to a remote-tracking ref under
``refs/remotes/*``, because ``HEAD`` or a local branch can be moved by
the checked-out PR and cannot anchor trust). The single buffer that is
verified is the same buffer that is parsed and dispatched (no CWE-367
window). The outcomes:

  * **trusted** -- bytes identical to the trusted blob after checkout
    filters (``git cat-file --filters`` reproduces the checkout
    conversion the local checkout applies to that path, so
    ``core.autocrlf`` consumers do not false-halt on line endings);
    dispatch proceeds.
  * **diverged** -- bytes differ (whitespace included; byte identity is
    the contract). The gate halts with exit 2 before executing any
    command and prints a unified diff to stderr.
  * **missing-base** -- the config does not exist at the trusted ref, so
    tampering is indistinguishable from a new file. Halt, exit 2.
  * **git-error** -- verification itself is impossible (not a git work
    tree, trusted ref absent or not remote-tracking, git missing or
    timing out). Halt, exit 3.
  * **install-trusted** -- the config lives inside a host-declared
    plugin root (``COPILOT_PLUGIN_ROOT`` / ``CLAUDE_PLUGIN_ROOT``) that
    is outside the consumer's work tree, so no comparison is attempted
    and dispatch proceeds (issue #5112, Option 1). This is an ORIGIN
    claim, not a verification outcome: the operator installed the
    directory and PR content cannot write it, which is the same
    reasoning ``_ARGV_EXTERNAL`` already applies to an installed-plugin
    script named in a criterion's argv. The in-repo ``.claude/``
    fallback is excluded by construction, because it is inside the work
    tree and therefore PR-controlled. See
    :func:`_install_trusted_root` for the four conditions and for the
    residual this does not close.

Before issue #5112 there was no such status and the bundled config was
unreachable rather than untrusted: containment refused any ``--config``
outside the project root, so an installed ``/pr-review`` halted before
the trust check ran at all. Widening only the origin, and leaving the
command boundary below untouched, is what keeps that fix from becoming
a general relaxation.

A human who has inspected the surfaced diff can approve execution
explicitly by re-running with ``--approve-untrusted-config``, which
proceeds through **diverged** and **missing-base** with a loud stderr
warning and records the trust status in the JSON payload. **git-error**
is never overridable: with verification impossible there is no
trustworthy diff a human could have inspected, so approval would turn
an unverifiable state into an execution path. Config evolution through
normal PRs needs no flag: once the change merges to the base branch,
working tree and trusted ref agree again.

Two properties of the anchor and the surfaced text:

  * Surfaced diffs and config excerpts are PR-controlled text shown to
    the human whose inspection authorizes approval. C0/C1 control
    characters and Unicode bidi controls in them are escaped to a
    visible ``\\uXXXX`` form before printing, so a terminal cannot
    render a different command than the one approval would execute
    (Trojan Source, CVE-2021-42574).
  * The trusted ref is a locally cached remote-tracking ref, so trust
    is anchored to the operator's last fetch of the base branch. A
    stale ref anchors to an OLDER base-branch state, which PR content
    still cannot move; the residual is a rollback to previously merged
    config. Fetch the base branch before running when freshness
    matters.

Dispatched-file trust boundary (CWE-829 / CWE-494)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A trusted config still NAMES files, and those files live in the same
checked-out PR tree. So once the config passes, and before any
criterion runs, :func:`_verify_command_trust` renders every criterion's
command with the same :func:`_format_command` the dispatcher uses and
byte-compares each argv element that resolves to a git-tracked file
inside the work tree against its copy at ``--trusted-ref``. The
outcomes mirror the config check: **trusted** proceeds, **untrusted**
(bytes differ, or the file is absent at the trusted ref) halts with
exit 2 and lists the files, and **git-error** halts with exit 3 and is
never overridable. ``--approve-untrusted-config`` covers the untrusted
case as well; there is one approval model, not two.

What is classified, and why:

  * Option flags (leading ``-``), the substituted PR number, bare
    interpreter names that are not paths (``python3`` resolves under
    the cwd but no such file exists), and directories are skipped:
    there is nothing to compare. Classification is by token shape and
    by what is on disk, never by argv position. There is no
    option-position tracking, so an option VALUE that names an existing
    file is classified exactly like any other path token. That is how
    a tracked ``--dispositions-file`` value comes to be compared.
  * Files OUTSIDE the git work tree are recorded in
    ``command_trust.skipped_external_files`` and not compared. An
    absolute interpreter path or an installed-plugin script cannot be
    rewritten by a PR to the consumer repository, and it has no
    trusted-ref copy to compare against.
  * UNTRACKED work-tree files are recorded in
    ``command_trust.skipped_untracked_files`` and not compared. PR
    content arrives through a checkout, so it is always tracked; an
    untracked file is the operator's own state, such as a local scratch
    fixture a reviewer writes during the review. Comparing those would
    halt every real run against a trusted-ref copy that cannot exist.

    ``--dispositions-file`` used to be the example here and is no longer
    a safe one. Classification follows the git state of the workspace
    this runs in, nothing else, and that answer differs by workspace.
    In the upstream repository, PR #5481 committed
    ``.agents/pr-checks/dispositions.json``, the path the shipped config
    passes, so there it is tracked and compared, and a PR that edits it
    halts the gate until the change is approved. That is the posture to
    want for a file whose contents can wave a red check through. In an
    installed-plugin consumer it is not the same file. Each marketplace
    maps ``project-toolkit`` to one root and only one, ``./.claude`` in
    ``.claude-plugin/marketplace.json`` and ``./src/copilot-cli`` in
    ``.github/plugin/marketplace.json``, and neither root contains the
    upstream ``.agents`` tree, so a consumer workspace has no such path
    until someone writes one, and a file written there is untracked and
    skipped exactly as before.
  * A repo-local path whose resolution leaves the work tree (a
    PR-committed symlink) or cannot be resolved fails closed as
    untrusted: the link is PR content and its target has no trusted-ref
    copy (CWE-59).

Static imports are inside the boundary too. Every argv-named ``.py``
file is parsed with ``ast`` and each module it imports is resolved
against the roots that script can actually import from: its own
directory, any ``lib`` directory in an ancestor at or below the work
tree, and the work tree root. Resolution recurses, so the whole
work-tree import closure is verified. This is not hypothetical
tidiness: all five verifiers the shipped ``pr-review-config.yaml``
names put ``<repo>/.claude/lib`` on ``sys.path`` and import
``github_core.api`` before doing any work, so leaving imports outside
the boundary left the CVSS 8.8 path open with every named script
byte-identical to the trusted ref (PR #5146 security review, F-1).

The closure was chosen over verifying the containing directory
because a directory rule halts on any sibling change, including files
no criterion loads, and that is what trains an operator to pass
``--approve-untrusted-config`` by reflex. The closure covers what
actually executes and nothing else.

Scope of the guarantee
~~~~~~~~~~~~~~~~~~~~~~

``config_trust: trusted`` plus ``command_trust: trusted`` asserts that
the config, every tracked work-tree file its commands name, and that
closure's statically-resolvable work-tree imports are the trusted ref's
copies. What remains outside, and is covered by neither field:

  * **Dynamically resolved imports.** ``importlib`` by computed name,
    an ``exec`` of file contents, a ``sys.path`` entry built at runtime
    from a value this module does not model, or a C extension loaded by
    path. The closure is static, so it cannot see these.
  * **Untracked work-tree files.** Recorded, not compared. PR content
    arrives through a checkout and is therefore tracked, so this is a
    scoping decision rather than a gap in coverage of PR content. A
    path that is untracked because it sits in a submodule or nested
    repository is NOT skipped; it fails closed.
  * **This dispatcher.** ``run_completion_gate.py`` lives in the same
    PR tree; a PR that rewrites it to skip the check executes attacker
    code while printing a trusted verdict. Nothing a script asserts
    about itself can close that.
  * **The window between verification and dispatch.** Unlike the config
    check, which verifies the exact buffer it then parses, the command
    check verifies files on disk and ``_evaluate_criterion`` re-opens
    them when it executes (CWE-367). Anything able to write to the work
    tree between the two can swap a verified file. That is a local
    attacker, not the PR under review, whose content is fixed at
    checkout; do not read the config check's no-TOCTOU property as
    extending here.

Each residual is the same exposure as running any test or lint on a PR
branch. Do not read these fields as covering them.

Substitution
------------

Only ``{pr}`` is substituted into ``command`` templates, and the
substituted value is the integer ``--pull-request`` argument validated
by argparse (``type=int``) plus a positivity check. Other ``{...}``
slots present in the surrounding ``pr-review-config.yaml`` (for
example ``{thread_id}`` or ``{body}`` in the thread-resolution scripts)
belong to other consumers and are not handled here. Future maintainers
extending this dispatcher must re-validate every new slot they add.

Exit codes follow ADR-035:
    0 - All criteria passed
    1 - At least one criterion failed (or had an evaluation error)
    2 - Config/usage error (config missing, malformed, no criteria, or
        untrusted: diverged from / absent at the trusted ref)
    3 - External error (trust verification impossible: git failed)
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import os
import re
import shlex
import subprocess
import sys
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple


# Resolve the project root by walking up to find the ``scripts/``
# package. A fixed ``parents[N]`` index works for the canonical
# ``.claude/skills/.../pr/`` location but breaks for the
# ``src/copilot-cli/skills/.../pr/`` mirror (one extra ``src/`` level)
# and for an installed plugin (the script lives under
# ``~/.copilot/installed-plugins/`` with no ``scripts/`` tree above it).
# The walk resolves the right root regardless of where the script lives.
def _resolve_project_root() -> Path:
    here = Path(__file__).resolve().parent
    for ancestor in (here, *here.parents):
        if (ancestor / "scripts" / "utils" / "path_validation.py").is_file():
            return ancestor
    # Installed-plugin context (issue #2572): the script is bundled without the
    # repo's scripts/ tree. The plugin runs with cwd = the user's repo, so
    # resolve the project root from the working directory by walking up for a
    # repo marker. This makes the default config path and path containment base
    # point at the user's repo, not the installed-plugins directory.
    cwd = Path.cwd().resolve()
    for ancestor in (cwd, *cwd.parents):
        if (ancestor / ".claude").is_dir() or (ancestor / ".git").exists():
            return ancestor
    return cwd


_PROJECT_ROOT = _resolve_project_root()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from scripts.utils.path_validation import validate_safe_path
except ModuleNotFoundError:
    # Installed-plugin fallback (issue #2572): the repo's top-level scripts/
    # package is not bundled with the skill, so the canonical import is
    # unavailable when the user's repo is not ai-agents itself.
    # Canonical source:
    # scripts/utils/path_validation.py::validate_safe_path. Contract quote:
    # "Resolve path safely within base directory."
    # Divergence: this fallback is local to installed-plugin execution and
    # implements only the containment contract needed by this script.
    def validate_safe_path(path: str | Path, base_dir: str | Path) -> Path:
        """Resolve ``path`` under ``base_dir`` and reject any escape."""
        resolved_base = Path(base_dir).resolve()
        if not resolved_base.exists():
            raise FileNotFoundError(f"Base directory does not exist: {base_dir}")
        if not resolved_base.is_dir():
            raise ValueError(f"Base path is not a directory: {base_dir}")
        resolved_path = (resolved_base / path).resolve()
        try:
            resolved_path.relative_to(resolved_base)
        except ValueError:
            raise ValueError(
                f"Path {path} is outside base directory {base_dir}"
            ) from None
        return resolved_path

# PyYAML is a hard dependency for this script. The rest of the codebase
# already requires PyYAML; matching that is simpler than maintaining a
# stdlib-only loader and avoids the schema-drift risk of a partial parser.
try:
    import yaml as _yaml_module
    yaml: Any = _yaml_module
    _HAVE_YAML = True
except ImportError:  # pragma: no cover - exercised when PyYAML missing
    yaml = None
    _HAVE_YAML = False


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


_DEFAULT_CONFIG_PATH = (
    _PROJECT_ROOT / ".claude" / "commands" / "pr-review-config.yaml"
)


class ConfigError(Exception):
    """Schema or load error in the completion-gate config.

    Raised by :func:`_read_config_bytes`, :func:`_load_config_bytes`,
    and :func:`_evaluate_criterion` to
    distinguish a config bug (which the dispatcher exits 2 for, per
    ADR-035) from a criterion that legitimately failed (exit 1).
    """


class WorkTreeUnavailableError(Exception):
    """The consumer's git work tree could not be established.

    Raised by :func:`_consumer_work_tree` and handled in
    :func:`_resolve_and_read_config`, which exits **3**, not 2. Per
    ADR-035 and this repo's exit-code table (0 ok, 1 logic, 2 config,
    3 external, 4 auth), a git probe that cannot run, times out, or
    reports no work tree is an EXTERNAL failure. The config path is not
    what is wrong, so reporting it as one sends the reader to the wrong
    place. This is the same reasoning that already makes
    :data:`TRUST_GIT_ERROR` exit 3 and non-overridable: with the extent
    of PR-controlled content unknown, no approval could be informed.

    It is raised only after a plugin-root variable has been declared and
    named an existing directory. A run with neither variable set never
    probes git and is unaffected.
    """


def _read_config_bytes(path: Path) -> bytes:
    """Read the config exactly once. Raises ConfigError on any failure mode.

    The returned buffer is what gets trust-verified AND parsed, so there
    is no window for the file to change between the two (CWE-367).
    """
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"Cannot read config {path}: {exc}") from exc


def _load_config_bytes(raw: bytes, path: Path) -> dict[str, Any]:
    """Parse config bytes as YAML. Raises ConfigError on any failure mode.

    ``RecursionError`` is caught alongside ``yaml.YAMLError`` because it
    is not a YAMLError subclass: deeply nested untrusted input would
    otherwise escape as a traceback and exit 1, which this script's
    ADR-035 contract reserves for "a criterion failed", not "the config
    could not be parsed".
    """
    if not _HAVE_YAML:
        # Name the interpreter rather than a bare `pip install`. The shipped
        # skill invokes this through `uv run python`, which resolves to the
        # consumer project's environment, while a bare `pip` targets whatever
        # is first on PATH. Those can differ, so the old text could send an
        # operator to install PyYAML somewhere the next run never looks.
        raise ConfigError(
            "PyYAML is required to parse the completion-gate config; install "
            f"it for the interpreter running this script ({sys.executable}). "
            "Under uv that is `uv run --with pyyaml python ...`; a bare "
            "`pip install pyyaml` may target a different environment.",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"Config {path} is not valid UTF-8: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except (yaml.YAMLError, RecursionError) as exc:
        raise ConfigError(f"Cannot parse config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(
            f"Config root must be a mapping, got {type(data).__name__}",
        )
    return data




# ---------------------------------------------------------------------------
# Config trust verification (CWE-829)
# ---------------------------------------------------------------------------


# Trust statuses returned by _verify_config_trust.
TRUST_TRUSTED = "trusted"
TRUST_DIVERGED = "diverged"
TRUST_MISSING_BASE = "missing-base"
TRUST_GIT_ERROR = "git-error"
# Usage-error status used by _enforce_config_trust before verification
# runs: a syntactically malformed --trusted-ref is a CLI usage error
# (exit 2), not a verification outcome, so it does not reuse
# TRUST_GIT_ERROR (whose contract is exit 3).
TRUST_MALFORMED_REF = "malformed-ref"
# Trust status for a config that lives inside a host-declared plugin root
# outside the consumer's work tree (issue #5112, Option 1). It is NOT a
# verification outcome: nothing is compared against the trusted ref,
# because there is nothing in the consumer repository to compare against.
# The origin itself carries the trust, exactly as _ARGV_EXTERNAL already
# treats an installed-plugin script the argv names.
TRUST_INSTALL_TRUSTED = "install-trusted"

# Host-declared plugin roots, in the order resolve_pr_review_config() in
# .claude/commands/pr-review.md consults them. Quoted verbatim from that
# function per .claude/rules/canonical-source-mirror.md, first two list
# entries only (the rest are the in-repo and installed-plugin fallbacks,
# which this constant deliberately does not cover):
#
#     for root in \
#       "${COPILOT_PLUGIN_ROOT:-}" \
#       "${CLAUDE_PLUGIN_ROOT:-}" \
#       ...
#       if [ -n "$root" ] && [ -f "$root/commands/pr-review-config.yaml" ]; then
#
# The loop CONTINUES when a root is set but does not hold the config, so
# COPILOT_PLUGIN_ROOT being set does not by itself exclude
# CLAUDE_PLUGIN_ROOT. _host_declared_roots below matches that: it yields
# both in order and the caller falls through to the second when the
# first does not contain the config.
#
# An earlier revision cited ${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}
# as the canonical form. That expression lives elsewhere and means
# something DIFFERENT: it selects COPILOT_PLUGIN_ROOT whenever that is
# set, with no fall-through on a missing config. Copying its semantics
# here would have broken the second-root case. Found by Copilot review
# on PR #5329.
_PLUGIN_ROOT_ENV_VARS = ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")

# This dispatcher's own location, used to bind install trust to the plugin
# that SHIPS this file. Module-level so tests can rebind it; the value is
# never read from the environment.
#
# Being a directory the host named is not evidence the root belongs to us.
# This repository already documents that it may not: _resolve_lib_dir in
# pr-comment-responder/scripts/cluster_threads.py says COPILOT_PLUGIN_ROOT is
# "set by the Copilot CLI host, may point to whichever plugin triggered the
# context-mode hook, not this one", and resolve_pr_conflicts.py records the
# same for CLAUDE_PLUGIN_ROOT under issue #4961. Both defend by validating
# each candidate before use; this function did not.
#
# Reproduced before the fix (Copilot review, PR #5329): a co-installed plugin
# root exported as COPILOT_PLUGIN_ROOT, holding its own
# commands/pr-review-config.yaml, was install-trusted, and its criterion
# `sh -c '...'` EXECUTED, printing its marker to stderr. Command trust caught
# nothing because a bare `sh`, an option `-c`, and an option VALUE are all
# skipped, so no argv token resolved to a work-tree file (CWE-829).
_DISPATCHER_PATH = Path(__file__).resolve()

# A trusted ref must look like a git revision and must not start with
# ``-`` so it can never be parsed as a git option (argument injection).
_TRUSTED_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@^~{}-]*$")

_GIT_TIMEOUT_SECONDS = 30

def _escape_terminal_controls(text: str) -> str:
    """Render PR-controlled text safely for the approving human's terminal.

    PR-controlled text (diffs, config excerpts) is shown to the human
    whose inspection authorizes --approve-untrusted-config. Unicode
    format characters (category Cf, which includes the bidi controls
    such as U+202E) can make a terminal display a different command
    than the one that would execute (Trojan Source, CVE-2021-42574),
    and C0/C1 controls (category Cc, e.g. CR, ESC) can overwrite or
    restyle previously printed lines. Every Cc/Cf character except
    newline and tab is therefore rendered as a visible ``\\uXXXX``
    escape.
    """
    return "".join(
        ch
        if ch in ("\n", "\t")
        or unicodedata.category(ch) not in ("Cc", "Cf")
        else f"\\u{ord(ch):04x}"
        for ch in text
    )


class TrustCheck(NamedTuple):
    """Outcome of comparing the on-disk config against the trusted ref.

    ``status`` is one of the TRUST_* constants. ``detail`` carries the
    unified diff for :data:`TRUST_DIVERGED` and the error description
    for the other non-trusted statuses; it is empty when trusted.
    """

    status: str
    detail: str


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
    """Run a git command, capturing raw bytes.

    Byte capture matters because ``git cat-file --filters`` output is
    compared byte for byte against the working-tree config; decoding
    would corrupt the comparison on non-UTF-8 content.
    """
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
    )


def _require_remote_tracking_ref(
    trust_anchor_ref: str,
    cwd: Path,
) -> TrustCheck | None:
    """``None`` when the ref anchors trust; a git-error TrustCheck otherwise.

    The ref must resolve to ``refs/remotes/*``. ``HEAD``, a local branch, a
    tag, and a bare SHA are all refused, because the checked-out PR can move
    or create them, which would make trust self-referential: the PR's own
    content would become the thing its content is compared against.

    Extracted so the install-trusted path and :func:`_verify_config_trust`
    cannot diverge. They did: this check lived only in the latter, which
    install trust skips, and `--trusted-ref HEAD` then let command trust
    compare PR-modified verifiers against the PR's own commit and execute
    them (Copilot review, PR #5329). One implementation, two callers, is
    what keeps the two paths honest about the same requirement.
    """
    # Guarded HERE, not at the call sites. _verify_config_trust happens to
    # call this inside its own try, but the install-trusted caller invokes it
    # directly, so a git timeout or a missing binary escaped as a traceback
    # and exit 1 instead of the documented non-overridable exit 3. Putting
    # the catch in the shared helper is what stops the two callers from
    # disagreeing about it, which is the same failure that produced this
    # helper in the first place (Copilot review, PR #5329).
    try:
        proc = _run_git(
            ["rev-parse", "--symbolic-full-name", trust_anchor_ref], cwd,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return TrustCheck(
            TRUST_GIT_ERROR,
            f"could not resolve trusted ref {trust_anchor_ref!r}: {exc}",
        )
    full_name = proc.stdout.decode(errors="replace").strip()
    if proc.returncode == 0 and full_name.startswith("refs/remotes/"):
        return None
    return TrustCheck(
        TRUST_GIT_ERROR,
        f"trusted ref {trust_anchor_ref!r} must resolve to a "
        f"remote-tracking ref (refs/remotes/*), got "
        f"{full_name or 'a local, detached, or unknown revision'}; "
        f"HEAD and local branches can be moved by the checked-out "
        f"PR and cannot anchor trust",
    )


def _verify_config_trust(
    config_path: Path,
    trust_anchor_ref: str,
    tree_bytes: bytes,
) -> TrustCheck:
    """Compare ``tree_bytes`` byte for byte against the trusted-ref copy.

    ``tree_bytes`` is the single read of the config the caller will also
    parse and dispatch from, so the bytes verified ARE the bytes executed
    (no TOCTOU window between verification and parse; CWE-367).

    Byte identity is deliberate: a whitespace-only or comment-only edit
    still halts, because "close enough" comparison is exactly where a
    tampered ``completion_criteria.command`` would hide. The trusted side
    is read with ``git cat-file --filters``, which applies the same
    checkout conversion (EOL, working-tree-encoding) the working tree
    received, so a consumer repo with ``core.autocrlf`` does not
    false-halt on line endings alone. The claim is deliberately modest:
    custom smudge/process filter drivers can rewrite content
    arbitrarily, so a match proves the working tree carries the LOCAL
    CHECKOUT CONVERSION of the trusted content. Those drivers live in
    git config, which PR content cannot modify; a PR-controlled
    ``.gitattributes`` can only select among locally configured
    conversions, not define new filter commands.

    The trusted ref must resolve to a remote-tracking ref
    (``refs/remotes/*``). ``HEAD``, a local branch, a tag, or a bare SHA
    is refused: after ``gh pr checkout`` those can point at or be moved
    by the PR's own history, so "trusted" would be self-referential.

    The caller decides what each status means for the exit code; this
    function never raises.
    """
    try:
        proc = _run_git(["rev-parse", "--show-toplevel"], config_path.parent)
        if proc.returncode != 0:
            return TrustCheck(
                TRUST_GIT_ERROR,
                f"{config_path} is not inside a git work tree: "
                f"{proc.stderr.decode(errors='replace').strip()}",
            )
        toplevel = Path(proc.stdout.decode(errors="replace").strip())

        # The config's work tree must BE the project root's work tree.
        # rev-parse from config_path.parent resolves the NEAREST git
        # repository, so a config placed inside a PR-vendored nested
        # repository or initialized submodule would otherwise be
        # verified against that nested repository's origin/main, whose
        # remote the PR author can own, making an attacker-committed
        # config byte-identical to an attacker-controlled trusted ref.
        proc = _run_git(["rev-parse", "--show-toplevel"], _PROJECT_ROOT)
        if proc.returncode != 0:
            return TrustCheck(
                TRUST_GIT_ERROR,
                f"project root {_PROJECT_ROOT} is not inside a git work "
                f"tree: {proc.stderr.decode(errors='replace').strip()}",
            )
        project_toplevel = Path(proc.stdout.decode(errors="replace").strip())
        if toplevel.resolve() != project_toplevel.resolve():
            return TrustCheck(
                TRUST_GIT_ERROR,
                f"config {config_path} resides in a different git work "
                f"tree ({toplevel}) than the project root "
                f"({project_toplevel}); a nested repository or submodule "
                f"cannot anchor trust",
            )

        try:
            rel = config_path.resolve().relative_to(toplevel.resolve())
        except ValueError:
            return TrustCheck(
                TRUST_GIT_ERROR,
                f"config {config_path} resolves outside git work tree {toplevel}",
            )

        anchor_error = _require_remote_tracking_ref(trust_anchor_ref, toplevel)
        if anchor_error is not None:
            return anchor_error

        proc = _run_git(
            ["rev-parse", "--verify", "--quiet", f"{trust_anchor_ref}^{{commit}}"],
            toplevel,
        )
        if proc.returncode != 0:
            return TrustCheck(
                TRUST_GIT_ERROR,
                f"trusted ref {trust_anchor_ref!r} not found; fetch it or pass "
                f"--trusted-ref",
            )

        spec = f"{trust_anchor_ref}:{rel.as_posix()}"
        # Existence check via ls-tree, not ``cat-file -e``: cat-file -e
        # exits 128 for BOTH an absent path and a real object-store
        # error (probed on git 2.54), which would let a verification
        # failure masquerade as the approvable missing-base status.
        # ls-tree separates them structurally: a nonzero exit is an
        # error (never approvable, exit 3); an empty stdout on exit 0
        # is a genuinely absent path.
        proc = _run_git(
            ["ls-tree", trust_anchor_ref, "--", rel.as_posix()], toplevel,
        )
        if proc.returncode != 0:
            return TrustCheck(
                TRUST_GIT_ERROR,
                f"git ls-tree {trust_anchor_ref} -- {rel.as_posix()} failed: "
                f"{proc.stderr.decode(errors='replace').strip()}",
            )
        if not proc.stdout.strip():
            # missing-base is approvable, so the human must be shown the
            # exact content approval would execute. With no trusted copy
            # to diff against, surface the whole working-tree config as
            # a full-file addition diff.
            addition_diff = "".join(
                difflib.unified_diff(
                    [],
                    tree_bytes.decode(errors="replace").splitlines(
                        keepends=True,
                    ),
                    fromfile=f"{spec} (absent)",
                    tofile=f"{rel.as_posix()} (working tree)",
                )
            )
            return TrustCheck(
                TRUST_MISSING_BASE,
                f"{rel.as_posix()} does not exist at {trust_anchor_ref}; a config "
                f"absent from the trusted ref cannot be distinguished from a "
                f"tampered one. The working-tree config that approval would "
                f"dispatch:\n{addition_diff}",
            )

        proc = _run_git(["cat-file", "--filters", spec], toplevel)
        if proc.returncode != 0:
            return TrustCheck(
                TRUST_GIT_ERROR,
                f"git cat-file --filters {spec} failed: "
                f"{proc.stderr.decode(errors='replace').strip()}",
            )
        anchor_bytes = proc.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        return TrustCheck(TRUST_GIT_ERROR, f"trust verification failed: {exc}")

    if anchor_bytes == tree_bytes:
        return TrustCheck(TRUST_TRUSTED, "")

    diff = difflib.unified_diff(
        anchor_bytes.decode(errors="replace").splitlines(keepends=True),
        tree_bytes.decode(errors="replace").splitlines(keepends=True),
        fromfile=spec,
        tofile=f"{rel.as_posix()} (working tree)",
    )
    return TrustCheck(TRUST_DIVERGED, "".join(diff))


def _enforce_config_trust(
    config_path: Path,
    trust_anchor_ref: str,
    approved: bool,
    tree_bytes: bytes,
    install: InstallTrust | None = None,
) -> tuple[TrustCheck, int | None]:
    """Gate dispatch on config trust; returns ``(trust, exit_code_or_None)``.

    ``None`` means dispatch may proceed. A non-``None`` exit code means the
    gate halted before executing any criterion command: 2 for a malformed
    ref or an untrusted config (diverged / missing-base), 3 when trust
    verification itself is impossible (git-error), per ADR-035.

    ``approved`` covers diverged and missing-base only: those surface an
    inspectable diff or file for the human to have reviewed. git-error is
    never overridable, because approving with nothing to inspect would
    turn an unverifiable state into an execution path.

    ``install``, when not ``None``, carries the host-declared plugin root
    that install-trusts this config (issue #5112, Option 1). Verification
    is skipped rather than attempted: the config is outside the
    consumer's work tree, so the trusted ref has no copy of it to compare
    against and :func:`_verify_config_trust` would return git-error, which
    is not overridable and would halt at exit 3. That is precisely the
    dead end the issue reports. Skipping is sound only because the origin
    carries the trust, which is what :func:`_install_trusted_root`
    establishes; do not extend this branch to any config the consumer
    repository can write.
    """
    # Ref validation runs BEFORE the install-trusted short-circuit, not
    # after. Both guards on --trusted-ref used to sit on the path install
    # trust skips: this regex, and the refs/remotes/* requirement inside
    # _verify_config_trust. _enforce_command_trust repeats neither, so an
    # install-trusted config left the ref wholly unvalidated while command
    # trust still consumed it.
    #
    # Reproduced before this fix (Copilot review, PR #5329, High):
    # --trusted-ref HEAD under install trust made command trust compare
    # every work-tree verifier against the PR's OWN commit, so a
    # PR-modified verify.sh was declared trusted and EXECUTED (its stderr
    # marker reached the output). An option-shaped ref likewise reached a
    # git invocation. Widening the config origin must not widen the
    # command boundary, and skipping these checks did exactly that.
    if not _TRUSTED_REF_RE.match(trust_anchor_ref):
        print(
            f"Refusing malformed --trusted-ref {trust_anchor_ref!r}",
            file=sys.stderr,
        )
        return TrustCheck(TRUST_MALFORMED_REF, "malformed trusted ref"), 2

    if install is not None:
        # The regex admits HEAD, so it alone does not close the reproduction
        # above. The refs/remotes/* requirement is the one that does, and
        # _verify_config_trust (its usual home) is skipped here, so enforce
        # it directly, in the work tree the install decision was made
        # against rather than in some other repository.
        anchor_error = _require_remote_tracking_ref(
            trust_anchor_ref, install.work_tree,
        )
        if anchor_error is not None:
            print(anchor_error.detail, file=sys.stderr)
            return anchor_error, 3
        return (
            TrustCheck(
                TRUST_INSTALL_TRUSTED,
                f"config {config_path} is install-trusted: it resides in "
                f"host-declared plugin root {install.root}, outside the "
                f"consumer work tree, which PR content cannot write",
            ),
            None,
        )

    trust = _verify_config_trust(config_path, trust_anchor_ref, tree_bytes)
    if trust.status == TRUST_TRUSTED:
        return trust, None

    if trust.status == TRUST_GIT_ERROR:
        # Approval requires an inspectable artifact. On git-error there is
        # no trustworthy diff a human could have reviewed, so approving
        # would turn an unverifiable state into an execution path
        # (PR #5089 agent-safety finding). Never overridable.
        print(
            f"HALT: completion-gate config {config_path} cannot be "
            f"verified ({trust.status}) against {trust_anchor_ref}; no "
            f"criterion command was executed.",
            file=sys.stderr,
        )
        if trust.detail:
            print(_escape_terminal_controls(trust.detail), file=sys.stderr)
        print(
            "--approve-untrusted-config does not apply when verification "
            "is impossible: there is no trustworthy diff to inspect. Fix "
            "the environment or fetch the trusted ref.",
            file=sys.stderr,
        )
        return trust, 3

    if not approved:
        print(
            f"HALT: completion-gate config {config_path} is not trusted "
            f"({trust.status}) against {trust_anchor_ref}; no criterion "
            f"command was executed.",
            file=sys.stderr,
        )
        if trust.detail:
            print(_escape_terminal_controls(trust.detail), file=sys.stderr)
        print(
            "If a human has inspected the diff above and approves "
            "executing this config, re-run with --approve-untrusted-config.",
            file=sys.stderr,
        )
        return trust, 2

    print(
        f"WARNING: executing completion-gate config {config_path} "
        f"despite trust status {trust.status!r} against {trust_anchor_ref} "
        f"(--approve-untrusted-config given).",
        file=sys.stderr,
    )
    if trust.detail:
        print(_escape_terminal_controls(trust.detail), file=sys.stderr)
    return trust, None


# ---------------------------------------------------------------------------
# pass_when DSL
# ---------------------------------------------------------------------------


def _resolve_path(data: dict, path: str) -> Any:
    """Resolve a dotted path against a parsed-stdout dict.

    The leading segment may be ``stdout-json`` (or absent); both refer to
    the dict itself. Returns ``None`` if any segment is missing, so the
    caller can compare against ``null`` literals.
    """
    segments = path.split(".")
    if segments and segments[0] == "stdout-json":
        segments = segments[1:]

    cur: Any = data
    for seg in segments:
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


def _parse_literal(token: str) -> Any:
    """Parse a single DSL literal: int, bool, null, or quoted string."""
    if token == "true":
        return True
    if token == "false":
        return False
    if token == "null":
        return None
    if (
        len(token) >= 2
        and token[0] == '"'
        and token[-1] == '"'
    ):
        return token[1:-1]
    try:
        return int(token)
    except ValueError as exc:
        raise ValueError(f"Unrecognized literal in pass_when: {token!r}") from exc


def _eval_atom(data: dict, atom: list[str]) -> bool:
    """Evaluate a 3-token atom: ``<path> <op> <literal>``."""
    if len(atom) != 3:
        raise ValueError(
            f"pass_when atom must have 3 tokens, got {atom!r}"
        )
    path, op, literal_tok = atom
    actual = _resolve_path(data, path)
    expected = _parse_literal(literal_tok)
    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    raise ValueError(f"Unsupported pass_when operator: {op!r}")


def _eval_pass_when(data: dict, expr: str) -> bool:
    """Evaluate a pass_when expression against parsed stdout-json data.

    Tokens are split with ``shlex.split(posix=False)`` so double-quoted
    string literals stay intact (``"PR merged"`` remains one token, not
    two). Atoms are joined left-to-right with ``AND`` / ``OR``
    connectives; AND and OR have equal precedence and evaluate strictly
    in order (no parentheses). Atoms are pure dict lookups, so the
    evaluation order does not affect correctness.
    """
    try:
        tokens = shlex.split(expr, posix=False)
    except ValueError as exc:
        raise ValueError(f"pass_when tokenization failed: {exc}") from exc
    if not tokens:
        raise ValueError("pass_when expression is empty")

    result: bool | None = None
    pending_op: str | None = None
    i = 0
    while i < len(tokens):
        atom = tokens[i:i + 3]
        i += 3
        atom_value = _eval_atom(data, atom)

        if result is None:
            result = atom_value
        elif pending_op == "AND":
            result = result and atom_value
        elif pending_op == "OR":
            result = result or atom_value
        else:
            raise ValueError(
                f"Missing AND/OR connective before atom {atom!r}"
            )

        if i >= len(tokens):
            break

        pending_op = tokens[i]
        if pending_op not in ("AND", "OR"):
            raise ValueError(
                f"Expected AND/OR, got {pending_op!r}"
            )
        i += 1
        # Per Copilot review: a trailing connective with no atom after
        # it (e.g. ``x == 1 AND``) silently passed before because the
        # outer loop checked ``i < len(tokens)`` only at the top. Catch
        # it explicitly: an AND/OR must be followed by another atom.
        if i >= len(tokens):
            raise ValueError(
                f"pass_when ends with dangling connective {pending_op!r}",
            )

    return bool(result)


# Comparison-operator AST node -> Python operation. Only these
# comparison forms are permitted in a pass_when_python lambda.
_COMPARE_OPS: dict[type[ast.cmpop], Any] = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Is: lambda a, b: a is b,
    ast.IsNot: lambda a, b: a is not b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


class _UnsafeExpressionError(ValueError):
    """A pass_when_python lambda used a construct outside the safe subset."""


def _parse_pass_when_python(expr: str) -> ast.Lambda:
    """Parse and structurally validate a pass_when_python lambda.

    Returns the ``ast.Lambda`` node for a single ``lambda <param>: <body>``
    form. Raises ``ValueError`` on any malformed or non-lambda input so the
    caller fails closed.
    """
    if not isinstance(expr, str):
        raise ValueError("pass_when_python must be a string")
    expr = expr.strip()
    if not expr.startswith("lambda"):
        raise ValueError("pass_when_python must be a lambda expression")
    if "\n" in expr or "\r" in expr:
        raise ValueError("pass_when_python must be a single line")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"pass_when_python is not valid Python: {exc}") from exc
    node = tree.body
    if not isinstance(node, ast.Lambda):
        raise ValueError("pass_when_python must be a lambda expression")
    args = node.args
    if (
        len(args.args) != 1
        or args.vararg is not None
        or args.kwarg is not None
        or args.kwonlyargs
        or args.posonlyargs
        or args.defaults
    ):
        raise ValueError(
            "pass_when_python lambda must take exactly one positional argument",
        )
    return node


def _eval_node(node: ast.AST, param_name: str, data: dict) -> Any:
    """Evaluate one whitelisted AST node against the bound ``data`` dict.

    Supports the closed set a completion criterion needs: boolean
    composition (``and``/``or``), ``not``, comparisons (including ``is`` and
    ``in``), constants, tuple/list membership operands, the single lambda
    parameter (which resolves to ``data``), and ``<param>.get(key[, default])``
    lookups. Any other node raises ``_UnsafeExpressionError`` so an unexpected
    construct fails closed instead of executing.
    """
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result: Any = True
            for value in node.values:
                result = _eval_node(value, param_name, data)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            result: Any = False
            for value in node.values:
                result = _eval_node(value, param_name, data)
                if result:
                    return result
            return result
        raise _UnsafeExpressionError(f"unsupported boolean op: {type(node.op).__name__}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, param_name, data)
    if isinstance(node, ast.Compare):
        return _eval_compare(node, param_name, data)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id != param_name:
            raise _UnsafeExpressionError(f"unknown name: {node.id}")
        return data
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_eval_node(elt, param_name, data) for elt in node.elts]
    if isinstance(node, ast.Call):
        return _eval_call(node, param_name, data)
    raise _UnsafeExpressionError(f"unsupported expression node: {type(node).__name__}")


def _eval_compare(node: ast.Compare, param_name: str, data: dict) -> bool:
    """Evaluate a (possibly chained) comparison against the safe op table."""
    left = _eval_node(node.left, param_name, data)
    result = True
    for op, comparator in zip(node.ops, node.comparators, strict=True):
        op_fn = _COMPARE_OPS.get(type(op))
        if op_fn is None:
            raise _UnsafeExpressionError(
                f"unsupported comparison op: {type(op).__name__}",
            )
        right = _eval_node(comparator, param_name, data)
        if not op_fn(left, right):
            return False
        left = right
    return result


def _eval_call(node: ast.Call, param_name: str, data: dict) -> Any:
    """Evaluate the only permitted call form: ``<param>.get(key[, default])``."""
    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Name)
        and func.value.id == param_name
    ):
        raise _UnsafeExpressionError(
            "only <param>.get(...) calls are allowed in pass_when_python",
        )
    if node.keywords or not 1 <= len(node.args) <= 2:
        raise _UnsafeExpressionError(
            "<param>.get(...) takes one or two positional arguments",
        )
    key = _eval_node(node.args[0], param_name, data)
    default = (
        _eval_node(node.args[1], param_name, data)
        if len(node.args) == 2
        else None
    )
    if not isinstance(data, dict):
        return default
    return data.get(key, default)


def _eval_pass_when_python(data: dict, expr: str) -> bool:
    """Evaluate a pass_when_python expression via a safe AST walk.

    The expression must be a single ``lambda d: ...`` form. The lambda
    receives the parsed stdout-json dict and is evaluated through
    ``_eval_node``, which accepts only a whitelisted node set (boolean
    composition, comparisons, constants, membership operands, the single
    parameter, and ``<param>.get(...)`` lookups). ``eval`` is never called,
    so a config expression cannot reach builtins or the class hierarchy.
    Any out-of-subset construct raises and the caller fails closed.
    """
    node = _parse_pass_when_python(expr)
    param_name = node.args.args[0].arg
    return bool(_eval_node(node.body, param_name, data))


# ---------------------------------------------------------------------------
# Criterion dispatch
# ---------------------------------------------------------------------------


def _format_command(template: str, pr_number: int) -> list[str]:
    """Render a command template with ``{pr}`` substitution and split it.

    ``pr_number`` MUST be an int. The CLI is the only validated entry
    point: argparse coerces ``--pull-request`` to int and ``main``
    rejects non-positive values before this function is reached. This
    assertion documents that contract for any future caller and
    forecloses CWE-78 via stringly-typed PR identifiers.
    """
    if not isinstance(pr_number, int) or isinstance(pr_number, bool):
        raise TypeError(f"pr_number must be int, got {type(pr_number).__name__}")
    rendered = template.replace("{pr}", str(pr_number))
    return shlex.split(rendered)


def _parse_stdout_json(stdout: str) -> dict | None:
    """Return parsed JSON dict from stdout or None if unparseable."""
    text = stdout.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _validate_criterion_schema(criterion: dict) -> tuple[str, str, str | None, str | None]:
    """Schema-check one criterion. Raises ConfigError on any violation.

    Returns ``(name, command, pass_when, pass_when_python)``.

    Schema rules (mirror scripts/validate_pr_review_config.py):
      * ``verification`` must be ``"command"`` (only kind supported).
      * ``command`` must be a non-empty string. Bot review feedback:
        if YAML parses ``command`` as a list (e.g. due to indentation),
        ``_format_command`` would crash later; catch the type error here.
      * ``fail_open``, when present, must be a real bool. Truthy
        non-bools (``"yes"``, ``1``) silently change gate behavior;
        reject them at schema time.
      * Exactly one of ``pass_when`` / ``pass_when_python`` must be set.
    """
    if not isinstance(criterion, dict):
        raise ConfigError(f"criterion is not a mapping: {criterion!r}")

    # Per Copilot review: presence-with-default lets a missing or
    # wrong-typed ``name``/``verification`` slip through. Require them
    # explicitly and type-check ``name`` so the validator and the
    # dispatcher reject the same configs.
    if "name" not in criterion:
        raise ConfigError("criterion missing required field: name")
    name = criterion["name"]
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(
            f"criterion: name must be a non-empty string "
            f"(got {type(name).__name__})",
        )
    if "verification" not in criterion:
        raise ConfigError(
            f"criterion {name!r}: missing required field: verification",
        )
    verification = criterion["verification"]
    if verification != "command":
        raise ConfigError(
            f"criterion {name!r}: unsupported verification kind "
            f"{verification!r} (expected 'command')",
        )
    cmd_template = criterion.get("command", "")
    if not isinstance(cmd_template, str) or not cmd_template:
        raise ConfigError(
            f"criterion {name!r}: command must be a non-empty string "
            f"(got {type(cmd_template).__name__})",
        )
    if "fail_open" in criterion and not isinstance(criterion["fail_open"], bool):
        raise ConfigError(
            f"criterion {name!r}: fail_open must be a boolean "
            f"(got {type(criterion['fail_open']).__name__})",
        )

    pass_when = criterion.get("pass_when")
    pass_when_python = criterion.get("pass_when_python")
    # Type-check both expression fields when present. The validator
    # already does this; mirror it here so a config that bypasses
    # the standalone validator (direct dispatcher invocation) cannot
    # smuggle a non-string into the eval/DSL paths.
    for field, value in (
        ("pass_when", pass_when),
        ("pass_when_python", pass_when_python),
    ):
        if field in criterion and (
            not isinstance(value, str) or not value.strip()
        ):
            raise ConfigError(
                f"criterion {name!r}: {field} must be a non-empty string "
                f"(got {type(value).__name__})",
            )
    if pass_when and pass_when_python:
        raise ConfigError(
            f"criterion {name!r}: pass_when and pass_when_python are "
            f"mutually exclusive; specify exactly one",
        )
    if not pass_when and not pass_when_python:
        raise ConfigError(
            f"criterion {name!r}: missing pass_when or pass_when_python",
        )
    return name, cmd_template, pass_when, pass_when_python


# ---------------------------------------------------------------------------
# Dispatched-command trust verification (CWE-829 / CWE-494)
# ---------------------------------------------------------------------------


# Statuses returned by _verify_command_trust. Kept distinct from the
# TRUST_* config constants: the config check has a missing-base outcome
# that this check folds into "untrusted" (a verifier file absent from the
# trusted ref is PR-supplied code, and there is no separate approvable
# state for it).
COMMAND_TRUST_TRUSTED = "trusted"
COMMAND_TRUST_UNTRUSTED = "untrusted"
COMMAND_TRUST_GIT_ERROR = "git-error"

# Classification of a single argv element by _classify_argv_token.
_ARGV_SKIP = "skip"
_ARGV_VERIFY = "verify"
_ARGV_EXTERNAL = "external"
_ARGV_ESCAPES = "escapes"


class CommandTrustCheck(NamedTuple):
    """Outcome of verifying the files a config's commands name.

    ``checked_files`` and ``untrusted_files`` hold work-tree-relative
    POSIX paths (``untrusted_files`` also carries the raw token of any
    repo-local path that escapes the work tree). ``skipped_external_files``
    holds absolute paths outside the work tree and
    ``skipped_untracked_files`` work-tree paths git does not track;
    both are recorded but never compared. ``detail`` carries the error
    description when ``status`` is :data:`COMMAND_TRUST_GIT_ERROR`.
    """

    status: str
    checked_files: list[str]
    untrusted_files: list[str]
    skipped_external_files: list[str]
    skipped_untracked_files: list[str]
    detail: str


def _is_within(path: Path, root: Path) -> bool:
    """True when ``path`` is ``root`` or lies under it."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _are_disjoint(first: Path, second: Path) -> bool:
    """True when neither path is at or under the other.

    Containment in EITHER direction is the thing callers care about, and
    testing only one of them is a live defect shape rather than a style
    point: :func:`_install_trusted_root` shipped a one-way test and a
    declared plugin root that was an ANCESTOR of the project passed it
    while every PR-controlled file sat inside that root (CWE-829, found
    by Copilot review on PR #5329). Naming the symmetric question once
    keeps the two directions from drifting apart again.
    """
    return not (_is_within(first, second) or _is_within(second, first))


def _first_symlinked_component(candidate: Path, root: Path) -> Path | None:
    """First symlinked component of ``candidate`` at or below ``root``.

    Shared by the config check (:func:`_symlinked_config_component`) and
    argv classification, because both face the same hazard: resolving a
    path follows its symlinks, so what gets verified is the TARGET while
    the LINK is what the PR actually controls and what the config
    actually named (CWE-59 link following).

    Only components at or below ``root`` are inspected. Those are the
    ones PR content can create; a symlink above the root, such as a
    symlinked home directory, is the operator's own environment and must
    not false-halt the gate.
    """
    probe = Path(candidate.parts[0])
    for part in candidate.parts[1:]:
        probe = probe / part
        if not _is_within(probe, root):
            continue
        try:
            if probe.is_symlink():
                return probe
        except OSError:
            return probe
    return None


def _classify_argv_token(token: str, toplevel: Path) -> tuple[str, str]:
    """Classify one argv element for trust verification.

    Returns ``(kind, value)`` where kind is one of the ``_ARGV_*``
    constants:

      * ``_ARGV_SKIP`` -- nothing to verify: an option flag, a PR
        number, a bare interpreter name that is not a path (``python3``
        resolves under the cwd but no such file exists), or a
        directory. Only the leading-hyphen test is by shape; every
        other token is classified by what is on disk. An option value
        is not skipped for being one, so a value naming an existing
        file falls through to the cases below like any other path.
      * ``_ARGV_VERIFY`` -- an existing file inside the work tree; the
        value is its work-tree-relative POSIX path. Whether git tracks
        it is decided later, in one batched probe
        (:func:`_tracked_subset`), because this function runs no
        subprocess.
      * ``_ARGV_EXTERNAL`` -- an existing file outside the work tree (an
        absolute interpreter path, an installed-plugin script). The
        value is its absolute path. PR content cannot rewrite it through
        the consumer repository, so it is recorded and not compared.
      * ``_ARGV_ESCAPES`` -- a repo-local path that reaches its target
        through a symlink, or that cannot be resolved at all. Fail
        closed. ANY symlinked component at or below the work tree is
        refused, not only one whose target leaves the tree: resolution
        follows the link, so a link pointing at a different in-tree file
        would have the TARGET byte-compared while the LINK, which is the
        path the config actually named and the blob the PR actually
        controls, went unverified (CWE-59). The config path is refused
        on the same rule by :func:`_symlinked_config_component`.

    Relative tokens resolve against the current working directory
    because that is what ``subprocess.run`` in :func:`_evaluate_criterion`
    inherits, so the path classified here is the path executed.
    :func:`_verify_command_trust` refuses to run at all when the cwd is
    outside the work tree, so that equivalence always holds.
    """
    if not token or token.startswith("-"):
        return _ARGV_SKIP, ""

    candidate = Path(token)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    # normpath collapses ".." lexically without following symlinks.
    # Path.relative_to is purely lexical, so it would otherwise accept
    # "<toplevel>/../etc/passwd" as living inside the work tree.
    literal = Path(os.path.normpath(candidate))

    if _first_symlinked_component(literal, toplevel) is not None:
        return _ARGV_ESCAPES, token

    try:
        resolved = candidate.resolve()
        resolved_is_file = resolved.is_file()
    except OSError:
        return (_ARGV_ESCAPES, token) if _is_within(literal, toplevel) else (
            _ARGV_SKIP,
            "",
        )

    if not _is_within(resolved, toplevel):
        # Defense in depth. The symlink pre-check above already refuses
        # every repo-local link, so reaching here means resolution left
        # the tree by some route that check did not see, such as a link
        # created between the two calls. Fail closed either way.
        if _is_within(literal, toplevel):
            return _ARGV_ESCAPES, token
        return (_ARGV_EXTERNAL, str(resolved)) if resolved_is_file else (
            _ARGV_SKIP,
            "",
        )

    if not resolved_is_file:
        return _ARGV_SKIP, ""
    return _ARGV_VERIFY, resolved.relative_to(toplevel).as_posix()


def _collect_command_paths(
    criteria: list[Any],
    pr_number: int,
    toplevel: Path,
) -> tuple[list[str], list[str], list[str]]:
    """Resolve every criterion command into the paths trust must cover.

    Returns ``(to_verify, external, escaping)``, each de-duplicated and
    in first-seen order. Commands are rendered with the same
    :func:`_format_command` the dispatcher uses, so the argv classified
    here is the argv executed.

    Raises :class:`ConfigError` on a schema violation or an unparseable
    command line; the caller exits 2 per ADR-035.
    """
    to_verify: list[str] = []
    external: list[str] = []
    escaping: list[str] = []
    buckets = {
        _ARGV_VERIFY: to_verify,
        _ARGV_EXTERNAL: external,
        _ARGV_ESCAPES: escaping,
    }

    for criterion in criteria:
        _, cmd_template, _, _ = _validate_criterion_schema(criterion)
        try:
            argv = _format_command(cmd_template, pr_number)
        except ValueError as exc:
            raise ConfigError(
                f"command is not a parseable command line: {exc}",
            ) from exc
        for token in argv:
            kind, value = _classify_argv_token(token, toplevel)
            bucket = buckets.get(kind)
            if bucket is not None and value not in bucket:
                bucket.append(value)

    return to_verify, external, escaping


def _import_roots(script: Path, toplevel: Path) -> list[Path]:
    """Directories a work-tree script can import from, most specific first.

    Reproduces where the shipped verifiers actually look. Each one puts a
    plugin ``lib`` directory on ``sys.path`` before importing from it,
    for example
    ``.claude/skills/github/scripts/pr/get_unresolved_review_threads.py``
    resolves ``github_core.api`` to ``.claude/lib/github_core/api.py``.
    So the roots are the script's own directory (sibling modules), every
    ``lib`` directory in an ancestor at or below the work tree, and the
    work tree itself (top-level packages such as ``scripts.utils``).
    """
    roots = [script.parent]
    for ancestor in script.parents:
        if not _is_within(ancestor, toplevel):
            continue
        lib = ancestor / "lib"
        if lib.is_dir():
            roots.append(lib)
    roots.append(toplevel)
    return roots


def _imported_module_names(source: bytes) -> list[tuple[int, str]]:
    """``(level, dotted)`` for every import in ``source``; [] if unparseable.

    ``level`` is 0 for an absolute import and the number of leading dots
    for a relative one. Relative imports must be carried through rather
    than dropped: the shipped ``github_core.api`` reaches its siblings
    with ``from .log_safety import ...``, so ignoring them would leave
    most of the library outside the closure while looking complete.

    Both the module and each imported name are emitted, because
    ``from pkg import mod`` cannot be told from ``from pkg import func``
    without importing; the resolver simply finds nothing for a function.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((0, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base:
                found.append((node.level, base))
            for alias in node.names:
                found.append(
                    (node.level, f"{base}.{alias.name}" if base else alias.name),
                )
    return found


def _relative_import_root(script: Path, level: int, toplevel: Path) -> list[Path]:
    """Package directory a ``level``-dotted relative import resolves from.

    ``from .x import y`` in ``pkg/mod.py`` reads ``pkg/x``; each extra
    dot climbs one more directory. Returns an empty list when climbing
    would leave the work tree, so a crafted ``from ..... import x``
    cannot reach outside it.
    """
    base = script.parent
    for _ in range(level - 1):
        base = base.parent
    return [base] if _is_within(base, toplevel) else []


def _resolve_module_file(dotted: str, roots: list[Path], toplevel: Path) -> str | None:
    """Work-tree-relative path of ``dotted``, or None when not in the tree.

    A name that resolves nowhere in the work tree is standard library or
    an installed dependency: not PR content, so not this boundary's
    concern. Resolution stops at the first root that has the module,
    matching ``sys.path`` order.
    """
    parts = [part for part in dotted.split(".") if part]
    if not parts:
        return None
    for root in roots:
        for candidate in (
            root.joinpath(*parts).with_suffix(".py"),
            root.joinpath(*parts, "__init__.py"),
        ):
            if not candidate.is_file() or not _is_within(candidate, toplevel):
                continue
            if _first_symlinked_component(candidate, toplevel) is not None:
                continue
            return candidate.relative_to(toplevel).as_posix()
    return None


def _expand_import_closure(rel_paths: list[str], toplevel: Path) -> list[str]:
    """``rel_paths`` plus every work-tree module they transitively import.

    Closes the transitive-import half of CWE-829. Verifying only the
    argv-named script leaves the modules that script imports at load time
    PR-controlled, and in this repository that is not hypothetical: all
    five shipped verifiers import ``github_core.api`` from the work
    tree's plugin ``lib`` directory before doing any work, so a PR that
    rewrote that module got code execution with every named script
    byte-identical to the trusted ref.

    Deliberately the import CLOSURE rather than the containing
    directory: a directory rule would halt on any sibling change, which
    is what trains operators to pass the approval flag by reflex. The
    closure covers what actually executes and nothing else, so a PR that
    edits an unrelated script in the same directory still runs clean.

    Best-effort by construction. Dynamic imports, ``importlib`` by
    computed name, and ``sys.path`` entries this function does not model
    are not covered; see the module docstring's scope section.
    """
    seen = list(rel_paths)
    queue = [path for path in rel_paths if path.endswith(".py")]
    while queue:
        current = queue.pop()
        script = toplevel / current
        try:
            source = script.read_bytes()
        except OSError:
            continue
        absolute_roots = _import_roots(script, toplevel)
        for level, dotted in _imported_module_names(source):
            roots = (
                absolute_roots
                if level == 0
                else _relative_import_root(script, level, toplevel)
            )
            found = _resolve_module_file(dotted, roots, toplevel)
            if found is None or found in seen:
                continue
            seen.append(found)
            queue.append(found)
    return seen


def _tracked_subset(rel_paths: list[str], toplevel: Path) -> tuple[set[str], str]:
    """Which of ``rel_paths`` git tracks; ``(tracked, error)``.

    Trust is scoped to tracked files because the threat is PR content,
    and PR content arrives through a checkout, so it is always tracked.
    An untracked work-tree file is the operator's own state (a local
    scratch fixture, a reviewer's private copy of a config); comparing
    it would halt every real run against a trusted-ref copy that cannot
    exist, which trains operators to pass the approval flag by reflex.
    ``--dispositions-file`` used to be the example here, and it is a
    poor one now because the answer depends on the workspace: upstream,
    PR #5481 committed the path the shipped config passes, so there it
    is tracked and compared; in an installed-plugin consumer, which
    receives no ``.agents`` tree, any file written at that path is
    untracked and skipped. This probe reports the workspace it is given
    and takes no position beyond it. A non-empty ``error`` means the
    probe itself failed and the caller must halt.

    ``-z`` because paths are not newline-safe and ``core.quotePath``
    would otherwise escape non-ASCII names out of alignment with the
    paths passed in.

    Every path is passed as an explicit ``:(literal)`` pathspec. Git
    reads pathspec magic from a leading ``:`` even after ``--``, so a
    tracked file literally named ``:(glob)evil.py`` would otherwise
    never match its own path, come back absent, and be classified
    untracked, which SKIPS verification and hands the PR arbitrary code
    execution. ``:(literal)`` disables that parsing. The results are
    still plain paths, so the caller's membership test is unaffected.
    """
    if not rel_paths:
        return set(), ""
    pathspecs = [f":(literal){path}" for path in rel_paths]
    proc = _run_git(["ls-files", "-z", "--", *pathspecs], toplevel)
    if proc.returncode != 0:
        return set(), (
            f"git ls-files failed: "
            f"{proc.stderr.decode(errors='replace').strip()}"
        )
    listed = proc.stdout.decode(errors="replace").split("\0")
    return {path for path in listed if path}, ""


def _verify_worktree_file_trust(
    rel_path: str,
    toplevel: Path,
    trust_anchor_ref: str,
) -> tuple[bool, str]:
    """Compare one work-tree file byte for byte against the trusted ref.

    Returns ``(is_trusted, error)``. A non-empty ``error`` means
    verification itself was impossible and ``is_trusted`` carries no
    meaning; the caller halts with exit 3.

    Mirrors :func:`_verify_config_trust`: existence is probed with
    ``git ls-tree`` (whose nonzero exit is structurally an error, unlike
    ``cat-file -e``), and the trusted bytes come from
    ``git cat-file --filters`` so checkout conversion (EOL,
    working-tree-encoding) is applied to the trusted side too. Divergence
    from that function: a path absent at the trusted ref is untrusted
    rather than a separate missing-base status, because a verifier script
    the base branch does not have is PR-supplied code with nothing to
    compare against.
    """
    spec = f"{trust_anchor_ref}:{rel_path}"
    # ":(literal)" for the same reason as in _tracked_subset: a leading
    # ":" in a filename is pathspec magic even after "--". Here an
    # unmatched path fails closed (absent at the trusted ref reads as
    # untrusted), so this is defense in depth rather than a live hole.
    proc = _run_git(
        ["ls-tree", trust_anchor_ref, "--", f":(literal){rel_path}"], toplevel,
    )
    if proc.returncode != 0:
        return False, (
            f"git ls-tree {trust_anchor_ref} -- {rel_path} failed: "
            f"{proc.stderr.decode(errors='replace').strip()}"
        )
    if not proc.stdout.strip():
        return False, ""

    proc = _run_git(["cat-file", "--filters", spec], toplevel)
    if proc.returncode != 0:
        return False, (
            f"git cat-file --filters {spec} failed: "
            f"{proc.stderr.decode(errors='replace').strip()}"
        )
    anchor_bytes = proc.stdout

    try:
        current_bytes = (toplevel / rel_path).read_bytes()
    except OSError as exc:
        return False, f"cannot read work-tree file {rel_path}: {exc}"

    return anchor_bytes == current_bytes, ""


def _is_in_nested_repository(rel_path: str, toplevel: Path) -> bool:
    """True when ``rel_path`` lives in a submodule or nested repository.

    ``git ls-files`` does not descend into a gitlink, so every file
    inside a submodule reads as untracked in the superproject. Untracked
    paths are skipped rather than compared, so a PR that converts a
    config-named path into a submodule would otherwise turn verification
    off for that path while the file still executes.

    Mirrors the nested-repository defense :func:`_verify_config_trust`
    already applies to the config file: resolve the work tree from the
    file's own directory and require it to BE the superproject's work
    tree. A nested repository's ``origin/main`` can be owned by the PR
    author, so it cannot anchor trust. Fails closed on any git error.
    """
    parent = (toplevel / rel_path).parent
    if not parent.is_dir():
        return False
    proc = _run_git(["rev-parse", "--show-toplevel"], parent)
    if proc.returncode != 0:
        return True
    nested = Path(proc.stdout.decode(errors="replace").strip())
    try:
        return nested.resolve() != toplevel
    except OSError:
        return True


def _verify_command_trust(
    criteria: list[Any],
    pr_number: int,
    trust_anchor_ref: str,
) -> CommandTrustCheck:
    """Verify every work-tree file the criterion commands name.

    Runs after the config passes its own trust check and before any
    criterion is dispatched, so a PR that leaves the config untouched
    while rewriting a verifier script cannot reach execution.

    Never raises except :class:`ConfigError` (schema violation in a
    criterion); git failures become :data:`COMMAND_TRUST_GIT_ERROR`.
    """
    try:
        proc = _run_git(["rev-parse", "--show-toplevel"], _PROJECT_ROOT)
        if proc.returncode != 0:
            return CommandTrustCheck(
                COMMAND_TRUST_GIT_ERROR, [], [], [], [],
                f"project root {_PROJECT_ROOT} is not inside a git work "
                f"tree: {proc.stderr.decode(errors='replace').strip()}",
            )
        toplevel = Path(proc.stdout.decode(errors="replace").strip()).resolve()

        # Relative argv elements resolve against the cwd, and so does the
        # dispatch in _evaluate_criterion. If the cwd is outside the work
        # tree being verified, those two agree with each other but not
        # with this check's containment test, so a work-tree script would
        # be classified external and skipped. Refuse to reason about it.
        if not _is_within(Path.cwd().resolve(), toplevel):
            return CommandTrustCheck(
                COMMAND_TRUST_GIT_ERROR, [], [], [], [],
                f"cwd {Path.cwd()} is outside the git work tree {toplevel}; "
                f"relative command paths cannot be classified",
            )

        named, external, escaping = _collect_command_paths(
            criteria, pr_number, toplevel,
        )
        candidates = _expand_import_closure(named, toplevel)
        tracked, probe_error = _tracked_subset(candidates, toplevel)
        if probe_error:
            return CommandTrustCheck(
                COMMAND_TRUST_GIT_ERROR, [], [], external, [], probe_error,
            )
        checked = [path for path in candidates if path in tracked]
        # An untracked candidate is skipped only when it is genuinely the
        # operator's own file. One that sits in a nested repository is
        # untracked for a different reason and fails closed.
        untracked = [
            path
            for path in candidates
            if path not in tracked and not _is_in_nested_repository(path, toplevel)
        ]
        nested = [
            path
            for path in candidates
            if path not in tracked and path not in untracked
        ]

        untrusted = list(escaping) + nested
        errors: list[str] = []
        for rel_path in checked:
            is_trusted, error = _verify_worktree_file_trust(
                rel_path, toplevel, trust_anchor_ref,
            )
            if error:
                errors.append(error)
            elif not is_trusted:
                untrusted.append(rel_path)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandTrustCheck(
            COMMAND_TRUST_GIT_ERROR, [], [], [], [],
            f"command trust verification failed: {exc}",
        )

    if errors:
        return CommandTrustCheck(
            COMMAND_TRUST_GIT_ERROR, checked, untrusted, external, untracked,
            "\n".join(errors),
        )
    if untrusted:
        return CommandTrustCheck(
            COMMAND_TRUST_UNTRUSTED, checked, untrusted, external, untracked, "",
        )
    return CommandTrustCheck(
        COMMAND_TRUST_TRUSTED, checked, [], external, untracked, "",
    )


def _enforce_command_trust(
    criteria: list[Any],
    pr_number: int,
    trust_anchor_ref: str,
    approved: bool,
) -> tuple[CommandTrustCheck, int | None]:
    """Gate dispatch on verifier-file trust; ``(check, exit_code_or_None)``.

    ``None`` means dispatch may proceed. Exit codes match
    :func:`_enforce_config_trust`: 2 for untrusted files, 3 when
    verification itself is impossible. ``approved`` is the same
    ``--approve-untrusted-config`` flag the config check honors (one
    approval model, not two) and, as there, it does not cover git-error.
    """
    trust = _verify_command_trust(criteria, pr_number, trust_anchor_ref)
    if trust.status == COMMAND_TRUST_TRUSTED:
        return trust, None

    if trust.status == COMMAND_TRUST_GIT_ERROR:
        print(
            f"HALT: completion-gate verifier files cannot be verified "
            f"against {trust_anchor_ref}; no criterion command was executed.",
            file=sys.stderr,
        )
        # Every COMMAND_TRUST_GIT_ERROR constructed above carries a
        # detail, so this needs no emptiness guard.
        print(_escape_terminal_controls(trust.detail), file=sys.stderr)
        print(
            "--approve-untrusted-config does not apply when verification "
            "is impossible: there is no trustworthy file listing to "
            "inspect. Fix the environment or fetch the trusted ref.",
            file=sys.stderr,
        )
        return trust, 3

    # Paths come from the PR-controlled config, so escape them before
    # printing (Trojan Source, CVE-2021-42574), same as the config diff.
    listing = _escape_terminal_controls(
        "\n".join(f"  {path}" for path in trust.untrusted_files),
    )
    if not approved:
        print(
            f"HALT: completion-gate verifier files differ from "
            f"{trust_anchor_ref} or are absent there; no criterion command was "
            f"executed. Untrusted files:\n{listing}",
            file=sys.stderr,
        )
        print(
            "If a human has inspected these files and approves executing "
            "them, re-run with --approve-untrusted-config.",
            file=sys.stderr,
        )
        return trust, 2

    print(
        f"WARNING: executing completion-gate verifier files that are not "
        f"trusted against {trust_anchor_ref} (--approve-untrusted-config "
        f"given). Untrusted files:\n{listing}",
        file=sys.stderr,
    )
    return trust, None


def _evaluate_criterion(criterion: dict, pr_number: int) -> dict:
    """Run one criterion's command and evaluate its pass_when expression.

    Returns a dict with: name, passed (bool), reason (str), command (str),
    exit_code (int|None), parsed (bool), stdout (str), stderr (str).

    Raises :class:`ConfigError` on any schema violation; the caller
    (``main``) translates that to exit 2 per ADR-035. Once the schema
    check passes, the function never raises: command failures, malformed
    output, and broken pass_when expressions are all reported as a
    failed criterion (with ``fail_open`` honored where applicable).

    Failure semantics:
      * Command not found / timeout / non-zero exit -> dispatch error;
        ``passed = fail_open``.
      * Stdout is not a JSON object -> dispatch error;
        ``passed = fail_open``.
      * pass_when raises (DSL syntax error, bad literal, broken lambda)
        -> evaluator failure; ``passed = False`` regardless of
        ``fail_open``. A verifier that ran successfully but whose
        contract cannot be evaluated is a config bug, not a verifier
        outage; masking it with ``fail_open`` would let a typo silently
        green the gate.
    """
    name, cmd_template, pass_when, pass_when_python = _validate_criterion_schema(criterion)
    # Schema check above already proved this is a real bool (or absent);
    # no permissive truthiness coercion here.
    fail_open = criterion.get("fail_open", False)

    result: dict = {
        "name": name,
        "passed": False,
        "reason": "",
        "command": "",
        "exit_code": None,
        "parsed": False,
        "stdout_json": None,
        "stdout": "",
        "stderr": "",
    }

    argv = _format_command(cmd_template, pr_number)
    result["command"] = " ".join(argv)

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        result["reason"] = f"command failed to run: {exc}"
        result["passed"] = fail_open
        return result

    result["exit_code"] = proc.returncode
    result["stdout"] = proc.stdout
    result["stderr"] = proc.stderr

    if proc.returncode != 0:
        result["reason"] = (
            f"command exited non-zero ({proc.returncode}); "
            f"fail_open={fail_open}; stderr={proc.stderr.strip()[:200]!r}"
        )
        result["passed"] = fail_open
        return result

    parsed = _parse_stdout_json(proc.stdout)
    if parsed is None:
        result["reason"] = (
            f"command stdout is not a JSON object; fail_open={fail_open}"
        )
        result["passed"] = fail_open
        return result

    result["parsed"] = True
    result["stdout_json"] = parsed

    try:
        if pass_when_python:
            verdict = _eval_pass_when_python(parsed, pass_when_python)
        else:
            verdict = _eval_pass_when(parsed, pass_when)
    except Exception as exc:
        # A broken pass_when expression is a config bug, not a verifier
        # outage. fail_open does NOT apply: masking a typo with a
        # green gate would defeat the dispatcher's purpose.
        #
        # Catching ``Exception`` (broad) is intentional: a
        # ``pass_when_python`` lambda body can raise anything
        # (``ZeroDivisionError``, ``IndexError``, custom domain
        # exceptions). Per CodeRabbit review, the prior tight-list
        # catch (ValueError, KeyError, ...) let those leak through.
        # ``KeyboardInterrupt`` and ``SystemExit`` are NOT caught
        # because they inherit from ``BaseException``.
        result["reason"] = f"pass_when error (fails closed): {exc}"
        result["passed"] = False
        return result

    result["passed"] = verdict
    if not verdict:
        result["reason"] = (
            f"pass_when evaluated false; stdout-json keys: "
            f"{sorted(parsed.keys())}"
        )
    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_table(rows: list[dict]) -> None:
    """Print a per-criterion result table to stdout.

    For failing rows, also prints the verifier's command and a short
    excerpt of stdout/stderr so the operator can triage without re-running
    the verifier separately. Per CodeRabbit review feedback: an operator
    reading the table should see the same evidence the JSON consumer sees.
    """
    print()
    print("Completion Gate Results")
    print("=" * 60)
    print(f"{'PASS':<6} {'CRITERION':<48}")
    print("-" * 60)
    for row in rows:
        marker = "PASS" if row["passed"] else "FAIL"
        print(f"{marker:<6} {row['name']:<48}")
        if not row["passed"]:
            if row.get("reason"):
                print(f"       reason: {row['reason']}")
            if row.get("command"):
                print(f"       command: {row['command']}")
            stdout_excerpt = (row.get("stdout") or "").strip()
            if stdout_excerpt:
                excerpt = stdout_excerpt.splitlines()[0][:200]
                print(f"       stdout: {excerpt}")
            stderr_excerpt = (row.get("stderr") or "").strip()
            if stderr_excerpt:
                excerpt = stderr_excerpt.splitlines()[0][:200]
                print(f"       stderr: {excerpt}")
    print("-" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the /pr-review completion gate.",
    )
    parser.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG_PATH),
        help="Path to pr-review-config.yaml",
    )
    parser.add_argument(
        "--pull-request",
        type=int,
        required=True,
        help="Pull request number",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a single JSON object rather than the human table",
    )
    parser.add_argument(
        "--evidence-path",
        default="",
        help="Write the completion gate JSON evidence to this repo-local path",
    )
    parser.add_argument(
        "--trusted-ref",
        # The flag and the JSON evidence key stay "trusted-ref"; only the
        # Python attribute is spelled differently. CodeQL's
        # py/clear-text-logging-sensitive-data treats any identifier
        # matching /trusted/ as a secret (its maybeSecret() heuristic
        # reads "trusted data" as a credential), so args.trusted_ref
        # flowing into the halt messages raised HIGH cleartext-logging
        # alerts on a value that is a git revision name, validated
        # against _TRUSTED_REF_RE and required to resolve to a
        # remote-tracking ref. "trust anchor" is also the accurate term
        # for what this ref is.
        dest="trust_anchor_ref",
        default="origin/main",
        help=(
            "Git ref holding the trusted copies; the working-tree config and "
            "every work-tree file its commands name must be byte-identical "
            "to it before any criterion runs"
        ),
    )
    parser.add_argument(
        "--approve-untrusted-config",
        action="store_true",
        help=(
            "Proceed although the config, or a verifier file its commands "
            "name, diverges from or is absent at the trusted ref. Pass ONLY "
            "after a human has inspected the surfaced diff and file list and "
            "explicitly approved them. Does NOT apply when "
            "verification itself is impossible (git-error exits 3 "
            "regardless): with nothing to inspect there is nothing a human "
            "could have approved"
        ),
    )
    return parser


def _assert_cwd_inside_project_root() -> None:
    cwd = Path.cwd().resolve()
    try:
        cwd.relative_to(_PROJECT_ROOT)
    except ValueError as exc:
        raise ConfigError(
            f"cwd {cwd} is outside resolved project root {_PROJECT_ROOT}",
        ) from exc


def _write_evidence(path_arg: str, payload: dict[str, Any]) -> None:
    _assert_cwd_inside_project_root()
    path = validate_safe_path(path_arg, _PROJECT_ROOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _try_write_evidence(path_arg: str, payload: dict[str, Any]) -> bool:
    if not path_arg:
        return True
    try:
        _write_evidence(path_arg, payload)
    except (ConfigError, FileNotFoundError, ValueError, OSError) as exc:
        print(f"Failed to write completion gate evidence: {exc}", file=sys.stderr)
        return False
    return True


def _symlinked_config_component(config_arg: str) -> Path | None:
    """First symlinked component of the config path under the project
    root, or ``None`` when the path has no PR-controlled symlink.

    ``validate_safe_path`` RESOLVES symlinks before its containment
    check, so a PR-committed symlink at ``pr-review-config.yaml`` (or a
    symlinked parent directory) passes containment while redirecting
    every later read to its target. The trust check then verifies the
    TARGET's path, and a local-only target such as an untracked
    ``.env`` or ``.git/config`` is absent from the trusted ref, so the
    missing-base halt would print the target file in full as the
    approval diff (CWE-59 link following; CWE-200 exposure). Only
    components at or below the project root are checked: those are the
    ones PR content can create, while a symlink above the root (for
    example a symlinked home directory) is the operator's own
    environment and must not false-halt the gate.
    """
    candidate = Path(config_arg)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return _first_symlinked_component(candidate, _PROJECT_ROOT)


def _resolve_or_none(path: Path) -> Path | None:
    """``path.resolve()``, or ``None`` when it cannot be resolved.

    Exists to normalize ONE portability trap into a single place.
    ``Path.resolve()`` does not raise a single exception family across the
    versions this ships to: on a symlink loop, CPython 3.10, 3.11 and 3.12
    raise ``RuntimeError("Symlink loop from ...")`` from ``pathlib``, while
    3.14 returns the unresolved path without raising. ``RuntimeError`` is
    not an ``OSError``, so an ``except OSError`` guard lets the loop escape
    as an unhandled traceback on exactly the interpreters the repo's
    hook-portability floor targets (``.claude/rules/python.md``: skill
    scripts run under the host's ambient interpreter, floor 3.10).

    Measured rather than assumed: grep of ``pathlib.py`` in the 3.10, 3.11
    and 3.12 stdlibs shows the raise; 3.14 returned the path for the same
    two-link loop. Found by Copilot review on PR #5329, which is a
    reminder that "it did not raise locally" says nothing about the
    versions a plugin is installed onto.

    Callers decide what ``None`` means. None of them may treat it as
    success: an unresolvable path cannot be shown to lie inside or outside
    any boundary.
    """
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return None


def _consumer_work_tree() -> Path:
    """The consumer's git work-tree root, or :exc:`WorkTreeUnavailableError`.

    This, and NOT ``_PROJECT_ROOT``, is the boundary install trust must be
    disjoint from. ``_resolve_project_root`` exists to locate the repo's
    ``scripts/`` package and falls back to the nearest ancestor of the cwd
    holding ``.claude`` OR ``.git``. That heuristic is fine for finding
    imports and is unsafe as a trust boundary, because **PR content can
    create a `.claude` directory** and thereby move it.

    The attack it enables (Copilot review, PR #5329): the host starts in
    ``repo/subdir``; the PR adds ``repo/subdir/.claude``; ``_PROJECT_ROOT``
    becomes ``repo/subdir``; a declared root of ``repo/.claude`` is then
    neither above nor below it, so a disjointness test anchored on
    ``_PROJECT_ROOT`` passes and a wholly PR-controlled config becomes
    install-trusted, skipping byte-identity verification (CWE-829).
    Reproduced end to end before this fix.

    ``git rev-parse --show-toplevel`` cannot be moved this way: it reports
    the real work tree, which is exactly the set of files the checked-out
    PR controls.

    Raises :exc:`WorkTreeUnavailableError` rather than returning a sentinel when
    git is absent, times out, errors, or reports no work tree for the cwd.
    That is an exit-3 ``git-error`` condition under this module's contract,
    not an exit-2 config problem: the failure is external, the config path
    may be perfectly well-formed, and it is the same "verification is
    impossible" state that :data:`TRUST_GIT_ERROR` already covers and
    deliberately makes non-overridable.

    An earlier revision returned ``None`` here and let the caller fall
    through to work-tree containment. It still failed closed, but it exited
    2 printing "Refusing to load config from unsafe path", which names the
    wrong cause: the path was not the problem, the unestablishable work tree
    was. Found by Copilot review on PR #5329.

    ``subprocess.TimeoutExpired`` is caught explicitly because it is NOT an
    ``OSError`` (its MRO is TimeoutExpired -> SubprocessError -> Exception),
    so an ``except OSError`` alone lets a 30-second git hang escape as an
    unhandled traceback. The two other guarded ``_run_git`` callers in this
    module already catch the pair; this one did not, which was the defect.
    """
    try:
        proc = _run_git(["rev-parse", "--show-toplevel"], Path.cwd())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkTreeUnavailableError(f"could not run git: {exc}") from exc
    if proc.returncode != 0:
        raise WorkTreeUnavailableError(
            f"git reported no work tree for {Path.cwd()}: "
            f"{proc.stderr.decode(errors='replace').strip()}",
        )
    toplevel = proc.stdout.decode(errors="replace").strip()
    if not toplevel:
        raise WorkTreeUnavailableError(
            f"git reported an empty work-tree root for {Path.cwd()}",
        )
    resolved = _resolve_or_none(Path(toplevel))
    if resolved is None:
        raise WorkTreeUnavailableError(
            f"work-tree root {toplevel!r} does not resolve",
        )
    return resolved


def _absolute_config_candidate(config_arg: str) -> Path:
    """``--config`` as an absolute path, resolved against the cwd once.

    One helper so every consumer of ``--config`` agrees on which file the
    argument names. ``validate_safe_path`` builds its result as
    ``(resolved_base / path).resolve()``, so a RELATIVE ``--config``
    resolves against whatever base it is handed. Passing a different base
    would therefore silently name a different file than the one an
    earlier check approved, which is the authorized-path-is-not-the-read-
    path shape this gate exists to prevent (see ``_verify_config_trust``
    on verifying the bytes that are executed).

    The cwd is the right anchor because it is what ``_symlinked_config_
    component`` already uses and what ``subprocess.run`` in
    :func:`_evaluate_criterion` inherits.
    """
    candidate = Path(config_arg)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate


class InstallTrust(NamedTuple):
    """A config admitted by its ORIGIN, with everything that decision used.

    Three fields, each carried rather than recomputed, because recomputing
    any of them reopens a hole:

    ``config_path`` is the resolved path :func:`_install_trusted_root`
    actually approved. Resolving ``--config`` a second time to read it is a
    TOCTOU window (CWE-367): a repo-controlled symlink swapped between the
    two calls resolves inside the root for the decision and outside it for
    the read, while ``root`` stays non-null and byte verification stays
    skipped. Found by Copilot review on PR #5329.

    ``work_tree`` is the boundary the decision was made against. It is also
    the repository the trust anchor must be validated in, and validating it
    somewhere else would answer a different question.
    """

    root: Path
    config_path: Path
    work_tree: Path


def _host_declared_roots() -> Iterator[Path]:
    """Existing directories named by the host's plugin-root variables.

    Named to avoid the substring ``_plugin_root``. That is not cosmetic:
    ``TestBootstrapSourceCode`` in ``tests/skills/github/test_bootstrap_fallback.py``
    selects "bootstrap scripts" with ``"_plugin_root" in f.read_text()`` and then
    requires each one to carry the literal
    ``os.path.isdir(os.path.join(_plugin_root, "lib", "github_core"))``.
    This module reads those variables to decide config TRUST and never puts a
    plugin root on ``sys.path`` (the only ``sys.path`` insert here is
    ``_PROJECT_ROOT``), so it has no ``_plugin_root`` variable and that literal
    would be dead code. An earlier name matched the fragment by accident and
    failed the guard. Do not reintroduce the fragment.

    Yields in ``_PLUGIN_ROOT_ENV_VARS`` order, so a host that exports both
    resolves through the Copilot variable first, and skips a variable that
    is unset, empty, whitespace, unresolvable, or not a directory. Declaring
    a root is necessary for install trust and nowhere near sufficient:
    :func:`_install_trusted_root` applies the boundary conditions.
    """
    for env_var in _PLUGIN_ROOT_ENV_VARS:
        raw = os.environ.get(env_var, "").strip()
        if not raw:
            continue
        root = _resolve_or_none(Path(raw))
        if root is not None and root.is_dir():
            yield root


def _install_trusted_root(config_arg: str) -> InstallTrust | None:
    """The host-declared plugin root that install-trusts ``config_arg``.

    Returns the resolved root when every condition below holds, else
    ``None`` (the caller then applies the normal work-tree containment
    and trusted-ref verification unchanged).

    Issue #5112: ``resolve_pr_review_config()`` in
    ``.claude/commands/pr-review.md`` offers plugin roots as config
    sources, but containment refused any ``--config`` outside
    ``_PROJECT_ROOT``, so an installed ``/pr-review`` whose config
    resolved to the bundled copy could not dispatch at all. Option 1 of
    that issue admits the bundled copy as a second trusted ORIGIN.

    Why an origin can carry trust here: the operator installed the
    plugin, and PR content cannot write into the install directory
    through the consumer repository. That is the same reasoning
    :func:`_classify_argv_token` already applies under ``_ARGV_EXTERNAL``
    to an installed-plugin script an argv names, so this widens the
    config boundary to match a boundary the gate already draws, rather
    than inventing a new trust class.

    Conditions, each load-bearing:

    1. ``COPILOT_PLUGIN_ROOT`` or ``CLAUDE_PLUGIN_ROOT`` is set and
       non-empty. An unset environment changes nothing.
       (Applied by :func:`_host_declared_roots`.)
    2. The root resolves to an existing directory.
       (Applied by :func:`_host_declared_roots`.)
    3. The resolved root is **disjoint** from BOTH the consumer's git
       work tree (:func:`_consumer_work_tree`) and ``_PROJECT_ROOT``,
       where disjoint means neither path is at or under the other
       (:func:`_are_disjoint`). All four containments are load-bearing
       and each direction failed once:

       * root under either boundary: withholds install trust from the
         in-repo fallback the same command offers, which the checked-out
         PR writes and which must keep the full byte-identity check.
       * either boundary under root: a declared root of ``$HOME`` with
         the project at ``$HOME/repo`` is not *below* the project, so a
         one-way test admitted it while it contained every PR-controlled
         file in the repo (CWE-829).

       The work tree is checked FIRST and is the authoritative boundary,
       because ``_PROJECT_ROOT`` is attacker-influenceable:
       :func:`_resolve_project_root` stops at the nearest ancestor
       holding a plugin directory, so a PR that adds one in a
       subdirectory relocates it and makes a wholly PR-controlled root
       look disjoint. ``git rev-parse --show-toplevel`` cannot be moved
       that way. ``_PROJECT_ROOT`` is still checked as well, because in
       the installed case it can resolve somewhere the work tree does
       not cover.

       Both bypasses were found by Copilot review on PR #5329, in
       consecutive rounds, the second defeating the fix for the first.
    4. The **resolved** config is inside the resolved root. Resolution
       happens before containment, so a symlink planted in the install
       directory that points back into the checked-out PR tree lands
       outside the root and is refused (CWE-59). Only a link whose
       target is also install-controlled survives.

    Not widened by this function: the command boundary.
    :func:`_enforce_command_trust` still verifies every work-tree file
    the criteria name, so an install-trusted config cannot execute a
    PR-rewritten verifier script.

    Residual, recorded rather than claimed closed: an actor who can
    already edit the workflow that invokes this gate can both set these
    variables and write the directory they name. That actor can run
    arbitrary commands in the same workflow, so this is a strictly
    smaller capability than they already hold, and it is not a boundary
    this gate can close.
    """
    project_root = _resolve_or_none(_PROJECT_ROOT)
    if project_root is None:
        # Fail closed. Condition 3 compares against this tree, and a
        # boundary that cannot be resolved cannot be compared against.
        return None
    candidate = _absolute_config_candidate(config_arg)
    # Resolved lazily, on first use, and at most once. Only a DECLARED root
    # can install-trust anything, so a run with neither variable set (the
    # overwhelmingly common case, and every caller that predates issue
    # #5112) must not pay a subprocess call or perturb a test's git mocks.
    # A failed probe raises WorkTreeUnavailableError out of this function rather
    # than degrading to "no install trust"; see that class for why exit 3.
    # Since the probe now returns a Path or raises, "still None" means
    # "not yet resolved", so no separate resolved-flag is needed and the
    # type narrows without an assert.
    work_tree: Path | None = None

    for root in _host_declared_roots():
        # Condition 3a: the root must be the plugin that ships THIS file.
        # A host variable names a plugin root; it does not promise the root
        # is ours. See _DISPATCHER_PATH for the reproduction and for this
        # repository's own record that the variable can name a foreign
        # context-mode plugin.
        if not _is_within(_DISPATCHER_PATH, root):
            continue
        # Condition 3b: the declared root and the project tree must be
        # DISJOINT, checked in BOTH directions.
        #
        # Testing only "root is not below the project" leaves the
        # ancestor direction open, and that direction is the whole
        # bypass: with the project at $HOME/repo and
        # CLAUDE_PLUGIN_ROOT=$HOME, the root is not below the project
        # (so a one-way test passes it) while every PR-controlled file
        # in the repo IS inside the root, so condition 4 passes too. A
        # config the checked-out PR wrote would then be install-trusted
        # and skip byte-identity verification entirely (CWE-829).
        # Reproduced on this branch before the fix: declared root
        # /home/user install-trusted
        # /home/user/ai-agents/.claude/commands/pr-review-config.yaml.
        # Found by Copilot review on PR #5329.
        if work_tree is None:
            work_tree = _consumer_work_tree()
        # Disjoint from the real work tree FIRST: that is the authoritative
        # extent of PR-controlled content and the only one PR content
        # cannot relocate. _PROJECT_ROOT is then checked as well, because
        # in the installed case it may resolve somewhere the work-tree
        # check does not cover, and a root overlapping either is refused.
        if not _are_disjoint(root, work_tree):
            continue
        if not _are_disjoint(root, project_root):
            continue
        resolved_config = _resolve_or_none(candidate)
        if resolved_config is None:
            return None
        # Condition 4: resolution already followed any symlink, so a
        # link out of the install directory fails this containment.
        # resolved_config is RETURNED, not recomputed by the caller: it is
        # the exact path this containment approved (CWE-367).
        if _is_within(resolved_config, root):
            return InstallTrust(root, resolved_config, work_tree)
    return None


class ResolvedConfig(NamedTuple):
    """Outcome of resolving ``--config``.

    ``exit_code`` is set if and only if resolution FAILED, and it carries
    the code the process must exit with. Callers branch on it rather than
    on ``path is None``, because the two failure kinds exit differently:
    2 for a config problem (containment, symlink, unreadable) and 3 for an
    external one (:exc:`WorkTreeUnavailableError`). The earlier 3-tuple form
    could express only one of those, which is how a git-probe failure came
    to be reported as an unsafe path (Copilot review, PR #5329).
    """

    path: Path | None
    raw: bytes | None
    install: InstallTrust | None
    exit_code: int | None


def _resolve_and_read_config(config_arg: str) -> ResolvedConfig:
    """Validate the config path and read it exactly once.

    On success returns the path, the single read of its bytes, and the
    install-trusted root or ``None``, with ``exit_code`` unset. That one
    read is what gets trust-verified AND parsed, so there is no window for
    the file to change between the two (CWE-367).

    On failure prints to stderr and sets ``exit_code``: **2** when the path
    is unsafe (CWE-22 containment), reaches through a repo-local symlink
    (CWE-59), or is unreadable; **3** when the consumer's git work tree
    could not be established, which is external rather than a config fault.

    ``install_root`` is resolved HERE, once, and threaded to
    :func:`_enforce_config_trust` rather than recomputed there, so the root
    that decided containment is provably the root that decides trust.
    Recomputing invites the two to disagree if the environment changes
    between the calls.
    """
    try:
        install = _install_trusted_root(config_arg)
    except WorkTreeUnavailableError as exc:
        # Exit 3, never 2: see WorkTreeUnavailableError. Not overridable by
        # --approve-untrusted-config, matching TRUST_GIT_ERROR, because
        # there is no inspectable artifact for an approval to be based on.
        print(
            f"Refusing to evaluate install trust: {exc}. A plugin root is "
            f"declared, so the consumer work tree must be known to decide "
            f"whether that root lies outside it.",
            file=sys.stderr,
        )
        return ResolvedConfig(None, None, None, 3)

    if install is not None:
        # Do NOT route this through validate_safe_path with the install root
        # as the base. That helper builds its result as
        # (resolved_base / path).resolve(), which would make the
        # environment-declared root a component of the path READ rather
        # than only the boundary it is CHECKED against, and for a
        # relative --config would name a different file than the one
        # _install_trusted_root just approved. Containment against the
        # root is already established, on this exact resolved path, by
        # that function's condition 4, so reuse it.
        #
        # Keeping the root deny-only is also what stops an environment
        # variable from participating in constructing a path whose
        # contents become a criterion's argv.
        #
        # The symlink probe is skipped here rather than run: it is
        # bounded to the project root by _first_symlinked_component
        # ("if not _is_within(probe, root): continue"), so for an
        # out-of-tree config it inspects nothing and returns None. The
        # CWE-59 hazard it guards is a PR-CREATED link, and condition 4
        # already refuses any link that escapes the install root.
        #
        # Reused, never re-resolved. Calling .resolve() again here would
        # be a second resolution of the same argument, and a repo-controlled
        # symlink swapped between the two lands inside the root for the
        # DECISION and outside it for the READ, with verification still
        # skipped (CWE-367, Copilot review on PR #5329).
        config_path = install.config_path
    else:
        symlink = _symlinked_config_component(config_arg)
        if symlink is not None:
            print(
                f"Refusing config path with symlinked component {symlink}: "
                f"a repo-local symlink would redirect trust verification to "
                f"its target and surface that file in the approval diff.",
                file=sys.stderr,
            )
            return ResolvedConfig(None, None, None, 2)
        try:
            config_path = validate_safe_path(config_arg, _PROJECT_ROOT)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            # RuntimeError joins the pair because validate_safe_path calls
            # (resolved_base / path).resolve() unguarded, and resolve()
            # raises RuntimeError on a symlink loop under CPython 3.10 to
            # 3.12 (see _resolve_or_none). Caught HERE rather than in that
            # shared helper, which many other scripts call and which is out
            # of scope for this change; that broader fix is flagged on the
            # PR instead. Exit 2: a loop in --config is a bad config path,
            # the same class as the containment failures beside it.
            print(
                f"Refusing to load config from unsafe path {config_arg!r}: {exc}",
                file=sys.stderr,
            )
            return ResolvedConfig(None, None, None, 2)
    try:
        return ResolvedConfig(
            config_path,
            _read_config_bytes(config_path),
            install,
            None,
        )
    except ConfigError as exc:
        print(f"Failed to load config {config_path}: {exc}", file=sys.stderr)
        return ResolvedConfig(None, None, None, 2)


def _extract_criteria(config: dict[str, Any]) -> list[Any] | None:
    """Return the completion_criteria list, or None (with stderr) if invalid.

    Rejects anything other than a non-empty list. The previous inline
    ``if not criteria`` accepted a dict that is non-empty, which would
    silently iterate the dict's keys (CodeRabbit review feedback).
    """
    criteria = config.get("completion_criteria")
    if not isinstance(criteria, list):
        print(
            f"completion_criteria must be a list, got "
            f"{type(criteria).__name__}",
            file=sys.stderr,
        )
        return None
    if not criteria:
        print("No completion_criteria in config", file=sys.stderr)
        return None
    return criteria


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.pull_request <= 0:
        print("Pull request number must be positive.", file=sys.stderr)
        return 2

    resolved = _resolve_and_read_config(args.config)
    if resolved.path is None or resolved.raw is None:
        # One branch, not two: testing path/raw narrows the types AND
        # detects failure, since exit_code is set on exactly the paths
        # that leave them None. The conditional expression is the
        # unreachable-default; `or 2` would be the falsy-override bug
        # python.md rejects, even though 0 never occurs here.
        return 2 if resolved.exit_code is None else resolved.exit_code
    config_path, raw_config = resolved.path, resolved.raw
    install = resolved.install

    # CWE-829 trust boundary: no criterion command runs unless the
    # working-tree config is byte-identical to the trusted-ref copy, a
    # human has explicitly approved the divergence, or the config came
    # from an install-trusted origin the consumer repository cannot
    # write (issue #5112). The command boundary below is NOT widened by
    # the third case: an install-trusted config still cannot execute a
    # PR-rewritten verifier script.
    trust, halt_code = _enforce_config_trust(
        config_path,
        args.trust_anchor_ref,
        args.approve_untrusted_config,
        raw_config,
        install,
    )
    if halt_code is not None:
        return halt_code

    try:
        config = _load_config_bytes(raw_config, config_path)
    except ConfigError as exc:
        print(f"Failed to load config {config_path}: {exc}", file=sys.stderr)
        return 2

    criteria = _extract_criteria(config)
    if criteria is None:
        return 2

    # CWE-829/CWE-494 second boundary: the config is trusted, but the
    # FILES its commands name live in the same checked-out PR tree.
    # Verify each work-tree file the argv resolves to before any command
    # runs, so a PR that leaves the config untouched and rewrites a
    # verifier script cannot reach execution.
    try:
        command_trust, halt_code = _enforce_command_trust(
            criteria,
            args.pull_request,
            args.trust_anchor_ref,
            args.approve_untrusted_config,
        )
    except ConfigError as exc:
        print(f"Config error in completion_criteria: {exc}", file=sys.stderr)
        return 2
    if halt_code is not None:
        return halt_code

    rows: list[dict[str, Any]] = []
    try:
        for criterion in criteria:
            rows.append(_evaluate_criterion(criterion, args.pull_request))
    except ConfigError as exc:
        # Schema bug in a criterion: exit 2 per ADR-035, do not pretend
        # the gate ran. Distinguishes a malformed config from a verifier
        # legitimately reporting failure.
        print(f"Config error in completion_criteria: {exc}", file=sys.stderr)
        return 2

    payload = {
        "pull_request": args.pull_request,
        "all_passed": all(r["passed"] for r in rows),
        "config_trust": {
            "status": trust.status,
            "trusted_ref": args.trust_anchor_ref,
            "approved": args.approve_untrusted_config,
        },
        "command_trust": {
            "status": command_trust.status,
            "trusted_ref": args.trust_anchor_ref,
            "approved": args.approve_untrusted_config,
            "checked_files": command_trust.checked_files,
            "untrusted_files": command_trust.untrusted_files,
            "skipped_external_files": command_trust.skipped_external_files,
            "skipped_untracked_files": command_trust.skipped_untracked_files,
        },
        "criteria": rows,
    }

    if not _try_write_evidence(args.evidence_path, payload):
        return 2

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_table(rows)

    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
