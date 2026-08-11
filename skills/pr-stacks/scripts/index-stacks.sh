#!/usr/bin/env bash
#
# index the caller's open prs and derive their stacks. emits one json object on
# stdout; every rendering decision belongs to the skill, not to this script.
#
# nothing here is hardcoded: the login, the org, the repos, the default branch
# and the ticket keys are all read from what github and the branch names
# actually say right now. a repo that appears tomorrow is picked up tomorrow.
#
# two kinds of stack, because they have different guarantees:
#
#   branch stack — a pr whose base is another open pr's head, in the same repo.
#     github enforces the order (a child cannot merge into main before its
#     parent) and retargets the child automatically when the parent merges and
#     its branch is deleted. this is a real dependency.
#
#   ticket group — prs across repos sharing a [KEY-N] title prefix. nothing
#     enforces anything; the order lives in someone's head. surfaced separately
#     for exactly that reason.
#
set -euo pipefail

usage() {
  cat <<'EOF'
usage: index-stacks.sh --org ORG [--author LOGIN] [--limit N] [--include-drafts]

emit json describing the caller's open prs, their branch stacks, their ticket
groups, and per-pr review latency. reads github only; writes nothing.

options:
  --org ORG          REQUIRED. the org or user whose repos to search.
  --author LOGIN     default: the authenticated user
  --limit N          max prs to consider (default 200)
  --include-drafts   drafts are included by default; this flag is accepted and
                     ignored, kept so callers can be explicit
  -h, --help

--org is required rather than defaulted. an unscoped search reaches every org
the account can see, which on a machine with work and personal access means
quietly indexing one from the other and reporting a stack that spans them.
naming the scope is one word and removes the whole class of surprise.
EOF
}

author=""
org=""
limit=200

while [[ $# -gt 0 ]]; do
  case "$1" in
    --author) author="$2"; shift 2 ;;
    --org) org="$2"; shift 2 ;;
    --limit) limit="$2"; shift 2 ;;
    --include-drafts) shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

for cmd in gh jq; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "error: '$cmd' is required but not found" >&2
    exit 1
  }
done

if [[ -z "$org" ]]; then
  echo "error: --org is required (e.g. --org acme). see --help for why." >&2
  exit 1
fi

[[ -n "$author" ]] || author=$(gh api user --jq '.login')

now_epoch=$(date -u +%s)

query="author:${author} is:pr is:open org:${org}"

# search gives the repo set; it does not give base/head refs, so the repos it
# names are then asked directly.
#
# shellcheck disable=SC2086  # $query must word-split into separate qualifiers
repos=$(gh search prs $query --limit "$limit" --json repository \
  --jq '[.[].repository.nameWithOwner] | unique | .[]')

if [[ -z "$repos" ]]; then
  jq -n --arg author "$author" --arg org "$org" \
    '{author: $author, org: $org, generated_at: (now | todate), repos: [], skipped: [],
      counts: {open: 0, drafts: 0, in_branch_stacks: 0, waiting_on_review: 0},
      preflight: {fresh_window_minutes: 3, failing: [], recently_changed: []},
      pull_requests: [], branch_stacks: [], ticket_groups: []}'
  exit 0
fi

# per repo: the default branch (so stack roots are recognised without assuming
# a name) and every open pr of this author with the refs needed to build edges.
prs_json="[]"
repo_list="[]"
skipped="[]"

