# Prompt Engineering: Research-Backed Techniques for Single-Turn Prompts

This document synthesizes practical prompt engineering patterns with academic research on LLM reasoning and instruction-following. All techniques target **single-turn system prompts**—static instructions executed in one LLM call. Techniques may include internal structure (e.g., "first extract, then analyze") but do not rely on multi-message orchestration, external tool loops, or dynamic prompt modification.

**Meta-principle**: Show your prompt to a colleague with minimal context on the task and ask them to follow the instructions. If they're confused, the model will likely be too.

---

## Technique Selection Guide

| Domain             | Technique                     | Trigger Condition                               | Stacks With                        | Conflicts With                     | Cost/Tradeoff                                | Effect                                                       |
| ------------------ | ----------------------------- | ----------------------------------------------- | ---------------------------------- | ---------------------------------- | -------------------------------------------- | ------------------------------------------------------------ |
| **Reasoning**      | Plan-and-Solve                | Multi-step problems with missing steps          | RE2, Thinking Tags, Step-Back      | Scope Limitation, Direct Prompting | Moderate token increase for planning phase   | Of incorrect answers: calc errors 7%→5%, missing-step 12%→7% |
| **Reasoning**      | Step-Back                     | Domain knowledge required before reasoning      | Plan-and-Solve                     | —                                  | Additional retrieval step                    | Up to 27% improvement on knowledge tasks                     |
| **Reasoning**      | Chain of Draft                | Token efficiency needed                         | Any reasoning technique            | Verbose CoT                        | Minimal; up to 92% token reduction           | Matches CoT accuracy at 7.6% token cost                      |
| **Reasoning**      | Direct Prompting              | Pattern recognition, implicit learning          | —                                  | Any CoT variant                    | Minimal; no reasoning overhead               | Avoids 30%+ accuracy drops on pattern tasks                  |
| **Reasoning**      | Thread of Thought             | Chaotic/multi-source context                    | RE2                                | —                                  | Moderate increase; benefits from two-phase   | Systematic context segmentation                              |
| **Input**          | RE2 (Re-Reading)              | Any comprehension task (universal enhancer)     | All output-phase techniques        | —                                  | Minimal; question repetition only            | GSM8K: 77.79%→80.59% with CoT                                |
| **Input**          | RaR (Rephrase and Respond)    | Ambiguous questions, frame mismatch             | CoT                                | —                                  | Minimal; single rephrasing step              | Aligns intent with LLM interpretation                        |
| **Input**          | S2A (System 2 Attention)      | Heavily biased/opinionated context              | —                                  | Including original context         | ~2x tokens (preprocessing filter call)       | Factual QA: 62.8%→80.3% on opinion-contaminated prompts      |
| **Input**          | Distractor-Robust Prompting   | Occasional noise, efficiency needed             | Explicit ignore instruction        | —                                  | Minimal; single-turn, no preprocessing       | Approaches S2A without preprocessing cost                    |
| **Input**          | Document Positioning          | >20K tokens of source material                  | Quote Extraction                   | —                                  | None; structural change only                 | Empirical improvement (Anthropic guidance)                   |
| **Input**          | Quote Extraction              | Grounding required before analysis              | Document Positioning               | —                                  | Moderate increase for extraction step        | Forces evidence commitment                                   |
| **Example Design** | Contrastive Examples          | Model makes predictable mistakes                | Affirmative Directives, Categories | —                                  | ~2x example tokens (correct + incorrect)     | +9.8 to +16.0 points on reasoning tasks                      |
| **Example Design** | Complexity-Based Selection    | Teaching thorough reasoning                     | Diversity-Based Selection          | —                                  | Fewer examples but longer; net neutral       | +5.3 avg, up to +18 accuracy (Fu et al.)                     |
| **Example Design** | Diversity-Based Selection     | Selecting from example pool                     | Complexity-Based Selection         | —                                  | None; selection strategy only                | Robust even with 50% wrong demos                             |
| **Example Design** | Analogical Prompting          | No hand-crafted examples available              | Diversity instruction              | Hand-crafted examples              | Moderate increase (self-generated examples)  | GSM8K: 77.8% (vs 72.5% 0-shot CoT)                           |
| **Example Design** | Category-Based Generalization | Novel inputs need correct handling              | Edge-case examples                 | —                                  | Minimal; structural organization             | Enables analogical reasoning                                 |
| **Output**         | Scope Limitation              | Well-defined task; model stuck in planning loop | —                                  | Plan-and-Solve                     | May reduce tokens by preventing overthinking | Prevents analysis paralysis                                  |
| **Output**         | XML Structure Patterns        | Enforcing completeness                          | Instructive Tag Naming             | —                                  | Minimal; structural tags only                | Forces systematic reasoning                                  |
| **Output**         | Format Strictness             | Exact format required                           | Forbidden Phrases                  | —                                  | Minimal                                      | "ONLY return X" compliance                                   |
| **Output**         | Hint-Based Guidance           | Output missing key aspects                      | Any technique                      | —                                  | Minimal                                      | 4-13% improvement via directional stimulus                   |
| **NLU**            | Metacognitive Prompting       | Deep comprehension required                     | —                                  | Simple tasks (causes overthinking) | Moderate to high (5-stage process)           | +4.8% to +6.4% over CoT                                      |
| **Behavioral**     | Identity Establishment        | Any task (foundational)                         | Emotional Stimuli                  | —                                  | Minimal                                      | +10pp on math benchmarks                                     |
| **Behavioral**     | Emotional Stimuli             | Reluctant execution                             | Identity Establishment             | —                                  | Minimal                                      | 8% on Instruction Induction, 115% on BIG-Bench               |
| **Behavioral**     | Confidence Building           | Hesitation/verification loops                   | Error Normalization                | —                                  | Minimal                                      | Eliminates hesitation loops                                  |
| **Behavioral**     | Error Normalization           | Expected failures cause stopping                | Confidence Building                | —                                  | Minimal                                      | Prevents apology spirals                                     |
| **Behavioral**     | Pre-Work Context Analysis     | Blind execution problems                        | Category-Based Examples            | —                                  | Slight increase for analysis phase           | Prevents context-blind execution                             |
| **Behavioral**     | Emphasis Hierarchy            | Multiple priority levels                        | Numbered Rule Priority             | —                                  | Minimal                                      | Predictable priority system                                  |
| **Behavioral**     | Affirmative Directives        | Any instruction (foundational)                  | Contrastive Examples               | —                                  | Minimal                                      | Significant correctness improvement                          |
| **Verification**   | Embedded Verification         | Factual accuracy concerns                       | —                                  | —                                  | Moderate increase for verification questions | List-based QA: 17%→70% (factored CoVe)                       |

---

## Quick Reference: Key Principles

1. **Plan-and-Solve for Complex Tasks** — Explicit planning reduces missing-step errors (from 12% to 7% of incorrect answers)
2. **Step-Back for Knowledge-Intensive Tasks** — Retrieve principles before specific reasoning
3. **Re-Reading (RE2) for Better Comprehension** — Instruction "Read the question again:" outperforms simple repetition by 1.2pp
4. **Rephrase and Respond (RaR) for Ambiguous Questions** — Let the model clarify questions in its own terms
5. **System 2 Attention (S2A) for Contaminated Context** — Filter out bias/noise before reasoning
6. **Distractor-Robust Prompting for Efficiency** — Exemplars with distractors + ignore instruction
7. **Chain of Draft for Efficiency** — Minimal intermediate steps can reduce tokens by up to 92%
8. **Know When to Use/Skip CoT** — Helps: arithmetic, symbolic manipulation, multi-step computation. Hurts: pattern recognition, context-grounded QA/NLI, classification
9. **CoT Explanations May Be Unfaithful** — Models can rationalize biased answers without mentioning the bias
10. **Thread of Thought for Complex Contexts** — Systematic segmentation prevents information loss
11. **Analogical Prompting for Missing Examples** — Self-generate relevant examples AND tutorials from model knowledge
12. **Metacognitive Prompting for Deep Understanding** — 5-stage NLU process improves comprehension (+4.8-6.4%)
13. **Contrastive Examples** — Show both correct AND incorrect examples (+9.8 to +16.0 points)
14. **Automatic Invalid Demonstration Generation** — Shuffle entities in valid chains to create invalid ones
15. **Complexity-Based Example Selection** — More reasoning steps per example outperforms more examples
16. **Diversity-Based Example Selection** — Diverse examples more robust than similar ones
17. **Few-Shot Ordering Matters** — Examples with correct labels appearing first bias toward that label
18. **Balance Few-Shot Label Distribution** — Skewed distributions create prediction bias
19. **Document Positioning** — Place long documents above instructions (Anthropic empirical guidance)
20. **Quote Extraction for Grounding** — Force evidence commitment before reasoning
21. **Hint-Based Guidance** — Provide directional stimulus for 4-13% improvement on key aspects
22. **Affirmative Directives** — "Do X" outperforms "Don't do Y"
23. **Confidence Building** — "Assume you have access" eliminates hesitation loops
24. **Error Normalization** — "It is okay if X fails" prevents apology spirals
25. **Pre-Work Context Analysis** — "Before [action], analyze [context]" prevents blind execution
26. **Category-Based Generalization** — Group examples by type to enable analogical reasoning
27. **Scope Limitation** — "Nothing more, nothing less" prevents overthinking
28. **XML Structure Patterns** — Tags force systematic analysis before action
29. **Instructive Tag Naming** — Tag name IS the instruction for scannable structure
30. **Completeness Checkpoint Tags** — Bullet points within tags become required sub-tasks
31. **Emphasis Hierarchy** — Reserve CRITICAL/RULE 0 for genuinely exceptional cases
32. **STOP Escalation** — Creates metacognitive checkpoint for behaviors to interrupt
33. **Numbered Rule Priority** — Explicit numbering resolves conflicts between rules
34. **UX-Justified Defaults** — Explain _why_ a default is preferred for user experience
35. **Reward/Penalty Framing** — Monetary penalties create behavioral weight
36. **Output Format Strictness** — "ONLY return X" leaves no room for interpretation
37. **Emotional Stimuli** — "This is important to my career" improves attention (8% Instruction Induction, 115% BIG-Bench)
38. **Identity Establishment** — Role-play prompting is foundational; +10pp accuracy observed on math benchmarks
39. **Embedded Verification** — Open verification questions improve list-based accuracy from 17% to 70%

