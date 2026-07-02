---
name: idea-gen
description: Generate and rank research ideas given a broad direction. Brainstorms 8-12 ideas via external LLM, filters by feasibility, novelty, impact, and Prof. He's 4-dimension framework. Use when user says "找idea", "brainstorm ideas", "generate research ideas", "想点子", "what can we work on", or wants to explore a research area for publishable directions.
argument-hint: [research-direction]
allowed-tools: Bash(*), Read, Write, Grep, Glob, WebSearch, WebFetch, Agent, mcp__codex__codex, mcp__codex__codex-reply
---

# Research Idea Generator

Generate publishable research ideas for: $ARGUMENTS

## Overview

Given a broad research direction from the user, systematically generate, validate, and rank concrete research ideas. This skill uses an external LLM for divergent brainstorming, then applies multiple filtering layers — feasibility, novelty quick-check, impact estimation, and Prof. Bingsheng He's 4-dimension evaluation framework — to distill 8-12 raw ideas down to 4-6 high-quality, actionable research directions.

This skill is designed to compose with the `/lit-survey` skill (run first for best results) and feeds into `/idea-screen` and `/idea-refine` downstream.

## Constants

- **REVIEWER_MODEL = `gpt-5.4`** — Model used via Codex MCP for brainstorming and review. Must be an OpenAI model (e.g., `gpt-5.4`, `o3`, `gpt-4o`).
- **MIN_IDEAS = 8** — Minimum number of ideas to generate in the brainstorming phase.
- **MAX_IDEAS = 12** — Maximum number of ideas to generate in the brainstorming phase.
- **FILTER_THRESHOLD = 12** — Minimum composite score (out of 20) on Prof. He's 4-dimension filter for an idea to survive.
- **SURVIVING_TARGET = 4-6** — Target number of ideas that survive all filtering stages.

## Workflow

### Phase 1: Landscape Verification (~2 min — NOT a full literature search)

The purpose of this phase is to establish enough context for high-quality idea generation. It is NOT a replacement for `/lit-survey`.

1. **Check for existing landscape artifacts**:
   - Read `outputs/LANDSCAPE.json` if it exists
   - Read `outputs/LANDSCAPE.md` if it exists
   - These files are produced by the `/lit-survey` skill

2. **If landscape files exist**:
   - Verify the research direction in the landscape matches the user's current direction (fuzzy match is acceptable — e.g., "efficient transformers" matches "transformer efficiency")
   - Extract the **Gap Identification Matrix** or equivalent gap listing from the landscape
   - Extract the **key papers** list (titles + one-line summaries)
   - Extract any **open problems** or **future work** themes
   - Store these as `landscape_summary`, `identified_gaps`, and `key_papers` for use in Phase 2

3. **If landscape files do NOT exist** (fallback — abbreviated inline survey):
   - Print a notice: "No landscape files found. Running abbreviated inline survey. For better results, run `/lit-survey [direction]` first."
   - Run 3-5 quick WebSearch queries:
     - `"[direction] survey" site:arxiv.org`
     - `"[direction] benchmark" NeurIPS OR ICML OR ICLR 2024 2025`
     - `"[direction] limitations" OR "future work"`
     - `"[direction]" state-of-the-art`
     - One more query based on a specific sub-aspect of the direction
   - For the top 5-8 results, use WebFetch to read abstracts/introductions
   - Build a **mini landscape map**:
     - Group findings into 2-4 sub-themes
     - List 5-10 key papers (title, year, one-sentence summary)
     - Identify 3-5 gaps or open questions
   - Store as `landscape_summary`, `identified_gaps`, and `key_papers`

4. **Direction specificity check**:
   - **Auto-narrowing for broad directions**: If the user's direction is very broad (e.g., just "NLP" or "computer vision"), do NOT stop to ask. Instead:
     1. Identify the top 3 most promising sub-directions based on the landscape
     2. Generate ideas for each sub-direction (3-4 ideas each)
     3. Merge all ideas into a single pool and apply normal filtering
     4. Log in `outputs/PIPELINE_LOG.md`: "⚠️ Direction was broad, auto-narrowed to: [sub1], [sub2], [sub3]"
   - A good direction is 1-2 sentences specifying the problem, domain, and constraint — e.g., "factorized gap in discrete diffusion LMs" or "sample efficiency of offline RL with image observations"
   - If the direction is broad, auto-narrowing handles it autonomously; the pipeline never stops to ask

