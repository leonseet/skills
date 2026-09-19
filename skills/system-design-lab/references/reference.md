# System Design Lab — reference

Read this after `SKILL.md` when scaffolding. Copy conventions, not the ad-click domain.

## Cloud → local stand-ins

Recreate the *job*, not the brand. Only include a row if the article has that box.

| Article says | Local stand-in | Viewer |
| --- | --- | --- |
| Kinesis / PubSub / EventBridge | Kafka (Apache Kafka 3.8 KRaft, 7-day retention if the lesson mentions replay) | Kafka UI `:8091` |
| S3 / GCS / Firehose / Kafka Connect S3 | MinIO | MinIO console `:9001` |
| Spark / MapReduce / EMR | Short Python job (`jobs/<name>/main.py`) with an HTTP trigger + optional cron | `docker compose logs` + lab button |
| Dynamo / ElastiCache / "the cache" | Redis 7 | Redis Commander `:8092` |
| RDS / "the DB" / catalog | Postgres 16 | Adminer `:8093` |
| Redshift / Druid / "OLAP" / pre-aggregated query store | ClickHouse | ClickHouse Play `:8123/play` |
| Flink / Spark Streaming / Kinesis Analytics | Flink SQL **or** a small Python consumer if a full cluster teaches nothing extra | Flink dashboard `:8081` |
| ALB / API Gateway | nginx in `gateway/` | Lab UI `:8090` |
| Lambda / ECS task / "a worker" | Python process in `jobs/` or `services/` | logs |
| CloudWatch | `print` + `docker compose logs -f` | — |

Do not add a store "for completeness." A news-feed lab may need Redis + Postgres and nothing else.

## Port map (keep stable across labs)

| Surface | Port | Notes |
| --- | --- | --- |
| Lab UI + walkthrough (nginx) | **8090** | Never bind the product UI to 8080 |
| Kafka host listener | 9092 | In-docker listener `kafka:9093` |
| Flink JM | 8081 | Only if Flink runs |
| ClickHouse HTTP | 8123 | user/pass `olap` / `olap` |
| MinIO S3 | 9000 (internal) | console **9001**, user `minio` / `minio12345` |
| Kafka UI | 8091 | |
| Redis Commander | 8092 | |
| Adminer | 8093 | System PostgreSQL, server `postgres` |

Pin images. Reuse the versions from the `ad_click_aggregator` lab when the same store appears:

- `postgres:16-alpine`
- `redis:7-alpine`
- `apache/kafka:3.8.1`
- `clickhouse/clickhouse-server:24.8`
- `quay.io/minio/minio:RELEASE.2024-11-07T00-52-20Z`
- `provectuslabs/kafka-ui:v0.7.2`
- `rediscommander/redis-commander:latest`
- `adminer:4`
- `nginx:1.27-alpine` (gateway)
- `python:3.12-slim` (services + jobs)
- `node:22-alpine` (frontend build stage)

## Compose conventions

- One service per diagram box. Shared env via YAML anchor (`x-python-env`).
- Healthchecks on stores; app services `depends_on: condition: service_healthy`.
- Init containers for topics / buckets (`kafka-init`, `minio-init`).
- Generic Dockerfiles with a build `ARG` (`SERVICE`, `JOB`) so each process is a one-liner in compose.
- Gateway last: port `8090:80`, volume `./walkthrough.html:/usr/share/nginx/html/walkthrough.html:ro`.
- Companion viewers always `depends_on` their store.

Gateway nginx: resolve Docker DNS (`resolver 127.0.0.11`), proxy each API prefix to one upstream, `try_files` the SPA, exact location for `/walkthrough.html`.

```
location /ads        → ad-placement:8000
location /click      → click-processor:8000
location /analytics  → analytics:8000
location = /walkthrough.html
location /           → SPA
```

Replace prefixes with the article’s API surface.

## Walkthrough page

Single static HTML, same visual language as the frontend (see below). Served at `/walkthrough.html`.

### Required sections (in order)

