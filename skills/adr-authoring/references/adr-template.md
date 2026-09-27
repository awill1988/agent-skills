# Architecture Decision Record Template

Follow Michael Nygard's document structure with explicit modeling of invariants and system abstention.

---

```markdown
# [Number]. [Short title of solved problem and decision]

Date: [YYYY-MM-DD]

## Status

[Proposed | Accepted | Rejected | Deprecated | Superseded by ADR-XXXX]

## Context

What is the context and problem statement? Describe the forces at play, technical constraints, organizational requirements, and prior art without premature commitment to a solution.

## Decision

What is the change we are committing to? State the decision in clear, active voice. Identify which architectural seam or subsystem boundary owns the concept.

## Invariants & Abstention

- **System Invariants**: What properties must remain true under this decision?
- **Where We Abstain**: Under what conditions must the system explicitly refuse to act or delegate responsibility?

## Consequences

What becomes easier, what becomes harder, and what new trade-offs are introduced?

### Positive
- [Benefit 1]
- [Benefit 2]

### Negative & Operational Costs
- [Cost 1]
- [Cost 2]
```
