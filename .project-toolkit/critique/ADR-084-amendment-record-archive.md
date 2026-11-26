# ADR-084 amendment record archive

This file holds two entries of the ADR-084 Amendment Record. They moved here
verbatim on 2026-11-25 from
`.project-toolkit/architecture/ADR-084-vendored-hook-roi-bar.md`. The move keeps
that record under the 500-line cap. The text below is unchanged. "This ADR" and
"this amendment" in it mean ADR-084 and the dated amendment. The debate that
reviewed the move is `.project-toolkit/critique/ADR-084-debate-log-4.md`.

## Amendment Record entries

**2026-08-18, rule 3, tool-use events only.** The original rule 3 treated
"the host cannot express this declaratively" as sufficient warrant for a
spawning hook. Two measured properties of the Copilot surface show that is too
weak for `PreToolUse` and `PostToolUse`.

Copilot's native matcher targets are tool names. For `preToolUse` and
`postToolUse` the target is `toolName`, per the hook reference recorded in
`.claude/skills/agent-harness-reference/references/official-hook-contracts.md`.
There is no argument-scoped form, so a Claude-side `Bash(git push*)` matcher
has no Copilot equivalent and degrades to bare `Bash`. The generated matcher
shim re-reads the payload and skips, after the interpreter has already started.

Copilot also registers one command per event, so the host matcher is the union
of every registered group's matcher. Measured on `origin/main` before the issue
#5154 retirements, `src/copilot-cli/hooks/hooks.json` carried
`"PreToolUse" -> "Bash|Agent|Task"` and `"PostToolUse" -> "Write|Edit"`. One
markdownlint guard scoped to `Bash(git push*)` therefore put bare `Bash` into
that union and cost a consumer a process spawn on every Bash call in the
session. A badly scoped tool-use hook does not only cost what it does; it taxes
every unrelated call that shares its event.

**The primary evidence is blast radius, not latency.** ADR-085 lines 428 to 431
record issue #5013: `push_pr_script_identity_guard` on a bare `Bash` matcher,
combined with the Copilot dispatcher's timed child-process deny (#4706), denied
127 unrelated Bash commands over more than 21 minutes before the owner contained
it. A wrong deny on a hot tool takes out unrelated work; that is the failure
mode rule 6 exists to price.

A third mechanism sets the ceiling above union widening.
`event_matcher_union` (`build/scripts/generate_dispatcher.py:556`) returns
`None` when ANY registered matcher fails to reduce to a known tool name, and its
docstring states the consequence: "emit no matcher; the dispatcher fires on
every call and filters in-process". One unreducible matcher, such as an MCP tool
name, therefore deletes the matcher for every hook on that event.

