---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-14685-pr-autofix-4888.json
qaCommit: 55dbc844fb973b4b43fe3a02852c44c9ca40d9c7
---

# PR 4888 copilot marketplace sha pin

## Result

PASS. `.github/copilot/settings.json` is the only non-`.agents/` file this PR
touches. The fix adds a `sha` field to each of the five
`extraKnownMarketplaces` entries, pinning every source to the commit that was
current on each repo's default branch at review time. This resolves both open
review threads (CWE-494, download of code without integrity check) without
changing any other behavior of the file.

## Evidence

- `python3 -m json.tool .github/copilot/settings.json` parses without error
  (syntax check; ran in the PR worktree at commit
  `55dbc844fb973b4b43fe3a02852c44c9ca40d9c7`).
- `grep -rn "\.github/copilot/settings" tests/ scripts/` in the PR worktree
  returns no matches: no repository test or CI validator reads this file, so
  there is no existing suite to run against it.
- Confirmed the fix contract against two sources this session, not from
  training-data recall:
  - Upstream: `raw.githubusercontent.com/github/copilot-cli/main/changelog.md`
    (fetched live), 1.0.8x release notes: "Pin plugins to an exact commit SHA
    using the `sha` field in plugin source configuration."
  - In-repo: `.agents/security/ADR-045-framework-extraction-security-review.md`,
    which already records this exact CWE-494 finding against
    `extraKnownMarketplaces` and prescribes the same `sha` field remediation.
- Each pinned SHA was read live via `gh api repos/{owner}/{repo}/commits/main`
  for `JuliusBrussee/caveman`, `DietrichGebert/ponytail`, `rjmurillo/ai-agents`,
  `MattKotsenas/agent-plugins`, and `Virag-Koradiya/graybeard` on 2026-08-11,
  and each `sha` value in the diff matches the value returned by that call.
- No other file in the PR diff changes behavior this QA report needs to
  re-verify: `git show --stat 55dbc844fb973b4b43fe3a02852c44c9ca40d9c7` shows
  exactly one file changed, `.github/copilot/settings.json` (10 insertions, 5
  deletions).

## Stricter/looser/different than canonical

The upstream `copilot-cli` changelog documents only the `sha` field as
required for pinning; it does not additionally require a `ref` field. This fix
adds only `sha`, matching the narrower upstream contract rather than the
`ref` + `sha` pattern shown in `.agents/analysis/claude-code-plugin-marketplaces.md`,
which documents Claude Code's (a different product's) marketplace schema. Both
`repo` values are unchanged; only `sha` was added.

## Scope note

This PASS verdict covers the JSON-configuration change only. It does not
re-validate unrelated repository behavior (CI infrastructure, test suite,
other PRs' changes) merged into this branch via the required `main` sync
merge commit `b88b543124`; that content already passed its own review and CI
on `main` before this PR merged it in.
