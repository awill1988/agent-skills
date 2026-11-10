#!/usr/bin/env python3
"""Audit coding agent installations, upstream stable releases, configs, privacy switches, and dev modes."""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    display_name: str
    binaries: tuple[str, ...]
    repo: str
    tag_prefix: str = "v"
    changelog_paths: tuple[str, ...] = ("CHANGELOG.md",)
    xdg_config_relpaths: tuple[str, ...] = ()
    home_config_relpaths: tuple[str, ...] = ()
    profile_subdir: str = ""


KNOWN_AGENTS: dict[str, AgentSpec] = {
    "agy": AgentSpec(
        agent_id="agy",
        display_name="Google Antigravity CLI",
        binaries=("agy",),
        repo="google-antigravity/antigravity-cli",
        tag_prefix="",
        xdg_config_relpaths=(
            "antigravity/settings.json",
            "antigravity-restricted/settings.json",
        ),
        home_config_relpaths=(".gemini/antigravity-cli/settings.json",),
        profile_subdir="antigravity",
    ),
    "claude": AgentSpec(
        agent_id="claude",
        display_name="Claude Code CLI",
        binaries=("claude", "claude-secondary"),
        repo="anthropics/claude-code",
        tag_prefix="v",
        changelog_paths=("CHANGELOG.md",),
        xdg_config_relpaths=(
            "claude/settings.json",
            "claude/.claude.json",
            "claude-secondary/settings.json",
            "claude-secondary/.claude.json",
        ),
        home_config_relpaths=(".claude/settings.json", ".claude.json"),
        profile_subdir="claude",
    ),
    "codex": AgentSpec(
        agent_id="codex",
        display_name="OpenAI Codex CLI",
        binaries=("codex",),
        repo="openai/codex",
        tag_prefix="rust-v",
        changelog_paths=("CHANGELOG.md",),
        xdg_config_relpaths=("codex/config.toml",),
        home_config_relpaths=(".codex/config.toml",),
        profile_subdir="codex",
    ),
    "gemini": AgentSpec(
        agent_id="gemini",
        display_name="Gemini CLI",
        binaries=("gemini",),
        repo="google-gemini/gemini-cli",
        tag_prefix="v",
        changelog_paths=("CHANGELOG.md",),
        xdg_config_relpaths=("gemini/settings.json",),
        home_config_relpaths=(".gemini/settings.json",),
        profile_subdir="gemini",
    ),
    "opencode": AgentSpec(
        agent_id="opencode",
        display_name="OpenCode CLI",
        binaries=("opencode",),
        repo="sst/opencode",
        tag_prefix="v",
        changelog_paths=("CHANGELOG.md",),
        xdg_config_relpaths=("opencode/opencode.json", "opencode/config.json"),
        home_config_relpaths=(".opencode/opencode.json",),
        profile_subdir="opencode",
    ),
    "aider": AgentSpec(
        agent_id="aider",
        display_name="Aider CLI",
        binaries=("aider",),
        repo="Aider-AI/aider",
        tag_prefix="v",
        changelog_paths=("aider/website/HISTORY.md", "HISTORY.md", "CHANGELOG.md"),
        xdg_config_relpaths=("aider/.aider.conf.yml",),
        home_config_relpaths=(".aider.conf.yml",),
        profile_subdir="aider",
    ),
    "goose": AgentSpec(
        agent_id="goose",
        display_name="Block Goose CLI",
        binaries=("goose",),
        repo="block/goose",
        tag_prefix="v",
        xdg_config_relpaths=("goose/config.yaml",),
        profile_subdir="goose",
    ),
    "copilot": AgentSpec(
        agent_id="copilot",
        display_name="GitHub Copilot CLI",
        binaries=("copilot", "github-copilot-cli"),
        repo="github/copilot-cli",
        tag_prefix="v",
        xdg_config_relpaths=("github-copilot/config.json",),
        profile_subdir="copilot",
    ),
}

PRERELEASE_TOKEN_RE = re.compile(
    r"(?:^|[-._+])(alpha|beta|rc|dev|nightly|canary|preview|insiders|pre|snapshot|experimental)(?:[-._+\d]|$)",
    re.IGNORECASE,
)
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$")
VERSION_EXTRACT_RE = re.compile(r"\b(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\b")

SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|credential|auth[_-]?header|bearer|"
    r"private[_-]?key|client[_-]?secret|webhook|dsn|connection[_-]?string|session[_-]?key)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"^(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"AIza[0-9A-Za-z_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|https?://[^/\s:@]+:[^/\s@]+@)",
)

ENV_PRIVACY_RE = re.compile(
    r"(TELEMETRY|OTEL|ANALYTICS|STATSIG|GROWTHBOOK|SENTRY|POSTHOG|SEGMENT|DATADOG|"
    r"ERROR_REPORTING|CRASH|BUGSNAG|DO_NOT_TRACK|SURVEY|FEEDBACK|NONESSENTIAL|"
    r"NON_ESSENTIAL|AUTO_?UPDATE|UPDATE_CHECK|UPDATES|AUTO_?MEMORY|DATA_COLLECTION|"
    r"OFFLINE|ATTRIBUTION|PROACTIVITY|GOTELEMETRY)",
    re.IGNORECASE,
)
ENV_DEV_RE = re.compile(
    r"(DEV_MODE|DEVELOPER|DEBUG|EXPERIMENTAL|INSPECTOR|CODE_MODE|MISSION_CONTROL|"
    r"INTERNAL|UNSAFE|TRACE|PROFILE|SANDBOX|FEATURE)",
    re.IGNORECASE,
)

