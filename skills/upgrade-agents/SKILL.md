---
name: upgrade-agents
description: >-
  Audits installed or declaratively packaged coding agent programs against their
  latest upstream stable releases, scours GitHub release notes and changelogs
  across the version delta for stale or deprecated configuration keys, enforces
  maximum privacy by disabling all telemetry, analytics, crash reporting, remote
  feature beacons, and auto-updaters, and automatically enables safe local
  developer modes. Presents an audit report and proposed diff for confirmation
  before modifying packages or configurations unless immediate application is
  requested. Use when updating or hardening coding agent CLIs (such as Claude
  Code, Codex, Antigravity/AGY, Gemini CLI, OpenCode, Aider, Goose, or Copilot
  CLI), cleaning up deprecated agent settings, locking down agent privacy, or
  hunting for developer modes. Do NOT use for authoring agent system prompts,
  creating Agent Skills, or updating general project library dependencies.
argument-hint: "[agent...] [--workspace PATH] [--apply]"
license: MIT
compatibility: Requires Python 3.11+; uses authenticated gh CLI when available or GitHub REST API.
metadata:
  version: "1.0.0"
---

# Agent Program Upgrades and Hardening

Upgrade coding agent CLIs to their latest **stable** releases while keeping configuration files free of deprecated keys, completely dark on outbound telemetry/analytics, and configured with safe local developer-mode capabilities.

Resolve `<skill-dir>` from this loaded `SKILL.md` directory and run bundled helper commands against `<skill-dir>/scripts/audit_agents.py`, never assuming the current working directory is the skill directory.

---

## Core Invariants and Abstention

1. **Stable Releases Only**: Target only stable upstream releases. Reject `draft: true`, `prerelease: true`, and any tag carrying prerelease markers (`alpha`, `beta`, `rc`, `canary`, `nightly`, `preview`, `dev`, `insiders`, `snapshot`), even when tagged more recently than stable.
2. **Audit-First Confirmation Gate**: By default, execute Steps 1–4 (discovery, upstream delta audit, binary probe, and proposed diff) and **wait for explicit user confirmation** before upgrading packages or rewriting configuration files. Proceed directly to Step 5 only when the user explicitly requests immediate application (for example, passing `--apply` or stating "apply now").
3. **Respect Installation Provenance**: Upgrade each agent exclusively through the mechanism that owns it (`nix` overlay/flake, `homebrew`, `npm`/`pnpm`/`bun`, `uv`/`pipx`, `cargo`, or native vendor installer). Never run imperative self-updaters over Nix-managed, Homebrew-managed, or lockfile-pinned installations, and never overwrite an intentional local/offline stub derivation (`is_local_stub: true`) with a remote binary without explicit user instruction.
4. **Dual-Layer Privacy and Zero Telemetry**: Disable all telemetry, analytics, OpenTelemetry (`OTEL`), remote experimentation/feature-flag SDKs (`Statsig`, `GrowthBook`), crash/error reporting (`Sentry`), prompt/response/session collection, cloud memory/skill sync, satisfaction surveys, AI attribution trailers, and startup update checks across **both** persisted config files and wrapper/session environment variables where supported.
5. **Automatic Safe Dev Modes Only**: Automatically include discovered local/power-user developer modes in the proposed configuration **only** when they pass all four safety gates (zero outbound telemetry/trace upload, zero sandbox/approval regressions, concrete local capability, and target binary compatibility). Exclude and report any dev/debug mode that phones home or weakens permissions.
6. **Zero Credential Exposure**: Never print unredacted API keys, bearer tokens, webhook URLs, or credential environment values in audit reports or diffs.

---

## Workflow

### Step 1 — Inventory Installed and Declared Agents

Run local discovery (passing `--workspace "$PWD"` when operating inside a dotfiles or declarative configuration repository):

```bash
python3 "<skill-dir>/scripts/audit_agents.py" discover --workspace "$PWD"
```

