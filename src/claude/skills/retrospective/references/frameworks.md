# Retrospective Frameworks

Phase 0 (Data Gathering), Phase 1 (Generate Insights), and the closing activities. The
rubrics below are lifted verbatim from the canonical source agent body at
`.claude/agents/retrospective.md` (the original Phase 0, Phase 1, and Phase 6 sections).
Keep them byte-for-byte; the SKILL.md orchestration links to the activity headings here.

---

## Phase 0: Data Gathering

Gather facts before interpretation. Observation precedes diagnosis.

### Activity: 4-Step Debrief

Separate observation from interpretation.

| Step | Human Version | Agent Version | Output |
|------|---------------|---------------|--------|
| 1. Observe | "What did you see and hear?" | What tools called, outputs produced, errors occurred | Facts only |
| 2. Respond | "What surprised you? Where were you challenged?" | Where did agents pivot, retry, escalate, or block? | Reactions |
| 3. Analyze | "What insight do you have?" | What patterns emerge about agent behavior? | Interpretations |
| 4. Apply | "What would you do differently?" | What skill updates or process changes follow? | Actions |

**Template:**

````markdown
## 4-Step Debrief

### Step 1: Observe (Facts Only)
- Tool calls: [List with timestamps]
- Outputs: [What was produced]
- Errors: [What failed]
- Duration: [Time spent]

### Step 2: Respond (Reactions)
- Pivots: [Where did flow change?]
- Retries: [What was attempted multiple times?]
- Escalations: [What required human input?]
- Blocks: [What stopped progress?]

### Step 3: Analyze (Interpretations)
- Patterns: [What recurring behaviors?]
- Anomalies: [What was unexpected?]
- Correlations: [What happened together?]

### Step 4: Apply (Actions)
- Skills to update: [List]
- Process changes: [List]
- Context to preserve: [List]
````

### Activity: Execution Trace Analysis

Adapted from Timeline activity. Create a chronological picture of agent execution.

**Purpose:** See the full sequence. Identify where things stalled, accelerated, or went wrong.

**Steps:**

1. Extract execution sequence from logs, tool calls, and outputs
2. Arrange events chronologically
3. Mark significant events: starts, completions, failures, pivots
4. Annotate with energy indicators (high activity, stalled, blocked)
5. Look for patterns across the timeline

**Template:**

````markdown
## Execution Trace

| Time | Agent | Action | Outcome | Energy |
|------|-------|--------|---------|--------|
| T+0 | orchestrator | Route to analyst | Success | High |
| T+1 | analyst | Research API | Success | High |
| T+2 | analyst | Search memory | Empty result | Medium |
| T+3 | analyst | Retry with broader query | Success | Medium |
| ... | ... | ... | ... | ... |

### Timeline Patterns
- [Pattern 1]: [Description]
- [Pattern 2]: [Description]

### Energy Shifts
- High to Low at: [Point] - Reason: [Why]
- Stall points: [List]
````

### Activity: Outcome Classification

Adapted from Mad Sad Glad. Classify execution outcomes by emotional valence.

| Category | Agent Meaning | Examples |
|----------|---------------|----------|
| **Mad (Blocked)** | Failures that stopped progress | Errors, timeouts, missing dependencies |
| **Sad (Suboptimal)** | Worked but poorly | Slow, inefficient, required retries |
| **Glad (Success)** | Worked as intended | Clean execution, good outcomes |

**Template:**

````markdown
## Outcome Classification

### Mad (Blocked/Failed)
- [Event]: [Why it blocked progress]

### Sad (Suboptimal)
- [Event]: [Why it was inefficient]

### Glad (Success)
- [Event]: [What made it work well]

### Distribution
- Mad: [N] events
- Sad: [N] events
- Glad: [N] events
- Success Rate: [%]
````

---

## Phase 1: Generate Insights

Make meaning from data. Look past symptoms to find causes.

### Activity: Five Whys

Mandatory for all failures. Ask "Why?" until you reach root cause.

**Purpose:** Discover underlying conditions that contribute to an issue.

**Process:**

1. State the problem
2. Ask "Why did this happen?"
3. For each answer, ask "Why?" again
4. Repeat until you reach something outside agent control or a fixable root cause
5. Stop at 5 levels or when cause is actionable

**Template:**

````markdown
## Five Whys Analysis

**Problem:** [Statement of what went wrong]

**Q1:** Why did [problem] occur?
**A1:** [Answer]