CHANGELOG_STALE_RE = re.compile(
    r"\b(deprecat\w*|remov\w*|renam\w*|obsolet\w*|drop\w*|retir\w*|legacy|migrated?|"
    r"replaced\s+by|no\s+longer\s+supported|unrecognized|invalid\s+config)\b",
    re.IGNORECASE,
)
CHANGELOG_PRIVACY_RE = re.compile(
    r"\b(telemetry|analytics|otel|opentelemetry|statsig|growthbook|sentry|posthog|"
    r"privacy|data\s+collection|opt[- ]?out|opt[- ]?in|tracking|do_not_track|"
    r"crash\s+report\w*|error\s+report\w*|survey\w*|feedback|auto[- ]?memory|"
    r"cloud\s+sync|auto[- ]?updat\w*|attribution|co-authored-by|usage\s+stat\w*)\b",
    re.IGNORECASE,
)
CHANGELOG_DEV_RE = re.compile(
    r"\b(dev\s+mode|developer\s+mode|--dev\b|debug\s+mode|inspector|code[-_ ]mode|"
    r"experimental|feature\s+flag\w*|power[- ]user|headless|local[- ]only|offline\s+mode|"
    r"toolpreset)\b",
    re.IGNORECASE,
)
CHANGELOG_BREAKING_RE = re.compile(
    r"(\bbreaking\b|!:|\bbackwards?[- ]incompatible\b|\bpermission\w*\s+change|\bsandbox\b)",
    re.IGNORECASE,
)

# Map containers whose immediate child keys are user-named identifiers (paths, server IDs)
# rather than fixed upstream configuration schema properties.
USER_NAMED_CONTAINERS = frozenset({
    "mcpServers",
    "mcp_servers",
    "projects",
    "providerOptions",
    "profiles",
    "env",
    "sessionEnv",
    "enabledPlugins",
    "model_migrations",
    "model_availability_nux",
})


def redact_value(key_path: str, value: object) -> object:
    """Redact sensitive scalar values while preserving booleans, numbers, and safe enums."""
    leaf = key_path.rsplit(".", 1)[-1]
    if SECRET_KEY_RE.search(leaf):
        if isinstance(value, bool):
            return value
        return "<REDACTED>"
    if isinstance(value, str):
        stripped = value.strip()
        if SECRET_VALUE_RE.match(stripped):
            return "<REDACTED>"
        if len(stripped) > 40 and re.fullmatch(r"[A-Za-z0-9+/=_-]+", stripped):
            return "<REDACTED>"
    return value


def flatten_config(node: object, prefix: str = "", skip_schema_at_next: bool = False) -> list[dict[str, object]]:
    """Flatten nested dict structures into redacted key/value entries with schema-check hints."""
    entries: list[dict[str, object]] = []
    if isinstance(node, dict):
        for raw_key, child in node.items():
            key = str(raw_key)
            dotted = f"{prefix}.{key}" if prefix else key
            is_user_key = skip_schema_at_next
            next_skip = key in USER_NAMED_CONTAINERS
            if isinstance(child, dict):
                if not child:
                    entries.append({
                        "key": dotted,
                        "value": {},
                        "schema_candidate": not is_user_key,
                    })
                else:
                    entries.extend(flatten_config(child, dotted, skip_schema_at_next=next_skip))
            elif isinstance(child, list):
                safe_list = [redact_value(dotted, item) if not isinstance(item, (dict, list)) else "<nested>" for item in child[:10]]
                entries.append({
                    "key": dotted,
                    "value": safe_list,
                    "schema_candidate": not is_user_key,
                })
            else:
                entries.append({
                    "key": dotted,
                    "value": redact_value(dotted, child),
                    "schema_candidate": not is_user_key,
                })
    return entries


def parse_agent_override(raw: str) -> AgentSpec:
    """Parse --agent <id> or --agent <id>=<owner/repo>[:<tag_prefix>]."""
    if "=" not in raw:
        key = raw.strip().lower()
        if key not in KNOWN_AGENTS:
            raise ValueError(f"unknown agent '{key}'; pass {key}=owner/repo to audit a custom GitHub repo")
        return KNOWN_AGENTS[key]
    name_part, rhs = raw.split("=", 1)
    agent_id = name_part.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", agent_id):
        raise ValueError(f"invalid agent identifier: {agent_id}")
    if ":" in rhs:
        repo, tag_prefix = rhs.split(":", 1)
    else:
        repo, tag_prefix = rhs, "v"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo.strip()):
        raise ValueError(f"invalid GitHub repository '{repo}'; expected owner/repo")
    base = KNOWN_AGENTS.get(agent_id)
    if base:
        return AgentSpec(
            agent_id=agent_id,
            display_name=base.display_name,
            binaries=base.binaries,
            repo=repo.strip(),
            tag_prefix=tag_prefix,
            changelog_paths=base.changelog_paths,
            xdg_config_relpaths=base.xdg_config_relpaths,
            home_config_relpaths=base.home_config_relpaths,
            profile_subdir=base.profile_subdir,
        )
    return AgentSpec(
        agent_id=agent_id,
        display_name=agent_id,
        binaries=(agent_id,),
        repo=repo.strip(),
        tag_prefix=tag_prefix,
        xdg_config_relpaths=(f"{agent_id}/config.json", f"{agent_id}/config.toml", f"{agent_id}/settings.json"),
        home_config_relpaths=(f".{agent_id}/config.json", f".{agent_id}/settings.json"),
        profile_subdir=agent_id,
    )


def parse_semver_tag(tag: str, tag_prefix: str = "") -> tuple[tuple[int, int, int] | None, str, bool]:
    """Return ((major, minor, patch), normalized_version, is_stable) for a Git tag."""
    cleaned = tag.strip()
    if not cleaned:
        return None, "", False
    if tag_prefix:
        if not cleaned.startswith(tag_prefix):
            return None, "", False
        version_part = cleaned[len(tag_prefix):]
    else:
        # Reject monorepo component prefixes like sdk-v1.0.0 when expecting bare or v-prefixed tags.
        if re.match(r"^[A-Za-z0-9_-]+-v?\d", cleaned) and not cleaned.startswith("v"):
            return None, "", False
        version_part = cleaned[1:] if cleaned.startswith("v") else cleaned

    match = SEMVER_RE.match(version_part)
    if not match:
        return None, "", False

    major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
    prerelease = match.group(4)
    build_meta = match.group(5)

    is_stable = prerelease is None and not PRERELEASE_TOKEN_RE.search(cleaned)
    if build_meta and PRERELEASE_TOKEN_RE.search(build_meta):
        is_stable = False

    normalized = f"{major}.{minor}.{patch}" + (f"-{prerelease}" if prerelease else "")
    return (major, minor, patch), normalized, is_stable