### Phase 2: Idea Generation via External LLM

Use the external LLM via Codex MCP for divergent, high-quality brainstorming. This is the creative core of the skill.

**Codex MCP failure handling**: If `mcp__codex__codex` call fails (tool unavailable, timeout, or error):
1. Fall back to Claude's own brainstorming capability
2. Use the same prompt structure but execute it directly (not via external LLM)
3. Log: "⚠️ Codex MCP unavailable. Brainstorming performed by Claude (single-model mode, reduced diversity)."
4. Continue the pipeline normally — do NOT stop or ask the user.

**Call `mcp__codex__codex`** with the following parameters:

- **model**: REVIEWER_MODEL (i.e., `gpt-5.4`)
- **config**: `{"model_reasoning_effort": "xhigh"}`
- **prompt**: Construct the prompt below, filling in the bracketed sections with data from Phase 1:

```
You are a senior ML/systems researcher. Your task is to generate research ideas
that are NOVEL, SPECIFIC, and EVALUATABLE.

Research direction: [user's direction from $ARGUMENTS]

Current landscape (from systematic survey):
[paste landscape_summary — either from LANDSCAPE.md or the mini-survey]

Identified gaps:
[paste identified_gaps — either the Gap Identification Matrix or the mini-survey gaps]

Generate 8-12 concrete research ideas. For each idea, provide:

1. **Title**: A concise, descriptive title (as it would appear on a paper)
2. **One-sentence thesis**: The core claim, stated as "We show that X by Y"
3. **Problem it solves**: Which specific gap from the landscape does this address?
4. **Core mechanism**: The key technical insight (not just "apply X to Y")
5. **Why it is non-obvious**: What would a skeptic's first objection be, and why is it wrong?
6. **Expected contribution type**: empirical finding / new method / theoretical result / diagnostic / new formulation
7. **Risk level**: LOW / MEDIUM / HIGH (with 1-sentence justification)
8. **Estimated effort**: person-weeks to a publishable result
9. **Closest existing work**: The single most similar paper and the precise delta

Quality criteria for generated ideas:
- REJECT "apply X to Y" unless the application reveals a genuinely surprising mechanism
- REJECT ideas where the outcome does not matter (if +3% or -3%, who cares?)
- PREFER ideas where a NEGATIVE result is equally publishable
- PREFER ideas that challenge an assumption the field takes for granted
- PREFER ideas with a clear "skeleton experiment" that takes < 1 week
- Each idea must be differentiated from the landscape papers above

Generate diverse ideas: at least 2 should be HIGH risk / high reward,
at least 2 should be LOW risk / solid contribution, and the rest MEDIUM.
```

**After the call**:
- Parse the response to extract individual ideas into a structured list
- Verify that at least MIN_IDEAS (8) ideas were generated; if fewer, call `mcp__codex__codex-reply` on the same thread asking for additional ideas to reach the minimum
- Verify that no more than MAX_IDEAS (12) ideas are kept; if more were generated, keep all but note the count
- **Save the threadId** — it will be used for potential follow-up in later skills (e.g., `/idea-screen`)
- Assign each idea an identifier: `IDEA-01`, `IDEA-02`, etc.

### Phase 3: First-Pass Filtering

For each generated idea, perform three quick evaluations. The goal is to eliminate clearly non-viable ideas before investing time in deeper scoring.

#### 3a. Feasibility Check

For each idea, evaluate:

- **Compute requirements**: Estimate GPU-hours needed for the minimum viable experiment. Skip ideas requiring > 1 month of GPU time.
- **Data availability**: Is the required data publicly available or obtainable? Skip ideas requiring proprietary or non-existent datasets.
- **Implementation complexity**: Can this be implemented in a reasonable timeframe by a small team (1-3 researchers)?
- **Dependency risk**: Does this require access to specific models, APIs, or infrastructure that may not be available?

Mark each idea as: `FEASIBLE`, `FEASIBLE WITH CAVEATS`, or `INFEASIBLE`.
Eliminate `INFEASIBLE` ideas. Note the reason for elimination.

