---
id: ADR-091
status: accepted
date: 2026-07-31
decision-makers: [rjmurillo]
supersedes: [ADR-079]
superseded-by: null
explainer: null
implemented: true
---

# ADR-091: Post-Merge Bot Owns Plugin Version and Count Baselines

## Status

Accepted (2026-07-31). Supersedes ADR-079 (Plugin Version Bump Stays at PR Time).

Requested by issue #4080. The issue measured that 14 of 22 conflicting open PRs conflicted on nothing but the `version` integer in the two parity manifests. Re-measurement on 2026-07-31 against `origin/main` at `372de0c34` shows the current count is **11 manifest-only conflicts** and **2 taste-baseline-only conflicts** out of 24 DIRTY PRs total (the set has moved since the issue was filed). Together these two conflict classes are blocking the merge of roughly 100 pending issue fixes. The serialization cost is now O(N^2): every merge re-conflicts the remaining N-1 PRs, and no author can compute the correct target version without inspecting all other open branches.

## Date

2026-07-31

## Context

### Measured conflict classes (2026-07-31, N=24 DIRTY)

| Class | Count | Conflicting file |
|-------|-------|-----------------|
| Manifest-only (version field) | 11 | `.claude/.claude-plugin/plugin.json` and `src/copilot-cli/.claude-plugin/plugin.json` |
| Taste-baseline-only | 2 | `scripts/ci/taste_count_baseline.txt` |
| Manifest + real content | 8 | plugin.json + other files |
| Real content only | 2 | other files only |
| Flagged DIRTY but no actual conflict | 1 | - |

Measurement command:
```
git merge-tree --write-tree --name-only origin/main <pr-head-sha>
```

### Consumer inventory (measured, not from memory)

**plugin.json consumers:**

1. **`build/scripts/validate_plugin_version_bump.py`**: reads `version` via
   `git show <ref>:path/to/plugin.json`. Enforces `version > base_ref_version`
   (strictly-greater SemVer). Triggered by `.github/workflows/validate-plugin-version-bump.yml`
   when PR touches `.claude/**`, `src/claude/**`, or `src/copilot-cli/**`.

2. **`build/scripts/check_plugin_manifest_parity.py`**: reads the working-tree copy.
   Checks that `.claude/.claude-plugin/plugin.json` and
   `src/copilot-cli/.claude-plugin/plugin.json` carry identical `version` values.
   `src/claude/.claude-plugin/plugin.json` is a separate `claude-agents` plugin on an
   independent version line; this gate does NOT cover it.

3. **GitHub Copilot CLI (v1.0.69-0, verified in shipped `app.js`)**: parses version as
   `s.version||"unknown"`. The update check is `previousVersion!==newVersion`
   (inequality, not ordering). A second check `l.version!==a[c]?.version` drives
   skill-reload and cache-clear. **An omitted or static version permanently prevents
   Copilot CLI from detecting updates.** No SHA fallback exists.

4. **Claude Code**: if `version` is omitted, resolves to the git commit SHA. Every
   commit is therefore a distinct version, so Claude Code users always receive fresh
   installs. Claude Code does NOT require a committed, changing version.

5. **`scripts/validation/run_plugin_version_bump_ci.py`**: CI entry point that invokes
   `validate_plugin_version_bump.py` after depth-normalizing the fetch.

6. **`scripts/validation/validate_plugin_version_bump.py`** and the npm publish path:
   read `packages/ai-agents-cli/package.json`, NOT `plugin.json`. Unaffected.

**taste/ruff baseline consumers:**

1. **`scripts/ci/taste_count_ratchet.py`** (and its shared base `scripts/ci/count_ratchet.py`):
   reads `scripts/ci/taste_count_baseline.txt` (currently `613`). The ratchet fails if
   `current_count > committed_baseline`. A PR that lowers the count MUST also lower
   the committed baseline via `--update`, causing the same git conflict as the version.

2. **`scripts/ci/ruff_count_ratchet.py`**: reads `scripts/ci/ruff_count_baseline.txt`
   (currently `331`). Same pattern. These two baseline-only conflicts are class 2 above.

### Why ADR-079's rejection is re-examined here

ADR-079 (2026-07-08) enumerated the post-merge bot alternative and rejected it with two primary arguments:

1. **Torn `main`**: the window between the content merge and the bot's bump commit leaves
   `main` carrying changed content under an unchanged version.
2. **New trust surface**: the bot requires a branch-protection carve-out for a
   self-committing workflow.

Both arguments remain technically valid. The decision changes because the cost model has
changed:

- At N=11 manifest-only conflicts growing as the fix queue drains, the O(N^2) rebump
  cost is no longer a "common but bounded" cost; it is blocking the entire fix queue.