def parse_plain_semver(raw: str) -> tuple[int, int, int] | None:
    """Parse a plain X.Y.Z version string for comparison."""
    cleaned = raw.strip().lstrip("v")
    match = SEMVER_RE.match(cleaned)
    if not match:
        found = VERSION_EXTRACT_RE.search(cleaned)
        if not found:
            return None
        match = SEMVER_RE.match(found.group(1))
        if not match:
            return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def hex_or_digest_to_sri(digest_or_hex: str) -> str | None:
    """Convert 'sha256:<hex>' or 64-char SHA-256 hex into Nix SRI 'sha256-<base64>'."""
    raw = digest_or_hex.strip()
    if raw.startswith("sha256-"):
        return raw
    if raw.startswith("sha256:"):
        raw = raw.split(":", 1)[1].strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", raw):
        return None
    encoded = base64.b64encode(bytes.fromhex(raw)).decode("ascii")
    return f"sha256-{encoded}"


def compute_url_hashes(url: str, timeout_secs: int = 30, max_bytes: int = 300 * 1024 * 1024) -> dict[str, str]:
    """Stream an asset URL and return hex + Nix SRI SHA-256 hashes."""
    req = urllib.request.Request(url, headers={"User-Agent": "agent-skills-upgrade-agents/1.0"})
    hasher = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(req, timeout=timeout_secs) as resp:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"asset exceeds {max_bytes} byte safety limit: {url}")
            hasher.update(chunk)
    digest_hex = hasher.hexdigest()
    sri = hex_or_digest_to_sri(digest_hex) or ""
    return {"sha256_hex": digest_hex, "sri": sri}


SHELL_EXPORT_RE = re.compile(
    r"""^\s*(?:export\s+)?([A-Z][A-Z0-9_]{2,80})=(?:"([^"$]*)"|'([^']*)'|([^\s;#]+))""",
    re.MULTILINE,
)
WRAP_SET_RE = re.compile(
    r"""--set(?:-default)?\s+([A-Z][A-Z0-9_]{2,80})\s+(?:"([^"]*)"|'([^']*)'|([^\s\\]+))"""
)
EXEC_PATH_RE = re.compile(r"""(/[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)+)""")


def extract_wrapper_details(script_text: str, expected_names: tuple[str, ...]) -> tuple[dict[str, object], list[str]]:
    """Extract exported env vars and candidate wrapped binary paths from a shell wrapper."""
    dynamic_prefixes = tuple(f"{n.upper().replace('-', '_')}_" for n in expected_names if n)
    known_prefixes = ("CLAUDE_", "CODEX_", "AGY_", "ANTIGRAVITY_", "OPENCODE_", "GEMINI_", "AIDER_") + dynamic_prefixes
    env_vars: dict[str, object] = {}
    for match in SHELL_EXPORT_RE.finditer(script_text):
        key = match.group(1)
        val = next((g for g in match.groups()[1:] if g is not None), "")
        if ENV_PRIVACY_RE.search(key) or ENV_DEV_RE.search(key) or key.startswith(known_prefixes):
            env_vars[key] = redact_value(key, val)
    for match in WRAP_SET_RE.finditer(script_text):
        key = match.group(1)
        val = next((g for g in match.groups()[1:] if g is not None), "")
        env_vars[key] = redact_value(key, val)

    candidates: list[str] = []
    for line in script_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "exec " in stripped or "--add-flags" in stripped or "wrapProgram" in stripped:
            for path_match in EXEC_PATH_RE.finditer(stripped):
                candidates.append(path_match.group(1))

    expected_set = set(expected_names) | {f".{n}-wrapped" for n in expected_names}
    prioritized: list[str] = []
    secondary: list[str] = []
    for cand in candidates:
        base = os.path.basename(cand)
        if base in expected_set or base.endswith(".js"):
            prioritized.append(cand)
        elif "profile-router" not in base:
            secondary.append(cand)
    return env_vars, prioritized + secondary


def classify_install_owner(chain: list[str]) -> str:
    """Classify which package manager or installer owns an executable chain."""
    for item in chain:
        if item.startswith("/nix/store/"):
            return "nix"
    for item in chain:
        lower = item.lower()
        if "/cellar/" in lower or "/homebrew/" in lower or "linuxbrew" in lower:
            return "homebrew"
        if "/node_modules/" in lower or "/.npm" in lower or "/pnpm/" in lower or "/.bun/" in lower:
            return "npm"
        if "/uv/tools/" in lower or "/pipx/venvs/" in lower:
            return "uv-or-pipx"
        if "/.cargo/bin/" in lower:
            return "cargo"
    if chain:
        home = str(Path.home())
        if any(p.startswith(f"{home}/.local/") or p.startswith(f"{home}/.") for p in chain):
            return "vendor-local"
    return "system"


