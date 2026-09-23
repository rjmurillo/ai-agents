<!-- GENERATED -- DO NOT EDIT -->
<!-- Source: .claude/skills/review/references/agent-safety.md -->
<!-- Run: python3 build/scripts/generate_pr_quality_prompts.py -->
<!-- CONTEXT_MODE: ${CONTEXT_MODE} (full|summary|partial); PASS forbidden when not full, per AI-REVIEW-MODEL-POLICY.md -->

# Agent Safety Review Task

You are reviewing a pull request for agent-safety risk: changes that alter how an autonomous agent behaves, what it can run, or what guardrails it must clear before acting.

## Context Mode Enforcement (REQUIRED)

The CI harness prepends a `CONTEXT_MODE: [full|summary|partial]` header to the
context it sends you. Read that header before you decide a verdict. It tells you
how much of the diff you actually received.

- `full`: the complete diff is present. `PASS`, `WARN`, and `CRITICAL_FAIL` are
  all permitted on the merits.
- `summary`: only a file list or stat-only summary is present (the PR exceeded
  the diff-size limit). You did not see the line-level changes.
- `partial`: only a bounded slice of the diff is present (for example, the first
  N lines). You did not see the rest.

When `CONTEXT_MODE` is not `full`, you MUST NOT emit `PASS`. A PASS asserts
evidence you do not have. Emit `WARN` (or a higher-severity verdict if the
available metadata already shows a problem), state that context was
`summary` or `partial`, and name the specific evidence you would need to clear
the PR. Treat a missing or unrecognized `CONTEXT_MODE` value as not `full`.

This is a manipulation-resistance control: an adversary can craft a PR that
trips summary mode to hide a change behind a stat-only context. Forbidding PASS
keeps that change from passing on absent evidence. See
`.agents/governance/AI-REVIEW-MODEL-POLICY.md` ("CONTEXT_MODE Header (REQUIRED)").

## Grounding Rules

- Do NOT claim software versions are "beta", "unstable", or "unreleased" based on training data. Your training data has a cutoff and may be outdated.
- Do NOT claim tools (ruff, mypy, pytest, etc.) lack support for a version unless you have concrete evidence from the diff itself.
- For dependency update PRs: evaluate the diff for internal consistency, not external ecosystem assumptions. If CI tests pass, the tooling works.
- Base findings on what the code shows, not on recalled release schedules.

## When This Axis Applies

Apply the focus areas below when the diff modifies an agent prompt or template, a skill (`SKILL.md` or its scripts), or a lifecycle hook (SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop). When `CONTEXT_MODE` is `full` and the change does not touch agent behavior, tool access, or a guardrail, this axis is not material and may emit `PASS`. When `CONTEXT_MODE` is `summary` or `partial`, emit `WARN` instead and state that line-level evidence is missing.

## Reference Material

Ground findings in the project's agent-safety artifacts. All paths are under `.claude/` and ship with vendored installs:

- `security-scan` skill: detects CWE-78 (command injection) regex patterns in Python, PowerShell, Bash, and C# before submission. Invoke when a skill script or hook builds a shell command from input.
- `.claude/skills/security-scan/references/autonomous-execution-guardrails.md`: the autonomous-execution guardrails reference. Use it to check that a change does not let an agent skip validation, make autonomous "won't fix" dismissals, or treat thread resolution as addressing a concern.
- `.claude/skills/security-scan/references/agent-guardrails-template.md`: the Four Laws of agent safety (declared scope, verify before destructive ops, preserve audit trail, escalate when uncertain). Use it to name which law a change that widens agent capability fails to honor.
- `.claude/skills/security-scan/references/agent-memory-inference-leakage.md`: the unauthorized-memory-inference reference. Use it on memory write paths to check that a write is factual capture, not a behavioral inference or a standing order the user did not authorize.
- `threat-modeling` skill: OWASP four-question framework and STRIDE. Invoke when a change adds attack surface to an agent path (new tool access, a new input the agent acts on, a new external call).

## Analysis Focus Areas

### 1. Tool and Permission Surface

- Does the change grant an agent new tool access or broader permissions than the task needs?
- Are new capabilities scoped to the minimum the workflow requires?
- Could a prompt or skill change let an agent invoke a destructive or irreversible operation without confirmation?

### 2. Command Construction (CWE-78)

- Does a new or changed skill script or hook build a shell command from agent or user input?
- Is the input passed as separate arguments rather than interpolated into a command string?
- Would the `security-scan` skill flag this path? If you cannot tell, recommend running it.

### 3. Autonomous-Execution Guardrails

- Does the change weaken a pre-merge gate (orchestrator, critic, QA, security review)?
- Could it let an agent mark a comment "won't fix" without the required analysis, or resolve a thread without a substantive reply?
- Does it optimize for completion in a way that bypasses validation?

### 4. Prompt and Instruction Integrity

