# Example: Hello Interview “Scaling Writes” → this lab

Read this only when the article is a **write-path / streaming / lambda** design. Do not clone the ad-click domain for unrelated articles. Use it to see how boxes, stand-ins, seed data, labs, and viewers line up.

Source repo: the `ad_click_aggregator` lab.

## Article problem

10k clicks/s must not share a database with advertiser `GROUP BY` queries. Record every click cheaply, pre-aggregate on the write path, query a small OLAP table.

## Cloud names → local boxes

| Lesson | Local process | Why |
| --- | --- | --- |
| ALB / API gateway | `gateway` nginx `:8090` | One entry; fan-out `/ads` `/click` `/analytics` |
| Ad DB | Postgres `ads` table | Catalog only; targeting out of scope |
| Ad Placement | `services/ad_placement` | Mint `impression_id`, HMAC, Redis `issued:` |
| Cache | Redis | Dedupe **before** the stream |
| Click Processor | `services/click_processor` | Verify → dedupe → **Kafka first** → cache → 302 |
| Kinesis | Kafka `ad-clicks` (6 partitions, 7-day retention) | Absorb spikes; replay |
| Flink / Kinesis Analytics | Flink SQL `jobs/flink/clicks.sql` | `COUNT(*)` per `(ad_id, minute)`, ~2s flush |
| ClickHouse sink connector | `jobs/olap_writer` | JDBC has no ClickHouse upsert dialect |
| OLAP | ClickHouse `click_counts` | Advertisers query this, never raw events |
| Analytics API | `services/analytics` | `GET /metrics`, `POST /reconcile`, `POST /simulate-miss` |
| Firehose / Connect S3 | `jobs/archiver` → MinIO `raw-clicks` | Raw lake |
| Spark / MapReduce | `jobs/reconciler` | Re-aggregate lake; overwrite OLAP |

Kafka is the Kinesis stand-in. The reconciler is the Spark stand-in. Same jobs, less cluster ceremony.

## Lesson notes that show up in code

These are the reason the lab exists. Each one is a docstring, a comment, or seed data — not a README-only claim.

| Lesson | Where it lives |
| --- | --- |
| `<a href>` is `/click`, never the advertiser URL | `ad_placement` builds `click_url`; `AdvertiserPage` explains the 302 |
| HMAC stops forged IDs and ad-id swaps | `shared/hmac_util.py` |
| Write stream before cache | `click_processor`: produce, then `SET clicked:` |
| Dedupe before Kafka so a retry cannot split minute windows | `clicked:` check returns 302 without produce |
| Celebrity / hot shard: key `ad_id:N`, payload `ad_id` stays clean | `kafka_key_for`; seed `nike-lebron` `celebrity_shards=4` |
| Checkpoints vs 7-day replay | Flink SQL comments; Kafka `KAFKA_LOG_RETENTION_HOURS: 168` |
| Lambda: speed layer vs batch; raw objects win | Flink + olap-writer vs archiver + reconciler; `source` column |
| Simulate a miss so reconcile is visible | `POST /analytics/simulate-miss` + Analyst buttons |

## Seed the hard case

`infra/postgres/init.sql` is not three generic ads. `nike-lebron` is `is_celebrity` with 4 shards so Lab 4 has something to look at. `bean-there` is the control (plain `ad_id` key).

OLAP: `click_counts` is `ReplacingMergeTree(updated_at)` so Flink upserts and reconciler overwrites are the same insert path. `source` is `flink` | `reconciler` | `simulated-miss`.

## Frontend roles

| Route | Persona | Causes |
| --- | --- | --- |
| `/` User | End user | Place impression, click (302), new impression (retargeting) |
| `/advertiser/:adId` | Advertiser landing | Proves the 302; back-button retry for Lab 3 |
| `/analyst` | Advertiser analyst | Polls ClickHouse every 3s; simulate miss; reconcile |

User cards print `impression_id`, HMAC prefix, and “href is `/click` not nike.com” so Labs 1–4 do not need DevTools.

## Labs (the sessions)

| Lab | Concept | Do this | Viewer |
| --- | --- | --- | --- |
| 0 | Catalog | Open `ads` table | Adminer `:8093` |
| 1 | Place + HMAC | New impression; copy id | Redis Commander `issued:` |
| 2 | Click + Kafka first + 302 | Visit advertiser | Kafka UI `ad-clicks` + processor logs + Redis `clicked:` |
| 3 | Idempotency | Back + same click | Processor log `skip Kafka`; Kafka count unchanged |
| 4 | Hot shards | Several Nike clicks | Kafka keys `nike-lebron:0..3`; Analyst still one series |
| 5 | Speed layer | Open job graph | Flink `:8081` + Kafka `ad-clicks-aggregated` + olap-writer logs |
| 6 | Query path | Analyst chart | ClickHouse Play `click_counts FINAL` |
| 7 | Raw lake | After a click | MinIO `raw-clicks/dt=…/ad=…` |
| 8 | Lambda batch | Simulate miss → Reconcile | Chart `source` flips; MinIO still has JSON |

Each lab has a mini SVG of that hop only, **Code** file names, **Do this**, and a CLI fallback.

## Viewers this article earned

Built-in: Lab UI `:8090`, Flink `:8081`, ClickHouse Play `:8123`, MinIO `:9001`.
Companion: Kafka UI `:8091`, Redis Commander `:8092`, Adminer `:8093`.
CLI: processor / archiver / olap-writer / reconciler logs.

No extra stores. No CloudWatch clone.

## Request path (what README + walkthrough both print)

```
User click
  → GET /click?ad_id&impression_id&sig
  → HMAC check
  → Redis clicked:{id}?  yes → 302, no Kafka
  → Kafka topic ad-clicks  (key = ad_id or ad_id:N)
  → Redis SET clicked:{id}
  → 302 /advertiser/{ad_id}

ad-clicks ─┬→ Flink → ad-clicks-aggregated → olap-writer → ClickHouse
           └→ archiver → MinIO → reconciler (cron or button) → ClickHouse
```

## How to reuse the *method*

When generating a new lab, fill this same table for the new article:

1. Problem in one sentence
2. Each article box → local process + file
3. Lesson notes → exact file they will live in
4. Seed row that makes the hard case visible
5. Role pages and the buttons that cause each lesson
6. One lab per lesson, each with a viewer
7. Only the viewers those stores need
