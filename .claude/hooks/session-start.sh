#!/usr/bin/env bash
# Claude Code on the web: SessionStart hook.
#
# Delegates to scripts/bootstrap-vm.sh, the canonical container bootstrap
# script. Without this, Claude Code remote containers start with no project
# Python deps installed, no markdownlint-cli2, and git hooks unconfigured;
# every test/lint run diverges from CI behavior.
#
# Gated on $CLAUDE_CODE_REMOTE so a developer running `claude` against this
# repo on their own laptop does not get a system-wide bootstrap.
#
# bootstrap-vm.sh is idempotent (each tool is installed only if missing), so
# re-running on every session start is safe and cheap after the first run.

set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Declare this environment a remote container (Issue #5541). The ADR-104 rule 8
# reclamation bound reads AI_AGENTS_REMOTE_CONTAINER through
# _is_remote_container() in scripts/validation/run_workflow_local_test.py, and
# the filesystem probe there finds nothing on a runtime that writes no marker
# file. Claude Code sets this gate in its web container, the environment rule 8
# was measured against. Anyone who exports it locally gets the marker too.
#
# This runs before the bootstrap check so a missing bootstrap-vm.sh cannot skip
# it, and the write is non-fatal so an unwritable $CLAUDE_ENV_FILE cannot stop
# the bootstrap below. The guard reads the LAST line touching the variable:
# when it is not the exact export line (absent, a later `=0`, a later `unset`,
# or a multi-name statement), a new line is appended, because the last
# statement is the one sourcing leaves in effect.
# Accepted limit: a `readonly` or `declare -r` line makes the variable
# read-only, so the appended export fails when sourced ("readonly variable")
# and the earlier value stays. The append is still attempted; it cannot win.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  # End the file's last line first. Another SessionStart hook can leave it
  # without a trailing LF, and an append would then fuse onto that line:
  # `FOO=bar` becomes `FOO=barexport ...` and the marker never takes effect.
  # `$(tail -c1)` is empty only when the last byte is LF, so a non-empty
  # result means the last line is unterminated. Applies to every append below.
  if [ -s "$CLAUDE_ENV_FILE" ] && [ -n "$(tail -c1 "$CLAUDE_ENV_FILE" 2>/dev/null)" ]; then
    { echo >> "$CLAUDE_ENV_FILE"; } 2>/dev/null || true
  fi
  # Match every non-comment line that names the variable as a whole word: an
  # assignment (`=`, `+=`, or one operand of a multi-name `export FOO=1 NAME=0`),
  # or an `unset`, `export -n`, `declare`, `typeset`, or `readonly` line, even
  # when other names share the statement. Any such line can change the value
  # sourcing leaves in effect, so only the exact export line as the LAST match
  # skips the append. Read-only lines are matched but cannot be overridden
  # (see the accepted limit above). A name that merely shares the prefix is not a match.
  last_marker="$(grep -v '^[[:space:]]*#' "$CLAUDE_ENV_FILE" 2>/dev/null |
    grep -E '(^|[^[:alnum:]_])AI_AGENTS_REMOTE_CONTAINER([^[:alnum:]_]|$)' | tail -n 1 || true)"
  if [ "$last_marker" != 'export AI_AGENTS_REMOTE_CONTAINER=1' ]; then
    echo 'export AI_AGENTS_REMOTE_CONTAINER=1' >> "$CLAUDE_ENV_FILE" ||
      echo "[session-start] could not write AI_AGENTS_REMOTE_CONTAINER to CLAUDE_ENV_FILE" >&2
  fi
else
  echo "[session-start] CLAUDE_ENV_FILE is unset; AI_AGENTS_REMOTE_CONTAINER was not persisted" >&2
fi

# Resolve repo root from the script's own location so the hook is robust
# against $CLAUDE_PROJECT_DIR being unset, $PWD being something unexpected,
# or any environment-variable manipulation (CWE-22 defense).
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"

if [ ! -x "$repo_root/scripts/bootstrap-vm.sh" ]; then
  echo "[session-start] scripts/bootstrap-vm.sh not found or not executable; skipping" >&2
  exit 0
fi

cd "$repo_root"
# Run bootstrap-vm.sh as best-effort: capture its exit code and continue so a
# partial failure (e.g. a single tool install step erroring out) does not abort
# session start. Anything that did install successfully (uv, the pinned
# Python, project deps) remains available; failures are logged for the
# maintainer to diagnose later.
bootstrap_status=0
./scripts/bootstrap-vm.sh || bootstrap_status=$?
if [ "$bootstrap_status" -ne 0 ]; then
  echo "[session-start] bootstrap-vm.sh exited $bootstrap_status; continuing in degraded mode" >&2
fi

# Persist PATH for the agent loop so newly-installed tools (uv, the
# uv-managed python3, etc.) are reachable from subsequent Bash tool calls in
# the session.
#
# Order matters: the project venv's bin must come first so bare `python3`
# resolves to the synced .venv (the interpreter pinned in .python-version,
# with project deps installed by `uv sync`). $HOME/.local/bin follows so
# `uv` and the uv-managed default python3 (the no-venv fallback) resolve to
# the bootstrap-installed copies rather than older image-provided ones. The
# pyenv entries are kept for container images that still carry
# pyenv-provisioned interpreters; they sit last so they never shadow the
# uv-managed toolchain.
#
# Idempotent: SessionStart fires every session, so each line is guarded by
# its own marker. The PATH line is keyed on the venv bin dir (not on
# PYENV_ROOT): containers that ran an older version of this hook already
# have a PYENV_ROOT line in $CLAUDE_ENV_FILE, and keying the PATH append on
# it would skip the venv-first PATH on upgraded sessions.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  # Shell-escape repo_root before writing it into a file a later shell
  # sources: the checkout directory name is not trusted input (an
  # attacker who controls where the repo is cloned controls this string),
  # and writing it as literal shell source without escaping lets a quote,
  # newline, or command substitution in the path execute at source time
  # (CWE-78). `printf '%q'` produces a token safe to splice back into
  # unquoted shell source as-is; wrapping it in an ADDITIONAL pair of
  # double quotes would be wrong, since %q's backslash-escaping is meant
  # for an unquoted context, not for nesting inside one.
  repo_root_escaped=$(printf '%q' "$repo_root")
  if ! grep -qF "$repo_root_escaped/.venv/bin" "$CLAUDE_ENV_FILE" 2>/dev/null; then
    echo "export PATH=${repo_root_escaped}/.venv/bin:\$HOME/.local/bin:\$HOME/.cargo/bin:\$HOME/.pyenv/shims:\$HOME/.pyenv/bin:\$PATH" >> "$CLAUDE_ENV_FILE"
  fi
  if ! grep -q '^export PYENV_ROOT=' "$CLAUDE_ENV_FILE" 2>/dev/null; then
    echo 'export PYENV_ROOT="$HOME/.pyenv"' >> "$CLAUDE_ENV_FILE"
  fi
fi
