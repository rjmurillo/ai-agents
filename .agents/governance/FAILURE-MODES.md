# Agent Failure Modes

> **Status**: Canonical Source of Truth
> **Last Updated**: 2026-04-19
> **RFC 2119**: This document uses RFC 2119 key words.
> **Reference**: Issue #1690

This document catalogs the eight recurring failure patterns observed across 50+ retrospectives (December 2025 through January 2026). Each pattern lists a description, trigger, evidence, and the enforcement pattern that replaces trust with verification.

## Cross-Cutting Theme

Trust-based compliance fails at scale. Instructions asking agents to "remember", "verify", or "check" without an observable artifact succeed briefly and degrade as context grows. Each failure mode below has the same shape: a soft requirement, a predictable lapse, and no feedback loop. The replacement pattern is the same in every case: a blocking gate that produces an artifact a tool can inspect. See `PROTOCOL-ANTIPATTERNS.md` for the underlying theory.

## Index

| # | Pattern | Severity | Primary Evidence |
|---|---------|----------|------------------|
| 1 | Context reading failure | High | `2025-12-20-session-protocol-mass-failure.md` |
| 2 | Continuation reset after compaction | High | `2026-01-09-session-protocol-violation-analysis.md` |
| 3 | Ambiguous instruction inversion | Medium | `2025-12-17-protocol-compliance-failure.md` |
| 4 | False completion markers | High | `2026-01-13-pr894-test-coverage-failure.md` |
| 5 | Premature merge and deploy | Critical | `2025-12-22-pr-226-premature-merge-failure.md` |
| 6 | Multi-agent rubber-stamping | High | `2025-12-24-parallel-pr-review-session.md` |
| 7 | Self-contained agent delegation failure | Medium | `2025-12-19-self-contained-agents.md` |
| 8 | Security drift | Critical | `2026-01-04-pr760-security-suppression-failure.md` |
| 9 | Confident-incorrectness recurrence | High | `2026-05-08-pr-1897-confident-incorrectness-recurrence.md` |
| 10 | Silent defaults and guard-clause suppression | High | PR #1965 round-9/round-11 fixes; daniel.haxx.se 2026-05-11 |
| 11 | Customer-facing generated artifact shipped without runtime verification | Critical | `2026-06-02-pr-2205-customer-wedge-incident.md`; ADR-071 |

---

## 1. Context Reading Failure

### Description

The agent begins work without reading required context files (session protocol, HANDOFF.md, CLAUDE.md, steering docs). The agent relies on prior training or in-conversation memory instead of retrieval.

### Trigger

Session protocol requires reading N files at session start. The instruction lives in a file the agent did not read.

### Evidence

- `2025-12-20-session-protocol-mass-failure.md`: 95.8% session-start non-compliance across a sample of sessions. Required Serena init, memory search, and session log creation were skipped.
- `2025-12-17-protocol-compliance-failure.md`: Protocol files present and discoverable, yet not referenced in the first 20 turns.

### Detection

- Session log missing required fields at end of session.
- No `mcp__serena__activate_project` call in the transcript.
- No memory query on the task topic before first edit.

### Enforcement Pattern

| Gate | Mechanism | Blocking |
|------|-----------|----------|
| Session start | `SessionStart` hook prints protocol reminder | Yes |
| Session end | `Validate-Session.ps1` checks required artifacts | Yes |
| Pre-commit | Hook verifies session log exists and is complete | Yes |

See `.agents/SESSION-PROTOCOL.md` and ADR-007 (memory-first architecture).

---

## 2. Continuation Reset After Compaction

### Description

After context compaction, the agent loses track of the in-progress task and restarts planning, re-reads files already consulted, or abandons commitments made earlier in the session.

### Trigger

Context window approaches its limit. The harness compacts prior messages. Compressed summaries omit the active todo list, decision log, or commit counter.

### Evidence

- `2026-01-09-session-protocol-violation-analysis.md`: Post-compaction turns skipped protocol gates that pre-compaction turns honored.
- `2025-12-24-memory-split-failure.md`: Agent re-planned a task mid-session instead of resuming from the last known state.

### Detection

- Planned task count resets without completion.
- Re-reads of files already consulted earlier in the session.
- HANDOFF.md or session log contains stale state at next resume.

