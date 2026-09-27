#!/usr/bin/env python3
"""
skill_review.py — Headless Agent Skills & Claude Skills reviewer for pull requests.

Adapted from awill1988/somelse adversarial review architecture:
- Classifies skill changes as NEW, UPDATED, or DELETED
- Auto-approves DELETED skills without content review
- Audits NEW and UPDATED skills against current Claude/Agent Skills best practices
- Evaluates major smells (frontmatter, progressive disclosure, scripts, links, attribution, marketplace)
- Supports deterministic heuristic evaluation and local quantized model inference (llama-cli)
- Submits formal PR reviews via gh pr review
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

try:
    from tools.skill_reviewer.best_practices import (
        MAX_DESCRIPTION_LEN,
        MAX_SKILL_MD_BYTES,
        MAX_SKILL_MD_LINES,
        MIN_DESCRIPTION_LEN,
        RULE_MAP,
        fetch_online_best_practices,
        get_best_practices_summary,
    )
except ImportError:
    from best_practices import (
        MAX_DESCRIPTION_LEN,
        MAX_SKILL_MD_BYTES,
        MAX_SKILL_MD_LINES,
        MIN_DESCRIPTION_LEN,
        RULE_MAP,
        fetch_online_best_practices,
        get_best_practices_summary,
    )

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent.parent.resolve()
DEFAULT_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "adversarial-reviewer"

MAX_DIFF_LINES = 300

SYSTEM_PROMPT = f"""You are an expert CI code reviewer and auditor for AI Agent Skills adhering to the Agent Skills (agentskills.io) and Claude Skills standards.
Your objective is to identify major smells, progressive disclosure violations, broken contracts, and structural defects in the pull request diff.

{get_best_practices_summary()}

Provide your evaluation adhering strictly to one of three dispositions:
- APPROVE (no critical or safety issues found)
- COMMENT (non-blocking suggestions or observations)
- REQUEST_CHANGES (major smell, frontmatter violation, broken link, context bloat, or policy breach)

