# ADR-068 / ADR-071 / ADR-085 metric-refresh debate log (issue #4874)

Six-agent adr-review of the dispatcher-metric refresh triggered by the
`plugin-pretooluse-10-require_subagent_model` dispatch group. Agents:
architect, critic, independent-thinker, security, analyst,
high-level-advisor. Each round ran all six in parallel against the staged
diff and the live tree, returning structured verdicts
(Accept / Disagree-and-Commit / Block) with P0/P1/P2 findings.

Change under review: ADR-068, ADR-071, and ADR-085 updated for the third
PreToolUse plugin gate (three shims, 110 seconds configured timeout, 115
second host entry, four vendored registrations across two events), plus the
knowledge-test pins in `tests/build_scripts/test_hook_contract_knowledge.py`.

## Round 1: 3 Block, 1 Disagree-and-Commit, 2 Accept

Blocking consensus (architect, critic, independent-thinker):

- P0: ADR-068's own re-evaluation triggers 2 (beyond two shims / 100
  seconds) and 3 (new blocking gate on the consolidated path) fired, and the
  change shipped as a metric refresh without recording the re-evaluation.
- P0: the refresh was partial. ADR-068 kept contradictory current values
  (100/105 seconds in Consequences against 110/115 in Decision item 4) and
  six stale two-shim statements across Alternatives, Consequences, rationale,
  and the impact table.
- P1 (critic): no measured host contract backs the new `Agent|Task` matcher
  on Copilot; ADR-071 owns that ledger.
- P1 (security, D&C): ADR-071 omitted the new gate's deliberate shim-level
  fail-open (#4672 policy).
- P1 (independent-thinker): the `.github/hooks` registration surface was
  recorded in no ADR.

Resolution: dated Status amendment added to ADR-068 recording the fired
triggers and re-affirmation; every stale numeral rewritten; trigger 2
thresholds reset with an absolute ceiling added later; ADR-071 gained the
fail-open policy note and matcher-evidence caveat; ADR-085 gained the
`.github/hooks` surface note; the knowledge test gained refutations of the
superseded numerals.

## Round 2: 2 Block, 1 Disagree-and-Commit, 3 Accept

- P1 (security, independent-thinker, Block): ADR-071 claimed "shim
  self-filtering is the enforced layer" for Agent/Task calls while calling
  the same layer unprobed, and the shim could not match a native lowercase
  `task` payload.
- P1 (critic, D&C): ADR-068's residual text contradicted shipped #4706 code:
  the Copilot dispatcher runs timed shims in child processes and a timeout
  denies, while the ADR still described an unbounded in-process hang and
  listed the child-process alternative as wholly rejected.
- P1 (critic): ADR-068's Context omitted the `.github/hooks` direct
  registration, the exact shape its Alternatives table calls unadopted.
- P1 (architect, advisor): two skill docs-of-record still carried the
  pre-#4874 inventory (`ai-agents-architecture-contract`,
  `ai-agents-portability-campaign`).

