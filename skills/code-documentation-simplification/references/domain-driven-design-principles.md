# Domain-Driven Design Comment & Documentation Principles

This reference synthesizes the core principles of Eric Evans' seminal work, *Domain-Driven Design: Tackling Complexity in the Heart of Software* (2003), applied directly to the craft of code comments and in-source documentation.

---

## 1. The Core DDD Documentation Axiom

> **"First, a document shouldn’t try to do what the code already does well. The code already supplies the detail. It already is the ultimately exact specification of program behavior. It falls to other documents to illuminate meaning, to give insight into large-scale structures, and to focus attention on core elements."**
> — Eric Evans, *Domain-Driven Design*, Chapter 2: "Documents and Diagrams", p. 33

### Why Procedural Comments Fail
In Chapter 2, Evans identifies why code comments frequently degrade software quality instead of enhancing it:

1. **Inescapable Accuracy of Executable Code**: Running code and tests unambiguously execute system behavior. Comments do not affect runtime execution, so they inevitably drift out of synchronization with the active code and driving model.
2. **False Sense of Security**: Out-of-date or ambiguous comments deceive developers who rely on them without verifying the underlying code.
3. **Cognitive Overload**: Explaining *how* an algorithm steps through memory or loops over items forces the reader into procedural machine-level thinking rather than conceptual domain reasoning.

---

## 2. Intention-Revealing Interfaces (Chapter 10, pp. 172–174)

> **"If a developer must consider the implementation of a component in order to use it, the value of encapsulation is lost. If someone other than the original developer must infer the purpose of an object or operation based on its implementation, that new developer may infer a purpose that the operation or class fulfills only by chance."**
> — Eric Evans, *Domain-Driven Design*, Chapter 10: "Supple Design", p. 172

### The Pattern
Name classes, interfaces, types, functions, and arguments to describe their **effect and purpose**, without reference to the **means** by which they do what they promise:

- **State intent, not mechanism**: Describe *what* is achieved in the domain, not *how* bits are shuffled.
- **Formulate the rule, not the procedural execution**: State relationships and rules, not how they are sequentially computed.
- **Relieve the client developer**: When names conform to the **Ubiquitous Language**, client developers do not need to pierce the veil or read comments to understand how to interact with the component.

### Impact on Comments
Whenever a comment explains:
- *"This function takes X, iterates over Y, checks Z, and updates W..."*
The remedy is **not** to polish the comment. The remedy is to rename the function, parameters, and return types into an Intention-Revealing Interface, and **delete the comment completely**.

---

## 3. Assertions & Invariants (Chapter 10, pp. 179–182)

> **"State post-conditions of operations and invariants of classes and aggregates. Make side effects explicit and make state boundaries predictable."**
> — Eric Evans, *Domain-Driven Design*, Chapter 10: "Supple Design", p. 179

When a comment *is* required, its highest-value form is an **Assertion** or **Invariant**:
- **Domain Invariant**: A condition that must always remain true for a domain entity or aggregate to remain valid (e.g. `// Invariant: total volume is strictly conserved across mixing operations`).
- **Precondition / Postcondition**: What must hold before entry and what is guaranteed upon exit.
- **Hardware / OS Quirk**: Non-obvious real-world constraints that the type system cannot express (e.g. `// Invariant: backing pixel dimensions must be non-zero before native BGFX surface initialization`).
- **Seam Contract**: Architectural boundaries where payloads cross between decoupled substrates (e.g. `// Seam: raw flow packets are stripped; only minimized telemetry_event records cross into DuckDB`).

---

## 4. Side-Effect-Free Functions (Chapter 10, pp. 175–178)

> **"Place as much of the logic of the program as possible into functions, operations that return results with no observable side effects. Strictly segregate commands (resulting in modifications to observable state) into very simple operations that do not return domain information."**
> — Eric Evans, *Domain-Driven Design*, Chapter 10: "Supple Design", p. 175

Procedural comments often serve as defensive warning signs:
- *"Warning: calling this method will also mutate state in cache X and trigger notification Y."*

Under DDD Supple Design:
- Segregating commands and queries removes the need for defensive mutation warnings.
- Side-effect-free calculations on Value Objects require zero explanatory comments because their behavior is mathematically predictable and idempotent.

---

## 5. Conceptual Contours (Chapter 10, pp. 183–184)

> **"Decompose design elements into cohesive units, taking into consideration your intuition of the important divisions in the domain... Observe the axes of change and stability through successive refactorings and look for the underlying CONCEPTUAL CONTOURS."**
> — Eric Evans, *Domain-Driven Design*, Chapter 10: "Supple Design", p. 183

- Comments should never attempt to bridge fractured, poorly-decomposed classes.
- When code aligns with true domain contours, methods and modules represent single complete concepts ("Whole Values"). The need for narrative connective tissue in comments evaporates.

---

## 6. The Evans Comment Evaluation Quadrant

Every comment in the codebase belongs to one of four quadrants:

| Category | Typical Phrasing | DDD Verdict | Action |
|---|---|---|---|
| **1. The Redundant Echo** | `/// get_user - gets the user` | **Harmful Noise** | Delete immediately. |
| **2. The Procedural Re-narration** | `// First loop over items, then check flag...` | **Drift Hazard** | Delete; replace with Intention-Revealing Selectors. |
| **3. The Apologetic Explainer** | `// Hack: we do this weird math because of Foo...` | **Design Smell** | Refactor code contour; if constraint is external, distill to 1-line rationale. |
| **4. The Invariant / Seam Contract** | `// Invariant: template must be rights-cleared (ADR-0007)` | **High-Signal Asset** | Preserve and distill to maximum density. |