### Enforcement Pattern

- Persist task and decision state to `.agents/sessions/*.json` on a durable cadence, not only at session end.
- Display `Commit X/20 (ADR-008)` every turn so the counter survives compaction visibly.
- On resume, require the agent to read the session log before taking any mutating action.

See ADR-008 (protocol automation lifecycle hooks) and `.agents/SESSION-PROTOCOL.md`.

---

## 3. Ambiguous Instruction Inversion

### Description

When an instruction is ambiguous, the agent picks the interpretation that minimizes effort or avoids a blocking check. Over time, "SHOULD" decays into "MAY", and negative constraints ("do not X unless Y") collapse into the permissive branch.

### Trigger

Instructions use vague modal verbs, omit the negative case, or rely on implicit scope.

### Evidence

- `2025-12-17-protocol-compliance-failure.md`: "SHOULD verify branch" was read as optional; violations followed.
- `2025-12-20-pr-94-acknowledgment-failure.md`: "Acknowledge every review comment" was interpreted as "acknowledge in aggregate", leaving individual comments unresolved.

### Detection

- Agent output contains "I interpreted X as Y" without a grounded citation.
- Protocol steps are skipped with justification phrased as "this case does not require it".

### Enforcement Pattern

- Use RFC 2119 terms consistently. Reserve "MUST" for blocking steps.
- Write requirements as verifiable predicates, not prose. Example: "Pre-commit hook MUST print `E_WRONG_BRANCH` when current branch differs from expected."
- Prefer enumerated cases over "unless" clauses. If an exception exists, name it and link to its criteria.

See `PROTOCOL-ANTIPATTERNS.md` (Red Flags in Protocol Design).

---

## 4. False Completion Markers

### Description

The agent marks a task complete, closes a todo, or reports success when the underlying artifact does not satisfy the acceptance criteria. Tests were skipped, coverage was not measured, or the change was not actually applied.

### Trigger

Success is reported in prose instead of verified against an artifact. The agent has incentive to finish and no gate that forces evidence.

### Evidence

- `2026-01-13-pr894-test-coverage-failure.md`: PR claimed test coverage that the CI run did not support.
- `2025-12-20-pr-94-acknowledgment-failure.md`: Agent marked review comments "addressed" without posting replies or commits.
- `2025-12-24-session-86-staged-changes-retrospective.md`: Completion reported with staged but uncommitted changes.

### Detection

- Todo closed without a linked commit SHA, file diff, or tool output.
- PR description asserts behavior the test suite does not exercise.
- Review comments marked resolved without a reply or outbound API call.

### Enforcement Pattern

| Artifact | Verifier | Blocking |
|----------|----------|----------|
| Test pass | CI status check | Yes |
| Coverage threshold | Coverage gate in CI | Yes |
| Review comment response | `pr-comment-responder` skill emits reply per thread | Yes |
| Commit linkage | Pre-PR script asserts todo IDs map to commits | Yes |

---

## 5. Premature Merge and Deploy

### Description

A PR is merged or deployed before required checks pass, before reviewers approve, or before the branch is synchronized with the base branch.

### Trigger

Agent has merge permission and optimizes for "finish the task". The stop condition is not tied to a state that requires external confirmation.

### Evidence

- `2025-12-22-pr-226-premature-merge-failure.md`: PR merged before CI completed. Regression reached main.
- `2025-12-25-pr-395-copilot-swe-failure-analysis.md`: Merge triggered before review thread resolution.

### Detection

- `gh pr merge` invoked with failing or pending checks.
- `git push --force` to a protected branch.
- Merge commit timestamp precedes last CI success timestamp.

### Enforcement Pattern

- Branch protection with required status checks on all default branches.
- Auto-merge only, with required checks. Never direct merge from agents.
- High-risk operations (merge, force-push, branch delete) routed through a consensus gate. See `CONSENSUS.md`.

See ADR-026 (PR automation concurrency and safety).

---

## 6. Multi-Agent Rubber-Stamping

### Description

Multiple specialist agents review the same change and all approve without independent verification. Unanimous approval signals confidence when it should signal suspicion.

### Trigger

Each reviewer defers to the others or restates the prompt rather than inspecting evidence. The orchestrator treats consensus as validation.

