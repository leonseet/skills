# Tickets

A ticket is a unit of work in one queue. Every team has queues named `<team>-<area>`; a ticket's number is unique per queue, not globally, so a ticket is always addressed as `<queue>#<n>`.

Commands: `tix ticket`, `tix api /queues/:queue/tickets`.

## Operations

- `find by title` (read): tickets in a queue whose title matches.
- `show` (read): one ticket's fields and its last comments.
- `create` (write): a new ticket in a queue.
- `close` (write): close with a resolution.
- `delete` (destructive): remove a ticket and its history.

## Finding things

- **Queue**: from the team and area (`res-reid`). `tix queue list -o json | jq -r '.[].name'` lists the ones the caller can see.
- `Q` and `N`: the queue and ticket number (`res-reid`, `142`). `N` from a title: `find by title` below.
- **User handle** (for `--assignee` filters): `tix user find "<name>" -o json | jq -r '.[0].handle'`. Display names are not accepted.

## Recipes with tix

### find by title

```bash
tix ticket list --queue "$Q" --search "$TEXT" --limit 10 -o json \
  | jq '[.[] | {n: .number, title, state, assignee: .assignee.handle}]'
```

Returns `[{n, title, state, assignee}]`. `--search` matches title only; an empty array means no match, not an error.

### show

```bash
tix ticket view "$Q#$N" -o json \
  | jq '{n: .number, title, state, labels, assignee: .assignee.handle, body: (.body[:500]), last_comments: [.comments[-3:][] | {by: .author.handle, at: .created_at, text: (.body[:300])}]}'
```

Body and comments are truncated to keep the output small. Fetch the full body only when the task needs it: `tix ticket view "$Q#$N" -o json | jq -r .body > /tmp/ticket.md`.

### create

```bash
tix ticket create --queue "$Q" --title "$TITLE" --body "$BODY" -o json \
  | jq '{n: .number, url: .web_url}'
```

Read-back: `show` on the returned number; `title` and `state: "open"` match.

### close

```bash
tix ticket close "$Q#$N" --resolution fixed
```

Prints nothing on success. Read-back: `tix ticket view "$Q#$N" -o json | jq '{state, resolution}'` returns `{"state":"closed","resolution":"fixed"}`.

### delete

Destructive. Preview first and show it to the user: `tix ticket view "$Q#$N" -o json | jq '{n: .number, title, comments: (.comments | length)}'`. Only after their explicit yes:

```bash
tix ticket delete "$Q#$N" --yes
```

Read-back: `tix ticket view "$Q#$N"` exits 1 with `not found`.

## Gotchas

- `tix ticket list` defaults to 20 results and silently truncates; always pass `--limit`.
- `--labels` on `edit` replaces the whole set. To add one label, read the current labels first and send the union.
- `close` without `--resolution` succeeds but leaves `resolution: null`, which the team's dashboards count as abandoned.
