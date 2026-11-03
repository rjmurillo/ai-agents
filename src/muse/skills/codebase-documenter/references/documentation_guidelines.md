# Documentation Guidelines

These standards apply to every document this skill scaffolds. Keep them in sight while filling in placeholders.

## Voice

- **Active voice.** "The service validates the request" beats "The request is validated by the service."
- **Second person.** Address the reader as "you." It is shorter and more direct than "the user" or "developers."
- **Short sentences.** Aim for under 20 words. Break long sentences at the first conjunction.
- **Concrete nouns.** "API key" beats "credential." "PostgreSQL" beats "the database technology."
- **No marketing language.** No "blazing fast," no "world-class," no "seamlessly." Cite numbers if speed matters.

## Structure

Documentation follows progressive disclosure. The reader starts with what they need now and drills down only if they need more.

1. **Headline first.** The reader knows the topic from the first heading.
2. **Quick start before reference.** Show how to do the most common thing in five minutes. Reference detail comes after.
3. **Scannable headings.** A reader skimming the table of contents can find the section they need without reading body text.
4. **Five-minute target.** A page should be readable in under five minutes. Past that, split.
5. **One concept per page.** Architecture goes in `ARCHITECTURE.md`, not the README. API reference goes in `API.md`, not the README.

## Audience

The reader is a developer who is new to **this project**, not new to programming. They know the language and the ecosystem. They do not know:

- What this project does or who it is for.
- How to run it locally.
- Where to look when something fails.
- The trade-offs you made and why.

Write for that reader, not for the team that already knows the answers. The author may be senior; the reader is not.

## Placeholder Convention

Use square brackets to mark placeholders the reader must fill in.

- `[Project name]` for short replacements (one to four words).
- `[One-line summary of what this project does]` for descriptive replacements.
- Backticked placeholders inside code: `[install command]`, `[ENV_VAR]`.

The reader can search for `[` and `]` to find every placeholder. Do not use `<>` or `{}` because those collide with code syntax in many languages.

## What to Avoid

- **Weasel words**: "nearly," "almost," "some," "may." If you mean "always," say so. If you mean "sometimes," give the condition.
- **Marketing language**: "powerful," "robust," "elegant." Replace with data.
- **Filler phrases**: "It is worth noting that," "in order to," "due to the fact that." Cut them.
- **Apologetic prose**: "Unfortunately, you have to..." Just say what to do.
- **Nested parentheses**: A reader holding three open parens has lost the thread. Restructure the sentence.

## Code Samples

- **Make samples runnable.** A reader should be able to copy the block and run it. Include the imports.
- **Use realistic data.** "Foo bar baz" examples teach nothing. Use the kind of data the project actually handles.
- **Show output when it helps.** A code block followed by the expected output prevents misinterpretation.
- **Trim noise.** A 60-line example to teach one concept obscures the concept.

## Diagrams

Diagrams reduce ambiguity. They do not decorate. See `visual_aids_guide.md` for when and how.

## Linkage

- Link from the README to deeper docs (ARCHITECTURE, API, contributing guide).
- Link from each deep doc back to the README so a lost reader can find their way home.
- Use relative links inside the repository so they survive renames of the host.

## Self-Review

Before you ship a doc, walk this list.

- [ ] A new contributor could clone, install, and run from the README in under five minutes.
- [ ] No marketing language, weasel words, or filler.
- [ ] Active voice; sentences under 20 words.
- [ ] Code samples include imports and produce visible output.
- [ ] Each link works.
- [ ] No environment-specific paths or secrets.
