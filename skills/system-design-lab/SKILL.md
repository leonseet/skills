---
name: system-design-lab
description: >-
  Turns a system-design article URL into a runnable local walkthrough lab:
  playable frontend, docker-compose services plus viewer UIs, and session-based
  walkthrough.html. Use when the user pastes a Hello Interview / ByteByteGo /
  Grokking / system-design article link, says /system-design-lab, or asks to
  generate a lab they can click through, watch in viewers, and read the code.
---

# System Design Lab

Generate a local lab from a system-design article so the user can:

- try it in the UI
- see the change in the services
- review the code to understand how they flow

`walkthrough.html` holds the current sessions. `docker-compose.yml` holds the services we need and also the viewer services required as well. `frontend/` is there to play with.

Do not copy the ad-click domain into every lab. Recreate the *job* each article box does.

## Learning loop

Every generated lab must close this loop:

1. Click something in `frontend/`
2. Watch the bytes land in a viewer (or `docker compose logs` / `exec`)
3. Read the exact file the walkthrough names

If a box cannot be triggered from the UI and inspected in a viewer, it does not belong in the first cut — or it needs a lab button (simulate miss, reconcile, replay, expire, …).

## Workflow

Copy and track:

```
Lab progress:
- [ ] 1. Read the article
- [ ] 2. Distill local architecture
- [ ] 3. Design labs before code
- [ ] 4. Scaffold repo
- [ ] 5. Implement services, jobs, frontend
- [ ] 6. Compose + viewers
- [ ] 7. walkthrough.html + README
- [ ] 8. Verify
```

### 1. Read the article

Fetch the URL. Extract:

- problem and scale numbers
- component boxes and why each exists
- sync HTTP vs async stream vs batch edges
- **lesson notes that must show up in code** (ordering, keys, idempotency, consistency, repair)

Ask the user where to write the lab if the current workspace is not empty. Default: a sibling directory named after the article (`url-shortener`, `news-feed`, …).

### 2. Distill a local architecture

One OS process per diagram box. Cloud product names become local stand-ins — see [reference.md](reference.md). Do not recreate AWS.

Only pull Flink, ClickHouse, MinIO, Redis, Kafka, etc. when that box exists in the design. A cache lesson does not need a lake.

If the article is a write-path / streaming / lambda design, also read [example-ad-click.md](example-ad-click.md).

### 3. Design labs before code

Numbered sessions: Lab 0 … Lab N. One concept each. Design the sessions *before* scaffolding so the UI and viewers exist to serve them.

Each lab must include:

- Mini path SVG (this hop only) with a link back to the full architecture
- **Code:** exact files + symbols
- **Do this:** UI clicks or one API call
- **Viewer:** which companion UI shows the bytes
- **If viewer is down:** a `docker compose exec …` CLI

### 4. Scaffold

```
README.md
docker-compose.yml
walkthrough.html
gateway/          nginx + built UI; walkthrough mounted
frontend/         Vite + React, one page per role
services/         FastAPI, one folder per online box
jobs/             stream / batch workers (only if needed)
shared/           settings + clients
infra/            seed SQL, topic scripts
```

### 5. Implement for walkthrough, not production

- FastAPI + small Python. One file per service when it fits.
- Module docstring restates the lesson (why this box, required order of operations).
- `print` on every interesting event so `docker compose logs -f` is a viewer.
- Seed data that makes the *hard* case visible (hot key, expired row, conflict, celebrity shard).
- Frontend: role pages, a “What to try” list, buttons that *cause* the design.

### 6. Compose + viewers

`docker-compose.yml` is both the system *and* the classroom. Always include viewers for stores you actually run. Lab UI listens on **8090** (do not steal 8080). Port map and image pins: [reference.md](reference.md).

Gateway serves the SPA and `walkthrough.html` (nginx + Vite build, walkthrough volume-mounted so HTML edits do not require a frontend rebuild).

### 7. Walkthrough + README

Same paper/ink serif look as the `ad_click_aggregator` lab’s `frontend/src/styles.css` / `walkthrough.html`.

README is one command (`docker compose up --build`), a viewer table with URLs and creds, “why each box exists,” and the request-path ASCII.

### 8. Verify

- `docker compose config` must parse
- If Docker is available: `docker compose up --build`, then hit `/` and `/walkthrough.html`
- Walk one lab: UI action → viewer shows bytes → named file exists
- Stop when the loop works. Do not polish past the labs.

## Output contract

The user should be able to:

```bash
docker compose up --build
```

then open `http://localhost:8090/walkthrough.html` and do every lab without reading the article again.

## Anti-patterns

- Generic microservice demo with no article lessons in the code
- Compose stack with no viewers
- Walkthrough that is a blog post (no **Do this** / no viewer)
- Shipping Flink/ClickHouse/MinIO “because the gold standard has them”
- Production hardening (auth, TLS, k8s, multi-AZ) unless the article *is* that lesson
