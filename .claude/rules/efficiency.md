---
paths:
  - "**/*.py"
  - "**/*.cs"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.go"
  - "**/*.rs"
  - "**/*.java"
  - "**/*.c"
  - "**/*.h"
  - "**/*.cpp"
  - "**/*.sh"
  - "**/*.ps1"
  - "**/*.sql"
  - "**/*.json"
  - "**/*.yaml"
  - "**/*.yml"
  - "**/*.proj"
  - "**/*.csproj"
  - "**/*.sln"
  - "**/*.slnx"
---

# Efficiency

Stop at the first rung that holds:

1. Needed at all? (YAGNI)
2. Already in the codebase? Reuse it.
3. Stdlib, platform, or installed dependency? Use it.
4. One line?
5. Then: minimum code that works.

No unrequested abstractions. Deletion over addition. Shortest diff wins, after
you understand the problem, not instead of it.

Bounds construction, not coverage: edge cases, error paths and tests stay
complete. Never trim trust-boundary validation, error handling that prevents
data loss, security, accessibility, or what was asked for.
