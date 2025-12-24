# Skill-Planning-003: Parallel Exploration Pattern

**Statement**: For infrastructure work, launch parallel Explore agents to gather context concurrently before planning.

**Context**: Infrastructure changes (workflows, CI/CD, multi-file). Launch before planning.

**Evidence**: Session 03: 3 parallel Explore agents reduced planning time by ~50%.

**Atomicity**: 95% | **Impact**: 9/10

**CRITICAL CAVEAT**: Planning does NOT replace validation. Session 03 had excellent planning but required 24+ fix commits due to untested assumptions.
