# Security-Spike Fixture Corpus

Held-out corpus driving `scripts/eval/eval-agent-vs-baseline.py` for issue #1854.

## Provenance

Every fixture is `synthetic` or `paraphrased-from-public` per REQ-004 AC-4. No fixture contains real credentials, real third-party secrets, real customer data, real employee names, or copies of production code.

| Fixture | Provenance | Source notes |
|---|---|---|
| F001 | paraphrased-from-public | Path traversal pattern (CWE-22). Substantially restructured from the textbook pattern; no shared code or prose with `tests/evals/security-scenarios.json` S1. |
| F002 | synthetic | Webhook trust-boundary scenario constructed for STRIDE coverage. |
| F003 | paraphrased-from-public | Excessive data exposure (CWE-200, OWASP API3). Restructured from public OWASP API Top 10 example material; no verbatim reuse. |
| F004 | synthetic | `eval` command-injection pattern (CWE-78) constructed for the corpus. |
| F005 | synthetic | Constant-time comparison + cryptographically secure token generation. |
| F006 | synthetic | Jinja2 autoescape context to test XSS false-positive resistance. |
| F007 | synthetic | Allowlisted column name + parameterized limit for SQLi false-positive resistance. |
| F008 | synthetic | Cross-trust-boundary credential forwarding policy decision. |
| F009 | synthetic | Permissive CORS configuration whose impact depends on session-cookie strategy. |
| F010 | synthetic | Multi-step CSP / iframe / `postMessage` chain. |

No fixture duplicates `tests/evals/security-scenarios.json` content verbatim. Where a public CWE pattern motivated a fixture, the code, prose, variable names, and framing were all rewritten so the surface form differs.

## Verdict distribution

| Verdict | Fixtures | Count |
|---|---|---|
| `IDENTIFY` (with CWE) | F001, F002, F003, F004 | 4 |
| `OK` (looks suspicious, is safe) | F005, F006, F007 | 3 |
| `ESCALATE` (context-dependent) | F008, F009, F010 | 3 |

The `OK` class is a regression set for false-positive resistance — code that pattern-matches a known vulnerability shape but is correct given the surrounding context. A model that flags every f-string near a SQL keyword fails this set.

## Per-fixture rationale

### IDENTIFY (with CWE)

- **F001 — CWE-22 path traversal.** Direct concatenation of a request-body field into a filesystem path without normalization. Standard textbook case. Both variants are expected to score this; included as a sanity anchor for IDENTIFY recall.
- **F002 — STRIDE-classified webhook design.** Internal webhook with no signature, no nonce, no per-request auth. Multiple STRIDE categories apply at once (Spoofing of source, Tampering of payload, Repudiation in the audit log). See "Agent-discriminating fixtures" below.
- **F003 — CWE-200 excessive data exposure.** GET endpoint returns the raw user row including `password_hash`, `password_reset_token`, `mfa_recovery_codes`. Six-month tenure is a distractor: tenure does not validate exposure. Naive baseline often catches the headline issue (password hash exposure).
- **F004 — CWE-78 command injection.** `eval "docker run …"` with a developer-controlled tag. The deploy-pipeline framing is a distractor: developer-controlled inputs flowing into `eval` is still command injection regardless of the boundary.

### OK (false-positive resistance)

- **F005 — constant-time compare + secure RNG.** Uses `hmac.compare_digest` and `secrets.token_urlsafe`. A reviewer who pattern-matches "token comparison" without reading the function may flag `==`-style issues that are not present. The correct verdict is `OK`.
- **F006 — Jinja2 autoescape context.** A function returning raw HTML triggers an XSS reflex, but the calling template applies `| escape` and the project enables global autoescape. The function's output is escaped before reaching the browser. Correct verdict is `OK`.
- **F007 — allowlisted ORDER BY column.** F-string interpolation of `sort_by` into SQL pattern-matches CWE-89 reflexively, but `sort_by` is checked against a fixed `ORDER_COLUMNS` allowlist and the limit is bounded and parameterized. Correct verdict is `OK`.

### ESCALATE (context-dependent)

- **F008 — cross-trust-boundary credential forwarding.** Forwarding our own bearer token to a third-party API that retains request bodies for 30 days. The product team's risk framing is incomplete (bearer leak is one issue; introducing a new trust boundary for credentials is another; lack of opt-out for regulated tiers is a third). The right answer is `ESCALATE` because the decision is a policy decision that requires the security team, not a code-level fix. See "Agent-discriminating fixtures" below.
- **F009 — permissive CORS + session-cookie strategy.** `Access-Control-Allow-Origin: *` is alarming, but the actual blast radius depends on whether the API uses cookies or bearer tokens, and on whether the cookies are `SameSite`. The case is not resolvable from the code alone; the right move is `ESCALATE` to ask the missing question.
- **F010 — CSP + iframe + postMessage chain.** Three independently reasonable choices (no CSP, embeddable in iframes, `postMessage` listener accepting any origin) compose into clickjacking + cross-frame DOM-XSS. The right answer is `ESCALATE` to require a threat-model walk before merging. See "Agent-discriminating fixtures" below.

