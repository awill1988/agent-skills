---
name: new-agent-skill
description: >-
  Creates and registers skills in the awill1988/agent-skills repository.
  Use when adding a reusable workflow to this collection or developing a new
  skill through an interview.
license: MIT
compatibility: Requires Python 3 and Git; validation requires uv.
---

# New Agent Skill (awill1988)

Develop a complete, locally validated skill in the user's writable collection
checkout. User instructions take precedence over this workflow. Draft creation
does not authorize commits, pushes, pull requests, or publication.

## Locate the collection

Resolve this installed skill's directory from the path supplied by the client.
Run its bundled `scripts/skill_workspace.py --help` for command usage. Resolve
script paths against that directory, not the current working directory. The
installed package supplies instructions; it is not the editable checkout.

Run `python3 <skill-directory>/scripts/skill_workspace.py locate`. On first use,
ask where `awill1988/agent-skills` is cloned, then run `configure <path>` to
validate and remember it. The helper stores `repo_path` in
`${XDG_CONFIG_HOME:-~/.config}/awill1988-agent-skills/config.json`, shared across
clients. Reuse a valid location without asking again. If the location has moved
or the configuration is invalid, ask for the replacement and run `configure`.

If no clone exists, explain `git clone https://github.com/awill1988/agent-skills.git
<destination>` and obtain the intended destination before cloning. Never use an
installed plugin cache as the editing destination or record a machine path in
tracked files. Read the checkout's applicable repository instructions.

## Define and scaffold

Establish the user's goal and a lowercase hyphenated identifier. Inspect existing
skills for overlap. Extend an existing skill when it already owns the workflow;
do not silently overwrite a name collision or create a duplicate capability.

Read [authoring guidance](references/authoring.md) when shaping the description,
instructions, and examples. Once the purpose and identifier are known, use
`scaffold <slug> --description <description> --display-name <label>
--short-description <summary>` to create `SKILL.md` and `agents/openai.yaml`.
The helper refuses to overwrite existing paths. It creates a draft, not a
finished or registered skill.

## Interview and complete

Ask only what the user has not already supplied. Adapt questions to establish:

- A representative request and the expected resulting artifact or behavior.
- Activation conditions and nearby requests that should not activate the skill.
- Required inputs, tools, environment, and facts the agent must not assume.
- Decisions requiring judgment, exact operations requiring a script, and
  conditions requiring clarification or stopping.
- Examples that demonstrate success, a boundary case, and a likely failure.

Keep each question focused on a consequential choice. Use the answers to replace
all scaffold placeholders. Write direct instructions and explicit completion
criteria. Add resources only when the task needs them, linking each from the
entrypoint with its loading condition. Keep the skill independent of this
creator once authored.

## Register and validate

Read the current catalogs and README before editing. Add exactly one Claude
entry with the stable slug, display label, accurate description, category,
keywords, `source: "./"`, and `skills: ["./skills/<slug>"]`. The root bundle
automatically includes skill directories for Codex and AGY; do not add duplicate
bundle entries. Add the skill to the README index and maintain its Codex
`agents/openai.yaml` interface.

From the checkout, run `uv run --with-requirements tools/requirements.txt python
tools/validate_collection.py`, then tests relevant to any scripts added. Resolve
format, link, and catalog failures; assess prose warnings without mechanically
adding text or splitting files. Exercise the representative examples and report
whether that verification was structural or used an actual client/model.

Finish with the completed capability, changed paths, validation evidence, and
an example invocation. Leave publication explicit.
