# Code Comment Anti-Patterns & Simplification Taxonomy

This guide catalogs common comment smells, explains why they degrade codebase maintainability under Domain-Driven Design (DDD), and provides concrete remediation formulas to reduce line count while maximizing signal.

---

## 1. The Play-by-Play Announcer (Procedural Re-Narration)

### Symptom
Comments that provide a chronological, step-by-step narrative of what the code is doing line by line.

```rust
// Anti-Pattern:
// First, check if the input buffer has sufficient capacity.
// Then loop through each incoming packet in the batch.
// For each packet, parse the header bytes and extract the sequence ID.
// If the sequence ID is valid, push it onto our verified vector.
// Finally, return the total count of verified packets.
```

### Why It Fails
- Duplicates the code's exact executable specification.
- Creates vertical bloat that pushes crucial context off the screen.
- Inevitably drifts when a future maintainer alters the loop logic or short-circuits an edge case.

### DDD Remediation Formula
1. Verify the function and method names clearly express intent (Intention-Revealing Interface).
2. Delete the procedural walkthrough.
3. If an invariant or boundary contract exists, express it in a single concise line.

```rust
// Distilled:
// Invariant: drops malformed packet headers without interrupting batch processing.
```

---

## 2. The Redundant Signature Echo (The Echo Chamber)

### Symptom
Docstrings or doc comments that merely rephrase the name of the function, struct, or parameters without adding any new domain knowledge.

```swift
// Anti-Pattern:
/// Get the active user profile.
/// - Parameter userId: The ID of the user.
/// - Returns: The user profile object.
func getUserProfile(userId: String) -> UserProfile
```

### Why It Fails
- Adds 5 lines of vertical noise that communicates zero bits of information beyond what the compiler and type system already declare.
- Slows down code scanning and increases maintenance overhead.

### DDD Remediation Formula
- If the signature is self-describing, delete the redundant docstring or condense to a single line only if explaining domain context or side-effects.

```swift
// Distilled:
func getUserProfile(userId: String) -> UserProfile
```

---

## 3. The Apologetic Code Mask

### Symptom
Lengthy comments explaining convoluted, deeply nested, or poorly factored code instead of refactoring the code to be expressive.

```python
# Anti-Pattern:
# We need to do this weird lookup in the dictionary because sometimes the legacy
# payload comes back with 'usr_id' instead of 'user_id', and in that case we also
# have to check whether the account was migrated, because if it was, the key is
# actually in the metadata dict under 'sub_id'.
if "usr_id" in raw_payload:
    val = raw_payload.get("metadata", {}).get("sub_id") or raw_payload["usr_id"]
```

### Why It Fails
- Masks design debt with prose.
- Violates Conceptual Contours by forcing the client to navigate domain anomalies inside low-level logic.

### DDD Remediation Formula
1. Encapsulate the translation into an explicit adapter or normalized domain constructor.
2. Reduce the comment to a crisp statement of external compatibility constraint.

```python
# Distilled:
# Compatibility: handles legacy schema variants prior to 2024 migration.
user_id = normalize_legacy_identity(raw_payload)
```

---

## 4. The Drifted Algorithmic Novel

### Symptom
Multi-paragraph essays explaining how a complex algorithm was implemented years ago, referencing obsolete requirements or deleted data structures.

```rust
// Anti-Pattern:
// In the original 2021 design, we used a BTreeSet to maintain ordered timestamps.
// However, during the Q3 load testing, we noticed significant heap allocation churn,
// so we decided to switch to an array of ring buffers indexed by shard ID.
// Note that shard 0 is reserved for admin operations...
```

### Why It Fails
- Confuses current maintainers: is shard 0 still reserved? Is it still a ring buffer?
- Clutters the source file with historical git commit logs and design artifacts that belong in ADRs (Architecture Decision Records) or VCS history.

### DDD Remediation Formula
- Move historical design trade-offs to an ADR or commit message.
- Retain only the active architectural invariant and seam reference.

```rust
// Distilled:
// ADR-0012: ring-buffer shard layout optimized for zero-allocation telemetry dispatch.
```

---

## 5. The Obvious Guard Clause Echo

### Symptom
Comments above `if`, `guard`, or `match` statements that translate obvious boolean expressions into English.

```swift
// Anti-Pattern:
// Check if the user is authenticated
guard isAuthenticated else {
    // If not authenticated, return an error
    return .unauthorized
}
```

### Why It Fails
- Trivial restatement of basic programming keywords.
- Insults the intelligence of the reader and pollutes diffs.

### DDD Remediation Formula
- Delete entirely.

```swift
// Distilled:
guard isAuthenticated else { return .unauthorized }
```

---

## 6. The Decorative Divider

### Symptom
ASCII banners, lines of dashes, or asterisks separating sections of a file.

```c
// Anti-Pattern:
/*****************************************************************************
 *                     HELPER UTILITY FUNCTIONS                              *
 *****************************************************************************/
```

### Why It Fails
- High line count, zero semantic value.
- Signals poor modularization: if a file has distinct sections requiring banners, it often should be split into cohesive modules following DDD Conceptual Contours.

### DDD Remediation Formula
- Delete divider lines. Separate with standard single blank lines or factor into cohesive submodules.