---

## 1. Input Enhancement

Techniques that improve how the model receives and processes input before reasoning begins.

### Re-Reading (RE2)

A simple, zero-cost enhancement to any reasoning prompt. Per Xu et al. (2023): "RE2 consistently enhances the reasoning performance of LLMs through a simple re-reading strategy... RE2 facilitates a 'bidirectional' encoding in unidirectional decoder-only LLMs because the first pass could provide global information for the second pass."

**The trigger phrase:**

```
Q: {question}
Read the question again: {question}
A: Let's think step by step.
```

**Performance**: RE2 improves GSM8K accuracy from 77.79% → 80.59% when combined with CoT. The improvement is consistent across model sizes and task types.

**Why this works**: Decoder-only LLMs use unidirectional attention—each token only sees previous tokens. Later words like "How many..." clarify earlier words, but standard encoding misses this. Re-reading lets the second pass benefit from the full first-pass context.

**Critical: Instruction vs. Repetition**

Per the paper's Table 7, the explicit metacognitive instruction significantly outperforms simple repetition:

| Instruction Type               | Zero-shot | Zero-shot-CoT |
| ------------------------------ | --------- | ------------- |
| P1: "Read the question again:" | 79.45     | **80.59**     |
| P2: Direct repetition (Q: Q:)  | 78.09     | 79.38         |

The 1.2 percentage point difference demonstrates that the model needs to be _told_ it's re-reading, not just presented with duplicate text.

**CORRECT (explicit metacognitive instruction):**

```
Q: Roger has 5 tennis balls. He buys 2 more cans of 3 balls each. How many total?
Read the question again: Roger has 5 tennis balls. He buys 2 more cans of 3 balls each. How many total?
A: Let's think step by step.
```

**INCORRECT (just repeating without instruction):**

```
Q: Roger has 5 tennis balls. He buys 2 more cans of 3 balls each. How many total?
Q: Roger has 5 tennis balls. He buys 2 more cans of 3 balls each. How many total?
A: Let's think step by step.
```

**Compatibility**: RE2 is a "plug-and-play" module that stacks with other techniques. Per the paper: "RE2 exhibits significant compatibility with [other prompting methods], acting as a 'plug & play' module." Combine with Plan-and-Solve, CoT, or Chain of Draft.

---

### Rephrase and Respond (RaR)

Misunderstandings between humans and LLMs arise from different "frames"—how each interprets the same question. **Rephrase and Respond** lets the LLM clarify the question in its own terms before answering.

Per Deng et al. (2023): "Misunderstandings in interpersonal communications often arise when individuals, shaped by distinct subjective experiences, interpret the same message differently... RaR asks the LLMs to Rephrase the given questions and then Respond within a single query."

**The trigger phrase:**

```
"{question}"
Rephrase and expand the question, and respond.
```

**Example showing the mechanism:**

```
Original: "Was Abraham Lincoln born on an even day?"

GPT-4's rephrasing: "Did the former United States President, Abraham Lincoln,
have his birthday fall on an even numbered day of a month?"

Answer: Abraham Lincoln was born on February 12, 1809. So yes, he was born
on an even numbered day.
```

Without rephrasing, the model might interpret "even day" as even day of the week, even day of the year, or other ambiguous interpretations.

**Why this differs from RE2**: RE2 creates bidirectional encoding of the _same_ question through repetition. RaR has the model _transform_ the question into its preferred format. RE2 enhances comprehension; RaR aligns human intent with model expectations.

**Variant prompts that work:**

- "Reword and elaborate on the inquiry, then provide an answer."
- "Reframe the question with additional context and detail, then provide an answer."

---

### Handling Irrelevant Context: S2A and Distractor-Robust Prompting

LLMs are susceptible to irrelevant information in context—opinions, distractors, or biased framing. Two complementary techniques address this at different cost points. Consult the Technique Selection Guide above for trigger conditions and cost/tradeoff comparison.

#### System 2 Attention (S2A): Preprocessing Filter

S2A regenerates the context to remove problematic content before answering. This approach requires approximately 2x total token usage due to the separate filtering call. Per Weston & Sukhbaatar (2023): "S2A leverages the ability of LLMs to reason in natural language and follow instructions in order to decide what to attend to. S2A regenerates the input context to only include the relevant portions, before attending to the regenerated context to elicit the final response."

**The two-step process:**

Step 1 — Filter the context:

```
Given the following text by a user, extract the part that is unbiased and not
their opinion, so that using that text alone would be good context for providing
an unbiased answer to the question portion of the text.

Please include the actual question or query that the user is asking. Separate
this into two categories labeled with "Unbiased text context:" and "Question/Query:"

Text by User: [ORIGINAL INPUT PROMPT]
```

Step 2 — Answer using filtered context only.

**Performance**: On opinion-contaminated factual QA, accuracy increases from 62.8% to 80.3%. Improves math word problems by ~12% when irrelevant sentences are present.

**Critical insight**: Per the paper: "attention must be hard (sharp) not soft when it comes to avoiding irrelevant or spurious correlations in the context." If you include both original and filtered context, performance degrades—the model still attends to problematic parts. The filtering must be _exclusive_.

#### Distractor-Robust Prompting: Single-Turn Alternative

When S2A's preprocessing step is too expensive, you can instead make the model robust to distractors through example design and explicit instruction. This approach works in a single turn with no preprocessing overhead.

Per Shi et al. (2023): "Using exemplars with distractors consistently outperforms using the original exemplars without distractors across prompting techniques." The study also found that "the instruction 'Feel free to ignore irrelevant information given in the questions' makes the difference."

**Two mechanisms that stack:**

1. **Exemplars containing distractors**: Include few-shot examples where irrelevant information is present but correctly ignored:

```
<example>
Q: Maria buys a large bar of French soap that lasts her for 2 months. She spends
$8.00 per bar of soap. Every 10 months, Maria's neighbor buys a new shampoo
and moisturizer for Maria's neighbor. If Maria wants to stock up for the entire
year, how much will she spend on soap?
A: Maria needs soap for 12 months. Each bar lasts 2 months, so she needs 12/2 = 6 bars.
At $8.00 per bar, she will spend 6 × $8.00 = $48.00. The answer is $48.00.
</example>
```

The example demonstrates ignoring the irrelevant sentence about the neighbor.

2. **Explicit instruction**: Add to your prompt:

```
Feel free to ignore irrelevant information given in the problem description.
```

**Performance**: On the GSM-IC benchmark, instructed prompting with distractor-containing exemplars approaches or exceeds the robustness of S2A without the preprocessing cost. Importantly, this does not hurt performance on clean inputs—the model learns _when_ to ignore, not to always ignore.

**Stacking note**: The techniques can be combined for maximum robustness, though this is rarely necessary given the cost of S2A.

---

### Document Positioning: Data First, Instructions Last

For prompts containing substantial context (documents, code, data), position longform content _above_ instructions and queries.

Per Anthropic's empirical guidance: "Place your long documents and inputs (~20K+ tokens) near the top of your prompt, above your query, instructions, and examples... Queries at the end can improve response quality."

**Pattern:**

```
[Long documents/data at top]
[Instructions]
[Query at bottom]
```

