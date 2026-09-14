---
name: publishing-docs
description: >-
  Steers the writing of technical documentation that is about to be published —
  design docs, decision records, RFCs, architecture pages, proposals headed for
  a wiki or a review audience. Restructures a draft into a register that
  teaches: define terms before using them, survey alternatives fairly, hedge
  what is unproven, and demote detail to appendices. Use before publishing,
  posting, or substantially rewriting any document that people beyond the
  implementers will read. Do NOT use for code comments, commit messages, API
  reference generation, changelogs, or chat replies.
license: MIT
metadata:
  version: 1.0.0
---

# Publishing technical documentation

A published document outlives the conversation that produced it, and most of
its readers were not in that conversation. They arrive cold: they do not know
the system's vocabulary, they were not present for the alternatives, and they
cannot ask a follow-up question. The people who approve and fund work read this
way. So the register for a published document is the register of a good
textbook introduction: **summarize, introduce, invite.**

Three verbs, three duties. *Summarize* the terrain so the reader can hold it.
*Introduce* every concept before it is used. *Invite* the reader onward — into
an appendix, a linked evidence page, an executing ticket — instead of forcing
everything inline.

Two failure modes sit on either side of this register, and both read as
disrespect for the reader's time. The **spec** buries the reader in decision
tables and citations before they know what the system is. The **pitch**
compresses everything into a named-enemy headline and bullet points, which
demonstrates confidence but teaches nothing. Condensing and teaching are
different operations. When a draft is too long, the correction is not
compression — it is reordering the material so that each sentence lands on a
reader who is prepared for it.

## First, identify the audience

If the only readers are the implementers on the same team, a spec is the right
form; stop here and publish the spec. This skill applies when the document
travels — to leadership, to an adjacent team, to a future reader deciding
whether the design still holds. When in doubt, assume it travels: documents
outlive their intended distribution.

## The eight moves

Apply them in order against the draft. Each is a transformation, not a
checklist item — a draft usually needs three or four of them, not all eight.

**1. Teach before claiming.** Open by defining the domain terms the reader
needs, in plain declarative sentences, before making any claim that depends on
them. Deliverable metadata — ticket links, "as of" dates, the document's own
status — comes second, phrased as reader guidance ("readers who want the full
evidence will find it in...") rather than decree.

**2. Picture, then mechanism, then number.** Offer a diagram early, as an aid
("it may help to begin with a picture"), and keep it quiet: shape only. No
rates, verdicts, checkmarks, or per-path judgments baked into the art — the
prose carries judgment. Then narrate the causal mechanism in prose. Only after
the mechanism is understood do the headline figures land; a number presented
before its mechanism is decoration, after it is evidence.

```
  producer ──► sync worker ──┬──► primary store
                             └──► derived store
```

**3. Find the narrative turn.** Somewhere in the material is one observation
that reframes the question — the existing component that already solves the
hard part, the constraint that eliminates half the option space. Name it
explicitly ("the lower path is the interesting one") and let the
recommendation hang off it. A document with a turn reads as discovery; one
without reads as advocacy.

**4. Survey, don't dispatch.** Present alternatives as prose paragraphs, each
granted its genuine merit *before* its weakness ("this keeps every change
small and reviewable... its weakness appears in the aggregate"). Order them so
the recommendation arrives as the survey's natural last step. The reasoning
should produce the decision; a decision followed by a rejection table reads as
a verdict with the trial held elsewhere.

**5. Demote detail.** Schemas, contract sketches, key derivations, and
source-verified citations go to one appendix, referenced once from the body.
Metrics and inventories that live in another document stay there — link, never
restate. A reader who wants the detail follows the invitation; a reader who
does not is never made to scroll past it.

**6. Hedge as content.** A dedicated open-questions section, framed as
questions the authors would rather name than paper over. Name the
prerequisites that are actually someone else's agreement, the assumptions that
have not been verified (and who would verify them), the placements still
unsettled, and the epistemics of the key figures — where an estimate came from
and how the plan tests it rather than trusts it. Confidence is not a virtue in
a published document; falsifiability is.

**7. Cite only where it teaches.** Keep a citation where its analogy or
principle does work at the point of use; delete the ones that exist to lend
authority. A page-numbered citation on every section header is decoration. Two
citations that each carry an idea are scholarship.

**8. End with invitations.** Close with where to go from here — evidence,
execution, neighboring work — as links outward. No closing summary; a reader
who reached the end just read the summary.

## When rewriting an existing document

A rewrite for audience must be verifiably substance-preserving. Before
publishing, diff the decision content of old against new: the same components,
the same contracts, the same scopes, the same outbound links. Every change
should be rhetorical. If the diff shows a decision changed, that is a revision
wearing a rewrite's clothes — split it out and say so.

Rewrite in the document's original tense, as if it had always been written
this way. No storytelling about prior drafts, no "previously this page said" —
version history already records that.

## The mechanical floor

Independent of register, before publishing:

- Wrap developer-facing literals in backticks: paths, identifiers, flags,
  config keys, resource names, environment variables.
- Section headings must read cleanly in a table of contents — terse noun
  phrases a reader can navigate by.
- No time estimates or scheduling adjectives; communicate scope in terms of
  components touched and invariants protected.
- No attribution to any tool or assistant, anywhere in the document or its
  version messages.
- Validate that markdown-sensitive characters in generated content are escaped
  for the target renderer before posting.

A worked before/after showing the moves applied to one document:
[`references/example-rewrite.md`](references/example-rewrite.md).

## Troubleshooting

**The draft resists the register** — it may genuinely be a spec. If every
reader is an implementer, publish the spec and skip the transformation.

**The rewrite keeps getting longer** — moves 1–4 add prose; moves 5 and 8
remove it. If length grows, detail is not being demoted, only introduced.

**No narrative turn exists** — then the document is a status report, not a
decision, and it should say so plainly instead of manufacturing a pivot.

**The open-questions section is empty** — it is not. An unproven assumption is
always present; an empty hedge section means the confident answers were left
in the body.
