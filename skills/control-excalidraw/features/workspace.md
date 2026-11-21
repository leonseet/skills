# Workspace

The workspace is the account container: its members, pending invites and audit log. These commands need an admin's key. Only the reads are mapped here. Changing members or invites (`workspace update`, `workspace users update|remove`, `workspace invites create|create-link|update|delete`) is unproven: read the command's `--help`, treat a remove or revoke as destructive, and remember that `invites create` sends an email.

Commands: `excalidraw whoami`, `excalidraw workspace get`, `excalidraw workspace users list`, `excalidraw workspace invites list`, `excalidraw logs list`.

## Operations

- `whoami` (read): which key, key type and workspace the CLI is using.
- `workspace` (read): the workspace's name, plan state and roles.
- `members` (read): users with access.
- `invites` (read): pending invites.
- `audit logs` (read): who did what, filtered.

## Finding things

- A user id (`U`, for `--user`): `members`.
- An action name (`ACTION`, for `--action`): the `availableActions` list every `logs list` response carries, e.g. `scene`, `collection`, `scene:link-sharing`, `workspace:invite`. Other values are ignored without an error.
- `SINCE`: an ISO 8601 date, e.g. `2026-11-01`.

## Recipes with excalidraw

### whoami

```bash
excalidraw whoami | jq '{keyType, credentialSource, workspace: .workspace.name, id: .workspace.id}'
```

Returns `{keyType: "personal"|"workspace", credentialSource: "login"|"env"|"flag", workspace, id}`.

### workspace

```bash
excalidraw workspace get | jq '{id, name, subscriptionStatus, created, roles, users: (.users | length), invites: (.invites | length)}'
```

`roles` maps user id to `admin` or `member`.

### members

```bash
excalidraw workspace users list --limit 50 | jq '{hasNextPage, users: [.data[] | {id, name, email, role, lastActive}]}'
```

Returns `{hasNextPage, users: [{id, name, email, role, lastActive}]}`.

### invites

```bash
excalidraw workspace invites list --limit 50 | jq '{hasNextPage, invites: .data}'
```

Returns `{hasNextPage, invites: [...]}`; the list is empty when nothing is pending.

### audit logs

```bash
excalidraw logs list --limit 20 --date-from "$SINCE" \
  | jq '{totalCount, nextCursor, logs: [.logs[] | {at: .created_at, action, operation, status, by: .user_full_name, via: .source_type, details}]}'
```

Returns `{totalCount, nextCursor, logs: [{at, action, operation, status, by, via, details}]}`, newest first. Narrow with `--action "$ACTION"`, `--operation create|read|update|delete`, `--user "$U"`, `--date-to`. Next page: `--cursor <nextCursor>`.

## Gotchas

- `logs list` pages by cursor and returns `{logs, nextCursor, hasMore, totalCount, availableActions}`, unlike every other listing's `{data, hasNextPage}`.
- Each raw log row carries the caller's IP address and picture URL; the projection drops them. Keep it.
- A member's personal key gets `HTTP 403` on everything here except `whoami`.
