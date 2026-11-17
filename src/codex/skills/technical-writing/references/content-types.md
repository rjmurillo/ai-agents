# Content Types

Give each page one job. A tutorial that turns into a reference table, or a
concept page that turns into a procedure, serves neither reader. Split it.

Use the outline the target site already uses for the type. Use these outlines
only when the site has none. Headings are sentence case unless the site uses
title case.

## Tutorial

Teaches by building one small, working thing from start to finish.

```markdown
# Build <result> with <technology>

What you build, what you learn, and how long it takes.

## Prerequisites
## Step 1: <first visible progress>
## Step 2: <build on step 1>
## Verify it works
## Clean up            (when the tutorial created resources)
## Next steps
```

- Every step ends in a state the reader can see or check.
- Do not branch into options. Pick the path and link alternatives at the end.

## How-to guide

Gets a reader who already knows the basics through one task.

```markdown
# <Verb> <object>

One sentence: when you need this task.

## Prerequisites
## <Verb> <object>      (numbered steps)
## Verify
## Troubleshoot         (optional)
## See also
```

- Name the page after the task ("Export data"), not the feature ("Export feature").
- One action per step. Put the expected result after the action.

## Concept

Explains what something is, why it exists, and how it fits with the rest.

```markdown
# <Concept>

What it is in one or two sentences.

## How it works
## When to use it
## When not to use it
## Related concepts
```

- Explain the mental model before details. Link procedures; do not embed them.

## Reference

Lists facts a reader looks up: options, parameters, rules, error codes.

```markdown
# <Thing> reference

| Name | Type | Default | Description |
```

- Keep entries parallel and complete. Generate the page from source when the
  site can, so it cannot drift.
- One short example per entry beats prose.

## Troubleshooting

Moves a reader from a symptom to a fix.

```markdown
## <Symptom as the reader sees it, error text included>

**Cause:** <why it happens>

**Fix:** <steps>
```

- Lead with the exact error text so search finds it.
- Never blame the reader. State what did not happen and how to recover.

## Rule or diagnostic page

Explains one analyzer rule, lint rule, or error code. Common in tool projects.

```markdown
# <ID>: <rule title>

| Item | Value |
|---|---|
| Rule ID | <ID> |
| Category | <category> |
| Default severity | <severity> |

## Cause
## Rule description
## How to fix violations    (a failing example, then a passing example)
## When to suppress warnings
## See also
```

- Show the code that triggers the rule and the corrected code, both compiled.
- Keep the ID, title, and severity identical to the source that defines them.

## User guide

Groups several workflows for one product or feature.

```markdown
# <Product> user guide

## Overview
## Get started
## <Workflow 1>
## <Workflow 2>
## Troubleshooting
## Frequently asked questions
```

- Organize by task, not by menu or feature list.

## Blog post or announcement

Tells a story about a change, a result, or a lesson. Use only when the site has
a blog. First person and "we" fit here and nowhere else in product docs.

```markdown
# <Specific title that names the result>

The problem and why it matters now.

## What we changed
## How it works
## Results               (measured numbers, with method)
## What we would do differently
## Try it
```

## Other artifact types

- Architecture decision records: use the `adr-generator` skill.
- API guides built around endpoints: use the `api-doc-authoring` skill.
- PRDs and specifications: delegate to the `explainer` agent.
