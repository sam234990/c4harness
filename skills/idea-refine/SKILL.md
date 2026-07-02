---
name: idea-refine
description: "Iterative deep refinement of a research idea via Problem Anchor + skeleton extraction + external LLM review. Turns a rough idea into a venue-ready proposal. Use when user says \"refine idea\", \"打磨idea\", \"deepen this idea\", \"flesh out\", \"细化方案\", or wants to turn a rough idea into a focused, concrete proposal."
argument-hint: "[idea description or reference to SCREENING_RANKED.md]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, mcp__codex__codex, mcp__codex__codex-reply
---

# Idea Refine: Problem-Anchored, Skeleton-Guided, Frontier-Aware Proposal Refinement

Refine and concretize: **$ARGUMENTS**

## Overview

Use this skill when a research idea exists but needs to be turned into a concrete, venue-ready proposal. The goal is not to produce a bloated proposal or a benchmark shopping list. The goal is to turn a rough idea into a **problem -> focused method -> minimal validation** document that is concrete enough to implement, elegant enough to feel paper-worthy, and current enough to resonate in the foundation-model era.

Four principles dominate this skill:

1. **Do not lose the original problem.** Freeze an immutable **Problem Anchor** and reuse it in every round.
2. **The smallest adequate mechanism wins.** Prefer the minimal intervention that directly fixes the bottleneck.
3. **One paper, one dominant contribution.** Prefer one sharp thesis plus at most one supporting contribution.
4. **Modern leverage is a prior, not a decoration.** When LLM / VLM / Diffusion / RL / distillation / inference-time scaling naturally fit the bottleneck, use them concretely. Do not bolt them on as buzzwords.

```
User input (idea + rough approach)
  -> Phase 0 (Claude): Freeze Problem Anchor
  -> Phase 0.5 (Claude): Skeleton Extraction
  -> Phase 1 (Claude): Scan grounding papers -> identify technical gap -> choose the sharpest route -> write focused proposal
  -> Phase 2 (Codex/GPT-5.4): Review for fidelity, specificity, contribution quality, and frontier leverage
  -> Phase 3 (Claude): Parse + Top-2 diagnosis + Skeleton gap check -> revise method -> rewrite full proposal
  -> Phase 4 (Codex, same thread): Re-evaluate revised proposal
  -> Repeat Phase 3-4 until OVERALL SCORE >= 9 or MAX_ROUNDS reached
  -> Phase 5: Save full history to refine-logs/
```

## Constants

- **REVIEWER_MODEL = `gpt-5.4`** — Reviewer model used via Codex MCP.
- **MAX_ROUNDS = 3** — Maximum review-revise rounds. Reduced from 5 to 3 to prevent context window overflow in autonomous mode. Each round accumulates significant context from proposals and reviews.
- **SCORE_THRESHOLD = 9** — Minimum overall score to stop.
- **OUTPUT_DIR = `refine-logs/`** — Directory for round files and final report.
- **MAX_LOCAL_PAPERS = 15** — Maximum local papers/notes to scan for grounding.
- **MAX_PRIMARY_CLAIMS = 2** — Soft cap for paper-level claims. Prefer one dominant claim plus one supporting claim.
- **MAX_NEW_TRAINABLE_COMPONENTS = 2** — Soft cap for genuinely new trainable pieces. Exceed only if the paper breaks otherwise.

> Override via argument if needed, e.g. `/idea-refine "problem | approach" -- max rounds: 2, threshold: 9`.

## Output Structure

```
refine-logs/
├── skeleton.md
├── round-0-initial-proposal.md
├── round-1-review.md
├── round-1-refinement.md
├── round-2-review.md
├── round-2-refinement.md
├── ...
├── REVIEW_SUMMARY.md
├── FINAL_PROPOSAL.md
├── REFINEMENT_REPORT.md
└── score-history.md

outputs/
└── PIPELINE_LOG.md          # Autonomous decision log (appended each run)
```

Every `round-N-refinement.md` must contain a **full anchored proposal**, not just incremental fixes.

## Workflow

### Phase 0: Freeze the Problem Anchor

Before proposing anything, extract the user's immutable bottom-line problem. This anchor must be copied verbatim into every proposal and every refinement round.

