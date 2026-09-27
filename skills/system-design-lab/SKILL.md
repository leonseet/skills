---
name: system-design-lab
description: >-
  Turns a system-design article URL into a runnable local walkthrough lab:
  playable frontend, docker-compose services plus viewer UIs, and session-based
  walkthrough.html. Use when the user pastes a Hello Interview / ByteByteGo /
  Grokking / system-design article link, says /system-design-lab, or asks to
  generate a lab they can click through, watch in viewers, and read the code.
argument-hint: "<article-url>"
disable-model-invocation: true
---

# System Design Lab

Build a local lab where the user **clicks in the UI → watches the bytes land in a viewer → reads the exact code**. A box that can't close that loop is cut, or gets a lab button (simulate miss, expire, reconcile, reset).

| Read | When |
| --- | --- |
| [references/reference.md](references/reference.md) | stand-ins, ports, compose, gateway, SVG, frontend, README |
| [references/walkthrough.md](references/walkthrough.md) | writing `walkthrough.html` |
| [references/example-ad-click.md](references/example-ad-click.md) | write-path / streaming articles only (method, not domain) |
| `assets/` | copy these files; don't retype them |

## Workflow

```
- [ ] 1. Read the article
- [ ] 2. Propose compose services, wait for go
- [ ] 3. Design labs
- [ ] 4. Build services + frontend
- [ ] 5. Compose + viewers
- [ ] 6. walkthrough.html + README
- [ ] 7. Verify
```

1. **Read.** Extract scale, each box and why it exists, sync/stream/batch edges, and the lesson notes that must show up in code (ordering, keys, idempotency, consistency, repair). If the workspace isn't empty, ask where to write; default is a sibling dir named after the article.
2. **Propose.** One process per box; cloud products become local stand-ins; only stores the design has. List the services (image, job, port) and wait for approval.
3. **Labs.** Lab 0…N, one concept each, designed before code so the UI and viewers exist to serve them.
4. **Build for reading.** The user reads the code to learn the flow, so keep it plain:
   - FastAPI, one file per service when it fits, handlers in flow order, module docstring = the lesson + order of operations.
   - `print(f"[svc] …")` on every interesting event, so the logs are a viewer.
   - Seed the hard case (hot key, conflict, the user the ACL denies).
   - At the end of the main service: `GET /lab/peek` (state at a glance) and `POST /lab/reset` (back to seed: rows, blobs, in-flight uploads, caches).
   - Frontend: one page per role, a **What to try** list, buttons that cause the design.
5. **Compose** is the system and the classroom: a viewer for every store you run.
6. **Walkthrough + README**: [walkthrough.md](references/walkthrough.md), [reference.md](references/reference.md#readme).
7. **Verify.** Stop when every check passes; don't polish past the labs.
   - `docker ps` first. If another project holds a port, tell the user; don't stop it. Then `docker compose config` and `docker compose up --build`.
   - `curl` `:8090/`, `/walkthrough.html`, and every API route (JSON, not the SPA's HTML). `OPTIONS` returns 204.
   - In a browser (`agent-browser`), from `:8090` **and** `file://`: Send every API accordion, the chained flow end to end, and one error case each (403/404/409/422). Reset brings the DB, object store and caches back to the seed. Peek shows `Updated …`.
   - One lab end to end: UI action → viewer shows it → Code link opens the right line.
   - SVGs: every stroke meets a box, no crossings, no clipped labels. Reload with `?v=`.
   - At 420px wide, `scrollWidth` is 420 (no sideways scroll).
   - `python3 tools/code_links.py` runs clean.

## Gotchas

- The browser's HTTP cache hides CDN/cache HIT vs MISS: `fetch(url, { cache: "no-store" })`.
- POST/PATCH/DELETE from `file://` send a preflight: nginx must answer `OPTIONS` with 204.
- Presigned URLs are signed for the host the browser uses (`localhost:9000`), not the Docker hostname. Multipart parts are ≥ 5 MB except the last.
- `:8090` answering HTML to an API call means another lab owns the port.
- `walkthrough.html` is volume-mounted (no rebuild). nginx and frontend changes need `up --build`.
- Any source edit moves lines: re-run `tools/code_links.py`.

## Anti-patterns

- A generic microservice demo with no article lessons in the code; compose without viewers.
- A walkthrough that reads like a blog post (no **Do this**, no viewer); an ASCII `#map`.
- Code pointers as plain text or hand-typed line numbers.
- A peek that only shows state; every API must be callable, plus reset.
- Stores "for completeness"; production hardening (auth, TLS, k8s) unless that is the lesson.

## Output contract

`docker compose up --build`, open `http://localhost:8090/walkthrough.html`, and do every lab without reading the article again.