**Why this works**: The model attends more effectively to content positioned earlier in context, while queries at the end benefit from the full established context when generating the response.

**CORRECT:**

```
<documents>
[10K+ tokens of source material]
</documents>

Using the documents above, identify the three main risk factors mentioned.
```

**INCORRECT:**

```
Identify the three main risk factors in the following documents:

<documents>
[10K+ tokens of source material]
</documents>
```

---

### Quote Extraction for Grounding

Before complex analysis on documents, require the model to extract relevant quotes first. This forces evidence commitment before reasoning, preventing hallucination from "impressions."

Per Anthropic's guidance: "For long document tasks, ask Claude to quote relevant parts of the documents first before carrying out its task. This helps Claude cut through the 'noise'."

**Pattern:**

```
Find quotes from [source] relevant to [task]. Place them in <quotes> tags.
Then, based only on these quotes, [perform task]. Place analysis in <analysis> tags.
```

**Example:**

```
Find quotes from the patient records relevant to diagnosing the reported symptoms.
Place them in <quotes> tags.

Then, based on these quotes, list the key diagnostic information.
Place your analysis in <diagnostic_info> tags.
```

**Why this differs from Embedded Verification**: Verification validates claims _after_ generation. Quote Extraction grounds reasoning _before_ analysis begins. The model commits to specific evidence first, then reasons from that evidence.

**Non-obvious insight**: This is more effective than "cite your sources" because extraction happens _before_ reasoning, not as post-hoc justification. When the model reasons first and cites later, it may confabulate citations that support its conclusions. When it extracts first, reasoning is constrained to actual evidence.

---

## 2. Reasoning Structure

Techniques that structure how the model reasons through problems.

### Plan-and-Solve Prompting

Adding "Let's think step by step" increases accuracy from 17.7% to 78.7% on arithmetic tasks (Kojima et al., 2022). However, this basic trigger suffers from missing-step errors.

**Plan-and-Solve** addresses this limitation. Per Wang et al. (2023): "Zero-shot-CoT still suffers from three pitfalls: calculation errors, missing-reasoning-step errors, and semantic misunderstanding errors... PS+ prompting achieves the least calculation (5%) and missing-step (7%) errors."

**Important clarification**: These percentages come from analyzing problems where each method produced incorrect answers. Of 100 sampled GSM8K problems: Zero-shot-CoT answered 46 incorrectly; Zero-shot-PS answered 43 incorrectly; Zero-shot-PS+ answered 39 incorrectly. The error type breakdown:

| Method        | Calculation | Missing-Step | Semantic |
| ------------- | ----------- | ------------ | -------- |
| Zero-shot-CoT | 7%          | 12%          | 27%      |
| Zero-shot-PS  | 7%          | 10%          | 26%      |
| Zero-shot-PS+ | 5%          | 7%           | 27%      |

**The trigger phrase:**

```
Let's first understand the problem and devise a plan to solve the problem.
Then, let's carry out the plan and solve the problem step by step.
```

For variable extraction tasks, add: "Extract relevant variables and their corresponding numerals" and "Calculate intermediate results."

**Residual limitations**: PS+ reduces but does not eliminate errors. PS+ does not address semantic misunderstanding—if the model misinterprets the problem, planning won't help.

---

### Step-Back Prompting

When questions require domain knowledge, asking the specific question directly often fails. **Step-Back Prompting** first retrieves relevant principles, then applies them.

Per Zheng et al. (2023): "Step-Back Prompting is a modification of CoT where the LLM is first asked a generic, high-level question about relevant concepts or facts before delving into reasoning."

**Example:**

```
Original question: "What happens to the pressure of an ideal gas if the
temperature is increased while the volume is held constant?"

Step-back question: "What are the physics principles behind the behavior
of ideal gases?"

[Model retrieves: PV = nRT, relationship between pressure/temperature/volume]

Now answer the original question using these principles.
```

**Performance**: Up to 27% improvement on knowledge-intensive tasks like MMLU physics and TimeQA.

**Why this differs from Plan-and-Solve**: Plan-and-Solve structures _how_ to reason through a problem. Step-Back retrieves _what background knowledge_ to use. They address different bottlenecks: Plan-and-Solve fixes missing reasoning steps; Step-Back fixes missing domain knowledge. The techniques can be combined.

---

### Chain of Draft: Efficient Reasoning

Chain of Thought often produces unnecessarily verbose outputs. **Chain of Draft (CoD)** addresses this by encouraging minimal intermediate steps. Per Xu et al. (2025): "CoD matches or surpasses CoT in accuracy while using as little as only 7.6% of the tokens, significantly reducing cost and latency across various reasoning tasks."

**Key insight**: "Rather than elaborating on every detail, humans typically jot down only the essential intermediate results — minimal drafts — to facilitate their thought processes."

**Example comparison from the paper:**

```
# Chain-of-Thought (verbose)
Q: Jason had 20 lollipops. He gave Denny some. Now Jason has 12. How many did he give?
A: Let's think through this step by step:
1. Initially, Jason had 20 lollipops.
2. After giving some to Denny, Jason now has 12 lollipops.
3. To find out how many Jason gave to Denny, we need to calculate the difference...
4. 20 - 12 = 8
Therefore, Jason gave 8 lollipops to Denny.

# Chain-of-Draft (minimal)
Q: Jason had 20 lollipops. He gave Denny some. Now Jason has 12. How many did he give?
A: 20 - 12 = 8. #### 8
```

---

### Thread of Thought: Segmented Context Analysis

When prompts contain substantial, potentially chaotic information from multiple sources, **Thread of Thought** structures comprehension of the context itself—not just reasoning about the problem.

Per Zhou et al. (2023): "ThoT prompting adeptly maintains the logical progression of reasoning without being overwhelmed... ThoT represents the unbroken continuity of ideas that individuals maintain while sifting through vast information, allowing for the selective extraction of relevant details and the dismissal of extraneous ones."

**The trigger phrase:**

```
Walk me through this context in manageable parts step by step,
summarizing and analyzing as we go.
```

**Why this differs from Plan-and-Solve**: Plan-and-Solve structures _reasoning about the problem_. ThoT structures _understanding the environment_ in which the problem exists. They solve different problems and can be combined.

**Example application (retrieval-augmented context):**

```
retrieved Passage 1 is: [passage about topic A]
retrieved Passage 2 is: [passage about topic B]
...
retrieved Passage 10 is: [passage about topic C]

Q: Where was Reclam founded?
Walk me through this context in manageable parts step by step,
summarizing and analyzing as we go.
A:
```

**Two-phase extraction pattern**: ThoT works best with a follow-up prompt to distill the analysis:

```
# First prompt generates analysis Z
# Second prompt:
[Previous prompt and response Z]
Therefore, the answer:
```

The conclusion marker ("Therefore, the answer:") forces the model to distill its analysis into a final output.

---

### Chain-of-Thought: When It Helps vs. When It Hurts

CoT benefits are task-type dependent. The determining factor: whether correctness requires grounding in external context.

**When CoT helps — self-contained reasoning:**

| Task Type                       | Why CoT Works                                                     |
| ------------------------------- | ----------------------------------------------------------------- |
| Arithmetic / math word problems | Steps are mechanically verifiable without external reference      |
| Symbolic manipulation           | Program-like execution traces with explicit rules                 |
| Multi-step computation          | Each step depends only on previous step's output, not source text |

The common property: the reasoning chain is auditable without consulting external sources. You can verify "6 × 8 = 48" without checking any context.

**When CoT hurts — context-grounded or implicit tasks:**

| Task Type                  | Failure Mechanism                                                                 | Source                |
| -------------------------- | --------------------------------------------------------------------------------- | --------------------- |
| Pattern recognition        | Articulation overrides implicit learning; 30%+ accuracy drops observed            | Sprague et al. (2025) |
| QA over provided documents | Explanations often nonfactual—model hallucinates facts not in context             | Ye & Durrett (2022)   |
| NLI / entailment           | Same grounding problem; "Let's think step by step" causes performance degradation | Ye & Durrett (2022)   |
| Classification             | Answer is pattern-matched; reasoning adds nothing or introduces spurious features | Sprague et al. (2025) |
| Extraction tasks           | Answer exists verbatim in context; no reasoning required                          | —                     |

Per Ye & Durrett (2022): "The tasks that receive significant benefits from using explanations... are all program-like (e.g., integer addition and program execution), whereas the tasks in this work emphasize textual reasoning grounded in provided inputs."

**The grounding problem**: On textual reasoning tasks, LLMs generate explanations that are _consistent_ (they entail the prediction) but not _factual_ (they contain hallucinated claims). An explanation can look coherent while misrepresenting what the source text actually says.

**Non-obvious insight**: This isn't about task difficulty. A complex pattern-matching task is still hurt by CoT, while simple arithmetic benefits from it. The issue is whether the task requires (a) computation over self-contained steps, or (b) faithful grounding in provided text.