Write:

- **Bottom-line problem**: What technical problem must be solved?
- **Must-solve bottleneck**: What specific weakness in current methods is unacceptable?
- **Non-goals**: What is explicitly *not* the goal of this project?
- **Constraints**: Compute, data, time, tooling, venue, deployment limits.
- **Success condition**: What evidence would make the user say "yes, this method addresses the actual problem"?

If later reviewer feedback would change the problem being solved, mark that as **drift** and push back or adapt carefully.

### Phase 0.5: Skeleton Extraction

Before writing the proposal, extract the logical skeleton of the idea. This step forces clarity about what the proposal must communicate and serves as the structural yardstick for every subsequent phase.

Answer the root question:

> "This idea's mission is to move the reviewer from State A to State B. What are A and B?"

#### Steps:

1. **State A**: What does the reviewer currently believe about this problem space? What is the conventional wisdom? What don't they know?
2. **State B**: What must the reviewer believe after reading the proposal? What shift in understanding does this idea require? What beliefs, tools, or conclusions must they have gained?
3. **Skeleton Path**: Identify 3-5 logical steps that form the shortest path from A to B. Each step is a non-skippable logical node. If the reader misses any step, they cannot reach State B.

This skeleton is the **sole yardstick** for the proposal structure. Every section must map to a skeleton step. If a section doesn't map, it's either unnecessary or the skeleton is incomplete.

#### Output Format:

```
State A: [What the reviewer currently believes]
State B: [What the reviewer must believe after reading]
Skeleton: Step 1 -> Step 2 -> ... -> Step N
```

