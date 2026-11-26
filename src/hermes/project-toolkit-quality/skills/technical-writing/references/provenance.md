# Provenance

This skill combines three sources. Each keeps its own license and attribution.
None of the owners named here endorses or reviewed this skill.

## Sources

| Source | Pinned revision | Read | License |
|---|---|---|---|
| `microsoft/aspire.dev`, the `doc-writer` agent skill (SKILL.md and six references) | `24fa655677788e02b297ec5f2f6c78ad8275f92d` (committed 2026-11-17) | 2026-11-17 | MIT, Microsoft Corporation |
| `Neeeophytee/agent-stylebooks`, `skills/` (16 stylebooks) and `STYLE-MATRIX.md` | `85b318fcb69fbb50b9f066aadf81750d368c6988` (committed 2026-08-19) | 2026-11-17 | MIT, Shilpa Mitra, for the repository text only |
| This repository's `technical-writer` agent | last present at the parent of `782e492b1` (2026-02-09) | 2026-11-17 | This repository's license |

## What changed from each source

- **technical-writer agent.** Its writing process, audience table, content-type
  outlines, and quality checklist became [writing-process.md](writing-process.md)
  and [content-types.md](content-types.md). Advice that conflicted with the
  aspire.dev prose rules (opening hooks, signposting, title-case headings) was dropped.
- **aspire.dev doc-writer.** Generic rules became [prose-patterns.md](prose-patterns.md),
  [common-documentation-issues.md](common-documentation-issues.md),
  [cross-referencing.md](cross-referencing.md), and
  [testing-your-documentation.md](testing-your-documentation.md). The SKILL.md
  body, `integration-documentation.md`, and `terminal-recordings.md` moved under
  [site-profiles/aspire-dev/](site-profiles/aspire-dev/). The aspire-only rules from
  the other references are in its `site-specific-rules.md`.
  Em and en dashes were replaced, a code-block title separator became `<em-dash>`,
  and pipe-to-shell installer commands became a link to the official install page.
  The upstream SKILL.md showed `InstallPackage` and `InstallDotNetPackage` with a `package` prop.
  Both components declare `packageName` at `24fa655`, so the copy here uses `packageName`.
- **agent-stylebooks.** Each `SKILL.md` body became `stylebooks/<name>.md` with its
  frontmatter description as a "Use for" line. `STYLE-MATRIX.md` is reproduced in
  [stylebook-selection.md](stylebook-selection.md). The per-skill provenance files
  are reproduced below. Per-skill `agents/openai.yaml` files were not copied.

## agent-stylebooks notice

