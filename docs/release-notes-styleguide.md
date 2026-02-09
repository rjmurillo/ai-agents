# Release Notes Style Guide

## Purpose

This guide defines how to write release notes for the ai-agents project. It applies to anyone writing release notes, human or AI. The goal is consistent, benefit-focused documentation that tells readers what changed and why it matters. The style draws inspiration from Home Assistant's release blog format: conversational, community-oriented, and grounded in user value.

## Title Format

Use this pattern for release titles:

```text
AI Agents vX.Y.Z: Tagline Emoji Emoji
```

Rules:

- The tagline should be 2-5 words that capture the release theme.
- Use exactly two emojis that represent the core themes.
- Separate the version and tagline with a colon.

Examples from past releases:

- `AI Agents v0.2.0: Python-First, Security-Strong 🐍🔒`
- `AI Agents v0.3.0: Memory-First, Quality-Gated 🧠🛡️`

Bad examples:

- `v0.4.0 Release` (no tagline, no emojis, missing project name)
- `AI Agents v0.4.0: A Comprehensive Update to the Framework Extraction System With Many Improvements` (too long)

## Opening Paragraph

The opening paragraph sets the tone for the entire document. It should read like a short pitch, not a changelog.

Rules:

- Address the reader directly with "you."
- State what the release delivers in one sentence.
- State why it matters in one sentence.
- Include the commit count and issue count.
- Use a warm, conversational tone.

Example:

> AI Agents v0.3.0 delivers a memory system that remembers, reasons, and cites its sources. Agents now retrieve project knowledge before acting. Quality gates block bad code before it reaches a PR. This release includes 77 commits across 139 closed issues.

After the opening paragraph, add a second paragraph that expands on the highlights. Then include release metadata:

```markdown
**Released:** Month YYYY
**Highlights:** Feature 1, Feature 2, Feature 3, Feature 4
```

Follow the metadata with a horizontal rule and a table of contents.

## Table of Contents

Include a table of contents after the opening section. Link to every H2 section in the document. Use anchor links.

Example:

```markdown
## Table of Contents

- [Feature Section One](#feature-section-one)
- [Feature Section Two](#feature-section-two)
- [Breaking Changes](#breaking-changes)
- [All Changes](#all-changes)
- [Contributors](#contributors)
- [What's Next?](#whats-next)
```

## Feature Sections

Each major feature gets its own H2 section. Features are the heart of the release notes.

### Headings

Feature headings should be benefit-focused, not just the feature name.

Good:

- "Memories that cite their sources"
- "Quality gates that catch problems at commit time"
- "Context windows with less noise"

Bad:

- "Citation Schema Implementation"
- "Pre-commit Hook Addition"
- "AGENTS.md Refactoring"

You may use one emoji per heading, sparingly. Not every heading needs an emoji.

### Section Structure

1. Open with a short paragraph explaining the "why" and user benefit.
2. Use H3 subsections for distinct capabilities within the feature.
3. Provide technical details and usage information in each subsection.
4. End each subsection with PR links.

### PR Links

End each subsection with a reference to the relevant pull requests. Use this format:

```markdown
See [PR #1045](https://github.com/rjmurillo/ai-agents/pull/1045) for details.
```

For multiple PRs:

```markdown
See [PR #1045](https://github.com/rjmurillo/ai-agents/pull/1045) and [PR #1009](https://github.com/rjmurillo/ai-agents/pull/1009) for details.
```

For three or more PRs:

```markdown
See [PR #1013](https://github.com/rjmurillo/ai-agents/pull/1013), [PR #1019](https://github.com/rjmurillo/ai-agents/pull/1019), and [PR #1104](https://github.com/rjmurillo/ai-agents/pull/1104).
```

### Language

Use "we" and "you" throughout feature sections.

- "We added a graph traversal module that connects related memories."
- "You can now retrieve context with negligible latency."

## Tone and Voice

### Do

- Write in a conversational but professional tone.
- Use active voice and short sentences.
- Write at a grade 9 reading level.
- Explain technical concepts so a new contributor can follow.
- Celebrate accomplishments with specifics, not superlatives.

### Do Not

- Use em-dashes or en-dashes. Use commas, periods, or restructure.
- Use emojis in body text. Reserve them for headings only, and sparingly (max one per heading).
- Use passive voice. Write "we implemented" not "was implemented."
- Use jargon without explanation. If you must use a technical term, define it on first use.
- Write walls of text. Break content into short paragraphs of 2-3 sentences.

### Examples

Good:

> The MemoryRouter search dropped from ~260ms to ~10ms. That is a 26x improvement. Agents now retrieve context with negligible latency.

Bad:

> The MemoryRouter search performance was significantly improved through various optimizations that were implemented across multiple pull requests, resulting in a much better experience for all agents utilizing the memory subsystem.

## Breaking Changes Section

Use an H2 heading titled "Breaking Changes." Each breaking change gets an H3 with the affected area.

### Structure for Each Breaking Change

```markdown
### Name of the Breaking Change

**What changed**: One sentence describing the change.

**Impact**: Who is affected and how.

**Migration**: What users need to do.

See [PR #NNNN](https://github.com/rjmurillo/ai-agents/pull/NNNN).
```

### Example

```markdown
### Fail-Closed Hook Default

**What changed**: Git hooks now block operations when validation state is uncertain.

**Impact**: Operations that previously passed during uncertain validation states will now be blocked. This affects all contributors using the pre-push hooks.

**Migration**: No code changes needed. Be aware that some operations may be blocked that previously passed silently.

See [PR #1047](https://github.com/rjmurillo/ai-agents/pull/1047).
```

If a release has no breaking changes, include the section with a note: "This release contains no breaking changes."

## All Changes Section

Use an H2 heading titled "All Changes." Group entries by type using H3 subheadings.

### Type Groups (in order)

1. Features
2. Fixes
3. Performance
4. Refactoring
5. Docs
6. CI / Dependencies
7. Testing

Omit any group that has no entries.

### Entry Format

Each entry is a single line with a description and a linked PR number:

```markdown
- Description ([#NNNN](https://github.com/rjmurillo/ai-agents/pull/NNNN))
```

Rules:

- Use sentence case for descriptions.
- Strip conventional commit prefixes (`feat:`, `fix:`, `refactor:`, etc.) from descriptions.
- Start each description with a verb in present tense or imperative form: "Add", "Fix", "Optimize", "Update."
- For entries with multiple PRs, list all: `([#1122](url), [#1121](url))`

### All Changes Example

```markdown
### Features

- Add context optimizer tooling suite with passive context analysis ([#1116](https://github.com/rjmurillo/ai-agents/pull/1116))
- Inject retrieval-led reasoning directives across all phases ([#1110](https://github.com/rjmurillo/ai-agents/pull/1110))

### Fixes

- Use portable Python for skill learning hook ([#1095](https://github.com/rjmurillo/ai-agents/pull/1095))
- Resolve CWE vulnerabilities in session log creation ([#1085](https://github.com/rjmurillo/ai-agents/pull/1085))

### Performance

- Optimize MemoryRouter search from ~260ms to ~10ms ([#1044](https://github.com/rjmurillo/ai-agents/pull/1044))
```

## Contributors Section

Thank contributors by their GitHub handle. Include automated contributors.

### Format

```markdown
## Contributors

Thank you to everyone who contributed to this release.

- [@username](https://github.com/username) - Brief role description
- [@bot-name](https://github.com/apps/bot-name) - Automated contributions
```

End with one closing sentence about the collaborative nature of the release. Include a specific metric when possible (commit count, issue count, PR count).

### Contributors Example

```markdown
The agent system coordinated 77 commits across 139 closed issues. Memory enhancement, quality gates, and retrieval-led reasoning were designed, reviewed, and validated through multi-agent collaboration.
```

## What's Next Section

Use an H2 heading titled "What's Next?"

Rules:

- Include 3-5 bullet points about upcoming work.
- Bold the version number or theme name in each bullet.
- Provide a brief description of each focus area.
- Do not make promises. Use language like "we are focusing on" or "planned work includes."

### What's Next Example

```markdown
## What's Next?

With v0.3.0's memory and quality foundations in place, we are focusing on:

- **v0.3.1**: PowerShell-to-Python migration cleanup (P0 items)
- **v0.4.0**: Framework extraction for standalone plugin ecosystem
- **Context optimization**: Continued reduction of passive context overhead
- **Agent Teams**: Parallel multi-agent execution with Claude Code Agent Teams
```

## Closing

End the document with a full changelog comparison link:

```markdown
**Full Changelog**: [vX.Y-1.Z...vX.Y.Z](https://github.com/rjmurillo/ai-agents/compare/vX.Y-1.Z...vX.Y.Z)
```

## Anti-Patterns

Do not:

- Write a flat changelog with no narrative. The "All Changes" section is the changelog. Feature sections tell the story.
- Use passive voice. Write "we implemented" not "was implemented."
- Skip the "why" and jump straight to technical details. Every feature section opens with user benefit.
- List every PR in feature sections. Save exhaustive lists for the "All Changes" section.
- Use jargon without explanation. Define technical terms on first use.
- Write walls of text. Break into short paragraphs of 2-3 sentences.
- Forget PR links. Every claim should be traceable to a pull request.
- Use em-dashes or en-dashes anywhere in the document.
- Use emojis in body text. Emojis belong only in the title and optionally in section headings.
- Include internal implementation details that do not affect users. Focus on outcomes, not plumbing.