**Q2:** Why did [A1] happen?
**A2:** [Answer]

**Q3:** Why did [A2] happen?
**A3:** [Answer]

**Q4:** Why did [A3] happen?
**A4:** [Answer]

**Q5:** Why did [A4] happen?
**A5:** [Answer]

**Root Cause:** [The actual underlying issue]
**Actionable Fix:** [What can be changed]
````

**Example:**

````markdown
**Problem:** Implementer produced code that failed tests

**Q1:** Why did the code fail tests?
**A1:** The method signature didn't match the interface

**Q2:** Why didn't the signature match?
**A2:** Implementer didn't read the interface definition

**Q3:** Why didn't implementer read the interface?
**A3:** The plan didn't specify which interface to implement

**Q4:** Why didn't the plan specify?
**A4:** Analyst didn't identify the interface in research

**Q5:** Why didn't analyst identify it?
**A5:** Search query was too narrow

**Root Cause:** Insufficient research scope
**Actionable Fix:** Add interface discovery to analyst checklist
````

### Activity: Fishbone Analysis

Use for complex failures with multiple contributing factors.

**Purpose:** Look past symptoms to identify root causes across categories.

**Agent-Specific Categories:**

| Category | What It Covers |
|----------|----------------|
| **Prompt** | Instructions, context, framing, ambiguity |
| **Tools** | Tool selection, tool usage, tool failures |
| **Context** | Missing information, stale context, memory gaps |
| **Dependencies** | External services, APIs, file system state |
| **Sequence** | Agent routing, handoff issues, ordering problems |
| **State** | Accumulated errors, drift, context pollution |

**Template:**

````markdown
## Fishbone Analysis

**Problem:** [Head of fish - the issue being analyzed]

### Category: Prompt
- [Contributing factor]
- [Contributing factor]

### Category: Tools
- [Contributing factor]

### Category: Context
- [Contributing factor]

### Category: Dependencies
- [Contributing factor]

### Category: Sequence
- [Contributing factor]

### Category: State
- [Contributing factor]

### Cross-Category Patterns
Items appearing in multiple categories (likely root causes):
- [Pattern]: Appears in [Category A] and [Category B]

### Controllable vs Uncontrollable
| Factor | Controllable? | Action |
|--------|---------------|--------|
| [Factor] | Yes | [Fix] |
| [Factor] | No | [Mitigate] |
````

### Activity: Force Field Analysis

Use when a pattern keeps recurring despite "knowing better."

**Purpose:** Identify what drives change and what restrains it.

**Template:**

````markdown
## Force Field Analysis

**Desired State:** [What we want to achieve]
**Current State:** [What happens now]

### Driving Forces (Supporting Change)
| Factor | Strength (1-5) | How to Strengthen |
|--------|----------------|-------------------|
| [Factor] | [N] | [Action] |

### Restraining Forces (Blocking Change)
| Factor | Strength (1-5) | How to Reduce |
|--------|----------------|---------------|
| [Factor] | [N] | [Action] |

### Force Balance
- Total Driving: [Sum]
- Total Restraining: [Sum]
- Net: [Driving - Restraining]

### Recommended Strategy
- [ ] Strengthen: [Driving factor]
- [ ] Reduce: [Restraining factor]
- [ ] Accept: [Factor outside control]
````

### Activity: Patterns and Shifts

Use for multi-session or multi-execution analysis. Look for trends.

**Purpose:** Find connections between facts and feelings across executions.

**Template:**

````markdown
## Patterns and Shifts

### Recurring Patterns
| Pattern | Frequency | Impact | Category |
|---------|-----------|--------|----------|
| [Pattern] | [N times] | [H/M/L] | [Success/Failure/Efficiency] |

### Shifts Detected
| Shift | When | Before | After | Cause |
|-------|------|--------|-------|-------|
| [Shift name] | [Session/Time] | [Previous state] | [New state] | [Why] |

### Pattern Questions
- How do these patterns contribute to current issues?
- What do these shifts tell us about trajectory?
- Which patterns should we reinforce?
- Which patterns should we break?
````

### Activity: Learning Matrix

Quick categorization of insights. Use when short on time.

**Categories:**

