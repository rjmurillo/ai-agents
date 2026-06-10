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
# Idempotent: SessionStart fires every session, so guard on PYENV_ROOT being
# already exported in $CLAUDE_ENV_FILE to avoid appending duplicate lines.
if [ -n "${CLAUDE_ENV_FILE:-}" ] \
   && ! grep -q '^export PYENV_ROOT=' "$CLAUDE_ENV_FILE" 2>/dev/null; then
  {
    echo "export PATH=\"$repo_root/.venv/bin:\$HOME/.local/bin:\$HOME/.cargo/bin:\$HOME/.pyenv/shims:\$HOME/.pyenv/bin:\$PATH\""
    echo 'export PYENV_ROOT="$HOME/.pyenv"'
  } >> "$CLAUDE_ENV_FILE"
fi
