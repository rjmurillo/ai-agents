<?xml version="1.0" encoding="UTF-8"?>
<skill_specification version="1.0">

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- METADATA                                                                  -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <metadata>
    <name>cva-analysis</name>
    <version>1.0.0</version>
    <created>2026-02-07</created>
    <analysis_iterations>4</analysis_iterations>
    <timelessness_score>9</timelessness_score>

    <analysis_summary>
      <lenses_applied>
        <lens>first_principles</lens>
        <lens>inversion</lens>
        <lens>second_order_effects</lens>
        <lens>pre_mortem</lens>
        <lens>systems_thinking</lens>
        <lens>devils_advocate</lens>
        <lens>constraint_analysis</lens>
        <lens>pareto_analysis</lens>
        <lens>root_cause_analysis</lens>
        <lens>comparative_analysis</lens>
        <lens>opportunity_cost</lens>
      </lenses_applied>
      <questioning_rounds>4</questioning_rounds>
      <expert_perspectives>
        <expert>multi_paradigm_design_expert</expert>
        <expert>software_architect</expert>
        <expert>pattern_discovery_specialist</expert>
      </expert_perspectives>
    </analysis_summary>
  </metadata>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- CONTEXT                                                                   -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <context>
    <problem_statement>
      <what>Engineers need a systematic technique for discovering natural abstractions from requirements before selecting design patterns</what>
      <why>Wrong abstractions create technical debt worse than no abstraction. Traditional approach (pattern-first) leads to forced designs. Root cause: Lack of structured abstraction discovery in engineering practice.</why>
      <who>Software engineers and architects making design decisions, particularly when facing multiple similar but varying requirements. Applicable during initial design, refactoring, or architectural review.</who>
    </problem_statement>

    <existing_landscape>
      <related_skills>
        <skill name="architect">
          <relationship>CVA produces analysis artifacts that feed into ADR creation</relationship>
          <overlap_score>2/10</overlap_score>
        </skill>
        <skill name="decision-critic">
          <relationship>Can validate abstraction choices discovered via CVA</relationship>
          <overlap_score>3/10</overlap_score>
        </skill>
        <skill name="independent-thinker">
          <relationship>Can challenge whether abstraction is needed at all</relationship>
          <overlap_score>2/10</overlap_score>
        </skill>
      </related_skills>
      <distinctiveness>CVA is the only skill providing structured commonality/variability analysis for abstraction discovery. Complements YAGNI by making the "do we have enough examples?" question explicit and visual.</distinctiveness>
    </existing_landscape>

    <user_profile>
      <primary_audience>Software engineers (mid to senior level) familiar with SOLID principles and design patterns, making abstraction decisions</primary_audience>
      <expertise_level>intermediate-to-advanced</expertise_level>
      <context_assumptions>User understands basic design patterns (Strategy, Abstract Factory), SOLID principles, and the danger of wrong abstractions per CLAUDE.md Design Philosophy</context_assumptions>
    </user_profile>
  </context>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- REQUIREMENTS                                                              -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <requirements>
    <explicit>
      <requirement id="E1" priority="must">
        <description>Guide through matrix-building process: start with 1 use case, add rows (requirements), add columns (variations)</description>
        <source>User request</source>
      </requirement>
      <requirement id="E2" priority="must">
        <description>Translate matrix to patterns: rows = Strategy, columns = Abstract Factory</description>
        <source>User request, Coplien Multi-Paradigm Design</source>
      </requirement>
      <requirement id="E3" priority="must">
        <description>Handle edge cases: single use case (don't abstract), all variability (reconsider design)</description>
        <source>User request</source>
      </requirement>
      <requirement id="E4" priority="must">
        <description>Produce visual CVA matrix artifact for team discussion</description>
        <source>User request</source>
      </requirement>
      <requirement id="E5" priority="must">
        <description>Integration with architect agent and decision-critic for validation</description>
        <source>User request</source>
      </requirement>
    </explicit>

    <implicit>
      <requirement id="I1" priority="must">
        <description>Process must be faster than trial-and-error but more rigorous than intuition</description>
        <source>Engineering practice: balance speed with quality</source>
      </requirement>
      <requirement id="I2" priority="must">
        <description>Prevent premature pattern selection (pattern-first anti-pattern)</description>
        <source>CLAUDE.md Design Philosophy: "Greatest vulnerability is wrong or missing abstraction"</source>
      </requirement>
      <requirement id="I3" priority="should">
        <description>YAGNI-compatible: only abstract when evidence warrants</description>
        <source>Industry best practice: You Aren't Gonna Need It</source>
      </requirement>
      <requirement id="I4" priority="should">
        <description>Support reassessment triggers for when to re-run CVA</description>
        <source>Software evolution: today's constant may be tomorrow's variable</source>
      </requirement>
    </implicit>

    <discovered>
      <requirement id="D1" priority="should">
        <description>Tiered depth levels: Quick (2 use cases, 15 min), Standard (3-5 use cases, 30 min), Deep (6+ use cases, 60 min)</description>
        <source>Lens: pre-mortem - Prevent "too slow for fast-paced environment" failure</source>
        <discovery_round>1</discovery_round>
      </requirement>
      <requirement id="D2" priority="should">
        <description>Validation script to check matrix completeness and suggest patterns</description>
        <source>Lens: systems_thinking - Automation enables self-verification</source>
        <discovery_round>3</discovery_round>
      </requirement>
      <requirement id="D3" priority="should">
        <description>Multiple matrix formats: Markdown table (primary), optional Mermaid diagram</description>
        <source>Lens: constraint_analysis - "CVA requires UML" is false constraint</source>
        <discovery_round>2</discovery_round>
      </requirement>
      <requirement id="D4" priority="could">
        <description>Temporal dimension: "Future Variations" column for anticipated changes</description>
        <source>Lens: second_order_effects - Abstractions must handle evolution</source>
        <discovery_round>1</discovery_round>
      </requirement>
      <requirement id="D5" priority="must">
        <description>Explicit guidance on when NOT to use CVA (single use case, clear pattern)</description>
        <source>Lens: pareto_analysis - Focus on high-value scenarios</source>
        <discovery_round>1</discovery_round>
      </requirement>
    </discovered>
  </requirements>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- ARCHITECTURE                                                              -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <architecture>
    <pattern>
      <name>multi-phase</name>
      <rationale>CVA is inherently sequential: must identify commonalities before variabilities, must have matrix before pattern mapping. Phases mirror Coplien's original CVA technique.</rationale>
      <alternatives_considered>
        <alternative name="single-phase">
          <why_rejected>CVA has distinct cognitive phases (commonality discovery, variability analysis, pattern recognition). Collapsing loses pedagogical clarity and makes matrix building chaotic.</why_rejected>
        </alternative>
        <alternative name="checklist">
          <why_rejected>CVA requires iterative refinement, not just linear completion. Matrix often reveals missing commonalities that trigger backtracking.</why_rejected>
        </alternative>
      </alternatives_considered>
    </pattern>

    <phases>
      <phase id="1">
        <name>Identify Commonalities</name>
        <purpose>Establish what is ALWAYS true across all use cases. This becomes the stable foundation.</purpose>
        <inputs>
          <input>One or more use cases/requirements (minimum 1 to start)</input>
          <input>Domain knowledge or existing code (if refactoring)</input>
        </inputs>
        <process>
          <step order="1">Start with first use case: What does it need?</step>
          <step order="2">Add second use case: What do BOTH need?</step>
          <step order="3">Extract commonalities (what's shared across all cases)</step>
          <step order="4">Document as matrix ROWS</step>
        </process>
        <outputs>
          <output>List of commonalities (matrix rows)</output>
          <output>Initial understanding of problem domain</output>
        </outputs>
        <verification>
          <check>Each commonality is present in ALL use cases</check>
          <check>At least 2 commonalities identified (if only 1, reconsider scope)</check>
        </verification>
        <failure_handling>If no commonalities exist, use cases may be unrelated. Reconsider grouping or analyze separately.</failure_handling>
      </phase>

      <phase id="2">
        <name>Identify Variabilities</name>
        <purpose>Discover what VARIES between use cases. This reveals extension points.</purpose>
        <inputs>
          <input>Commonalities from Phase 1</input>
          <input>Use cases under analysis</input>
        </inputs>
        <process>
          <step order="1">For each commonality, ask: "How does this vary across cases?"</step>
          <step order="2">List variations for each commonality</step>
          <step order="3">Document as matrix COLUMNS</step>
          <step order="4">Add "Future Variations" column for anticipated changes (optional)</step>
        </process>
        <outputs>
          <output>List of variabilities (matrix columns)</output>
          <output>Populated CVA matrix (commonalities × variabilities)</output>
        </outputs>
        <verification>
          <check>Each variability differs in at least 2 use cases</check>
          <check>Matrix cells are filled with specific implementations</check>
          <check>If zero variability, abstraction may not be needed (proceed to edge case guidance)</check>
        </verification>
        <failure_handling>If all variability (no commonality), design may be too broad. Narrow scope or reconsider grouping.</failure_handling>
      </phase>

      <phase id="3">
        <name>Build CVA Matrix</name>
        <purpose>Create visual artifact showing commonality/variability relationships. Makes implicit design explicit.</purpose>
        <inputs>
          <input>Commonalities (rows) from Phase 1</input>
          <input>Variabilities (columns) from Phase 2</input>
        </inputs>
        <process>
          <step order="1">Create Markdown table with commonalities as rows, variabilities as columns</step>
          <step order="2">Fill each cell with concrete implementation for that commonality/variability combination</step>
          <step order="3">Highlight where cells are identical (potential for sharing)</step>
          <step order="4">Highlight where cells differ (extension points)</step>
          <step order="5">Optionally export to Mermaid diagram for presentation</step>
        </process>
        <outputs>
          <output>CVA matrix in Markdown table format</output>
          <output>Optional: Mermaid diagram export</output>
        </outputs>
        <verification>
          <check>Matrix is at least 2×2 (minimum for pattern discovery)</check>
          <check>All cells are filled (no empty cells)</check>
          <check>Patterns are becoming visible (commonalities group, variabilities diverge)</check>
        </verification>
        <failure_handling>If matrix reveals no useful patterns, abstraction may not be beneficial. Document rationale for concrete implementation instead.</failure_handling>
      </phase>

      <phase id="4">
        <name>Map to Patterns</name>
        <purpose>Translate matrix structure to design patterns. Patterns EMERGE from analysis, not imposed.</purpose>
        <inputs>
          <input>Completed CVA matrix from Phase 3</input>
        </inputs>
        <process>
          <step order="1">Read ROWS: Commonalities suggest Strategy pattern (vary algorithms for same operation)</step>
          <step order="2">Read COLUMNS: Variabilities suggest Abstract Factory pattern (vary implementations across product families)</step>
          <step order="3">Check for multidimensional variability (may need combination patterns)</step>
          <step order="4">Document pattern recommendations with rationale</step>
          <step order="5">Create ADR stub for architect agent review</step>
        </process>
        <outputs>
          <output>Pattern recommendations (Strategy, Abstract Factory, or combination)</output>
          <output>Implementation guidance based on matrix</output>
          <output>ADR stub for architectural review</output>
        </outputs>
        <verification>
          <check>Recommended patterns align with matrix structure</check>
          <check>Rationale explains WHY patterns fit</check>
          <check>Edge cases addressed (single use case, all variability)</check>
        </verification>
        <failure_handling>If no patterns fit, document rationale for concrete implementation. Abstraction may not be warranted yet (YAGNI applies).</failure_handling>
      </phase>

      <phase id="5">
        <name>Validation and Handoff</name>
        <purpose>Validate abstraction choices and route to appropriate agents for review.</purpose>
        <inputs>
          <input>Pattern recommendations from Phase 4</input>
          <input>CVA matrix artifact</input>
        </inputs>
        <process>
          <step order="1">Run validation script: `python3 scripts/validate-cva-matrix.py`</step>
          <step order="2">Check completeness: ≥2 rows, ≥2 columns, all cells filled</step>
          <step order="3">Route to decision-critic for abstraction validation</step>
          <step order="4">Route to architect agent for ADR creation (if abstraction warranted)</step>
          <step order="5">Document reassessment triggers for when to re-run CVA</step>
        </process>
        <outputs>
          <output>Validation report (passed/failed with specific issues)</output>
          <output>Handoff to decision-critic and/or architect agent</output>
          <output>Reassessment triggers documented</output>
        </outputs>
        <verification>
          <check>Validation script exits with code 0 (pass)</check>
          <check>Decision-critic review completed (if abstraction recommended)</check>
          <check>Reassessment triggers are specific (not vague "review later")</check>
        </verification>
        <failure_handling>If validation fails, return to earlier phase based on issue type (missing commonalities → Phase 1, incomplete matrix → Phase 3).</failure_handling>
      </phase>
    </phases>

    <decision_points>
      <decision_point phase="2" step="3">
        <condition>Zero variability detected (all use cases identical)</condition>
        <options>
          <option>Option A: Don't abstract (no variation to abstract over)</option>
          <option>Option B: Add "Future Variations" column and abstract proactively</option>
        </options>
        <default>Option A (YAGNI: don't abstract without evidence). Document decision in ADR if choosing Option B.</default>
      </decision_point>
      <decision_point phase="4" step="1">
        <condition>Matrix shows multidimensional variability (both rows AND columns vary independently)</condition>
        <options>
          <option>Option A: Start with dominant axis (commonality vs variability ratio)</option>
          <option>Option B: Use combination patterns (Strategy + Abstract Factory)</option>
        </options>
        <default>Option A (simpler). Note multidimensional case in "Extension Points" for future iteration.</default>
      </decision_point>
    </decision_points>

    <data_flow>
      <flow from="phase1" to="phase2">
        <data>List of commonalities (matrix rows)</data>
        <format>Array of strings or structured objects</format>
      </flow>
      <flow from="phase2" to="phase3">
        <data>Commonalities + Variabilities</data>
        <format>2D structure: rows (commonalities) × columns (variabilities)</format>
      </flow>
      <flow from="phase3" to="phase4">
        <data>Completed CVA matrix</data>
        <format>Markdown table or structured data</format>
      </flow>
      <flow from="phase4" to="phase5">
        <data>Pattern recommendations + ADR stub</data>
        <format>Structured document with rationale</format>
      </flow>
    </data_flow>
  </architecture>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- EVOLUTION ANALYSIS                                                        -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <evolution_analysis>
    <timelessness_score>9</timelessness_score>
    <score_justification>
      CVA is based on Coplien's Multi-Paradigm Design (1999), which itself derives from analysis techniques dating to the 1970s. The fundamental insight (commonality vs variability) is domain-independent and language-agnostic. While specific patterns (Strategy, Abstract Factory) may evolve, the matrix-based discovery technique remains valid. Score: 9/10 (not 10 because new paradigms like reactive programming may require additional lenses).
    </score_justification>

    <temporal_projection>
      <horizon period="6_months">
        <expected_state>Skill actively used for design decisions and refactoring analysis. Matrix format standardized across team.</expected_state>
        <risks>Team may find matrix format cumbersome, prefer ad-hoc analysis</risks>
        <mitigations>Tiered depth levels allow quick 15-min analysis. Validation script reduces manual effort.</mitigations>
      </horizon>
      <horizon period="1_year">
        <expected_state>CVA integrated into ADR workflow. Architect agent automatically requests CVA for abstraction decisions. Pattern library grows with .NET-specific examples.</expected_state>
        <risks>New team members unfamiliar with CVA may bypass it</risks>
        <mitigations>Onboarding includes CVA training. Reference docs have concrete examples from codebase.</mitigations>
      </horizon>
      <horizon period="2_years">
        <expected_state>CVA extended to handle multidimensional variability, reactive patterns, functional composition patterns. Mermaid export widely used in architecture presentations.</expected_state>
        <risks>Skill may become overly complex if trying to handle every edge case</risks>
        <mitigations>Extension points allow adding new pattern mappings without modifying core technique. Maintain simplicity of base workflow.</mitigations>
      </horizon>
    </temporal_projection>

    <extension_points>
      <extension_point>
        <location>Phase 4: Pattern mapping rules</location>
        <purpose>Add new pattern types beyond Strategy/Abstract Factory (e.g., Builder, Bridge, Visitor)</purpose>
        <mechanism>Create `references/pattern-mapping-extended.md` with additional matrix configurations</mechanism>
      </extension_point>
      <extension_point>
        <location>Phase 3: Matrix formats</location>
        <purpose>Add export formats beyond Markdown (e.g., Mermaid, PlantUML, JSON for tooling)</purpose>
        <mechanism>Create `scripts/export-cva-matrix.py` with format parameter</mechanism>
      </extension_point>
      <extension_point>
        <location>Phase 2: Multidimensional analysis</location>
        <purpose>Handle cases where both rows AND columns have independent variability</purpose>
        <mechanism>Create `references/multidimensional-cva.md` with 3D matrix techniques</mechanism>
      </extension_point>
      <extension_point>
        <location>Validation script</location>
        <purpose>Add AI-powered pattern suggestion based on matrix structure</purpose>
        <mechanism>Integrate with decision-critic or independent-thinker agent for automated review</mechanism>
      </extension_point>
    </extension_points>

    <dependencies>
      <dependency type="external">
        <name>Markdown table syntax</name>
        <stability>stable</stability>
        <fallback>If Markdown becomes obsolete, matrix can be represented in any tabular format (CSV, JSON, etc.)</fallback>
      </dependency>
      <dependency type="internal">
        <name>architect agent</name>
        <coupling>loose</coupling>
        <fallback>CVA can output ADR stub as standalone Markdown file if architect agent unavailable</fallback>
      </dependency>
      <dependency type="internal">
        <name>decision-critic skill</name>
        <coupling>loose</coupling>
        <fallback>Manual review of abstraction choices if decision-critic unavailable</fallback>
      </dependency>
      <dependency type="external">
        <name>Python 3.x for validation script</name>
        <stability>stable</stability>
        <fallback>Manual validation using checklist if Python unavailable</fallback>
      </dependency>
    </dependencies>

    <obsolescence_triggers>
      <trigger likelihood="low">
        <description>New programming paradigm eliminates need for abstractions (e.g., pure declarative systems)</description>
        <defensive_measure>CVA is paradigm-agnostic (discovers structure, not specific to OOP). Extensible to functional patterns via extension points.</defensive_measure>
      </trigger>
      <trigger likelihood="very_low">
        <description>AI tools automatically generate optimal abstractions, making manual analysis obsolete</description>
        <defensive_measure>CVA matrix provides explainable structure for AI-generated designs. Human understanding remains valuable even if automation exists.</defensive_measure>
      </trigger>
      <trigger likelihood="medium">
        <description>Team adopts different abstraction discovery technique (e.g., domain-driven design hexagonal architecture)</description>
        <defensive_measure>CVA complements other techniques (can analyze DDD bounded contexts). Documented integration patterns prevent replacement, enable composition.</defensive_measure>
      </trigger>
    </obsolescence_triggers>
  </evolution_analysis>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- ANTI-PATTERNS                                                             -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <anti_patterns>
    <anti_pattern severity="critical">
      <description>Pattern-First Design (selecting Strategy or Abstract Factory BEFORE running CVA)</description>
      <reason>Violates fundamental CVA principle: patterns should EMERGE from analysis, not be imposed. Leads to wrong abstractions that force requirements into preconceived structures.</reason>
      <example>Engineer decides "we need a Strategy pattern for payment processing" before analyzing commonalities/variabilities. Discovers later that Abstract Factory would have been better, but refactoring is costly.</example>
      <alternative>Run CVA first. Let matrix reveal natural pattern. If pattern doesn't emerge, abstraction may not be needed (YAGNI).</alternative>
    </anti_pattern>

    <anti_pattern severity="critical">
      <description>Forcing Abstractions (creating abstraction when CVA shows no variability)</description>
      <reason>Violates YAGNI and adds complexity without benefit. Worse than no abstraction per CLAUDE.md Design Philosophy.</reason>
      <example>CVA matrix shows all cells identical (no variability). Engineer creates Strategy pattern anyway "for future extensibility." Adds interfaces, factories, complexity for zero current value.</example>
      <alternative>When CVA shows no variability, explicitly document decision NOT to abstract. Revisit when variability emerges (reassessment trigger).</alternative>
    </anti_pattern>

    <anti_pattern severity="major">
      <description>Skipping Matrix Visualization (going straight from requirements to patterns)</description>
      <reason>Loses pedagogical and collaborative benefits. Matrix makes implicit assumptions explicit, enables team discussion, reveals gaps.</reason>
      <example>Engineer identifies commonalities/variabilities mentally, jumps to pattern selection without documenting matrix. Team can't review analysis, assumptions buried in code.</example>
      <alternative>Always create visual matrix artifact (Markdown table minimum). Use for team review, documentation, ADR rationale.</alternative>
    </anti_pattern>

    <anti_pattern severity="major">
      <description>Analysis Paralysis (spending hours on CVA for simple 2-use-case scenario)</description>
      <reason>CVA is a tool, not an end. Time-boxing prevents over-analysis. Quick tier (15 min) is sufficient for most decisions.</reason>
      <example>Engineer spends 3 hours analyzing 2 simple use cases, creating elaborate matrix with future variations, temporal dimensions, multidimensional analysis. Implementation could have been done in 1 hour.</example>
      <alternative>Use tiered approach: Quick (15 min) for simple cases, Standard (30 min) for moderate complexity, Deep (60 min) only for architectural decisions. Set timer and commit to best-available analysis at time-box.</alternative>
    </anti_pattern>

    <anti_pattern severity="minor">
      <description>Ignoring Temporal Dimension (assuming today's constants remain constant)</description>
      <reason>Software evolves. Today's constant may be tomorrow's variable. CVA should anticipate change where reasonable.</reason>
      <example>CVA matrix shows "payment amount currency" as constant (always USD). 6 months later, international expansion requires multi-currency. Abstraction must be refactored.</example>
      <alternative>Include "Future Variations" column in matrix for anticipated changes. Discuss with product/business stakeholders. Balance YAGNI (don't over-engineer) with reasonable foresight (architect for known roadmap).</alternative>
    </anti_pattern>

    <anti_pattern severity="minor">
      <description>Using CVA for Single Use Case (no comparison possible)</description>
      <reason>CVA requires multiple use cases to identify commonality/variability. Single use case has no basis for abstraction discovery.</reason>
      <example>Engineer runs CVA on payment processing before any other financial transaction exists. Matrix has 1 row, 1 column. No patterns emerge.</example>
      <alternative>Wait for 2nd use case (YAGNI), OR document anticipated use cases with stakeholder validation, OR use different analysis technique (pre-mortem, domain modeling).</alternative>
    </anti_pattern>
  </anti_patterns>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- SUCCESS CRITERIA                                                          -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <success_criteria>
    <criterion id="SC1" type="functional" priority="must">
      <description>Skill produces valid CVA matrix with ≥2 commonalities (rows) and ≥2 variabilities (columns)</description>
      <verification_method>Run `python3 scripts/validate-cva-matrix.py [matrix-file.md]`, check exit code 0</verification_method>
    </criterion>

    <criterion id="SC2" type="functional" priority="must">
      <description>Pattern recommendations align with matrix structure (rows → Strategy, columns → Abstract Factory)</description>
      <verification_method>Manual review: Check that recommended patterns match matrix configuration. Cross-validate with decision-critic agent.</verification_method>
    </criterion>

    <criterion id="SC3" type="quality" priority="must">
      <description>Process prevents premature pattern selection (pattern emerges from matrix, not imposed)</description>
      <verification_method>Check workflow: Pattern recommendation appears in Phase 4, AFTER matrix completion in Phase 3. No pattern mentioned in Phases 1-2.</verification_method>
    </criterion>

    <criterion id="SC4" type="quality" priority="must">
      <description>Edge cases handled explicitly (single use case → don't abstract, all variability → reconsider scope)</description>
      <verification_method>Reference docs include edge case guidance. Anti-patterns section documents what to avoid.</verification_method>
    </criterion>

    <criterion id="SC5" type="usability" priority="should">
      <description>Tiered depth levels support fast execution (Quick: 15 min, Standard: 30 min, Deep: 60 min)</description>
      <verification_method>Time-box experiment: Can complete Quick tier CVA in ≤15 min? Standard in ≤30 min?</verification_method>
    </criterion>

    <criterion id="SC6" type="integration" priority="should">
      <description>Seamless handoff to architect agent for ADR creation</description>
      <verification_method>CVA output includes ADR stub with pattern rationale. Architect agent accepts stub without requiring reformatting.</verification_method>
    </criterion>

    <criterion id="SC7" type="evolution" priority="should">
      <description>Extension points enable adding new patterns without modifying core workflow</description>
      <verification_method>Add new pattern mapping (e.g., Builder) via `references/pattern-mapping-extended.md` without changing SKILL.md or core scripts.</verification_method>
    </criterion>

    <criterion id="SC8" type="evolution" priority="must">
      <description>Reassessment triggers documented so team knows when to re-run CVA</description>
      <verification_method>Check CVA output for "Reassessment Triggers" section with specific conditions (e.g., "3+ new use cases", "major architectural shift").</verification_method>
    </criterion>
  </success_criteria>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- VERIFICATION PROTOCOL                                                     -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <verification_protocol>
    <structural_checks>
      <check type="frontmatter">YAML frontmatter with name, version, description, model, license</check>
      <check type="sections">All required sections: Triggers, Process (5 phases), Anti-Patterns, Verification, References</check>
      <check type="triggers">3-5 distinct trigger phrases (e.g., "run CVA", "discover abstractions", "commonality variability analysis")</check>
      <check type="process">Clear 5-phase structure with explicit inputs/outputs per phase</check>
    </structural_checks>

    <content_checks>
      <check type="clarity">CVA terminology explained (commonality, variability, matrix rows/columns)</check>
      <check type="actionability">Each phase has concrete steps, not vague guidance</check>
      <check type="completeness">Edge cases documented (single use case, all variability, no commonality)</check>
      <check type="examples">.NET examples included (ASP.NET providers, dependency injection patterns)</check>
    </content_checks>

    <evolution_checks>
      <check type="timelessness">Score ≥ 7 (CVA scores 9: based on 25+ year old technique)</check>
      <check type="extensions">4 extension points documented (pattern mapping, matrix formats, multidimensional, AI integration)</check>
      <check type="dependencies">All dependencies have stability assessment and fallback plan</check>
    </evolution_checks>

    <synthesis_requirements>
      <requirement>Unanimous 3/3 approval from synthesis panel (Design, Audience, Evolution agents)</requirement>
      <requirement>All agents score ≥ 7 in their focus areas</requirement>
      <requirement>Zero critical issues from any agent</requirement>
    </synthesis_requirements>

    <script_validation>
      <check type="script_exists">validate-cva-matrix.py exists in scripts/</check>
      <check type="script_executable">Script has execute permissions (chmod +x)</check>
      <check type="script_exit_codes">Exit 0 on valid matrix, exit 10 on validation failure, exit 1 on error</check>
      <check type="script_output">Produces structured validation report (passed/failed with reasons)</check>
    </script_validation>
  </verification_protocol>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- GENERATION INSTRUCTIONS                                                   -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  <generation_instructions>
    <skill_md_structure>
      <section order="1">Frontmatter (YAML): name, version, description, model, license, metadata</section>
      <section order="2">Title and brief intro (2-3 paragraphs on CVA purpose)</section>
      <section order="3">Triggers (3-5 natural language phrases)</section>
      <section order="4">Quick Reference table (phases, inputs, outputs)</section>
      <section order="5">Process (5 phases with explicit steps, verification, failure handling)</section>
      <section order="6">When to Use vs When NOT to Use</section>
      <section order="7">Anti-Patterns (6 patterns from inversion analysis)</section>
      <section order="8">Integration with Other Skills (architect, decision-critic, independent-thinker)</section>
      <section order="9">Verification checklist</section>
      <section order="10">Reassessment Triggers</section>
      <section order="11">References (pattern mapping, matrix examples, Coplien papers)</section>
    </skill_md_structure>

    <reference_docs>
      <doc>references/pattern-mapping-guide.md - How to read matrix and map to patterns (Strategy, Abstract Factory, combinations)</doc>
      <doc>references/matrix-building-examples.md - .NET examples (ASP.NET providers, DI patterns, middleware pipeline)</doc>
      <doc>references/multidimensional-cva.md - Advanced: handling multiple axes of variability</doc>
      <doc>references/coplien-multi-paradigm-design.md - Academic foundation and further reading</doc>
    </reference_docs>

    <scripts_needed>
      <script type="validation">scripts/validate-cva-matrix.py - Check matrix completeness (≥2 rows, ≥2 cols, cells filled, patterns suggested)</script>
      <script type="generation">scripts/generate-cva-template.py - Create empty matrix template from user input</script>
      <script type="export">scripts/export-cva-matrix.py - Convert Markdown table to Mermaid diagram</script>
    </scripts_needed>

    <estimated_size>
      <skill_md>400-500 lines</skill_md>
      <references>600-800 lines total (4 docs × 150-200 lines each)</references>
      <scripts>300-400 lines total (3 scripts × 100-150 lines each)</scripts>
      <total_with_references>1300-1700 lines</total_with_references>
    </estimated_size>

    <integration_notes>
      <note>CVA output should include ADR stub that architect agent can consume directly</note>
      <note>Validation script output format should match decision-critic input expectations</note>
      <note>Reassessment triggers should align with project's retrospective cycle (quarterly review)</note>
    </integration_notes>
  </generation_instructions>

</skill_specification>
