# Decision boundaries

| Scenario | Record choice | Reason |
|---|---|---|
| A shared text-replacement library serves a current editor extension. Research explores a future network proxy using the same library. | One ADR for the shared core, with deferred proxy research subordinate to the decision. | The research informs the boundary; it does not approve deploying privileged interception. |
| A later proposal chooses privileged interception, certificate trust, and platform enforcement for that proxy. | A separate ADR linked to the shared-core record. | The deployment choice can be rejected or superseded while retaining the shared library. |
| An implemented architecture is replaced with a different ownership boundary. | A new ADR superseding the established decision, with links in both directions. | Maintainers need the original rationale to interpret code and operational history. |

When consolidating developing records, retain the decision, constraints,
alternatives, evidence, and unresolved questions in the surviving record.
Repair references to the removed paths. If a record has already been relied on,
preserve its historical identity instead of treating it as a disposable draft.
