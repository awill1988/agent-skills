---
name: pr-stacks
description: >-
  Index stacked pull requests across an org and write the message that asks for
  review — merge order, what each PR does, its tracker ticket, and where review
  has stalled. Renderings: a team-facing digest, a per-PR split for separate
  threads, and a nudge naming only what has genuinely gone quiet. Use when asked
  to list or summarise stacked PRs, say a stack is ready for review, chase
  reviewers, check what is waiting on whom, or draft a PR status update for
  Slack. Do NOT use for reviewing the contents of a PR, for writing a PR
  description or commit message, or for a single PR that is not part of a stack.
argument-hint: "--org ORG [digest|split|nudge] [--description-length short|medium|long] [--stack repo#number] [--idle 30m] [--urgent]"
license: MIT
metadata:
  version: 1.0.0
---

# PR stacks

Turn the live state of open pull requests into something a teammate can act on
in one read.

**The job is de-risking the ask, not broadcasting status.** Every message this
skill writes spends someone else's attention. The default posture is a
colleague asking for help, not a system reporting a queue depth.

Nothing is hardcoded. The login comes from `gh api user`, the repos come from
what the search returns, the stack edges come from base/head refs, and ticket
keys come from PR titles. A repo or a stack that exists tomorrow is picked up
tomorrow with no edit here.

## Step 1 — index

```bash
bash "$SKILL_DIR/scripts/index-stacks.sh" --org ORG > /tmp/pr-stacks.json
```

`--org` is required. An unscoped search reaches every org the account can see,
which on a machine with work and personal access quietly reports a stack
spanning both.

**Expected output:** one JSON object with `org`, `counts`, `repos`, `skipped`,
`preflight`, `pull_requests`, `branch_stacks`, `ticket_groups`. Sanity-check
`counts.open` against what you expect before rendering anything.