def trace_executable(entry_path: Path, expected_names: tuple[str, ...]) -> dict[str, object]:
    """Follow symlinks and shell wrappers to locate the underlying agent payload binary."""
    chain: list[str] = []
    wrapper_env: dict[str, object] = {}
    visited: set[str] = set()
    current = entry_path

    for _ in range(12):
        curr_str = str(current)
        if curr_str in visited or not current.exists():
            break
        visited.add(curr_str)
        chain.append(curr_str)

        if current.is_symlink():
            try:
                resolved_step = (current.parent / os.readlink(current)).resolve()
                current = resolved_step
                continue
            except OSError:
                break

        if not current.is_file():
            break

        # Inspect small shell wrapper scripts for env exports and exec targets.
        try:
            size = current.stat().st_size
            with current.open("rb") as fh:
                head = fh.read(4096)
        except OSError:
            break

        is_shell_wrapper = head.startswith(b"#!") and any(
            sh in head.splitlines()[0] for sh in (b"sh", b"bash", b"zsh", b"dash")
        )
        if is_shell_wrapper and size <= 262144:
            text = current.read_text(encoding="utf-8", errors="replace")
            envs, next_paths = extract_wrapper_details(text, expected_names)
            wrapper_env.update(envs)

            wrapped_sibling = current.parent / f".{current.name}-wrapped"
            if wrapped_sibling.is_file():
                current = wrapped_sibling
                continue

            advanced = False
            for cand in next_paths:
                cand_path = Path(cand)
                if cand_path.is_file() and str(cand_path) not in visited:
                    current = cand_path
                    advanced = True
                    break
            if advanced:
                continue
        break

    payload = chain[-1] if chain else str(entry_path)
    return {
        "entrypoint": str(entry_path),
        "payload_binary": payload,
        "chain": chain,
        "install_owner": classify_install_owner(chain),
        "wrapper_env": wrapper_env,
    }


def safe_probe_env() -> dict[str, str]:
    """Build a telemetry-disabled environment for read-only CLI version/help probes."""
    env = os.environ.copy()
    env.update({
        "DO_NOT_TRACK": "1",
        "OTEL_SDK_DISABLED": "true",
        "OTEL_TRACES_EXPORTER": "none",
        "OTEL_METRICS_EXPORTER": "none",
        "DISABLE_TELEMETRY": "1",
        "DISABLE_AUTOUPDATER": "1",
        "CODEX_DISABLE_TELEMETRY": "1",
        "CODEX_DISABLE_UPDATE_CHECK": "1",
        "AGY_CLI_DISABLE_TELEMETRY": "true",
        "AGY_CLI_DISABLE_UPDATE_CHECK": "true",
        "OPENCODE_TELEMETRY_ENABLED": "false",
        "GOTELEMETRY": "off",
        "CI": "1",
        "TERM": "dumb",
    })
    return env


def query_installed_version(binary_path: str) -> dict[str, str | None]:
    """Run `<binary> --version` safely and parse a semantic version."""
    try:
        proc = subprocess.run(
            [binary_path, "--version"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env=safe_probe_env(),
            timeout=5,
            check=False,
        )
        combined = f"{proc.stdout}\n{proc.stderr}".strip()
        first_line = combined.splitlines()[0].strip() if combined else ""
        match = VERSION_EXTRACT_RE.search(combined)
        return {
            "raw": first_line or None,
            "semver": match.group(1) if match else None,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"raw": f"error: {exc}", "semver": None}


def load_config_file(path: Path) -> dict[str, object]:
    """Parse JSON or TOML configuration file and return redacted flattened entries."""
    suffix = path.suffix.lower()
    raw_text = path.read_text(encoding="utf-8", errors="replace")
    parsed: object = None
    fmt = suffix.lstrip(".") or "text"

    if suffix == ".json":
        parsed = json.loads(raw_text)
        # `.claude.json` stores thousands of internal session/cache state keys alongside `mcpServers`.
        if path.name == ".claude.json" and isinstance(parsed, dict):
            parsed = {k: v for k, v in parsed.items() if k in ("mcpServers", "telemetry", "autoUpdates", "hasCompletedOnboarding")}
    elif suffix == ".toml" and tomllib is not None:
        parsed = tomllib.loads(raw_text)
    else:
        # Lightweight line-key extraction for YAML/dotenv-style files without external deps.
        keys: list[dict[str, object]] = []
        for line in raw_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z0-9_.-]+)\s*[:=]\s*(.*)$", stripped)
            if m:
                k, v = m.group(1), m.group(2).strip().strip("\"'")
                keys.append({
                    "key": k,
                    "value": redact_value(k, v),
                    "schema_candidate": True,
                })
        return {
            "path": str(path),
            "format": fmt,
            "is_symlink": path.is_symlink(),
            "entries": keys,
        }

    return {
        "path": str(path),
        "format": fmt,
        "is_symlink": path.is_symlink(),
        "entries": flatten_config(parsed),
    }


def discover_config_files(spec: AgentSpec) -> list[dict[str, object]]:
    """Locate existing configuration files across XDG, dotdir, and profile directories."""
    home = Path.home()
    xdg_config = Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config"))
    candidates: list[Path] = []

    for rel in spec.xdg_config_relpaths:
        candidates.append(xdg_config / rel)
    for rel in spec.home_config_relpaths:
        candidates.append(home / rel)

    profiles_root = xdg_config / "profiles"
    if spec.profile_subdir and profiles_root.is_dir():
        for prof_dir in sorted(profiles_root.iterdir()):
            sub = prof_dir / spec.profile_subdir
            if sub.is_dir():
                for fname in ("settings.json", "config.toml", "opencode.json", "config.json", ".claude.json"):
                    candidates.append(sub / fname)

    seen_paths: set[str] = set()
    results: list[dict[str, object]] = []
    for cand in candidates:
        key = str(cand)
        if key in seen_paths or not cand.is_file():
            continue
        seen_paths.add(key)
        try:
            results.append(load_config_file(cand))
        except Exception as exc:
            results.append({
                "path": key,
                "format": cand.suffix.lstrip("."),
                "is_symlink": cand.is_symlink(),
                "parse_error": str(exc),
                "entries": [],
            })
    return results