#### 3b. Novelty Quick-Check

For each remaining idea, run 2-3 targeted WebSearch queries to check if it has already been done:

- Search for the idea's title or close paraphrase
- Search for the core mechanism + domain combination
- Search for the closest existing work mentioned in the idea + the proposed delta

For each idea, assign a novelty status:
- `LIKELY NOVEL` — No close matches found
- `NEEDS DEEPER CHECK` — Tangentially related work exists, but the exact angle appears unexplored
- `ALREADY DONE` — A paper doing essentially the same thing was found

Eliminate `ALREADY DONE` ideas. Note the paper that already covers it.

#### 3c. Impact Estimation ("So What?" Test)

For each remaining idea, evaluate:

- If the experiment succeeds with a positive result, does it change how people think or work?
- If the experiment produces a negative result, is that equally informative and publishable?
- Is the finding actionable (leads to better methods, new understanding) or just academically interesting?
- Would a reviewer at a top venue find the contribution significant?

Mark each idea as: `HIGH IMPACT`, `MEDIUM IMPACT`, or `LOW IMPACT`.
Eliminate `LOW IMPACT` ideas where neither a positive nor negative result would be interesting.

**After Phase 3**: Typically 8-12 ideas reduce to 5-8 survivors. Record all eliminated ideas and their elimination reasons.

### Phase 4: Prof. He's 4-Dimension Filter

Apply Prof. Bingsheng He's research idea evaluation framework. This is a structured scoring system that captures dimensions often missed by pure novelty/feasibility analysis.

For each surviving idea from Phase 3, score on four dimensions (1-5 scale each):

| Dimension | Score (1-5) | Scoring Criteria |
|-----------|-------------|------------------|
| **Longevity** | | Will this topic still be relevant in 3-5 years? Score 5 if it addresses a fundamental question. Score 1 if it rides a transient trend that may be obsolete in 1-2 years. |
| **Passion alignment** | | Does this align with the researcher's stated interests, skills, and existing expertise? If the user has not stated preferences, default to score 3. If they have (e.g., "I work on systems" or "I'm interested in theory"), score accordingly. |
| **Application potential** | | Can this strengthen a paper's motivation with real-world impact? Score 5 if it directly improves a deployed system or addresses a practitioner pain point. Score 1 if it is purely theoretical with no foreseeable application. |
| **Uniqueness** | | Can the researcher make a unique contribution here that others cannot easily replicate? Score 5 if the idea leverages a unique dataset, insight, or methodological strength. Score 1 if any well-funded lab could do this faster. |

**Composite score** = Longevity + Passion + Application + Uniqueness (out of 20).

**Elimination rule**: Ideas scoring below FILTER_THRESHOLD (12/20) are eliminated. Record the scores and the reason (which dimension(s) dragged the score down).

**Dynamic threshold adjustment**: If ALL ideas score below FILTER_THRESHOLD (12/20):
1. Lower the threshold to 10/20
2. Keep the top 3 ideas regardless of score
3. Log: "⚠️ All ideas below threshold 12/20. Lowered to 10/20, keeping top 3."
4. If still no ideas survive at 10/20, keep the single highest-scoring idea and log: "⚠️ Emergency: keeping highest-scoring idea (score: X/20) despite low score"

**After Phase 4**: Target SURVIVING_TARGET (4-6) ideas. If more than 6 survive, keep all but note that the top 6 by composite score are recommended. If fewer than 4 survive, revisit eliminated ideas from Phase 3 that scored `MEDIUM IMPACT` or `FEASIBLE WITH CAVEATS` and re-evaluate with the He framework — some may pass on a second look.

### Phase 5: Anti-Pattern Check

Before finalizing the output, check each surviving idea against four common anti-patterns. This is a quality gate to catch ideas that look good on paper but have structural problems.

For each surviving idea, check:

1. **"Overly trendy"** — If 5+ papers in the landscape already address this exact angle, flag it. The space is crowded and differentiation will be hard.

2. **"Overly niche"** — If 0 papers in the landscape are even tangentially related, flag it. The idea may be too far from the current discourse to get reviewer buy-in, or it may indicate an underdeveloped landscape search.

