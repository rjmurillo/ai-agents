---
name: cva-analysis
version: 1.0.0
description: Systematic abstraction discovery using Commonality Variability Analysis. Build matrix of what varies vs what's constant, then let patterns emerge. Prevents wrong abstractions by deferring pattern selection until requirements are analyzed. Use when facing multiple similar requirements and need to discover natural abstractions.
model: claude-sonnet-4-5
license: MIT
metadata:
  tier: 3
  timelessness: 9
  domains:
    - design
    - architecture
    - patterns
    - abstraction-discovery
  author: Multi-Paradigm Design (Coplien 1999), adapted for modern engineering
---

# CVA Analysis - Discover Natural Abstractions

Commonality Variability Analysis (CVA) is a systematic technique for discovering abstractions from requirements. Instead of choosing patterns first, you build a matrix showing what's COMMON (constant across use cases) vs what VARIES (differs between cases). Patterns emerge naturally from the matrix structure.

**Core Insight**: Rows (commonalities) map to Strategy pattern. Columns (variabilities) map to Abstract Factory pattern. The matrix reveals whether abstraction is needed at all.

**From CLAUDE.md Design Philosophy**: "Greatest vulnerability is wrong or missing abstraction." CVA prevents wrong abstractions by making pattern selection evidence-based, not intuition-based.

## Triggers

Activate CVA when you encounter:

- `discover abstractions for [domain]`
- `run CVA analysis on [requirements]`
- `commonality variability analysis`
- `prevent wrong abstraction`
- `what patterns emerge from [use cases]`

## Quick Reference

| Phase | Purpose | Input | Output | Time |
|-------|---------|-------|--------|------|
| 1. Identify Commonalities | Find what's constant across ALL use cases | Use cases/requirements | List of commonalities (matrix rows) | 5-10 min |
| 2. Identify Variabilities | Find what VARIES between use cases | Commonalities + use cases | List of variabilities (matrix columns) | 5-10 min |
| 3. Build Matrix | Visualize commonality × variability relationships | Rows + columns | CVA matrix (Markdown table) | 5-15 min |
| 4. Map to Patterns | Translate matrix structure to design patterns | Completed matrix | Pattern recommendations + rationale | 5-10 min |
| 5. Validate & Handoff | Validate choices, route to appropriate agents | Pattern recommendations | Validation report + ADR stub | 5-10 min |

**Total Time**: Quick (15 min), Standard (30 min), Deep (60 min)

## When to Use

**Use CVA when:**

- Facing 2+ similar but varying requirements
- About to select a design pattern (validate with CVA first)
- Refactoring code with duplicated logic
- Need evidence for abstraction decisions (ADR material)
- Team debates whether to abstract (make implicit explicit)

**Do NOT use CVA when:**