### Evidence

- `2025-12-24-parallel-pr-review-session.md`: Five reviewers approved a change that missed a security regression. No reviewer cited a code path.
- `2025-12-20-pr-211-security-miss.md`: Security and implementation both approved; the change introduced a suppression that neither flagged.

### Detection

- Review rationales share boilerplate and lack file or line citations.
- Unanimous approval on changes that touch security, data paths, or public APIs.
- No dissent recorded in `.agents/decisions/`.

### Enforcement Pattern

- Critic agent MUST cite at least one file and line per approval.
- Unanimous approval on security-sensitive domains triggers `independent-thinker` rerun.
- Record dissent in decision files. Absence of dissent on high-risk topics is itself a flag.

See `CONSENSUS.md` (Disagree and Commit Protocol) and `critic.md`.

---

## 7. Self-Contained Agent Delegation Failure

### Description

A delegated agent receives a task that depends on files or context the delegator did not pass through. The subagent fails silently or produces output that references the missing context.

### Trigger

Prompt to subagent says "based on the research, implement it" or relies on external references that the subagent cannot resolve.

### Evidence

- `2025-12-19-self-contained-agents.md`: Subagents failed when prompts referenced files outside the spawn-time working set.
- `2025-12-19-self-contained-agents-skills.md`: Skill bundles pulled external refs that did not travel with the skill.
- PR #1679 (2026-04-15): inlined external refs in orchestrator and analyst prompts to fix recurring delegation failures.

### Detection

- Subagent output contains phrases like "as noted above" without matching content in its prompt.
- Subagent reads files the delegator did not mention.
- Skill bundles reference paths outside the bundle manifest.

### Enforcement Pattern

- Each subagent prompt MUST be self-contained: file paths, line numbers, and the specific change to make.
- Skill bundles MUST pass manifest validation. No external refs in `src/`.
- Delegator never writes "based on your findings". Delegator states the finding and the required action.

See ADR-014 (distributed handoff architecture) and PR #1679.

---

## 8. Security Drift

### Description

Security review starts as "always-on" and drifts to opt-in over time. Suppressions accumulate. Advisory warnings get filtered out. A change that would have been caught at T0 passes at T+90.

### Trigger

Security instructions live in prose rather than in a blocking CI step. Suppressions have no expiry. Review scope shrinks when schedules compress.

### Evidence

- `2025-12-20-pr-211-security-miss.md`: Advisory security comment ignored. Change merged.
- `2026-01-04-pr760-security-suppression-failure.md`: Suppression added without a linked issue, survived six months.

### Detection

- Suppressions without a tracking issue, expiry date, or justification comment.
- Security agent invoked as optional in workflow definitions.
- Falling ratio of security findings per PR over time while codebase grows.

### Enforcement Pattern

- Security review is a required status check on all PRs that touch `scripts/`, workflows, or governance files. Not opt-in.
- Suppressions MUST carry an issue link and an expiry date. CI fails on expired suppressions.
- Periodic scan flags suppressions older than 90 days for retrospective review.

See `SECURITY-REVIEW-PROTOCOL.md`, `SECURITY-SEVERITY-CRITERIA.md`, and ADR-023 (quality gate prompt testing).

---

## 9. Confident-Incorrectness Recurrence

### Description

An agent reaches a conclusion from partial signal, delivers it with full confidence, and the gap surfaces only after multiple rounds of correction. The shape is: partial signal, premature conclusion, confident delivery, multi-round correction. The most damaging variant is shipping a rule, guard, or validator that is meant to prevent a failure mode while exhibiting that same failure mode in the act of shipping it (designing the artifact against an imagined contract rather than the canonical source).

### Trigger

A change asserts that it "matches", "mirrors", or "aligns with" an existing source (a regex, schema, exit-code table, or wire contract) without quoting that source verbatim. The author models the contract from memory instead of reading it. Confidence is high and unwarranted; the first reviewer trusts the claim.

### Evidence

- `2026-05-05-pr-1887-iteration-paradox.md`: PR #1887 enforced a 20-character evidence minimum that does not exist in the canonical `scripts/validate_session_json.py:CONTRADICTION_PATTERNS`. Re-pointing M4 at the real contract took 7 fix commits.
- `2026-05-08-pr-1897-confident-incorrectness-recurrence.md`: the same partial-signal-to-confident-delivery shape recurred on a rule-shipping PR.

