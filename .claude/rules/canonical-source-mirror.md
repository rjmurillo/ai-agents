---
paths:
  - ".claude/hooks/**"
  - ".claude/rules/**"
  - "scripts/validation/**"
  - "build/scripts/**"
  - ".claude/skills/**"
  - ".github/prompts/**"
  - ".agents/governance/**"
  - ".agents/retrospective/**"
priority: high
---

# Canonical Source Mirror Rule

When a component's docstring, comment, or README claims to "match", "mirror", "align with", or "extend" an existing source (a regex, a schema, a function signature, a set of exit codes, a JSON contract), the claim is a load-bearing assertion. The reader trusts it. So does the reviewer. So does the next maintainer who replays the contract from your code instead of from the source.

This rule binds those claims to evidence. It exists because PR #1887 (the M4 evidence-rule guard) was designed against an imagined contract instead of the canonical `scripts/validate_session_json.py:CONTRADICTION_PATTERNS` regex. The error survived several reviews. Aligning M4 to canonical took 7 fix commits. The retrospective at `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` names this anti-pattern "confident incorrectness": partial signal, premature conclusion, confident delivery, multi-round correction.

## What this rule binds

This rule binds any new component under `.claude/hooks/`, `.claude/rules/`, `scripts/validation/`, `build/scripts/`, `.claude/skills/`, `.github/prompts/`, `.agents/governance/`, or `.agents/retrospective/` whose contract is derived from another source in the repository. The two Copilot-side mirrors scope differently by consumer. `.github/instructions/canonical-source-mirror.instructions.md`, read by Copilot in full-repo context, keeps the full path set (`.claude/hooks/**`, `.claude/rules/**`, `scripts/validation/**`, `build/scripts/**`, `.claude/skills/**`, `.github/prompts/**`, `.agents/governance/**`, `.agents/retrospective/**`). Its `src/copilot-cli/` twin ships inside the plugin, so it narrows to the paths that travel with the plugin (`scripts/validation/**`, `build/scripts/**`, `.github/prompts/**`). The rule still binds the `.claude/` paths on the Claude side. Examples:

- A pre-push hook that "mirrors" a CI validator's regex.
- A skill helper that "matches" the exit codes of a validator script.
- A build script that "extends" a schema defined in another module.
- An adapter that "aligns with" the wire format produced by an existing emitter.

If your code contains the words **matches**, **mirrors**, **aligned with**, **same as**, **per `<path>`**, or **identical to** in a docstring or top-level comment, this rule applies.

## What the first commit MUST do

The first commit that introduces the claim MUST:

1. **Cite the path verbatim.** Include the absolute repo path of the canonical source in the docstring or top-level comment. Example: `scripts/validate_session_json.py` or `.agents/architecture/ADR-035-exit-code-standardization.md`.

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

## Behavioral claims: read the body, not the name

A claim about what another component **does** is load-bearing in the same way a "mirrors" claim is. "Validator X skips directory Y." "Hook Z runs on push." "Helper W returns None on failure." The reader acts on these without re-deriving them, and a rule file that carries one is read by every agent on every session it applies to.

A function's name is not evidence of its behavior. Neither is its call site, a prior PR description, or your memory of it. Open the file and read the body. Then quote the line you are relying on, with its path and line number:

```python
# build/scripts/validate_plugin_manifests.py:318-327 prunes it by name:
#     excluded_dirs = {".agent-tmp", ".worktrees", "worktrees", "node_modules",
#                      ".git", "cache", ".pytest_cache", ".pytest_tmp"}
```

PR #3775 shipped rule text in `.claude/rules/testing.md` claiming `.pytest_tmp` was "the only name both `validate_plugin_manifests.py` and `check_placeholder_identity.py` skip". The second half was false. `scripts/validation/check_placeholder_identity.py:36 _is_pytest_tmp` never inspects a directory of that name. It returns true only when the whole repository root sits under `tempfile.gettempdir()` and its resolved path contains `pytest-of-`, which is a different question entirely. The author reasoned from the function's name and never opened the file. The false claim reached always-on instruction text and survived two review rounds before a third-model review caught it.