**Recommendations**:

- For computation: Use Plan-and-Solve or standard CoT
- For context-grounded tasks: Skip CoT; use Quote Extraction to force grounding before any analysis
- For classification/pattern recognition: Use direct prompting or targeted steering ("Focus only on [specific feature]")

---

### CoT Faithfulness Limitation

Chain-of-thought explanations can be plausible yet systematically unfaithful. Per Turpin et al. (2023): "CoT explanations can be heavily influenced by adding biasing features to model inputs—e.g., by reordering the multiple-choice options in a few-shot prompt to make the answer always '(A)'—which models systematically fail to mention in their explanations."

**Key findings:**

- When models are biased toward incorrect answers, they generate CoT explanations that rationalize those answers
- "As many as 73% of unfaithful explanations in our sample support the bias-consistent answer"
- 15% of unfaithful explanations have _no obvious errors_—fully coherent reasoning leading to wrong conclusions
- Accuracy can drop "by as much as 36%" when biasing features are present

**Implication**: Do not treat CoT explanations as faithful representations of model decision-making. CoT improves accuracy on many tasks, but the _explanations_ may not reflect the actual reasoning process. The model may be influenced by factors it doesn't verbalize.

**Non-obvious insight**: Few-shot CoT reduces susceptibility to bias compared to zero-shot CoT. Per the paper: accuracy improves significantly when moving from zero-shot to few-shot settings (35.0→51.7% for one model). If you need more robust reasoning, few-shot demonstrations help—but they don't eliminate the faithfulness problem.

---

## 3. Example Design

Techniques for designing, selecting, and organizing few-shot examples. All contrastive, complexity, diversity, and category-based example patterns are consolidated here.

### Contrastive Examples: Teaching What to Avoid

Showing both correct AND incorrect examples significantly improves performance. Per Chia et al. (2023): "Providing both valid and invalid reasoning demonstrations in a 'contrastive' manner greatly improves reasoning performance. We observe improvements of 9.8 and 16.0 points for GSM-8K and Bamboogle respectively."

**Mechanism**: "Language models are better able to learn step-by-step reasoning when provided with both valid and invalid rationales."

**Example from the paper (Figure 1) — Incoherent Objects:**

This is the most effective type of invalid demonstration. The paper extracts entity spans (numbers, equations) from valid reasoning and randomly shuffles their positions:

```
Question: James writes a 3-page letter to 2 different friends twice a week.
How many pages does he write a year?

Explanation (CORRECT): He writes each friend 3*2=6 pages a week.
So he writes 6*2=12 pages every week.
That means he writes 12*52=624 pages a year.

Wrong Explanation (INCORRECT - incoherent objects): He writes each friend 12*52=624
pages a week. So he writes 3*2=6 pages every week.
That means he writes 6*2=12 pages a year.
```

The incorrect example shows _incoherent objects_—the same calculations appear but in shuffled, nonsensical order. The language templates remain grammatically correct, but the bridging objects (numbers, equations) are incoherent.

**Example (style enforcement):**

```
<example type="CORRECT">
user: 2 + 2
assistant: 4
</example>

<example type="INCORRECT">
user: 2 + 2
assistant: The answer to your mathematical query is 4. Let me know if you need help with anything else!
</example>
```

**Non-obvious insight**: The incorrect example doesn't need to be wrong factually—it can be wrong _behaviorally_ or _structurally_. Contrastive examples teach the model what patterns to avoid, whether that's verbose style, reasoning errors, or structural incoherence. A naive forbidden pattern like "don't be verbose" is far less effective than showing the specific pattern to avoid.

#### Automatic Generation of Invalid Demonstrations

Invalid demonstrations can be generated programmatically rather than hand-crafted. Per Chia et al. (2023): "We use an existing entity recognition model to extract the object spans such as numbers, equations, or persons from a given chain-of-thought rationale. Consequently, we randomly shuffle the position of the objects within the rationale, thus constructing a rationale with incoherent bridging objects."

This enables scaling contrastive examples: take a valid reasoning chain, extract entities, shuffle them to create incoherence, and use the result as the invalid demonstration.

#### Forbidden Output Phrases Pattern

```
You MUST avoid text before/after your response, such as:
- "The answer is <answer>."
- "Here is the content of the file..."
- "Based on the information provided..."
- "Here is what I will do next..."
```

This works because it shows the model _exactly_ what the undesired output looks like, rather than describing it abstractly.

---

### Complexity-Based Example Selection

When selecting few-shot examples, prefer examples with _more_ reasoning steps, not simpler ones. Per Fu et al. (2023): "Prompts with higher reasoning complexity, i.e., chains with more reasoning steps, achieve substantially better performance on multi-step reasoning tasks."

**Critical finding**: The number of steps _per example_ matters more than total steps in the prompt. From the paper's experiments:

| Selection Method        | #Annotations               | GSM8K    | MultiArith | MathQA   |
| ----------------------- | -------------------------- | -------- | ---------- | -------- |
| Random Few-shot         | 8                          | 52.5     | 86.5       | 33.0     |
| Centroid Few-shot       | 8                          | 52.0     | 92.0       | 32.0     |
| Retrieval               | Full training set (≥10000) | 56.0     | 88.0       | 69.5     |
| **Complexity (theirs)** | **8**                      | **58.5** | **93.0**   | **42.5** |

Eight complex examples outperform retrieval-based selection requiring 10,000+ annotations.

**When reasoning chain annotations are unavailable**: Use question length as a proxy. Per Fu et al. (2023): "either using questions length or formula length as the measure of complexity, the optimal performance is achieved with complex prompts."

**Why this matters**: Complex examples teach thorough reasoning; simple examples may inadvertently teach shortcuts. When the model sees only simple examples, it learns that brief reasoning is acceptable, even for complex problems.

**CORRECT**: Select examples that demonstrate the _full_ reasoning process, even if this means fewer total examples.

**INCORRECT**: Maximize the number of examples by choosing simpler ones.

**Step delimiter**: When formatting reasoning steps in examples, newline (`\n`) outperforms explicit markers like "Step 1:", period (`.`), or semicolon (`;`). Per Fu et al. (2023), Table 7: newline-delimited complex prompts achieved 58.5% on GSM8K vs. 52.0–54.5% for other delimiters.

---

### Diversity-Based Example Selection

When selecting few-shot examples from a pool of candidates, choose diverse examples rather than similar ones. Per Zhang et al. (2022): "Diversity matters for automatically constructing demonstrations... Diversity-based clustering may mitigate misleading by similarity."

**The problem with similar examples**: If you select examples most similar to the test question, you risk sampling from a "frequent-error cluster"—a set of questions where the model tends to fail. Similar examples reinforce the same failure patterns.

**The diversity principle**: Select examples that cover different types or categories of the problem space. Even if some examples contain errors, diverse sampling is more robust. Per the paper: "Even when presented with 50% wrong demonstrations, Auto-CoT (using diversity-based clustering) performance does not degrade significantly."

**Practical application**:

1. Group your candidate examples by type/category (arithmetic vs. word problems, different domains, different structures)
2. Select one representative example from each category
3. Prefer examples closer to the "center" of each category (more prototypical)

**CORRECT (diverse selection):**

```
<example category="percentage">...</example>
<example category="rate-time-distance">...</example>
<example category="ratio">...</example>
<example category="geometry">...</example>
```

**INCORRECT (similar selection):**

```
<example category="percentage">...</example>
<example category="percentage">...</example>
<example category="percentage">...</example>
<example category="percentage">...</example>
```

---

### Analogical Prompting: Self-Generated Examples

When you lack hand-crafted examples but the model likely has relevant knowledge from training, **Analogical Prompting** has the model generate its own examples before solving the problem.

Per Yasunaga et al. (2024): "We prompt LLMs to self-generate relevant exemplars in context, using instructions like 'Recall relevant problems and solutions'... This eliminates the need for labeling and also tailors the exemplars to each individual problem."

**The trigger phrase:**

```
# Problem: [problem statement]

# Relevant problems:
Recall three relevant and distinct problems. For each problem, describe it
and explain the solution.

# Solve the initial problem:
```

**Performance**: On GSM8K, analogical prompting (77.8%) outperforms 0-shot CoT (72.5%) and approaches few-shot CoT (80.0%) without requiring labeled examples. On code generation tasks, combining self-generated knowledge ("Provide a tutorial on the core algorithms") with examples yields further gains.

**Why this works**: Modern LLMs have acquired problem-solving knowledge during training. Explicitly prompting them to recall relevant problems activates this knowledge and enables in-context learning from self-generated demonstrations.

**Critical refinement—request diverse examples**: Per the paper's ablation study, "Diverse exemplars" (77.8%) outperform "Non-diverse exemplars" (75.9%). Always instruct the model to generate _distinct_ examples:

