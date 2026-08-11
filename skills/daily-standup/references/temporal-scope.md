# Temporal scope — the day as it stood at its end

The report describes the target day **as of that day's ceiling**, as if the
clock stopped. Every source and every state obeys this uniformly.

The trap it exists to avoid: a PR opened as a draft on the target day, then
readied and merged the *next* day, reads from the API as `merged`. Reporting it
that way describes a day that did not happen. It was a live draft the whole time
and belongs in the report as *opened (draft)*, with the ready and the merge
landing under **Plans today**.

## Find the governing timestamp, not `updatedAt`

Every state has one timestamp that decides whether it is in-window. Test *that*
field against `[FLOOR_UTC, CEIL_UTC]`.

| source · state | governing timestamp | if it is after the ceiling |
|---|---|---|
| PR · merged/closed | `closedAt` | report the ceiling state: `open`, or `draft` if it was a draft then |
| PR · draft→ready (and back) | `ready_for_review` / `convert_to_draft` timeline events | replay to the ceiling; a `ready_for_review` after the ceiling means still `draft` |
| review · verdict | review `submitted_at` | drop the review |
| ticket · done | `completedAt` | the started/QC state it held at the ceiling |
| ticket · cancelled | `canceledAt` | prior status |
| ticket · started | `startedAt` | whatever preceded (`Todo`/`Backlog`) |
| ticket · created / triaged | `createdAt` | omit — it did not exist yet |
| ticket · any other transition | **no dedicated field.** Gate on `updatedAt`: at-or-before the ceiling means the current status is safe; after it, reconstruct from issue history | the status held at the ceiling; if history is unavailable, drop the status claim and keep only in-window comments |
| ticket · comment | comment `createdAt` | drop the comment |

Prefer the exact fields (`completedAt`, `canceledAt`, `startedAt`) over
`updatedAt` wherever the tracker offers them. Fall back to issue history only
for transitions none of them cover — and note that some trackers expose history
only on the raw API, not through their MCP.

## Computing draft-ness at the ceiling

Do not read the current `isDraft`.

A PR is a draft at the ceiling **unless** there is a `ready_for_review` event
at-or-before the ceiling with no later `convert_to_draft` also at-or-before it.

A PR with no draft/ready events was opened in whatever state it currently shows:
currently-ready with no events means it opened ready; currently-draft with no
events means it opened draft.

## Bounds

Compute once, up front, in UTC, from local midnight in **the machine's own
zone** — derived, never named:

```bash
DATE="$TARGET"
FLOOR_UTC=$(TZ=UTC date -r "$(date -j -f '%Y-%m-%d %H:%M:%S' "$DATE 00:00:00" +%s)" +%Y-%m-%dT%H:%M:%SZ)
CEIL_UTC=$(TZ=UTC  date -r "$(date -j -f '%Y-%m-%d %H:%M:%S' "$DATE 23:59:59" +%s)" +%Y-%m-%dT%H:%M:%SZ)
echo "window: $FLOOR_UTC → $CEIL_UTC ($(date +%Z))"
```

Hardcoding a zone abbreviation in the `-f` format string does not mis-offset by
an hour — BSD `date` rejects it outright, both bounds come back empty, and every
query silently widens to all time. Echoing the zone is what makes that visible.

## In catch-up mode the window widens, the discipline does not

The gap window runs from `last_activity` to now, and may span days. Every item
inside it is still reconstructed as of **its own** moment rather than as the API
describes it today, and the "while you were away" section still reports state as
it stands now — because that is what you are catching up *to*.

State both bounds in the report's first line when the window is not a single
day, so nobody has to infer which days are covered.