To target specific built-in agents or register any arbitrary GitHub-hosted agent program, pass repeatable `--agent` flags (`--agent claude --agent custom=owner/repo:v`).

Inspect the JSON output for each discovered agent:
- `installed_binaries`: Entrypoint wrapper path, traced `payload_binary` (following symlinks, `profile-router`, and `.foo-wrapped` chains), `install_owner`, installed `version.semver`, and redacted `wrapper_env` switches. Note `delegates_to` aliases (for example, `gemini` aliasing `agy`) so aliased binaries are not misaudited against the wrong upstream repository.
- `workspace_declarations`: Declarative package files (`*.nix`, `Brewfile`, `mise.toml`, `package.json`), pinned versions, and `is_local_stub`.
- `config_files`: Active JSON/TOML/YAML configurations across `$XDG_CONFIG_HOME`, `$HOME`, and `$XDG_CONFIG_HOME/profiles/*` with secret values redacted.

### Step 2 — Scour Upstream Stable Releases and Changelogs

For each target agent, query upstream releases across the full `(installed_version, latest_stable]` range:

```bash
python3 "<skill-dir>/scripts/audit_agents.py" releases \
  --agent <agent_id> \
  --since <installed_semver> \
  --hashes
```

- Pass `--hashes` whenever declarative packages (such as Nix overlays) require per-platform `sha256-<base64>` SRI hashes (`aarch64-darwin`, `x86_64-darwin`, `x86_64-linux`, `aarch64-linux`).
- Review all four extracted changelog signal buckets (`stale_and_deprecated`, `privacy_and_telemetry`, `dev_mode_and_features`, `breaking_changes`) across **every** intermediate version since `<installed_semver>`, not merely the latest tag.
- Also check whether the release bundle added new companion binaries (such as local code-mode hosts or MCP helpers) or changed tarball layout (`sourceRoot` / archive naming).
- When release notes link to external migration docs or summarize tersely, fetch the referenced upstream documentation (`CHANGELOG.md`, `docs/`, or release PR descriptions) before finalizing conclusions.

### Step 3 — Probe Payload Binary, Privacy Baseline, and Dev-Mode Rubric

Cross-check each installed binary's CLI flags and embedded identifier strings against active user configuration:

```bash
python3 "<skill-dir>/scripts/audit_agents.py" probe-binary --agent <agent_id>
```

1. **Stale Config Triage**: Inspect `unmatched_config_keys` alongside Step 2's `stale_and_deprecated` notes. Follow [references/dev-mode-and-stale-config-rubric.md](references/dev-mode-and-stale-config-rubric.md) to distinguish removed/renamed upstream keys from legitimate local wrapper keys, and check for mutable activation merges ([Avoiding the Mutable Merge Trap](references/dev-mode-and-stale-config-rubric.md#avoiding-the-mutable-merge-trap)).
2. **Maximum Privacy Audit**: Reconcile `configured_env_switches`, `unset_privacy_env_candidates`, `cli_help.privacy_and_update_flags`, and persisted config entries against [references/privacy-and-telemetry-matrix.md](references/privacy-and-telemetry-matrix.md). Ensure every telemetry, analytics, OTEL, Statsig/GrowthBook, error-reporting, survey, cloud-memory, attribution, and auto-updater switch is explicitly disabled.
3. **Developer-Mode Hunt**: Inspect `binary_dev_env_candidates`, `cli_help.dev_and_feature_flags`, and Step 2's `dev_mode_and_features` notes. Evaluate every candidate against [The 4-Gate Dev-Mode Safety Rubric](references/dev-mode-and-stale-config-rubric.md#the-4-gate-dev-mode-safety-rubric):
   - **Pass Gates 1–4**: Include automatically in the proposed configuration changes.
   - **Fail any gate (or unverified outbound behavior)**: Exclude from changes and record in the gated findings table.

