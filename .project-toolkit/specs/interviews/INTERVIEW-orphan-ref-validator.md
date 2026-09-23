# Interview: orphan-ref-validator

Source: issue #1939, handoff 2026-05-10, ADR-056 envelope, ADR-035 exit codes.
PRD captured in /spec session 1830 inline. See REQ/DESIGN/TASK artifacts.

Status: COMPLETE. PRD walked all 7 design-tree branches (User stories, Data model, Integrations, Failure modes, Security, Observability, Scope).

Key decisions:
- ADR-056 envelope (not ADR-051; issue had typo)
- Vendored-install via INFO+skip, not raise
- Severity: critical for skill-name+script-path+count-claim mismatches; warn for parse failures
- Out of scope: code-comment scanning, auto-fix, ADR-051 frontmatter
