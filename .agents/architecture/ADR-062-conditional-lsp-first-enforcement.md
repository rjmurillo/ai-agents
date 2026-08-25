---
id: ADR-062
status: accepted
date: 2026-07-27
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-062: Conditional LSP-First Navigation Enforcement

## Status

Accepted as amended (repo-owner @rjmurillo, 2026-07-18). Originally proposed
2026-05-31; amended 2026-07-17 (adr-review consensus 6/6 Accept) to retire the
runtime enforcement layer and retain only the static steering. See the
Amendment section below.

## Date

2026-05-31

## Amendment 2026-07-17 (accepted): Retire the runtime enforcement layer, keep the static steering

Status of this amendment: Accepted (repo-owner @rjmurillo, 2026-07-18).
adr-review consensus recorded (6/6 Accept, see the debate log). This amendment
is filed as issue #3214 and unblocks the hook removal in issue #3216, part of
the #3197 vendored-hook ROI review. It records the decision only. It does not
delete any hook. The deletion is the implementation issue this unblocks.

Change: mark the LSP-first runtime enforcement hooks retired. The retired set is
the five PreToolUse guards (`invoke_lsp_read_guard.py`, `invoke_lsp_grep_guard.py`,
`invoke_lsp_bash_grep_guard.py`, `invoke_lsp_glob_guard.py`,
`invoke_lsp_pre_delegation_guard.py`), the two retired PostToolUse trackers
(`invoke_lsp_read_tracker.py`, `invoke_lsp_usage_tracker.py`), the SessionStart
reset (`invoke_lsp_session_reset.py`), and the shared state and detection
modules under `.claude/lib/hook_utilities/` that only those hooks consume
(`lsp_gate_state.py`, plus any code in `lsp_provider.py`, `lsp_symbols.py`,
and `lsp_health.py` with no other caller, enumerated during #3216). Keep the static steering: the
canonical rule `.claude/rules/lsp-first.md` shipped as context every session,
the Serena Init BLOCKING step in AGENTS.md, and the removed per-turn
`invoke_serena_reassertion.py` nudge (issue #1993). Lefthook handles Git events
and has no user-prompt lifecycle event. Issue #3216 classified this advisory
nudge for removal because static steering and Serena Init already carry the
behavior. The removal is complete, and it needs no Lefthook replacement. The
three-tier navigation preference (Decision, Section 1) survives as steering; only the blocking
behavior is withdrawn.

Rationale: the #3197 ROI review measured the enforcement layer against three
evidence streams (adversarial prosecution, 24 real Claude transcripts, 64
Copilot logs). It found:

- One true positive in 6.5 weeks. The single catch was a harmless grep redirect.
  Against it stand documented false positives #3091 (a cargo-cult "LSP CONTEXT"
  incantation agents emit to satisfy the gate), #2200, #2454 (merge-conflict
  reads), and #2622 (LSP-down hard blocks), plus multiple blocks this week.
- The retired Read gate fired on the hottest tool. The deleted `invoke_lsp_read_guard.py` ran on
  every Read to enforce a preference, not a safety property, and paid the 250 ms
  to 1 s Windows spawn tax measured in #3075 on every invocation.
- The preference now has two enforcement-free carriers.
  `.claude/rules/lsp-first.md` ships as context every session, Serena Init is
  BLOCKING at session start (AGENTS.md). The removed #1993 per-turn reassertion
  hook used to be a third carrier. The runtime block was the most expensive layer
  on a preference the remaining carriers already preserve.
- Most of the family self-neuters in consumer repos. The guards gate on the git
  origin being `ai-agents` (`skip_if_consumer_repo`), so they no-op in any
  customer repo regardless of the block.