### Step 4 — Present Audit Report and Proposed Diff (Confirmation Gate)

Present a structured report covering every audited agent before making changes:

1. **Release & Provenance Summary**: Installed version → latest stable version, skipped newer prereleases (if any), owning installer/file, and verified artifact SRI hashes where applicable.
2. **Stale & Deprecated Config Plan**: File path, key/variable, evidence (release tag or binary absence), and exact removal/migration action (including activation merge cleanup if runtime files are deep-merged).
3. **Privacy & Telemetry Lockdown Delta**: Already-enforced controls vs missing/newly introduced switches to add across config files and wrapper environments.
4. **Developer-Mode Decisions**:
   - *Auto-Enabling (Safe Local/Power-User)*: Setting, capability unlocked, and gate verification.
   - *Excluded / Gated*: Setting and the specific privacy/security gate it failed.
5. **Proposed Diff / Command Plan**: Concise unified diff preview (secrets redacted) and exact upgrade/build commands.

Ask for confirmation before executing Step 5 unless immediate application was already requested.

### Step 5 — Apply, Re-Probe Upgraded Binaries, and Verify

Once confirmed:

1. **Upgrade Packages via Owning Mechanism**:
   - *Declarative (Nix overlays/flakes, lockfiles)*: Update version strings, artifact URLs/companions, and per-platform SRI hashes; run build checks (`nix flake check` or `nix build`) before activation.
   - *Package Managers*: Run the owning upgrade command (`HOMEBREW_NO_ANALYTICS=1 brew upgrade <formula>`, `npm update -g`, `uv tool upgrade`, `cargo install`, etc.).
2. **Apply Config Cleanup, Privacy Lockdowns, and Safe Dev Modes**:
   - Update declarative templates, wrapper exports, activation merge/pruning scripts, and active runtime config files across configured profiles.
3. **Post-Upgrade Binary Re-Probe**:
   - Re-run `python3 "<skill-dir>/scripts/audit_agents.py" probe-binary --agent <agent_id>` against the **newly installed** binary to catch any brand-new telemetry env vars, newly retired config keys, or new safe dev-mode switches introduced in the upgraded binary itself. Apply any delta discovered.
4. **Verification**:
   - Confirm `<agent> --version` reports the target stable version.
   - Confirm `<agent> --help` (and config validation subcommands where supported) exits cleanly with zero deprecated/unrecognized config warnings.
   - Validate modified JSON/TOML/Nix files syntactically and run repository checks when inside a declarative repo.

---

## Representative Examples

- **Default audit-first invocation**: *"Audit my installed coding agents for latest stable updates, stale config keys, full telemetry disablement, and any dev modes."* → Runs Steps 1–4 across all discovered agents, presents the per-agent report and redacted diff (auto-staging safe local dev modes and telemetry lockdowns), and waits for confirmation before modifying files.
- **Targeted immediate upgrade**: *"Upgrade codex and claude in this dotfiles repo to latest stable, strip deprecated keys, lock down new telemetry flags, enable safe dev modes, and apply."* → Audits `codex` and `claude` across `overlays/` and `modules/`, updates versions + SRI hashes + activation pruning + privacy/dev switches, re-probes upgraded binaries, and runs `nix flake check`.
- **Boundary case (prerelease + unsafe dev flag)**: Upstream publishes `v2.2.0-beta.1` above `v2.1.292` and adds both `--enable-local-inspector` (loopback-only) and `DEBUG_REMOTE_TRACES=1` (uploads trace spans). The skill targets `2.1.292` (noting `v2.2.0-beta.1` skipped), includes the safe local inspector setting, and excludes `DEBUG_REMOTE_TRACES=1` under Gate 1.
- **Out of scope**: *"Refactor my repository AGENTS.md rules"* or *"Bump FastAPI and Pydantic to latest stable"* → Do not activate; those tasks modify prompt prose or application libraries rather than coding agent programs and their runtime configurations.
