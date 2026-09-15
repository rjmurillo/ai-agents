# Decision Procedure

Migrated from `.claude/rules/builder-ethos.md` (epic #5456, M4). Walk it before Phase 1 for any non-trivial plan.

For any non-trivial task, walk this list in order:

1. **Has the user constrained scope?** If yes, that constraint wins (User Sovereignty). Apply it, state any trade-off once, and proceed. Skip the remaining steps that conflict with it.
2. **Search.** Layer 1 (this codebase, runtime built-ins), then Layer 2 (current docs, recent ecosystem), then Layer 3 (first principles applied to the specific constraint). Stop searching when you have enough to decide; do not stall in Layer 1 if Layer 3 reasoning already gives you the answer.
3. **Classify scope.** Lake or ocean? Use the threshold heuristic in `builder-ethos.md`, Boil the Lake. If lake, continue. If ocean, flag and stop.
4. **Build the complete lake.** Tests, edge cases, error paths, documentation. If it exceeds one response, state the plan and execute in confirmed parts.
5. **Present and ask** when ambiguity is high-stakes (Confusion Protocol in `writing-style-and-confusion-protocol.md`, beside this file). Otherwise act minimally and flag what you skipped or assumed.
6. **Stop at terminal.** Once every deliverable satisfies the frozen contract and no blocker remains (`builder-ethos.md`, Task Completion Contract), stop; an optional finding here does not restart step 4.

Step 1 can short-circuit any of the others. That is intentional: the user's stated decision is the precedence-stack top.
