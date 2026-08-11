---
name: daily-standup
description: >-
  Build a standup report for the previous working day from what actually
  happened — PRs authored, updated and reviewed, tracker tickets that changed
  state, and the coding-session nuance none of those record. Detects a gap in
  your own activity and switches to catch-up mode, reporting what moved while
  you were away instead of an empty day. Use when asked for a standup, yesterday's
  summary, standup notes, "what did I do yesterday", or a catch-up after time off.
  Do NOT use for sprint reports, retrospectives, or anyone else's activity.
argument-hint: "--org ORG [YYYY-MM-DD] [--catch-up|--no-catch-up] [--gap 24h]"
license: MIT
metadata:
  version: 1.0.0
---

# Daily standup

Reconstruct a working day from its evidence and write the message you post to
your team.

**The report describes the day as it stood at that day's end** — not as the API
describes it now. A PR opened as a draft on Tuesday and merged on Wednesday was
a draft all through Tuesday, and a Tuesday standup that calls it "merged" is
wrong in the way nobody catches.

Identity is derived, never configured: `gh api user` for the GitHub login, and
your tracker's MCP for the tracker identity. `--org` is required — an unscoped
search reaches every org the account can see.

## Step 1 — pick the window

The target day defaults to **the previous working day**, overridable with a
`YYYY-MM-DD` argument.

Bind every fact to that day with a hard floor and ceiling **in the machine's own
zone**, computed once, up front. Never name or hardcode a zone:

```bash
DATE="$TARGET"                       # YYYY-MM-DD
FLOOR_UTC=$(TZ=UTC date -r "$(date -j -f '%Y-%m-%d %H:%M:%S' "$DATE 00:00:00" +%s)" +%Y-%m-%dT%H:%M:%SZ)
CEIL_UTC=$(TZ=UTC  date -r "$(date -j -f '%Y-%m-%d %H:%M:%S' "$DATE 23:59:59" +%s)" +%Y-%m-%dT%H:%M:%SZ)
```

Echo `date +%Z` alongside the bounds so the zone is visible. A hardcoded
abbreviation in the format string does not merely mis-offset — BSD `date`
rejects it and both bounds come back empty, silently widening every query to
"all time".

## Step 2 — check for a gap before assuming there is a day to report

**Find the last moment you did anything**, across every source: your newest
commit, PR event, review, tracker transition or comment, and doc edit. Call it
`last_activity`.

```
now - last_activity > --gap (default 24h)   →  catch-up mode
```

This subsumes the special case of "it is Monday". A weekend is one instance of a
gap; so is a week of leave, a conference, or an illness. Keying on the calendar
means asking whether today is Monday when the real question is whether anything
happened. Keying on the data answers both, and does not need a new rule the next
time the shape of the absence changes.

`--catch-up` forces it on, `--no-catch-up` forces it off, `--gap` moves the
threshold.

### What catch-up mode changes

A standup after time away is not a report of an empty day. It is a statement
that **you have already absorbed what you missed** — the reading happened before
the meeting, and what your team needs is where you are landing, not an apology.

So the report inverts:

1. **One line naming the gap**, factually, without apology. "Back after three
   days" is the whole of it.
2. **What moved while you were away** — the section that carries the weight:
   - merges into branches you own or had open work on
   - review requests aimed at you, and reviews others left on your PRs
   - tickets assigned or reassigned to you, and status changes on tickets you own
   - incidents, rollbacks, or reverts touching your areas
   - decisions recorded in docs or tickets that change work you had planned
3. **What you are picking up today**, written as already-accounted-for. The
   implication of catching up is that it is done — so name the work, not the
   catching up.

**Never write "I need to catch up" or "still getting up to speed."** That
undersells reading you have already done and invites someone to re-explain it.
State the conclusion you reached, not the process of reaching it.

Where a normal standup omits other people's work, catch-up mode reports it —
because during the gap their work *is* the change in your context. Attribute it
plainly and never claim it.

## Step 3 — gather, then gate

Pull candidates from every source, then apply the activity gate: a resource
earns a place **only if you took a genuine in-window action on it**, never
because its `updatedAt` moved. See
[`references/activity-gate.md`](references/activity-gate.md) — this is where
most of the wrongness lives, and it is worth reading before trusting a result.

Reconstruct each item's state **as of the ceiling** using the governing
timestamp for that transition, not the record's `updatedAt`. Table of governing
timestamps per source and state:
[`references/temporal-scope.md`](references/temporal-scope.md).

Sources, in order of signal:

1. **PRs authored** — opened in-window.
2. **PRs updated** — pre-existing, but crossed a lifecycle milestone in-window.
3. **PRs reviewed** — a review you submitted in-window.
4. **Tracker tickets** — status transitions and comments you authored.
5. **Coding sessions** — the day's nuance, via
   `scripts/scan_sessions.py`. This is the only source permitted to open a
   work-stream with no PR or ticket behind it: an investigation, a remediation
   plan, a query that settled a question.

## Step 4 — write it

**Group by work-stream, not by PR type.** One bold header per stream. The
authored/updated/reviewed split drives gathering; it is not the visible
structure.

```
*Yesterday — YYYY-MM-DD*

*<work-stream>*
- <what happened> <raw url>

*Reviews — <topic>*
- Approved|Changes requested <what> (TICKET-#) <raw url>

*Plans today*
- <what you are picking up>
```

Omit any stream with no activity.

**Nuance attaches to the work, never to a section of its own.** Name the change,
not the exchange:

```
- Pivoted to polling — the provider emits nothing on that event   ✅
- Asked about the webhook surface and found it emits nothing      ❌ narrates the session
```

A decision states what was chosen **and what it was chosen over**. One line, the
fact that changed the work.

**Never mention the assistant, a session, a prompt, or a transcript.** The
report is your work; naming the tooling is both noise and a misattribution.

### Slack formatting

The output is pasted into Slack, whose mrkdwn is not Markdown:

- `*bold*` single asterisks, `_italic_`, `` `code` ``, `-` for bullets
- **never** `[text](url)` and **never** `<url|text>` — both arrive literally.
  A link is a title, a space, then the raw url
- `—` between a title and its description, `→` for transitions
- no `#` headers, no tables

## Step 5 — hand off

Write the report to a file and open it. That is how the skill concludes.

```bash
report="/tmp/standup-<target-date>.txt"
printf '%s\n' "$REPORT" > "$report"
${VISUAL:-${EDITOR:-open}} "$report"
```

Chat gets the path and any judgement call worth flipping — a dropped item, an
ambiguous attribution, whether catch-up mode fired. Not the report body: it is
edited and sent from the editor, and a wall of it in the console is noise.

## Troubleshooting

**Both time bounds are empty** — a zone abbreviation was hardcoded in the
`date -f` format string. Remove it; let `date` interpret local midnight.

**An item you remember is missing** — it probably failed the activity gate.
Check whether you crossed a milestone on it or only pushed commits; routine
iteration is deliberately not reportable.

**A merged PR is reported as open** — correct, if it merged after the ceiling.
The report describes the day, not now.

**No tracker MCP connected** — report PRs and sessions, and say the tracker was
unavailable rather than implying there were no ticket changes.

**Catch-up fired when you were working** — your activity was in a source the
skill does not read (a different forge, a wiki it cannot reach). Use
`--no-catch-up` and consider whether that source is worth adding.

**`scan_sessions.py` returns nothing** — it reads local transcripts, so it only
sees the machine it runs on. Sessions from another machine are invisible; say so
rather than reporting a quiet day.
