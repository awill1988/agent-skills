# Stacked PRs on GitHub

Read after `SKILL.md` Step 3, or when asked how to announce that a stack is
ready.

## Two kinds of stack, and they are not equivalent

Conflating them is the mistake that gets a merge done in the wrong order.

### Branch stack — GitHub enforces it

A PR whose base is another open PR's head, in the same repo. Since stacked pull
requests reached public preview (2026-07-30) this is a **first-class GitHub
object**, not just a base-ref convention:

- a linked stack renders a **stack map** in the merge box of every member
- policy and Actions evaluate each PR against the **base of the stack**, not its
  direct base — so a mid-stack PR is held to the trunk's rules
- **merge queues** take the whole stack in order; if one is ejected, everything
  above it goes too
- when the parent merges and its branch is deleted, GitHub **automatically
  retargets** the child onto the parent's base

Inside a checkout, `gh stack view --json` is authoritative for that stack —
prefer it over the derived graph. The index covers the org-wide view and the
repos you are not standing in.

### Ticket group — nothing enforces it

PRs across repos sharing a `[KEY-N]` title prefix. Native stacks are documented
as **same-repository only**, so an infra-module → service-config chain cannot be
a GitHub stack however much it behaves like one. Its order exists only in prose,
so the prose has to carry it. Never present a ticket group as though GitHub were
protecting it.

## Announcing that a stack is ready

**Link it as a real stack first, then write one short message.** GitHub carries
the structure itself, which is what lets the message be short enough to read.

1. **Register the stack.** In a checkout, `gh stack submit`. For PRs that
   already exist and are managed by other tooling, `gh stack link <bottom> <top>`
   works without adopting local tracking. On the web, GitHub shows a
   **recommendation banner** on PRs whose branches already line up, offering to
   link them in one click. Once linked, the stack map is the canonical "here is
   the set" and stays correct with no maintenance.
2. **Flip them ready bottom-up**, so the first thing a reviewer opens is the
   first thing that should merge. `gh stack submit --open` marks new *and*
   existing PRs ready; per-PR, `gh pr ready` does the same and is reversible with
   `--undo`. Neither merges nor approves. Drafts cannot be merged and do not
   request code owners, so the flip is the actual signal. Stop at the first PR
   whose checks are not green and say which one stopped it.
3. **Then one message** — the digest, kept short *because* the stack map already
   carries the structure.

A tracking issue with a task list remains the fallback for a **cross-repo ticket
group**: a task list in an issue body unfurls each PR with its title and live
state, shows a completed/total count, gives each PR a "Tracked in" backlink, and
auto-ticks as they merge. Do not reach for it on a single-repo stack — it
duplicates both the tracker and the stack map.

Sub-issues replaced task-list blocks (100 per parent, 8 levels) but hold
*issues*, not PRs, so they do not serve a PR stack.

## Constraints worth knowing before recommending any of this

- **Same repository only.** No cross-fork, no cross-repo stacks.
- **Merging uses the asynchronous merge API.** ChatOps or bots built on the
  legacy merge endpoint cannot land a stacked PR.
- **`gh stack` needs `gh` 2.90.0+.** Check `gh --version` and say so if the
  local CLI is older; the index still derives stacks from base/head refs, but
  native linking will not be available.
- **Not supported in GitHub Desktop.**

## Re-approval: the cost nobody mentions until it happens

GitHub records the diff state when a PR is approved. If that state changes —
including *because a related pull request merged into the target branch* — the
approval is dismissed as stale where the repo enables
`dismiss_stale_reviews_on_push`. The cascading rebase that keeps a stack linear
then pushes new commits on top of that.

So a three-PR stack is three approvals, not one. The index derives
`repos[].review_policy` per repo so the warning appears only where it is true.
Tell reviewers up front — see `SKILL.md` Step 4.

The documented alternative, `require_last_push_approval`, keeps approvals alive
by requiring one from someone other than the last pusher. **Do not propose it.**
Loosening a review control to reduce your own churn is a trade for the repo's
owners to make deliberately, not a workaround a status skill suggests.