- Only 1 use case exists (wait for 2nd per YAGNI)
- Pattern is obvious and uncontested (don't over-analyze)
- Time-critical decision (<15 min available, use intuition)
- Requirements are still highly uncertain (premature)

## Process

### Phase 1: Identify Commonalities

**Purpose**: Establish what is ALWAYS true across ALL use cases. This becomes the stable foundation.

**Steps**:

1. **Start with first use case**: What does it need? List all capabilities.
2. **Add second use case**: What do BOTH need? Extract shared capabilities.
3. **For each additional use case**: What do ALL cases need?
4. **Document as matrix ROWS**: Each row is a commonality present in every use case.

**Example** (Payment Processing):

```text
Use Case 1: Credit card payment
Use Case 2: PayPal payment
Use Case 3: Bank transfer

Commonalities (ALL cases need):
- Validate payment amount
- Authorize transaction
- Record transaction
- Handle transaction errors
```

**Verification**:

- [ ] Each commonality appears in ALL use cases
- [ ] At least 2 commonalities identified (if only 1, reconsider scope)
- [ ] Commonalities are capabilities/behaviors, not implementation details

**Failure Handling**: If no commonalities exist, use cases may be unrelated. Analyze separately or reconsider grouping.

---

### Phase 2: Identify Variabilities

**Purpose**: Discover what VARIES between use cases. This reveals extension points where Strategy or Abstract Factory patterns may apply.

**Steps**:

1. **For each commonality, ask**: "How does this vary across cases?"
2. **List variations**: Document different implementations for each commonality.
3. **Document as matrix COLUMNS**: Each column is a variation.
4. **Optional**: Add "Future Variations" column for anticipated changes.

**Example** (continuing Payment Processing):

```text
Commonality: Validate payment amount

Variations:
- Credit Card: Check card limit, validate CVV
- PayPal: Check PayPal balance, validate account status
- Bank Transfer: Check account balance, validate routing number

Commonality: Authorize transaction

Variations:
- Credit Card: Contact card issuer API
- PayPal: OAuth flow with PayPal
- Bank Transfer: ACH authorization
```

**Verification**:

- [ ] Each variability differs in at least 2 use cases
- [ ] Variations are concrete implementations, not abstract
- [ ] If ZERO variability (all cells identical), abstraction may not be needed

**Failure Handling**: If all variability (no commonality), design may be too broad. Narrow scope or reconsider.

---

### Phase 3: Build CVA Matrix

**Purpose**: Create visual artifact showing commonality × variability relationships. Makes implicit design explicit for team discussion.

**Steps**:

1. **Create Markdown table**: Commonalities as rows, variabilities as columns
2. **Fill each cell**: Concrete implementation for that commonality/variability pair
3. **Highlight patterns**: Where cells are identical (sharing opportunity), where they differ (extension point)
4. **Optional**: Export to Mermaid diagram using `scripts/export-cva-matrix.py`

**Example Matrix**:

| Commonality | Credit Card | PayPal | Bank Transfer |
|-------------|-------------|--------|---------------|
| Validate amount | Check card limit, CVV | Check PayPal balance, account | Check account balance, routing |
| Authorize | Card issuer API | PayPal OAuth | ACH authorization |
| Record | Log to CardTransactionDB | Log to PayPalTransactionDB | Log to BankTransactionDB |
| Handle errors | Card decline codes | PayPal error codes | ACH rejection codes |

**Interpretation**:

- **Row perspective (Strategy pattern)**: "Authorize" varies across payment methods → Strategy pattern for authorization
- **Column perspective (Abstract Factory pattern)**: Each payment method has consistent set of operations → Abstract Factory for payment providers
- **Cell perspective**: "Log to *TransactionDB" shows common pattern with variation → Template Method or Strategy

**Verification**:

- [ ] Matrix is at least 2×2 (minimum for pattern discovery)
- [ ] All cells are filled (no empty cells)
- [ ] Patterns becoming visible (some cells identical, some divergent)

**Failure Handling**: If matrix shows no useful patterns, abstraction may not be beneficial. Document rationale for concrete implementation.

---

### Phase 4: Map to Patterns

**Purpose**: Translate matrix structure to design patterns. Patterns EMERGE from analysis, not imposed.

**Steps**:

1. **Read ROWS (commonalities)**:
   - If each row has different implementations across columns → **Strategy pattern** (vary algorithm for same operation)
   - Example: "Authorize" row has 3 implementations → `IAuthorizationStrategy`

2. **Read COLUMNS (variabilities)**:
   - If each column represents a coherent family of implementations → **Abstract Factory pattern** (vary implementations across product families)
   - Example: "Credit Card" column has consistent set of card-specific operations → `CreditCardPaymentFactory`

3. **Check for multidimensional variability**:
   - If BOTH rows AND columns vary independently → Combination patterns or reconsider scope
   - Start with dominant axis (more variance), note multidimensional case in Extension Points

4. **Document recommendations**:
   - Which pattern(s) fit?
   - WHY do they fit? (cite matrix structure)
   - What are alternatives? (if any)

**Example Output**:

```markdown
## Pattern Recommendations

### Primary: Abstract Factory Pattern

**Rationale**: Each payment method (Credit Card, PayPal, Bank Transfer) requires a coherent family of related operations. Matrix columns show consistent product families.

**Implementation**:
```csharp
public interface IPaymentFactory {
    IAmountValidator CreateValidator();
    ITransactionAuthorizer CreateAuthorizer();
    ITransactionRecorder CreateRecorder();
    IErrorHandler CreateErrorHandler();
}

public class CreditCardPaymentFactory : IPaymentFactory {
    // Concrete implementations from "Credit Card" column
}
```

**Alternative**: Strategy pattern per row (4 separate strategies). Rejected because operations are not independent - they share payment method context. Factory keeps cohesion.

```

**Create ADR stub** for architect agent:

```markdown
# ADR-XXX: Payment Processing Abstraction

## Context
CVA matrix revealed 3 payment methods with 4 common operations, each varying by method.

## Decision
Use Abstract Factory pattern with `IPaymentFactory` per method.

## Rationale
- Matrix columns show coherent product families
- Operations share payment method context (not independent)
- New payment methods extend without modifying existing

## Alternatives Considered
- Strategy per operation: Rejected (operations not independent, loses cohesion)
- No abstraction: Rejected (3 methods with clear variations justify abstraction per YAGNI threshold)
```

**Verification**:

- [ ] Recommended patterns align with matrix structure
- [ ] Rationale explains WHY patterns fit (cites matrix evidence)
- [ ] Edge cases addressed (single use case → don't abstract, all variability → reconsider)
- [ ] ADR stub created with decision rationale

**Failure Handling**: If no patterns fit cleanly, document rationale for concrete implementation. Abstraction may not be warranted yet.

---

### Phase 5: Validation and Handoff

**Purpose**: Validate abstraction choices and route to appropriate agents for review.

**Steps**:

1. **Run validation script**:

   ```bash
   python3 .claude/skills/cva-analysis/scripts/validate-cva-matrix.py cva-matrix.md
   ```

   - Checks: ≥2 rows, ≥2 columns, all cells filled, patterns suggested
   - Exit code 0 = pass, 10 = validation failure, 1 = error

2. **Route to decision-critic** (if abstraction recommended):

   ```bash
   # Use decision-critic skill to validate abstraction choice
   /decision-critic "Validate Abstract Factory pattern for payment processing per CVA analysis"
   ```

3. **Route to architect agent** (for ADR creation):

   ```bash
   # Hand off ADR stub to architect agent
   Task(subagent_type="architect", prompt="Create ADR from CVA analysis stub")
   ```

4. **Document reassessment triggers**:

   ```markdown
   ## Reassessment Triggers

   Re-run CVA when:
   - 3+ new payment methods added
   - Major architectural shift (e.g., microservices split)
   - Performance issues with current abstraction
   - Team feedback: abstraction is too complex or not pulling weight
   ```

**Outputs**:

- Validation report (pass/fail with specific issues)
- Handoff to decision-critic and/or architect agent
- Reassessment triggers documented

**Verification**:

- [ ] Validation script exits with code 0
- [ ] Decision-critic review completed (if abstraction recommended)
- [ ] Reassessment triggers are specific, not vague

**Failure Handling**: If validation fails, return to earlier phase based on issue:

- Missing commonalities → Phase 1
- Incomplete matrix → Phase 3
- Pattern mismatch → Phase 4

---

## Anti-Patterns

| Anti-Pattern | Why Bad | Example | Instead |
|--------------|---------|---------|---------|
| **Pattern-First Design** | Violates CVA principle: patterns emerge, not imposed. Leads to wrong abstractions. | Decide "we need Strategy pattern" BEFORE running CVA | Run CVA first. Let matrix reveal pattern. If no pattern emerges, abstraction may not be needed. |
| **Forcing Abstractions** | Creates complexity without benefit. Worse than no abstraction per CLAUDE.md. | CVA shows no variability, but create Strategy anyway "for future" | When CVA shows no variability, explicitly document decision NOT to abstract. Revisit when variability emerges. |
| **Skipping Matrix Visualization** | Loses pedagogical and collaborative benefits. Matrix makes assumptions explicit. | Identify commonalities/variabilities mentally, skip matrix, jump to pattern | Always create visual matrix (Markdown table minimum). Use for team review, ADR rationale. |
| **Analysis Paralysis** | CVA is a tool, not an end. Over-analysis wastes time. | Spend 3 hours on CVA for 2 simple use cases | Use tiered approach: Quick (15 min) for simple, Standard (30 min) moderate, Deep (60 min) architectural. Set timer. |
| **Ignoring Temporal Dimension** | Today's constant may be tomorrow's variable. | CVA assumes "currency" constant (USD only). 6 months later, need multi-currency. | Include "Future Variations" column for anticipated changes. Balance YAGNI with known roadmap. |
| **Using CVA for Single Use Case** | CVA requires 2+ cases to identify commonality/variability. | Run CVA on payment before any other transaction exists | Wait for 2nd use case (YAGNI), OR document anticipated cases with stakeholder validation. |

## Integration with Other Skills

### architect Agent

CVA produces ADR stub with pattern rationale. Architect agent creates formal ADR.

**Handoff Protocol**:

```python
Task(subagent_type="architect", prompt="Create ADR from CVA analysis at cva-payment-processing.md")
```

### decision-critic Skill

Validates abstraction choices discovered via CVA. Applies inversion thinking to pattern recommendation.

**Usage**:

```bash
/decision-critic "Validate Abstract Factory pattern for payment processing per CVA matrix"
```

### independent-thinker Agent

Challenges whether abstraction is needed at all. Use when CVA is borderline (minimal variability).

**Usage**:

```python
Task(subagent_type="independent-thinker", prompt="Challenge whether payment abstraction is justified given only 2 current methods")
```

## Verification Checklist

After completing CVA:

- [ ] Matrix has ≥2 rows (commonalities) and ≥2 columns (variabilities)
- [ ] All matrix cells are filled with concrete implementations
- [ ] Recommended patterns align with matrix structure (rows → Strategy, columns → Factory)
- [ ] Rationale explains WHY patterns fit (cites matrix as evidence)
- [ ] Edge cases handled (single use case, all variability, no commonality)
- [ ] Validation script passes: `python3 scripts/validate-cva-matrix.py [file]`
- [ ] ADR stub created with decision rationale
- [ ] Reassessment triggers documented (when to re-run CVA)

## Reassessment Triggers

Re-run CVA when:

1. **3+ new use cases** added (may reveal new patterns or invalidate current abstraction)
2. **Major architectural shift** (e.g., monolith → microservices)
3. **Performance issues** with current abstraction (overhead not justified)
4. **Team feedback**: Abstraction is too complex, not pulling weight, or forcing designs
5. **Quarterly review** (align with retrospective cycle)

## Tiered Depth Levels

Choose depth based on decision impact:

| Tier | Time | Use Cases | When to Use |
|------|------|-----------|-------------|
| Quick | 15 min | 2-3 | Simple decisions, clear patterns, low risk |
| Standard | 30 min | 3-5 | Moderate complexity, some uncertainty, medium risk |
| Deep | 60 min | 6+ | Architectural decisions, high uncertainty, high risk |

**Time-boxing**: Set timer, commit to best-available analysis when time expires. CVA is a tool, not a perfectionist exercise.

## .NET Examples

See `references/matrix-building-examples.md` for complete .NET examples:

- ASP.NET Middleware Pipeline (commonality: process request, variability: authentication, logging, compression)
- Dependency Injection Providers (commonality: resolve dependencies, variability: lifetime scope, registration patterns)
- Data Access Patterns (commonality: CRUD operations, variability: SQL, NoSQL, in-memory)

## References

- [Pattern Mapping Guide](references/pattern-mapping-guide.md) - How to read matrix and map to Strategy, Abstract Factory, combinations
- [Matrix Building Examples](references/matrix-building-examples.md) - .NET examples with complete CVA workflows
- [Multidimensional CVA](references/multidimensional-cva.md) - Advanced: handling multiple axes of variability
- [Coplien Multi-Paradigm Design](references/coplien-multi-paradigm-design.md) - Academic foundation and further reading

## Scripts

### validate-cva-matrix.py

Check CVA matrix completeness and suggest patterns.

**Usage**:

```bash
python3 .claude/skills/cva-analysis/scripts/validate-cva-matrix.py cva-matrix.md
```

**Exit Codes**:

- 0: Valid matrix, patterns suggested
- 10: Validation failure (missing rows/columns, empty cells)
- 1: Error (file not found, invalid format)

### generate-cva-template.py

Create empty matrix template from user input.

**Usage**:

```bash
python3 .claude/skills/cva-analysis/scripts/generate-cva-template.py \
  --commonalities "Validate,Authorize,Record,Handle errors" \
  --variabilities "CreditCard,PayPal,BankTransfer" \
  --output cva-matrix.md
```

### export-cva-matrix.py

Convert Markdown table to Mermaid diagram for presentations.

**Usage**:

```bash
python3 .claude/skills/cva-analysis/scripts/export-cva-matrix.py \
  --input cva-matrix.md \
  --format mermaid \
  --output cva-diagram.mmd
```

## Extension Points

1. **Pattern Mapping**: Add new pattern types beyond Strategy/Abstract Factory
   - Edit `references/pattern-mapping-guide.md`
   - Add Builder, Bridge, Visitor patterns with matrix signatures

2. **Matrix Formats**: Add export formats beyond Markdown
   - Use `scripts/export-cva-matrix.py --format <json|plantuml|csv>`

3. **Multidimensional Analysis**: Handle complex cases with 3+ axes
   - See `references/multidimensional-cva.md`

4. **AI Integration**: Automated pattern suggestion
   - Route to decision-critic or independent-thinker for automated review
