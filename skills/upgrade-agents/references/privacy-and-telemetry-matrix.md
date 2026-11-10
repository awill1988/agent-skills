# Privacy, Telemetry, and Analytics Lockdown Matrix

Agent CLIs commonly emit outbound network traffic before or outside model inference: OpenTelemetry (`OTEL`) traces/metrics, remote A/B feature-flag evaluations (`Statsig`, `GrowthBook`, `LaunchDarkly`), crash dumps (`Sentry`, `Bugsnag`), startup version checks, background auto-updaters, prompt/session transcript telemetry, cloud memory/skill sync, and satisfaction surveys.

Enforce privacy across **two independent layers** whenever supported by the installation method:
1. **Persisted configuration files** (`settings.json`, `config.toml`, `opencode.json`, `.aider.conf.yml`) so direct invocations of the unwrapped binary remain locked down.
2. **Process environment / wrapper exports** so SDKs initialized before configuration parsing (such as OpenTelemetry, Go runtime telemetry, or early feature-flag bootstrap) never transmit a startup beacon.

---

## Universal Environment Baseline

Apply these cross-vendor environment variables in agent wrappers or profile routers unless a specific local OTEL collector is intentionally operated by the user:

| Variable | Value | Surface Disabled |
|---|---|---|
| `DO_NOT_TRACK` | `1` | Console Do-Not-Track convention honored by modern CLI toolchains |
| `OTEL_SDK_DISABLED` | `true` | OpenTelemetry SDK initialization across Rust, Node, Go, and Python |
| `OTEL_TRACES_EXPORTER` | `none` | Fallback trace exporter suppression for partial OTEL implementations |
| `OTEL_METRICS_EXPORTER` | `none` | Fallback metrics exporter suppression |
| `OTEL_LOGS_EXPORTER` | `none` | Fallback log exporter suppression |
| `GOTELEMETRY` | `off` | Go toolchain/runtime telemetry in Go-compiled CLIs and MCP helpers |
| `NEXT_TELEMETRY_DISABLED` | `1` | Embedded Next/Vercel web UI or local dashboard bundles |

---

## Outbound Telemetry Vectors to Scour in Changelogs and Binaries

Check every release delta and `probe-binary` output against all eight categories:

1. **Usage Telemetry and Event Pipelines**: `telemetry`, `analytics`, `usageStatistics`, `runtime_metrics`, `analytics_plan_history`, `PostHog`, `Segment`, `RudderStack`.
2. **Remote Experimentation and Feature-Flag Beacons**: `Statsig`, `GrowthBook`, `LaunchDarkly`. Remote flag evaluators transmit device/account metadata on startup even when labeled "feature flags" rather than "telemetry".
3. **Crash, Exception, and Diagnostic Reporting**: `Sentry`, `Bugsnag`, `error_reporting`, `crash_report`, diagnostic bundle uploaders.
4. **Prompt, Response, and Safety-Classifier Logging**: `log_user_prompt`, `log_agent_responses`, `log_guardian_assessments`, `interactionCollection`, data-sharing / model-training opt-ins (`data_collection`).
5. **Cloud Memory, Remote Skills, and Organizational Discovery**: `autoMemory`, `memories`, `external_agent_memory_import`, `chronicle`, cloud `skills`, `remote_plugin`, `recommended_plugins`, `plugin_sharing`, `tool_suggest`, organizational MCP auto-sync (unless explicitly required by a work profile), `api_key_model_discovery`.
6. **In-Session Surveys and Feedback Prompts**: `feedback`, `surveys`, `feedbackSurveyRate`.
7. **Auto-Updaters and Startup Version Checks**: `autoUpdaterStatus`, `enableAutoUpdate`, `check_for_update_on_startup`, `in_app_updates`, background `daemon_auto_start`. Besides phoning home on every launch, self-updaters corrupt or conflict with Nix, Homebrew, and lockfile-managed installations.
8. **AI Attribution and Session Link Injection**: `attribution.commit`, `attribution.pr`, `attribution.sessionUrl`, `co-authored-by` trailers. Set commit/PR attribution strings to `""` and session URL sharing to `false`.

---

## Vendor Floor Reference

Treat the settings below as a **minimum baseline floor**, never an exhaustive ceiling. Vendors rename keys and add new telemetry surfaces across minor releases; always reconcile against live `audit_agents.py releases` and `audit_agents.py probe-binary` output.

### Claude Code (`anthropics/claude-code`)