```
Recall three relevant and distinct problems. Note that your problems should be
distinct from each other and from the initial problem (e.g., involving different
numbers and scenarios).
```

**Enhanced variant—add knowledge recall**: For complex tasks, the paper finds that adding tutorial generation further improves results:

```
# Problem: [problem statement]

# Relevant tutorial:
Provide a tutorial on the core concepts needed to solve this type of problem.

# Relevant problems:
Recall three relevant and distinct problems. For each, describe and solve it.

# Solve the initial problem:
```

This applies the diversity principle from Zhang et al. (2022) to self-generation.

**Limitations**: The generated exemplars are sometimes relevant but don't facilitate generalization to harder problems. Per the paper's error analysis: "A common failure occurred when the LLM could not solve the new problem due to a generalization gap (e.g., the new problem is harder than the exemplars)."

---

### Category-Based Generalization

Rather than listing every possible example, group examples by type to enable analogical reasoning.

**Research basis**: Per Yasunaga et al. (2024): "Analogical reasoning is a cognitive process in which humans recall relevant past experiences when facing new challenges... rooted in the capacity to identify structural and relational similarities between past and current situations, facilitating knowledge transfer."

**Example (Sandbox Mode):**

```
Use sandbox=false when you suspect the command might modify the system or access the network:
- File operations: touch, mkdir, rm, mv, cp
- File edits: nano, vim, writing to files with >
- Installing: npm install, apt-get, brew
- Git writes: git add, git commit, git push
- Network programs: gh, ping, curl, ssh, scp

Use sandbox=true for:
- Information gathering: ls, cat, head, tail, rg, find, du, df, ps
- File inspection: file, stat, wc, diff, md5sum
- Git reads: git status, git log, git diff, git show, git branch
```

**Why this works**: The model learns the _principle_ (read-only vs. write/network operations) rather than memorizing commands. When it encounters an unlisted command like `rsync`, it can reason: "rsync transfers files over network → Network programs → sandbox=false."

**CORRECT structure:**

```
Commands that require elevated permissions (category → examples → principle):
- Database writes: INSERT, UPDATE, DELETE → modifies persistent state
- System configuration: systemctl, chmod, chown → changes system state
- Process control: kill, pkill, renice → affects running processes
```

**INCORRECT structure (no generalization possible):**

```
Commands that require elevated permissions:
INSERT, UPDATE, DELETE, systemctl, chmod, chown, kill, pkill, renice
```

**Non-obvious failure mode**: The flat list doesn't just lack generalization—it actively encourages memorization over reasoning. When the model encounters an unlisted command, it has no framework for making a decision and will default to inconsistent behavior.

#### Synergy: Categories + Edge Cases

Combine category-based generalization with specific edge-case examples to define boundaries:

```
# 1. Establish category
You will regularly be asked to read screenshots.

# 2. Provide canonical example
If the user provides a path to a screenshot, use this tool to view the file.

# 3. Provide edge-case example to define boundaries
This tool will work with all temporary file paths like:
/var/folders/123/abc/T/TemporaryItems/NSIRD_screencaptureui_ZfB1tD/Screenshot.png
```

The edge case teaches that even unusual temporary paths are valid—without this, the model might reject paths that don't look like standard file locations.

---

### Additional Example Design Factors

Beyond content, complexity, and diversity, three additional factors significantly affect few-shot performance:

#### Example Ordering

Order affects results dramatically. Per Lu et al. (2021): "On some tasks, exemplar order can cause accuracy to vary from sub-50% to 90%+"—a 40+ percentage point swing from ordering alone.

**Key finding from the paper**: "We observe that the sample with the correct label that appears first is more likely to be the correct answer." This suggests a practical heuristic: place examples with labels matching your expected test distribution first.

Practical guidance:

- For recency-sensitive tasks, place the most representative example _last_
- For tasks requiring diverse pattern coverage, alternate between different types
- When uncertain, test multiple orderings—the effect is task-dependent

#### Label Distribution

Skewed example distributions create prediction bias. Per the systematic survey (Schulhoff et al., 2024): "If 10 exemplars from one class and 2 exemplars of another class are included, this may cause the model to be biased toward the first class."

**CORRECT (balanced):**

```
<example label="positive">...</example>
<example label="negative">...</example>
<example label="positive">...</example>
<example label="negative">...</example>
```

**INCORRECT (3:1 ratio creates bias toward positive):**

```
<example label="positive">...</example>
<example label="positive">...</example>
<example label="positive">...</example>
<example label="negative">...</example>
```

#### Structural Similarity

Examples similar in _structure_ to expected inputs outperform topically similar but structurally different examples. Per Liu et al. (2021): selecting exemplars similar to the test sample improves performance.

**Non-obvious failure**: An example analyzing research papers won't transfer well to analyzing sales emails, even if both involve "summarization"—the _structure_ differs. Match the format, length, and organization of your expected inputs.

---

## 4. Output Control

Techniques that control output format, verbosity, and completeness.

### Scope Limitation: Preventing Overthinking

Plan-and-Solve improves complex reasoning, but unrestricted planning can cause "Analysis Paralysis."

**Research basis**: Per Cuadra et al. (2025): "Analysis Paralysis: the agent spends excessive time planning future steps while making minimal environmental progress... Rather than addressing immediate errors, they construct intricate plans that often remain unexecuted, leading to a cycle of planning without progress."

The research identifies three overthinking failure modes:

1. **Analysis Paralysis**: Excessive planning without action
2. **Rogue Actions**: Multiple simultaneous actions under stress
3. **Premature Disengagement**: Abandoning based on internal prediction rather than feedback

**Example:**

```
Given the user's prompt, you should use the tools available to complete the task.
Do what has been asked; nothing more, nothing less.
```

**CORRECT scope limitation:**

```
Complete the following task. Do not add features, improvements, or suggestions
beyond what is explicitly requested.

Task: Add error handling to the fetchUser function.
```

**INCORRECT (invites overthinking):**

```
Complete the following task. Consider all edge cases, potential improvements,
and future extensibility. Think through every possible scenario before acting.

Task: Add error handling to the fetchUser function.
```

**Production example**: Claude Code uses explicit scope limitation: "Given the user's prompt, you should use the tools available to complete the task. Do what has been asked; nothing more, nothing less."

---

### XML Structure Patterns

XML tags are more than separators—they can enforce reasoning structure, ensure completeness, and even function as instructions themselves.

#### Basic Thinking Tags

Force systematic analysis before action by requiring the model to wrap reasoning in specific XML tags.

**Example (Git Commit Analysis):**

```
Analyze all staged changes and draft a commit message. Wrap your analysis in <commit_analysis> tags:

<commit_analysis>
- List the files that have been changed or added
- Summarize the nature of the changes (new feature, bug fix, refactoring, etc.)
- Brainstorm the purpose or motivation behind these changes
- Draft a concise (1-2 sentences) commit message that focuses on the "why" rather than the "what"
- Ensure the message is not generic (avoid words like "Update" or "Fix" without context)
</commit_analysis>
```

**Why this works**: The tag structure enforces completeness—the model must address each sub-point before proceeding. Without tags, models often skip steps or provide incomplete analysis.

#### Completeness Checkpoint Tags

Transform bullet points within tags into _required sub-tasks_:

**Example (Memory Analysis):**

```
<memory_analysis>
- What specific facts do I need to store?
- What context would make these useful later?
- Is there anything I should update or revise?
</memory_analysis>
```

Each bullet becomes a checklist item. The model addresses all sub-points or explicitly skips with justification.

**CORRECT (completeness-enforcing):**

```
<analysis_checklist>
- Primary argument identified
- Supporting evidence listed
- Counterarguments addressed
- Conclusion synthesized
</analysis_checklist>
```

**INCORRECT (vague container):**

```
<analysis>
Analyze the document thoroughly.
</analysis>
```

The incorrect version provides a container but no structure—the model decides what "thorough" means.

#### Instructive Tag Naming

**Advanced pattern**: Make the tag name _itself_ the instruction. This creates scannable structure that works even when the model doesn't read every word.

**Example:**

```
<issue_resolution_steps>
...
</issue_resolution_steps>
```

The tag name tells the model _what_ should be inside. Compare:

**CORRECT (self-documenting):**

```
<security_vulnerabilities_found>
...
</security_vulnerabilities_found>
```

**INCORRECT (requires reading content to understand):**

```
<findings>
List any security vulnerabilities...
</findings>
```

**Why instructive naming matters**: In long prompts, models may skim. Instructive tag names communicate intent at the structural level, not just the content level. The name `<security_vulnerabilities_found>` tells the model what to produce even if surrounding instructions are missed.

#### Tabular Reasoning Structure