The MIT License applies to the original repository text and validation code.
It does not relicense third-party source guides. See [PROVENANCE.md](https://github.com/Neeeophytee/agent-stylebooks/blob/85b318fcb69fbb50b9f066aadf81750d368c6988/PROVENANCE.md)
for the source and treatment of every skill.

Names such as Apple, CDC, GitHub, GitLab, Google, Kubernetes, Mailchimp, MDN,
Microsoft, NASA, NHS, Red Hat, SEC, W3C, and GOV.UK may be trademarks or identifiers
of their respective owners.
They identify the editorial systems discussed by the skills. This community
project is not affiliated with, endorsed by, or sponsored by those owners.

The skills contain independently written operational guidance. They do not
include third-party logos, screenshots, word-list dumps, or copied style-guide
chapters.

The stylebooks do not provide certification, regulatory compliance, legal advice,
medical approval, W3C status, NASA publication approval, or ASD-STE100 compliance.

## Stylebook sources

### 18f-content

- Primary source: <https://github.com/18F/content-guide>
- Source terms: public domain in the United States and CC0 1.0 worldwide.
- Source status: archived in 2023; the historical source remains useful but is not
  presented as current policy.
- Classification: A (open source).
- Accessed: 2026-08-18.
- Method: independently written operational instructions; no source passages are included.
- Attribution: 18F Content Guide contributors.
- Affiliation: community interpretation; not an official 18F or GSA skill.

### apple-interface-writing

- Primary source: <https://developer.apple.com/design/human-interface-guidelines/writing>
- Source terms: no permissive content license was identified for this reuse.
- Classification: B (reference only).
- Accessed: 2026-08-18.
- Method: independent expression of general interface-writing principles. No source
  prose, screenshots, UI examples, or distinctive example pairs are included.
- Affiliation: community interpretation; not an official Apple skill.

### cdc-clear-communication

- Primary source: <https://www.cdc.gov/ccindex/tool/index.html>
- Classification: A (open/source-grounded).
- Accessed: 2026-08-19.
- Method: independently written instructions; see the source notes below for the complete
  source and reuse audit.
- Affiliation: community interpretation; not an official CDC or HHS skill.

- Primary source: <https://www.cdc.gov/ccindex/tool/index.html>
- Supporting source: <https://www.cdc.gov/ccindex/pdf/clear-communication-user-guide.pdf>
- Source overview and scope: <https://www.cdc.gov/ccindex/tool/faq.html>
- Reuse policy: <https://www.cdc.gov/other/agencymaterials.html>
- Publisher: Centers for Disease Control and Prevention, US Department of Health
  and Human Services.
- Accessed: 2026-08-19.
- Classification: A (open/source-grounded). Most CDC website information is US
  public-domain material, subject to the exceptions and conditions in the agency's reuse
  policy. No restricted image, logo, third-party contribution, or checklist text is included.
- Operationalized: audience and objective selection; one primary message; early placement;
  a visible call to action; familiar language; information structure; explanation of numbers;
  and contextual, uncertainty-aware risk communication.
- Not copied: the Index questions, scoring method, score sheets, source examples, tables,
  figures, and distinctive wording.
- Method: independently written operational instructions informed by the source's public
  communication model. This skill is not a substitute for audience research, pretesting,
  clinical review, or the official Index.
- Attribution: principles informed by the CDC Clear Communication Index.
- Affiliation: community interpretation; not an official CDC or HHS skill. Reference to CDC
  does not imply endorsement by CDC, HHS, or the United States Government.

### github-docs

- Primary source: <https://docs.github.com/en/contributing/style-guide-and-content-model/style-guide>
- License evidence: <https://github.com/github/docs/blob/main/LICENSE>
- Source terms: documentation content is CC BY 4.0.
- Classification: A (open source).
- Accessed: 2026-08-18.
- Method: independently written operational instructions; no source passages or
  examples are included.
- Attribution: GitHub Docs contributors.
- Affiliation: community interpretation; not an official GitHub skill.

### gitlab-docs

- Primary source: <https://docs.gitlab.com/development/documentation/styleguide/>
- License evidence: <https://gitlab.com/gitlab-org/gitlab/-/blob/master/CONTRIBUTING.md>
- Source terms: natural-language documentation under `doc/` is CC BY-SA 4.0.
- Classification: A (open source).
- Accessed: 2026-08-18.
- Method: independently written operational instructions. No source examples,
  word-list dumps, or passages are included.
- Attribution: GitLab documentation contributors.
- Affiliation: community interpretation; not an official GitLab skill.

### google-developer-docs

- Primary source: <https://developers.google.com/style/>
- Source terms: page content is CC BY 4.0 unless otherwise noted; code samples
  use Apache 2.0.
- Classification: A (open source).
- Accessed: 2026-08-18.
- Method: independently written operational instructions informed by the public
  guide. No source examples, word-list entries, or extended passages are included.
- Attribution: Google developer documentation style guide, Google.
- Affiliation: community interpretation; not an official Google skill.

### govuk

- Primary source: <https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/writing-guidelines/>
- License reference: <https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/>
- Source terms: GOV.UK content is generally available under the Open Government
  Licence v3.0 unless otherwise stated.
- Classification: A (open source).
- Accessed: 2026-08-18.
- Method: independently written operational instructions; no source examples or
  extended passages are included.
- Attribution: contains principles informed by GOV.UK content guidance under OGL v3.0.
- Affiliation: community interpretation; not an official UK government skill.

### kubernetes-docs

- Primary source: <https://kubernetes.io/docs/contribute/style/style-guide/>
- License evidence: <https://github.com/kubernetes/website/blob/main/LICENSE>
- Source terms: Kubernetes website documentation is CC BY 4.0.
- Classification: A (open source).
- Accessed: 2026-08-18.
- Method: independently written operational instructions; no source examples or
  substantial text are included.
- Attribution: Kubernetes Authors.
- Affiliation: community interpretation; not an official Kubernetes skill.

### mailchimp-content

- Primary source: <https://styleguide.mailchimp.com/>
- Focus page: <https://styleguide.mailchimp.com/voice-and-tone/>
- Source terms: CC BY-NC 4.0 with attribution.
- Classification: B (reference only). The non-commercial condition is not imported
  into this repository.
- Accessed: 2026-08-18.
- Method: independent expression of high-level voice and tone ideas. No source prose,
  examples, word lists, or distinctive phrasing are included.
- Affiliation: community interpretation; not an official Mailchimp or Intuit skill.

### mdn-web-docs

- Primary source: <https://developer.mozilla.org/en-US/docs/MDN/Writing_guidelines/Writing_style_guide>
- License evidence: <https://developer.mozilla.org/en-US/docs/MDN/Writing_guidelines/Attrib_copyright_license>
- Source terms: documentation is CC BY-SA 2.5 or later unless otherwise indicated;
  code samples have separate terms.
- Classification: A (open source).
- Accessed: 2026-08-18.
- Method: independently written operational instructions and original examples only.
- Attribution: Mozilla Contributors.
- Affiliation: community interpretation; not an official Mozilla or MDN skill.

### microsoft-writing-style

- Primary source: <https://learn.microsoft.com/en-us/style-guide/welcome/>
- Terms reference: <https://learn.microsoft.com/en-us/legal/termsofuse>
- Source terms: the general Microsoft Learn terms restrict copying unless a page
  states otherwise; no permissive license was relied on for this skill.
- Classification: B (reference only).
- Accessed: 2026-08-18.
- Method: independent expression of high-level editorial ideas. No source prose,
  tables, word-list content, screenshots, or examples are included.
- Affiliation: community interpretation; not an official Microsoft skill.

### nasa-technical-writing

- Primary source: <https://sti.nasa.gov/for-sti-publishers/>
- Classification: B (reference only).
- Accessed: 2026-08-19.
- Method: independently written instructions; see the source notes below for the complete
  source and reuse audit.
- Affiliation: community interpretation; not an official NASA skill or publication standard.

- Primary source: <https://sti.nasa.gov/for-sti-publishers/>
- Writing resources: <https://sti.nasa.gov/writing-resources-and-style-guides/>
- NASA STI publication guide: <https://ntrs.nasa.gov/citations/20050189209>
- NASA STI standards: <https://ntrs.nasa.gov/citations/20060049392>
- Technical documentation style guide record: <https://standards.nasa.gov/standard/KSC/KSC-DF-107>
- Copyright context: <https://nodis3.gsfc.nasa.gov/displayCA.cfm?Internal_ID=N_PR_2200_002C_&page_name=Chapter4>
- Publisher: National Aeronautics and Space Administration.
- Accessed: 2026-08-19.
- Classification: B (reference-only interpretation). US-government employee works may be
  public domain in the United States, but NASA technical publications can include contractor,
  grantee, transferred, or third-party rights. Public download or distribution clearance does
  not by itself establish an MIT-compatible adaptation licence for every source listed.
- Operationalized: purpose and scope; reproducible methods; test conditions; measurements and
  units; separation of results and interpretation; evidence-to-conclusion traceability;
  limitations; and restrained recommendations.
- Not copied: source prose, templates, report-series requirements, tables, figures, examples,
  NASA identifiers, and any third-party style-manual content referenced by NASA.
- Method: independently written engineering-report decisions grounded in official NASA STI
  resources and the task specification. NASA-specific approval and distribution processes are
  outside this skill.
- Affiliation: community interpretation; not an official NASA skill, publication, standard,
  approval, compliance review, or endorsement.

### nhs-health-content

- Primary source: <https://service-manual.nhs.uk/content>
- Classification: B (reference only).
- Accessed: 2026-08-19.
- Method: independently written instructions; see the source notes below for the complete
  source and reuse audit.
- Affiliation: community interpretation; not an official NHS or NHS England skill.

- Primary source: <https://service-manual.nhs.uk/content>
- Health-content standard: <https://service-manual.nhs.uk/content/standard-for-creating-health-content>
- Writing principles: <https://service-manual.nhs.uk/content/how-we-write>
- Patient messages: <https://service-manual.nhs.uk/content/writing-nhs-messages>
- Inclusive content: <https://service-manual.nhs.uk/content/inclusive-content>
- Accessibility: <https://service-manual.nhs.uk/accessibility>
- Publisher: NHS England.
- Accessed: 2026-08-19.
- Classification: B (reference-only interpretation). Some NHS and UK public-sector sites
  expressly apply the Open Government Licence, but the reviewed NHS digital service manual
  pages display NHS England copyright and did not provide a page-specific OGL reuse grant.
  Public availability and an invitation to adapt a pattern are not treated here as permission
  to relicense source expression under MIT.
- Operationalized: patient needs; evidence and clinical review; plain explanations of medical
  terms; action-led messages; explicit urgency; uncertainty; inclusion; accessibility; and
  preservation of clinically important qualifications.
- Not copied: source prose, A-to-Z entries, templates, examples, visual patterns, code, logos,
  and NHS identity assets.
- Method: independent expression of high-level editorial and safety principles. Revisit the
  classification if NHS England identifies an authoritative licence that covers these pages.
- Affiliation: community interpretation; not an official NHS or NHS England skill, service,
  clinical standard, or endorsement.

### red-hat-docs

- Primary source: <https://github.com/redhat-documentation/supplementary-style-guide>
- Content-model source: <https://github.com/redhat-documentation/modular-docs>
- Source terms: both source repositories state CC BY-SA 4.0.
- Classification: A (open source).
- Accessed: 2026-08-18.
- Method: independently written operational instructions; no source examples,
  word-list content, or extended passages are included.
- Attribution: Red Hat supplementary style guide and Modular Documentation
  Project contributors.
- Affiliation: community interpretation; not an official Red Hat skill.

### sec-plain-english

- Primary source: <https://www.sec.gov/pdf/handbook.pdf>
- Classification: A (open/source-grounded).
- Accessed: 2026-08-19.
- Method: independently written instructions; see the source notes below for the complete
  source and reuse audit.
- Affiliation: community interpretation; not an official SEC skill or legal advice.

- Primary source: <https://www.sec.gov/pdf/handbook.pdf>
- Official publication page: <https://www.sec.gov/about/reports-publications/newsextrahandbook>
- Plain English Disclosure final rule: <https://www.sec.gov/rules-regulations/1998/01/plain-english-disclosure>
- Current plain-writing overview: <https://www.sec.gov/about/plain-writing-initiative>
- Publisher: US Securities and Exchange Commission.
- Accessed: 2026-08-19.
- Classification: A (open/source-grounded). The handbook states that it is not copyrighted
  and may be distributed freely. The skill nevertheless uses independent wording and does not
  reproduce the handbook's contributed examples or presentation.
- Operationalized: investor-oriented information design; material information before
  boilerplate; concrete language; active constructions where useful; explanation of necessary
  terms; sentence and condition control; and visual structures for dense comparisons.
- Not copied: handbook prose, before-and-after examples, cartoons, templates, contributor
  material, and the text of SEC rules or forms.
- Method: independently written operational instructions that add an explicit material-fact
  preservation workflow. The official rule and current law, not this skill, govern filings.
- Affiliation: community interpretation; not an official SEC skill. It is a writing aid, not
  legal advice, securities-law compliance advice, filing review, or SEC approval.

### w3c-technical-reports

- Primary source: <https://www.w3.org/guide/manual-of-style/>
- Classification: B (reference only).
- Accessed: 2026-08-19.
- Method: independently written instructions; see the source notes below for the complete
  source and reuse audit.
- Affiliation: community interpretation; not an official W3C skill or Technical Report.

- Primary source: <https://www.w3.org/guide/manual-of-style/>
- Process and report status: <https://www.w3.org/policies/process/#reports>
- W3C document licence: <https://www.w3.org/copyright/document-license-2023/>
- Normative vocabulary: <https://www.rfc-editor.org/rfc/rfc2119>
- Normative vocabulary clarification: <https://www.rfc-editor.org/rfc/rfc8174>
- Publisher: World Wide Web Consortium; RFC 2119 and RFC 8174 are RFC Editor publications.
- Accessed: 2026-08-19.
- Classification: B (reference-only interpretation). The W3C Document License permits copying
  and distribution with notices but restricts derivative W3C documents, including publication
  of derivative works as technical specifications. This MIT skill does not copy or adapt W3C
  expression and does not present itself as a W3C report.
- Operationalized: normative/informative separation; term definition; consistent requirement
  strength; explicit actors, conditions, exceptions, conformance, references, accessibility,
  and internationalization; accurate caution around RFC 2119/8174 key words.
- Not copied: W3C boilerplate, templates, publication rules, status language, source examples,
  markup, tables, visual styling, and specification text.
- Method: independent expression of general specification-editing decisions. Formal W3C
  publication must follow the current W3C Process and publication rules, not this skill.
- Affiliation: community interpretation; not an official W3C skill, Technical Report,
  publication process, consensus document, or endorsement.

## License texts

### microsoft/aspire.dev

```text
MIT License

Copyright (c) Microsoft Corporation.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE
```

### Neeeophytee/agent-stylebooks

```text
MIT License

Copyright (c) 2026 Shilpa Mitra

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