- The torn window is 30-120 seconds (GitHub Actions queues a new workflow run within
  seconds of a push event). The Copilot CLI plugin-refresh cadence is hours. No user
  session has ever seen a torn version at install time, and the probability of collision
  in a 120-second window is negligible against hours of cache TTL.
- ADR-079 noted that the rejected merge-driver option "deserves a separate spike." That
  spike has now been run (verified in this investigation): GitHub's server-side merge
  ignores `.gitattributes` custom drivers, so `mergeable` still reports CONFLICTING
  regardless of any local driver. That option is closed.
- The parity gate (`check_plugin_manifest_parity.py`) continues to function identically
  regardless of who writes the version, as long as both manifests are always written
  together. The bot will write both atomically in one commit.

### The `git rev-list --count` shallow-clone hazard

One obvious approach for a "derived version" would use `git rev-list --count HEAD` as
the version number. That approach is **not used here**. Measured: `.github/workflows/pytest.yml`
runs `git fetch --depth=1`, and a depth-1 clone returns count=1. A version that reads 1
in CI and 5444 locally is a worse defect than the one being closed. Incrementing from the
existing SemVer patch number avoids the shallow-clone problem entirely.

## Decision

**Accept the post-merge auto-bump bot for `plugin.json` and the committed count baselines.**
PRs stop owning these scalar fields. A GitHub Actions workflow fires on push to `main`,
increments the patch version (or lowers the count baseline) atomically, and commits to `main`
with `[skip ci]` in the commit message.

Specific decisions:

1. **PRs MUST NOT include version bumps in `plugin.json`.** The PR-time gate is
   inverted: the workflow fails if the PR diff touches the `version` field in either
   parity manifest. PRs that do not touch plugin source files are unaffected (no diff
   touching plugin source, no gate to trigger).

2. **The post-merge bot owns both parity manifest versions.** After any push to `main`
   that changes content under `.claude/` or `src/copilot-cli/` (excluding `plugin.json`
   itself to avoid loops), the bot increments the patch version in both manifests and
   pushes the result. The commit message is
   `chore(plugins): auto-bump version to <new> [skip ci]`.

3. **`src/claude/.claude-plugin/plugin.json`** is a separate `claude-agents` plugin.
   It is NOT in the parity gate and is NOT touched by this ADR's bot. It retains its
   independent manual-bump workflow unchanged.

4. **The count baseline files are treated identically.** `taste_count_baseline.txt` and
   `ruff_count_baseline.txt` remain committed files, but PRs no longer own them. The
   post-merge bot updates the baseline to the current count if it has improved,
   committing in the same atomic run as the version bump where applicable. PRs that
   improve the taste/ruff count do not include a baseline edit; the PR passes the gate
   by having `count <= committed_baseline` at PR time (the committed value is from
   `main`, which is always >= the improved value on any improvement PR). The bot
   ratchets the baseline down after merge.

5. **Strict-greater enforcement is replaced by no-manual-bump enforcement.** The
   PR-time gate no longer checks `version > base_ref_version`. It checks that the PR
   diff does NOT include a version change in the two parity manifests. A PR that
   manually bumps the version fails the gate, directing the author to let the bot do it.
   The post-merge bot guarantees strict monotonicity by reading the current merged version
   and computing `current_patch + 1`.

6. **The parity gate is unchanged.** `check_plugin_manifest_parity.py` continues to
   verify that both parity manifests carry the same version. The bot writes both in the
   same commit, so parity is maintained.

7. **The `src/claude` version gate is unchanged.** `validate_plugin_version_bump.py`
   continues to enforce strict-greater bumps for `src/claude/.claude-plugin/plugin.json`
   when `src/claude/**` content changes.

### On the torn-`main` window

Between the content merge commit and the bot's bump commit, `main` carries changed
content under the pre-bump version. This window is accepted with the following
constraints:

- The bot runs as the first step of the `post-merge-version-bump` workflow triggered
  on `push` to `main`. Typical latency from push to workflow start is 5-30 seconds.
- Copilot CLI checks for plugin updates on a refresh cadence of hours, not seconds.
- The `[skip ci]` tag on the bot's commit prevents re-triggering the full test suite.
- If the workflow is delayed or fails, a re-run or manual trigger closes the window.
- A monitoring check may be added to alert if the bot's commit does not follow the
  content commit within 5 minutes.

This window is a known and accepted trade-off. It is not a safety or correctness risk
for Copilot CLI; it would cause one Copilot install to refresh to the pre-bump version
and then re-refresh on the next cadence cycle to the bumped version. That is harmless.

## Migration Plan

### Phase 1: deploy the bot (this ADR's implementation)

