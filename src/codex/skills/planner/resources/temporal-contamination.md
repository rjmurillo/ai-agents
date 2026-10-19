# Temporal Contamination in Code Comments

This document defines terminology for identifying comments that leak information about code history, change processes, or planning artifacts. Both @agent-technical-writer and @agent-quality-reviewer reference this specification.

## The Core Principle

> **Timeless Present Rule**: Comments must be written from the perspective of a reader encountering the code for the first time, with no knowledge of what came before or how it got here. The code simply _is_.

In a plan, this means comments are written _as if the plan was already executed_.

## Detection Heuristic

Evaluate each comment against these four questions. Signal words are examples -- extrapolate to semantically similar constructs.

### 1. Does it describe an action taken rather than what exists?

**Category**: Change-relative

| Contaminated                           | Timeless Present                                            |
| -------------------------------------- | ----------------------------------------------------------- |
| `// Added mutex to fix race condition` | `// Mutex serializes cache access from concurrent requests` |
| `// New validation for the edge case`  | `// Rejects negative values (downstream assumes unsigned)`  |
| `// Changed to use batch API`          | `// Batch API reduces round-trips from N to 1`              |

Signal words (non-exhaustive): "Added", "Replaced", "Now uses", "Changed to", "New", "Updated", "Refactored"

### 2. Does it compare to something not in the code?

**Category**: Baseline reference

| Contaminated                                      | Timeless Present                                                    |
| ------------------------------------------------- | ------------------------------------------------------------------- |
| `// Replaces per-tag logging with summary`        | `// Single summary line; per-tag logging would produce 1500+ lines` |
| `// Unlike the old approach, this is thread-safe` | `// Thread-safe: each goroutine gets independent state`             |
| `// Previously handled in caller`                 | `// Encapsulated here; caller should not manage lifecycle`          |

Signal words (non-exhaustive): "Instead of", "Rather than", "Previously", "Replaces", "Unlike the old", "No longer"

### 3. Does it describe where to put code rather than what code does?

**Category**: Location directive

| Contaminated                  | Timeless Present                              |
| ----------------------------- | --------------------------------------------- |
| `// After the SendAsync call` | _(delete -- diff structure encodes location)_ |
| `// Insert before validation` | _(delete -- diff structure encodes location)_ |
| `// Add this at line 425`     | _(delete -- diff structure encodes location)_ |

Signal words (non-exhaustive): "After", "Before", "Insert", "At line", "Here:", "Below", "Above"

**Action**: Always delete. Location is encoded in diff structure, not comments.

### 4. Does it describe intent rather than behavior?

**Category**: Planning artifact

| Contaminated                           | Timeless Present                                         |
| -------------------------------------- | -------------------------------------------------------- |
| `// TODO: add retry logic later`       | _(delete, or implement retry now)_                       |
| `// Will be extended for batch mode`   | _(delete -- do not document hypothetical futures)_       |
| `// Temporary workaround until API v2` | `// API v1 lacks filtering; client-side filter required` |

Signal words (non-exhaustive): "Will", "TODO", "Planned", "Eventually", "For future", "Temporary", "Workaround until"

**Action**: Delete, implement the feature, or reframe as current constraint.

### 5. Does it describe the author's choice rather than code behavior?

**Category**: Intent leakage

| Contaminated                               | Timeless Present                                     |
| ------------------------------------------ | ---------------------------------------------------- |
| `// Intentionally placed after validation` | `// Runs after validation completes`                 |
| `// Deliberately using mutex over channel` | `// Mutex serializes access (single-writer pattern)` |
| `// Chose polling for reliability`         | `// Polling: 30% webhook delivery failures observed` |
| `// We decided to cache at this layer`     | `// Cache here: reduces DB round-trips for hot path` |

Signal words (non-exhaustive): "intentionally", "deliberately", "chose", "decided", "on purpose", "by design", "we opted"

**Action**: Extract the technical justification; discard the decision narrative. The reader doesn't need to know someone "decided" -- they need to know WHY this approach works.

**The test**: Can you delete the intent word and the comment still makes sense? If yes, delete the intent word. If no, reframe around the technical reason.

---

**Catch-all**: If a comment only makes sense to someone who knows the code's history, it is temporally contaminated -- even if it does not match any category above.

## Subtle Cases

Same word, different verdict -- demonstrates that detection requires semantic judgment, not keyword matching.

| Comment                                | Verdict      | Reasoning                                        |
| -------------------------------------- | ------------ | ------------------------------------------------ |
| `// Now handles edge cases properly`   | Contaminated | "properly" implies it was improper before        |
| `// Now blocks until connection ready` | Clean        | "now" describes runtime moment, not code history |
| `// Fixed the null pointer issue`      | Contaminated | Describes a fix, not behavior                    |
| `// Returns null when key not found`   | Clean        | Describes behavior                               |

## The Transformation Pattern

> **Extract the technical justification, discard the change narrative.**

1. What useful info is buried? (problem, behavior)
2. Reframe as timeless present

Example: "Added mutex to fix race" -> "Mutex serializes concurrent access"
