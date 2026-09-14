# A worked rewrite

One document, shown in the spec register and then after the eight moves. The
domain is generic — a product catalog whose entries are copied into a search
index — and the design substance is identical in both versions, which is the
point: every change is rhetorical.

## Before: the spec register

> # Catalog→index sync: design decision
>
> Design deliverable for TICKET-101. Inputs: TICKET-98 failure inventory, the
> `indexer` service's existing write contract, the staleness gauges from
> TICKET-72. As of 2025-03-02.
>
> **Decision:** extend `indexer` with one service, `EntrySyncService`, two
> RPCs (`SyncEntry`, `SyncPricing`), one shared outcome enum. Migrate the four
> hand-rolled write paths onto it.
>
> Rejected alternatives:
>
> | option | why rejected |
> | --- | --- |
> | per-path patches | duplicated scaffolding, drift |
> | shared client library | second write authority, parallel dedupe stores |
> | new sync worker | re-owns machinery `indexer` already has |
>
> Migration: 4 steps. Metrics: `sync_writes_total{path,outcome}`. Staleness
> gauge acceptance per step. See TICKET-101 for scope.

Everything a reviewer needs is present, and nothing is readable. The first
sentence is metadata. The decision arrives before the reader knows what an
entry, an index, or a sync is. The alternatives are dispatched in a table —
the trial was held elsewhere. There are no open questions, so the reader must
either trust it or re-derive it.

## After: the moves applied

> # Catalog→index sync: design decision
>
> Every product at Acme is described in two places. The catalog is the record
> of truth: pricing, availability, and descriptions are entered there.
> The search index keeps a copy of the same product — the version a customer's
> query actually hits. Entries in the index are always copied from the
> catalog, never originated in it; when the copying is dependable the two
> agree, and when it is interrupted or repeated they drift apart.
>
> This page introduces how that copying works today, the approaches we
> considered for making it dependable, and the one we recommend. It closes
> with the questions we have not resolved. Readers who want the failure
> inventory, path by path, will find it in TICKET-98.
>
> ## Two copies, and how they drift
>
> It may help to begin with a picture of how entries travel today:
>
> ```
>   storefront ── product edits ────► index
>         │────── pricing updates ──► index
>         │────── availability ─────► index
>         └────── bulk imports ─────► index
>
>   indexer ───── category tree ────► index, idempotently
> ```
>
> The four upper paths were each written for a different feature, and each
> carries its own idea of what to do when a write fails partway. None marks a
> write in a way that lets a retry be recognized as a repeat, so an
> interrupted write either vanishes or lands twice. As of the February audit,
> 4.1% of live entries disagree with their catalog record.
>
> The lower path is the interesting one. The `indexer` service already copies
> the category tree with the discipline the other paths lack: a deterministic
> key per write, an explicit already-applied answer on replay. The question is
> not how to invent dependable copying, but where the paths that lack it
> should acquire it.
>
> ## Approaches we considered
>
> The most conservative is to patch each path in place. This keeps every
> change small and reviewable. Its weakness appears in the aggregate: the
> missing-key scaffolding would be rebuilt four times, and each copy would
> drift on its own — which is how we arrived here.
>
> A second approach is a shared client library beside the callers. It avoids
> a network hop; its weakness is a second write authority whose dedupe store
> can itself disagree with `indexer`'s.
>
> A third is a new standalone sync worker — the right shape, but the wrong
> home, since `indexer` already owns the queue, the retry lifecycle, and the
> dedupe store such a worker would need.
>
> The fourth, which we recommend, is to widen `indexer`'s existing surface.
>
> ## The recommendation
>
> One new service on `indexer`, `EntrySyncService` ... *(contract sketch in
> the appendix)* ... introduced in two gauge-gated increments rather than one
> migration.
>
> ## Open questions
>
> Whether the indexer team is the right owner is the first — the design
> widens their surface and their on-call load; their agreement is a
> prerequisite, not an assumption. Whether asynchronous acceptance is
> tolerable everywhere is the second; our reading of the callers says yes,
> but that reading has not been confirmed with the storefront team. And the
> drift attribution is derived from thirty days of logs, not an entry-level
> study — the gauge-gated rollout is shaped so the estimate is tested rather
> than trusted.
>
> ## Where to go from here
>
> The evidence: TICKET-98 · The execution: TICKET-101 · The gauges: TICKET-72

## What moved, move by move

| move | before | after |
| --- | --- | --- |
| 1 teach before claiming | opens with ticket metadata | opens by defining catalog, index, copying |
| 2 picture → mechanism → number | no diagram; numbers absent | quiet diagram, then the mechanism, then 4.1% |
| 3 narrative turn | none — decision asserted | "the lower path is the interesting one" reframes the question |
| 4 survey, don't dispatch | rejection table | prose, merit before weakness, recommendation last |
| 5 demote detail | RPC names and metrics inline | contract sketch referenced once, kept in an appendix |
| 6 hedge as content | no open questions | ownership, async tolerance, estimate epistemics |
| 7 cite where it teaches | inputs list up top | links appear where the reader would want them |
| 8 end with invitations | "see TICKET-101 for scope" | a closing section of outward links |

The decision content — one service, two RPCs, the same three rejected
alternatives, the same gauge-gated rollout — is unchanged. Diffing that
content is the final check before publishing any rewrite.