1. Add `.github/workflows/post-merge-version-bump.yml`.
2. Update `.github/workflows/validate-plugin-version-bump.yml` to fail if the PR diff
   includes a version change in either parity manifest (invert the gate for parity
   manifests; leave the `src/claude` gate as-is).
3. Update `build/scripts/validate_plugin_version_bump.py` to support the inverted gate.
4. Add `.github/workflows/post-merge-baseline-ratchet.yml` (or extend the version-bump
   workflow) to update `taste_count_baseline.txt` and `ruff_count_baseline.txt` after
   merges that improve the count.
5. Update `scripts/ci/taste_count_ratchet.py` and `scripts/ci/ruff_count_ratchet.py`
   to accept a new `--no-update-required` mode where `count < baseline` is a PASS with
   no `--update` action required; the bot will ratchet after merge.

### Phase 2: drain the existing queue

After the bot is deployed and verified on a real merge, open PRs that carry manual
version bumps will need to drop the bump. The PR-time gate will tell them. The tooling
note in `.github/instructions/plugin-version-bump.instructions.md` (issue #2873) must
be updated to say "do NOT bump the version; the bot does it after merge."

## Prior Art Investigation

- **NBGV (Nerdbank.GitVersioning)**: stamps version at build time, never checks it in.
  Not applicable here because there is no build boundary (hosts read raw HEAD).
- **Helm chart `Chart.yaml` version**: typically auto-bumped by CI on merge to release
  branch. The pattern is established; this ADR applies it here.
- **GitHub Actions `GITHUB_TOKEN`**: can push to protected branches when
  `contents: write` is granted at the workflow level, without a PAT, as long as the
  branch protection rule has "allow specified workflows" or the workflow has `write`
  permission explicitly. This is the mechanism used by the bot.

## Rationale

The three candidate directions from issue #4080:

| Direction | Outcome |
|-----------|---------|
| **1. Stop committing the version (post-merge bot)** | **CHOSEN.** Removes the conflict class. Torn-main window is acceptable at this scale. |
| **2. Merge queue** | Not sufficient alone: the strictly-greater gate fails when two queue entries set the same version (N+1). Serializes without removing the conflict. |
| **3. Custom merge driver** | GitHub server-side merge ignores `.gitattributes` drivers. `mergeable` still reports CONFLICTING. Closed. |

Direction 1 is chosen because it removes the class, not just eases it.

## Consequences

### Positive

- Any two PRs touching disjoint plugin source files can land without either author
  editing a version field. This is the acceptance criterion in issue #4080.
- The O(N^2) rebump cost is gone. Each PR merges cleanly; the bot runs once per merge.
- `taste_count_baseline.txt` and `ruff_count_baseline.txt` conflicts are eliminated
  by the same post-merge pattern.

### Negative

- `main` has a torn-version window of approximately 30-120 seconds after each content
  merge. Accepted (see above).
- A new self-committing workflow requires `contents: write` permission on `main`.
  Scoped to the specific workflow and paths; no PAT required.
- The bot's commit itself may trigger other CI checks (mitigated by `[skip ci]`).
- PR authors who manually bump the version will see a new gate failure. The gate message
  directs them to remove the bump.

### Neutral

- Parity gate is unchanged.
- `src/claude` plugin versioning is unchanged.
- The existing `validate_plugin_version_bump.py` is updated, not replaced.
- Issue #2543 (merge-resolver auto-bump for version-only conflicts) and PR #2873
  (recovery-recipe instruction) are superseded for parity manifests and may be
  archived or updated to say "bot handles this."

## Acceptance Criteria

1. A PR that touches disjoint plugin source files (not `plugin.json`) can merge without
   its author editing any version or baseline field.
2. After that PR merges, the bot increments the version in both parity manifests within
   5 minutes and the parity gate passes on the merged state.
3. A PR that manually includes a version bump in a parity manifest fails the updated gate.
4. The mutation harness kills every mutant in the test suite for the updated gate.

## Related Decisions

- ADR-079 (superseded): Plugin Version Bump Stays at PR Time.
- ADR-006 (thin workflows, testable modules): the new workflow calls scripts; no logic
  lives in YAML.
- ADR-072 (JTBD plugin architecture): defines the packaged-plugin model.
- Issue #4080 (request), issue #2855 (original throughput report), issue #3875 (traffic
  measurement that updated ADR-079 cost model).

## References

- `build/scripts/validate_plugin_version_bump.py`
- `build/scripts/check_plugin_manifest_parity.py`
- `.github/workflows/validate-plugin-version-bump.yml`
- `scripts/ci/count_ratchet.py`, `scripts/ci/taste_count_ratchet.py`,
  `scripts/ci/ruff_count_ratchet.py`
- `scripts/ci/taste_count_baseline.txt`, `scripts/ci/ruff_count_baseline.txt`
- GitHub Actions `contents: write` permission docs.
