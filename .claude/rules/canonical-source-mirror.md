---
paths:
  - ".claude/hooks/**"
  - "scripts/validation/**"
  - "build/scripts/**"
  - ".claude/skills/**"
  - ".claude/review-axes/**"
  - ".github/prompts/**"
priority: high
---

# Canonical Source Mirror Rule

When a component's docstring, comment, or README claims to "match", "mirror", "align with", or "extend" an existing source (a regex, a schema, a function signature, a set of exit codes, a JSON contract), the claim is a load-bearing assertion. The reader trusts it. So does the reviewer. So does the next maintainer who replays the contract from your code instead of from the source.

This rule binds those claims to evidence. It exists because PR #1887 (the M4 evidence-rule guard) was designed against an imagined contract instead of the canonical `scripts/validate_session_json.py:CONTRADICTION_PATTERNS` regex. The error survived several reviews. Aligning M4 to canonical took 7 fix commits. The retrospective at `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` names this anti-pattern "confident incorrectness": partial signal, premature conclusion, confident delivery, multi-round correction.

## What this rule binds

This rule binds any new component under `.claude/hooks/`, `scripts/validation/`, `build/scripts/`, `.claude/skills/`, `.claude/review-axes/`, or `.github/prompts/` whose contract is derived from another source in the repository. The Copilot-side mirror at `.github/instructions/canonical-source-mirror.instructions.md` (and its `src/copilot-cli/` twin) scopes only to paths Copilot can see (`scripts/validation/**`, `build/scripts/**`, `.github/prompts/**`); the rule still binds the `.claude/` paths on the Claude side. Examples:

- A pre-push hook that "mirrors" a CI validator's regex.
- A skill helper that "matches" the exit codes of a validator script.
- A build script that "extends" a schema defined in another module.
- An adapter that "aligns with" the wire format produced by an existing emitter.

If your code contains the words **matches**, **mirrors**, **aligned with**, **same as**, **per `<path>`**, or **identical to** in a docstring or top-level comment, this rule applies.

## What the first commit MUST do

The first commit that introduces the claim MUST:

1. **Cite the path verbatim.** Include the absolute repo path of the canonical source in the docstring or top-level comment. Example: `scripts/validate_session_json.py`, `.agents/architecture/ADR-035-exit-code-standardization.md`, `build/scripts/validate_marketplace_counts.py`.

2. **Quote the contract verbatim.** Include the exact regex, schema, function signature, exit-code table, or JSON shape, copied character-for-character from the canonical source. Reword nothing. If the contract is too long to inline, quote the load-bearing fragment (the regex pattern, the type signature, the enum values) and link to the file and line range.

3. **Document any intentional divergence.** If your component is stricter, looser, or different than canonical (a pre-push guard that blocks something CI would only warn about; a fast-path that skips a check the canonical performs), add a section to the docstring titled `Stricter/looser/different than canonical` that names the divergence and the reason for it.

These three steps land in **the same commit** that introduces the claim. Not a follow-up. Not after the first review. The point of the rule is to prevent the imagined-contract bug, which is only avoidable before the imagined contract reaches the reviewer.

## What the reviewer MUST verify

When you review a PR that touches these paths and the diff includes the words **matches**, **mirrors**, **aligned with**, or similar:

- Open the cited canonical source. Confirm the verbatim quote is correct, character-for-character. Differences in whitespace, character classes, or boundary tokens are not minor.
- Confirm the divergence section names every behavioral difference, not just the most obvious one.
- If the cited source is itself absent or wrong, treat the PR as blocked until the citation is fixed. A wrong citation is worse than no citation; it weaponizes the next reader's trust.

## Stricter than canonical: defending divergence

A pre-push guard or other local check is allowed to be stricter than the canonical CI validator. This is the M5 evidence-rule pattern documented in the retrospective: block locally what would only be flagged at CI to shorten the feedback loop. When you choose this position, the divergence section is your reviewer-facing communication. Name the canonical floor (e.g. "validator emits a warning"), name the local ceiling (e.g. "guard blocks the push"), and name the reason ("we have observed N rounds of CI bouncing on this; blocking pre-push moves the feedback to the author's terminal where the cost is lowest").

A guard that is silently stricter than canonical is a bug in waiting. A guard that documents its strictness is a feature.

## Anti-patterns rejected by this rule

- **"Matches X" with no path.** A docstring says `# matches the validator` but does not name the validator file. The next reader cannot find what you mean. Reject.
- **"Mirrors X" with a paraphrased contract.** The docstring describes the regex in prose instead of pasting it. The prose drifts from the regex within one revision. Reject.
- **"Aligned with X" with no divergence section, when the implementation diverges.** The reader assumes parity; the code does not deliver parity; the bug compounds with the false claim. Reject.
- **First-commit citation deferred to "I will add it later".** The cost of citing the canonical source is roughly zero at write time and roughly one round of review later. Pay the zero. Reject.
- **Self-referential test that mirrors the producer's own output.** A test that asserts a generator emits a specific string, then checks the generator emitted that string, pins the output to itself. It proves the producer is internally consistent; it proves nothing about the canonical contract the output is supposed to honor, and it cannot catch a wrong variable, a wrong path, or a wrong exit code. This is this rule applied at the test layer. The test that satisfies the rule exercises the contract INDEPENDENTLY: it runs the artifact under the real runtime conditions (the cwd and environment the host sets) and asserts the intended effect, with a negative control proving the test fails when the artifact is wrong. PR #2205 shipped a string-match test of this shape against `generate_hooks._build_copilot_entry`; it passed while the generated hooks wedged customer environments. See `.claude/rules/generated-artifacts.md` and `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md`.

## Reference: the M4 episode

`scripts/validate_session_json.py:CONTRADICTION_PATTERNS` is a single compiled regex:

```python
CONTRADICTION_PATTERNS = re.compile(
    r"(?i)\b(not available|skipped|N/A|deferred|will validate|will run|TODO|pending|TBD)\b"
)
```

The first iteration of M4 in PR #1887 enforced a 20-character minimum on evidence strings. That minimum is not in the canonical regex; it does not appear anywhere in `validate_session_json.py`. It came from the author's mental model of "what counts as evidence". Two commits and two test rewrites later, the M4 guard had been re-pointed at the canonical contract. The first commit's docstring claimed M4 "matches" the validator. The claim was load-bearing and false. This rule exists to prevent the same shape of mistake from landing again.

## References

- `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`. PR #1887 retrospective; "Phase 1, Step 3, Five Whys: M4 evidence rule" names the failure mode.
- `scripts/validate_session_json.py`. Canonical session-log validator; the contract M4 was meant to mirror.
- `templates/agents/implementer.shared.md`, section "Evidence Standards". The implementer-side hierarchy this rule supports at the file-rule layer.