- Does a prompt change introduce a contradictory or ambiguous instruction an agent could exploit to skip a protocol?
- Is there a prompt-injection surface (the agent treats untrusted content as instructions)?
- Are confirmation gates and STOP points preserved?

### 5. Threat Surface

- Does the change add a new external integration point or a new untrusted input the agent acts on?
- If it adds meaningful attack surface, recommend a `threat-modeling` pass and name the assets at risk.

## Output Requirements

Provide your analysis in this format:

### Agent Safety Assessment

| Aspect | Rating (1-5) | Notes |
|--------|--------------|-------|
| Tool/Permission Scope | | |
| Command Safety | | |
| Guardrail Integrity | | |
| Prompt Integrity | | |
| Threat Surface | | |

**Overall Agent Safety Score**: X/5

### Findings

| Severity | Category | Finding | Location | Recommendation |
|----------|----------|---------|----------|----------------|
| Critical/High/Medium/Low | [category] | [description] | [file:line] | [fix] |

### Recommendations

1. [Specific safety improvements; cite the autonomous-execution guardrails reference, `security-scan`, or `threat-modeling` where relevant]

### Verdict

Choose ONE verdict:

- `VERDICT: PASS` - Change does not weaken agent safety
- `VERDICT: WARN` - Minor safety gaps that should be addressed
- `VERDICT: CRITICAL_FAIL` - Change removes a guardrail or opens a command-injection or escalation path

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [Brief explanation]
```

## Critical Failure Triggers

Automatically use `CRITICAL_FAIL` if you find:

- A skill script or hook that builds a shell command from unsanitized input (CWE-78 vector)
- A change that removes or bypasses a pre-merge gate (orchestrator, critic, QA, or security review)
- A prompt change that lets an agent make autonomous "won't fix" or dismissal decisions without the required review
- New tool access or broadened permissions with no stated need
- A prompt-injection surface where untrusted content is treated as agent instructions

## Structured JSON Output

After your human-readable analysis, emit a fenced JSON block matching the inline schema below (a JSON Schema for this output also lives at `.agents/schemas/pr-quality-gate-output.schema.json` in projects that ship it; vendored installs do not):

```json
{
  "verdict": "PASS|WARN|CRITICAL_FAIL",
  "message": "One sentence summary",
  "agent": "agent-safety",
  "timestamp": "ISO 8601",
  "findings": [
    {
      "severity": "critical|high|medium|low",
      "category": "tool-scope|command-injection|guardrail|prompt-integrity|threat-surface",
      "description": "What was found",
      "location": "file:line",
      "recommendation": "Suggested fix"
    }
  ]
}
```

## Output Schema

Each finding MUST be reported with these structured fields:

- **severity**: one of `critical`, `high`, `medium`, `low` (matches the JSON schema field used in the body section above; treat `critical` as a CRITICAL_FAIL trigger and `high` as a WARN trigger). Maps to verdict
  precedence: any `critical` raises the axis verdict to `CRITICAL_FAIL`.
- **category**: short keyword identifying the failure class, drawn from the
  axis `category` enum in the JSON schema above (e.g. `tool-scope`,
  `command-injection`, `guardrail`). Used for clustering.
- **location**: `file:line` (or `file:line-range`). Required for every finding.
- **recommendation**: one-sentence imperative fix the author can act on.
Top-level (NOT per-finding; the schema rejects `verdict` inside
`findings` items; `additionalProperties: false` is set on the finding
object):

- **verdict**: one of `PASS`, `WARN`, `CRITICAL_FAIL`. Choose one of these
  three explicitly; do NOT emit `UNKNOWN` yourself. `UNKNOWN` is reserved
  for `/review`'s parser when an axis output cannot be parsed
  (`extract_verdict` returns `UNKNOWN` on no match); it is never an authored
  verdict. The axis-level verdict is the highest-severity outcome across the
  findings list (any `critical` severity -> CRITICAL_FAIL; any `high` ->
  WARN; otherwise PASS).

The response MUST contain a final line matching the regex
`(?m)^\s*(?i:(?:Final\s+)?Verdict):\s*\[?(PASS|WARN|CRITICAL_FAIL|REJECTED|FAIL|NEEDS_REVIEW|NON_COMPLIANT|COMPLIANT|PARTIAL|UNKNOWN)(?![|A-Z_])\]?` (label is case-insensitive; tokens are case-sensitive uppercase).
This line is parsed by `extract_verdict` in
`.claude/lib/ai_review_common/verdict.py` and consumed by `merge_verdicts`
when `/review` aggregates across all axes.

Refs REQ-008-01, REQ-008-05 (issue #1934).

<!-- vendor-portability: declared. This review axis cites the model policy under .agents/governance/ and the output schema under .agents/schemas/ (both upstream-only; the file states inline that vendored installs do not ship the schema, so the JSON contract is documented inline). The verdict parser at .claude/lib/ai_review_common/verdict.py ships in the vendor install and works. None of these block the axis. Issue #2050. -->