The function's own docstring stated the real behavior accurately. Reading it would have cost seconds. That is the asymmetry this section exists for: verification is cheap at write time, and a false behavioral claim in a rule file is expensive for as long as it stands, because every reader who trusts it inherits the error and some of them build on it.

This section binds any assertion about another component's behavior, whatever words carry it. The trigger is not a phrase like "mirrors"; the trigger is that you told the reader what some other code does.

## True when you wrote it is not true at merge

The rules above assume the thing you cite exists. In a repository worked through several worktrees at once, that assumption is the one most likely to be false, and it fails in a way no reviewer notices, because the citation was accurate on the machine where it was written.

You write documentation on branch A naming a test, a constant, or a function that you added on branch B. Your shell finds it. Every reader of branch A does not. If A merges first it ships a pointer to nothing.

Nothing in this repository catches that. Two gates look like they would and neither does:

- `orphan-ref-validator` reports four kinds of finding, and its type at `.claude/skills/orphan-ref-validator/scripts/envelope.py:28-34` enumerates all of them:

  ```python
  Kind = Literal[
      "skill_name",
      "script_path",
      "rule_path",
      "instruction_path",
      "scan_truncated",
  ]
  ```

  Every pattern in `patterns.py` matches a file path or a skill name. A test function name and a module constant are neither, so they are invisible to it.

- markdownlint never sees governance prose at all. `.markdownlint-cli2.yaml:131` lists `- ".agents/**"` under `ignores:`, so a PASS on any `.agents/` path means the file was not linted.

To every gate in the repository, a citation to a symbol is ordinary prose. The only check is the one you run.

Before you merge a document that names a test, a symbol, or a count, run `git grep -nF -- "<name>"` **in the worktree of the branch that will merge**, not the one you did the work in. If it returns nothing, either move the documentation to the branch that owns the code or move the code.

The same applies to numbers. A count is a measurement of a commit, not a permanent fact. Re-run it against the tree you are shipping.

On 2026-08-03 both halves of this fired in one change. `TESTING-ANTI-PATTERNS.md` on `test/vacuous-assertion-anti-pattern` cited a test name and a `DID_NOT_RUN` constant that existed only on `fix/gate-aggregator-did-not-run`; `git grep` returned zero hits for both on the branch carrying the prose. Two review rounds on that branch had not reported it. The passing count in the same paragraph was stale for the same reason: it was measured when the file held 41 tests and the file had since grown to 42.

## The one place the mirror outranks the source: always-on membership

Everything above says the canonical source is authoritative and a generated mirror is not. For one question that is backwards, and the inversion is easy to miss because it contradicts the rest of this file.

The question is whether a rule loads on every agent turn. A rule is always-on when its **generated** `applyTo` resolves to `**`, so the answer lives in the generated tree.

The two destination trees now agree, measured on this branch after `session-logs` dropped its optional-session-log mention from `knowledge-persistence`:

| Tree | Consumer | Always-on |
|---|---|---|
| `.github/instructions` | Copilot working in this repository | 7 rules, 70,269 bytes |
| `src/copilot-cli/instructions` | the shipped plugin, installed elsewhere | 7 rules, 70,269 bytes |

The membership is identical: `builder-ethos`, `claude-model-patches`, `code-quality`, `knowledge-persistence`, `search-before-building`, `universal`, `voice`.

Those byte figures are whole generated files, frontmatter included, which is what a consumer actually loads. State the basis whenever you quote one. The same seven rules measure 70,385 bytes at `.claude/rules/`, 116 more, because the generator rewrites the frontmatter on the way out: it drops `priority:` and turns `paths:` or `alwaysApply:` into `applyTo:`. A figure that disagrees with a fresh measurement by roughly that much is a basis mismatch rather than staleness.

