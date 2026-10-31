# Resolving the review-marker validator

`ship` pre-flight check 3 runs `validate_review_marker.py` from the `review`
skill. Resolving it takes a root walk rather than a fixed path, because the
script's location differs between this checkout, a Claude plugin cache, and a
Copilot CLI install.

Prefer `CLAUDE_SKILL_DIR` when the harness sets it. Otherwise walk the roots in
order and take the first that actually holds the directory.

```bash
if [ -n "${CLAUDE_SKILL_DIR:-}" ]; then
  REVIEW_MARKER_SCRIPT="$CLAUDE_SKILL_DIR/../review/scripts/validate_review_marker.py"
else
  resolve_review_scripts_dir() {
    repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    for root in \
      "${COPILOT_PLUGIN_ROOT:-}" \
      "${CLAUDE_PLUGIN_ROOT:-}" \
      "$repo_root/.claude" \
      "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit" \
      "${HOME:-}/.copilot/installed-plugins"/*/project-toolkit \
      "${HOME:-}/.claude/plugins/cache"/*/project-toolkit; do
      if [ -n "$root" ] && [ -d "$root/skills/review/scripts" ]; then
        printf '%s\n' "$root/skills/review/scripts"
        return 0
      fi
    done
    printf '%s\n' ".claude/skills/review/scripts"
  }
  REVIEW_SCRIPTS_DIR="$(resolve_review_scripts_dir)"
  REVIEW_MARKER_SCRIPT="$REVIEW_SCRIPTS_DIR/validate_review_marker.py"
fi
python3 "$REVIEW_MARKER_SCRIPT" --ref HEAD --repo-root "$(pwd)"
```

The in-repo rung is anchored on `git rev-parse --show-toplevel` rather than a
bare relative path, per the resolver-anchoring rule: a bare `.claude` rung only
resolves when the working directory happens to be the repository root, and from
a subdirectory it falls through to an installed-plugin copy that can be
arbitrarily old.

The default form, when nothing else resolves, is
`${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/review/scripts/validate_review_marker.py`.

## Exit codes

| Code | Meaning | What ship does |
|------|---------|----------------|
| 0 | HEAD is a review marker commit whose `Reviewed-By: /review@<axes> on <sha>` trailer binds the reviewed tip, its parent, and whose body holds the review report its `Review-Artifact` digest covers. HEAD may also be a clean merge of `origin/main` above such a marker | Check 3 PASSES |
| 1 | No marker, a stale marker, new code after review (a merge with conflict edits or an extra edit counts), an unknown or repeated axis name, or a missing or altered review report | Check 3 FAILS: run review, then re-run ship |
| 2 | Configuration error | Check 3 FAILS |

## Coverage

The marker proves only the axes its `Reviewed-By: /review@<axes>` trailer declares. The
validator PASS line prints them. `/review` is risk-selected, so a valid marker may name a
subset; deep review declares the full set. Risk-selected review is acceptable for shipping
without a blanket deep review.

- Report the declared axes. Never call the result a full review.
- An axis absent from the marker is `NOT RUN`. Keep it distinct from a passed axis.
- `/ship` requires no axis by default. To require one, add `--require-axis <axis>`
  (repeatable) to the validator command. Exit `1` with "required axis not declared" means
  the axis is not verified and check 3 FAILS. Re-run `/review` with that axis pinned.
- SHA binding, the `Review-Artifact` digest, unknown axes, and repeated axes fail as before.
