---
paths: ["**"]
priority: critical
---

# Universal Rules

These rules apply to every change in the active host repository.

## MUST

1. **Branch discipline**. MUST NOT push or commit directly to `main` or `master`. Create a feature branch first.
2. **Work item linkage**. When the host workflow uses a tracked work item, every change review MUST reference it with the host's supported closing or non-closing syntax.
3. **Verify closing claims against the diff before merging.** Tie each closing claim to a named hunk. Use the host's non-closing reference syntax when the diff does not support closure. Missing closing keywords are not automatically defects. Read the body before adding a closing keyword to another author's change. Post-merge body edits do not change merge-time automation. Close orphaned work items with a comment citing the merge commit.
4. **Verify a red remote check with equivalent evidence, or report it unreproduced.** MUST NOT claim a red remote check is cleared by a local run unless the checker, ruleset, flags, and version are demonstrably identical. State the command and why it is the same check; if you cannot, say the check is red and you could not reproduce it. A different tool produces evidence about a different check, and calling that "resolved" tells the reader to disregard a live finding.
5. **Conventional commits**. Commit messages MUST follow `<type>(<scope>): <desc>` and include a `Co-Authored-By:` trailer when authored with an AI agent.
6. **No secrets**. MUST NOT commit credentials, tokens, or API keys. Secrets live in environment variables or the secrets manager.
7. **Pin automation dependencies**. New automation action references MUST pin to immutable revisions when the host supports them, never floating tags.
8. **Session continuity**. Long-running work MUST preserve its current state in
   the host workflow's durable handoff surface. Optional memory services are
   retrieval aids, not the only record of required work.
9. **Git identity cannot prove a human acted.**

## SHOULD

1. **Retrieval-led reasoning**. SHOULD read the host project's constraint and architecture guidance when those documents exist, not rely on pre-training.
2. **Capability-first**. SHOULD prefer an existing host capability over inline shell commands when one exists.
3. **Host conventions for scripts**. SHOULD use the project's documented language and tooling conventions for new scripts. MUST NOT create a new shell script when the project provides a supported alternative.
4. **Minimal diff**. SHOULD NOT introduce unrelated refactors in a change. Keep the blast radius small.
5. **Atomic commits (advisory)**. Keep each commit to one logical, reviewable change. Follow host guidance for file-count limits when it exists.

## MUST NOT

1. MUST NOT force-push shared branches.
2. MUST NOT skip hooks, signing, or required validation gates. Do not change
   the host's bypass settings to avoid a failed check. When a hook blocks you
   for a reason unrelated to your diff, hand off the branch with the measured
   reason instead of bypassing.
3. MUST NOT put business logic in declarative workflow files when a checked-in program can own it.
4. MUST NOT use em-dashes (U+2014) or en-dashes (U+2013) in any authored text:
   markdown prose, code comments, agent prompts, commit messages, change
   descriptions, rule files, retrospectives, ADRs, or session logs. Use
   commas, periods, colons, parentheses, hyphens, or restructure the sentence.
   Automated reviewers may flag every occurrence. Keep generated mirrors
   identical; do not regress one distribution while fixing another.
   **Carve-out**: test fixtures may contain prohibited bytes when the host's
   validator explicitly excludes them because the test needs those bytes.
   **Quotations**: the ban still applies inside external quotes. If a quoted
   span or title has a prohibited dash, do not rewrite it. End the quote before
   it, use `[...]`, or split the quote and explain the dash's job in your prose.
5. MUST NOT add auto-generated headers, generation timestamps, or "do not edit"
   comments to any file (agent prompts, documentation, code, template outputs).
   Generated output must be indistinguishable from hand-written content:
   metadata headers waste tokens and hide the output's intended content. If a
   script grows a helper that emits such headers, delete the helper instead of
   calling it.
6. Worktrees MUST remain available for the duration of the handoff and follow
   the host's path rules.
7. MUST NOT rely on an optional memory service alone to persist a convention
   that other harnesses or contributors must obey. Optional memory services
   are retrieval complements, not the cross-harness binding.
8. MUST NOT cite an operator preference as a repository rule. State the durable
   source or state the advice without project attribution.
9. MUST NOT assert an absence from a single probe. This is the mirror of item 8
   and is worse, because an absence is unfalsifiable by later reading: a cited
   presence claim gets checked the next time someone opens the file, while an
   absence claim has no such automatic trigger. Before writing that no script,
   validator, rule, or caller exists, search the active host checkout and cite
   the search, or narrow the claim to the scope actually searched.

10. MUST NOT mutate a host-owned memory or handoff store from a linked worktree
    when it resolves to another checkout. Route the write through the owning
    checkout or return the content to the parent session.

11. MUST NOT fabricate tool results, command flags, facts, mutable state, or
    artifact fields. If an authoritative source fails, preserve the error
    context and report the result as unknown or unconfirmed until an
    authoritative observation confirms it. A missing observation is not
    success.

## Recovery and truthfulness

When an operation or retrieval fails, classify the observed result before
choosing the next action.

1. A transient failure permits a bounded retry. Record the observed result.
2. A documented alternate authoritative path may be tried after the primary
   path is ruled out.
3. An authoritative refusal is terminal for that strategy. Do not repeat the
   equivalent call or invent a flag, force option, or undocumented path.
4. An unavailable required source produces an unknown or unavailable result.
   Missing evidence is not success.
5. Read and validate a current schema or example before creating a
   schema-governed artifact. If the shape is unavailable, stop without
   fabricating fields.

## Evidence and retrospective claims

Separate observed facts, inferences, and unknowns in reports and retrospectives.
Use raw execution evidence when making claims about causes, friction, or agent
performance. Apply the same evidence bar to self-blame and external blame.
Persist a durable learning only through a host-approved surface after the
evidence supports it.

## Autonomous execution boundaries

Autonomous execution keeps the normal validation and review gates. Do not waive
tests, security review, or substantive responses to review findings to reach a
merge faster. After three failed attempts on the same blocker, stop repeating
the strategy and report the attempts with evidence. A user-supplied patch is a
signal to verify understanding before continuing. Record discoveries outside
the task contract and defer them unless the user authorizes scope expansion.

## Choosing a persistence surface

When you learn a durable fact, convention, or decision procedure that future
sessions must honor, choose the persistence surface by who must obey it and
across which harnesses. A convention that lives in only one harness's memory
is invisible to the other two harnesses.

1. **Ephemeral, this-task-only**: do not persist as a rule. Record unfinished issue state in the per-issue handoff.
2. **Retrieval aid, non-binding**: an optional memory or note store. Use it for
   useful context, never as the binding for a convention other harnesses must
   follow.
3. **Durable convention that binds every contributor and every harness**: the
   host's always-on rule surface. This is the canonical surface.

Once you know which tree you are writing to, follow the host's documented
generation and indexing mechanics.

Historical evidence for this placement contract includes these source-repository
records. Treat them as citations, not local paths or commands to run:

```text
- `parallel/parallel-001-worktree-isolation.md`
- `scripts/memory/update_memory_index_tokens.py`
- `78e808238`, corrected in `9cd7097f1`
```

## References

- The host project's contributor policy. Boundaries and standards.
- The host project's architecture guidance. Canonical design constraints.