That agreement is recent and it is load bearing, so keep naming the tree with the number. Until issue #4317 closed, the generator universalized a rule whose scope was entirely internal, which made `governance`, `secret-redaction`, and `session-logs` always-on in the plugin and cost a vendor install 7,532 bytes a turn on three rules pointing at `.agents/` paths the installing repository does not have. PR #4426 replaced that fallback with an explicit skip, so those rules are now absent from the plugin tree rather than universalized in it. The plugin ships 23 instruction files against 28 in `.github/instructions`, and that gap is the fix rather than drift.

`tests/validation/test_always_on_corpus_claims.py` pins the two trees together and pins the figures on this page against a live measurement, so both the convergence and the numbers quoting it are guarded invariants. Re-measure before changing a number here, and expect the guard to fail if you change one without the other.

`build/scripts/generate_rules.py` reaches `applyTo: "**"` from four different source situations. Only the first is visible in the source file:

1. **The source declares it.** `paths: ["**"]` or `applyTo: '**'`, renamed verbatim per the generator's contract at `build/scripts/generate_rules.py:24`.
2. **The source declares `alwaysApply: true` and no path scope.** Line 25 drops `alwaysApply:`, leaving no scope, so situation 3 applies. `_has_path_scope` at line 209 reads only the path-scope keys, so `alwaysApply` never counts as a scope.
3. **The source declares no scope at all.** Situations 2 and 3 share one branch, `build/scripts/generate_rules.py:338-341`:

   ```python
   if not had_scope and "applyTo" not in result:
       # Universal-scope default for unscoped rules. Insert at the top
       # of the output frontmatter for consistent placement.
       result = {"applyTo": _UNIVERSAL_SCOPE, **result}
   ```

4. **The source declares a scope whose globs are all filtered as internal-only.** This case no longer reaches `**`. `build/scripts/generate_rules.py:342-344` skips the rule instead:

   ```python
   applyto_value = result.get("applyTo")
   if had_scope and isinstance(applyto_value, str) and not applyto_value.strip():
       return _SCOPE_SKIPPED
   ```

   This one is **destination-dependent**. `templates/platforms/copilot-cli.yaml:39-40` lists `.github/instructions` under `keepInternalGlobsFor`, which disables the filter for that tree, so the skip cannot fire there and the in-repo Copilot agent keeps rules it needs for editing `.claude/` and `.agents/`. It fires only for `src/copilot-cli/instructions`, which is why the plugin ships fewer instruction files than `.github/instructions`. The generator reports the count as `Skipped (all-internal scope)` and prunes any artifact it previously emitted.

Situations 3 and 4 leave no source line to grep for. Situation 4 used to fall back to `**`, which inverted intent: narrowing a rule to `.claude/**` read like a reduction in scope and silently widened it to every turn in the shipped plugin. Issue #4317 tracked that inversion and PR #4426 fixed it by skipping rather than universalizing. The generator still prints `WARNING: dropped internal-only glob from applyTo` to stderr per dropped glob, and nobody reads stderr during a build, so trust the skip count and the file count over the warnings.

So a measurement taken from `.claude/rules/` is not conservative, it is wrong in both directions. A measurement taken from one generated tree still does not answer for the other, even while they agree today. Name the tree with the number.

## Read frontmatter with a YAML parser, never a line regex

A scope key can be an inline string or a block list. `.claude/rules/knowledge-persistence.md` uses the block form:

```yaml
paths:
  - "**"
```

A pattern like `^applyTo:\s*(.+)$` returns nothing for that file and reports the rule as unscoped, which is the opposite of the truth: the rule is universally scoped. Use `yaml.safe_load` on the frontmatter block. This is not hypothetical; it produced a wrong always-on count during the audit that added this section, and the count looked plausible enough to act on.

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