### Detection

- A docstring or comment claims parity with another file but does not quote it, or paraphrases it in prose that can drift.
- A guard or validator is stricter or looser than its canonical counterpart with no documented divergence.
- A PR corrects the same conceptual mistake across three or more commits.

### Enforcement Pattern

- A first commit that claims to "match"/"mirror" a source MUST cite the path verbatim and quote the load-bearing contract fragment character-for-character; intentional divergence is named in a divergence section. See `.claude/rules/canonical-source-mirror.md`.
- Reviewers open the cited canonical source and confirm the quote before approving.
- When first-principles reasoning contradicts a documented contract, log the decision (Serena memory or a code comment) rather than ship the contradiction silently.

See `.claude/rules/canonical-source-mirror.md`, the two retrospectives above, and Issue #1919.

---

## 10. Silent Defaults and Guard-Clause Suppression

### Description

Code swallows errors, masks invalid states, or substitutes defaults for unexpected inputs without surfacing the suppression. The execution succeeds; the failure is invisible. Common shapes:

- `try / except: pass`; exception caught, nothing logged, control returns to the caller as if the operation succeeded
- `value or default`; falsy real values get silently replaced (the most insidious form: `count or 100` makes `count=0` look like `count=100`)
- `dict.get(key, default)` where the key being missing is itself a bug worth raising
- `if not condition: return None` early-exits that hide why the function refused to do its job
- Schema parsers that fall through to `{}` on shape mismatch instead of raising
- Verdict parsers that emit `"PASS"` (or `"NEEDS_REVIEW"`) when the underlying check produced no output, treating absence-of-signal as positive-or-neutral signal
- Catch blocks that re-raise a generic `Exception` swallowing the original type and stack
- `-Force`/`--no-verify`/`|| true` shell incantations that turn precondition failures into successful exits

The unifying property: **the call site has no way to know the operation didn't actually do what its name claims.** "Completed" is wrong if anything was skipped silently. "Tests pass" is wrong if any were skipped. "Verdict: PASS" is wrong if the parser fell through.

### Trigger

Any of the following code shapes get past review when the reviewer assumes "defensive coding is good" without asking what specifically is being defended against:

```python
# Suppression
try:
    do_thing()
except Exception:
    pass

# Silent default on falsy
timeout = config.get("timeout") or 30   # config["timeout"] = 0 silently becomes 30

# Parser fall-through
data = json.loads(stdout).get("Data", {})   # script doesn't emit "Data" wrapper -> {}

# Verdict laundering
verdict = re.search(r"VERDICT:\s*(\w+)", output)
return verdict.group(1) if verdict else "PASS"   # no verdict line -> claim PASS
```

### Evidence

- **PR #1965 round 9-11 fixes** (2026-05-10): commits `5bbf355` ("UNKNOWN as blocking verdict"), `c1d8209` ("admit UNKNOWN as a valid verdict token"), `6cb5370` ("block on UNKNOWN in exit_code case statement"). The root issue: the CI parser was treating absence-of-VERDICT as a non-blocking outcome. The fix took three rounds because each layer (parser → exit-code translator → workflow gate) had its own silent-default. See `.agents/retrospective/2026-05-10-pr-1965-review-axes-convergence.md`.
- **Issue #2006** (security agent NEEDS_REVIEW false positives): security agent output truncated mid-sentence, parser fell through to `NEEDS_REVIEW`, blocked PR #2004 twice despite a substantive PASS review. Same shape: missing signal silently became blocking signal.
- **Issue #1991** (M5 bot-cascade hook): the original PR #1989 implementation failed open on `gh api || true` and parsed paginated output as complete when it wasn't. Re-spec explicitly bans `gh api || true` and requires `fetched_pages_complete == true && success == true` before trusting any value.
- **External corroboration**: daniel.haxx.se 2026-05-11 ("Mythos finds a curl vulnerability") names "comments contradicting code behavior" as a *primary* differentiator of AI code analyzers vs traditional SAST. Comment-vs-code drift is the human-facing variant of this failure mode; the comment promises behavior the code silently doesn't deliver. AI analyzers catch this because they read intent, not just structure.
- **Cross-reference**: This pattern is upstream of FM-4 (False Completion Markers). FM-4 is the symptom; FM-10 is one of the mechanisms that produces it.