1. **How to use** — keep this tab open; do the lab in the UI; open the viewer
2. **TOC** — `#architecture`, `#map`, `#viewers`, `#lab0` … `#labN`
3. **System architecture** — one SVG; every box is a link to its lab (or `/` / `/analyst`). Legend for client / service / store / job and for sync / stream / batch edges
4. **Live peek** (optional) — `fetch` the same gateway routes the UI uses
5. **What each box is for** — ASCII request path
6. **Where to watch the data** — card per viewer: Built-in / Companion / CLI
7. **Labs** — one `<section id="labN">` per session
8. **CLI cheat sheet** — table of `docker compose exec` fallbacks

### Lab section template

```html
<section id="labN">
  <h2>Lab N — <concept></h2>
  <p><!-- why this hop exists; the lesson note --></p>
  <figure class="lab-arch">
    <p class="eyebrow">This lab · <a href="#architecture">full architecture</a></p>
    <!-- SVG of THIS hop only. Highlight the active box; fade context. -->
  </figure>
  <p><strong>Code:</strong> <span class="file">path/to/file.py</span> <code>symbol</code></p>
  <p><strong>Do this</strong></p>
  <ol>
    <li>UI action with a real href (e.g. <a href="/">User page</a>).</li>
    <li>Viewer action with a real href (e.g. Kafka UI).</li>
    <li>What the user should see (key name, log line, row).</li>
  </ol>
  <p><strong>If <viewer> is down</strong></p>
  <pre>docker compose exec …</pre>
</section>
```

Architecture SVG colors (match CSS tokens):

| Kind | Fill | Stroke |
| --- | --- | --- |
| Client / gateway | `#fff7ed` | `#b45309` (gateway fill `#b45309`, text `#fff7ed`) |
| Online service | `#fffaf2` | `#1c1917` |
| Store | `#ecfccb` | `#3f6212` |
| Job / stream processor | `#ffedd5` | `#9a3412` |

Edges: solid = sync HTTP, dashed = stream, dotted = batch repair.

## Frontend

Vite + React + react-router. No component library.

**Role pages**, not a single dashboard. Each persona in the article gets a route:

- Writer / user / client — *causes* the write path
- Reader / analyst / advertiser — *observes* the query path
- Landing / 302 target — when the lesson is a redirect

Every role page starts with a **What to try** `<ol>`. Buttons must cause the design (place, click, mint, expire, simulate miss, reconcile). Show the interesting ids (impression, sig, partition key) on the card so the user can paste them into a viewer.

Link `<a href="/walkthrough.html">Walkthrough</a>` in the nav.

## Visual language

Reuse these tokens in both `frontend/src/styles.css` and `walkthrough.html`:

```css
:root {
  --ink: #1c1917;
  --muted: #57534e;
  --paper: #f6f1e8;
  --card: #fffaf2;
  --line: #e7ddd0;
  --accent: #b45309;
  --accent-ink: #fff7ed;
  --ok: #3f6212;
}
body {
  font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  background: radial-gradient(circle at top left, #fff7ed, var(--paper) 45%);
}
```

Eyebrow: uppercase, 0.12em letter-spacing, sans, accent color. Nav chips: pill, 999px radius. Code in walkthrough: dark `#1c1917` / `#fef3c7`, file paths `#fdba74`.

## Code style

- FastAPI apps listen on `8000`. Jobs are `python main.py` unless they also expose a trigger (reconciler).
- Module docstring = the lesson (order of operations, what this box is a stand-in for).
- `print(f"[service] …")` on every interesting event.
- Seed the *hard case* in `infra/*/init.sql`, not in a comment.
- Shared settings from env (`shared/settings.py`). YAML anchor in compose matches those names.
- Comments only when they restate a lesson note (`# Write the stream first, then the dedupe key.`).

## README skeleton

```markdown
# <Name> Lab

Local, readable version of <article>. One process per box.

    docker compose up --build

Then http://localhost:8090 and http://localhost:8090/walkthrough.html

| Viewer | URL |
| Walkthrough / Lab UI | :8090 |
| …only stores you actually run… | |

## What to do in the UI
## Why each box exists   (table: piece, problem, file)
## Request path          (ASCII)
## Lesson notes that show up in code
## Layout
```

## Verification

```bash
docker compose config
docker compose up --build
# then
curl -sS -o /dev/null -w "%{http_code}" http://localhost:8090/
curl -sS -o /dev/null -w "%{http_code}" http://localhost:8090/walkthrough.html
```

Walk Lab 0 in the browser: UI action → viewer → named file.
