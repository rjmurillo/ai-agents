#!/usr/bin/env bash
# Claude Code on the web: SessionStart hook.
#
# Delegates to scripts/bootstrap-vm.sh, the canonical container bootstrap
# script. Without this, Claude Code remote containers start with no project
# Python deps installed, no markdownlint-cli2, and git hooks unconfigured —
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

repo_root="${CLAUDE_PROJECT_DIR:-$(pwd)}"

if [ ! -x "$repo_root/scripts/bootstrap-vm.sh" ]; then
  echo "[session-start] scripts/bootstrap-vm.sh not found or not executable; skipping" >&2
  exit 0
fi

cd "$repo_root"
./scripts/bootstrap-vm.sh

# Persist PATH for the agent loop so newly-installed tools (uv, pyenv, etc.)
# are reachable from subsequent Bash tool calls in the session.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo 'export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.pyenv/bin:$PATH"'
    echo 'export PYENV_ROOT="$HOME/.pyenv"'
  } >> "$CLAUDE_ENV_FILE"
fi