| Quadrant | Icon | Question |
|----------|------|----------|
| Top-Left | :) | What did we do well that we want to continue? |
| Top-Right | :( | What would we like to change? |
| Bottom-Left | Idea | What new ideas have come up? |
| Bottom-Right | Invest | What improvements should we invest in? |

**Template:**

````markdown
## Learning Matrix

### :) Continue (What worked)
- [Item]

### :( Change (What didn't work)
- [Item]

### Idea (New approaches)
- [Item]

### Invest (Long-term improvements)
- [Item]

### Priority Items
Top items from each quadrant:
1. [Item from Continue to reinforce]
2. [Item from Change to fix]
3. [Item from Ideas to try]
````

---

## Closing Activities

Evaluate the retrospective itself. Continuous improvement.

### Activity: +/Delta

Quick self-assessment of the retrospective process.

| Category | Questions |
|----------|-----------|
| **+ (Keep)** | What worked in this analysis? What activities produced useful insights? |
| **Delta (Change)** | What took too long? What activities yielded nothing? What should be skipped? |

**Template:**

````markdown
## +/Delta

### + Keep
- [What worked well in this retrospective]

### Delta Change
- [What should be different next time]

### Backlog Candidates
| Delta Item | Priority | Action |
|------------|----------|--------|
| [Item] | P0/P1/P2/P3 | Issue/Memory/Skip |
````

### Activity: Delta Triage

Process Delta items to capture actionable improvements. Delta items represent change requests that should not be forgotten.

**Actionable Delta Categories:**

| Category | Description | Examples |
|----------|-------------|----------|
| **Missing Documentation** | Gaps in guides, READMEs, or inline comments | "Agent didn't know about X script" |
| **Tool/Script Awareness** | Existing tools that agents fail to discover | "Should have used Y instead of Z" |
| **Process Improvements** | Workflow or protocol changes | "Need earlier validation step" |
| **Feature Requests** | New capabilities needed | "Add automated X detection" |

**Triage Protocol:**

1. **Review each Delta item** from the +/Delta output
2. **Classify as actionable** if it matches a category above
3. **Assign priority** based on impact and frequency:
   - **P0**: Blocks core functionality, recurring failures
   - **P1**: Significant impact, affects multiple sessions
   - **P2**: Normal improvement, would help efficiency
   - **P3**: Nice-to-have, low frequency
4. **Route to destination**:
   - **P0/P1**: Create GitHub issue immediately (use the `github` skill)
   - **P2/P3**: Store in backlog memory for future triage
   - **Skip**: Not actionable or duplicate of existing item

**Delta Triage Template:**

````markdown
## Delta Triage

### Actionable Items Identified

| Delta Item | Category | Priority | Destination | Reference |
|------------|----------|----------|-------------|-----------|
| [Item from Delta] | [Missing Docs/Tool Gap/Process/Feature] | P0/P1/P2/P3 | Issue #N / Memory / Skip | [Link] |

### Issues Created

| Issue | Title | Priority | Labels |
|-------|-------|----------|--------|
| #[N] | [Title] | P0/P1 | enhancement, source:retrospective |

### Backlog Items Stored

| Item | Priority | Memory File |
|------|----------|-------------|
| [Item] | P2/P3 | backlog/retro-YYYY-MM-DD-items.md |

### Skipped Items

| Item | Reason |
|------|--------|
| [Item] | [Duplicate of #X / Not actionable / Already addressed] |
````

### Activity: ROTI (Return on Time Invested)

Measure if retrospective was worth the effort.

| Score | Meaning | Action |
|-------|---------|--------|
| 0 | No benefit, wasted cycles | Stop this retrospective pattern |
| 1 | Break-even | Continue with modifications |
| 2 | Benefit > effort | Keep pattern |
| 3 | High return | Document as best practice |
| 4 | Exceptional | Extract into reusable template |

**Template:**

````markdown
## ROTI Assessment

**Score**: [0-4]

**Benefits Received**:
- [Benefit 1]
- [Benefit 2]

**Time Invested**: [Duration]

**Verdict**: [Continue | Modify | Stop]
````

### Activity: Helped, Hindered, Hypothesis

Meta-learning about the retrospective process.

| Category | Questions |
|----------|-----------|
| **Helped** | What data, tools, or context made analysis easier? |
| **Hindered** | What was missing, broken, or unclear? |
| **Hypothesis** | What should be tried next time to improve? |

**Template:**

````markdown
## Helped, Hindered, Hypothesis

### Helped
- [What made this retrospective effective]

### Hindered
- [What got in the way]

### Hypothesis
- [Experiment to try next retrospective]
````