def scan_workspace_declarations(workspace: Path, specs: list[AgentSpec]) -> dict[str, list[dict[str, object]]]:
    """Scan a declarative repository (Nix overlays/modules, Brewfile, mise, package.json) for agent pins."""
    declarations: dict[str, list[dict[str, object]]] = {s.agent_id: [] for s in specs}
    if not workspace.is_dir():
        return declarations

    candidate_files: list[Path] = []
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "result", "target", "dist", "venv", ".venv")]
        rel_depth = len(Path(root).relative_to(workspace).parts)
        if rel_depth > 5:
            dirs[:] = []
            continue
        for fname in files:
            if fname.endswith(".nix") or fname in ("Brewfile", "mise.toml", ".tool-versions", "package.json"):
                candidate_files.append(Path(root) / fname)

    for fpath in sorted(candidate_files):
        try:
            if fpath.stat().st_size > 512 * 1024:
                continue
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel = str(fpath.relative_to(workspace))
        for spec in specs:
            fname_stem = fpath.stem.lower()
            mentions_repo = spec.repo.lower() in text.lower()
            mentions_pname = bool(re.search(rf'\bpname\s*=\s*"{re.escape(spec.agent_id)}"', text))
            is_named_overlay = fpath.suffix == ".nix" and fname_stem in (spec.agent_id, *spec.binaries)

            if not (mentions_repo or mentions_pname or is_named_overlay):
                continue

            ver_match = re.search(r'\bversion\s*=\s*"([^"]+)"', text)
            has_fetchurl = "fetchurl" in text or "fetchFromGitHub" in text or "releases/download" in text
            is_local_stub = bool(mentions_pname and not has_fetchurl and ("writeText" in text or "writeShell" in text))

            declarations[spec.agent_id].append({
                "file": rel,
                "declared_version": ver_match.group(1) if ver_match else None,
                "references_upstream_repo": mentions_repo,
                "fetches_release_artifact": has_fetchurl,
                "is_local_stub": is_local_stub,
            })

    return declarations


def discover_agents(specs: list[AgentSpec], workspace: Path | None = None) -> dict[str, object]:
    """Discover installed binaries, provenance, versions, configs, and workspace declarations."""
    home = Path.home()
    extra_bins = [home / ".local" / "bin"]
    ws_decls = scan_workspace_declarations(workspace, specs) if workspace else {}

    agents_report: list[dict[str, object]] = []
    for spec in specs:
        found_bins: list[dict[str, object]] = []
        seen_entries: set[str] = set()

        for bname in spec.binaries:
            which_hit = shutil.which(bname)
            candidates = [Path(which_hit)] if which_hit else []
            for extra in extra_bins:
                cand = extra / bname
                if cand.exists():
                    candidates.append(cand)

            for entry in candidates:
                key = str(entry)
                if key in seen_entries:
                    continue
                seen_entries.add(key)
                trace = trace_executable(entry, spec.binaries)
                payload_name = os.path.basename(str(trace["payload_binary"]))
                # Detect aliases/wrappers where `gemini` delegates to `agy`.
                delegates_to = None
                if spec.agent_id == "gemini" and "agy" in payload_name:
                    delegates_to = "agy"

                ver_info = query_installed_version(str(trace["payload_binary"]))
                if not ver_info["semver"] and str(trace["entrypoint"]) != str(trace["payload_binary"]):
                    ver_info = query_installed_version(str(trace["entrypoint"]))

                trace["version"] = ver_info
                if delegates_to:
                    trace["delegates_to"] = delegates_to
                found_bins.append(trace)

        configs = discover_config_files(spec)
        decls = ws_decls.get(spec.agent_id, [])
        if found_bins or configs or decls:
            agents_report.append({
                "agent_id": spec.agent_id,
                "display_name": spec.display_name,
                "upstream_repo": spec.repo,
                "tag_prefix": spec.tag_prefix,
                "installed_binaries": found_bins,
                "config_files": configs,
                "workspace_declarations": decls,
            })

    return {"agents": agents_report}


def github_api_get_json(endpoint: str, timeout_secs: int = 20) -> object:
    """Fetch GitHub API JSON using authenticated `gh api` when available, else urllib."""
    gh_bin = shutil.which("gh")
    if gh_bin:
        proc = subprocess.run(
            [gh_bin, "api", endpoint],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout_secs,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout)

    url = endpoint if endpoint.startswith("https://") else f"https://api.github.com/{endpoint.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "agent-skills-upgrade-agents/1.0",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout_secs) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def github_fetch_raw_file(repo: str, path: str, ref: str = "HEAD", timeout_secs: int = 15) -> str | None:
    """Fetch a raw text file (such as CHANGELOG.md) from a GitHub repository."""
    encoded_path = "/".join(urllib.parse.quote(part) for part in path.split("/"))
    endpoint = f"repos/{repo}/contents/{encoded_path}?ref={urllib.parse.quote(ref)}"
    try:
        data = github_api_get_json(endpoint, timeout_secs=timeout_secs)
        if isinstance(data, dict) and data.get("encoding") == "base64" and isinstance(data.get("content"), str):
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


def classify_release_notes(body: str, tag: str) -> dict[str, list[dict[str, str]]]:
    """Extract high-signal lines from release notes into stale-config, privacy, dev-mode, and breaking buckets."""
    buckets: dict[str, list[dict[str, str]]] = {
        "stale_and_deprecated": [],
        "privacy_and_telemetry": [],
        "dev_mode_and_features": [],
        "breaking_changes": [],
    }
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("<!--"):
            continue
        cleaned = re.sub(r"^[-*+]\s+", "", line)
        if len(cleaned) > 320:
            cleaned = cleaned[:317] + "..."
        item = {"release": tag, "note": cleaned}
        if CHANGELOG_STALE_RE.search(cleaned):
            buckets["stale_and_deprecated"].append(item)
        if CHANGELOG_PRIVACY_RE.search(cleaned):
            buckets["privacy_and_telemetry"].append(item)
        if CHANGELOG_DEV_RE.search(cleaned):
            buckets["dev_mode_and_features"].append(item)
        if CHANGELOG_BREAKING_RE.search(cleaned):
            buckets["breaking_changes"].append(item)
    return buckets


def extract_changelog_delta(changelog_text: str, since_tuple: tuple[int, int, int] | None, latest_tuple: tuple[int, int, int]) -> str:
    """Slice versioned sections from CHANGELOG.md strictly newer than `since_tuple` up to `latest_tuple`."""
    header_re = re.compile(r"^#{1,3}\s+\[?v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\]?")
    collected: list[str] = []
    capturing = False
    sections_captured = 0

    for line in changelog_text.splitlines():
        m = header_re.match(line.strip())
        if m:
            ver_str = m.group(1)
            parsed, _, is_stable = parse_semver_tag(ver_str, "")
            if parsed is None:
                capturing = False
                continue
            if since_tuple is not None and parsed <= since_tuple:
                break
            if is_stable and parsed <= latest_tuple:
                capturing = True
                sections_captured += 1
                if sections_captured > 25:
                    break
            else:
                capturing = False
        if capturing:
            collected.append(line)
    return "\n".join(collected)