The latency figures are supporting evidence and are weaker than they look. The
owner's stated platform cost is 50 to 100 ms per spawn on Windows, worse on
a loaded machine. That figure is owner-recalled and is measured nowhere in this
repository. The one Windows figure on record is not the same measurement:
ADR-068 line 150 records a "HISTORICAL Windows cold start of about 246 ms for
`py -3 -u <shim>`", a cold start of the older per-shim launcher rather than a
warm per-spawn cost under the current dispatcher. Measured clean-path dispatcher
cost on Linux under Python 3.14.6, median of 3 to 5 runs (issue #5154): 102 ms
for a bare-`Bash` guard, 74 ms on `Write|Edit`, 71 ms on `Agent|Task`, 498 ms on
`Bash(git push*)`. Quote the platform and the measurement basis with any figure;
none of these are interchangeable. Two caveats the #5154 debate log records and
this ADR carries forward: the three retired figures are not reproducible from
the tree once their dispatch groups are deleted, and the 498 ms figure is not a
spawn cost at all. It is 4.9x the bare-`Bash` figure for a strictly narrower
matcher, so it measures the guard's own work (subprocess, git, markdownlint),
not interpreter start. An independent run on other Linux hardware measured the
surviving dispatcher at 132 ms against the 71 ms recorded here, a 1.9x spread on
one platform.

The amendment does not rest on the Windows figure. The Linux measurements and
the matcher-union mechanism above are sufficient on their own.

What the amendment does not change: rules 1, 2, 4, and 5; the security
carve-out; and rule 3's original reading for every event other than the two
tool-use events.

**2026-10-31, rule 2a and the rule 5 correction (accepted 2026-11-04).** REQ-048 asks for
a Stop hook that suggests `/retrospective` when a session shows heavy tool-side
friction. Rule 2 as written listed "retros" as internal, so any such hook was
barred, even one that only advises. The word was meant for this repository's
retro protocol, not for a consumer's own sessions. The hook that motivated the
word was the since-deleted `invoke_auto_retrospective.py`. It wrote skeleton files at Stop and
returned `decision: "block"`, which dirtied the tree and kept turns alive
(#3140). PR #3372 (issue #3349) deleted it in `b862e14e9`. Rule 2a draws the
line at that behavior. Writing, blocking, demanding, or instructing the agent
is enforcement. A fixed-text, counts-only, non-blocking line to the user about
their own session is not.

Why condition d names `Stop` alone (round 1, critic P0-1). An earlier draft
allowed any per-turn event. `UserPromptSubmit` and `SessionStart` output
enters model context, so a fixed line there could steer the agent and still
pass every other condition. Conditions d and f close that path together.

Evidence that the gap exists, measured 2026-10-31 (REQ-048 Q5): 8,305
Claude Code transcripts from 30 days held 550 errored tool results. 11
sessions had 10 or more errors plus repeated identical calls. The existing correction
nudge stayed silent on all 11. Scope: every transcript is from this
repository's own projects (`~/.claude/projects/*ai-agents*`), one operator,
and many errors come from this repository's validators. The same person labels
the REQ-048 held-out sample. The figures show the gap exists here. They show no
consumer demand, and this amendment does not claim any. REQ-048 AC-19 owns
the ship gate (amended 2026-11-03 under owner decision D19: cross-validation 12 of 16, 75 percent, Wilson lower bound 0.505) and REQ-048's Observability section owns the kill criterion.
Both are judged on the owner's own transcripts only, because the hook sends
no telemetry and consumer sessions cannot be seen. The default is calibrated
on one operator's corpus, and consumers' friction sources are unmeasured.

Alternatives considered (REQ-048 Q-1). Narrowing rule 2 alone was rejected:
the narrowed word draws no line, so a later hook could call any behavior
advisory. An exception alone was rejected: rule 2 would still list "retros"
and contradict it. Keeping the hook dogfood-only until consumer evidence
exists was rejected by the owner, who chose the vendored route on 2026-10-31
(REQ-048 D3). That decision, not consumer demand, is the reason on record.

Rollback: remove the hook's dispatch group and cut a release. If that
empties the vendored surface, the same PR deletes both rule 5 tests, as
`f79e70c01` did, and the restoration duty passes to the next vendored hook.
Rule 2a lapses under its sunset clause. Consumers keep the hook until they
upgrade the plugin, and its off switch covers that gap. Their marker directory (`ai-agents-reflect-nudge` under the
per-user state root) stays until they delete it.

Rule 6 is not engaged, since `Stop` is outside its four events. The Stop
output channel is undocumented on both harnesses, which is why REQ-048 AC-17
and the Copilot exclusion exist. The full reasoning for both is in
`.project-toolkit/critique/ADR-084-debate-log-2.md` ("Rationale moved from
ADR-084").

The rule 5 correction is a fact repair, not a policy change. The two enforcing
tests went with the vendored surface in `f79e70c01`. The rule still binds, so
the next vendored hook restores them. `tool-use-hook-bar.md` "What a first
re-add owes" lists that restoration for tool-use hooks. The correction extends
it to every vendored hook.

Open items this amendment left, both closed 2026-11-04 by REQ-048 TASK-006:

- Rule 5 bound through review only, since no guard test saw a new `surface: "plugin"` group. TASK-006 restores both rule 5 tests in
  `tests/hooks/test_dispatch_groups_parity.py`: `test_every_vendored_hook_states_its_customer_value` and
  `test_the_customer_value_check_examines_a_nonempty_surface`. The Copilot exclusion test is
  `test_copilot_plugin_has_no_entry_for_the_hook` in `tests/hooks/test_plugin_stop_registration.py`.
- `tool-use-hook-bar.md` "What a first re-add owes" scoped the rule 5 restoration to tool-use hooks. It now says
  the check binds every vendored hook. Neither closure changes a rule; the owner
  accepted rule 2a and the rule 5 duties on 2026-11-04.

What this amendment does not change: rules 1, 3, 4, 5's presence
requirement, and 6;
the security carve-out; ADR-097's retirement of the tool-use surface; and the
deletion in PR #3372.
