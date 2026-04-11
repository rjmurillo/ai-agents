---
source: wiki/concepts/Prompting/Prompt Engineering Anti-Patterns.md
created: 2026-04-11
review-by: 2026-07-11
---

# Prompt Engineering Anti-Patterns

Systematic failures in prompt design and effective replacements based on observed model behavior.

## Core Insight

Prompts shape tone and priorities. They cannot guarantee compliance. When they fail, they fail silently. The strongest parts bias behavior. The weakest parts read like procedural law.

## Anti-Pattern Catalog

| Anti-Pattern | Why It Fails | Replacement |
|-------------|-------------|------------|
| Acronym frameworks (4-D, 5-C) | Labels without substance | Actionable steps, no decorative names |
| "REQUIRED" / "EXACTLY" in all-caps | Decoration, not enforcement | Write as preferences/biases |
| Elaborate welcome messages | Context waste for zero value | Skip to actionable instructions |
| Confidence percentages | Verbalized confidence != logprobs | Use citations instead |
| Finalization gates | No real switches to enforce steps | Task-specific constraints locally |
| Nested conditionals >2 levels | Unpredictable branching | Flatten logic, explicit fallbacks |
| Vague instructions ("be helpful") | No testable constraint | Every behavior must be explicit |
| Global mandatory rules | Fail silently when model drifts | Local reinforcement per task |

## What Actually Works

### Biasing Headers (~80 tokens)

Written as preferences, not mandates. Shape tone without procedural theater.

```
Default to strict facts: no invention.
If unsure, say so.
Browse for verifiable/recency claims or stop if you can't.
Ask 1-2 questions when ambiguity matters.
Stay in scope.
Correct mistakes fast.
```

### Anthropic 3-Step Hallucination Reduction

1. Allow "I don't know" (prevents gap-filling with plausible fiction)
2. Verify with citations (every claim needs a source)
3. Use direct quotes (extract word-for-word before analyzing)

Tradeoff: citation constraints reduce creative output ~15-20% (arXiv 2307.02185). Toggle research mode on/off.

### Engineering Restraint (CLAUDE.md Pattern)

Priority order with explicit conflict resolution:
1. Correctness (money/security/data integrity)
2. Simplicity + clarity
3. Maintainability
4. Reversibility (beats performance)
5. Performance

Non-goals as negative constraints: theoretical elegance, trendy architectures, premature optimization, speculative future-proofing. Negative constraints are harder to ignore than positive aspirations.

### Cognitive Infrastructure Pattern

Core sequence: Pattern, Territory, Gap, Recognition, Embodiment.

1. Show the pattern (how parts relate, not a parts list)
2. Point to familiar territory (2-3 everyday examples)
3. Stop. Don't explain the connection. Let the user bridge.

"When you explain everything, they memorize. When they figure it out, they understand."

### Natural Human Voice

Forbidden patterns (AI tells): "not X, but Y" framing, em dashes in paragraphs, excessive bullets, corrective antithesis.

Effective constraints: get to the point fast, short sentences, simple words, conversational transitions, active voice, concrete examples over abstractions.

## The Subtraction Trap

Stripping AI tells without replacing them with anything real creates its own tell. Prompts built from "don't" rules cause flat, minimal output. The absence becomes a signature.

Counter: replace subtraction rules with positive craft instructions from actual voice samples.

## More Rules = More Fingerprint

Adding structural rules to make output human-like can make it more detectable. Each rule is a regularity the model follows precisely. Those regularities compound into a pattern.

## Meta-Rules for Prompt Design

1. No vague instructions. Every behavior must be testable.
2. No capability creep. Don't add capabilities user didn't ask for.
3. Fewer rules, written as preferences. Applied consistently beats elaborate procedures.
4. Local reinforcement > global declarations.
5. Shrink, don't expand. Most prompts are better shorter.
6. Treat as biasing header, not enforcement.

## Verification > Prompt Engineering

Strict prompts shift responsibility to the user. The model can follow rules and still miss context. Verification workflows matter more than prompt engineering long-term.

Multi-agent verification pattern: teams of AIs on the same project. One AI calls out fabrications from another.
