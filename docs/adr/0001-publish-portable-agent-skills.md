# 0001. Publish a portable skill collection from GitHub

Date: 2026-10-12

## Status

Proposed. Accept through review of the publication PR.

## Context

The collection must install in Claude Code, Codex, and Antigravity from one
public repository. Skill instructions share a portable format, while discovery
metadata and plugin installation differ across clients. Contributors also need
a writable checkout distinct from an installed plugin's cached files.

Local marketplace registration configures one client; it does not publish the
collection. Official provider directories have separate submission processes.
The installation experience belongs in [README.md](../../README.md), while this
record owns the distribution choice and its release procedure.

## Decision

Publish the collection through `awill1988/agent-skills` on GitHub. Merge reviewed
changes to `main` to update the source used by the README installation commands.
Tags and GitHub releases are optional; no registry upload is required.

| Client | Package | Discovery |
|---|---|---|
| Claude Code | `.claude-plugin/marketplace.json`, one package per skill | Display name, description, category, keywords, and explicit skill path |
| Codex | `.agents/plugins/marketplace.json`, one root bundle | Catalog label and category; individual `agents/openai.yaml` interfaces |
| AGY | Root `plugin.json` and `skills/` bundle | Package description and individual skill descriptions |

Keep the shared manifest limited to `name` and `description`. Keep stable skill
identifiers and client-specific fields in their respective discovery surfaces.
The marketplace identifier is `awill1988-agent-skills`; the README documents
migration from `agent-skills`.

The `new-agent-skill` workflow authors in a separate writable clone. Its helper
stores the clone's absolute path in a user-local JSON configuration under
`${XDG_CONFIG_HOME:-~/.config}/awill1988-agent-skills/`. All three clients use
that file. This is machine configuration, not tracked skill content or a promise
of persistence through provider-managed memory.

Use the existing Python tooling for deterministic package validation and
scaffolding. Bundle the creator's portable helper with the skill so installation
does not require repository tooling merely to locate or scaffold a checkout.

## Invariants and abstention

- An individual Claude package exposes exactly its named skill. Both root
  bundles expose every skill in the collection exactly once.
- Packaged references resolve within each skill; authoring never edits an
  installation cache or overwrites an existing skill directory.
- Descriptions and invocation prompts accurately identify the workflow.
  Format errors block validation; prose length and style are review guidance.
- Skill creation ends at a validated local draft. It does not authorize git
  publication, directory submissions, or account configuration changes.
- A missing or invalid remembered checkout requires a replacement location.
  Do not guess a destination or silently change the user's clone.
- Publish only reviewed changes with passing verification. Obtain explicit
  merge approval; never force a rejected push or push directly to `main`.

## Consequences

Users install from one repository without a separate package registry or release
artifact. Provider-specific catalogs preserve native discovery and allow Claude
users to choose individual skills. The creator has a consistent setup across
clients without depending on their separate memory systems.

Catalogs and display metadata must stay synchronized. Clients may cache installs
and require refresh or restart. GitHub availability and client compatibility
remain installation dependencies. User-local configuration must be repaired
when a checkout moves. Official directory discovery is not provided by this
distribution decision.

## Release procedure

1. Prepare one feature-branch PR containing skills, catalogs, metadata, and
   user-facing migration instructions. Review new files for local paths and
   credentials. Preserve skill identifiers across revisions.
2. Run the commands in the README contributing section and `git diff --check`.
   Resolve validation errors and assess authoring warnings.
3. Run `claude plugin validate --strict .` and `agy plugin validate .` with
   supported clients. Inspect output as well as exit codes. Record versions.
4. Install the reviewed branch from GitHub in isolated client configurations.
   Verify the expected skill inventories and README invocation syntax. Keep
   discovery checks separate from model-backed behavior tests, and report
   untested behavior explicitly. Do not alter live maintainer installations.
5. Verify `git branch --show-current`, then use plain `git push` and open the
   PR. Require passing checks and explicit approval before merging to `main`.
6. After merge, repeat installation and discovery against `main`. If a named
   release is desired, choose its version and reviewed revision deliberately;
   do not equate marketplace metadata versions with individual skill versions.

## CI gates

`collection-validation.yml` runs on relevant pull requests, including drafts,
and on pushes to `main`. It validates YAML and JSON, discovery interfaces,
catalog coverage, packaged file links, Markdown heading fragments, and completed
scaffolds. It runs creator, validator, reviewer, and comment-scanner tests with
read-only repository permissions and no model credentials.

`skill-review.yml` remains a separate model-backed review on non-draft PRs.
Deterministic checks are lint, not review. Missing or failed model execution
cannot produce an approval; incomplete model review fails that job. Its style
guidance is advisory; format and broken-reference findings remain actionable.
Client installation checks are release verification, not currently
automated CI. Configuring branch protection is a repository administration step;
the existence of workflows alone does not enforce it.

## Official directories

Submit to official Claude, Codex, or AGY directories separately after verifying
their current publisher requirements. Record the submitted revision, listing
URL, and review result. Do not claim directory availability before acceptance.

## References

- [Agent Skills specification](https://agentskills.io/specification)
- [Claude marketplace reference](https://code.claude.com/docs/en/plugins/marketplace-reference)
- [Codex plugin packaging](https://developers.openai.com/plugins/build/plugins)
- [AGY plugin packaging](https://antigravity.google/docs/plugins)
