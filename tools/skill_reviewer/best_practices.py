"""
best_practices.py — Authoritative Agent Skills & Claude Skills best practices specification.

Synthesizes:
- Agent Skills specification (agentskills.io)
- Anthropic's "Building Effective AI Agents"
- Academic taxonomy: "From Anatomy to Smells: An Empirical Study of SKILL.md in Agent Skills"
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re
import urllib.request

# -----------------------------------------------------------------------------
# Core Constraints & Thresholds
# -----------------------------------------------------------------------------

MAX_SKILL_MD_LINES = 500          # Progressive disclosure limit
MAX_SKILL_MD_BYTES = 25000        # ~25 KB context budget
MAX_DESCRIPTION_LEN = 1024        # Agent Skills specification limit
MIN_DESCRIPTION_LEN = 30          # Minimum semantic length for discovery

# -----------------------------------------------------------------------------
# Rule Definitions
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    code: str
    category: str
    severity: str  # "BLOCKER", "MAJOR", "MINOR"
    title: str
    description: str


RULES = [
    Rule(
        code="FM001",
        category="frontmatter",
        severity="BLOCKER",
        title="Missing YAML frontmatter",
        description="SKILL.md must start with a valid YAML frontmatter block enclosed in '---'.",
    ),
    Rule(
        code="FM002",
        category="frontmatter",
        severity="BLOCKER",
        title="Invalid or missing 'name' field",
        description="Frontmatter 'name' must be lowercase, alphanumeric, hyphenated (1-64 chars), and match the directory name.",
    ),
    Rule(
        code="FM003",
        category="frontmatter",
        severity="BLOCKER",
        title="Invalid or missing 'description' field",
        description="Frontmatter 'description' must be informative (30-1024 chars), written in third-person, and specify both WHAT the skill does and WHEN to activate it.",
    ),
    Rule(
        code="PD001",
        category="progressive_disclosure",
        severity="MAJOR",
        title="Context bloat: SKILL.md exceeds line limit",
        description=f"SKILL.md exceeds {MAX_SKILL_MD_LINES} lines. Deep references, long examples, and extensive documentation should be factored into references/ or examples/.",
    ),
    Rule(
        code="PD002",
        category="progressive_disclosure",
        severity="MAJOR",
        title="Broken relative link in markdown",
        description="Internal relative links within SKILL.md must resolve to valid files in the skill directory or repository.",
    ),
    Rule(
        code="SC001",
        category="scripts",
        severity="MAJOR",
        title="Non-executable script in scripts/",
        description="Scripts provided in scripts/ must have executable permissions (+x).",
    ),
    Rule(
        code="SC002",
        category="scripts",
        severity="MAJOR",
        title="Missing shebang in script",
        description="Scripts in scripts/ must begin with a standard shebang line (e.g., #!/usr/bin/env bash).",
    ),
    Rule(
        code="SC003",
        category="scripts",
        severity="MAJOR",
        title="Hardcoded absolute environment path",
        description="Scripts and documentation must not contain hardcoded user home directories (e.g. /Users/, /home/). Use environment variables like $HOME or $SKILL_DIR.",
    ),
    Rule(
        code="AI001",
        category="policy",
        severity="BLOCKER",
        title="AI attribution detected",
        description="Skill files and commits must not contain AI attribution signatures or tags (e.g. 'Co-Authored-By', 'Generated-By').",
    ),
    Rule(
        code="CT001",
        category="catalog",
        severity="MAJOR",
        title="Missing from marketplace.json",
        description="Skill must be registered as a plugin in .claude-plugin/marketplace.json.",
    ),
    Rule(
        code="CT002",
        category="catalog",
        severity="MINOR",
        title="Missing from root README.md",
        description="Skill should be documented in the root README.md skills index table.",
    ),
]

RULE_MAP = {r.code: r for r in RULES}

# -----------------------------------------------------------------------------
# Online Lookup & Cache
# -----------------------------------------------------------------------------

ONLINE_SPEC_URL = "https://agentskills.io/specification"
CACHE_FILE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "adversarial-reviewer" / "agent_skills_spec_cache.json"


def fetch_online_best_practices(url: str = ONLINE_SPEC_URL, timeout_secs: int = 3) -> dict | None:
    """Optionally fetch latest online spec updates with graceful cache/fallback."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Claude-Skill-Reviewer/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_secs) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            data = {"url": url, "snippet": content[:2000]}
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
            return data
    except Exception as exc:
        logging.debug("online spec fetch failed (%s); using canonical built-in rules.", exc)
        return None


def get_best_practices_summary() -> str:
    """Format the canonical Agent Skills best practices for prompt injection or documentation."""
    lines = [
        "### Canonical Agent Skills & Claude Skills Best Practices:",
        "1. **Frontmatter Integrity**: Must define `name` (matching directory name) and `description` (3rd-person, explaining what & when).",
        "2. **Progressive Disclosure**: Keep `SKILL.md` <= 500 lines. Demote manuals, background, and extensive examples to `references/` or `examples/`.",
        "3. **Deterministic Scripts**: Place automation in `scripts/`, ensure executable bit (+x), valid shebang, and portable path variables ($SKILL_DIR).",
        "4. **Link Integrity**: All markdown relative links must resolve to existing files.",
        "5. **Catalog Registration**: Must be registered in `.claude-plugin/marketplace.json` and documented in root `README.md`.",
        "6. **Zero AI Attribution**: Never include 'Co-Authored-By', 'Generated-By', or AI signatures.",
    ]
    return "\n".join(lines)