For each skeleton step, write one sentence explaining why this step is non-skippable (what breaks in the reader's understanding if it is omitted).

Save to `refine-logs/skeleton.md`.

### Phase 1: Build the Initial Proposal

#### Step 1.1: Scan Grounding Material

Check `papers/` and `literature/` first. Read only the relevant parts needed to answer:

- What mechanism do current methods use?
- Where exactly do they fail for this problem?
- Which recent LLM / VLM / Diffusion / RL era techniques are actually relevant here?
- What training objectives, representations, or interfaces are reusable?
- What details distinguish a real method from a renamed high-level idea?

If local material is insufficient, search recent top-venue/arXiv work online. Focus on **method sections, training setup, and failure modes**, not just abstracts.

#### Step 1.2: Identify the Technical Gap

Do not stop at generic research questions. Make the gap operational:

1. **Current pipeline failure point**: where does the baseline break?
2. **Why naive fixes are insufficient**: larger context, more data, prompting, memory bank, or stacking more modules.
3. **Smallest adequate intervention**: what is the least additional mechanism that could plausibly fix the bottleneck?
4. **Frontier-native alternative**: is there a more current route using foundation-model-era primitives that better matches the bottleneck?
5. **Core technical claim**: what exact mechanism claim could survive top-venue scrutiny?
6. **Required evidence**: what minimum proof is needed to defend that claim?

#### Step 1.3: Choose the Sharpest Route

Before locking the method, compare two candidate routes if both are plausible:

- **Route A: Elegant minimal route** — the smallest mechanism that directly targets the bottleneck.
- **Route B: Frontier-native route** — a more modern route that uses LLM / VLM / Diffusion / RL / distillation / inference-time scaling *only if* it gives a cleaner or stronger story.

Then decide:

- Which route is more likely to become a strong paper under the stated constraints?
- Which route has the cleaner novelty story relative to the closest work?
- Which route avoids contribution sprawl?

If both routes are weak, rethink the framing instead of combining them into a larger system by default.

#### Step 1.4: Concretize the Method First

The proposal must answer "how would we actually build this?" Prefer method detail over broad experimentation and prefer reuse over invention.

Cover:

1. **One-sentence method thesis**: the single strongest mechanism claim.
2. **Contribution focus**: one dominant contribution and at most one supporting contribution.
3. **Complexity budget**: what is frozen or reused, what is new, and what tempting additions are intentionally excluded.
4. **System graph**: modules, data flow, inputs, outputs.
5. **Representation design**: what latent, embedding, plan token, reward signal, memory state, or alignment space is used?
6. **Training recipe**: data source, supervision, pseudo-labeling, negatives, curriculum, losses, weighting, stagewise vs joint training.
7. **Inference path**: how the trained components are used at test time and what signals flow where.
8. **Why the mechanism stays small**: why a larger stack is unnecessary.
9. **Exact role of any frontier primitive**: if you use an LLM / VLM / Diffusion / RL component, specify whether it acts as planner, teacher, critic, reward model, generator prior, search controller, or distillation source.
10. **Failure handling**: what could go wrong and what fallback or diagnostic exists?
11. **Novelty and elegance argument**: why this is more than naming a module and why the paper still looks focused.

If the method is still only described as "add a module" or "use a planner," it is not concrete enough.

#### Step 1.5: Evaluation Sketch

Instead of a full claim-driven validation section with detailed baselines and ablation designs, write a lightweight evaluation sketch. Detailed experiment planning belongs in a separate `/experiment-plan` step, not here.

```markdown
## Evaluation Sketch
- How would this idea be validated? (1-3 sentences)
- What is the key metric?
- What would success look like?
- What would failure look like?

## Resource Estimate
- Scale: SMALL (1 person-week) / MEDIUM (2-4 person-weeks) / LARGE (1-2 person-months)
- Compute: LOW (single GPU) / MEDIUM (multi-GPU) / HIGH (cluster)
- Data: Available / Needs collection / Needs annotation
```

#### Step 1.6: Write the Initial Proposal

Save to `refine-logs/round-0-initial-proposal.md`.

Use this structure:

```markdown
# Research Proposal: [Title]

## Problem Anchor
- Bottom-line problem:
- Must-solve bottleneck:
- Non-goals:
- Constraints:
- Success condition:

## Skeleton
- State A:
- State B:
- Skeleton Path: Step 1 -> Step 2 -> ... -> Step N

## Technical Gap
[Why current methods fail, why naive bigger systems are not enough, and what mechanism is missing]

## Method Thesis
- One-sentence thesis:
- Why this is the smallest adequate intervention:
- Why this route is timely in the foundation-model era:

## Contribution Focus
- Dominant contribution:
- Optional supporting contribution:
- Explicit non-contributions:

## Proposed Method
### Complexity Budget
- Frozen / reused backbone:
- New trainable components:
- Tempting additions intentionally not used:

### System Overview
[Step-by-step pipeline or ASCII graph]

### Core Mechanism
- Input / output:
- Architecture or policy:
- Training signal / loss:
- Why this is the main novelty:

### Optional Supporting Component
- Only include if truly necessary:
- Input / output:
- Training signal / loss:
- Why it does not create contribution sprawl:

### Modern Primitive Usage
- Which LLM / VLM / Diffusion / RL-era primitive is used:
- Exact role in the pipeline:
- Why it is more natural than an old-school alternative:

### Integration into Base Generator / Downstream Pipeline
[Where the new method attaches, what is frozen, what is trainable, inference order]

### Failure Modes and Diagnostics
- [Failure mode]:
- [How to detect]:
- [Fallback or mitigation]:

### Novelty and Elegance Argument
[Closest work, exact difference, why this is a focused mechanism-level contribution rather than a module pile-up]

## Evaluation Sketch
- How would this idea be validated?
- What is the key metric?
- What would success look like?
- What would failure look like?

## Resource Estimate
- Scale: SMALL / MEDIUM / LARGE
- Compute: LOW / MEDIUM / HIGH
- Data: Available / Needs collection / Needs annotation
```

### Phase 2: External Method Review (Round 1)

Send the full proposal to GPT-5.4 for an **elegance-first, frontier-aware, method-first** review. The reviewer should spend most of the critique budget on the method itself, not on expanding the experiment menu.

```
mcp__codex__codex:
  model: REVIEWER_MODEL
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    You are a senior ML reviewer for a top venue (NeurIPS/ICML/ICLR).
    This is an early-stage, method-first research proposal.

    Your job is NOT to reward extra modules, contribution sprawl, or a giant benchmark checklist.
    Your job IS to stress-test whether the proposed method:
    (1) still solves the original anchored problem,
    (2) is concrete enough to implement,
    (3) presents a focused, elegant contribution,
    (4) uses foundation-model-era techniques appropriately when they are the natural fit.

    Review principles (enforce these strictly):
    1. Trace the reader's journey, not the author's intent
    2. Every claim needs a reason the reader already has
    3. Concepts before terms — don't introduce jargon before the framework
    4. One concept, one name — terminology consistency
    5. Don't defend, state — no defensive language
    6. Precision scales with commitment — don't over-promise
    7. Venue awareness — evaluate for the target venue

    Additional review stance:
    - Prefer the smallest adequate mechanism over a larger system.
    - Penalize parallel contributions that make the paper feel unfocused.
    - If a modern LLM / VLM / Diffusion / RL route would clearly produce a better paper, say so concretely.
    - If the proposal is already modern enough, do NOT force trendy components.
    - Do not ask for extra experiments unless they are needed to prove the core claims.

    Read the Problem Anchor first. If your suggested fix would change the problem being solved,
    call that out explicitly as drift instead of treating it as a normal revision request.

    === PROPOSAL ===
    [Paste the FULL proposal from Phase 1]
    === END PROPOSAL ===

    Score these 7 dimensions from 1-10:

    1. **Problem Fidelity** (weight: 15%): Does the method still attack the original bottleneck, or has it drifted into solving something easier or different?

    2. **Method Specificity** (weight: 25%): Are the interfaces, representations, losses, training stages, and inference path concrete enough that an engineer could start implementing?

    3. **Contribution Quality** (weight: 25%): Is there one dominant mechanism-level contribution with real novelty, good parsimony, and no obvious contribution sprawl?

    4. **Frontier Leverage** (weight: 15%): Does the proposal use current foundation-model-era primitives appropriately when they are the right tool, instead of defaulting to old-school module stacking?

    5. **Feasibility** (weight: 10%): Can this method be trained and integrated with the stated resources and data assumptions?

    6. **Validation Focus** (weight: 5%): Are the proposed experiments minimal but sufficient to validate the core claims? Is there unnecessary experimental bloat?

    7. **Venue Readiness** (weight: 5%): If executed well, would the contribution feel sharp and timely enough for a top venue?

    **OVERALL SCORE** (1-10): Weighted as specified above.

    For each dimension scoring < 7, provide:
    - The specific weakness
    - A concrete fix at the method level (interface / loss / training recipe / integration point / deletion of unnecessary parts)
    - Priority: CRITICAL / IMPORTANT / MINOR

    Then add:
    - **Simplification Opportunities**: 1-3 concrete ways to delete, merge, or reuse components while preserving the main claim. Write "NONE" if already tight.
    - **Modernization Opportunities**: 1-3 concrete ways to replace old-school pieces with more natural foundation-model-era primitives if genuinely better. Write "NONE" if already modern enough.
    - **Drift Warning**: "NONE" if the proposal still solves the anchored problem; otherwise explain the drift clearly.
    - **Verdict**: READY / REVISE / RETHINK

    Verdict rule:
    - READY: overall score >= 9, no meaningful drift, one focused dominant contribution, and no obvious complexity bloat remains
    - REVISE: the direction is promising but not yet at READY bar
    - RETHINK: the core mechanism or framing is still fundamentally off
```

**Codex MCP failure handling**: If `mcp__codex__codex` is unavailable:
1. Fall back to Claude performing the review directly
2. Use the same 7-dimension scoring prompt
3. Log: "Warning: Codex MCP unavailable. Review performed by Claude (self-review — reduced objectivity)."
4. Lower SCORE_THRESHOLD to 8 when in self-review mode (Claude reviewing its own work is inherently less critical)
5. Continue pipeline — do NOT stop or ask the user.

**CRITICAL: Save the `threadId`** from this call for all later rounds.

**CRITICAL: Save the FULL raw response** verbatim.

Save review to `refine-logs/round-1-review.md` with the raw response in a `<details>` block.

### Phase 3: Parse Feedback and Revise the Method

#### Step 3.1: Parse the Review

Extract:

- **Problem Fidelity** score
- **Method Specificity** score
- **Contribution Quality** score
- **Frontier Leverage** score
- **Feasibility** score
- **Validation Focus** score
- **Venue Readiness** score
- **Overall score**
- **Verdict**
- **Drift Warning**
- **Simplification Opportunities**
- **Modernization Opportunities**
- **Action items** ranked by priority

Update `refine-logs/score-history.md`:

```markdown
# Score Evolution

| Round | Problem Fidelity | Method Specificity | Contribution Quality | Frontier Leverage | Feasibility | Validation Focus | Venue Readiness | Overall | Verdict |
|-------|------------------|--------------------|----------------------|-------------------|-------------|------------------|-----------------|---------|---------|
| 1     | X                | X                  | X                    | X                 | X           | X                | X               | X       | REVISE  |
```

**STOP CONDITION**: If overall score >= SCORE_THRESHOLD, verdict is READY, and there is no unresolved drift warning, skip to Phase 5.

**Automatic convergence**: When MAX_ROUNDS is reached but score < SCORE_THRESHOLD:
1. Do NOT ask the user what to do
2. Select the proposal version with the highest overall score across all rounds
3. Use that version as FINAL_PROPOSAL.md
4. Set verdict to the actual verdict from that round (REVISE or RETHINK)
5. Log: "Warning: Reached MAX_ROUNDS (3) without achieving score threshold (9/10). Best score: X/10 from round N. Using that version as final proposal."
6. Continue to Phase 5 (Final Report) normally

#### Step 3.2: Top-2 Diagnosis

Instead of trying to fix everything the reviewer mentioned, identify exactly the **top 2 largest remaining problems**. Not 3, not 5 — exactly 2. This forces prioritization and prevents the proposal from oscillating between too many changes per round.

For each of the two issues, answer from first principles:

1. **What would the reader experience?** Trace the reader's sentence-by-sentence journey through the proposal. Where does confusion arise? Where does skepticism trigger? At which point would a reader stop believing the argument?
2. **What would a hostile reviewer write?** Formulate the specific criticism or question that an adversarial reviewer would raise. Make it concrete — not "the method is vague" but "the training signal for component X is undefined; how would gradients flow from Y to Z?"
3. **Why is this a problem at the structural level?** Don't just say "this part is weak" — explain the logical gap it creates in the skeleton (from Phase 0.5). Which skeleton step is broken or missing support?

#### Step 3.3: Skeleton Gap Check

For each skeleton step (from Phase 0.5), verify:

- Is there a section in the current proposal that carries this step?
- Does that section complete the step convincingly, or is it superficial?

If a skeleton step has no corresponding section, that is a **LOGICAL GAP** — a point where a reviewer will attack. For each gap:

- What is missing?
- What happens if this gap is not filled? (Where will the reader be confused? Where will reviewer attacks come from?)
- How should it be filled? (Direction and approximate scope)

If the skeleton itself needs revision based on what was learned during review, update `refine-logs/skeleton.md` and note the change.

#### Step 3.4: Revise With Anchor Check, Simplicity Check, and Top-2 Focus

Before changing anything:

1. Copy the **Problem Anchor verbatim**.
2. Write an **Anchor Check**:
   - What is the original bottleneck?
   - Does the current method still solve it?
   - Which reviewer suggestions would cause drift if followed blindly?
3. Write a **Simplicity Check**:
   - What is the dominant contribution now?
   - What components can be removed, merged, or kept frozen?
   - Which reviewer suggestions add unnecessary complexity?
   - If a frontier primitive is central, is its role still crisp and justified?

Then process reviewer feedback with the Top-2 diagnosis as the primary guide:

- If **valid**: sharpen the mechanism, simplify if possible, or modernize if the paper really improves.
- If **debatable**: revise, but explain your reasoning with evidence.
- If **wrong, drifting, or over-complicating**: push back with evidence from local papers and the Problem Anchor.

Bias the revisions toward:

- a sharper central contribution
- fewer moving parts
- cleaner reuse of strong existing backbones
- more natural foundation-model-era leverage when it improves the paper
- filling skeleton gaps identified in Step 3.3

Do **not** add multiple parallel contributions just to chase score. If the reviewer requests another module, first ask whether the same gain can come from a better interface, distillation signal, reward model, or inference policy on top of an existing backbone.

Save to `refine-logs/round-N-refinement.md`:

```markdown
# Round N Refinement

## Problem Anchor
[Copy verbatim from round 0]

## Anchor Check
- Original bottleneck:
- Why the revised method still addresses it:
- Reviewer suggestions rejected as drift:

## Simplicity Check
- Dominant contribution after revision:
- Components removed or merged:
- Reviewer suggestions rejected as unnecessary complexity:
- Why the remaining mechanism is still the smallest adequate route:

## Top-2 Issues Diagnosed

### Issue 1: [Title]
- Reader experience: [What confusion or skepticism arises]
- Hostile reviewer critique: [Specific attack]
- Structural impact: [Which skeleton step is broken]

### Issue 2: [Title]
- Reader experience: [What confusion or skepticism arises]
- Hostile reviewer critique: [Specific attack]
- Structural impact: [Which skeleton step is broken]

## Skeleton Gap Check
| Skeleton Step | Covered by Section? | Assessment | Action Needed? |
|---------------|---------------------|------------|----------------|
| Step 1        | [section name]      | [adequate / superficial / missing] | [yes/no + what] |
| Step 2        | ...                 | ...        | ...            |

## Changes Made

### 1. [Method section changed]
- Reviewer said:
- Action:
- Reasoning:
- Impact on core method:

### 2. [Method section changed]
- Reviewer said:
- Action:
- Reasoning:
- Impact on core method:

## Revised Proposal
[Full updated proposal from Problem Anchor through Evaluation Sketch — complete, not incremental]
```

### Phase 4: Re-evaluation (Round 2+)

Send the revised proposal back to GPT-5.4 in the **same thread**.

**Context management**: Before sending the re-evaluation prompt, summarize previous rounds to control context size:
- Round 1 review: include full text (it's the first review)
- Round 2+ reviews: summarize each previous review to 5-7 bullet points covering:
  - Overall score and verdict
  - Top 2 issues identified
  - Key changes requested
  - What was resolved vs. what remains
- Never include raw reviewer text from rounds older than the immediately previous round
- This ensures the prompt stays under ~4000 tokens of review history regardless of round count

```
mcp__codex__codex-reply:
  threadId: [saved from Phase 2]
  model: REVIEWER_MODEL
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N re-evaluation]

    I revised the proposal based on your feedback.
    First, check whether the original Problem Anchor is still preserved.
    Second, judge whether the method is now more concrete, more focused, and more current.

    Key changes:
    1. [Method change 1]
    2. [Method change 2]
    3. [Simplification / modernization / pushback if any]

    === REVISED PROPOSAL ===
    [Paste the FULL revised proposal]
    === END REVISED PROPOSAL ===

    Please:
    - Re-score the same 7 dimensions and overall
    - State whether the Problem Anchor is preserved or drifted
    - State whether the dominant contribution is now sharper or still too broad
    - State whether the method is simpler or still overbuilt
    - State whether the frontier leverage is now appropriate or still old-school / forced
    - Focus new critiques on missing mechanism, weak training signal, weak integration point, pseudo-novelty, or unnecessary complexity
    - Use the same verdict rule: READY only if overall score >= 9 and no blocking issue remains

    Same output format: 7 scores, overall score, verdict, drift warning, simplification opportunities, modernization opportunities, remaining action items.
```

Save review to `refine-logs/round-N-review.md`.

Then return to Phase 3 until:

- **Overall score >= SCORE_THRESHOLD** and verdict is READY and no unresolved drift
- or **MAX_ROUNDS reached** — in which case, apply the automatic convergence rule from Phase 3, Step 3.1 (select best-scoring version, log the shortfall, and proceed to Phase 5 without user interaction)

### Phase 5: Final Report and Logs

#### Step 5.1: Write `refine-logs/REVIEW_SUMMARY.md`

This file is the high-level round-by-round review record. It should answer: each round was trying to solve what, what changed, what got resolved, and what remained.

```markdown
# Review Summary

**Problem**: [user's problem]
**Initial Approach**: [user's vague approach]
**Date**: [today]
**Rounds**: N / MAX_ROUNDS
**Final Score**: X / 10
**Final Verdict**: [READY / REVISE / RETHINK]

## Problem Anchor
[Verbatim anchor used across all rounds]

## Skeleton
[Final skeleton from Phase 0.5, noting any revisions made during refinement]

## Round-by-Round Resolution Log

| Round | Main Reviewer Concerns | What This Round Simplified / Modernized | Top-2 Issues Targeted | Solved? | Remaining Risk |
|-------|-------------------------|------------------------------------------|-----------------------|---------|----------------|
| 1     | [top issues from review] | [main method changes]                    | [the 2 issues]        | [yes / partial / no] | [if any] |
| 2     | ...                     | ...                                      | ...                   | ...     | ...            |

## Overall Evolution
- [How the method became more concrete]
- [How the dominant contribution became more focused]
- [How unnecessary complexity was removed]
- [How modern technical leverage improved or stayed intentionally minimal]
- [How drift was avoided or corrected]
- [How skeleton gaps were filled across rounds]

## Final Status
- Anchor status: [preserved / corrected / unresolved]
- Focus status: [tight / slightly broad / still diffuse]
- Modernity status: [appropriately frontier-aware / intentionally conservative / still old-school]
- Skeleton completeness: [all steps covered / gaps remain at steps X, Y]
- Strongest parts of final method:
- Remaining weaknesses:
```

#### Step 5.2: Write `refine-logs/FINAL_PROPOSAL.md`

This file is the clean final version document. It should contain only the final proposal itself, without review chatter, round history, or raw reviewer output.

```markdown
# Research Proposal: [Title]

[Paste the final refined proposal only]
```

If the final verdict is not READY, still write the best current final version here.

#### Step 5.3: Write `refine-logs/REFINEMENT_REPORT.md`

```markdown
# Refinement Report

**Problem**: [user's problem]
**Initial Approach**: [user's vague approach]
**Date**: [today]
**Rounds**: N / MAX_ROUNDS
**Final Score**: X / 10
**Final Verdict**: [READY / REVISE / RETHINK]

## Problem Anchor
[Verbatim anchor used across all rounds]

## Skeleton
[Final skeleton]

## Output Files
- Review summary: `refine-logs/REVIEW_SUMMARY.md`
- Final proposal: `refine-logs/FINAL_PROPOSAL.md`
- Skeleton: `refine-logs/skeleton.md`

## Score Evolution

| Round | Problem Fidelity | Method Specificity | Contribution Quality | Frontier Leverage | Feasibility | Validation Focus | Venue Readiness | Overall | Verdict |
|-------|------------------|--------------------|----------------------|-------------------|-------------|------------------|-----------------|---------|---------|
| 1     | ...              | ...                | ...                  | ...               | ...         | ...              | ...             | ...     | ...     |

## Round-by-Round Review Record

| Round | Main Reviewer Concerns | Top-2 Issues Targeted | What Was Changed | Result |
|-------|-------------------------|-----------------------|------------------|--------|
| 1     | [top issues]            | [the 2 issues]        | [main fixes]     | [resolved / partial / unresolved] |
| 2     | ...                     | ...                   | ...              | ...    |

## Final Proposal Snapshot
- Canonical clean version lives in `refine-logs/FINAL_PROPOSAL.md`
- Summarize the final thesis in 3-5 bullets here

## Method Evolution Highlights
1. [Most important simplification or focusing move]
2. [Most important mechanism upgrade]
3. [Most important modernization or justification for staying simple]

## Pushback / Drift Log
| Round | Reviewer Said | Author Response | Outcome |
|-------|---------------|-----------------|---------|
| 1     | [criticism]   | [pushback + anchor / evidence] | [accepted / rejected] |

## Remaining Weaknesses
[Honest unresolved issues]

## Raw Reviewer Responses

<details>
<summary>Round 1 Review</summary>

[Full verbatim response from GPT-5.4]

</details>

...

## Next Steps
- If READY: the proposal is venue-ready; proceed to experiment planning if needed
- If REVISE: the best available version has been saved as FINAL_PROPOSAL.md. Remaining weaknesses are documented above. A follow-up `/idea-refine` run can target them.
- If RETHINK: the core mechanism may need fundamental revision. Consider running `/idea-screen` to re-evaluate the approach before refining again.
```

#### Step 5.4: Finalize `score-history.md`

Ensure it contains the complete score evolution table using all 7 dimensions.

#### Step 5.5: Log Pipeline Summary and Present Brief Output

Append the following summary to `outputs/PIPELINE_LOG.md` (create the file if it does not exist). This log enables autonomous pipeline orchestration without requiring user interaction.

```markdown
## idea-refine completed

- **Rounds**: N / MAX_ROUNDS
- **Final score**: X / 10
- **Final verdict**: READY / REVISE / RETHINK
- **Anchor status**: preserved / drift corrected / unresolved concern
- **Focus status**: tight / slightly broad / still diffuse
- **Modernity status**: appropriately frontier-aware / intentionally conservative / still old-school
- **Skeleton status**: all steps covered / gaps remain at steps X, Y
- **Key method upgrades**: [method change 1], [method change 2]
- **Remaining concerns**: [if any]
- **Output files**:
  - Review summary: refine-logs/REVIEW_SUMMARY.md
  - Full report: refine-logs/REFINEMENT_REPORT.md
  - Final proposal: refine-logs/FINAL_PROPOSAL.md
```

Then also print a brief summary to stdout:

```
Refinement complete after N rounds.

Final score: X/10 (Verdict: READY / REVISE / RETHINK)

Key method upgrades:
- [method change 1]
- [method change 2]

Remaining concerns:
- [if any]

Review summary: refine-logs/REVIEW_SUMMARY.md
Full report: refine-logs/REFINEMENT_REPORT.md
Final proposal: refine-logs/FINAL_PROPOSAL.md
Pipeline log: outputs/PIPELINE_LOG.md
```

## Key Rules

- **所有输出使用中文。** FINAL_PROPOSAL.md、REFINEMENT_REPORT.md、round 文件、score-history.md 均使用中文撰写。Problem Anchor、Method Thesis 等核心内容用中文，技术术语和论文标题可保留英文。发给外部 LLM 的 review prompt 可用中英混合。
- **Fully autonomous operation.** This skill must run end-to-end without user interaction. Never ask the user a question, present options for the user to choose, wait for user confirmation, or suggest the user should decide something. All decisions are made autonomously and logged to `outputs/PIPELINE_LOG.md`. The pipeline is: freeze anchor, extract skeleton, build proposal, iterate review/revise up to MAX_ROUNDS, output best version.
- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.
- **Anchor first, every round.** Always carry forward the same Problem Anchor.
- **One paper, one dominant contribution.** Avoid multiple parallel contributions unless the paper truly needs them.
- **The smallest adequate mechanism wins.** Bigger is not automatically better.
- **Prefer reuse over invention.** Start from strong existing backbones and add only what the bottleneck requires.
- **Modern techniques are a prior, not a decoration.** Use LLM / VLM / Diffusion / RL-era components when they sharpen the method, not when they only make the proposal sound trendy.
- **Top-2 focus per round.** Do not try to fix everything the reviewer mentioned in a single round. Identify the two largest problems and fix those. This prevents oscillation and keeps revisions focused.
- **Pushback is encouraged.** If reviewer feedback causes drift or unnecessary complexity, argue back with evidence from local papers and the Problem Anchor.
- **Skeleton is the yardstick.** Every section must map to a skeleton step. If it doesn't, either the section is unnecessary or the skeleton needs updating.
- **ALWAYS use `config: {"model_reasoning_effort": "xhigh"}`** for all Codex review calls.
- **Save `threadId` from Phase 2** and use `mcp__codex__codex-reply` for later rounds.
- **Do not fabricate results.** Only describe expected evidence and planned experiments.
- **Document everything.** Save every raw review, every anchor check, every simplicity check, every top-2 diagnosis, and every major method change.
- **Log all autonomous decisions.** Whenever the skill makes a decision that would previously have required user input (convergence without threshold, Codex fallback, route selection, etc.), append a timestamped entry to `outputs/PIPELINE_LOG.md`.

## Composing with Other Skills

This skill sits between idea screening and execution:

```
/idea-screen -> /idea-refine  <- you are here
/idea-pipeline orchestrates the full flow
```

Typical flow:

1. `/idea-screen` evaluates and ranks candidate ideas
2. `/idea-refine` turns the top idea into an anchored, elegant, frontier-aware method proposal
3. Further experiment planning and execution happen downstream

This skill also works standalone if you already have an idea and just need the method to become concrete and venue-ready.