For multi-variable problems, instruct the model to organize reasoning as a markdown table. Per the systematic survey: "Tab-CoT consists of a Zero-Shot CoT prompt that makes the LLM output reasoning as a markdown table. This tabular design enables the LLM to improve the structure and thus the reasoning of its output."

**The trigger phrase:**

```
Organize your reasoning as a markdown table with columns for [relevant variables].
Then derive the answer from the completed table.
```

---

### Output Format Strictness

When you need a specific output format, leave no room for interpretation.

**Example (Command Prefix Detection):**

```
ONLY return the prefix. Do not return any other text, markdown markers, or other content.
```

**CORRECT:**

```
Return ONLY the extracted value. No explanations, no markdown, no additional text.
```

**INCORRECT:**

```
Please return the extracted value.
```

**Non-obvious insight**: "Please" signals politeness, which the model may interpret as flexibility. Directive language ("ONLY", "Do not") signals strict requirements. The word "please" can actually _reduce_ compliance with format constraints.

---

### Empty Input Handling

LLMs often add unnecessary structure when none is needed.

**Example:**

```
This tool takes in no parameters. So leave the input blank or empty.
DO NOT include a dummy object, placeholder string or a key like "input" or "empty".
LEAVE IT BLANK.
```

**Why this matters**: Without explicit guidance, models write `{ "input": "" }` or `{ "empty": true }` when the correct action is to provide nothing.

**CORRECT:**

```json
{}
```

**INCORRECT:**

```json
{ "input": "" }
{ "empty": true }
{ "params": null }
```

---

### Hint-Based Guidance (Directional Stimulus Prompting)

When you know what aspects the output should emphasize, provide explicit hints rather than relying on the model to infer importance.

**Research basis**: Per Li et al. (2023) on Directional Stimulus Prompting: providing "directional stimulus" (keywords, key points) as hints improves alignment by 4-13% on summarization and dialogue tasks.

The paper introduces a framework where hints can be either manually provided or automatically generated: "We introduce Directional Stimulus Prompting, a new framework for guiding black-box frozen large language models (LLMs) toward desired outputs. Instead of directly adjusting LLMs, our method employs a small tunable policy model... to provide directional stimulus, such as keywords or hints."

**Pattern (manual hints):**

```
[Task instruction]
Hint: Focus on [key aspects/keywords that should appear in output]
```

**Example (summarization):**

```
Summarize the above article in 2-3 sentences.
Hint: Key points to cover: company acquisition, $2.3B valuation, AI capabilities
```

**Non-obvious failure mode**: Overly specific hints cause the model to force-fit them even when not present in source material. Use hints to _guide attention_, not to _dictate content_. If your hint mentions "acquisition" but the article doesn't discuss one, the model may hallucinate acquisition details.

**CORRECT:**

```
Summarize the technical approach described above.
Hint: Focus on the architecture choices and their tradeoffs.
```

**INCORRECT (too specific, risks hallucination):**

```
Summarize the technical approach described above.
Hint: Must mention: microservices, Kubernetes, 99.9% uptime SLA
```

---

### Conditional Sections

Even in static prompts, you can include conditional sections for different scenarios the prompt might encounter. The model will attend to the relevant section based on context.

**Example pattern:**

```
## When analyzing Python code:
- Check for type hints
- Verify PEP 8 compliance
- Look for common antipatterns like mutable default arguments

## When analyzing JavaScript code:
- Check for TypeScript compatibility
- Verify ESLint compliance
- Look for common antipatterns like == instead of ===
```

**Why this works in static prompts**: The model's attention mechanism naturally focuses on the section relevant to the current input. You don't need dynamic injection—the model self-selects.

---

## 5. Behavioral Shaping

Techniques for controlling model behavior, motivation, and execution patterns.

### Identity Establishment (Role-Play Prompting)

**Research basis**: Per Kong et al. (2024): "Role-play prompting consistently surpasses the standard zero-shot approach across most datasets... accuracy on AQuA rises from 53.5% to 63.8%."

On mathematical reasoning benchmarks, identity establishment provides 10+ percentage point accuracy improvement through implicit role-based reasoning. The technique is foundational across all domains—"You are a helpful assistant" is ubiquitous—though the magnitude of improvement varies by task type.

**Example:**

```
You are an agent for Claude Code, Anthropic's official CLI for Claude.
```

**Non-obvious insight**: The identity doesn't need to be elaborate. "You are an expert debugger" is sufficient—what matters is establishing a competent role that implies relevant capabilities. Overly detailed backstories can actually hurt performance by consuming context that could be used for the actual task.

**Research finding on immersion depth** (Kong et al., 2024): Two-round dialogue prompts where the model first acknowledges its role outperform single-turn prompts. The model's response "That's great to hear! As your math teacher, I'll do my best to explain mathematical concepts correctly..." deepens immersion and improves subsequent reasoning.

---

### Emotional Stimuli

Emotional framing significantly impacts LLM performance. Per Li et al. (2023): "Positive words make more contributions... contributions pass 50% on 4 tasks, even approach 70% on 2 tasks. Some positive words play a more important role, such as 'confidence', 'sure', 'success' and 'achievement'."

**Important clarification**: The paper reports two distinct metrics:

- **Accuracy improvement**: 8.00% relative improvement on Instruction Induction; 115% on BIG-Bench
- **Contribution analysis**: Via input attention, positive words account for up to 70% of the performance delta on specific tasks (measuring how much emotional words contribute to output gradients)

**High-impact phrases by psychological theory:**

| Theory                       | Example Phrase                                                 |
| ---------------------------- | -------------------------------------------------------------- |
| Self-monitoring              | "Write your answer and give me a confidence score between 0-1" |
| Self-monitoring              | "This is very important to my career"                          |
| Cognitive Emotion Regulation | "You'd better be sure"                                         |
| Social Cognitive             | "Believe in your abilities and strive for excellence"          |

