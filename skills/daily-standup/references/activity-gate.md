# The activity gate

A bumped `updatedAt` is not activity. This is the filter that decides what
appears in the report, and it is where most wrong standups come from — a search
matched on `--updated`, the item looked recent, and it went in the report
despite nobody having touched it.

**A resource earns a place only if you took a genuine in-window action on it.**
Applied to every candidate before the as-of-ceiling reconstruction: no in-window
action by you → the resource does not appear, in any stream.

## GitHub pull requests

The bar is a **lifecycle milestone by you, in-window** — not mere change.

**Reportable:**

- a PR **opened** in-window (it is a new authored item)
- a pre-existing PR you **merged, closed, marked ready for review, reviewed, or
  commented on** in-window

**Not reportable:**

- **pushing commits, or merging the trunk into the branch.** Routine iteration
  crosses no milestone. A still-open PR that only accrued commits is dropped —
  it gets reported the day it lands. This is the case most worth holding the
  line on: a real feature commit landed, the work was genuinely done, and it
  still does not appear, because a standup reports milestones and the milestone
  is coming.
- label, milestone or assignee edits
- base-branch or fork syncs
- CI status writes
- a merge, close, comment or review performed by **a bot or another person** —
  each moves `updatedAt` into the window without you having acted

Confirm the actor and the action on the PR timeline before including any
pre-existing PR:

```bash
gh api "repos/<org>/<repo>/issues/<number>/timeline" \
  --jq '.[] | select(.created_at >= "'"$FLOOR_UTC"'" and .created_at <= "'"$CEIL_UTC"'")
        | {event, actor: .actor.login, created_at}'
```

## Tracker issues

Reportable if and only if there is an in-window **status transition**, or an
in-window **comment you authored**.

Not reportable — all of these move `updatedAt` without any real activity:

- a cycle, sprint or backlog re-assignment
- a sub-issue link
- a relation or label edit
- a parent bumped by a child issue's creation

## Coding sessions

Reportable if the session shows, in-window, a **decision point, a direction
change, a durable finding, or file edits**.

Not reportable:

- a session that only read or searched
- a scan that returned nothing
- a plan that was abandoned
- a session whose whole content is already stated by a PR or ticket bullet —
  fold it in rather than repeating it

**Sessions are the one source permitted to open a work-stream with no PR or
ticket behind it**: an investigation, a remediation plan, a production query
that settled a question. That exemption is theirs alone; every other clause of
this gate stands.

## Catch-up mode inverts the actor, not the bar

When a gap has fired, the "while you were away" section reports **other
people's** actions — that is the point of it. The bar does not soften: a merge,
a review, an assignment or a status transition still has to have happened, and a
passive bump still does not count. Only the actor changes, and the report
attributes it plainly.

Your own items in that window are still gated normally. Time away does not make
routine iteration reportable.

## Report what you dropped

Say in chat which candidates the gate removed and why. A silently dropped item
looks identical to an item that never existed, and the gate is strict enough
that a wrong drop is the likeliest failure. Listing them makes it a correction
rather than a mystery.
