# Orchestrator Anti-Patterns

Loaded by the `orchestrator` agent when it reviews a routing plan for mistakes. The agent body keeps a one-line summary of each.

| Avoid | Why | Instead |
|-------|-----|---------|
| Pasting a skill's full text into a delegation prompt | Spends the subagent's window on text it can load itself; the paste is the pollution | Name the skill and let the subagent load it |
| Relaying a worker's "done" without checking the artifact | The report states intent, not the actual change; a false "done" ships as success | Inspect the diff, created file, or command output before synthesizing |
| Bounded tier on open-ended work | Review cost can exceed the token savings | Route bounded work down; normal work to the specified tier |
| Judgment tier for bounded disposable work | Spends expensive review capacity on cheap work | Use the bounded tier with a verifier |
| Treating more effort as better | Adds latency and tokens without raising acceptance | Start at the task-shape effort; validate any raise |
| Cheap model at high effort | Costs more without supplying missing judgment | Match effort to task shape; escalate on failed acceptance |
| Same-family self-verification | Correlated blind spots make it a weak check | Cross-check with a different model family |
| Serial when a human is blocked on the result | Wastes wall clock a human is paying for | Parallelize independent routes |
| Mutating repo-wide git commands during concurrent writes | Stash, reset, checkout, and clean can capture or overwrite sibling changes | Isolate writing workers, or run those commands after concurrent writes finish |
| Orchestrator implementing itself | Coordination and acceptance become one closed loop | Delegate to the registered worker and verify its delta |
