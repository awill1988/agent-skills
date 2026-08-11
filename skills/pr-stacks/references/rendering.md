# Rendering: modes, templates, budget

Read after `SKILL.md` Step 5. Everything here is Slack mrkdwn — see the format
table in `SKILL.md` before writing a line.

## The word budget

Split every message into two kinds of text and budget only the second.

**Informational — free, never trimmed.** Anything you are *quoting or
reporting*: urls, `repo#number`, the PR title as written, `+add/-del`, file
counts, draft/ready, CI state, review state, the ticket key and its title, the
deadline. These are what the reader acts on. A message that drops a fact to make
room for prose has it backwards.

**Authored — budgeted.** The line-item description, the framing, the ask, the
exit line, any justification.

### `--description-length`

| setting | per line item | use when |
|---|---|---|
| `short` | 10–25 words | the channel has context — a standup thread, a re-ping, a ticket everyone is watching |
| `medium` *(default)* | 25–50 words | the normal ask: what it does, what it unblocks, why it is its own PR |
| `long` | 50–90 words | a reviewer with no context, a cross-repo group whose order needs explaining, or a change whose *shape* is under review |

**The band is a target, not a quota.** A line item that says everything in 20
words stays at 20 even on `medium`. The floor exists to stop one-liners that say
nothing, not to demand volume — padding to reach it is the failure the whole
budget exists to prevent.

### Everything else

| span | budget |
|---|---|
| connective prose in one `digest` | 40 / 60 / 100 words for short / medium / long |
| one `split` message | its line item, plus 15 words of framing |
| one `nudge` | 60 words, line items forced to `short` |
| one `--urgent` | 80 words — the extra 20 buys the consequence and the exit |

Per message, not per stack. Three stacks is three messages each inside its own
budget, not one message at triple the size.

`scripts/check-budget.sh` enforces this. Run it before delivering.

## Mode: digest (default)

```
<emoji> *<ticket key> — <ticket title>* · <n> PRs
<the ask: which one to start with>

• *<repo>#<n>* · +<add>/-<del>, <files> files · <ready|draft> · <ci> · <review state>
  <line item>
  <url>

• ...

<the exit line>
<blockers, if any>
```

The ask sits on line two, above Slack's fold. List bottom-of-stack first and say
"start with" rather than numbering — Slack will not render `1.` as a list and a
bare digit reads as a count.

### Worked example — `medium`

Line items of 38 and 31 words, 26 words of connective prose against the 60-word
budget:

```
🧱 *PROJ-412 — one identity primitive for the gateway and the api* · 2 PRs
Start with #1456 — the second only makes sense after it.

• *acme/platform#1456* · +2886/-425, 134 files · ready · checks green · changes requested
  The gateway and the api stop keeping separate user shapes and share one
  principal. A new credential source lands in shadow mode, so no live request
  changes its decision yet.
  https://github.com/acme/platform/pull/1456

• *acme/platform#1465* · +1224/-41, 22 files · ready · checks green · no review yet
  Counts every authorization decision with an `enforced` label, which is what
  turns "what breaks if we enforce this" from an afternoon in the log store
  into one query.
  https://github.com/acme/platform/pull/1465

If you're heads-down, say so and I'll find another reviewer rather than let
it sit.
```

Note what is **absent**: no sentence explaining that the second targets the
first's branch. A linked stack renders that in every merge box, and narrating it
spends budget on something already on screen.

### Rules

- Order is depth order from the index (`members` is pre-sorted).
- State each PR's draft status. A draft in a stack is a deliberate signal —
  drafts cannot be merged and do not request code owners.
- **Never call a stack ready** when a member has a failing required check or a
  lower member is still draft. Say which one is holding it.
- One stack per message. Past two or three stacks, list them with a line each
  and offer to expand one.
- The framing sentence about merge order is usually cuttable — keep it only when
  the stack is *not* linked, or for a cross-repo ticket group.

## Mode: split

One message per PR, each pasted into its own thread. Every message must stand
alone — someone seeing only the third still needs to know it is third and what
it sits on.

```
*<repo>#<n>* — <title>
<line item>

<i> of <n> in the <ticket key> stack · sits on <repo>#<parent>
+<add>/-<del> across <files> files · <ready|draft> · <ci> · <review state>
<url>
<ticket url>
```

### Worked example — `medium`

```
*acme/platform#1465* — feat(identity): report every authorization decision
Counts every authorization decision with an `enforced` label, which is what
turns "what breaks if we enforce this" from an afternoon in the log store into
one query.

2 of 2 in the PROJ-412 stack · sits on acme/platform#1456
+1224/-41 across 22 files · ready · checks green · no review yet
https://github.com/acme/platform/pull/1465
https://linear.app/acme/issue/PROJ-412
```

Number within the stack, from the bottom. Keep the "sits on" line even for a
root — write `sits on main` so the reader knows it is the bottom.

`short` is usually wrong here: the message has to stand alone, which is the case
the longer bands exist for. If one still needs a paragraph on top of `long`, the
PR needs a better title — fix that instead of buying words.

## Mode: nudge

Two outputs. The triage block is the author's own view and belongs in chat; the
chase itself is a message and goes to a file like every other mode.

Default threshold 30 minutes; `--idle` overrides (`45m`, `2h`, `1d`). Idle is
`idle_minutes` from the index: minutes since the newest submitted review, or
since the last update when nobody has reviewed. It is a *plausible waiting
time*, not a promise — a PR pushed 20 minutes ago reads as 20 minutes idle even
if the request went out yesterday. Say "idle", never "ignored".

### Triage block — chat only

```
📊 *PR status* — <n> open, <n> in <n> stacks, <n> waiting on review

*Stacks*
• <ticket key> — <n> PRs, <bottom-most unmerged> is next · <state>

*Waiting on review* (idle > <threshold>)
• <repo>#<n> <title> — <reviewers or "no reviewer requested"> · idle <duration>

*Mergeable now*
• <repo>#<n> — approved, checks green
```

### The chase — outbound

```
Morning — *acme/platform#1456* is still open when you get a chance. It's the
bottom of the PROJ-412 stack, so nothing above it can move until it lands.
https://github.com/acme/platform/pull/1456

No rush if you're mid-something; tell me and I'll ask someone else.
```

Twenty-nine authored words, no duration anywhere.

### Rules

- **Chase only what has asked for something**: ready, with a reviewer requested.
  A draft appears in the triage block and never in the chase.
- **Distinguish "no reviewer requested" from "requested and quiet."** The first
  is the author's to fix; only the second is a chase.
- Sort by idle descending. Cap at ten and say how many were cut.
- If nothing is over the threshold, say exactly that in one line. A nudge with
  no findings is a useful answer, not an empty one.

## Sync — drift worth reporting

Check these against the index before rendering and report any hit inline:

| check | why it matters |
|---|---|
| a member's `base` is the default branch but it is not the root | GitHub retargeted it: its parent merged, so the stack is shorter than the author thinks |
| a child is `BEHIND` its parent (`merge_state`) | its diff shows changes the parent already landed |
| a lower member is ready while an upper one is draft | the reviewable unit is inverted; reviewers start in the wrong place |
| `mergeable` is `CONFLICTING` | the stack cannot land in the stated order until it is rebuilt |
| two members share a ticket key with a third PR outside the stack | a ticket group is hiding behind the branch stack; say both shapes |

**Report drift; do not repair it.** Rebasing a stack rewrites history on
branches that may already carry review threads.
