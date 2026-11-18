# Writing Process

## 1. Plan

- Name the reader and what they know already. Name the one outcome the page gives them.
- Pick the content type ([content types](content-types.md)) and the stylebook
  ([stylebook selection](stylebook-selection.md)).
- Read two or three existing pages of the same type on the site and copy their
  shape, front matter, and components.
- Gather the facts from the source of truth: code, tests, the product, the
  changelog, or the issue. Record where each fact came from.

## 2. Draft

- Write the whole page before polishing any part of it.
- Lead with the result or the task. Put background after the reader knows why it matters.
- Run every safe code sample and command now, not at the end. See the gate in
  [testing your documentation](testing-your-documentation.md).
- When a fact is missing, ask the maintainer or leave a visible gap in your
  report. Do not ship placeholder text in the page.

## 3. Check facts

- Match every name, flag, default, version, and limit against its source.
- Confirm platform and version differences instead of assuming one platform.
- Check examples for insecure defaults and deprecated APIs.

## 4. Edit

- Cut sentences that say what the page is about to do.
- Split long sentences. Replace jargon or define it on first use.
- Check the page against [prose patterns](prose-patterns.md),
  [common documentation issues](common-documentation-issues.md), and
  [cross-referencing](cross-referencing.md).

## 5. Test and polish

- Follow [testing your documentation](testing-your-documentation.md).
- Confirm code fences carry a language, links resolve, and headings follow the site's case.

## Adapt to the reader

| Reader | Give them |
|---|---|
| New to the topic | Definitions, the "why" before the "how", one recommended path |
| Experienced practitioner | Direct steps, exact options, edge cases, performance and security notes |
| Technical leader | Trade-offs, risks, cost, and what changes for the team |
| Non-technical stakeholder | Outcomes and decisions, with technical detail linked, not inlined |

## Quality checklist

- [ ] A reader new to the topic can follow the main path.
- [ ] Every technical detail and example was checked against its source or run.
- [ ] The page delivers what its title and first paragraph promise.
- [ ] A reader can scan headings and find the task they came for.
- [ ] Sentences translate cleanly: literal words, no idioms, explicit subjects.
- [ ] Sources are linked where a claim depends on them.
