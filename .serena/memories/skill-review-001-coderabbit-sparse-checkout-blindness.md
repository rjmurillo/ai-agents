# Skill-Review-001: CodeRabbit Sparse Checkout Blindness

**Statement**: CodeRabbit flags .agents/ files as missing due to sparse checkout pattern.

**Atomicity**: 95%

**Verify**: `git ls-tree HEAD .agents/`
