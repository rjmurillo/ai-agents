# Skill Sidecar Learnings: agent-prompt-optimization

**Last Updated**: 2026-04-11
**Sessions Analyzed**: 1 (feat/agent-prompt-optimization branch)
**Related**: knowledge-integration-observations.md (PR #1614, same refs pattern but for skills)

## Constraints (HIGH confidence)

### 1. Agents are prompts, not skill directories

Agents in `.claude/agents/*.md` are system prompts loaded at invocation. They have NO `references/` mechanism like skills do. Any persona-specific knowledge that differentiates one agent from another must go inline in the prompt itself.

Skills load demand-loaded content via progressive disclosure (SKILL.md triggers, references/*.md loaded only when needed). Agents do not.

**Implication**: Wiki enrichment and domain knowledge must be compressed and inlined for agents. Do not design agent enrichment around a references/ pattern.

**Source**: User correction 2026-04-11 - "agents don't themselves have reference material, they are just prompts. so if we want specialization for that particular personality, then it needs to go inline"

### 2. Do not merge agents to reduce count

Merging agents destroys adversarial specialization. critic/security/architect/independent-thinker encode different refusal patterns, risk thresholds, and blind spots. A merged "reviewer" agent converges toward lowest-common-denominator review behavior.

The right lever for reducing agent bloat is **slimming prompts**, not consolidating personas. Best-performing agents in this repo are narrow and lean (high-level-advisor 8KB = 4.83, adr-generator 7KB = 4.67).

**Implication**: Reject "consolidate 23 to 5-7" framing. Keep all agents. Reduce bytes, not files.

**Source**: /autoplan CEO+Eng review 2026-04-11, 12/12 consensus confirmations from Codex + Claude subagent across both phases. User approved revised direction (option A).

### 3. Unconditional mandates are the primary failure mode

Absolute rules like "MUST load memories first", "ask questions FIRST", "Read the plan before reviewing" cause agents to refuse work when the required context is absent. This is the dominant failure pattern in bloated agent prompts.

**Observed failures**:
- explainer: "ask first, write second" mandate → refused to produce PRDs on Clear problems
- implementer: "MUST load strategic memories" → refused to start work when memories unavailable
- critic: "Read the plan. Read the code it references" → demanded more documentation instead of reviewing prompt text

**Implication**: Always make behavior conditional on problem complexity. Use explicit decision tables (Clear/Complicated/Complex/Chaotic → expected behavior).

**Source**: 3 independent failures observed and fixed in this session

### 4. The "produce when you can, ask when you must" template

A decision table mapping situation → behavior works across all ask-first agents:

| Situation | Behavior |
|-----------|----------|
| Standard feature with known patterns | Produce directly with best-practice defaults |
| Concept explanation, documentation | Produce directly with concrete examples |
| Vague or ambiguous request | Push back with specific clarifying questions |
| Novel feature with multiple stakeholders | Ask clarifying questions first |
| External-facing or security-sensitive | Ask about auth/scope/constraints first |

**Data**: Applied to explainer (+2.31), spec-generator (+1.20), analyst (+0.98), all measured improvements.

**Implication**: Use this template when slimming any agent with an "always ask first" pattern.

**Source**: Consistent multi-data-point results from slimming work

### 5. Missing information is a finding, not a blocker

Review/judgment agents (critic, analyst, quality-auditor, security) must explicitly permit critiquing available information and flagging gaps as findings. The slim must say so directly.

**Data**: critic v1 slim without this mandate regressed from 3.42 to 2.81. v2 with "Missing information is a finding, not a blocker" fixed it to 4.25.

**Implication**: For every review agent, include explicit permission to judge incomplete information. State that refusing to review = failure.

**Source**: critic v1 regression incident 2026-04-11

## Preferences (MED confidence)

### Cynefin-aware eval dimensions are essential

A 3-dimension eval (role_adherence, actionability, quality) produces misleading signals for agents whose behavior should vary with problem complexity. Adding a 4th "appropriateness" dimension tied to Cynefin classification exposes real failures.

**Data**: explainer slim v1 scored 2.92 on 3-dim eval (looked like progress from 2.25 baseline) but 2.44 on 4-dim Cynefin-aware eval (revealed still-broken state). 4-dim eval prevented a false-positive commit.

**Implication**: When evaluating agents that do conditional reasoning (ask vs produce, explore vs commit), the eval framework must have a dimension that measures context-appropriate behavior.

### Size and agent quality are inversely correlated

Data from baseline assessment of 23 agents + post-slim of 7:
- Best agents: 7-9KB (high-level-advisor 4.83, adr-generator 4.67)
- Worst agents: 45-69KB (implementer 2.83, orchestrator 3.33)
- Post-slim 7 agents: all 5-8KB, all scoring 4.0+

**Targets**: 5-8KB per agent, hard cap 16KB. Split if larger.

**Implication**: Aggressive trimming of duplicated boilerplate (style guide, activation profile, memory protocol, handoff protocol) is nearly always correct.

### Boilerplate across all 23 agents

These sections appear in most/all agents and are candidates for extraction to shared passive context (AGENTS.md):

- Style Guide Compliance (identical in all)
- Activation Profile (keyword lists - routing metadata, not behavior)
- Claude Code Tools (tool access declarations)
- Memory Protocol (Serena search patterns)
- Handoff Protocol (return to orchestrator language)

Slimming these out saved 40-89% per agent without any capability loss.

## Edge Cases (MED confidence)

### Tagging eval prompts with Cynefin classification

For agents with conditional behavior, each eval prompt must be tagged with its complexity. Without tags, the scorer cannot judge whether the agent picked the right mode.

Example: spec-generator's 4 test prompts include 1 complicated (standard password reset) + 3 complex (share reports, make faster, webhooks). The agent should produce directly on the complicated one and ask questions on the complex ones. Scoring without tags treats all 4 uniformly and rewards the wrong behavior.

**Implication**: When adding new agents to eval-agents.py, always include complexity tags.

### tee | grep pipeline block-buffering

Long-running background scripts piped through `tee | grep` block-buffer stderr, making progress invisible through the grep output even as the log file is actively growing. Read the log file directly for accurate progress.

**Implication**: Monitor file modification time (`stat -c '%Y'`) and file size, not grep output, to assess liveness.

### Skill vs agent architectural distinction

From Miessler, Anthropic platform docs, and Anthropic context engineering guide:

- **Skills** = domain containers with progressive disclosure (SKILL.md + demand-loaded references/)
- **Workflows** = task procedures inside skills
- **Agents** = parallel workers / personas that invoke skills
- Decision rule: "what should I do next?" = agent. "how do I do this consistently?" = skill.

This is THE fundamental distinction for knowledge placement. Skills can afford rich content because it loads on demand. Agents cannot.

**Implication**: Use skills for reusable capability packages. Use agents for persona definitions. Never conflate.

## Notes for Review (LOW confidence)

- Consider whether task-decomposer, milestone-planner, roadmap would also benefit from the same slim pattern even though they scored above 3.5 baseline
- Research whether "produce when you can, ask when you must" template should be extracted into a shared agent fragment referenced by all ask-first agents
- Investigate whether the 4.0 floor we achieved post-slim is actually a ceiling imposed by the LLM-as-judge scoring framework rather than the actual agents
- Consider publishing eval-agents.py with Cynefin-aware scoring as a reusable tool for other agent-based projects
