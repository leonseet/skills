# Databases

A database is a container whose rows are pages. Since API version `2025-09-03`, its schema and rows belong to a **data source** inside it, and a database can hold several data sources. Rows are read, queried and created against the data source id (`DS`), not the database id (`DB`). This workspace's databases each hold one data source. Row bodies are page bodies: edit them through [pages](./pages.md).

Commands: `ntn api v1/search`, `ntn datasources query|resolve`, `ntn api v1/data_sources/{id}`, `ntn api v1/databases`, `ntn api v1/pages` (rows).

## Operations

- `find` (read): data sources by name.
- `schema` (read): a data source's properties, their types and options.
- `query` (read): rows, filtered and sorted.
- `add row` (write): a new row with properties and an optional markdown body.
- `update row` (write): change a row's properties.
- `add property` (write): a new column.
- `create database` (write): a new database inline on a page.
- `trash row` (destructive): [pages](./pages.md) `trash` on the row.
- `drop property` (destructive): remove a column and its values in every row.

## Finding things

- `DS` by name: `find`. From a database id or a database URL: `ntn datasources resolve "$DB" --json </dev/null | jq -r '.data_sources[0].id'`. Inline databases show up in [blocks](./blocks.md) listings as `child_database`, whose block id is `DB`.
- The workspace's fixed ones: the workspace map (SKILL.md).
- `R` (a row): from `query`, or [pages](./pages.md) `find by title`.
- Property names and option values: from `schema`. Names are case-sensitive and may hold spaces (`Project name`).

## Recipes with ntn

### find (read)

```bash
ntn api v1/search -d "$(jq -n --arg q "$Q" '{query: $q, filter: {property: "object", value: "data_source"}, page_size: 20}')" </dev/null \
  | jq $NJQ 'include "notion"; [.results[] | {ds: .id, db: .parent.database_id, name: title, columns: (.properties | keys)}]'
```

Leave `Q` empty to list every data source. The workspace holds about 26, personal ones included.

### schema (read)

```bash
ntn api v1/data_sources/"$DS" </dev/null \
  | jq $NJQ 'include "notion"; {name: title, db: .parent.database_id, props: (.properties | map_values({type} + (if .type == "select" or .type == "status" or .type == "multi_select" then {options: [.[.type].options[].name]} else {} end)))}'
```

Returns `{name, db, props: {<name>: {type, options?}}}`.

### query (read)

```bash
ntn datasources query "$DS" --limit 20 -s 'Date desc' --filter "$(cat <<'EOF'
{"property": "Status", "select": {"equals": "done"}}
EOF
)" --json </dev/null | jq $NJQ 'include "notion"; [.results[] | {id, props: props}], {has_more, next_cursor}'
```

Returns `[{id, props: {<name>: <plain value>}}]`, then `{has_more, next_cursor}`. Drop `--filter` to get every row, and drop `-s` for the default order; repeat `-s` for more sort keys. The filter is Notion's JSON: `{"and": [...]}` and `{"or": [...]}` combine conditions, and each condition is `{"property": <name>, <type>: {<op>: <value>}}`. Examples: `"date": {"on_or_after": "2026-11-01"}`, `"rich_text": {"contains": "x"}`, `"checkbox": {"equals": true}`. Continue with `--start-cursor "$CURSOR"`. For a quick look, `--plain` prints one row per line with no header, columns in alphabetical property order.

### add row (write)

```bash
ntn api v1/pages -d "$(jq -n --arg ds "$DS" --arg title "$TITLE" --arg md "$(cat <<'EOF'
Optional row body in **markdown**.
EOF
)" '{parent: {type: "data_source_id", data_source_id: $ds},
     properties: {Name: {title: [{text: {content: $title}}]}, Status: {select: {name: "todo"}}, Score: {number: 0.5}, Date: {date: {start: "2026-11-11"}}},
     markdown: $md}')" </dev/null | jq '{id, url}'
```

Name each property as `schema` spells it, with a value shaped for its type: `rich_text: [{text: {content: …}}]`, `multi_select: [{name: …}]`, `checkbox: true`, `people: [{id: …}]`, `relation: [{id: …}]`, `url: "…"`. Drop `markdown` for an empty body. Read-back: `ntn pages get <id> </dev/null` prints the properties as frontmatter, then the body.

### update row (write)

```bash
ntn api v1/pages/"$R" -X PATCH -d "$(cat <<'EOF'
{"properties": {"Status": {"select": {"name": "done"}}, "Score": {"number": 0.9}}}
EOF
)" </dev/null | jq $NJQ 'include "notion"; {id, props: props}'
```

Only the properties sent change. Read-back: the returned `props` show the new values.

### add property (write)

```bash
ntn api v1/data_sources/"$DS" -X PATCH -d "$(cat <<'EOF'
{"properties": {"Notes": {"rich_text": {}}}}
EOF
)" </dev/null | jq '.properties | map_values(.type)'
```

A select column is `{"select": {"options": [{"name": "a"}, {"name": "b"}]}}`. To rename a column, send `{"<old name>": {"name": "<new name>"}}`. Read-back: the column appears with its type in the output.

### create database (write)

```bash
ntn api v1/databases -X POST -d "$(jq -n --arg p "$PARENT" --arg t "$TITLE" '{parent: {type: "page_id", page_id: $p}, is_inline: true, title: [{text: {content: $t}}],
  initial_data_source: {properties: {Name: {title: {}}, Status: {select: {options: [{name: "todo"}, {name: "done"}]}}, Date: {date: {}}}}}')" </dev/null \
  | jq '{db: .id, ds: .data_sources[0].id, url}'
```

The database must have exactly one `title` property. Read-back: `schema` on the returned `ds`.

### drop property (destructive)

Preview: `query` with the column's values for the rows that hold one. Tell the user the column and how many rows lose a value. Only after their explicit yes:

```bash
ntn api v1/data_sources/"$DS" -X PATCH -d "$(jq -n --arg col "$COL" '{properties: {($col): null}}')" </dev/null | jq '.properties | keys'
```

`COL` is the column name. Read-back: it is gone from the returned keys.

## Gotchas

- Writing a select value that is not yet an option silently adds the option, so a typo creates a new one. Check `schema` first. `status` options cannot be added through the API at all.
- The title column has a different name in every database (`Name`, `Project name`, `Title`). `include "notion"; title` finds it, and the property key `title` addresses it in writes.
- `ntn datasources query` returns 25 rows unless told otherwise. Always pass `--limit`.
- `ntn datasources query` accepts a database id or URL only when the database has a single data source. With several, `resolve` lists them.