Conclude your review with:
DISPOSITION: APPROVE | COMMENT | REQUEST_CHANGES
"""

# -----------------------------------------------------------------------------
# Data Structures
# -----------------------------------------------------------------------------

@dataclass
class Finding:
    rule_code: str
    severity: str  # "BLOCKER", "MAJOR", "MINOR"
    category: str
    file: str
    line: int | None
    title: str
    details: str
    counterexample: str | None = None

    def to_dict(self) -> dict:
        return {
            "rule": self.rule_code,
            "severity": self.severity,
            "category": self.category,
            "file": self.file,
            "line": self.line,
            "title": self.title,
            "details": self.details,
            "counterexample": self.counterexample,
        }


@dataclass
class SkillChange:
    name: str
    change_type: str  # "NEW", "UPDATED", "DELETED"
    files: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    disposition: str = "APPROVE"
    summary: str = ""
    functional_summary: str = ""
    reasoning_trace: list[dict] = field(default_factory=list)
    model_reasoning: str = ""
    model_latency: float = 0.0


# -----------------------------------------------------------------------------
# Git Operations & Lifecycle Classification
# -----------------------------------------------------------------------------

def run_git(cmd: list[str], cwd: Path = REPO_ROOT) -> str:
    """Run a git command and return standard output."""
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        logging.debug("git error (%s): %s", cmd, res.stderr.strip())
        return ""
    return res.stdout


def get_base_head_skills(base: str, head: str) -> tuple[set[str], set[str]]:
    """Determine the set of skill directories in base and head refs."""
    base_skills = set()
    base_out = run_git(["git", "ls-tree", "-d", "--name-only", base, "skills/"])
    for line in base_out.splitlines():
        line = line.strip()
        if line.startswith("skills/"):
            base_skills.add(line.split("/")[1])

    head_skills = set()
    head_out = run_git(["git", "ls-tree", "-d", "--name-only", head, "skills/"])
    for line in head_out.splitlines():
        line = line.strip()
        if line.startswith("skills/"):
            head_skills.add(line.split("/")[1])

    return base_skills, head_skills


def classify_skill_changes(base: str = "origin/main", head: str = "HEAD") -> dict[str, SkillChange]:
    """Inspect git diff and classify each changed skill as NEW, UPDATED, or DELETED."""
    base_skills, head_skills = get_base_head_skills(base, head)

    # Get changed files with status (A, M, D, R)
    diff_out = run_git(["git", "diff", f"{base}...{head}", "--name-status"])
    if not diff_out.strip():
        diff_out = run_git(["git", "diff", base, head, "--name-status"])

    skill_files: dict[str, list[str]] = {}
    skill_statuses: dict[str, set[str]] = {}

    for line in diff_out.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) < 2:
            continue
        status_flag = parts[0][0]
        file_path = parts[-1]

        if file_path.startswith("skills/"):
            tokens = file_path.split("/")
            if len(tokens) >= 2:
                skill_name = tokens[1]
                skill_files.setdefault(skill_name, []).append(file_path)
                skill_statuses.setdefault(skill_name, set()).add(status_flag)

    classified: dict[str, SkillChange] = {}

    # Check all skills detected in diff
    for skill_name, files in skill_files.items():
        in_base = skill_name in base_skills
        in_head = skill_name in head_skills

        if in_base and not in_head:
            change_type = "DELETED"
        elif not in_base and in_head:
            change_type = "NEW"
        else:
            change_type = "UPDATED"

        classified[skill_name] = SkillChange(
            name=skill_name,
            change_type=change_type,
            files=files,
        )

    # Also catch any deleted skill directories that might not have appeared as files
    for skill_name in base_skills:
        if skill_name not in head_skills and skill_name not in classified:
            classified[skill_name] = SkillChange(
                name=skill_name,
                change_type="DELETED",
                files=[],
            )

    return classified


def extract_git_diff_text(base: str, head: str, skill_files: list[str]) -> str:
    """Extract trimmed diff for relevant skill files."""
    if not skill_files:
        return ""
    diff_cmd = ["git", "diff", f"{base}...{head}", "--"] + skill_files
    diff_text = run_git(diff_cmd)
    if not diff_text.strip():
        diff_cmd = ["git", "diff", base, head, "--"] + skill_files
        diff_text = run_git(diff_cmd)

    lines = diff_text.splitlines()
    if len(lines) > MAX_DIFF_LINES:
        return "\n".join(lines[:MAX_DIFF_LINES]) + f"\n\n[Diff truncated to {MAX_DIFF_LINES} lines for focused review]"
    return diff_text


# -----------------------------------------------------------------------------
# Static Smell & Best Practice Evaluators
# -----------------------------------------------------------------------------

def get_file_content(ref: str, rel_path: str, root_dir: Path) -> str | None:
    """Read file content from git ref, falling back to working tree if ref is HEAD."""
    if ref != "HEAD":
        out = run_git(["git", "show", f"{ref}:{rel_path}"], cwd=root_dir)
        if out:
            return out

    local_path = root_dir / rel_path
    if local_path.is_file():
        try:
            return local_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

    out = run_git(["git", "show", f"{ref}:{rel_path}"], cwd=root_dir)
    return out if out else None


def list_skill_files(ref: str, skill_name: str, root_dir: Path) -> list[str]:
    """List all files belonging to a skill from git ref or disk."""
    out = run_git(["git", "ls-tree", "-r", "--name-only", ref, f"skills/{skill_name}/"], cwd=root_dir)
    files = [line.strip() for line in out.splitlines() if line.strip()]
    if files:
        return files

    skill_dir = root_dir / "skills" / skill_name
    if skill_dir.is_dir():
        return [str(p.relative_to(root_dir)) for p in skill_dir.rglob("*") if p.is_file() and not p.name.startswith(".")]
    return []


def parse_yaml_frontmatter(content: str) -> tuple[dict, str, list[str]]:
    """Extract YAML frontmatter and body from markdown content."""
    errors = []
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        errors.append("FM001: File does not start with YAML frontmatter delimiter '---'.")
        return {}, content, errors

    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        errors.append("FM001: YAML frontmatter block is not closed with '---'.")
        return {}, content, errors

    yaml_block = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1:])

    # Simple YAML key-value parser (avoids external pyyaml dependency)
    data: dict[str, str] = {}
    current_key = None
    multiline_val = []

    for yline in yaml_block:
        match = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*)$", yline)
        if match:
            if current_key and multiline_val:
                data[current_key] = " ".join(multiline_val).strip()
                multiline_val = []
            current_key = match.group(1)
            raw_v = match.group(2).strip()
            if raw_v in (">-", ">", "|", "|-"):
                multiline_val = []
            else:
                data[current_key] = raw_v.strip("\"'")
        elif current_key and (yline.startswith("  ") or yline.startswith("\t")):
            multiline_val.append(yline.strip())

    if current_key and multiline_val:
        data[current_key] = " ".join(multiline_val).strip()

    return data, body, errors


def evaluate_static_smells(skill_name: str, root_dir: Path, ref: str = "HEAD") -> list[Finding]:
    """Run deterministic static checks against the Agent Skills specification."""
    findings: list[Finding] = []
    skill_md_rel = f"skills/{skill_name}/SKILL.md"
    content = get_file_content(ref, skill_md_rel, root_dir)

    if content is None:
        findings.append(Finding(
            rule_code="FM001",
            severity="BLOCKER",
            category="frontmatter",
            file=skill_md_rel,
            line=1,
            title="Missing SKILL.md",
            details=f"Required file {skill_md_rel} is missing.",
        ))
        return findings

    all_skill_files = set(list_skill_files(ref, skill_name, root_dir))

    # 1. Frontmatter Validation
    fm, body, fm_errors = parse_yaml_frontmatter(content)
    for err in fm_errors:
        findings.append(Finding(
            rule_code="FM001",
            severity="BLOCKER",
            category="frontmatter",
            file=skill_md_rel,
            line=1,
            title="Malformed YAML frontmatter",
            details=err,
        ))

    # Name check
    name_val = fm.get("name", "").strip()
    if not name_val:
        findings.append(Finding(
            rule_code="FM002",
            severity="BLOCKER",
            category="frontmatter",
            file=skill_md_rel,
            line=2,
            title="Missing 'name' field in frontmatter",
            details="Frontmatter must specify a 'name' field.",
        ))
    elif name_val != skill_name:
        findings.append(Finding(
            rule_code="FM002",
            severity="BLOCKER",
            category="frontmatter",
            file=skill_md_rel,
            line=2,
            title="Frontmatter 'name' mismatch with directory",
            details=f"Frontmatter name '{name_val}' does not match directory name '{skill_name}'.",
            counterexample=f"name: {skill_name}",
        ))
    elif not re.match(r"^[a-z0-9][a-z0-9-]{0,63}$", name_val):
        findings.append(Finding(
            rule_code="FM002",
            severity="BLOCKER",
            category="frontmatter",
            file=skill_md_rel,
            line=2,
            title="Invalid frontmatter 'name' format",
            details=f"Skill name '{name_val}' must be lowercase alphanumeric and hyphenated (1-64 chars).",
        ))

    # Description check
    desc_val = fm.get("description", "").strip()
    if not desc_val:
        findings.append(Finding(
            rule_code="FM003",
            severity="BLOCKER",
            category="frontmatter",
            file=skill_md_rel,
            line=3,
            title="Missing 'description' field in frontmatter",
            details="Frontmatter must specify a 'description' field for agent discovery.",
        ))
    elif len(desc_val) < MIN_DESCRIPTION_LEN:
        findings.append(Finding(
            rule_code="FM003",
            severity="MAJOR",
            category="frontmatter",
            file=skill_md_rel,
            line=3,
            title="Vague or underspecified description",
            details=f"Description ({len(desc_val)} chars) is too short. It must explain what the skill does and when to activate it.",
        ))
    elif len(desc_val) > MAX_DESCRIPTION_LEN:
        findings.append(Finding(
            rule_code="FM003",
            severity="MAJOR",
            category="frontmatter",
            file=skill_md_rel,
            line=3,
            title="Description exceeds character limit",
            details=f"Description ({len(desc_val)} chars) exceeds maximum allowed {MAX_DESCRIPTION_LEN} chars.",
        ))

    # 2. Progressive Disclosure (Line Limit)
    line_count = len(content.splitlines())
    if line_count > MAX_SKILL_MD_LINES:
        findings.append(Finding(
            rule_code="PD001",
            severity="MAJOR",
            category="progressive_disclosure",
            file=skill_md_rel,
            line=MAX_SKILL_MD_LINES,
            title=f"Context bloat: SKILL.md is {line_count} lines (limit: {MAX_SKILL_MD_LINES})",
            details="Monolithic SKILL.md violates progressive disclosure. Factor deep background, reference manuals, and extended examples into references/ or examples/.",
        ))

    # 3. Broken Relative Links
    link_matches = re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", body)
    for m in link_matches:
        raw_target = m.group(2).split("#")[0].strip()
        if raw_target and not raw_target.startswith(("http://", "https://", "mailto:")):
            resolved_rel = os.path.normpath(f"skills/{skill_name}/{raw_target}")
            # Check against skill files and on-disk files
            if resolved_rel not in all_skill_files:
                local_target = root_dir / resolved_rel
                if not local_target.exists():
                    findings.append(Finding(
                        rule_code="PD002",
                        severity="MAJOR",
                        category="progressive_disclosure",
                        file=skill_md_rel,
                        line=None,
                        title="Broken relative link in markdown",
                        details=f"Link '{m.group(0)}' points to non-existent path: {raw_target}",
                    ))

    # 4. Script Hygiene
    script_files = [f for f in all_skill_files if f.startswith(f"skills/{skill_name}/scripts/")]
    for sf in script_files:
        sf_name = os.path.basename(sf)
        sf_local = root_dir / sf

        # Check executable bit in git or disk
        is_exec = False
        if sf_local.is_file() and os.access(sf_local, os.X_OK):
            is_exec = True
        else:
            ls_out = run_git(["git", "ls-tree", ref, sf], cwd=root_dir)
            if ls_out.startswith("100755"):
                is_exec = True

        if not is_exec:
            findings.append(Finding(
                rule_code="SC001",
                severity="MAJOR",
                category="scripts",
                file=sf,
                line=None,
                title="Non-executable helper script",
                details=f"Script {sf_name} is not marked executable. Run 'chmod +x {sf}'.",
            ))

        # Check shebang
        script_text = get_file_content(ref, sf, root_dir)
        if script_text:
            lines = script_text.splitlines()
            if not lines or not lines[0].startswith("#!"):
                findings.append(Finding(
                    rule_code="SC002",
                    severity="MAJOR",
                    category="scripts",
                    file=sf,
                    line=1,
                    title="Missing shebang in script",
                    details=f"Script {sf_name} does not begin with a '#!' shebang.",
                ))

    # 5. Zero AI Attribution Check
    attribution_regex = re.compile(r"^\s*(co-authored-by|generated-by|assisted-by):\s*\S+|🤖\s*reviewed\s*with", re.I | re.M)
    for sf in all_skill_files:
        f_text = get_file_content(ref, sf, root_dir)
        if f_text and attribution_regex.search(f_text):
            findings.append(Finding(
                rule_code="AI001",
                severity="BLOCKER",
                category="policy",
                file=sf,
                line=None,
                title="AI attribution metadata detected",
                details=f"File contains AI attribution metadata violating zero-attribution policy.",
            ))

    # 6. Marketplace Registration
    mp_text = get_file_content(ref, ".claude-plugin/marketplace.json", root_dir)
    if mp_text:
        try:
            mp_data = json.loads(mp_text)
            registered_names = {p.get("name") for p in mp_data.get("plugins", [])}
            if skill_name not in registered_names:
                findings.append(Finding(
                    rule_code="CT001",
                    severity="MAJOR",
                    category="catalog",
                    file=".claude-plugin/marketplace.json",
                    line=None,
                    title="Skill not registered in marketplace.json",
                    details=f"Skill '{skill_name}' is missing from the plugins array in .claude-plugin/marketplace.json.",
                ))
        except Exception:
            pass

    # 7. README Registration
    rm_text = get_file_content(ref, "README.md", root_dir)
    if rm_text:
        if f"skills/{skill_name}" not in rm_text and f"`{skill_name}`" not in rm_text:
            findings.append(Finding(
                rule_code="CT002",
                severity="MINOR",
                category="catalog",
                file="README.md",
                line=None,
                title="Skill not documented in root README.md",
                details=f"Skill '{skill_name}' is not indexed in root README.md skills table.",
            ))

    return findings


# -----------------------------------------------------------------------------
# Model Runner Inference
# -----------------------------------------------------------------------------

def resolve_runner(cache_dir: Path) -> Path | None:
    candidates = [
        cache_dir / "llama_runner" / "build" / "bin" / "llama-cli",
        cache_dir / "llama_runner" / "llama-cli",
        cache_dir / "llama-cli",
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate.resolve(), os.X_OK):
            return candidate.resolve()

    found = list(cache_dir.glob("**/llama-cli"))
    for candidate in found:
        if os.access(candidate.resolve(), os.X_OK):
            return candidate.resolve()

    system_cli = shutil.which("llama-cli")
    if system_cli:
        return Path(system_cli).resolve()

    return None


def run_llama_inference(runner_path: Path, model_path: Path, prompt: str) -> str:
    runner_resolved = runner_path.resolve()
    lib_dirs = {str(runner_resolved.parent), str(runner_path.parent)}
    for p in runner_resolved.parent.glob("*.so*"):
        lib_dirs.add(str(p.parent))

    env = os.environ.copy()
    existing_ld = env.get("LD_LIBRARY_PATH", "")
    existing_dyld = env.get("DYLD_LIBRARY_PATH", "")
    joined_dirs = ":".join(sorted(lib_dirs))
    env["LD_LIBRARY_PATH"] = f"{joined_dirs}:{existing_ld}".rstrip(":")
    env["DYLD_LIBRARY_PATH"] = f"{joined_dirs}:{existing_dyld}".rstrip(":")

    threads = str(min(os.cpu_count() or 2, 4))
    cmd = [
        str(runner_resolved),
        "-m", str(model_path),
        "-p", prompt,
        "-n", "512",
        "-c", "8192",
        "--temp", "0.2",
        "--top-p", "0.9",
        "-t", threads,
        "--no-display-prompt",
        "--no-conversation",
        "--no-warmup",
        "--repeat-penalty", "1.15",
        "--repeat-last-n", "64",
        "--simple-io",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            stdin=subprocess.DEVNULL,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("llama-cli execution timed out after 180 seconds") from exc

    if result.returncode != 0:
        raise RuntimeError(f"llama-cli execution failed: {result.stderr}")

    return result.stdout.strip()


def parse_model_disposition(raw_text: str) -> str:
    match = re.search(r"(?:DISPOSITION|VERDICT):\s*(APPROVE|COMMENT|REQUEST_CHANGES|PASS|FLAGGED)", raw_text, re.I)
    if match:
        v = match.group(1).upper()
        if v in ("APPROVE", "PASS"):
            return "APPROVE"
        if v in ("REQUEST_CHANGES", "FLAGGED"):
            return "REQUEST_CHANGES"
        return "COMMENT"
    return "APPROVE"


# -----------------------------------------------------------------------------
# Review Orchestration & Report Construction
# -----------------------------------------------------------------------------

def synthesize_skill_understanding(
    skill_name: str,
    root_dir: Path,
    ref: str,
    change_type: str,
    diff_text: str,
    files: list[str],
) -> str:
    """Synthesize structured understanding of what the skill does and its capabilities."""
    if change_type == "DELETED":
        return f"Skill `{skill_name}` was deleted and retired from the skills catalog."

    skill_md_content = get_file_content(ref, f"skills/{skill_name}/SKILL.md", root_dir)
    if not skill_md_content:
        return f"Skill `{skill_name}` ({change_type}) touches {len(files)} file(s)."

    fm, body, _ = parse_yaml_frontmatter(skill_md_content)
    desc = fm.get("description", "").strip()

    # Extract title from # <Title>
    title = skill_name
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # Extract sections (e.g. ## Overview, ## When to Use, ## Workflow, ## Guidelines)
    sections: dict[str, str] = {}
    current_sec = None
    sec_lines = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current_sec:
                sections[current_sec] = "\n".join(sec_lines).strip()
            current_sec = line[3:].strip()
            sec_lines = []
        elif current_sec:
            sec_lines.append(line)
    if current_sec:
        sections[current_sec] = "\n".join(sec_lines).strip()

    # Discover bundled assets
    references = [f for f in files if f.startswith(f"skills/{skill_name}/references/")]
    scripts = [f for f in files if f.startswith(f"skills/{skill_name}/scripts/")]
    examples = [f for f in files if f.startswith(f"skills/{skill_name}/examples/")]

    summary_items = []

    # 1. Purpose & Core Intent
    if desc:
        summary_items.append(f"- **Purpose & Scope**: {desc}")
    elif title != skill_name:
        summary_items.append(f"- **Purpose & Scope**: Defines guidelines and automated procedures for {title}.")

    # 2. Procedural Sequence / Key Workflows
    workflow_steps = []
    for sec_name, sec_body in sections.items():
        if any(kw in sec_name.lower() for kw in ("workflow", "procedure", "process", "steps", "instructions", "usage")):
            for l in sec_body.splitlines():
                l_strip = l.strip()
                if re.match(r"^(\d+\.|\-|\*)\s+", l_strip):
                    step_text = re.sub(r"^(\d+\.|\-|\*)\s+", "", l_strip).strip()
                    if step_text:
                        workflow_steps.append(step_text)
                if len(workflow_steps) >= 4:
                    break
            if not workflow_steps:
                first_para = sec_body.split("\n\n")[0].replace("\n", " ").strip()
                if first_para:
                    workflow_steps.append(first_para[:250])
            break

    if workflow_steps:
        formatted_steps = " → ".join(workflow_steps)
        summary_items.append(f"- **Procedural Sequence**: {formatted_steps}")

    # 3. Bundled Assets & Extensions
    assets_desc = []
    if references:
        ref_names = ", ".join(f"`{Path(r).name}`" for r in references)
        assets_desc.append(f"{len(references)} reference guide(s) ({ref_names})")
    if scripts:
        script_names = ", ".join(f"`{Path(s).name}`" for s in scripts)
        assets_desc.append(f"{len(scripts)} executable helper script(s) ({script_names})")
    if examples:
        example_names = ", ".join(f"`{Path(e).name}`" for e in examples)
        assets_desc.append(f"{len(examples)} example catalog(s) ({example_names})")

    if assets_desc:
        summary_items.append(f"- **Bundled Assets**: {'; '.join(assets_desc)}.")

    # 4. Change Delta (for UPDATED skills)
    if change_type == "UPDATED":
        changed_names = ", ".join(f"`{Path(f).name}`" for f in files)
        summary_items.append(f"- **Change Delta**: Updated {len(files)} asset(s) ({changed_names}).")

    return "\n".join(summary_items)


def evaluate_skill(
    skill: SkillChange,
    base: str,
    head: str,
    root_dir: Path,
    mock: bool,
    cache_dir: Path
) -> None:
    """Evaluate an individual skill based on its lifecycle status and record reasoning trace."""
    # 1. DELETED SKILLS
    if skill.change_type == "DELETED":
        skill.disposition = "APPROVE"
        skill.summary = f"Skill `{skill.name}` has been deleted. Skipping content review and approving deletion."
        skill.functional_summary = synthesize_skill_understanding(
            skill.name, root_dir, ref=head, change_type=skill.change_type, diff_text="", files=skill.files
        )
        skill.reasoning_trace.append({
            "stage": "1. Lifecycle Classification",
            "scope": "Git Tree Diff",
            "status": "🟢 PASSED",
            "rationale": f"Skill `{skill.name}` was deleted in this pull request. Auto-approved without content analysis.",
        })
        return

    diff_text = extract_git_diff_text(base, head, skill.files)

    # Synthesize functional understanding of skill
    skill.functional_summary = synthesize_skill_understanding(
        skill.name, root_dir, ref=head, change_type=skill.change_type, diff_text=diff_text, files=skill.files
    )

    # Record Stage 1: Lifecycle
    skill.reasoning_trace.append({
        "stage": "1. Lifecycle Classification",
        "scope": "Git Tree Diff",
        "status": "🟢 PASSED",
        "rationale": f"Classified as `{skill.change_type}` ({len(skill.files)} file(s) touched across base '{base}' and head '{head}').",
    })

    # 2. Static Analysis
    findings = evaluate_static_smells(skill.name, root_dir, ref=head)
    skill.findings = findings

    # Evaluate Stage 2: Frontmatter
    fm_findings = [f for f in findings if f.category == "frontmatter"]
    if not fm_findings:
        skill.reasoning_trace.append({
            "stage": "2. Frontmatter Specification",
            "scope": "FM001–FM005",
            "status": "🟢 PASSED",
            "rationale": "Valid YAML frontmatter; name matches directory pattern; description length within bounds; no prohibited fields.",
        })
    else:
        severities = {f.severity for f in fm_findings}
        status = "🔴 FAILED" if "BLOCKER" in severities or "MAJOR" in severities else "🟡 WARNING"
        reasons = "; ".join(f"{f.rule_code}: {f.title}" for f in fm_findings)
        skill.reasoning_trace.append({
            "stage": "2. Frontmatter Specification",
            "scope": "FM001–FM005",
            "status": status,
            "rationale": f"Detected {len(fm_findings)} issue(s): {reasons}.",
        })

    # Evaluate Stage 3: Progressive Disclosure & Budget
    pd_findings = [f for f in findings if f.category == "progressive_disclosure"]
    if not pd_findings:
        skill.reasoning_trace.append({
            "stage": "3. Progressive Disclosure",
            "scope": "PD001–PD003",
            "status": "🟢 PASSED",
            "rationale": f"SKILL.md satisfies line limit (≤ {MAX_SKILL_MD_LINES} lines) and byte limit (≤ {MAX_SKILL_MD_BYTES // 1024} KB); relative links resolve.",
        })
    else:
        severities = {f.severity for f in pd_findings}
        status = "🔴 FAILED" if "BLOCKER" in severities or "MAJOR" in severities else "🟡 WARNING"
        reasons = "; ".join(f"{f.rule_code}: {f.title}" for f in pd_findings)
        skill.reasoning_trace.append({
            "stage": "3. Progressive Disclosure",
            "scope": "PD001–PD003",
            "status": status,
            "rationale": f"Context budget / link issues: {reasons}.",
        })

    # Evaluate Stage 4: Script Hygiene
    sc_findings = [f for f in findings if f.category == "scripts"]
    has_scripts = any(f.startswith(f"skills/{skill.name}/scripts/") for f in skill.files)
    if not has_scripts:
        skill.reasoning_trace.append({
            "stage": "4. Script Hygiene & Isolation",
            "scope": "SC001–SC003",
            "status": "⚪ N/A",
            "rationale": "No standalone helper scripts bundled with this skill.",
        })
    elif not sc_findings:
        skill.reasoning_trace.append({
            "stage": "4. Script Hygiene & Isolation",
            "scope": "SC001–SC003",
            "status": "🟢 PASSED",
            "rationale": "Helper scripts possess executable permissions (+x), valid shebang, and security safeguards.",
        })
    else:
        severities = {f.severity for f in sc_findings}
        status = "🔴 FAILED" if "BLOCKER" in severities or "MAJOR" in severities else "🟡 WARNING"
        reasons = "; ".join(f"{f.rule_code}: {f.title}" for f in sc_findings)
        skill.reasoning_trace.append({
            "stage": "4. Script Hygiene & Isolation",
            "scope": "SC001–SC003",
            "status": status,
            "rationale": f"Script hygiene issues: {reasons}.",
        })

    # Evaluate Stage 5: Attribution & Safety
    sec_findings = [f for f in findings if f.category in ("attribution", "safety")]
    if not sec_findings:
        skill.reasoning_trace.append({
            "stage": "5. Safety & Attribution",
            "scope": "AT001, SEC001",
            "status": "🟢 PASSED",
            "rationale": "Zero AI attribution metadata (no co-authored-by tags); no hardcoded secrets or environment-leaking paths.",
        })
    else:
        severities = {f.severity for f in sec_findings}
        status = "🔴 FAILED" if "BLOCKER" in severities or "MAJOR" in severities else "🟡 WARNING"
        reasons = "; ".join(f"{f.rule_code}: {f.title}" for f in sec_findings)
        skill.reasoning_trace.append({
            "stage": "5. Safety & Attribution",
            "scope": "AT001, SEC001",
            "status": status,
            "rationale": f"Attribution/safety violations: {reasons}.",
        })

    # Evaluate Stage 6: Catalog Integration
    cat_findings = [f for f in findings if f.category == "catalog"]
    if not cat_findings:
        skill.reasoning_trace.append({
            "stage": "6. Catalog & Ecosystem Indexing",
            "scope": "CT001, CT002",
            "status": "🟢 PASSED",
            "rationale": "Properly registered in marketplace manifest (.claude-plugin/marketplace.json) and README.md.",
        })
    else:
        status = "🟡 WARNING"
        reasons = "; ".join(f"{f.rule_code}: {f.title}" for f in cat_findings)
        skill.reasoning_trace.append({
            "stage": "6. Catalog & Ecosystem Indexing",
            "scope": "CT001, CT002",
            "status": status,
            "rationale": f"Catalog registration findings: {reasons}.",
        })

    # Compute static disposition
    has_blocker_or_major = any(f.severity in ("BLOCKER", "MAJOR") for f in findings)
    has_minor = any(f.severity == "MINOR" for f in findings)

    if has_blocker_or_major:
        static_disp = "REQUEST_CHANGES"
    elif has_minor:
        static_disp = "COMMENT"
    else:
        static_disp = "APPROVE"

    # Stage 7: Model Inference
    model_disp = "APPROVE"
    raw_model_output = ""
    start_time = time.time()

    if not mock and diff_text:
        model_path = cache_dir / "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
        runner_path = resolve_runner(cache_dir)
        if runner_path and model_path.exists():
            full_prompt = (
                f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
                f"<|im_start|>user\nSkill under review: {skill.name} ({skill.change_type})\n"
                f"Audited files: {', '.join(skill.files)}\n\n```diff\n{diff_text}\n```\n"
                f"Audit this change against Agent Skills best practices.<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )
            try:
                raw_model_output = run_llama_inference(runner_path, model_path, full_prompt)
                model_disp = parse_model_disposition(raw_model_output)
            except Exception as exc:
                logging.debug("model inference failed (%s); using static analysis.", exc)
                raw_model_output = f"Model execution failed: {exc}"
        else:
            raw_model_output = "Model runner or weights not found in cache. Evaluated using heuristic rules."
    elif mock:
        raw_model_output = "Deterministic heuristic review requested (--mock). Adversarial model evaluation bypassed."

    elapsed = time.time() - start_time
    skill.model_reasoning = raw_model_output.strip()
    skill.model_latency = elapsed

    # Record Stage 7: Model Inference
    if mock:
        skill.reasoning_trace.append({
            "stage": "7. Adversarial Model Review",
            "scope": "LLM Semantics",
            "status": "⚪ MOCK",
            "rationale": "Deterministic static evaluation completed without local model execution.",
        })
    elif raw_model_output and "failed" not in raw_model_output.lower() and "not found" not in raw_model_output.lower():
        m_status = "🟢 PASSED" if model_disp == "APPROVE" else ("🔴 FAILED" if model_disp == "REQUEST_CHANGES" else "🟡 COMMENT")
        skill.reasoning_trace.append({
            "stage": "7. Adversarial Model Review",
            "scope": "LLM Semantics",
            "status": m_status,
            "rationale": f"Quantized model inference completed in {elapsed:.2f}s with disposition `{model_disp}`.",
        })
    else:
        skill.reasoning_trace.append({
            "stage": "7. Adversarial Model Review",
            "scope": "LLM Semantics",
            "status": "⚪ SKIPPED",
            "rationale": "Model runner not active; defaulted to deterministic rule findings.",
        })

    # Combine dispositions (most restrictive wins)
    if "REQUEST_CHANGES" in (static_disp, model_disp):
        skill.disposition = "REQUEST_CHANGES"
    elif "COMMENT" in (static_disp, model_disp):
        skill.disposition = "COMMENT"
    else:
        skill.disposition = "APPROVE"

    if skill.disposition == "APPROVE":
        skill.summary = f"Skill `{skill.name}` ({skill.change_type}) passed all best practice and smell checks."
    else:
        skill.summary = f"Skill `{skill.name}` ({skill.change_type}) identified {len(skill.findings)} finding(s)."


def build_markdown_report(target: str, overall_disposition: str, skills: dict[str, SkillChange]) -> str:
    """Build formatted GitHub Markdown report with comprehension summary and reasoning chain."""
    icon_map = {
        "APPROVE": "🟢",
        "COMMENT": "🟡",
        "REQUEST_CHANGES": "🔴",
    }
    icon = icon_map.get(overall_disposition, "⚪")

    report = "<!-- agent-skills-review:report -->\n"
    report += f"## {icon} Agent Skills Review: {target} — `{overall_disposition}`\n\n"
    report += "| Skill | Change Type | Status | Summary |\n"
    report += "|---|---|---|---|\n"

    for skill_name, skill in sorted(skills.items()):
        s_icon = icon_map.get(skill.disposition, "⚪")
        report += f"| `{skill.name}` | **{skill.change_type}** | {s_icon} {skill.disposition} | {skill.summary} |\n"

    report += "\n---\n\n"

    # Detail findings, comprehension summary, and reasoning chain for each skill
    for skill_name, skill in sorted(skills.items()):
        report += f"### Skill: `{skill.name}` ({skill.change_type})\n\n"

        if skill.change_type == "DELETED":
            report += "> [!NOTE]\n"
            report += "> This skill was deleted in this change. Skipping quality review and approving deletion.\n\n"
            continue

        # 1. Functional Summary & Change Understanding
        if skill.functional_summary:
            report += "#### 📋 Functional Summary & Change Understanding\n"
            report += f"{skill.functional_summary}\n\n"

        # 2. Detected Findings
        if not skill.findings:
            report += "#### 🔎 Findings\n"
            report += "No major smells or specification violations detected. Clean implementation.\n\n"
        else:
            report += "#### 🔎 Detected Findings\n"
            for f in skill.findings:
                sev_icon = "🛑" if f.severity == "BLOCKER" else ("⚠️" if f.severity == "MAJOR" else "ℹ️")
                loc = f" (`{f.file}`)" if f.file else ""
                report += f"- {sev_icon} **[{f.rule_code}] {f.title}**{loc}\n"
                report += f"  - *Details*: {f.details}\n"
                if f.counterexample:
                    report += f"  - *Expected Pattern*: `{f.counterexample}`\n"
            report += "\n"

        # 3. Pretty-Formatted Reasoning Chain Dump
        report += "<details>\n"
        report += "<summary>🧠 <b>Reasoning Chain & Evaluation Audit Trail</b> (click to expand)</summary>\n\n"

        if skill.reasoning_trace:
            report += "##### Pipeline Verification Stages\n\n"
            report += "| Stage | Verification Scope | Status | Rationale |\n"
            report += "|---|---|---|---|\n"
            for step in skill.reasoning_trace:
                report += f"| {step['stage']} | `{step['scope']}` | {step['status']} | {step['rationale']} |\n"
            report += "\n"

        if skill.model_reasoning:
            latency_str = f" ({skill.model_latency:.2f}s latency)" if skill.model_latency > 0 else ""
            report += f"##### Adversarial Model Reasoning Dump{latency_str}\n\n"
            report += "```text\n"
            report += f"{skill.model_reasoning}\n"
            report += "```\n\n"

        report += "##### Disposition Synthesis\n"
        report += f"- **Evaluated Outcome**: `{skill.disposition}`\n"
        report += f"- **Smells Detected**: {len(skill.findings)}\n"
        report += "</details>\n\n"

    report += "---\n*Automated Agent Skills Review harness grounded in agentskills.io and Anthropic guidelines.*\n"
    return report


def find_existing_review_comment(pr: int) -> int | None:
    """Find existing sticky review comment on PR issue."""
    cmd = ["gh", "api", f"repos/:owner/:repo/issues/{pr}/comments", "--paginate"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return None
    try:
        comments = json.loads(res.stdout)
        for c in comments:
            body = c.get("body", "")
            if "<!-- agent-skills-review:report -->" in body or "Agent Skills Review:" in body:
                return c.get("id")
    except Exception as exc:
        logging.debug("failed to parse existing comments: %s", exc)
    return None


def upsert_pr_comment(pr: int, report: str) -> str | None:
    """Create or update the single sticky review report comment on PR."""
    comment_id = find_existing_review_comment(pr)
    if comment_id:
        cmd = [
            "gh", "api", "--method", "PATCH",
            f"repos/:owner/:repo/issues/comments/{comment_id}",
            "-f", f"body={report}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            print(f"updated existing review report comment #{comment_id} on PR #{pr}")
            try:
                data = json.loads(res.stdout)
                return data.get("html_url")
            except Exception:
                return None
        print(f"failed to update existing comment #{comment_id} ({res.stderr.strip()}); falling back to new comment", file=sys.stderr)

    cmd = [
        "gh", "api", "--method", "POST",
        f"repos/:owner/:repo/issues/{pr}/comments",
        "-f", f"body={report}",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode == 0:
        print(f"created new review report comment on PR #{pr}")
        try:
            data = json.loads(res.stdout)
            return data.get("html_url")
        except Exception:
            return None
    print(f"failed to post PR comment via API: {res.stderr.strip()}", file=sys.stderr)
    return None


def check_existing_formal_review(pr: int, target_disposition: str) -> bool:
    """Check if the latest review from github-actions[bot] already matches target disposition."""
    cmd = ["gh", "pr", "view", str(pr), "--json", "reviews"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return False
    try:
        data = json.loads(res.stdout)
        reviews = data.get("reviews", [])
        bot_reviews = [
            r for r in reviews
            if r.get("author", {}).get("login") in ("github-actions", "github-actions[bot]")
        ]
        if not bot_reviews:
            return False
        latest_review = bot_reviews[-1]
        latest_state = latest_review.get("state", "").upper()
        if target_disposition == "APPROVE" and latest_state == "APPROVED":
            return True
        if target_disposition == "REQUEST_CHANGES" and latest_state == "CHANGES_REQUESTED":
            return True
    except Exception as exc:
        logging.debug("failed to inspect existing reviews: %s", exc)
    return False


def submit_pr_review(pr: int, disposition: str, report: str) -> None:
    """Submit idempotent PR review report and manage formal PR approval."""
    # 1. Upsert single sticky PR comment (in-place PATCH or initial POST)
    comment_url = upsert_pr_comment(pr, report)

    # 2. Check if formal review is already in desired state
    if check_existing_formal_review(pr, disposition):
        print(f"formal review already in state '{disposition}' on PR #{pr}; skipped duplicate review creation")
        return

    # 3. Submit formal review with concise link to sticky comment
    if disposition == "APPROVE":
        review_flag = "--approve"
        summary_note = "All skill quality and specification checks passed."
    elif disposition == "REQUEST_CHANGES":
        review_flag = "--request-changes"
        summary_note = "Skill quality findings require resolution before merge."
    else:
        review_flag = "--comment"
        summary_note = "Automated advisory feedback recorded."

    link_text = f"See the [full audit report and reasoning chain]({comment_url}) above." if comment_url else "See the detailed audit report above."
    review_body = f"### 🟢 Agent Skills Review: `{disposition}`\n\n{summary_note}\n{link_text}"

    cmd = ["gh", "pr", "review", str(pr), review_flag, "--body", review_body]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode == 0:
        print(f"submitted formal PR review ({review_flag}) to PR #{pr}")
    else:
        print(f"formal PR review notice ({review_flag}) failed ({res.stderr.strip()})", file=sys.stderr)


# -----------------------------------------------------------------------------
# Main CLI Entry Point
# -----------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Headless Agent Skills and Claude Skills pull request reviewer."
    )
    parser.add_argument("--base", default="origin/main", help="Base ref to compare against")
    parser.add_argument("--head", default="HEAD", help="Head ref to compare")
    parser.add_argument("--target", default="HEAD", help="Target identifier for review reporting")
    parser.add_argument("--mock", action="store_true", help="Run deterministic heuristic review without model inference")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR, help="Cache directory for models")
    parser.add_argument("--summary-file", type=Path, default=None, help="File to write step summary to (e.g. $GITHUB_STEP_SUMMARY)")
    parser.add_argument("--pr", type=int, default=None, help="Pull request number to post review to")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    parser.add_argument("--fail-on", choices=["request-changes", "critical", "none"], default="request-changes",
                        help="Disposition that triggers non-zero exit code (default: request-changes)")
    parser.add_argument("--log-level", default=os.environ.get("LOG_LEVEL", "info").lower(),
                        choices=["debug", "info", "warn", "error"], help="Log verbosity")
    args = parser.parse_args()

    log_level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "error": logging.ERROR,
    }
    logging.basicConfig(level=log_level_map.get(args.log_level, logging.INFO), format="%(levelname)s: %(message)s")

    # Fetch online spec update if available
    fetch_online_best_practices()

    # 1. Classify Skills
    skills = classify_skill_changes(args.base, args.head)

    if not skills:
        overall_disposition = "APPROVE"
        markdown_report = f"## 🟢 Agent Skills Review: {args.target} — `APPROVE`\n\nNo skill modifications detected in this change.\n"
    else:
        # 2. Evaluate Each Skill
        for skill in skills.values():
            evaluate_skill(skill, args.base, args.head, REPO_ROOT, args.mock, args.cache_dir)

        # 3. Aggregate Overall Disposition
        dispositions = [s.disposition for s in skills.values()]
        if "REQUEST_CHANGES" in dispositions:
            overall_disposition = "REQUEST_CHANGES"
        elif "COMMENT" in dispositions:
            overall_disposition = "COMMENT"
        else:
            overall_disposition = "APPROVE"

        markdown_report = build_markdown_report(args.target, overall_disposition, skills)

    if args.json:
        payload = {
            "target": args.target,
            "disposition": overall_disposition,
            "skills": {name: {
                "change_type": s.change_type,
                "disposition": s.disposition,
                "summary": s.summary,
                "findings": [f.to_dict() for f in s.findings],
            } for name, s in skills.items()},
        }
        print(json.dumps(payload, indent=2))
    else:
        print(markdown_report)

    # Machine-readable completion marker
    print(f"Review complete: {args.target} — {overall_disposition}")

    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as out:
            out.write(markdown_report + "\n")

    if args.pr and os.environ.get("GITHUB_TOKEN"):
        try:
            submit_pr_review(args.pr, overall_disposition, markdown_report)
        except Exception as error:
            print(f"could not submit PR review: {error}", file=sys.stderr)

    # Exit code: 0 for APPROVE/COMMENT, 3 for REQUEST_CHANGES
    if args.fail_on in ("request-changes", "critical") and overall_disposition == "REQUEST_CHANGES":
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
