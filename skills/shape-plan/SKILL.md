---
name: shape-plan
description: Shape the planning artifacts before any implementation code — product review, system architecture, program design, test strategy. Name stages to run a subset; no argument runs all four.
argument-hint: "[stages...] <what you're building>"
disable-model-invocation: true
---

# Shape Plan

Planning runs before any implementation code. Each stage adds one section to a single **master plan**, and that plan's job is a **shared understanding** between the user and you:


| Stage                 | Question                                               | Guidelines                                                               |
| --------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------ |
| `product-review`      | *what* and *why*, in the user's terms                  | `[references/product-review.md](references/product-review.md)`           |
| `system-architecture` | *how*, at the level of services, contracts, and stores | `[references/system-architecture.md](references/system-architecture.md)` |
| `program-design`      | *how*, at the level of the shape of code               | `[references/program-design.md](references/program-design.md)`           |
| `test-strategy`       | what proves it works, pre-approved                     | `[references/test-strategy.md](references/test-strategy.md)`             |




## Where to save artifacts

Everything for a feature lives in `docs/shape-plans/<feature-slug>/`.

`master.md` holds the whole plan, with one `## <Stage>` heading per stage in table order. Each stage edits that file.

Every other artifact (e.g. mockups, HTML, mermaid diagrams, etc) sits beside `master.md` in that same folder, and `master.md` links to it at the point in the section that discusses it.
