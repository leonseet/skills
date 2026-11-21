# Search

Search ranks a collection's entities against a query: dense similarity on a vector field, BM25 keyword relevance on the sparse `bm25_vector`, or both fused. This skill has no embedding model, so the dense query is always the vector of an entity already stored (`similar`); free-text semantic search belongs to the app that owns the embedding model. Use it to check retrieval quality, find near-duplicates, or trace why a chunk does or does not come back.

Commands: `milvus.py similar`, `bm25`, `hybrid`.

## Operations

- `similar` (read): nearest neighbours of a stored entity's vector.
- `bm25` (read): keyword search on a collection with a BM25 function.
- `hybrid` (read): `similar` + `bm25` fused with reciprocal rank fusion.

## Finding things

- `ID`: the primary key of the anchor entity, from [entities](./entities.md) `query`.
- `TEXT`: keywords. BM25 tokenizes them with the field's analyzer (`standard` by default, `icu` in docres v3+).
- `F`: an optional pre-filter over scalar fields, same syntax as [entities](./entities.md). Scope to one app or document with `app_id`/`scope`/`doc_id`.
- Which collections support `bm25`/`hybrid`: [collections](./collections.md) `list` shows a `"sparse"` vector field.
- `--fields` in the recipes names RAG chunk fields. Docres v3+ uses `file_id,title,content`; ReID uses `camera_id,location,video_id,start_wall_clock`; [collections](./collections.md) `show` lists any collection's fields.

## Recipes with milvus.py

### similar (read)

```bash
uv run -q "$M" similar --db "$DB" --col "$COL" --id "$ID" --filter "$F" --limit 5 --fields doc_id,doc_title,chunk_type,text | jq -c '.[]'
```

One hit per line: `{<pk>, "distance", ...fields}`, best first. The anchor itself is the first hit at distance `1` (COSINE: higher is closer). `--field` picks a vector field when there are several; default is the first dense one.

### bm25 (read)

```bash
uv run -q "$M" bm25 --db "$DB" --col "$COL" --text "$TEXT" --filter "$F" --limit 5 --fields doc_title,text | jq -c '.[]'
```

Same shape; `distance` is the BM25 score (unbounded, higher is better). No lines means no token matched. On a collection without a BM25 function it prints `collection has no BM25 function` and exits 1.

### hybrid (read)

```bash
uv run -q "$M" hybrid --db "$DB" --col "$COL" --id "$ID" --text "$TEXT" --filter "$F" --limit 5 --fields doc_title,text | jq -c '.[]'
```

Same shape; `distance` is the RRF score, `1/(k+rank)` summed over the two halves: with `--k 60`, ~0.016 for a hit only one half ranks first, ~0.033 when both do. Compare against `similar` and `bm25` alone to see which half brought a hit in.

## Gotchas

- Distances are only comparable within one metric: COSINE (`similar`, the RAG and ReID indexes) is 0–1 higher-better, BM25 is unbounded, RRF is tiny. Never threshold across them.
- Most RAG `vector` indexes here are `FLAT` (exact); ReID uses `HNSW` (approximate), so near-ties can swap between runs.
- An empty `--filter` searches every app's rows in a shared collection; scope with `app_id` when checking one app's retrieval.
