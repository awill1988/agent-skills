---
name: adr-authoring
description: >-
  Guides the authoring and review of Architecture Decision Records (ADRs) following
  Michael Nygard's format. Enforces documenting forces, decision rationale, invariants,
  consequences, and explicit conditions where the system must abstain from acting.
  Use when proposing architectural changes, seam modifications, or evaluating technology trade-offs.
license: MIT
metadata:
  version: 1.0.0
---

# Architecture Decision Record (ADR) Authoring

Architecture Decision Records capture significant architectural choices along with their context, trade-offs, and invariants. An ADR serves as immutable historical rationale for future maintainers who were not present when the trade-off was negotiated.

---

## When to Write an ADR

Author an ADR whenever a change:
1. Crosses a major architectural seam or boundary.
2. Introduces, replaces, or deprecates a core technology, framework, or persistence engine.
3. Establishes a system-wide invariant that must be protected against local optimizations.
4. Dictates conditions where the system must explicitly abstain from acting.

Do **not** write an ADR for routine bug fixes, internal refactorings within an existing component, or formatting adjustments.

---

## Structure of an ADR

Every ADR must follow the standardized structure outlined in [references/adr-template.md](references/adr-template.md):

1. **Title**: Sequenced number and active decision phrase (e.g. `0018-duckdb-minimized-telemetry-storage.md`).
2. **Status**: `Proposed`, `Accepted`, `Rejected`, `Deprecated`, or `Superseded`.
3. **Context**: The forces, technical constraints, and motivation. Must not jump directly to the solution.
4. **Decision**: The active, authoritative statement of what will be done and which architectural layer owns the concept.
5. **Invariants & Abstention**:
   - **Invariants**: What system properties must remain true under all circumstances.
   - **Abstention**: Explicit definition of when and where the system must refuse to act or abstain from automated behavior.
6. **Consequences**: Balanced ledger of positive benefits and negative operational costs.

---

## Authoring Workflow

1. **Identify the Decision Scope**: Frame the specific architectural question or tension requiring resolution.
2. **Draft the Document**: Populate each section using [references/adr-template.md](references/adr-template.md).
3. **Verify Abstention Modeling**: Ensure non-action or boundary abstentions are explicitly documented.
4. **Commit with Conventional Commit**: Use `docs: adr-XXXX — <decision summary>` with zero AI attribution.
