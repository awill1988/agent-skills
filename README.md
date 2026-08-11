# agent-skills

Agent Skills for coding agents — portable across Claude Code, Claude.ai, and any
tool that implements the [Agent Skills](https://agentskills.io) standard.

## Skills

| skill | what it does |
|---|---|
| [`pr-stacks`](skills/pr-stacks) | Indexes stacked pull requests across an org and writes the message that asks for review — merge order, what each PR does, its tracker ticket, and where review has stalled. |
| [`daily-standup`](skills/daily-standup) | Reconstructs a working day from its evidence — PRs, tracker transitions, coding-session nuance — and switches to catch-up mode when you have been away. |

## Install

**As a plugin marketplace (Claude Code):**

```
/plugin marketplace add awill1988/agent-skills
/plugin install pr-stacks@agent-skills
```

**Manually:** copy a skill folder into `.claude/skills/` in your project, or
`~/.claude/skills/` for every project.

## pr-stacks

A stack of pull requests is cheap to open and expensive to ask for. Each layer
is a separate review, GitHub dismisses approvals as lower PRs merge, and the
person you are asking has to reconstruct the order from base refs. This skill
does the reconstruction and writes the ask.

```bash
# what it reads
bash skills/pr-stacks/scripts/index-stacks.sh --org acme > /tmp/stacks.json
```

It derives everything live — your login from `gh api user`, the repos from what
the search returns, stack edges from base/head refs, ticket keys from PR titles,
and each repo's review policy from its rulesets. There is no list of repos to
maintain.

**Three renderings:** a team-facing `digest`, a `split` with one self-contained
message per PR, and a `nudge` that names only what has genuinely gone quiet.

**It stops before it wastes someone's time.** A preflight gate halts on a
failing check or a push inside the last three minutes and asks whether you knew,
rather than shipping an ask for a PR that is red or about to move. It discards
the two false alarms that would otherwise make such a gate useless: cancelled
runs, and jobs belonging to a run a force-push superseded.

**It is opinionated about the ask itself.** Idle time decides whether to write,
and never appears in what a reviewer reads. The ask names the smallest
reviewable unit. Every message offers an exit. `--urgent` refuses to escalate
without a named deadline and consequence, because an urgent framing nobody can
check is what makes the next real one ignorable.

**Output is Slack mrkdwn**, budgeted in words — informational text (urls, sizes,
states) is free, authored prose is capped, and `check-budget.sh` enforces it
rather than asking a model to count.

### Requirements

- [`gh`](https://cli.github.com), authenticated (`gh auth login`)
- `jq`
- optional: `gh extension install github/gh-stack` (needs gh 2.90.0+) for native
  stack linking
- optional: a tracker MCP (Linear, Jira) for ticket enrichment

### Arguments

```
--org ORG                              required; the org or user to search
digest | split | nudge                 rendering, default digest
--description-length short|medium|long per-line-item detail, default medium
--stack repo#number                    limit to one stack
--idle 30m                             nudge threshold
--urgent                               escalate; asks for a deadline first
```

`--org` is required rather than defaulted: an unscoped search reaches every org
an account can see, which on a machine with work and personal access quietly
reports a stack spanning both.

## daily-standup

Most standup tooling reports what the API says *now*. A PR opened as a draft on
Tuesday and merged Wednesday reads as "merged", so a Tuesday standup describes a
day that did not happen. This one reconstructs each item's state **as of the
target day's end**, using the governing timestamp for each transition rather
than `updatedAt`.

It is strict about what counts. A bumped `updatedAt` is not activity: pushing
commits, syncing a branch, a label edit, or someone else's comment all move the
timestamp without you having crossed a milestone, and none of them earn a place
in the report.

**Catch-up mode** is the part worth stealing. Rather than special-casing Monday,
it measures the gap since your last activity across every source. Past the
threshold (24h by default) the report inverts: one line naming the gap, then
what moved *while you were away* — merges into your branches, reviews aimed at
you, tickets reassigned, decisions that change your plans — and then what you
are picking up today, written as already-accounted-for. A weekend is one
instance of a gap; so is leave, a conference, or illness. Keying on the data
handles all of them without a new rule each time.

### Requirements

- [`gh`](https://cli.github.com), authenticated
- `python3` for the session scanner
- optional: a tracker MCP (Linear, Jira) for ticket transitions

## Contributing

Skills follow the [Agent Skills](https://agentskills.io) layout: a kebab-case
folder containing `SKILL.md` with YAML frontmatter, plus optional `scripts/`,
`references/`, and `assets/`. Keep `SKILL.md` focused and move depth into
`references/` — it is loaded into context every time the skill triggers.

Shell scripts are `shellcheck`-clean.

## License

MIT — see [LICENSE](LICENSE).