Resolution: a lowercase `copilotMatcher` variant was built, measured, and
reverted after the generator dropped the host-level matcher for a
runtime-name token, which respawns the dispatcher on every tool call (the
#3075 regression). The shipped shape keeps `^(Agent|Task)$` with the host
union `Bash|Agent|Task`; ADR-071 records the rejected variant and the
version-sensitive residual. ADR-068 re-scoped the residual against #4706,
recorded the `.github/hooks` exception, the composition inversion, and the
broadened Copilot spawn surface. Skill counts and mirrors were fixed.

## Round 3: 1 Block, 2 Disagree-and-Commit, 3 Accept

- P0 (independent-thinker): ADR-068's remaining benefit claim ("saves one
  host process start") is falsified by #4706: a matched call starts the
  dispatcher plus one child per timed shim (four interpreter starts on
  `git push`) where direct registration starts at most two.
- P1 (critic, independent-thinker, security): the round-2 residual re-scope
  overcorrected. On the Claude side every PreToolUse group holds one shim in
  its own host entry, so no shim runs behind another today; the in-process
  bypass is latent, not live.
- P1 (critic): the amendment cited a debate log that did not yet exist in
  the tree, and ADR-071/ADR-085 carried no dated 2026-08 provenance.
- P2 (critic): `.claude/lib/hook_dispatch.py` still said timeout metadata is
  "validated but not enforced", contradicting its own #4706 code path.

Resolution: the benefit claim was corrected in ADR-068 Status, rationale,
and Consequences, and the knowledge test now pins the corrected claim; the
residual is stated as latent on the Claude side; trigger 3a (interpreter
starts per matched call, matcher-union width) was added; ADR-071's new
content moved under its own dated amendment heading with the plugin-path
reachability of the lowercase spelling stated precisely; ADR-085 Status
gained a dated provenance line; the `hook_dispatch.py` docstring was
corrected and mirrors regenerated; this file is that debate log, landing in
the same commit as the ADR edits.

Positions accepted without further change: the 2026-08-11 amendment date
(repository tooling clock), the reduction-ratio test pin, and deriving the
skill-surface counts inside the knowledge test (follow-up scope).

## Round 4: 2 Block, 3 Disagree-and-Commit, 1 Accept

- P0 (security): the ADRs claimed the shim converts malformed stdin to
  allow; the shipped generated shim exits 2 on malformed JSON and on a
  missing tool name (generator crash policy), confirmed by direct
  execution. The prose promised a fail-open guarantee the plugin artifact
  does not provide.
- P0 (independent-thinker): the disjoint-matcher budget claim was false on
  the Copilot dispatcher, which spawns every timed shim before the shim's
  own matcher check; any matched call can consume the full 110-second sum
  against the 115-second entry, and the Claude side drops per-shim timeouts
  entirely (host entries 300/60/60 are the real bounds).
- P1 (architect, critic, advisor): two savings-claim survivors (Context,
  Alternatives direct-register row) and the keep-one-host-entry row's
  inverted rationale; the ADR-071 amendment heading sat above July probe
  material it did not author; the union-cost bullet omitted the dominant
  direction (every Copilot Bash call pays a child start for a shim that
  cannot fire there; a sub-agent spawn went from zero hook cost to four
  starts); trigger 3a fired on the state it ratified; a stale
  "2 events and 3 groups" survived in weak-points.md.
- P2 (security): glob metacharacters in `subagent_type` spoofed the
  definition search (`"*"` allowed; CWE-22/CWE-400 shape).

Resolution: both P0 corrections landed (fail-open contract restated per
path: script-level fail-open holds end to end only on `.github/hooks`; the
plugin path denies on pre-dispatch input errors and timed-shim timeouts;
budget text states the spawn-before-filter behavior and per-harness
bounds). All savings survivors retired and added to the stale-string
blocklist with "can skip later gates". Status cost model harness-scoped.
Trigger 3a re-baselined to the 2026-08-11 state and formatted as a
continuation of trigger 3. ADR-071 amendment relocated below the July
material with a deny-on-timeout carve-out. weak-points.md corrected. The
glob-metacharacter spoof was fixed in code: unsearchable names fall
through to the model requirement, with parametrized tests, and the Copilot
shim was regenerated.

## Round 5: 1 Block, 2 Disagree-and-Commit, 3 Accept

- P0 (independent-thinker): the round-4 correction over-corrected. The
  deny-on-malformed-input contract is Copilot-only: the Claude plugin path
  has no generated shim and no per-shim timeout, so the host matcher
  filters, the script runs directly, and its fail-open covers malformed
  input there (measured exit 0). The ADR sentences were written
  unqualified.
- P1 (critic): the refuted matcher-disjointness budget sentence survived in
  ADR-068's Status amendment; the trigger 3a sub-agent baseline rested on
  the unprobed task-to-Agent mapping without saying so.
- P1 (advisor, independent-thinker P2): a stray binary
  `.agents/todos.db` was staged with the review set.
- P2 (architect, advisor): the five-shim / 150-second ceiling carried no
  non-re-baselinable marker; frontmatter date-field convention is mixed;
  the dependent-components table lacked the `.github/hooks` row.

Resolution: both failure-contract sentences are harness-scoped in both
directions (Copilot plugin: deny on pre-dispatch input errors and
timed-shim overruns; Claude plugin and `.github/hooks`: script-level
fail-open end to end, 60-second host entry as the Claude bound); the
disjointness sentence is replaced with the spawn-before-filter statement;
the sub-agent baseline is marked derived-not-probed; the ceiling is marked
absolute; the dependent-components row is added; the stray database file
is unstaged.

Accepted residuals, recorded rather than fixed: the frontmatter date-field
convention (mixed precedent, follow-up), the PostToolUse default-timeout
formula nuance (untimed shims receive a generator default of 30 seconds
that trigger 2's configured-sum metric does not see), the unprobed
115-second host grant, and the architect's standing position that the next
PreToolUse addition must carry a direct-registration comparison and either
re-affirm consolidation on measured grounds or supersede ADR-068.

## Round 6: consensus. 2 Accept, 4 Disagree-and-Commit, 0 Block

Verdicts: analyst Accept, high-level-advisor Accept, architect D&C,
security D&C, independent-thinker D&C, critic D&C. The analyst
independently re-verified every changed number against the shipped
artifacts (110/115, `Bash|Agent|Task`, 300/60/60 Claude host entries, four
vendored registrations, seven settings registrations, both
failure-contract halves by direct execution) and found no metric wrong.

Dissent conditions, all honored in the same commit:

- ADR-071's half-landed scope fix completed: the stale "only" deleted and
  "On the plugin path" scoped to the Copilot plugin path, so ADR-068 and
  ADR-071 now state the same failure contract.
- ADR-068 Implementation Notes item 4 corrected (#4706 enforces per-shim
  bounds on Copilot; Claude drops them, host entries bound).
- The two surviving savings clauses in "Why the In-Process Kill Was
  Rejected" rewritten; "No in-process timeout enforcement", "the spawn
  cost this ADR removes", and "removes process startup" added to the
  stale-string blocklist.
- `hook_dispatch.py`'s "cold-start paid once instead of N times" docstring
  scoped to untimed shims; mirror regenerated.
- Body amendment ledgers updated (ADR-068 and ADR-085 list 2026-08-11;
  the amendment count corrected to six).

Standing positions carried into the record rather than fixed here:

- Architect: the next PreToolUse addition must carry a
  direct-registration comparison and either re-affirm consolidation on
  measured grounds or supersede ADR-068; another metric refresh is the
  wrong change class for it. Trigger 3's 2026-08-11 baseline encodes this.
- Independent-thinker: the surviving cost case for consolidation is
  structural (registration shape, reviewed output policy), not
  quantitative; the deferral of a supersession is procedural.
- Status-section layering in ADR-068 is nearing the point where a
  consolidation rewrite of the section itself is warranted.

Consensus per the debate protocol: all six agents Accept or
Disagree-and-Commit, no unresolved P0, dissents recorded above.