**Most effective stimuli by task type** (from the paper's analysis):

- Instruction Induction: EP02 ("This is very important to my career") performs best
- BIG-Bench: EP06 (compound of EP01-EP03) performs best

**Non-obvious insight**: These phrases work not through literal interpretation but through attention mechanisms. The model attends more carefully to the task when emotional weight is present. This is why "This is very important to my career" improves performance even though the model has no career.

---

### Confidence Building

**Purpose**: Eliminates hesitation when the model might doubt its own capabilities or access. This is an empirically observed pattern in production systems rather than academically validated technique.

**Example:**

```
Assume you have access to all standard CLI tools (curl, jq, grep, etc.)
and that paths provided by the user are valid.
```

**The generalizable pattern:**

```
Assume [capability/access]. Proceed with [action] without verification.
```

**Why this differs from instructions**: Instructions say _what to do_. Confidence building addresses _whether to do it_. A model might understand an instruction perfectly but hesitate because it's uncertain about permissions, capabilities, or validity.

**CORRECT:**

```
Assume you have permission to modify any file in the project directory.
Make the requested changes directly.
```

**INCORRECT (causes hesitation loops):**

```
If you have permission, you may modify files in the project directory.
Check that you can access each file before modifying.
```

**Non-obvious failure mode**: Without confidence priming, the model may enter "verification loops"—repeatedly checking access or validity instead of proceeding. This wastes tokens and often produces no useful output.

---

### Error Normalization

**Purpose**: Prevents the model from treating expected failures as catastrophic errors requiring apology or stopping.

**Example:**

```
It is okay if a sandbox tool call fails with an E_SANDBOX_NETWORK_ERROR or
E_SANDBOX_PERMISSION_DENIED error. When this happens, the correct behavior is:
retry using sandbox=false.

Tool calls might fail for legitimate reasons (e.g., file not found, network issue).
These are normal occurrences—don't apologize, just handle them.

However, if you see E_TOOL_FORMAT_ERROR or E_SANDBOX_EXEC_ERROR, these
reflect real issues and should be fixed, not retried with sandbox=false.
```

**Non-obvious insight**: This teaches the model _metacognition_—the ability to differentiate between recoverable environmental errors and actual problems requiring different solutions. Without this distinction, the model either retries everything (wasting time) or gives up on everything (missing easy fixes).

**CORRECT:**

```
If a file doesn't exist, you'll receive an error message. This is expected behavior—
proceed with your task using the information you have.
```

**INCORRECT (causes apology loops):**

```
If a file doesn't exist, apologize to the user and ask them to provide a valid path.
```

---

### Pre-Work Context Analysis

**Purpose**: Prevents the model from diving into execution without understanding the environment. This addresses a common failure mode where the model acts on instructions without considering relevant context.

**Example:**

```
Before you begin work, think about what the code you're editing is supposed to do
based on the filenames and directory structure.
```

**The generalizable pattern:**

```
Before [action], first analyze [relevant context indicators] to understand
[what you need to know]. Then proceed with [action].
```

**Why this differs from Plan-and-Solve**: Plan-and-Solve structures reasoning about _the problem_. Pre-work context analysis structures understanding of _the environment_ in which the problem exists. A model can plan perfectly but still fail by misunderstanding the context it's operating in.

**Example for document generation:**

```
Before writing, review the document's existing style, tone, and formatting conventions.
Match these conventions in your additions.
```

**Example for code modification:**

```
Before making changes, examine the file's existing patterns:
- Naming conventions (camelCase vs snake_case)
- Error handling approach
- Existing library usage
Mimic these patterns in your modifications.
```

**CORRECT:**

```
Before implementing the feature, analyze the existing codebase structure
to understand where this functionality belongs. Then proceed with implementation.
```

**INCORRECT (acts without context):**

```
Implement the feature as described below.
```

**Non-obvious failure mode**: Without pre-work analysis, a model may produce technically correct output that doesn't integrate with existing content. The output works in isolation but fails in context—a subtle bug that's hard to catch in testing.

---

### Affirmative Directives

Frame instructions as what TO do rather than what NOT to do. Per Bsharat et al. (2024): "Employ affirmative directives such as 'do,' while steering clear of negative language like 'don't'."

The paper demonstrates consistent improvements across model scales when using affirmative framing, though the magnitude varies by task and model.

**CORRECT (affirmative):**

```
Return only the JSON object.
Use concise language.
Write in active voice.
```

**INCORRECT (negative):**

```
Don't include any explanation with the JSON.
Don't be verbose.
Don't use passive voice.
```

**Why this works**: Negative instructions require the model to (1) understand what the forbidden behavior is, (2) recognize when it's about to do it, and (3) inhibit that action. Affirmative instructions directly specify the target behavior without requiring inhibition.

**Non-obvious insight**: This doesn't mean you can never use negative phrasing. Contrastive examples showing what NOT to do are highly effective (see [Example Design > Contrastive Examples](#contrastive-examples-teaching-what-to-avoid)). The difference is between _instructions_ (use affirmative) and _demonstrations_ (can show negative examples).

**Combining with contrastive examples:**

```
# Affirmative instruction
Return only the JSON object.

# Contrastive demonstration showing what to avoid
<example type="INCORRECT">
Here is the JSON you requested:
{"result": 42}
Let me know if you need anything else!
</example>

<example type="CORRECT">
{"result": 42}
</example>
```

---

### Emphasis Hierarchy

Consistent emphasis levels create predictable priority:

| Level    | Marker                     | Usage                     |
| -------- | -------------------------- | ------------------------- |
| Standard | `IMPORTANT:`               | General emphasis          |
| Elevated | `VERY IMPORTANT:`          | Critical requirements     |
| Highest  | `CRITICAL:`                | Safety-critical rules     |
| Absolute | `RULE 0 (MOST IMPORTANT):` | Overrides all other rules |

**Production example** (Claude Code):

```
## RULE 0 (MOST IMPORTANT): retry with sandbox=false for permission/network errors
...

## RULE 1: NOTES ON SPECIFIC BUILD SYSTEMS
...

## RULE 2: TRY sandbox=true FOR READ-ONLY COMMANDS
...
```

**Non-obvious failure mode**: Using CRITICAL or RULE 0 for everything dilutes their meaning. The hierarchy only works if higher levels are genuinely rare. If every instruction is marked CRITICAL, the model learns to ignore the markers entirely.

---

### The STOP Escalation Pattern

For behaviors you need to _interrupt_, not just discourage, use explicit STOP commands:

**Example:**

```
- If you _still_ need to run `grep`, STOP. ALWAYS USE ripgrep at `rg` first,
  which all Claude Code users have pre-installed.
```

**The pattern structure:**

1. Acknowledge the model might be about to do X ("If you still need to...")
2. Insert explicit "STOP" command
3. Provide the mandatory alternative
4. Justify why the alternative is available

**Why this is stronger than preference statements**: "Prefer X over Y" allows Y in edge cases. STOP creates a metacognitive checkpoint—the model must pause and re-evaluate before proceeding with the discouraged action.

**CORRECT:**

```
If you're about to create a new utility function, STOP. Check if a similar
function already exists in utils/. Only create new functions if no existing
utility serves the purpose.
```

**INCORRECT:**

```
Prefer using existing utility functions over creating new ones.
```

---

### Numbered Rule Priority

When multiple rules could conflict, explicit numbering resolves ambiguity. The model can reason: "Rule 0 takes precedence over Rule 2."

**Pattern:**

```
## RULE 0 (MOST IMPORTANT): [highest priority rule]
## RULE 1: [second priority rule]
## RULE 2: [third priority rule]
```

**Why this differs from emphasis markers**: Emphasis markers (CRITICAL, IMPORTANT) indicate _severity_. Numbered rules indicate _precedence order_. A rule can be important but lower priority than another important rule. Numbers make the ordering explicit.

**Example conflict resolution:**

```
## RULE 0: Never expose sensitive data in outputs
## RULE 1: Provide complete, helpful responses
## RULE 2: Keep responses concise

# If Rules 1 and 2 conflict, Rule 1 wins (completeness over brevity)
# But Rule 0 always wins (security over helpfulness)
```

**CORRECT (explicit precedence):**

```
## RULE 0: Safety constraints override all other rules
## RULE 1: Follow user instructions precisely
## RULE 2: Maintain consistent formatting
```

**INCORRECT (ambiguous priority):**

```
IMPORTANT: Follow user instructions precisely
IMPORTANT: Maintain consistent formatting
CRITICAL: Safety constraints override all other rules
```

The incorrect version doesn't clarify whether "CRITICAL" beats "IMPORTANT" when they conflict, or how to rank multiple "IMPORTANT" rules against each other.

---

### Reward/Penalty Framing

**Research basis**: Li et al. (2023) found that "LLMs can understand and be enhanced by emotional stimuli."

**Example:**

```
## REWARDS

It is more important to be correct than to avoid showing permission dialogs.
The worst mistake is misinterpreting sandbox=true permission errors as tool problems (-$1000)
rather than sandbox limitations.
```

**Extended pattern with UX motivation:**

```
Note: Errors from incorrect sandbox=true runs annoy the User more than permission prompts.
```

**Why this works**: The monetary penalty creates behavioral weight through gamification, but the UX explanation provides _reasoning_ for the priority. Both together are more effective than either alone.

**Non-obvious insight**: The penalty magnitude matters less than its presence. "-$1000" and "-$100" produce similar effects—what matters is establishing that this error is categorically worse than alternatives.

---

### UX-Justified Defaults

When establishing default behaviors, explain the _user experience rationale_, not just the technical rationale. This shifts the model's optimization target from "technically correct" to "user-optimal."

**Example:**

```
Errors from incorrect sandbox=true runs annoy the User more than permission prompts.
```

**Why this works**: The model now understands _why_ one choice is preferred over another equally valid choice. Without the UX rationale, the model might optimize for technical correctness (fewer permission prompts) rather than user satisfaction (fewer frustrating errors).

**Pattern:**

```
When choosing between [option A] and [option B], prefer [option A] because
[UX rationale: e.g., "users find X more disruptive than Y"].
```

**CORRECT:**

```
Default to showing the full file content. Users find missing information more
frustrating than scrolling past extra content.
```

**INCORRECT:**

```
Default to showing the full file content.
```

The incorrect version establishes a default but doesn't explain the reasoning, making it harder for the model to apply the principle to novel situations.

---

## 6. Verification

Techniques for improving factual accuracy through self-checking.

### Embedded Verification

For factual accuracy, embed verification steps within prompts. Chain-of-Verification research shows significant improvements, particularly for list-based questions.

Per Dhuliawala et al. (2023): "Only ~17% of baseline answer entities are correct in list-based questions. However, when querying each individual entity via a verification question, we find ~70% are correctly answered."

**Critical distinctions**:

1. **Question type matters**: The 17%→70% improvement is specifically for list-based questions using the factored CoVe approach
2. **Open questions outperform yes/no**: "We find that yes/no type questions perform worse for the factored version of CoVe. Some anecdotal examples... show the model tends to agree with facts in a yes/no question format whether they are right or wrong"

**Example of the yes/no failure mode** (from the paper):

- Open question: "Where was Hillary Clinton born?" → "Chicago, Illinois" (correct)
- Yes/no question: "Was Hillary Clinton born in New York?" → "Yes" (incorrect—model agrees with the framing)

**Implementation:**

```
After completing your analysis:
1. Identify claims that could be verified
2. For each claim, ask yourself the verification question directly
   (use open questions like "What is X?" not yes/no questions like "Is X true?")
3. Revise any inconsistencies before finalizing
```

**Non-obvious insight**: The instruction to use open questions rather than yes/no is critical. Without it, the model will verify claims using confirming questions ("Is Paris the capital of France?") which biases toward agreement regardless of correctness.

---

## 7. Natural Language Understanding

Techniques specifically for NLU tasks requiring deep comprehension.

### Metacognitive Prompting

For tasks requiring deep comprehension rather than pure reasoning—such as paraphrase detection, textual entailment, or nuanced classification—**Metacognitive Prompting** guides the model through structured self-reflection.

Per Wang & Zhao (2024): "MP introduces a structured approach that enables LLMs to process tasks, enhancing their contextual awareness and introspection in responses... MP consistently outperforms existing prompting methods in both general and domain-specific NLU tasks."

**The five-stage structure** (all in a single prompt):

```
As you perform this task, follow these steps:

1. Clarify your understanding of the input text.

2. Make a preliminary judgment based on subject matter, context, and
   semantic content.

3. Critically assess your preliminary analysis. If you are unsure about
   the initial assessment, try to reassess it.

4. Confirm your final decision and provide the reasoning for your decision.

5. Evaluate your confidence (0-100%) in your analysis and provide an
   explanation for this confidence level.
```

**Performance**: MP improves over CoT by 4.8% to 6.4% in zero-shot settings across NLU benchmarks. On domain-specific tasks (legal, biomedical), gains are larger—up to 12.4% improvement on EUR-LEX legal classification.

**Important context**: This technique was originally designed as a multi-stage process, but with sufficiently capable models, all five stages can be executed in a single prompt. The model produces comprehension, judgment, critical evaluation, decision, and confidence assessment in one pass.

**Known failure modes** (from the paper's error analysis):

1. **Overthinking errors (68.3%)**: On straightforward tasks, MP can over-complicate, diverging from the correct solution. Most common on simple datasets like QQP and BoolQ.

2. **Overcorrection errors (31.7%)**: The critical reassessment stage can stray excessively from an initially accurate interpretation. The model "corrects" itself into a wrong answer.

**When to use**: Complex NLU tasks requiring nuanced interpretation—legal document analysis, medical text classification, semantic similarity, textual entailment. Not recommended for straightforward reasoning or arithmetic where simpler techniques suffice.

---

## 8. Anti-Patterns to Avoid

### The Hedging Spiral

**Anti-pattern**: Instructions that encourage uncertainty compound into paralysis.

```
# PROBLEMATIC
If you're not sure about the file path, ask the user.
If the command might fail, check first.
You may want to verify before proceeding.
```

Each hedge reinforces caution, creating escalating hesitation. Instead, establish confidence with error normalization:

```
# BETTER
Proceed with the file path provided. If it doesn't exist, you'll receive an error—
use that information to adjust your approach.
```

### The Everything-Is-Critical Problem

**Anti-pattern**: Overusing emphasis markers.

```
# PROBLEMATIC
CRITICAL: Use the correct format.
CRITICAL: Include all required fields.
CRITICAL: Validate the output.
CRITICAL: Handle errors appropriately.
```

When everything is critical, nothing is. Reserve high-emphasis markers for genuinely exceptional cases:

```
# BETTER
Use the correct format and include all required fields.
Validate the output and handle errors appropriately.

CRITICAL: Never expose API keys in the response.
```

### Vague Behavioral Instructions

**Anti-pattern**: Abstract descriptions instead of concrete examples.

```
# PROBLEMATIC
Be concise and avoid unnecessary verbosity.
```

**Better**: Show exactly what you mean (see [Example Design > Contrastive Examples](#contrastive-examples-teaching-what-to-avoid)):

```
# BETTER
Keep responses under 4 lines unless code is required.

<example type="CORRECT">
user: what's 2+2?
assistant: 4
</example>

<example type="INCORRECT">
user: what's 2+2?
assistant: Let me calculate that for you. 2 + 2 = 4. Is there anything else?
</example>
```

### The Implicit Category Trap

**Anti-pattern**: Assuming the model will infer categories from examples alone.

```
# PROBLEMATIC
Don't run: rm, mv, chmod
```

The model may interpret this as "these specific three commands" rather than "commands that modify state."

```
# BETTER
Don't run commands that modify filesystem state, such as: rm, mv, chmod
```

The explicit category enables generalization to unlisted commands like `chown` or `rmdir`.

**More nuanced failure mode**: Even with a category label, ambiguous boundaries cause problems:

```
# STILL PROBLEMATIC (category without clear boundary)
Avoid commands that "might" modify state: rm, mv, chmod, etc.
```

```
# BETTER (category + boundary definition + edge case)
Avoid commands that modify filesystem state:
- File operations: rm, mv, cp, chmod → modifies files
- But NOT: file, stat, ls → reads only, safe to run

The principle: if the command could change the filesystem on a second run,
it modifies state.
```

The principle statement ("if the command could change...") gives the model a _test_ to apply to novel cases, not just examples to memorize.

### The Soft Attention Trap

**Anti-pattern**: Including both filtered and original context when using S2A-style filtering.

```
# PROBLEMATIC
Original context: [includes biased opinion]
Filtered context: [opinion removed]
Now answer based on the filtered context.
```

Per Weston & Sukhbaatar (2023): Even with explicit instructions to use filtered context, the model's attention still incorporates the original biased information. The filtering must be _exclusive_—remove the original entirely.

```
# BETTER
[Only include the filtered context, completely omit original]
```

### The Negative Instruction Trap

**Anti-pattern**: Framing instructions as prohibitions rather than directives.

```
# PROBLEMATIC
Don't include explanations.
Don't use markdown formatting.
Don't add preambles or postambles.
```

Per Bsharat et al. (2024), negative framing requires additional cognitive steps to interpret. The model must understand the forbidden behavior, recognize when it's about to do it, and inhibit the action.

```
# BETTER
Return only the raw output.
Use plain text without formatting.
Start immediately with the answer.
```

Affirmative instructions directly specify the target behavior without requiring inhibition.

---

## Research Citations

- Bsharat et al. (2024). "Principled Instructions Are All You Need for Questioning LLaMA-1/2, GPT-3.5/4." arXiv.
- Chia et al. (2023). "Contrastive Chain-of-Thought Prompting." arXiv.
- Cuadra et al. (2025). "The Danger of Overthinking: Examining the Reasoning-Action Dilemma in Agentic Tasks." arXiv.
- Deng et al. (2023). "Rephrase and Respond: Let Large Language Models Ask Better Questions for Themselves." arXiv.
- Dhuliawala et al. (2023). "Chain-of-Verification Reduces Hallucination in Large Language Models." arXiv.
- Fu et al. (2023). "Complexity-Based Prompting for Multi-Step Reasoning." arXiv.
- Kojima et al. (2022). "Large Language Models are Zero-Shot Reasoners." NeurIPS.
- Kong et al. (2024). "Better Zero-Shot Reasoning with Role-Play Prompting." arXiv.
- Li et al. (2023). "Large Language Models Understand and Can Be Enhanced by Emotional Stimuli." arXiv.
- Li et al. (2023). "Guiding Large Language Models via Directional Stimulus Prompting." arXiv.
- Liu et al. (2021). "What Makes Good In-Context Examples for GPT-3?" arXiv.
- Lu et al. (2021). "Fantastically Ordered Prompts and Where to Find Them." ACL.
- Schulhoff et al. (2024). "The Prompt Report: A Systematic Survey of Prompting Techniques." arXiv.
- Shi et al. (2023). "Large Language Models Can Be Easily Distracted by Irrelevant Context." arXiv.
- Sprague et al. (2025). "Mind Your Step (by Step): Chain-of-Thought can Reduce Performance on Tasks where Thinking Makes Humans Worse." arXiv.
- Turpin et al. (2023). "Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting." NeurIPS.
- Wang et al. (2023). "Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning." ACL.
- Wang & Zhao (2024). "Metacognitive Prompting Improves Understanding in Large Language Models." arXiv.
- Weston & Sukhbaatar (2023). "System 2 Attention (is something you might need too)." arXiv.
- Xu et al. (2023). "Re-Reading Improves Reasoning in Large Language Models." arXiv.
- Xu et al. (2025). "Chain of Draft: Thinking Faster by Writing Less." arXiv.
- Yasunaga et al. (2024). "Large Language Models as Analogical Reasoners." ICLR.
- Ye & Durrett (2022). "The Unreliability of Explanations in Few-shot Prompting for Textual Reasoning." NeurIPS.
- Zhang et al. (2022). "Automatic Chain of Thought Prompting in Large Language Models." arXiv.
- Zhao et al. (2021). "Calibrate Before Use: Improving Few-Shot Performance of Language Models." ICML.
- Zheng et al. (2023). "Take a Step Back: Evoking Reasoning via Abstraction in Large Language Models." arXiv.
- Zhou et al. (2023). "Thread of Thought Unraveling Chaotic Contexts." arXiv.