while IFS= read -r repo; do
  [[ -n "$repo" ]] || continue

  # a repo that cannot be read is counted and skipped, never fatal. one flaky
  # api call should not turn a status report into no status report, and the
  # skipped list is what stops the gap being mistaken for "no prs there".
  if ! default_branch=$(gh api "repos/${repo}" --jq '.default_branch' 2>/dev/null); then
    skipped=$(jq -n --argjson acc "$skipped" --arg r "$repo" \
      '$acc + [{repo: $r, reason: "repo metadata unreadable"}]')
    continue
  fi

  # Whether this repo dismisses approvals when a branch is pushed. Derived, not
  # assumed: it decides whether the outbound message has to warn reviewers that
  # a stack costs them one approval per layer. Rulesets are additive, so any
  # active ruleset turning it on turns it on. A repo whose rulesets cannot be
  # read reports null, and the skill says "unverified" rather than guessing.
  rules=$(gh api "repos/${repo}/rulesets" --jq '[.[] | select(.enforcement=="active") | .id] | .[]' 2>/dev/null || true)
  dismisses="null"
  code_owner="null"
  last_push="null"

  if [[ -n "$rules" ]]; then
    dismisses="false"; code_owner="false"; last_push="false"
    while IFS= read -r rid; do
      [[ -n "$rid" ]] || continue
      params=$(gh api "repos/${repo}/rulesets/${rid}" \
        --jq '[.rules[]? | select(.type=="pull_request") | .parameters] | .[0] // {}' 2>/dev/null || echo '{}')
      [[ $(jq -r '.dismiss_stale_reviews_on_push // false' <<<"$params") == "true" ]] && dismisses="true"
      [[ $(jq -r '.require_code_owner_review // false' <<<"$params") == "true" ]] && code_owner="true"
      [[ $(jq -r '.require_last_push_approval // false' <<<"$params") == "true" ]] && last_push="true"
    done <<< "$rules"
  fi

  repo_list=$(jq -n --argjson acc "$repo_list" --arg r "$repo" --arg d "$default_branch" \
    --argjson dis "$dismisses" --argjson co "$code_owner" --argjson lp "$last_push" \
    '$acc + [{repo: $r, default_branch: $d, review_policy: {
        dismisses_stale_approvals_on_push: $dis,
        requires_code_owner_review: $co,
        requires_last_push_approval: $lp }}]')

  # reviewRequests / latestReviews carry the state a nudge needs. updatedAt is
  # the fallback clock when nothing was ever requested.
  page=$(gh pr list --repo "$repo" --author "$author" --state open --limit "$limit" \
    --json number,title,url,headRefName,baseRefName,isDraft,createdAt,updatedAt,additions,deletions,changedFiles,reviewDecision,reviewRequests,latestReviews,mergeable,mergeStateStatus,statusCheckRollup,body \
    2>/dev/null || echo '[]')

  prs_json=$(jq -n --argjson acc "$prs_json" --argjson page "$page" \
    --arg repo "$repo" --arg default_branch "$default_branch" \
    --argjson now "$now_epoch" '
    $acc + [ $page[] | {
      repo: $repo,
      default_branch: $default_branch,
      number: .number,
      title: .title,
      url: .url,
      head: .headRefName,
      base: .baseRefName,
      draft: .isDraft,
      created_at: .createdAt,
      updated_at: .updatedAt,
      additions: .additions,
      deletions: .deletions,
      changed_files: .changedFiles,
      review_decision: (.reviewDecision // "NONE"),
      reviewers_requested: [ .reviewRequests[]? | (.login // .name // .slug) ] | map(select(. != null)),
      reviews_submitted: [ .latestReviews[]? | {author: (.author.login // "unknown"), state: .state, submitted_at: .submittedAt} ],
      mergeable: .mergeable,
      merge_state: .mergeStateStatus,
      # the rollup mixes two shapes — check runs carry name/conclusion, legacy
      # status contexts carry context/state — so both spellings are read and a
      # check whose shape is neither is counted as unknown rather than passing.
      checks: (
        [ .statusCheckRollup[]? | {
            name: (.name // .context // "unnamed"),
            state: ((.conclusion // .state // .status // "PENDING") | ascii_upcase),
            started_at: (.startedAt // .createdAt // null),
            # the workflow run this job belongs to. run ids increase, so this is
            # what separates the live run from one a force-push superseded.
            run: ((.detailsUrl // .targetUrl // "")
                  | capture("/runs/(?<id>[0-9]+)"; "n").id? // null | tonumber?)
          } ] as $raw
        # The rollup keeps jobs from superseded runs, and they can report
        # `failure` — a matrix job killed mid-flight when the newer push landed.
        # Judging the PR on those means halting on a run that no longer exists,
        # which is how a gate earns its way into being ignored. Only the newest
        # run counts; checks with no run id (CodeBuild and other status
        # contexts) are always kept, since nothing supersedes them.
        | ([ $raw[] | .run | select(. != null) ] | max) as $newest_run
        | [ $raw[] | select(.run == null or $newest_run == null or .run == $newest_run) ] as $all
        | {
            total: ($all | length),
            # FAILURE/ERROR/TIMED_OUT are the run saying no. ACTION_REQUIRED is a
            # workflow waiting on a human, which blocks review just as hard.
            failing: [ $all[] | select(.state | test("^(FAILURE|ERROR|TIMED_OUT|ACTION_REQUIRED)$")) | .name ],
            # CANCELLED is almost always a run superseded by a newer push, not a
            # verdict. Counting it as failing would halt the gate on every
            # force-push — so it feeds the freshness signal instead, which is
            # what it actually means.
            superseded: [ $all[] | select(.state == "CANCELLED") | .name ],
            pending: [ $all[] | select(.state | test("^(PENDING|QUEUED|IN_PROGRESS|EXPECTED|WAITING)$")) | .name ],
            # minutes since the newest check began. a check starting seconds ago
            # means something was just pushed, which is the freshness signal the
            # preflight gate reads.
            newest_started_minutes: (
              [ $all[] | .started_at | select(. != null) | fromdateiso8601 ]
              | if length == 0 then null else (($now - max) / 60 | floor) end
            )
          }
      ),
      updated_minutes_ago: (.updatedAt | fromdateiso8601 | ($now - .) / 60 | floor),
      # the first non-empty line of the body, trimmed. the skill may use it as a
      # starting point for the one-line intent; it is never the final word,
      # because a body first line is not an intent statement.
      body_lead: ([ (.body // "") | split("\n")[] | select(test("\\S")) ] | .[0] // "" | .[0:240]),
      # ticket key from the title prefix, then the branch, then nothing. never
      # invented: a pr with no key reports null and the skill says so.
      ticket: (
        (.title | capture("^\\[(?<k>[A-Z][A-Z0-9]+-[0-9]+)\\]"; "n").k)?
        // (.title | capture("\\b(?<k>[A-Z][A-Z0-9]+-[0-9]+)\\b"; "n").k)?
        // (.headRefName | capture("(?<k>[A-Z][A-Z0-9]+-[0-9]+)"; "in").k | ascii_upcase)?
        // null
      ),
      # minutes since review was last plausibly waited on: the newest submitted
      # review if any, else the last push/update. a nudge threshold reads this.
      idle_minutes: (
        ( [ .latestReviews[]?.submittedAt ] | map(select(. != null)) | sort | last )
        // .updatedAt
        | fromdateiso8601 | ($now - .) / 60 | floor
      ),
      waiting_on_review: (
        (.isDraft | not)
        and ((.reviewDecision // "NONE") != "APPROVED")
        and (
          ([ .reviewRequests[]? ] | length > 0)
          or ([ .latestReviews[]? ] | length == 0)
        )
      )
    } ]')
done <<< "$repos"

# build the graph. an edge exists when a pr's base is another open pr's head in
# the same repo; roots target the repo default branch. depth and order fall out
# of walking parents, so the merge order printed later is derived rather than
# asserted.
jq -n --argjson prs "$prs_json" --argjson repos "$repo_list" \
  --argjson skipped "$skipped" --arg author "$author" --arg org "$org" '
  def key(p): "\(p.repo)#\(p.number)";

  # walking up needs the parent map in scope, so both walks are defined against
  # it as an argument rather than closing over a later binding.
  def depth($parent_of; k; n):
    if n > 32 then n
    elif ($parent_of[k] // null) == null then n
    else depth($parent_of; $parent_of[k]; n + 1) end;

  def rootof($parent_of; k; n):
    if n > 32 then k
    elif ($parent_of[k] // null) == null then k
    else rootof($parent_of; $parent_of[k]; n + 1) end;

  ($prs | map({ key: "\(.repo)|\(.head)", value: key(.) }) | from_entries) as $by_head
  | ($prs | map(. + { parent: ($by_head["\(.repo)|\(.base)"] // null) })) as $linked
  | ($linked | map({ key: key(.), value: .parent }) | from_entries) as $parent_of

  # a stack is every pr sharing a root. single-member groups are dropped: one pr
  # is not a stack, and calling it one is noise.
  | ( $linked
      | map(. + {
          depth: depth($parent_of; key(.); 0),
          root: rootof($parent_of; key(.); 0)
        })
    ) as $rooted
  | ( $rooted | group_by(.root) | map(select(length > 1) | sort_by(.depth)) ) as $stacks

  # ticket groups: same key, more than one pr, and not already one branch stack.
  | ( $rooted
      | map(select(.ticket != null))
      | group_by(.ticket)
      | map(select(length > 1))
      | map(select((map(.root) | unique | length) > 1 or (map(.repo) | unique | length) > 1))
      | map(sort_by([.repo, .number]))
    ) as $groups

  | {
      author: $author,
      org: $org,
      generated_at: (now | todate),
      repos: $repos,
      skipped: $skipped,
      counts: {
        open: ($rooted | length),
        drafts: ($rooted | map(select(.draft)) | length),
        in_branch_stacks: ($stacks | flatten | length),
        waiting_on_review: ($rooted | map(select(.waiting_on_review)) | length)
      },
      # what the preflight gate reads. computed here so the halt is a fact from
      # the api rather than something re-derived per rendering.
      preflight: {
        fresh_window_minutes: 3,
        failing: [ $rooted[] | select((.checks.failing | length) > 0)
                   | { repo, number, url, failing: .checks.failing } ],
        recently_changed: [ $rooted[]
          | select(
              (.updated_minutes_ago < 3)
              or ((.checks.newest_started_minutes // 9999) < 3)
              # a superseded run means a force-push landed, but only while the
              # picture is still settling — cancelled runs from days ago are
              # history, not freshness.
              or ((.checks.superseded | length) > 0 and .updated_minutes_ago < 30)
            )
          | { repo, number, url,
              updated_minutes_ago,
              checks_started_minutes_ago: .checks.newest_started_minutes,
              superseded_runs: (.checks.superseded | length) } ]
      },
      pull_requests: ($rooted | sort_by([.repo, .number])),
      branch_stacks: [ $stacks[] | { repo: .[0].repo, root: .[0].root, size: length, members: . } ],
      ticket_groups: [ $groups[] | { ticket: .[0].ticket, size: length, members: . } ]
    }
'