This reverses the core Decision ("adopt a conditional, availability-gated
LSP-first enforcement layer") on the enforcement axis only. The load-bearing
conditioning that made the original design fail-open is preserved by removal:
with no gate, there is no gate to wedge. The architect-review dissent recorded
under Consequences ("ship warn-first / measure-then-flip given the #1993 soft
layer is one day old and unmeasured") is now settled by the measurement the
dissent asked for. Six and a half weeks of data show the flip should have gone
the other way.

What this amendment does NOT change:

- `.claude/rules/lsp-first.md` and its two mirrors stay. The steering is
  retained, not retired. The enforcement-layer mechanics that file currently
  documents (the env-var escape hatches, the hook-tier description) are cleaned
  up by the #3216 removal when the hooks they describe are deleted; the
  three-tier navigation preference the file carries is what stays.
- Serena Init (AGENTS.md BLOCKING) stays. The #1993 re-assertion hook has been
  removed. Lefthook handles Git events and has no user-prompt lifecycle event.
  Issue #3216 classified the advisory nudge for removal because static steering
  and Serena Init already carry the behavior. It needs no Lefthook replacement.
- No security property changes. Section 4 already states the gate-state is not a
  security boundary and Section 7 shows the detection modules are CWE-78 and
  CWE-22 safe by construction; the modules are removed with the hooks, not
  weakened, and no security control depended on the gate.

Refs: issue #3214 (this amendment), issue #3197 (ROI review), issue #3216 (hook
removal this unblocks), issue #3075 (Windows spawn cost), issues #3091, #2200,
#2454, #2622 (false positives). The amendment's adr-review consensus is recorded
in `.agents/critique/ADR-062-debate-log.md` alongside the original debate.

## Context

Agents default to Grep, Glob, and full-file Read for code navigation. For
symbol-level questions ("where is X defined", "who calls Y") this is
token-expensive: a grep on a symbol returns noisy matches, then several wrong
file Reads. A Language Server Protocol (LSP) query answers the same question in
one call with a file:line result.

This repository already mandates Serena (an MCP symbol server) first, but only
through steering, never enforcement:

- AGENTS.md makes Serena Init BLOCKING at session start.
- A removed per-turn UserPromptSubmit re-assertion hook
  (`invoke_serena_reassertion.py`, issue #1993, commit `e6fa83a9`, merged
  2026-05-30) previously re-injected a Serena reminder every prompt.
- `.claude/rules/claude-model-patches.md` steers to dedicated tools over shell.

Measured drift evidence: 2026-05-10 session 16 logged 10+ native Read calls on
code files instead of `get_symbols_overview` / `find_symbol`. That motivated the
#1993 soft hook. No PreToolUse gate blocks a symbol search on a code file or
requires LSP navigation before a code Read today (the ~21 existing PreToolUse
guards in `.claude/hooks/PreToolUse/`, minus `_bootstrap.py` and
`push_guard_base.py` infrastructure, cover commit, push, security, and session
protocol, not navigation).

Corpus mix (tracked files, the source of the scope decision): 6031 files, 79
percent non-code (3566 `.md`, 1070 `.json`, 93 yaml), about 19 percent code
(1146 `.py` / 325K LOC, 25 `.ts`). `.serena/project.yml` configures 8 languages:
bash, yaml, python, markdown, powershell, typescript, json, toml. It is the
source of truth for which languages receive LSP treatment.

The external `claude-code-lsp-enforcement-kit` (nesaminua, MIT, v2.3.2)
implements hard enforcement via 7 Node.js hooks installed to user-global
`~/.claude`, with state in `~/.claude/state`, blocking unconditionally. Two
facts block direct use:

1. Toolchain and placement conflict: this repo is Python-first (ADR-042),
   per-repo plugin with dual registration, no scratch in tree, fail-open thin
   hooks (release-it.md, ADR-006). The kit violates each axis.
2. The "always connected" assumption is false here: Serena deactivates after
   compaction. Unconditional grep-block after a compaction wedges the agent: it
   can neither navigate (LSP down) nor search (blocked). A fail-closed deadlock,
   the inverse of the repo's universal fail-open convention.

User directive: enforce LSP-first for every file type any LSP can navigate;
detect availability Serena, then native LSP, then grep/glob/sed as the absolute
last resort; prefer an LSP whenever one exists; graduated hard-block; full
7-hook port; enabled on merge.

## Decision Drivers

- Token cost of grep-based symbol navigation on a 1146-file, 325K-LOC Python
  surface, plus the 2026-05-10 measured drift.
- Fail-open and graceful-degradation are mandatory (release-it.md). A navigation
  gate that can wedge a turn is unacceptable; the design must degrade to allowing
  the raw tool on any uncertainty.
- Precedent: the #1993 hook deliberately chose stateless, unconditional steering
  (see Relationship to Prior ADRs). The user has chosen to proceed past the
  unmeasured-soft-layer timing concern with hard enforcement; the architect
  review's dissent on timing is recorded under Consequences.

## Decision

Adopt a conditional, availability-gated LSP-first enforcement layer, ported to
Python, wired into both harnesses, covering every LSP-navigable file type. The
load-bearing decision is the conditioning: each guard is a no-op (exit 0, no
message) unless the target file's language has an available LSP that provides
the relevant capability. Enforcement is the exception, not the default.

### 1. Three-tier navigation preference

Serena MCP symbolic tools first; else native LSP (Claude built-in `LSP` tool /
Copilot auto-LSP); else grep/glob/sed. Detection order and the
`.serena/project.yml` language list decide which tier applies per file.
"Available" is a PURE configuration check (no live probe, see Section 8).

### 2. Conditional blocking, never unconditional

```
BLOCK iff:
    grep-family search (Grep tool, or bash grep/rg/egrep/fgrep/ag/ack)
    AND not `git grep`            (history search, always allowed)
    AND target language has SYMBOL-NAVIGATION capability
        (go-to-definition / find-references): programming languages only
    AND the pattern is a code symbol (camelCase/PascalCase/dotted/snake>=9)
    AND an LSP tier is available for that file type
Else: ALLOW (exit 0).
```

The symbol-grep guards key on go-to-definition / find-references capability, so
they never fire on markdown/json/yaml/toml (those have no symbol search that
replaces grep). The Read gate (item 3) uses a different capability and is where
the user's all-languages directive applies.

### 3. Graduated Read gate, three tiers, all configured languages

The Read gate keys on the `get_symbols_overview` capability, which Serena
provides for ALL 8 `.serena/project.yml` languages (including markdown, json,
yaml, toml). For files in any configured language with that capability available,
the gate ramps. `nav_required = 2` (matches the Surgical threshold; the Hard
block and Surgical tiers cannot disagree on the same `nav_count`).

| Tier | Trigger | Decision | Acceptance criterion |
|------|---------|----------|----------------------|
| Warmup | first gated Read this session, no warmup recorded, overview-capable LSP available | BLOCK (exit 2): call get_symbols_overview/diagnostics first | Read(x.py), state absent, Serena configured -> exit 2 |
| Soft warn | reads 1-2 after warmup | ALLOW; read 3 with nav_count 0 -> warn (exit 0, systemMessage) | 3rd Read, nav_count 0 -> exit 0 + warning text |
| Hard block | reads 4+ with nav_count < nav_required (2) | BLOCK (exit 2) until a nav call occurs | 4th Read, nav_count 0 -> exit 2 |
| Surgical | nav_count >= nav_required (2) | ALLOW all reads for the session | any Read, nav_count 2 -> exit 0 |

Every tier degrades to ALLOW when no overview-capable LSP is available for the
file type. (Capability binding: symbol-grep keys on definition/references; the
Read gate keys on get_symbols_overview. The two are named distinctly in
`detect_lsp_provider.py` so a guard requests only the capability it needs.)

### 4. State: owned, outside the working tree, fail-open

A PostToolUse usage tracker is the single system-of-record for gate-state
(warmup flag, nav_count, read_count, read-file set). It writes to a
user-scoped state directory OUTSIDE the git working tree (never committed),
keyed `hashlib.sha256(cwd)`. The guards only READ it. Reset is driven solely by
the SessionStart lifecycle signal (not agent-controllable input); the reset
handler is idempotent. A missing or unreadable state file is treated as "needs
warmup" and never raises. Gate-state is not a security boundary: it is
agent-adjacent, and fail-open means tampering degrades to allowing the raw tool,
never to a more-permissive security decision (CWE-284 noted, severity Low
because no security control depends on it).

### 5. Failure modes: fail-open is the default

LSP-provider-unavailable, unsupported file type, no symbols detected, malformed
input, tty/empty stdin, consumer-repo, and ANY exception all degrade to ALLOW
(exit 0) with a one-line stderr note. The gate never blocks on uncertainty.

### 6. Operability: kill switch and mode

- `SKIP_LSP_GATE=true` bypasses all guards (mirrors `SKIP_QA_GATE`,
  `SKIP_ADR_GATE`, `SKIP_WORKFLOW_LOCAL_TEST`). A misfire cannot wedge sessions.
- `LSP_GATE_MODE` accepts `block` (default, per user directive) or `warn`
  (advisory exit-0 messages instead of blocking). Single-toggle rollback from
  hard-block to advisory without a revert.
- Every decision writes a one-line record to the hook `audit.log`.

### 7. Security

Symbol detection is pure in-process (Python regex on naming convention plus file
extension). No `shell=True`, no string interpolation into a shell, no outbound
process on the tool path (CWE-78/77 eliminated by construction). All
tool-argument-derived strings are untrusted: paths are `Path.resolve()`
normalized and matched only against the resolved repo root, with an
always-bypassed allowlist (TMPDIR/mktemp scratch, out-of-repo paths, dotfiles)
(CWE-22 safe). Out-of-repo targets are never gated.

The always-bypass set also covers files that the LSP cannot meaningfully parse
during conflict resolution (issue #2454): when `.git/MERGE_HEAD`,
`.git/rebase-merge`, or `.git/rebase-apply` exists at the repo root, or when
the target file's leading window starts a line with a conflict marker
(`<<<<<<<`, `=======`, `>>>>>>>`). The merge-state check is pure `Path.exists`
on the three sentinel paths git itself writes (no shell-out, CWE-78 safe). The
conflict-marker scan is a bounded read (256 KB cap) anchored to column 0 so
prose, regex patterns, and string literals containing the marker characters do
not false-positive. The dotfile bypass already excluded the intentional fenced
examples in `.claude/skills/merge-resolver/` and `.serena/memories/`, so the
content scan only ever runs against plain in-repo source. Both new branches
fail open: any filesystem error degrades to "not gated" rather than blocking.

### 8. Performance

Availability is a pure configuration check (read `.serena/project.yml` plus MCP
server config presence plus the harness LSP capability list). There is NO
outbound reachability probe, so there is no probe timeout and the sub-100ms
per-invocation budget is met by construction. The config read is computed once
and cached per session in the state file. The "configured != active" gap is
handled at the actual tool-call boundary by fail-open, not by a live probe.

### 9. Module design (deep modules, thin guards)

- `detect_lsp_provider.py`: pure, no side effects. Inputs: file path, requested
  capability (symbol-navigation or symbols-overview), repo config. Output:
  ordered available providers offering that capability for that file. The kit's
  symbol-detection regex and provider registry are quoted character-for-character
  in the module docstring with the cited path and a stricter/looser/different
  divergence section (canonical-source-mirror.md).
- `symbol_detection.py`: pure. Inputs: pattern, target. Output: is-symbol,
  is-symbol-navigable-target.
- `gate_state.py`: the only module that mutates state. Read/write/reset.
- Guards (`invoke_lsp_*.py`): thin, parse-call-decide-format only
  (clean-architecture.md).

### 10. Cross-harness via generation

Register in `.claude/settings.json` and plugin `.claude/hooks/hooks.json`;
generate `src/copilot-cli/hooks/hooks.json` via `build/scripts/generate_hooks.py`
(Copilot uses `permissionDecision`, Claude uses exit-2; the generator owns the
translation and preserves the ADR-061 shim crash policy). One canonical rule
`.claude/rules/lsp-first.md` mirrored to `.github/instructions/` and
`src/copilot-cli/instructions/` by `build/scripts/generate_rules.py`; passes
`build/scripts/validate_install_parity.py`.

## Prior Art Investigation

What exists: steering, not enforcement (#1993 re-assertion hook merged
2026-05-30; claude-model-patches; AGENTS.md BLOCKING Serena Init). No Grep/Read
navigation gate. Why steering: cheap, reversible, no deadlock. Why change now:
the 2026-05-10 drift plus the token cost of grep navigation; the native LSP tier
now gives a real tier-2 fallback the kit's single-provider model lacked. Risks:
false "available" block (mitigated by fail-open + recovery message + kill
switch); session-start friction (graduated ramp; Serena Init already warms up).

## Rationale

### Alternatives Considered

| Alternative | Why Not Chosen |
|-------------|----------------|
| BUY kit as-is | Node.js (ADR-042), global install, unconditional (deadlock), bypasses dual-registration + parity |
| STEERING-ONLY (rule + #1993) | Already exists; ~60% compliance; a third parallel steering layer is information leakage |
| FOLD into #1993 hook | #1993 is UserPromptSubmit (cannot see tool calls); enforcement needs PreToolUse + a PostToolUse tracker; wrong lifecycle to extend |
| UNCONDITIONAL hard-block (faithful port) | Post-compaction deadlock; violates fail-open |
| BUILD conditional graduated block (chosen) | Enforcement + fail-open + language-general + cross-harness + reversible via env |

### Buy-vs-Build (Quick Tier, precondition)

BUILD. BUY is structurally impossible (every axis conflicts) and the kit's core
assumption (block unconditionally) is wrong here, so even a perfect BUY must be
rewritten conditional, which is a BUILD. PARTNER/DEFER add no value (MIT, no
vendor, need is concrete per the 2026-05-10 drift). JS contract cited verbatim
per canonical-source-mirror.md.

## Consequences

### Positive

Enforced LSP-first across all LSP-navigable types; token savings on symbol
navigation; cross-harness from one source; no deadlock (fail-open + kill switch);
single-toggle rollback (`LSP_GATE_MODE=warn`).

### Negative

New enforcement surface to maintain (7 hooks, shared lib, tests); symbol-regex
false-positive tail requiring tuning; dual hook trees plus tri-tree rule mirror
parity; session-start friction until warmup + 2 nav calls.

### Architect-review dissent (recorded, overridden by user under User Sovereignty)

The 6-agent review recommended (a) shipping warn-first / measure-then-flip given
the #1993 soft layer is one day old and unmeasured, and (b) deferring per the
ADR-061 withdrawal precedent. The analyst and independent-thinker additionally
preferred exempting md/json/yaml/toml from the Read gate. The user chose to ship
hard-block enabled now, gating all 8 configured languages on the Read path,
accepting the premature-abstraction risk, mitigated by the kill switch,
fail-open, `LSP_GATE_MODE` toggle, and audit-log observability.

### Neutral

New user-scoped gate-state file (outside the tree); exit-2 carries deny semantics
here.

## Impact on Dependent Components

| Component | Type | Update | Risk |
|-----------|------|--------|------|
| `.claude/settings.json` | Direct | register 4 PreToolUse + 1 PostToolUse + 1 SessionStart; add Grep matcher | Medium |
| `.claude/hooks/hooks.json` | Direct | mirror with CLAUDE_PLUGIN_ROOT; sequence bash-grep guard after the existing Bash chain | Medium |
| `src/copilot-cli/hooks/hooks.json` | Generated | `build/scripts/generate_hooks.py`, permissionDecision, preserve shim crash policy | Medium |
| `build/scripts/generate_rules.py` / `generate_hooks.py` | Indirect | new rule + hooks flow through | Low/Med |
| `.claude/.claude-plugin/plugin.json` (+ `src/claude`, `src/copilot-cli` copies) | Direct | semver bump from current 0.4.3; verify all copies before bumping (#2118) | Low |
| `build/scripts/validate_install_parity.py` | Indirect | RULE group includes the 3 rule mirrors | Low |
| `.claude/rules/claude-model-patches.md` | Indirect | add a symbolic-over-Read line; do not stack | Low |

## Relationship to Prior ADRs

- **#1993 removed hook (`invoke_serena_reassertion.py:16-29`)**: it rejected branching on
  Serena activation state because a UserPromptSubmit hook "cannot observe whether
  Serena MCP tools were called this turn, and no other hook writes a
  Serena-activation marker file. Inventing that state would couple two components
  on a fact neither owns reliably (information leakage)... The marker-branch can
  be added later if a real activation surface is introduced." This ADR introduces
  that activation surface: a PostToolUse usage tracker that observes LSP tool
  calls and owns the state (single system-of-record, not inter-component
  inference), so the leakage concern does not apply. The #1993 stateless steering
  was later removed; this enforcement originally sat above it.
- **ADR-033 (routing gates)**: sits beside the routing gates; agent-delegation
  gating has a single owner (the pre-delegation guard) to avoid double-gating.
- **ADR-061 (hook-matcher-shims-delegate-pattern, Withdrawn 2026-05-27)**: the
  Copilot mirror follows its matcher-shim delegate pattern; its withdrawal for
  premature abstraction is the precedent behind the timing dissent recorded above.
- **ADR-008 (lifecycle hook gates)**: the fail-open scope these hooks inherit.
- **ADR-035**: exit-2 deny is the Claude-hook-semantics exemption.

## Implementation Notes

This section describes the retired enforcement layer and its deleted hook files.

Retired exit codes: 0 = allow (including fail-open and warn mode), 2 = block.
ADR-035 Claude-hook-semantics exemption, historical precedent `invoke_skill_first_guard.py`,
historical `invoke_security_gate.py`, and removed `invoke_serena_reassertion.py:38-41`. Copilot uses
`permissionDecision`; the generator translates and preserves the shim crash
policy.

Availability detection establishes eligibility from configuration only;
configured != active. The fail-open + recovery-message + kill-switch design
converts any false positive into one redirected turn, never a deadlock. State
the caveat in the detection docstring.

Deliverables: bash-grep blocked set (grep, rg, egrep, fgrep, ag, ack); git grep
allowed (regression-tested as always-allowed); sed/awk content-search deferred
(low signal); steering rule generated to all three trees; plugin.json semver
bump; 100 percent test coverage including every fail-open path; per-tier
acceptance tests and a bash-grep-runs-after-existing-Bash-chain test in
`tests/hooks/`.

Sequencing: (1) this ADR with adr-review + architect sign-off (done,
ACCEPTED-WITH-DC; see `.agents/critique/ADR-062-debate-log.md`); (2) shared lib
(detect/symbol/state) 100% tests; (3) search guards + registration + tests; (4)
Read gate + tracker + reset + registration + tests; (5) pre-delegation guard
remapped to this repo's orchestrator/agent taxonomy + tests (highest-risk,
behind the kill switch); (6) rule + mirrors + parity; (7) generate Copilot hooks;
bump plugin.json; full validation; PR.

## More Information

- Numbering-integrity bug for the maintainer (separate from this ADR): two
  `ADR-061-*.md` files existed (`-orchestrator-as-router`,
  `-hook-matcher-shims-delegate-pattern`), and an ADR-058 duplicate was noted.
  The `-orchestrator-as-router` file was renumbered to ADR-065 (issue #1857) to
  clear the ADR-061 collision; `-hook-matcher-shims-delegate-pattern` keeps 061.
  The ADR-058 duplicate and a later ADR-062 duplicate remain open.
- Quality-attribute trade: enforced symbol-first navigation vs developer friction
  / false-positive block rate.
- Top 2-year failure mode: gate-state drift across compaction, or enforcement
  aggressive enough that agents route around it. Mitigations: SessionStart reset,
  fail-open, audit.log, `LSP_GATE_MODE`, kill switch.

## References

- github.com/nesaminua/claude-code-lsp-enforcement-kit (MIT, v2.3.2): adapted source.
- GitHub Docs: Copilot CLI LSP servers + hooks (auto-LSP, permissionDecision).
- Claude Code native LSP tool (v2.0.74+): tier-2 fallback.
- Removed reference: `.claude/hooks/UserPromptSubmit/invoke_serena_reassertion.py:16-29` (#1993 precedent).
- `.claude/rules/canonical-source-mirror.md`; `.claude/rules/release-it.md`; ADR-006; ADR-035; ADR-042; ADR-008; ADR-033. <!-- orphan-ref-ignore -->

---

*GitHub Issue: TBD (tracking issue created with the implementation PR)*

## Amendment 2026-07-27

ADR-088 moved the book-derived rule cited above into the `software-engineering-library` skill. The original citation remains as historical decision text. Use these paths for current guidance:

- Current guidance now lives at `.claude/skills/software-engineering-library/references/release-it.md`.

