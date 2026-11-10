# Stale Configuration Purge and Developer-Mode Evaluation Rubric

## 1. Stale and Deprecated Configuration Detection

Agent CLIs evolve their configuration schemas rapidly. Deprecated keys fall into three failure modes:
1. **Strict parser failure or startup warning**: Tools with typed deserializers (such as Rust `serde` in Codex or strict JSON Schema validators) emit warnings or abort when encountering removed keys (for example, retired `[features]` entries or moved `[tools.*]` keys).
2. **Silent no-op drift**: Renamed privacy or permission keys silently stop applying while giving the appearance of enforcement.
3. **Conflicting legacy/modern pairs**: Setting both a deprecated boolean and its replacement enum produces undefined precedence.

### Triaging Candidates from `probe-binary` and Changelogs

`audit_agents.py probe-binary` flags configured schema keys whose leaf identifiers do not appear in the payload binary's string table (`unmatched_config_keys`), and `audit_agents.py releases` extracts deprecation/removal notes across the version delta. Before removing a flagged key, classify it:

| Classification | Evidence | Action |
|---|---|---|
| **Confirmed Removed** | Release notes / `CHANGELOG.md` state removal, OR binary `--help` / startup emits unrecognized-key warning, OR key is absent from payload strings and upstream schema | **Delete** from config templates and active runtime files. |
| **Renamed / Migrated** | Changelog or docs specify replacement key, section, or enum value | **Migrate** value to the replacement key and delete the old key. |
| **Wrapper-Consumed Key** | Key is read by a local wrapper script, profile router, or external tool rather than the upstream binary | **Preserve** and note its local consumer in the audit report. |
| **Multi-Version Compatibility Floor** | Vendor changed key name across machines sharing dotfiles on temporarily skewed versions, and the binary accepts unknown keys silently | Keep both only while versions are skewed; schedule removal once all hosts upgrade. |

### Avoiding the Mutable Merge Trap

Many dotfile and profile-routing setups seed mutable runtime configuration files (`$XDG_CONFIG_HOME/<agent>/settings.json` or `config.toml`) by deep-merging a declarative template onto the existing file during activation (for example, `jq -s '.[0] * .[1]'` or `sed` append blocks).

**Invariant**: Deleting a stale key solely from the declarative template does **not** remove it from an already-materialized mutable runtime file; the merge preserves `.[0]`'s stale key forever.

When purging a stale key in an environment with mutable merge scripts:
1. Remove the key from the declarative source (`settings.json` generator, `config.toml` template, Nix module, chezmoi template).
2. Add or update explicit pruning in the activation/merge step (such as `| del(.obsoleteKey)` in `jq` or targeted `sed` deletion in TOML) so existing profile and base configs self-heal on activation.
3. Prune the key from live mutable config files across active profiles after user confirmation.

---

## 2. Scouring and Classifying Developer Modes (`dev mode`)

Vendors ship power-user, developer, and inspection capabilities across four surfaces:
- **Feature tables and config toggles**: `[features]` entries (such as `code_mode_host = true`), MCP server developer presets (`--toolPreset developer`), higher local output token ceilings, or local/offline execution modes.
- **CLI flags**: `--dev`, `--enable <feature>`, `--inspector`, `--mcp-debug`, `--verbose` (local stderr only).
- **Environment switches**: `*_DEV_MODE`, `*_MISSION_CONTROL`, `*_AGENT`, `*_CODE_MODE*`, `*_EXPERIMENTAL_*`, UI chrome/animation disablement (`*_ANIMATIONS_DISABLED`, `prefersReducedMotion = true`, `showSpinner = false`, `CLAUDE_CODE_DISABLE_PROACTIVITY=1`).
- **Companion binaries in release bundles**: Package tarballs occasionally ship new companion binaries alongside the main CLI (such as local code-mode hosts or local MCP bridges) that require symlink/PATH exposure when upgrading declarative packages.

### The 4-Gate Dev-Mode Safety Rubric

Evaluate every discovered developer mode, experimental feature flag, or power-user toggle through all four gates in order:

1. **Gate 1 — Zero Outbound Telemetry or Remote Trace Export**:
   - *Fail if*: Enabling the mode activates cloud trace uploads, remote debug logging, session URL sharing, crash dump transmission, or third-party cloud sandboxes.
2. **Gate 2 — Zero Security, Sandbox, or Approval Regressions**:
   - *Fail if*: Enabling the mode bypasses command/tool approval policies (`--dangerously-skip-permissions`, `yolo`), weakens filesystem/network sandbox isolation beyond the user's configured policy, disables TLS certificate verification, or binds an unauthenticated network listener beyond `127.0.0.1`.
3. **Gate 3 — Concrete Local Developer Ergonomics or Capability**:
   - *Pass if*: The toggle unlocks local execution capabilities (such as local code-mode host execution, developer tool presets for local MCP servers, subagent/orchestration control surfaces, deterministic reduced-motion/no-animation terminal rendering, or higher local output limits) without violating Gates 1 or 2.
4. **Gate 4 — Binary Compatibility**:
   - *Pass if*: The target stable binary recognizes the flag/setting cleanly without startup errors or deprecation warnings.

### Disposition Rule

- **Auto-Enable (include in proposed configuration changes)**: Modes passing **all four gates** (Gates 1–4). Document each auto-enabled setting, what it unlocks, and why it passed the privacy/security check in the audit report.
- **Gate / Exclude (do NOT enable; report only)**: Modes failing Gate 1, Gate 2, or Gate 4, or modes whose outbound network behavior cannot be verified from release docs/source/binary inspection. List them in a separate **Excluded / Gated Dev Modes** table in the audit report with the specific failed gate so the user has full visibility without silent exposure.