## Template

Copy this skeleton for new releases. Replace all `{PLACEHOLDER}` values.

```markdown
# AI Agents v{VERSION}: {TAGLINE} {EMOJI1}{EMOJI2}

AI Agents v{VERSION} delivers {ONE_SENTENCE_WHAT}. {ONE_SENTENCE_WHY}. This release includes {COMMIT_COUNT} commits across {ISSUE_COUNT} closed issues.

{EXPANDED_HIGHLIGHTS_PARAGRAPH}

**Released:** {MONTH} {YEAR}
**Highlights:** {HIGHLIGHT_1}, {HIGHLIGHT_2}, {HIGHLIGHT_3}, {HIGHLIGHT_4}

---

## Table of Contents

- [{FEATURE_1_HEADING}](#{FEATURE_1_ANCHOR})
- [{FEATURE_2_HEADING}](#{FEATURE_2_ANCHOR})
- [Breaking Changes](#breaking-changes)
- [All Changes](#all-changes)
- [Contributors](#contributors)
- [What's Next?](#whats-next)

---

## {FEATURE_1_HEADING}

{WHY_THIS_MATTERS_AND_USER_BENEFIT}

### {CAPABILITY_1}

{DETAILS_AND_USAGE}

See [PR #{PR_NUMBER}](https://github.com/rjmurillo/ai-agents/pull/{PR_NUMBER}) for details.

### {CAPABILITY_2}

{DETAILS_AND_USAGE}

See [PR #{PR_NUMBER}](https://github.com/rjmurillo/ai-agents/pull/{PR_NUMBER}) for details.

---

## {FEATURE_2_HEADING}

{WHY_THIS_MATTERS_AND_USER_BENEFIT}

### {CAPABILITY_1}

{DETAILS_AND_USAGE}

See [PR #{PR_NUMBER}](https://github.com/rjmurillo/ai-agents/pull/{PR_NUMBER}) for details.

---

## Breaking Changes

### {BREAKING_CHANGE_NAME}

**What changed**: {ONE_SENTENCE}

**Impact**: {WHO_IS_AFFECTED_AND_HOW}

**Migration**: {WHAT_USERS_NEED_TO_DO}

See [PR #{PR_NUMBER}](https://github.com/rjmurillo/ai-agents/pull/{PR_NUMBER}).

---

## All Changes

### Features

- {DESCRIPTION} ([#{PR_NUMBER}](https://github.com/rjmurillo/ai-agents/pull/{PR_NUMBER}))

### Fixes

- {DESCRIPTION} ([#{PR_NUMBER}](https://github.com/rjmurillo/ai-agents/pull/{PR_NUMBER}))

### Performance

- {DESCRIPTION} ([#{PR_NUMBER}](https://github.com/rjmurillo/ai-agents/pull/{PR_NUMBER}))

### Refactoring

- {DESCRIPTION} ([#{PR_NUMBER}](https://github.com/rjmurillo/ai-agents/pull/{PR_NUMBER}))

### Docs

- {DESCRIPTION} ([#{PR_NUMBER}](https://github.com/rjmurillo/ai-agents/pull/{PR_NUMBER}))

### CI / Dependencies

- {DESCRIPTION} ([#{PR_NUMBER}](https://github.com/rjmurillo/ai-agents/pull/{PR_NUMBER}))

### Testing

- {DESCRIPTION} ([#{PR_NUMBER}](https://github.com/rjmurillo/ai-agents/pull/{PR_NUMBER}))

---

## Contributors

Thank you to everyone who contributed to this release.

- [@{USERNAME}](https://github.com/{USERNAME}) - {ROLE_DESCRIPTION}
- [@dependabot[bot]](https://github.com/apps/dependabot) - Dependency updates

{CLOSING_SENTENCE_WITH_METRIC}

---

## What's Next?

With v{VERSION}'s {THEME} in place, we are focusing on:

- **{NEXT_VERSION_OR_THEME}**: {BRIEF_DESCRIPTION}
- **{NEXT_VERSION_OR_THEME}**: {BRIEF_DESCRIPTION}
- **{NEXT_VERSION_OR_THEME}**: {BRIEF_DESCRIPTION}

---

**Full Changelog**: [v{PREV_VERSION}...v{VERSION}](https://github.com/rjmurillo/ai-agents/compare/v{PREV_VERSION}...v{VERSION})
```
