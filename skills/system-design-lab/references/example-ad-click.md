# Example: "Scaling Writes" (ad-click aggregator)

Use this for write-path, streaming or lambda articles only. Copy the method, not the domain.

**Problem:** 10k clicks/s must not share a DB with advertiser `GROUP BY`s. Record each click cheaply, pre-aggregate on the write path, and query a small OLAP table.

| Box | Local | Lesson in code |
| --- | --- | --- |
| API gateway | `gateway` :8090 → `/ads` `/click` `/analytics` | |
| Ad Placement | `services/ad_placement` | mints an `impression_id` and signs it with HMAC (`shared/hmac_util.py`) |
| Click Processor | `services/click_processor` | verify → dedupe on Redis `clicked:` → **Kafka first** → cache → 302 |
| Kinesis | Kafka `ad-clicks`, 6 partitions, 7-day retention | replay; hot key `ad_id:N` (seed `nike-lebron`, 4 shards) |
| Flink | `jobs/flink/clicks.sql` | `COUNT(*)` per `(ad_id, minute)` |
| OLAP | ClickHouse `click_counts` `ReplacingMergeTree` | a `source` column: `flink` / `reconciler` / `simulated-miss` |
| Firehose → S3 | `jobs/archiver` → MinIO `raw-clicks` | raw lake |
| Spark | `jobs/reconciler` | re-aggregate the lake and overwrite OLAP (lambda) |
| Analytics API | `services/analytics` | `/metrics`, `/reconcile`, `/simulate-miss` |

**Roles:**
- `/` user: place an impression, click (302)
- `/advertiser/:id`: the 302 landing page; its back button replays a click (Lab 3)
- `/analyst`: live chart, plus simulate miss and reconcile

**Labs** (each lab: concept → viewer):
- Lab 0: catalog → Adminer
- Lab 1: HMAC → Redis `issued:`
- Lab 2: Kafka first → Kafka UI
- Lab 3: idempotency → log `skip Kafka`
- Lab 4: hot shards → Kafka keys
- Lab 5: speed layer → Flink :8081
- Lab 6: query path → ClickHouse Play
- Lab 7: raw lake → MinIO
- Lab 8: simulate a miss → reconcile flips `source`

**Method for a new article:**
1. State the problem in one sentence.
2. Map each box to a process and a file.
3. Map each lesson to the file it will live in.
4. Pick the seed row that makes the hard case visible.
5. Define role pages and the buttons that cause each lesson.
6. Write one lab per lesson, each with a viewer.
7. Add only the viewers those stores need.
