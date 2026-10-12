# Authoring a portable skill

## Purpose and discovery

Start with a recognizable user goal. Describe the capability and its activation
conditions before implementation details. Use task vocabulary and a concise
third-person description; avoid attracting unrelated requests through broad
keywords. Front-load the distinguishing information because clients may shorten
descriptions. Keep the stable slug separate from a friendly display label.

## Instructions

Write direct actions, explain non-obvious rationale, and use one term for each
concept. Define expected inputs, outputs, decisions, and completion criteria.
Keep judgment flexible where multiple approaches work. Use exact commands or
scripts where ordering and deterministic behavior matter. Do not repeat generic
advice the agent already knows or manufacture approval gates.

Explicit user instructions govern the task. A skill does not expand the user's
authorization or silently change the requested outcome. Interview only for
missing consequential information; reuse answers already in the conversation.

## References and anchors

Keep essential instructions in `SKILL.md`. Link optional material directly from
it with a condition and purpose, such as: “For an existing skill, read
[Updating an existing skill](#updating-an-existing-skill).” Use meaningful,
stable headings and relative paths. Resolve links in supporting documents from
the document containing the link. Keep packaged dependencies inside the skill.

Markdown fragments identify sections for navigation; they are not automatic
imports or a guarantee that only a section enters context. Our validator uses
GitHub-compatible heading slugs, including suffixes for duplicate headings.
Prefer ordinary headings over custom HTML anchors. Include a contents section
when a reference becomes difficult to navigate; do not split a coherent decision
solely to meet a file or word target.

## Resources and examples

Start with instructions. Add `references/` for conditional detail, `assets/`
for output templates, and `scripts/` for deterministic work. Do not create empty
directories. Scripts should document dependencies, offer useful `--help`, and
return concise results and actionable failures. Use provider-neutral resource
paths; client-specific substitution variables are not portable contracts.

Include examples that change an author's understanding: an ordinary request,
a nearby request outside scope, and a failure or boundary case. Test both
discovery and results. A valid YAML file does not establish behavioral quality.

## Updating an existing skill

Inspect its actual callers, resources, and examples. Preserve its identifier
and unrelated behavior. Extend the owner of the workflow instead of producing
a competing skill. Separate workflows only when their triggers, inputs, or
success criteria differ materially. Refine based on observed failures rather
than accumulating speculative universal rules.

## Format and client conventions

The shared format requires a matching lowercase hyphenated `name` and a
nonempty `description` no longer than 1,024 characters. Optional `metadata`
contains string values. Length recommendations are review guidance, not parser
limits. This collection warns above 500 entrypoint lines; it does not demand a
minimum description length or a percentage reduction in prose.

Claude discovery keywords belong in its catalog. Codex display metadata belongs
in `agents/openai.yaml`. Preserve recognized extensions such as `argument-hint`
without presenting them as universal fields. Do not invent top-level `tags` or
rely on client memory to locate the user's editable repository.

## Sources

Reviewed 2026-10-12. These are authoring references, not instructions to fetch
every source on every invocation. Recheck the relevant provider when changing
a client-specific contract.

- [Agent Skills specification](https://agentskills.io/specification): format and resource conventions.
- [OpenAI skill authoring](https://developers.openai.com/plugins/build/skills): workflow boundaries and supporting resources.
- [Codex discovery](https://learn.chatgpt.com/docs/build-skills): descriptions and invocation.
- [OpenAI skill evaluations](https://developers.openai.com/blog/eval-skills): discovery and outcome testing.
- [Anthropic authoring guidance](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices): specificity, examples, and shallow references.
- [Claude Code extensions](https://code.claude.com/docs/en/skills): client-specific fields and substitutions.
- [Google Antigravity skills](https://antigravity.google/docs/skills): focused skills and discovery.
- [Gemini CLI authoring guidance](https://geminicli.com/docs/cli/skills-best-practices/): procedural detail and script interfaces.
