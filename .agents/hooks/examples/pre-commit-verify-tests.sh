#!/usr/bin/env bash
# Pre-commit hook: block a commit if the project test command fails.
#
# Harness-agnostic reference implementation for the ai-agents hook
# contract (see .agents/hooks/README.md). Uses the `exit 2` convention:
#   0 = allow the commit
#   2 = block the commit
#
# This script reads a JSON hook payload from stdin (matching Claude Code
# and Copilot CLI conventions) but tolerates missing input so it can also
# run under git's native pre-commit or any other harness.
#
# Environment overrides:
#   AI_AGENTS_TEST_CMD       Test command to run (default: autodetected)
#   AI_AGENTS_SKIP_TESTS     If "1", skip the hook with a warning
#
# Exit codes: 0 allow, 2 block, anything else fails open.

set -u
IFS=$'\n\t'

log_info()  { printf '[pre-commit-verify-tests] %s\n' "$*" >&2; }
log_block() { printf '[pre-commit-verify-tests] BLOCK: %s\n' "$*" >&2; }

if [[ "${AI_AGENTS_SKIP_TESTS:-0}" == "1" ]]; then
  log_info "AI_AGENTS_SKIP_TESTS=1 set; skipping."
  exit 0
fi

# Drain stdin if a harness provided a payload. We do not parse it here;
# the contract only requires that we honor exit 0/2.
if [[ ! -t 0 ]]; then
  cat >/dev/null || true
fi

# Pick a test command. Callers should prefer an explicit override.
cmd="${AI_AGENTS_TEST_CMD:-}"
if [[ -z "${cmd}" ]]; then
  if   [[ -f "pytest.ini" || -f "pyproject.toml" ]] && command -v pytest >/dev/null 2>&1; then
    cmd="pytest -q"
  elif [[ -f "package.json" ]] && command -v npm >/dev/null 2>&1; then
    cmd="npm test --silent"
  elif [[ -f "Cargo.toml" ]] && command -v cargo >/dev/null 2>&1; then
    cmd="cargo test --quiet"
  else
    log_info "No test command autodetected; fail-open."
    exit 0
  fi
fi

log_info "Running: ${cmd}"

# shellcheck disable=SC2086
if ${cmd}; then
  log_info "Tests passed. Allowing commit."
  exit 0
fi

log_block "Tests failed. Commit denied. Override with AI_AGENTS_SKIP_TESTS=1 only if you understand the risk."
exit 2
