# System architecture

*How*, one level above code: how the services, endpoints, schemas, queues, and stores talk to each other.

This stage is high leverage because it is where the model's worst structural defaults get caught: a new service where an existing one already fits, a new table where a column would do, a queue standing in for a function call, a second source of truth for data that already has one. Say which existing pieces the change reuses, by name and path.

## What the section carries

Pick the views the change actually needs.

- **Sequence diagram** for a new or changed interaction across components.
- **Contract shapes** for every endpoint or message that is new or changed: path, request, response.
- **Data model** for schema work: the new or altered tables, and the new query shapes that read them.

Follow the visual vocabulary of the `show-me` skill — invoke it if it's installed, otherwise read [https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md).

## Diagrams that carry their weight

A diagram can lure both of us into a false sense of alignment — it looks precise, so it reads as agreed. Under each one, write the decision it settles in a sentence. A diagram that settles nothing gets cut.