If it fails, see [Troubleshooting](#troubleshooting). A repo the API refused
lands in `skipped` — **say so in the output**, because an empty section and an
unread repo look identical to the reader.

## Step 2 — preflight, and stop if it says stop

**Read `preflight` before writing anything outbound.** Two conditions halt the
run. Neither is a refusal — each is a question, and the answer may well be
"known, send it anyway."

| condition | why it halts |
|---|---|
| `preflight.failing` non-empty | asking for review on a red PR spends a reviewer's time on something you already know is wrong, and teaches a team that your requests are not worth opening |
| `preflight.recently_changed` non-empty | something landed in the last **3 minutes**; checks are stale or still running, and a reviewer may read a diff about to move under them |

On a hit, ask with `AskUserQuestion`, naming the PR and what was seen, and
offering three answers in this order: **fix first**, **send anyway and mention
it**, **drop it from the message**. "Send anyway" is legitimate — a known-red PR
with a note is honest, one presented as ready is not — so carry the caveat into
the message when it is chosen.

The index already discards two false alarms so you do not re-litigate them: a
`CANCELLED` check is a run a force-push superseded, not a verdict; and jobs from
superseded runs are dropped entirely, because a matrix job killed mid-flight
reports `failure` for a run that no longer exists. A gate that halts on a dead
run is one people learn to skip.

`nudge` reads the same fields without halting — an internal triage view is
exactly where a red check belongs. The gate guards *outbound* messages.

## Step 3 — know which kind of stack you have

**Branch stack** — a PR whose base is another open PR's head, in the same repo.
Since stacked PRs reached public preview this is a first-class GitHub object: a
linked stack renders a *stack map* in every member's merge box, policy and
Actions evaluate each PR against the base of the *stack*, and merge queues take
the whole stack in order.

**Ticket group** — PRs across repos sharing a `[KEY-N]` title prefix. Native
stacks are same-repo only, so a cross-repo chain cannot be one however much it
behaves like one. Nothing enforces its order; the prose has to carry it.

Say which one you are describing. Detail, plus how to link and announce a stack:
[`references/github-stacks.md`](references/github-stacks.md).

## Step 4 — tell reviewers a stack costs more than one approval

A stacked PR is not one review. When the PR below it merges, the child's merge
base moves and the rebase that keeps the stack linear pushes new commits — and
where a repo dismisses stale approvals on push, **the approval already given is
dismissed and has to be given again.**

The index carries `repos[].review_policy` per repo. When
`dismisses_stale_approvals_on_push` is `true`, disclose it once in the digest —
never per PR:

```
Heads up: each merge rebases the ones above it, so GitHub will dismiss your
approval and ask again. Sorry — that's the stack, not you.
```

`requires_code_owner_review: true` means naming a code owner rather than
"anyone". Any field `null` means the rulesets were unreadable — say the policy
is unverified rather than asserting either way.

Offer, in order: a **merge queue** (takes the stack in order, collapsing the
rounds into one), **review bottom-up and merge promptly**, or **ask for the
bottom PR only**. Do not offer to relax `require_last_push_approval` —
loosening a review control to reduce your own churn is not a trade this skill
proposes.

## Step 5 — write it

Read the PR body and write the *intent* and what it lets happen next, not the
file list. `body_lead` in the index is a starting point, not an answer — a first
line is often a heading or a caveat. If the body does not support a claim about
intent, say what the title says and stop.

- Good: "the two services stop keeping separate user shapes and share one
  principal. The new credential source lands in shadow mode, so no live request
  changes its decision yet."
- Bad: "adds a package and updates 90 controllers" — that is the diff, which the
  reader can already see.
- Bad: "improves identity handling" — says nothing, and costs a line to say it.

Enrich ticket keys from your tracker's MCP if one is connected (Linear, Jira)
and use the real title, state and URL. A key that resolves to nothing is
reported as `ticket unknown`, never inferred from the branch name.

Templates, worked examples and the full word budget:
[`references/rendering.md`](references/rendering.md).
Escalation protocol for `--urgent`: [`references/urgency.md`](references/urgency.md).

### Tone

Reviewing is someone stopping their own work. The index knows a PR has been
waiting 40 minutes; that fact decides **whether to write at all**, and does not
go in front of the reader.

- **Write "when you get a chance."** The idle figure is an input; to a peer it
  reads as a stopwatch.
- **Ask for the smallest reviewable thing.** A five-PR stack is a request for
  the bottom one. Name it.
- **Give the reader an exit.** "If you're heads-down, say so and I'll ask
  someone else" costs one line and removes the obligation to negotiate.
- **Lead with what it unblocks**, never with how long it has sat.
- **Write logins plainly, without @-mentions.** Tagging is the sender's call.
- **Escalate on a deadline, never on elapsed time.** A fast-moving team makes a
  short gap worth *noticing*; it is still not worth *saying*.
- **One nudge per PR per day**, and only if the state changed. Repetition is how
  a channel learns to filter you out.

### Format for Slack, not Markdown

Every message here is pasted into Slack, whose mrkdwn is a different dialect —
and the failure is silent, arriving looking careless in the channel where you
were asking a favour.

| write | not |
|---|---|
| `*bold*` single asterisks | `**bold**` |
| `_italic_` | `*italic*` |
| `•` or `-` at line start | `1.` auto-numbering, which Slack does not render |
| a bare url on its own line | `<url\|text>` — **does not work when pasted**, arrives literally |
| a blank line between blocks | `#`/`##` headers, which Slack ignores |
| plain lines, one fact each | tables — Slack has none |

**Emoji earn their place in headers.** Two or three in a whole message, marking
what a reader scans for. Never one per line item, never as a substitute for a
word.

Put the ask above the fold: the first two lines carry the ticket and what you
want, and detail follows.

## Step 6 — check the budget in code

```bash
bash "$SKILL_DIR/scripts/check-budget.sh" --file "$draft" --mode digest --length medium
```

Exits non-zero when over. Counting your own prose by eye is the least reliable
way to enforce the one constraint this skill exists to hold, so it is a script:
informational text (urls, `repo#number`, sizes, states) is free, authored text
is budgeted, and the two are reported separately.

Over budget means **delete a sentence, never compress a fact**. Cut in this
order: explanation the artifacts already carry, justification of why the work
was split, anything restating a title, adjectives.

## Step 7 — finish in an editor

**Every run ends by writing the message to a file and opening it.** That is the
handoff; a draft nobody can paste is not a finished job.

```bash
draft="/tmp/pr-stacks-<ticket>-<mode>.txt"
printf '%s\n' "$MESSAGE" > "$draft"
${VISUAL:-${EDITOR:-open}} "$draft"
```

The path is stable per ticket and mode on purpose: re-running updates the draft
already open rather than scattering new ones. **Say when a run replaced an
existing draft** — silently overwriting an edited message is the one way this
loses work. Re-open every run, including when unchanged; opening is what
surfaces the buffer.

For `split`, write one file per PR and open them together — each goes to a
different thread.

Chat gets two lines: which stack, which mode, what preflight found, and any
judgement call worth flipping. The body lives in the editor, where it is edited
and sent.

## Troubleshooting

**`error: --org is required`** — by design; see Step 1.

**`gh: command not found` / `gh auth status` fails** — the index reads GitHub
only. Run `gh auth login` and retry.

**A repo appears in `skipped`** — its metadata or rulesets were unreadable,
usually a token without access or a transient API failure. Report it in the
output; do not treat the gap as "no PRs there".

**`review_policy` fields are `null`** — rulesets need repo admin to read. Say
the re-approval policy is unverified rather than asserting either way.

**`gh stack` commands fail or are missing** — the extension needs `gh` 2.90.0+
(`gh --version`) and `gh extension install github/gh-stack`. Without it the
index still derives stacks from base/head refs; only native linking is
unavailable, so say so rather than claiming a stack is linked.

**No tracker MCP connected** — report the ticket key as written in the title and
skip enrichment. Never invent a ticket title.

**`counts.open` is 0 but you expect PRs** — check `--org` spelling and that
`--author` matches the account that opened them.