def audit_releases(
    spec: AgentSpec,
    since_version: str | None = None,
    max_releases: int = 30,
    compute_hashes: bool = False,
    include_changelog: bool = True,
) -> dict[str, object]:
    """Query GitHub releases, resolve latest stable version, and scour version-delta changelogs."""
    per_page = min(max(max_releases * 2, 40), 100)
    raw_releases = github_api_get_json(f"repos/{spec.repo}/releases?per_page={per_page}")
    if not isinstance(raw_releases, list):
        raise ValueError(f"unexpected GitHub releases payload for {spec.repo}")

    since_tuple = parse_plain_semver(since_version) if since_version else None
    stable_releases: list[tuple[tuple[int, int, int], dict[str, object]]] = []
    skipped_prereleases: list[dict[str, str]] = []

    for rel in raw_releases:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        tag = str(rel.get("tag_name") or "")
        sem_tuple, normalized, is_tag_stable = parse_semver_tag(tag, spec.tag_prefix)
        if sem_tuple is None:
            continue
        if rel.get("prerelease") or not is_tag_stable:
            skipped_prereleases.append({
                "tag": tag,
                "version": normalized,
                "published_at": str(rel.get("published_at") or ""),
            })
            continue
        stable_releases.append((sem_tuple, {
            "tag": tag,
            "version": normalized,
            "published_at": str(rel.get("published_at") or ""),
            "html_url": str(rel.get("html_url") or ""),
            "body": str(rel.get("body") or ""),
            "assets": rel.get("assets") if isinstance(rel.get("assets"), list) else [],
        }))

    stable_releases.sort(key=lambda item: item[0], reverse=True)
    if not stable_releases:
        return {
            "agent_id": spec.agent_id,
            "repo": spec.repo,
            "latest_stable": None,
            "skipped_prereleases": skipped_prereleases[:10],
            "error": f"no stable releases matching prefix '{spec.tag_prefix}' found in recent releases",
        }

    latest_tuple, latest_rel = stable_releases[0]
    newer_prereleases = [
        p for p in skipped_prereleases
        if (parse_plain_semver(p["version"]) or (0, 0, 0)) >= latest_tuple
    ]

    delta_releases: list[dict[str, object]] = []
    for sem_tuple, rel_info in stable_releases:
        if since_tuple is not None and sem_tuple <= since_tuple:
            break
        delta_releases.append(rel_info)
        if len(delta_releases) >= max_releases:
            break
    if not delta_releases:
        # Already on or ahead of latest stable; still inspect latest release notes for completeness.
        delta_releases = [latest_rel]

    aggregated_signals: dict[str, list[dict[str, str]]] = {
        "stale_and_deprecated": [],
        "privacy_and_telemetry": [],
        "dev_mode_and_features": [],
        "breaking_changes": [],
    }
    for rel_info in delta_releases:
        classified = classify_release_notes(str(rel_info["body"]), str(rel_info["tag"]))
        for key, items in classified.items():
            aggregated_signals[key].extend(items)

    changelog_excerpt = ""
    if include_changelog:
        for ch_path in spec.changelog_paths:
            raw_ch = github_fetch_raw_file(spec.repo, ch_path, ref=str(latest_rel["tag"]))
            if not raw_ch:
                raw_ch = github_fetch_raw_file(spec.repo, ch_path, ref="HEAD")
            if raw_ch:
                changelog_excerpt = extract_changelog_delta(raw_ch, since_tuple, latest_tuple)
                if changelog_excerpt:
                    ch_signals = classify_release_notes(changelog_excerpt, f"{ch_path}@{latest_rel['tag']}")
                    for key, items in ch_signals.items():
                        existing_notes = {x["note"] for x in aggregated_signals[key]}
                        for item in items:
                            if item["note"] not in existing_notes:
                                aggregated_signals[key].append(item)
                break

    assets_out: list[dict[str, object]] = []
    for asset in latest_rel["assets"]:  # type: ignore[index]
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        dl_url = str(asset.get("browser_download_url") or "")
        digest = str(asset.get("digest") or "")
        sri = hex_or_digest_to_sri(digest) if digest else None
        entry: dict[str, object] = {
            "name": name,
            "url": dl_url,
            "size": asset.get("size"),
            "sri": sri,
        }
        if not sri and compute_hashes and dl_url and name.endswith((".tar.gz", ".tgz", ".zip", ".tar.xz")):
            try:
                computed = compute_url_hashes(dl_url)
                entry["sri"] = computed["sri"]
                entry["sha256_hex"] = computed["sha256_hex"]
            except Exception as exc:
                entry["hash_error"] = str(exc)
        assets_out.append(entry)

    update_available = bool(since_tuple is not None and latest_tuple > since_tuple)
    return {
        "agent_id": spec.agent_id,
        "repo": spec.repo,
        "since_version": since_version,
        "latest_stable": {
            "version": latest_rel["version"],
            "tag": latest_rel["tag"],
            "published_at": latest_rel["published_at"],
            "url": latest_rel["html_url"],
            "assets": assets_out,
        },
        "update_available": update_available,
        "skipped_newer_prereleases": newer_prereleases[:10],
        "releases_scanned": [
            {"tag": r["tag"], "version": r["version"], "published_at": r["published_at"]}
            for r in delta_releases
        ],
        "signals": aggregated_signals,
    }


UPPER_ENV_TOKEN_RE = re.compile(rb"(?<![A-Za-z0-9_])([A-Z][A-Z0-9_]{4,80})(?![A-Za-z0-9_])")


