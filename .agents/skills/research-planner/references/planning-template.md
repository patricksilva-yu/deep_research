# Planning Template

Use this template when the task is broad enough to justify explicit planning.

## Template

```md
Question
- <restated task>
- <constraints: time, recency, geography, budget, technical depth>

Subquestions
- <subquestion 1>
- <subquestion 2>
- <subquestion 3>

Evidence
- <subquestion 1>: <best source types or artifacts>
- <subquestion 2>: <best source types or artifacts>
- <subquestion 3>: <best source types or artifacts>

Order
- 1. <what to investigate first and why>
- 2. <next step>
- 3. <later step or optional branch>

Stop when
- <what would make the answer good enough>

Deliverable
- <memo, comparison, recommendation, table, timeline, etc.>
```

## Example

```md
Question
- Recommend the best managed Postgres hosting option for a small SaaS in the United States.
- Constraints: current pricing, strong backups, low ops burden, migration effort matters.

Subquestions
- Which providers are credible candidates for this size and use case?
- How do they compare on price, backups, scaling, and operational complexity?
- Which tradeoffs matter most for this user's constraints?

Evidence
- candidate list: official provider docs and pricing pages
- feature comparison: official docs for backups, HA, scaling, regions
- tradeoffs: migration docs, limits, and operational requirements

Order
- 1. Identify a short candidate list from current official sources.
- 2. Compare the must-have operational features.
- 3. Evaluate cost and migration tradeoffs.

Stop when
- The shortlist is stable and the recommendation would not likely change with one more round of searching.

Deliverable
- Short recommendation with a comparison table and caveats.
```