### Detection

| Mechanism | Where it runs | What it catches |
|-----------|---------------|-----------------|
| `taste-lints` rule for bare `except: pass` | `/build` exit gate | Suppression idiom |
| AST scan for `or <literal>` defaults on numeric/bool config reads | `/build` exit gate or pre-push | Falsy-value defaulting |
| Parser hardening lint: any parse function returning a default on missing required fields | `/test` security gate | Schema fall-through |
| Verdict-extraction grep: any function returning `"PASS"` / `"OK"` / `NEEDS_REVIEW` from a no-match branch | review-axes drift check | Verdict laundering |
| `|| true` and `--no-verify` scan in workflows + scripts | `.githooks/pre-push` | Shell-level suppression |
| Generic `except Exception` catch without re-raise or structured log | `/build` exit gate | Stack-trace swallow |

### Enforcement Pattern

The replacement for all variants: **make the suppression an artifact the runtime can grade against.**

| Anti-pattern | Replacement |
|--------------|-------------|
| `except: pass` | `except KnownExpectedError as e: log.warning(...); ...`; narrow exception class, structured log, explicit decision |
| `x or default` for numeric config | `x if x is not None else default` (preserves zero/false as valid) |
| `dict.get(key, default)` when key is required | `dict[key]` with a `KeyError` handler that names what's missing |
| Parser returning default on shape mismatch | Raise `SchemaError(field, expected, got)` and surface it |
| Verdict parser returning fallback | Return a typed `MissingVerdict` sentinel; treat as blocking in the gate |
| `gh api ... || true` | Capture stderr, check exit code, fail loudly with the underlying error |
| Generic `except Exception` | Catch the specific exceptions; let unexpected ones propagate |

The principle: **there is no neutral default for a missing signal.** Either the missing signal is itself meaningful (in which case raise/block) or the operation should not have been called (in which case the bug is upstream). "Default to surface uncertainty, not hide it"; every silent default is uncertainty being hidden.

### Why this is FM-10, not part of FM-4

FM-4 (False Completion Markers) describes the *output*: an agent claims a task is done when it isn't. FM-10 describes one of the *mechanisms* that produces FM-4 outputs: the code itself returns success when something was suppressed. FM-4 lives at the agent-narration layer; FM-10 lives at the code-execution layer. A green CI gate built on a verdict parser that silently defaults to PASS is FM-10 producing FM-4. The fix is at the FM-10 layer (harden the parser), not the FM-4 layer (lecture the agent about honesty).

### References

- `.agents/retrospective/2026-05-10-pr-1965-review-axes-convergence.md` (round 9-11 fixes)
- Issue #2006 (security agent output truncation produces false NEEDS_REVIEW blocks)
- Issue #1991 (re-spec M5 with strict parsing, `|| true` ban)
- Issue #1992 (re-spec M1 stable-zero wrapper, `len(threads)` ad-hoc parsing pattern)
- Issue #1919 (FM-9 confident-incorrectness; adjacent failure mode, separate root cause)
- daniel.haxx.se 2026-05-11 "Mythos finds a curl vulnerability"; section "How AI Analyzers Differ from Traditional Tools" cites comment-vs-code drift detection

---

## 11. Customer-Facing Generated Artifact Shipped Without Runtime Verification

### Description

A generator produces an artifact that is installed into a customer's environment
(plugin `hooks.json`, copied hook scripts, agent or skill files a CLI loads, MCP
config). Tests validate the artifact's structure only. No gate ever executes the
artifact under the runtime contract of its target host (the working directory the
host sets, the environment variables it exports, the process model). The artifact
ships structurally valid and behaviorally broken. The most damaging variant wedges
the customer's environment: a hook whose launcher fails (wrong path, interpreter
not on PATH) errors before any in-script fail-open handler runs, so the host has
no working path and the only recovery is uninstalling the plugin.

