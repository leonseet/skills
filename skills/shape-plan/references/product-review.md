# Product review

The stage that turns sentences or a rambling voice note into something structured: *what* we're building and *why*. It stays in the product space with focus on user experience and not technical requirements.

## What the section carries

**Problem to solve** — the actual user pain, in the user's terms. Who hits it, when, and what they do today instead.

**What success looks like** — what we can read after shipping to decide the thing was worth building. Reach for a user outcome first ("finishes the XYZ workflow in less time", "hits onboarding milestone ABC earlier"). Where no user outcome is readable, a number works (error rate, latency), and so does "the support tickets about X stop."

**Scope** — what this change covers, and the neighbouring things it deliberately does not.

**Mockups** — anything the user sees, you mock up rather than describe. A rough HTML mockup of the actual screen settles in one look an argument three paragraphs only prolong. Write it into `docs/plans/<feature-slug>/` and link it from this section. For a workflow or a state machine, a JSON or YAML outline of the steps and exits does the same job.

## Staying in the product space

Do not procide any technical details at this point, stay in the product space.

When a technical unknown genuinely blocks a product decision, say so and offer the two exits: commit what's already settled and take the question into system architecture, or build a throwaway prototype to find out whether the thing is feasible at all using the `prototype` skill.

