---
paths:
  - ".claude/commands/spec.md"
  - ".agents/sessions/**"
  - ".agents/retrospective/**"
  - ".claude/skills/session-init/**"
  - ".claude/skills/session-end/**"
  - ".claude/rules/secret-redaction.md"
priority: high
---

# Secret and PII Redaction Before Emit

Free-text that an agent writes into a durable artifact can carry a credential, token, or PII verbatim. Halt-block `answer`/`evidence` fields, session-log work entries, retro records, PR descriptions, and metric tallies all land in git. A proposer's answer like `Alice@corp on prod-east-12.internal blocked on Bearer abc...` is then disclosed for the life of the history. This is CWE-209 (information exposure through an error/diagnostic message) and CWE-532 (insertion of sensitive information into a log).

This rule applies when you emit free-text that originated from a user answer, an external paste, or tool output into any committed artifact: spec halt blocks (Step 0 `answer`, Step 0.5 `evidence`), session logs, retros, and PR descriptions.

## MUST

1. **Redact before emit.** Before writing a free-text field that may contain a credential or PII into a committed artifact, run it through the redactor and emit the redacted form:

   ```bash
   python3 scripts/redact_secrets.py <file>      # or pipe the text on stdin
   ```

   Or, in Python, `from redact_secrets import redact; redact(text).text`. Matched token shapes (private keys, GitHub/Stripe/AWS/Slack tokens, JWTs, `Bearer` headers, emails, hex secrets >= 32 chars) become `[redacted: <reason>]`.

2. **Do not redact structured hex fields.** A field whose contract is a git SHA or content hash (e.g. `startingCommit`, `endingCommit`) legitimately holds 40 or 64 hex chars. Pass `include_hex=False` for those, or do not run the redactor over them. Redacting a real SHA corrupts the record.

3. **State that the artifact is durable.** When you author a halt block, note in the surrounding prose that the block lands in git history, so the proposer knows not to paste live secrets into answers in the first place. Redaction is a backstop, not a license to collect secrets.

## MUST NOT

1. MUST NOT emit a raw `answer`/`evidence` field that was copied from an untrusted paste without the redaction pass.
2. MUST NOT treat redaction as scanning of committed code. Use CodeQL / the security-scan skill for repository secret scanning; this rule is only the emit-time backstop for agent-authored free-text.

## References

- `scripts/redact_secrets.py`. The redactor (token-shape allowlist, `[redacted: <reason>]` output).
- `tests/test_redact_secrets.py`. Coverage for each token shape plus the SHA caveat.
- CWE-209, CWE-532. Information disclosure / sensitive data in logs.
- Issue #1975, REQ-008 Sec F4. Origin.