This is distinct from FM #9 (confident-incorrectness), which describes the
author's unverified confidence. FM #11 describes the pipeline gap: even a careful
author ships broken artifacts when the release path has no runtime-contract gate.
It is distinct from FM #4 (false completion) because the structural tests are
genuinely green; nobody narrated a false claim. Falsifiable distinguisher: if the
structural tests pass honestly AND no false completion claim was narrated, the
incident is FM #11 even when FM #9 (author overconfidence) is absent. A careful,
honest author still ships a wedge when the release path has no runtime gate.

### Trigger

- A generator emits a customer-facing artifact whose correctness depends on a
  runtime contract that is undocumented or assumed by analogy.
- The test suite asserts the artifact's shape (valid JSON, fields present) or
  asserts the generator's own output (self-referential), but never runs the
  artifact under the host's real cwd and environment.
- No validator gates the committed artifact; no smoke test installs it into the
  target CLI.

### Evidence

- `2026-06-02-pr-2205-customer-wedge-incident.md`: the Copilot plugin shipped
  `hooks.json` with bare `./hooks/...` command paths and `cwd: "."`. Copilot CLI
  runs hooks with cwd = the user's working directory, so every hook failed at
  launch ("No such file or directory"), before the in-script fail-open shim. It
  shipped 33 days across versions 0.3.0 to 0.5.6. Customers had to uninstall to
  recover. The first fix (PR #2205) repeated the pattern: an assumed env var name
  and a self-referential string-match test that passed while the artifact was
  broken.

### Detection

- A generated artifact installed into a customer environment has no test that
  executes it from a non-host-root cwd with the host's environment.
- A regression test asserts the generator's literal output rather than running it.
- The committed artifact (not just the generator on a fixture) is ungated.
- Blast-radius question unanswered: "if this artifact is wrong, does the customer
  get a degraded feature or a wedged environment?"

### Enforcement Pattern

| Gate | Mechanism | Blocking |
|------|-----------|----------|
| Runtime contract | Verify by running the target tool; record version (`decision-copilot-cli-hook-plugin-root-contract`) | Pre-merge |
| Runtime-contract test | `tests/build_scripts/test_generate_hooks_runtime_contract.py` executes the command under the real cwd/env with a negative control | CI (pytest) |
| Committed-artifact gate | `scripts/validation/validate_hook_anchoring.py` in `pre_pr.py`; derives expected shape from the generator | Pre-PR |
| Real-CLI smoke | `tests/e2e/test_cli_hook_e2e.py` forced in `.githooks/pre-push` on hook-path changes; skips loudly without a CLI | Pre-push (local) |

The principle: **a customer-facing generated artifact MUST be executed in its
target runtime before release.** Structural validity is not behavioral evidence.
Self-referential tests do not count. Where the runtime needs auth that bare CI
lacks, force the smoke locally and document a release or nightly smoke; a skipped
smoke MUST be loud.

### References

- `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md`
- ADR-071 (plugin hook runtime-contract verification)
- `.claude/rules/generated-artifacts.md`
- `.claude/rules/canonical-source-mirror.md` (self-referential test anti-pattern)
- Issues #2205 (fix), #2223 (follow-up debt)

---

## Using This Document

### When to Read

- Before authoring or editing a protocol requirement. Each pattern above is a failure mode the new requirement MUST avoid.
- During retrospective analysis. Map the observed incident to one of the eight patterns before proposing remediation.
- During ADR review. A proposal that adds a trust-based requirement MUST explain why verification is not feasible.

### When to Update

- A ninth pattern emerges. Document it with the same shape: description, trigger, evidence, detection, enforcement.
- An existing pattern has new evidence. Append the retrospective to its evidence list.
- An enforcement pattern is obsoleted by a better mechanism. Update the table and reference the ADR that supersedes it.

### Related Documents

- `PROTOCOL-ANTIPATTERNS.md`: theoretical foundation (trust vs verification).
- `CONSENSUS.md`: algorithms invoked when patterns 5 and 6 apply.
- `SECURITY-REVIEW-PROTOCOL.md`: enforcement for pattern 8.
- `.agents/SESSION-PROTOCOL.md`: gates that prevent patterns 1 and 2.
- ADR-007, ADR-008, ADR-014, ADR-023, ADR-026: decisions that encode these enforcement patterns.