def scan_binary_surface(
    binary_path: Path,
    candidate_needles: set[str],
    max_bytes: int = 250 * 1024 * 1024,
) -> tuple[set[str], set[str]]:
    """Stream a binary or bundle to collect uppercase env tokens and match candidate config keys.

    Uses direct byte-substring matching for `candidate_needles` because compiled Rust binaries
    pack adjacent `&str` literals in `.rodata` without null terminators or word boundaries.
    """
    env_tokens: set[str] = set()
    remaining: dict[str, bytes] = {
        needle: needle.encode("ascii", errors="ignore")
        for needle in candidate_needles
        if needle
    }
    matched_needles: set[str] = set()
    overlap = b""
    read_bytes = 0

    with binary_path.open("rb") as fh:
        while read_bytes < max_bytes:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            read_bytes += len(chunk)
            buf = overlap + chunk
            safe_end = len(buf) - 128 if len(chunk) == 1024 * 1024 else len(buf)
            window = buf[:safe_end]
            for m in UPPER_ENV_TOKEN_RE.finditer(window):
                env_tokens.add(m.group(1).decode("ascii"))

            if remaining:
                buf_lower = buf.lower()
                newly_found = [key for key, pat in remaining.items() if pat in buf_lower]
                for key in newly_found:
                    matched_needles.add(key)
                    del remaining[key]

            overlap = buf[max(0, len(buf) - 128):]

    return env_tokens, matched_needles


def capture_cli_help(binary_path: str) -> dict[str, object]:
    """Capture `--help` flags safely without triggering interactive sessions or telemetry."""
    try:
        proc = subprocess.run(
            [binary_path, "--help"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env=safe_probe_env(),
            timeout=5,
            check=False,
        )
        text = f"{proc.stdout}\n{proc.stderr}"
        flags = sorted(set(re.findall(r"(--[a-z0-9][a-z0-9-]{1,50})", text, flags=re.IGNORECASE)))
        dev_flags = [f for f in flags if re.search(r"(dev|debug|inspect|experimen|feature|offline|local|code-mode|mcp)", f, re.I)]
        privacy_flags = [f for f in flags if re.search(r"(telemet|analytic|update|privacy|survey|memory|otel|track)", f, re.I)]
        return {
            "exit_code": proc.returncode,
            "all_flags_count": len(flags),
            "dev_and_feature_flags": dev_flags,
            "privacy_and_update_flags": privacy_flags,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc), "dev_and_feature_flags": [], "privacy_and_update_flags": []}


