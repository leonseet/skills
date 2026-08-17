# Program design

The level below system architecture and above code: the **shape of code** — the types, the method signatures, the program layout, the call stacks.

## What the section carries

Draw the shape of code with the full visual vocabulary of the `show-me` skill — invoke it if it's installed, otherwise read [https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md). Light pseudocode beats mermaid at this level, and anything too dense for either earns its own HTML artifact beside `master.md`.

The views compound — each one tells a different part of the story, so carry every view the change needs to be understood.


## Choosing what to write down

Spend the space on code where a wrong guess is expensive: the domain types, the function whose signature fixes everyone else's, the control flow with a branch that's easy to get backwards. Boilerplate the codebase's own patterns already determine gets named in the file tree and nothing more.

Names come from the codebase's existing vocabulary. Where you introduce a new term, say what it means.

