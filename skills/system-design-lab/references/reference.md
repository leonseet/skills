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

Gateway nginx: resolve Docker DNS (`resolver 127.0.0.11`), proxy each API prefix to one upstream, `try_files` the SPA, exact location for `/walkthrough.html`. Add CORS on the server so walkthrough peek works from `file://` and editor previews (same-origin `:8090` does not need it, but the HTML is often opened as a file):

```
add_header Access-Control-Allow-Origin * always;
add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
add_header Access-Control-Allow-Headers "Content-Type, X-User-Id" always;
```

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

1. **How to use** — keep this tab open; do the lab in the UI; open the viewer. One sentence: a **Code** path opens that file in Cursor.
2. **TOC** — `#architecture`, `#map`, `#viewers`, `#lab0` … `#labN`
3. **System architecture** — one SVG; every box is a link to its lab (or `/` / `/analyst`). Legend for client / service / store / job and for sync / stream / batch edges
4. **Live peek** (optional) — if present, follow [Live peek](#live-peek-if-the-section-exists). Do not ship a one-shot relative `fetch`
5. **What each box is for** — SVG request-path lanes (same boxes as architecture). Not ASCII
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
  <p><strong>Code:</strong> <a class="file" title="Open in Cursor" href="cursor://file/ABS/path/to/file.py:21">path/to/file.py</a> <a class="goto" title="Open in Cursor" href="cursor://file/ABS/path/to/file.py:21"><code>symbol</code></a></p>
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

`ABS` is the lab directory’s absolute path. See [Code links](#code-links-open-in-cursor).

### Code links (open in Cursor)

Every **Code** line is a clickable deep link. The file path opens that file. A symbol next to it opens the same file on the line where that function is defined. Leave other `<code>` chips alone (API paths, SQL, Redis keys, docker commands).

Resolve the lab directory to an absolute path. The href is `cursor://file` plus that absolute path plus `:` plus the 1-based line:

`cursor://file/Users/…/lab/services/chat/main.py:314`

The absolute path already starts with `/`, so do not add another slash after `file`. Encode each path segment and keep the slashes. Use the line of the `def` (or line 1 when the reference has no symbol). When one file is listed with several symbols, the path opens at the first symbol and each symbol is its own link.

`#fdba74` is for file paths inside a dark `<pre>`. On the cream card, links use the accent color and an underline so they read as clickable:

```css
a.file {
  color: var(--accent);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.92em;
  text-decoration: underline;
  text-underline-offset: 3px;
}
a.file:hover { color: var(--ink); }
a.goto { color: inherit; text-decoration: none; }
a.goto code { color: var(--accent); text-decoration: underline; text-underline-offset: 2px; }
a.goto:hover code { color: var(--ink); }
```

The first click may ask the browser to allow opening Cursor.

### Drawing the architecture SVG

Orthogonal connectors only. A stroke is a horizontal run, then a vertical run. Do not draw a diagonal, and do not end a stroke in empty space.

- Every box has an edge. A second copy of a box (another worker, another store) is stacked and gets its own short edge so the two edges do not cross.
- A return path (SSE, the response) travels in the margin outside the boxes, back to the client. It does not leave a box and stop beside it.
- Writes from a service drop to a horizontal bus, then down into each store.
- Edge labels sit in the gutter between boxes. They do not sit inside a box, and they do not clip the viewBox. Keep about 16px of padding inside the viewBox; a label whose baseline is near `y=0` is cut off.
- The paragraph under the diagram names each stroke (solid sync HTTP, dashed stream, accent dashed return). The swatch row matches those strokes.
- The same rules apply to each lab’s mini SVG and to `#map`.
- The walkthrough file is volume-mounted, and browsers cache it. After an SVG edit, reload with `?v=` and confirm the new strokes are the ones on screen.

### Live peek (if the section exists)

Must work from `http://localhost:8090/walkthrough.html` **and** from `file://` / editor HTML previews. A relative `fetch("/ads")` only hits the gateway when the page is already served from `:8090`.

UI:

- `#refresh-peek` button and `#peek-status` (Loading / Updated / error)
- Two compact `<pre>` panes (`max-height` ~280px). Print ids, prices, counts — not full catalog rows
- Copy: these calls hit nginx on `localhost:8090`

JS — copy this shape, swap the article’s routes:

```javascript
const GATEWAY = "http://localhost:8090";

function peekUrls(path) {
  const urls = [];
  if (window.location.protocol === "http:" || window.location.protocol === "https:") {
    urls.push(new URL(path, window.location.origin).href);
  }
  const viaGateway = GATEWAY + path;
  if (!urls.includes(viaGateway)) urls.push(viaGateway);
  return urls;
}

async function fetchJson(path) {
  let lastErr;
  for (const url of peekUrls(path)) {
    try {
      const res = await fetch(url);
      if (!res.ok) {
        lastErr = new Error(`${res.status} ${res.statusText} from ${url}`);
        continue;
      }
      return await res.json();
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr;
}

async function peek() {
  const status = document.getElementById("peek-status");
  status.textContent = "Loading…";
  try {
    const [a, b] = await Promise.all([
      fetchJson("/LIST_ROUTE"),
      fetchJson("/HEALTH_OR_WHOAMI"),
    ]);
    document.getElementById("peek-a").textContent = JSON.stringify(compact(a), null, 2);
    document.getElementById("peek-b").textContent = JSON.stringify(compact(b), null, 2);
    status.textContent = "Updated " + new Date().toLocaleTimeString();
  } catch (err) {
    status.textContent = `${err} — is docker compose up? Try ${GATEWAY}/walkthrough.html`;
  }
}

document.getElementById("refresh-peek").addEventListener("click", peek);
peek();
setInterval(peek, 5000);
```

### What each box is for (`#map`)

This is the request-path diagram. It is not a second `#architecture` and it is not ASCII.

- Same SVG box language as System Architecture: colors below, `class="box"`, hover stroke, clickable `<a href="#labN">` or role routes
- One labeled lane per path the user actually takes (list, write, watch, query, repair, …)
- Lane title + one-line why (`LIST — ordinary CRUD`, `BID — Kafka first, then OCC`)
- Solid = sync HTTP, dashed = stream / pubsub, dotted = batch. Reuse the architecture swatches
- **Forbidden:** `<pre class="flow">` or a dark monospace ASCII dump as the map

README may keep a short ASCII path. The walkthrough must not.

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

Eyebrow: uppercase, 0.12em letter-spacing, sans, accent color. Nav chips: pill, 999px radius. Code in a dark `<pre>`: `#1c1917` / `#fef3c7`, file paths `#fdba74`. **Code** links on the cream card use `--accent` and an underline — see [Code links](#code-links-open-in-cursor).

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
## Request path          (short table; walkthrough #map is SVG)
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

If Live peek exists: `curl` those routes on `:8090` (JSON), then open `/walkthrough.html` and confirm `#peek-status` becomes `Updated …`. `#map` must contain an `<svg>` with clickable boxes — fail the lab if the map is only a `<pre>`.

Architecture SVG: every stroke meets a box, edges do not cross, and no label is clipped by the viewBox. Reload with `?v=` if the browser still shows the previous diagram.

Each **Code** line is an `<a class="file" href="cursor://file/…:LINE">`, and each named symbol is an `<a class="goto">` to that function’s line.
