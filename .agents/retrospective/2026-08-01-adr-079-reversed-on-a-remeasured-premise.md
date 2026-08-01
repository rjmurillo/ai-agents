# An owner decision stood for three weeks on a string comparison that never gated anything

Issue #4080. Branch `fix/4080-omit-plugin-version`. ADR-079 superseded by ADR-092.

## What happened

Twenty-two of thirty open pull requests were conflicting. For fourteen of them the entire conflict surface was two files, and inside those files a single line: `"version"` in the packaged plugin manifests. Measured with `git merge-tree --write-tree --name-only origin/main <head>`, which resolves the question without mutating a branch.

The gate that requires that line to change on every plugin-source PR is doing what it was designed to do. Two PRs that touch entirely disjoint files still both rewrite the same line from the same base, so git conflicts by construction. The conflict is not a symptom of anything going wrong. It is the mechanism working as specified.

## The part worth recording

ADR-079 decided in July to keep the hand bump and reject every automation that would move it. That decision was not careless. It ran the six-agent debate, it reached 6/6, and the owner confirmed it on the #2855 thread. Its decisive objection was sound and remains sound: a post-merge stamp leaves `main` carrying changed content under an unchanged version until the follow-up lands.

It also rested on an empirical claim:

> Copilot CLI plugin freshness is a version-string inequality (`!=`), not SemVer ordering (`app.js` v1.0.69-0). A distinct version is mandatory or installs never re-sync.

The `!=` is really there. It is not a freshness gate. Across four shipped bundles, `updateAll()` iterates the installed plugins and calls `updatePlugin(spec)` unconditionally, and every occurrence of `previousVersion !== newVersion` resolves to either a display string, `(v1 -> v2)` versus `(v2, already at latest)`, or a telemetry property named `version_changed`. Cache invalidation keys off `skillsCacheDirty` returned by the update operation. The version never decides anything.

Four consecutive builds behave identically, which rules out the comfortable reading that the vendor changed something underneath us. The original inspection found a string comparison involving two version values and concluded it was the freshness check. It was the sentence that tells the user what just happened.

## Why the correction took three weeks to surface

Nothing was hiding. The bundle was on disk the whole time and the grep takes seconds. What was missing was a reason to look again, and the cost signal that would have supplied one was being paid in small change: fifteen minutes here, a rebump there, spread across many sessions and many authors. ADR-079 even wrote the price down, "concurrent same-line PRs rebump O(K) worst case, accepted", and #3875 later measured that a third of merges touch plugin source.

The bill only became legible when twenty-two PRs were blocked at once and the conflict surface could be measured in one command. A cost that arrives as a per-PR tax does not trigger a re-examination of the premise that justified it. A cost that arrives as a queue does.

## The mistake I made inside this session

I proposed a GitHub merge queue as one of the options, and labelled it unverified. The owner selected it. It does not work: a merge queue rebases each entry onto the accumulated queue head and ejects any entry that conflicts, and every one of these PRs conflicts pairwise with every other by construction, so all of them would be ejected. I verified that before implementing rather than after, and said so.

That ordering is the only reason it cost a message instead of a day. The option should have been verified before it was offered, not before it was built. Presenting an unverified option inside a decision brief puts the burden of the check on the person least able to run it.

There was a second, smaller version of the same error. Assigning each PR a distinct version slot did make all of them mergeable, and PR #4077 then merged cleanly and advanced the base exactly as predicted. It looked like the fix. Merging it immediately re-conflicted the next four green PRs. The slot scheme fixes the gate comparison, which is what the gate checks, and does nothing about the textual conflict, which is what actually blocks the merge. Two different failures wearing one error message.

## What the fix is, and why it escapes the objection that killed the alternatives

Delete the field. Claude Code documents a resolution order for the freshness key, and step three is the git commit SHA for exactly the source shapes this repository uses. Both marketplace manifests already omit a per-plugin version, so deletion lands on the SHA case, and freshness becomes per-commit rather than per-hand-bump. That is strictly finer than what the counter provided.

ADR-079's objection does not reach this. It applies to a post-merge stamp, and there is no stamp. Nothing writes a version at any point, so there is no window in which `main` is torn. The choice looked like zero-tear against zero-conflict, and that trade was real, but only while the version stayed committed.

The sharpest detail: omitting the field was never one of the options ADR-079 weighed. The list was merge-time bump, merge queue, pre-PR re-bump, git-height, content-hash, and relaxing the gate to `>=`. All six keep a committed version and therefore keep the conflicting write. Given the set it considered, ADR-079's conclusion follows. The set was incomplete, and the thing that completes it is a paragraph of vendor documentation nobody had read against this problem.

## What to carry forward

A decision that rests on an observed behavior should record the observation in a form the next reader can re-run, not just the conclusion drawn from it. ADR-079 cited `app.js v1.0.69-0` and stated what it concluded. Had it pasted the surrounding expression, the next reader would have seen a template literal and asked the question three weeks earlier.

And when a gate's cost is paid per-PR, nobody experiences the total. Worth watching for the shape: an accepted O(K) tax with an unmeasured K is a decision deferred, not a decision made.

## Not verified

Bundle 1.0.69-0, the one ADR-079 cited, was not available for inspection; four later consecutive builds were. `pluginOperationsUpdatePlugin` is a native binding and only the JavaScript layer was readable, so what is established is that the JavaScript layer does not gate on the version.