- **Environment**:
  - `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`
  - `DISABLE_NON_ESSENTIAL_MODEL_CALLS=1`
  - `DISABLE_TELEMETRY=1`
  - `DISABLE_GROWTHBOOK=1`
  - `DISABLE_ERROR_REPORTING=1`
  - `DISABLE_AUTOUPDATER=1`
  - `DISABLE_UPDATES=1`
  - `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`
  - `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY=1`
  - `ENABLE_CLAUDEAI_MCP_SERVERS=false` (unless explicitly enabled for a corporate profile)
  - `DO_NOT_TRACK=1`, `OTEL_SDK_DISABLED=true`
- **`settings.json`**:
  - `"autoUpdaterStatus": "disabled"`, `"autoMemoryEnabled": false`, `"spinnerTipsEnabled": false`
  - `"telemetry": { "enabled": false, "analytics": false, "statsig": { "enabled": false } }`
  - `"feedback": { "prompt": false, "surveys": { "enabled": false } }`, `"feedbackSurveyRate": 0`
  - `"attribution": { "commit": "", "pr": "", "sessionUrl": false }`

### OpenAI Codex CLI (`openai/codex`)

- **Environment**:
  - `CODEX_DISABLE_TELEMETRY=1`
  - `CODEX_DISABLE_AUTO_UPDATE=1`
  - `CODEX_DISABLE_UPDATE_CHECK=1`
  - `DO_NOT_TRACK=1`, `OTEL_SDK_DISABLED=true`
- **`config.toml`**:
  - Top-level: `check_for_update_on_startup = false`
  - `[analytics]`: `enabled = false`
  - `[feedback]`: `enabled = false`
  - `[otel]`: `exporter = "none"`, `trace_exporter = "none"`, `metrics_exporter = "none"`, `log_user_prompt = false`, `log_agent_responses = false`, `log_guardian_assessments = false`
  - `[cloud]`: `skills = { enabled = false }`
  - `[memories]`: `generate_memories = false`, `use_memories = false`, `dedicated_tools = false`, `disable_on_external_context = true`
  - `[features]`: set cloud/telemetry/sync flags (`apps`, `plugins`, `remote_plugin`, `plugin_sharing`, `recommended_plugins`, `tool_suggest`, `skill_search`, `skill_mcp_dependency_install`, `in_app_updates`, `memories`, `external_agent_memory_import`, `chronicle`, `analytics_plan_history`, `api_key_model_discovery`, `runtime_metrics`, `daemon_auto_start`) to `false` unless explicitly requested by the user and verified supported in the target binary.

### Google Antigravity CLI (`google-antigravity/antigravity-cli`)

- **Environment**:
  - `AGY_TELEMETRY_ENABLED=false`
  - `ANTIGRAVITY_TELEMETRY_ENABLED=false`
  - `ANTIGRAVITY_DATA_COLLECTION=opt-out`
  - `AGY_CLI_DISABLE_TELEMETRY=true`
  - `AGY_CLI_DISABLE_UPDATE_CHECK=true`
  - `GOTELEMETRY=off`, `DO_NOT_TRACK=1`, `OTEL_SDK_DISABLED=true`
- **`settings.json`**:
  - `"privacy": { "enableTelemetry": false, "interactionCollection": "off", "usageStatisticsEnabled": false, "telemetry": false }`
  - `"general": { "enableAutoUpdate": false, "enableNotifications": false }`

### Gemini CLI (`google-gemini/gemini-cli`)

- **Environment**: `GEMINI_TELEMETRY_ENABLED=false`, `DO_NOT_TRACK=1`, `OTEL_SDK_DISABLED=true`
- **`settings.json`**: `"telemetry": { "enabled": false, "logPrompts": false }`, `"privacy": { "usageStatisticsEnabled": false }`, `"general": { "disableAutoUpdate": true, "disableUpdateNag": true }`

### OpenCode (`sst/opencode`)

- **Environment**: `OPENCODE_TELEMETRY_ENABLED=false`, `OPENCODE_DISABLE_AUTO_UPDATE=1`, `DO_NOT_TRACK=1`, `OTEL_SDK_DISABLED=true`
- **`opencode.json`**: `"autoupdate": false` / `"general": { "enableAutoUpdate": false }`, `"share": "disabled"`, `"telemetry": { "enabled": false }`

### Aider (`Aider-AI/aider`)

- **Environment**: `AIDER_ANALYTICS=false`, `AIDER_CHECK_UPDATE=false`, `AIDER_ATTRIBUTE_AUTHOR=false`, `AIDER_ATTRIBUTE_COMMITTER=false`, `AIDER_ATTRIBUTE_CO_AUTHORED_BY=false`
- **`.aider.conf.yml` / CLI flags**: `analytics: false`, `analytics-disable: true`, `check-update: false`, `attribute-author: false`, `attribute-committer: false`, and `--no-attribute-co-authored-by`