3. **"A+B stitching"** — If the idea is essentially "combine method A and method B" without a clear new mechanism or insight that explains why the combination is non-trivially better, flag it. This is the most common anti-pattern in mediocre research.

4. **"Scale-dependent"** — If the expected result only holds at a computational scale the researcher cannot reproduce (e.g., "this works at 100B parameters but we can only test at 1B"), flag it. The contribution becomes unverifiable.

**Flagging rules**:
- Flagged ideas get a warning label and a one-sentence explanation
- Flagged ideas are NOT automatically eliminated — the user may disagree with the flag or have additional context
- If an idea has 2+ flags, add a strong caution note
- Display flags prominently in the output

### Phase 6: Output

Write two output files. Ensure the `outputs/` directory exists before writing (create it if needed).

#### File 1: `outputs/IDEAS_RAW.md`

This file contains ALL generated ideas before any filtering, serving as a complete record.

```markdown
# Generated Research Ideas (Raw)

**Direction**: [research direction from $ARGUMENTS]
**Date**: [today's date]
**Model**: gpt-5.4
**Landscape source**: [LANDSCAPE.md / abbreviated inline survey]
**Ideas generated**: [N]
**Codex thread ID**: [threadId for follow-up]

---

## IDEA-01: [title]
- **Thesis**: We show that X by Y
- **Gap addressed**: [specific gap from landscape, e.g., "G3: No existing work on Z"]
- **Core mechanism**: [the key technical insight]
- **Non-obvious because**: [skeptic's objection + rebuttal]
- **Contribution type**: [empirical finding / new method / theoretical result / diagnostic / new formulation]
- **Risk**: [LOW / MEDIUM / HIGH] — [1-sentence justification]
- **Effort**: [N] person-weeks
- **Closest work**: [paper title + authors/year] — delta: [what is specifically different]

---

## IDEA-02: [title]
[same structure]

---

[repeat for all ideas]
```

#### File 2: `outputs/IDEAS_FILTERED.md`

This file contains the filtered, scored, and ranked ideas — the actionable output.

```markdown
# Filtered Research Ideas

**Direction**: [research direction from $ARGUMENTS]
**Date**: [today's date]
**Pipeline**: Generated [X] ideas -> Feasibility filter -> Novelty quick-check -> Impact filter -> Prof. He 4-dimension filter -> [Y] surviving
**Landscape source**: [LANDSCAPE.md / abbreviated inline survey]
**Codex thread ID**: [threadId for follow-up]

---

## Surviving Ideas (ranked by Prof. He composite score, descending)

### Rank 1: [title] (IDEA-XX)
- **Thesis**: We show that X by Y
- **Gap addressed**: [specific gap]
- **Core mechanism**: [technical insight]
- **Non-obvious because**: [skeptic's objection + rebuttal]
- **Contribution type**: [type]
- **Risk**: [level] — [justification]
- **Effort**: [N] person-weeks
- **Closest work**: [paper] — delta: [difference]
- **He Score**: Longevity [X] + Passion [X] + Application [X] + Uniqueness [X] = [XX]/20
- **Anti-pattern flags**: [none / list of flags with explanations]
- **Quick novelty**: [LIKELY NOVEL / NEEDS DEEPER CHECK]
- **Why this ranks #1**: [1-2 sentences explaining why this is the top recommendation]

---

### Rank 2: [title] (IDEA-XX)
[same structure]

---

[repeat for all 4-6 surviving ideas]

---

## Eliminated Ideas

| # | Idea | Stage | Reason |
|---|------|-------|--------|
| IDEA-XX | [title] | Feasibility | [e.g., Requires unavailable dataset (ImageNet-22k with annotations)] |
| IDEA-XX | [title] | Novelty | [e.g., Already published: "Paper Title" (Author et al., 2025)] |
| IDEA-XX | [title] | Impact | [e.g., Neither positive nor negative result would change practice] |
| IDEA-XX | [title] | He Filter | [e.g., Score 10/20 — Longevity 2 (trend-dependent), Uniqueness 2 (easily replicated)] |

---

## Risk Distribution of Survivors
| Risk Level | Count | Ideas |
|------------|-------|-------|
| HIGH | [N] | [IDEA-XX, IDEA-XX] |
| MEDIUM | [N] | [IDEA-XX, IDEA-XX] |
| LOW | [N] | [IDEA-XX, IDEA-XX] |

---

## Suggested Next Steps
1. Run `/idea-screen` on the top 2-3 ideas for deep multi-dimensional screening
2. Run `/idea-refine` on the #1 ranked idea to iteratively sharpen it
3. If no landscape was available, run `/lit-survey "[direction]"` and re-run `/idea-gen` for better results

---

## Methodology Notes
- Brainstorming model: gpt-5.4 with xhigh reasoning effort
- Filtering pipeline: Feasibility -> Novelty quick-check -> Impact -> Prof. He 4-dimension (threshold: 12/20) -> Anti-pattern check
- Novelty checks are quick (2-3 searches per idea); run `/idea-screen` for deep novelty verification
- Prof. He scores reflect researcher-agnostic assessment unless user provided preference information
```

