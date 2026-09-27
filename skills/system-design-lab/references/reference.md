# Reference

## Stand-ins (include a row only if the article has that box)

| Article says | Local | Viewer |
| --- | --- | --- |
| Kinesis / PubSub / EventBridge | Kafka `apache/kafka:3.8.1` KRaft (7-day retention if replay matters) | Kafka UI `provectuslabs/kafka-ui:v0.7.2` :8091 |
| S3 / GCS / Firehose | MinIO `quay.io/minio/minio:RELEASE.2024-11-07T00-52-20Z` | console :9001 (`minio` / `minio12345`) |
| CloudFront / CDN | `nginx:1.27-alpine` (`secure_link` + `proxy_cache`) | `X-Cache-Status` header + logs |
| Dynamo / ElastiCache / cache | `redis:7-alpine` | Redis Commander `rediscommander/redis-commander:latest` :8092 |
| RDS / "the DB" | `postgres:16-alpine` | Adminer `adminer:4` :8093 |
| Redshift / Druid / OLAP | `clickhouse/clickhouse-server:24.8` (`olap` / `olap`) | Play :8123/play |
| Flink / Spark Streaming | Flink SQL, or a small Python consumer if a cluster teaches nothing | :8081 |
| Spark / EMR / Lambda / worker | Python in `jobs/<name>/main.py` (HTTP trigger if a button needs it) | logs + lab button |
| ALB / API Gateway | `nginx:1.27-alpine` in `gateway/` + built UI | Lab UI **:8090** (never 8080) |
| CloudWatch | `print` + `docker compose logs -f` | — |

Services use `python:3.12-slim`; the frontend build stage uses `node:22-alpine`. Kafka listens on host 9092 and in Docker on `kafka:9093`.

## Layout + compose

```
README.md  docker-compose.yml  walkthrough.html
gateway/   nginx + built UI          frontend/  Vite + React + react-router
services/  FastAPI, one dir per box  jobs/      workers (only if needed)
infra/     seed SQL, bucket/topic init   tools/code_links.py
```

- One service per box. Shared env comes from a YAML anchor (`x-python-env`) whose names match `settings.py`.
- Stores have healthchecks. Apps use `depends_on: condition: service_healthy`. One-shot init containers (`minio-init`, `kafka-init`) set up buckets and topics.
- Use generic Dockerfiles with `ARG SERVICE`. Viewers `depends_on` their store.
- Gateway: `8090:80`, and mount `./walkthrough.html:/usr/share/nginx/html/walkthrough.html:ro`.
- If `/lab/reset` must clear a cache that another container owns, share a named volume.

Gateway `nginx.conf`:

```nginx
resolver 127.0.0.11 ipv6=off valid=10s;           # start even if upstreams are still booting
add_header Access-Control-Allow-Origin * always;   # walkthrough opened as file://
add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
add_header Access-Control-Allow-Headers "Content-Type, X-User-Id" always;
if ($request_method = OPTIONS) { return 204; }     # preflight answered here, not by FastAPI
location ~ ^/(files|users|lab)(/|$) { set $up svc:8000; proxy_pass http://$up; }   # the article's API prefixes
location = /walkthrough.html { try_files /walkthrough.html =404; }
location / { try_files $uri $uri/ /index.html; }
```

## SVG (architecture, `#map`, each lab's mini diagram)

- Orthogonal strokes only: horizontal, then vertical. Every stroke starts and ends on a box, and no two cross. A second copy of a box is stacked and gets its own edge.
- Return paths (responses, SSE, push) run in the margin back to the client. Writes drop to a horizontal bus, then into each store.
- Labels go in the gutters, with about 16px of padding inside the viewBox. Wide SVGs sit in `overflow-x: auto`.
- Box colors (fill / stroke):
  - client: `#fff7ed` / `#b45309`
  - gateway: `#b45309` fill with `#fff7ed` text
  - service: `#fffaf2` / `#1c1917`
  - store: `#ecfccb` / `#3f6212`
  - job: `#ffedd5` / `#9a3412`
- Edges: solid = sync HTTP, dashed = stream or push, dotted = batch or origin fetch. A swatch row names each one.

## Frontend

Vite + React + react-router, no component library, `:root` tokens from `assets/walkthrough.css`. Give each persona a route. Each page starts with a **What to try** `<ol>` and shows the ids a user would paste into a viewer. The nav links to `/walkthrough.html`.

## README

```markdown
# <Name> Lab
Local, readable version of <article>. One process per box.
    docker compose up --build
Then http://localhost:8090 and http://localhost:8090/walkthrough.html
| Viewer | URL | Login |        (only the stores you run)
Reset: walkthrough "Reset lab data" or `curl -X POST localhost:8090/lab/reset`. From scratch: `docker compose down -v`.
## What to do in the UI
## Why each box exists     (piece, problem, file)
## Request path            (short table; the walkthrough #map is SVG)
## Lesson notes that show up in code
## Layout
```
