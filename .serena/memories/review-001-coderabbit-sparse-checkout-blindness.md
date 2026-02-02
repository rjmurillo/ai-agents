# Review: Coderabbit Sparse Checkout Blindness

## Skill-Review-001: CodeRabbit Sparse Checkout Blindness

**Statement**: CodeRabbit sparse checkout blindness causes false positives for .agents/ files

**Context**: When CodeRabbit flags .agents/ files as missing, verify existence with `git ls-tree HEAD .agents/`

**Evidence**: PR #20 had 3 false positives due to sparse checkout pattern `!.agents/**`

**Atomicity**: 95%

**Tag**: helpful for pr-comment-responder agent

---