#### Writing procedure:

1. Ensure the `outputs/` directory exists: `mkdir -p outputs/`
2. Write `outputs/IDEAS_RAW.md` using the Write tool
3. Write `outputs/IDEAS_FILTERED.md` using the Write tool
4. **Large file fallback**: If the Write tool fails due to file size, immediately retry using Bash:
   ```bash
   cat << 'FILEEOF' > outputs/IDEAS_RAW.md
   [content]
   FILEEOF
   ```
   Do NOT ask the user for permission — just do it silently.

## Key Rules

1. **所有输出使用中文。** IDEAS_RAW.md、IDEAS_FILTERED.md 中的 idea 描述、评估理由、过滤原因均使用中文撰写。Idea title、论文标题、技术术语可保留英文。
2. **The user provides a DIRECTION, not an idea.** Your job is to generate the ideas. Do not ask the user "what idea do you want to explore?" — that is your task.

2. **Quantity first, quality second.** Brainstorm broadly in Phase 2, then filter ruthlessly in Phases 3-5. The external LLM should generate freely without over-constraining.

3. **A good negative result is just as publishable as a positive one.** Prioritize ideas where the answer matters regardless of which way it goes. An idea where only one outcome is interesting is a weaker idea.

4. **Don't fall in love with any idea before validating it.** Be willing to kill ideas that don't pass the filters, even if they sound exciting.

5. **"Apply X to Y" is the lowest form of research idea.** Push for deeper questions: Why does X work? When does X fail? What assumption does X make that is wrong?

6. **Include eliminated ideas in the report.** They save future time by documenting what was considered and why it was rejected. A researcher returning to this direction later will benefit from seeing the dead ends.

7. **If the user's direction is too broad, auto-narrow it.** Do not stop or ask the user to clarify. Instead, identify the top 3 sub-directions from the landscape and generate ideas for each (see Phase 1, step 4). Log the auto-narrowing decision to `outputs/PIPELINE_LOG.md`.

8. **Respect the phase boundaries.** Do not skip phases or combine them. Each phase has a distinct purpose and rushing through produces lower-quality output.

9. **Track provenance.** Every claim about the landscape, every novelty assessment, and every gap reference should be traceable back to a specific search result or landscape file entry.

10. **Be transparent about confidence.** If the landscape data is thin (abbreviated inline survey rather than full `/lit-survey`), say so. If a novelty check is inconclusive, say `NEEDS DEEPER CHECK` rather than guessing.

## Composing with Other Skills

This skill is designed to work as part of a larger research idea pipeline:

```
/lit-survey "direction"    -> landscape (run first for best results)
/idea-gen "direction"      <- you are here
/idea-screen               -> deep multi-dimensional screening of top ideas
/idea-refine               -> iterative refinement of top ideas
/idea-pipeline             -> full automated workflow (runs the above in sequence)
```

**Upstream**: `/lit-survey` produces `outputs/LANDSCAPE.json` and `outputs/LANDSCAPE.md` which this skill consumes. Running `/lit-survey` first significantly improves idea quality because the landscape data is more comprehensive.

**Downstream**: `/idea-screen` takes the surviving ideas from `outputs/IDEAS_FILTERED.md` and performs deep multi-dimensional screening (novelty verification, critical review, competitive analysis). `/idea-refine` then iteratively sharpens the top ideas based on screening feedback.
