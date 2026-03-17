---
name: research-planner
description: Build concise, actionable research plans for broad, ambiguous, or multi-step questions before deep investigation begins. Use when Codex needs to decompose a research problem into subquestions, identify the evidence needed to answer each one, choose a source strategy, sequence the work, or define stopping conditions and deliverable shape.
---

# Research Planner

## Overview

Turn an underspecified or complex research task into a short plan that is executable. Focus on reducing wasted search, clarifying what evidence would settle the question, and sequencing the work so the most decision-relevant unknowns are handled first.

Keep plans lean. A plan is a tool for investigation, not a second report.

## When To Plan

Create a research plan when one or more of these are true:
- the request is broad or ambiguous
- the answer depends on several subquestions
- source selection will materially affect the result
- there are multiple plausible ways to investigate
- the user wants rigor, comprehensiveness, or a defensible process
- the task risks drifting into unfocused browsing

Skip formal planning for narrow questions with an obvious source and a short path to an answer.

## Planning Workflow

### 1. Define the question precisely

Rewrite the task in operational terms:
- what is the exact question
- what decision or output is this supposed to support
- what constraints matter: time, geography, recency, source type, budget, technical depth
- what would count as a satisfactory answer

If the user asked a vague question, identify the ambiguity explicitly instead of hiding it inside the plan.

### 2. Decompose into subquestions

Break the task into the minimum set of subquestions needed to answer the main question. Avoid parallel branches that do not change the likely outcome.

Good subquestions usually cover:
- definitions and scope
- current state or baseline facts
- key comparisons or alternatives
- evidence of quality, risk, or cost
- unresolved unknowns that could change the answer

### 3. Define evidence needs

For each subquestion, state what evidence would answer it:
- primary documents
- official documentation
- source code or local files
- reputable reporting
- datasets or measurements
- expert commentary, only when primary evidence is insufficient

Do not plan around sources just because they are easy to search. Plan around sources that can actually settle the question.

### 4. Prioritize the work

Order subquestions by expected impact:
- answer blockers first
- unstable or time-sensitive facts early
- expensive branches only after cheaper discriminators
- leave low-impact nice-to-knows for last or omit them

### 5. Set stopping conditions

Define when the research is good enough:
- the main subquestions have evidence-backed answers
- the remaining uncertainty is visible and bounded
- additional searching is unlikely to materially change the conclusion
- the deliverable can be written without hand-waving

### 6. Choose the deliverable shape

State what the final answer should look like:
- short recommendation
- comparative table
- research memo
- ranked options
- timeline
- unresolved-risk list

## Planning Rules

- Keep the plan short enough to execute immediately.
- Prefer 3-7 subquestions, not exhaustive decomposition.
- State assumptions that shape the plan.
- Distinguish must-answer questions from optional enrichment.
- Revise the plan if early evidence invalidates the original path.
- Do not pretend uncertain scope has been resolved if it has not.

## Output Format

Use a compact structure:

- `Question`: restated task and constraints
- `Subquestions`: the minimum set needed to answer it
- `Evidence`: what sources or artifacts will answer each subquestion
- `Order`: what to investigate first and why
- `Stop when`: the threshold for sufficient confidence
- `Deliverable`: the intended final output shape

## Reference

Use [planning-template.md](./references/planning-template.md) when you need a reusable template or examples.
