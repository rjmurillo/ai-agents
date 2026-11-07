# Merge-check exit codes: `test_pr_merged.py`

`test_pr_merged.py` now exits **0** on any successful query
and reports merge state in the JSON `merged` field. This makes the script
behave like every other shell-friendly probe: exit 0 means "I answered your
question". Branch on the JSON, not the exit code.

Earlier history: the script used to exit **100** when the PR was merged
(Skill-PR-Review-007). Treating 100 as a failure caused wasted polling loops
on several PRs, and made successful merge verification look
failed on another.

When invoking from autofix code:

```bash
PR_NUMBER="123"
resolve_pr_scripts_dir() {
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  for root in \
    "${COPILOT_PLUGIN_ROOT:-}" \
    "${CLAUDE_PLUGIN_ROOT:-}" \
    "$repo_root/.claude" \
    "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit" \
    "${HOME:-}/.copilot/installed-plugins"/*/project-toolkit \
    "${HOME:-}/.claude/plugins/cache"/*/project-toolkit; do
    if [ -n "$root" ] && [ -d "$root/skills/github/scripts/pr" ]; then
      printf '%s\n' "$root/skills/github/scripts/pr"
      return 0
    fi
  done
  printf '%s\n' ".claude/skills/github/scripts/pr"
}
SCRIPTS_DIR="$(resolve_pr_scripts_dir)"
python3 "$SCRIPTS_DIR/test_pr_merged.py" --pull-request "$PR_NUMBER" | jq -e '.merged == true'
```

To restore the legacy skip-review sentinel (only for callers that already
encoded "100 = merged"):

```bash
PR_NUMBER="123"
resolve_pr_scripts_dir() {
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  for root in \
    "${COPILOT_PLUGIN_ROOT:-}" \
    "${CLAUDE_PLUGIN_ROOT:-}" \
    "$repo_root/.claude" \
    "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit" \
    "${HOME:-}/.copilot/installed-plugins"/*/project-toolkit \
    "${HOME:-}/.claude/plugins/cache"/*/project-toolkit; do
    if [ -n "$root" ] && [ -d "$root/skills/github/scripts/pr" ]; then
      printf '%s\n' "$root/skills/github/scripts/pr"
      return 0
    fi
  done
  printf '%s\n' ".claude/skills/github/scripts/pr"
}
SCRIPTS_DIR="$(resolve_pr_scripts_dir)"
python3 "$SCRIPTS_DIR/test_pr_merged.py" --pull-request "$PR_NUMBER" --exit-100-on-merged
```

The legacy `--exit-zero-on-merged` flag still parses as a no-op
for backward compatibility.
