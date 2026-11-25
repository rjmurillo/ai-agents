# ADR-059 claims ledger, 2026-11-25

Claims in the 2026-11-25 amendment or edited sentences of ADR-059. Commands ran in the working tree of branch `ci/delete-agent-env-jobs` at head `7cfb378901` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` on base `e74b842786`.

| Claim | Kind | Command | Result |
|---|---|---|---|
| pr-review-config.yaml lines 103-109 hold the verify_config_only_exits table | path | `sed -n '103,109p' src/claude/skills/pr-review/pr-review-config.yaml \| cut -c1-60` | VERIFIED: verify_config_only_exits: /     - exit_code: 0 /       meaning: "Config and the tracked files its scripts-map /     - exit_code: 2 /       meaning: "T |
| The old range 116-122 no longer holds the table | path | `sed -n '116,122p' src/claude/skills/pr-review/pr-review-config.yaml \| grep -c verify_config_only_exits` | VERIFIED: 0 |