def probe_agent_binary(
    spec: AgentSpec | None,
    binary_override: Path | None = None,
    extra_config_files: list[Path] | None = None,
) -> dict[str, object]:
    """Inspect an agent's payload binary, CLI flags, env switches, and potentially stale config keys."""
    trace: dict[str, object] | None = None
    if binary_override:
        expected = spec.binaries if spec else (binary_override.name,)
        trace = trace_executable(binary_override, expected)
    elif spec:
        for bname in spec.binaries:
            hit = shutil.which(bname) or (str(Path.home() / ".local" / "bin" / bname) if (Path.home() / ".local" / "bin" / bname).exists() else None)
            if hit:
                trace = trace_executable(Path(hit), spec.binaries)
                break

    if not trace:
        raise ValueError("target binary not found; specify --binary PATH or install the agent first")

    payload = Path(str(trace["payload_binary"]))
    configs: list[dict[str, object]] = discover_config_files(spec) if spec else []
    for extra in extra_config_files or []:
        if extra.is_file():
            configs.append(load_config_file(extra))

    candidate_variants: dict[str, tuple[str, ...]] = {}
    all_needles: set[str] = set()
    for cfg in configs:
        entries = cfg.get("entries", [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("schema_candidate", True):
                continue
            key_path = str(entry.get("key") or "")
            if key_path.startswith("env.") or not key_path:
                continue
            leaf = key_path.rsplit(".", 1)[-1]
            snake_leaf = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", leaf).lower()
            camel_leaf = re.sub(r"_([a-z])", lambda m: m.group(1).upper(), leaf).lower()
            kebab_leaf = snake_leaf.replace("_", "-")
            variants = tuple(dict.fromkeys(v for v in (leaf.lower(), snake_leaf, camel_leaf, kebab_leaf) if len(v) >= 3))
            candidate_variants[key_path] = variants
            all_needles.update(variants)

    env_tokens, matched_needles = scan_binary_surface(payload, all_needles)

    agent_prefixes = ("CLAUDE_", "CODEX_", "AGY_", "ANTIGRAVITY_", "OPENCODE_", "GEMINI_", "AIDER_", "OTEL_", "DO_NOT_TRACK", "DISABLE_", "ENABLE_", "GOTELEMETRY")
    privacy_env_candidates = sorted(
        tok for tok in env_tokens
        if ENV_PRIVACY_RE.search(tok) and (tok.startswith(agent_prefixes) or "_" in tok)
    )
    dev_env_candidates = sorted(
        tok for tok in env_tokens
        if ENV_DEV_RE.search(tok) and tok.startswith(agent_prefixes)
    )

    configured_env: dict[str, object] = dict(trace.get("wrapper_env", {}))  # type: ignore[arg-type]
    unmatched_keys: list[dict[str, object]] = []

    for cfg in configs:
        entries = cfg.get("entries", [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            key_path = str(entry.get("key") or "")
            if key_path.startswith("env."):
                env_name = key_path.split(".", 1)[1]
                configured_env[env_name] = entry.get("value")
                continue
            if not entry.get("schema_candidate", True):
                continue
            variants = candidate_variants.get(key_path, ())
            if variants and not any(v in matched_needles for v in variants):
                unmatched_keys.append({
                    "config_file": cfg.get("path"),
                    "key": key_path,
                    "value": entry.get("value"),
                    "reason": "leaf identifier not found in payload binary strings; verify against schema/changelog",
                })

    unset_privacy_env = [tok for tok in privacy_env_candidates if tok not in configured_env]
    unset_dev_env = [tok for tok in dev_env_candidates if tok not in configured_env]

    return {
        "agent_id": spec.agent_id if spec else payload.name,
        "trace": trace,
        "cli_help": capture_cli_help(str(payload)),
        "configured_env_switches": configured_env,
        "binary_privacy_env_candidates": privacy_env_candidates[:120],
        "unset_privacy_env_candidates": unset_privacy_env[:80],
        "binary_dev_env_candidates": dev_env_candidates[:120],
        "unset_dev_env_candidates": unset_dev_env[:80],
        "unmatched_config_keys": unmatched_keys,
    }


def render_markdown(data: dict[str, object], mode: str) -> str:
    """Render concise human-readable Markdown summaries for CLI output."""
    lines: list[str] = []
    if mode == "discover":
        agents = data.get("agents", [])
        lines.append(f"# Discovered Agent Programs ({len(agents) if isinstance(agents, list) else 0})")
        for item in agents if isinstance(agents, list) else []:
            if not isinstance(item, dict):
                continue
            lines.append(f"\n## `{item['agent_id']}` — {item['display_name']} (`{item['upstream_repo']}`)")
            for b in item.get("installed_binaries", []):
                ver = b.get("version", {})
                lines.append(
                    f"- **Binary**: `{b['entrypoint']}` → `{b['payload_binary']}` "
                    f"(owner: `{b['install_owner']}`, version: `{ver.get('semver') or ver.get('raw') or 'unknown'}`)"
                )
            for decl in item.get("workspace_declarations", []):
                lines.append(
                    f"- **Workspace Declaration**: `{decl['file']}` "
                    f"(pinned: `{decl.get('declared_version')}`, local_stub: `{decl.get('is_local_stub')}`)"
                )
            for cfg in item.get("config_files", []):
                lines.append(f"- **Config**: `{cfg['path']}` ({len(cfg.get('entries', []))} entries)")
        return "\n".join(lines) + "\n"

    if mode == "releases":
        latest = data.get("latest_stable")
        lines.append(f"# Upstream Release Audit: `{data.get('agent_id')}` (`{data.get('repo')}`)")
        if isinstance(latest, dict):
            lines.append(f"- **Latest Stable**: `{latest.get('version')}` (`{latest.get('tag')}`, published `{latest.get('published_at')}`)")
            lines.append(f"- **Update Available**: `{data.get('update_available')}` (since `{data.get('since_version')}`)")
        skipped = data.get("skipped_newer_prereleases", [])
        if isinstance(skipped, list) and skipped:
            tags = ", ".join(f"`{p['tag']}`" for p in skipped)
            lines.append(f"- **Skipped Newer Prereleases**: {tags}")
        signals = data.get("signals", {})
        if isinstance(signals, dict):
            for bucket, items in signals.items():
                if items:
                    lines.append(f"\n## {bucket} ({len(items)})")
                    for entry in items[:25]:
                        lines.append(f"- [`{entry['release']}`] {entry['note']}")
        return "\n".join(lines) + "\n"

    lines.append(f"# Binary Surface Probe: `{data.get('agent_id')}`")
    unmatched = data.get("unmatched_config_keys", [])
    lines.append(f"- **Potentially Stale Config Keys**: {len(unmatched) if isinstance(unmatched, list) else 0}")
    for u in unmatched if isinstance(unmatched, list) else []:
        lines.append(f"  - `{u['key']}` in `{u['config_file']}`")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    disc = sub.add_parser("discover", help="inventory installed agent CLIs, wrappers, configs, and declarative pins")
    disc.add_argument("--workspace", type=Path, help="optional declarative repo/dotfiles root to scan")
    disc.add_argument("--agent", action="append", default=[], help="filter or add custom id=owner/repo[:tag_prefix]")
    disc.add_argument("--format", choices=("json", "markdown"), default="json")

    rel = sub.add_parser("releases", help="fetch latest stable GitHub release and scour version-delta changelogs")
    rel.add_argument("--agent", required=True, help="agent id or custom id=owner/repo[:tag_prefix]")
    rel.add_argument("--since", help="installed semver (e.g. 2.1.280) to bound changelog delta")
    rel.add_argument("--max-releases", type=int, default=30, help="maximum stable releases to inspect")
    rel.add_argument("--hashes", action="store_true", help="extract or stream-compute Nix SRI sha256 hashes for assets")
    rel.add_argument("--no-changelog", action="store_true", help="skip fetching CHANGELOG.md from upstream repository")
    rel.add_argument("--format", choices=("json", "markdown"), default="json")

    probe = sub.add_parser("probe-binary", help="inspect payload binary flags, privacy/dev env vars, and stale config keys")
    probe.add_argument("--agent", help="agent id or custom id=owner/repo")
    probe.add_argument("--binary", type=Path, help="explicit path to executable or payload binary")
    probe.add_argument("--config-file", type=Path, action="append", default=[], help="additional config file to cross-check")
    probe.add_argument("--format", choices=("json", "markdown"), default="json")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "discover":
            specs = [parse_agent_override(raw) for raw in args.agent] if args.agent else list(KNOWN_AGENTS.values())
            ws = args.workspace.expanduser().resolve() if args.workspace else None
            result = discover_agents(specs, workspace=ws)
        elif args.command == "releases":
            spec = parse_agent_override(args.agent)
            result = audit_releases(
                spec,
                since_version=args.since,
                max_releases=args.max_releases,
                compute_hashes=args.hashes,
                include_changelog=not args.no_changelog,
            )
        else:
            if not args.agent and not args.binary:
                parser.error("probe-binary requires --agent or --binary")
            spec = parse_agent_override(args.agent) if args.agent else None
            bpath = args.binary.expanduser().resolve() if args.binary else None
            extra_cfgs = [p.expanduser().resolve() for p in args.config_file]
            result = probe_agent_binary(spec, binary_override=bpath, extra_config_files=extra_cfgs)

        if args.format == "markdown":
            sys.stdout.write(render_markdown(result, args.command))
        else:
            json.dump(result, sys.stdout, indent=2)
            sys.stdout.write("\n")
        return 0
    except (OSError, ValueError, urllib.error.URLError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