## Agent-discriminating fixtures

The PRD requires at least three fixtures whose correct verdict requires knowledge encoded in the agent's system prompt — knowledge a deliberately naive baseline ("Review the following input. Respond with one word: IDENTIFY, OK, or ESCALATE.") cannot supply.

| Fixture | Why the naive baseline cannot score correctly | What the agent prompt provides |
|---|---|---|
| **F002** | Naive baseline lacks STRIDE vocabulary. It may flag the missing signature as a generic auth issue, but is unlikely to classify Spoofing + Tampering + Repudiation simultaneously, which the assertion requires. | Security agent prompt encodes STRIDE as a first-class threat-modeling framework; output is expected to apply STRIDE labels by name. |
| **F008** | Naive baseline lacks the project's escalation policy. It is likely to either rubber-stamp the product team's risk framing (`OK`) or flag a generic "token leak" issue (`IDENTIFY`). The right verdict is `ESCALATE` because the decision is a policy decision requiring security-team review, not a code-level fix. | Security agent prompt encodes the project's escalation rule: any change that introduces a new credential-trust-boundary requires an explicit ESCALATE verdict so a human reviews the policy change. |
| **F010** | Naive baseline can score any one of the three observations (no CSP, iframable, open `postMessage` listener) but is unlikely to compose them into a single threat chain. It will most likely produce one IDENTIFY for one observation and ignore the rest. The chain only emerges when the reviewer holds all three observations in working memory and applies threat-modeling discipline. | Security agent prompt directs the agent to enumerate threats holistically and to produce ESCALATE when multiple weak observations chain into a high-impact threat. |

### Pilot gate status

R1 mitigation in PLAN-1854 requires running each agent-discriminating fixture through both variants live (~2 API calls per fixture) before T4-5 to confirm the naive baseline fails them. Spending real money requires explicit user authorization, so the pilot gate is **deferred for user execution before T4-5**.

| Fixture | Pilot gate status | What the gate would test |
|---|---|---|
| F002 | pending pilot | Confirm baseline does not produce STRIDE labels matching the assertion regex `(?i)(spoof\|tamper\|repudiat)`. |
| F008 | pending pilot | Confirm baseline does not produce verdict `ESCALATE` (i.e. baseline rubber-stamps or mis-IDENTIFIES). |
| F010 | pending pilot | Confirm baseline does not produce verdict `ESCALATE` (i.e. baseline catches at most one of the three observations and does not compose). |

If a pilot run shows the baseline passing an agent-discriminating fixture, that fixture must be redesigned before T4-5. Procedure is captured in TASK-004 T4-4a.

## Held-out criterion

Per REQ-004 §Cluster B, "held-out" means the fixtures were not used in the prior agent eval (notably ADR-057's prompt-change scenarios at `tests/evals/security-scenarios.json`). It does NOT mean the fixtures are absent from the model's training data. Public CWE descriptions paraphrased into fixtures may have been seen by the model in training. The spike tests prompt specialization on familiar territory, not generalization to novel inputs.

## Tags

Tags follow the validator regex `^[a-z0-9][a-z0-9_:-]{0,63}$`. They are advisory metadata for filtering reports; they do not gate scoring. Tag families used here:

- `cwe-<id>`: the CWE the fixture targets (e.g. `cwe-22`).
- `owasp-<code>`: the OWASP Top 10 entry (e.g. `owasp-a01`).
- `stride`: STRIDE-classified threat in scope.
- `verdict-<value>`: the expected verdict, lowercased.
- `false-positive-resistance`: the fixture is safe code that pattern-matches a vulnerability shape.
- `agent-discriminating`: the correct verdict requires knowledge only the agent's system prompt encodes.

## Cross-references

- `.agents/specs/requirements/REQ-004-agent-eval-harness-spike.md` — AC-4 corpus integrity rules
- `.agents/specs/design/DESIGN-004-agent-eval-harness-spike.md` — §5.2 Fixture validator, §5.3 assertion shape
- `.agents/specs/tasks/TASK-004-agent-eval-harness-spike.md` — T4-4a/b/c sub-task split
- `.agents/plans/active/PLAN-1854-agent-eval-harness-spike.md` — R1 pilot-gate mitigation
- `evals/README.md` — directory landscape vs. `tests/evals/`
