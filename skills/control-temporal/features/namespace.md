# Namespace and cluster

A namespace is Temporal's unit of isolation: workflow ids, task queues, retention and search attributes are all per namespace. A server starts with `default` and the internal `temporal-system`. This file covers the facts the other recipes depend on: versions, retention, and which search attributes a `--query` can filter on.

Commands: `temporal.py info`, `search-attributes`; API `/api/v1/cluster-info`, `/api/v1/settings`, `/api/v1/namespaces`, `/api/v1/namespaces/:ns`, `/api/v1/namespaces/:ns/search-attributes`.

## Operations

- `info` (read): server and UI versions, namespaces, the current namespace's retention and state.
- `search attributes` (read): the attributes usable in a visibility query, with their types.

## Finding things

- The namespace is `TEMPORAL_NAMESPACE` from the current repo's `.env`, else `default`; `-n <name>` before the command overrides it. `info` lists the ones that exist.

## Recipes with temporal.py

### info (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py info
```

Returns `{ui, uiVersion, server, persistence, namespaces, namespace, retention, state}`, e.g. `server: "1.32.0"`, `retention: "259200s"` (72 h), `state: "REGISTERED"`, plus `taskQueue`, the `TEMPORAL_TASK_QUEUE` setting or `null`. `--local info` shows the local docker server.

### search attributes (read)

```bash
uv run ~/.agents/skills/control-temporal/scripts/temporal.py search-attributes --system \
  | jq -c '{custom, system: (.system | keys)}'
```

Returns `{custom: {name: type}, system?: {name: type}}`; types are `KEYWORD`, `TEXT`, `INT`, `DATETIME`, `BOOL`, `DOUBLE`, `KEYWORD_LIST`. Without custom attributes, filters use the system ones: `WorkflowType`, `WorkflowId`, `ExecutionStatus`, `TaskQueue`, `StartTime`, `CloseTime`, `ExecutionDuration`, `HistoryLength`.

## Gotchas

- Changing retention, adding search attributes or creating namespaces is server administration, owned by whoever runs the server; this script has no command for it.
- `KEYWORD` attributes match exactly (`=`, `IN`, `STARTS_WITH`); `TEXT` matches words. Times compare as RFC 3339 strings in quotes.
