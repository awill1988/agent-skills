#!/usr/bin/env python3
"""
scan_comments.py — Scan source code comments for verbosity, procedural narration,
and redundancy, recommending Domain-Driven Design (DDD) simplifications.

Grounded in Eric Evans' Domain-Driven Design:
- Ch 2: Documents and Diagrams (Code specifies behavior; comments illuminate meaning/intent).
- Ch 10: Supple Design (Intention-Revealing Interfaces & Assertions/Invariants).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import re
import sys
from typing import Iterator

# -----------------------------------------------------------------------------
# Configuration & Constants
# -----------------------------------------------------------------------------

DEFAULT_EXTENSIONS = {
    ".rs", ".swift", ".py", ".ts", ".tsx", ".js", ".c", ".cpp", ".h", ".hpp", ".slint"
}

IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "target", "build", ".build",
    "DerivedData", "vendor", "dist", ".slint-build", ".venv", "venv", "__pycache__"
}

# Procedural narrative phrases that indicate "how/what" re-narration rather than "why".
PROCEDURAL_PATTERNS = [
    re.compile(r"\b(first|firstly)\b.*?\b(then|next|afterwards)\b", re.I),
    re.compile(r"\b(step\s+[0-9]+|step\s+[a-z])\b", re.I),
    re.compile(r"\bwe\s+(then|now|first|next|finally|loop|iterate|check|ensure|call|set)\b", re.I),
    re.compile(r"\b(loop|iterate)\s+(through|over|across)\b", re.I),
    re.compile(r"\b(check|checks|checking)\s+(if|whether)\b", re.I),
    re.compile(r"\bthis\s+(function|method|closure|routine|block|file)\s+(takes|returns|will|is\s+responsible\s+for|handles|does)\b", re.I),
    re.compile(r"\b(in\s+order\s+to\s+do\s+this|to\s+accomplish\s+this)\b", re.I),
    re.compile(r"\b(returns\s+true\s+if|returns\s+false\s+if)\b", re.I),
    re.compile(r"\b(increment|decrement|assign|initialize)\s+(the|counter|variable|field)\b", re.I),
]

# Signals of high-value "Why" and domain intent.
WHY_SIGNALS = [
    re.compile(r"\b(invariant|invariants)\b", re.I),
    re.compile(r"\b(rationale|reason)\b", re.I),
    re.compile(r"\b(because|due\s+to|necessitated\s+by)\b", re.I),
    re.compile(r"\b(adr[-\s]?[0-9]+)\b", re.I),
    re.compile(r"\b(contract|precondition|postcondition|guarantee)\b", re.I),
    re.compile(r"\b(seam|boundary|layer\s+[123])\b", re.I),
    re.compile(r"\b(workaround|quirk|errata|hardware|kernel|driver)\b", re.I),
    re.compile(r"\b(concurrency|thread-safe|non-reentrant|deadlock|atomicity)\b", re.I),
    re.compile(r"\b(odbl|license|provenance|attribution|rights)\b", re.I),
    re.compile(r"\b(safety|soundness|overflow|underflow|endianness)\b", re.I),
]

# Formatting filler patterns (decorative rules, ASCII boxes).
DECORATIVE_PATTERNS = [
    re.compile(r"^[/\\*#\s-]{4,}$"),
    re.compile(r"^[=~*#\-_]{4,}$"),
]

# -----------------------------------------------------------------------------
# Data Structures
# -----------------------------------------------------------------------------

@dataclass
class CommentBlock:
    file_path: Path
    start_line: int
    end_line: int
    lines: list[str]
    comment_type: str  # "line", "doc", "block", "docstring"
    following_code: str = ""

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    @property
    def cleaned_text(self) -> str:
        cleaned = []
        for line in self.lines:
            # Strip comment markers
            s = line.strip()
            if s.startswith("///"):
                s = s[3:]
            elif s.startswith("//!"):
                s = s[3:]
            elif s.startswith("//"):
                s = s[2:]
            elif s.startswith("#"):
                s = s[1:]
            elif s.startswith("/*") or s.startswith("/**"):
                s = re.sub(r"^/\*+\s*", "", s)
                s = re.sub(r"\*+/$", "", s)
            elif s.startswith("*"):
                s = re.sub(r"^\*+\s*", "", s)
            elif s.startswith('"""') or s.startswith("'''"):
                s = s.strip("\"'")
            cleaned.append(s.strip())
        return " ".join([c for c in cleaned if c])


@dataclass
class Finding:
    block: CommentBlock
    smell: str
    severity: str  # "HIGH", "MEDIUM", "LOW"
    recommendation: str
    estimated_saved_lines: int
    matched_patterns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file": str(self.block.file_path),
            "start_line": self.block.start_line,
            "end_line": self.block.end_line,
            "line_count": self.block.line_count,
            "comment_type": self.block.comment_type,
            "smell": self.smell,
            "severity": self.severity,
            "recommendation": self.recommendation,
            "lines_saved": self.estimated_saved_lines,
            "snippet": self.block.cleaned_text[:160] + ("..." if len(self.block.cleaned_text) > 160 else ""),
            "following_code": self.block.following_code[:120],
        }


# -----------------------------------------------------------------------------
# Parser
# -----------------------------------------------------------------------------

def extract_comment_blocks(file_path: Path) -> Iterator[CommentBlock]:
    """Parse comments and docstrings from source file."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logging.debug("error reading %s: %s", file_path, exc)
        return

    ext = file_path.suffix.lower()
    raw_lines = content.splitlines()
    total_lines = len(raw_lines)

    if ext == ".py":
        yield from _extract_python_comments(file_path, raw_lines)
    else:
        yield from _extract_c_style_comments(file_path, raw_lines)


def _extract_c_style_comments(file_path: Path, raw_lines: list[str]) -> Iterator[CommentBlock]:
    """Parse line comments (//, ///, //!) and block comments (/* ... */)."""
    i = 0
    total = len(raw_lines)

    while i < total:
        line = raw_lines[i]
        stripped = line.strip()

        # Check for block comment /* ... */
        if stripped.startswith("/*"):
            start_line = i + 1
            block_lines = [line]
            is_doc = stripped.startswith("/**")
            
            # Check single-line block comment /* ... */
            if "*/" in stripped and not stripped.endswith("/*"):
                end_line = start_line
                i += 1
            else:
                i += 1
                while i < total:
                    bline = raw_lines[i]
                    block_lines.append(bline)
                    if "*/" in bline:
                        break
                    i += 1
                end_line = i + 1
                i += 1

            following = _find_following_code(raw_lines, end_line)
            yield CommentBlock(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                lines=block_lines,
                comment_type="doc" if is_doc else "block",
                following_code=following,
            )
            continue

        # Check for line comment //, ///, //!
        if stripped.startswith("//"):
            start_line = i + 1
            is_doc = stripped.startswith("///") or stripped.startswith("//!")
            comment_prefix = "///" if stripped.startswith("///") else ("//!" if stripped.startswith("//!") else "//")
            block_lines = [line]

            i += 1
            while i < total:
                next_line = raw_lines[i]
                next_stripped = next_line.strip()
                if (comment_prefix == "///" and next_stripped.startswith("///")) or \
                   (comment_prefix == "//!" and next_stripped.startswith("//!")) or \
                   (comment_prefix == "//" and next_stripped.startswith("//") and not next_stripped.startswith("///") and not next_stripped.startswith("//!")):
                    block_lines.append(next_line)
                    i += 1
                elif next_stripped == "" and i + 1 < total and raw_lines[i + 1].strip().startswith(comment_prefix):
                    # Empty line separating comment paragraphs within same block
                    block_lines.append(next_line)
                    i += 1
                else:
                    break

            end_line = start_line + len(block_lines) - 1
            following = _find_following_code(raw_lines, end_line)
            yield CommentBlock(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                lines=block_lines,
                comment_type="doc" if is_doc else "line",
                following_code=following,
            )
            continue

        i += 1


def _extract_python_comments(file_path: Path, raw_lines: list[str]) -> Iterator[CommentBlock]:
    """Parse Python comments (#) and triple-quoted docstrings."""
    i = 0
    total = len(raw_lines)

    while i < total:
        line = raw_lines[i]
        stripped = line.strip()

        # Check for line comment #
        if stripped.startswith("#"):
            start_line = i + 1
            block_lines = [line]
            i += 1
            while i < total:
                next_line = raw_lines[i]
                next_stripped = next_line.strip()
                if next_stripped.startswith("#"):
                    block_lines.append(next_line)
                    i += 1
                elif next_stripped == "" and i + 1 < total and raw_lines[i + 1].strip().startswith("#"):
                    block_lines.append(next_line)
                    i += 1
                else:
                    break
            end_line = start_line + len(block_lines) - 1
            following = _find_following_code(raw_lines, end_line)
            yield CommentBlock(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                lines=block_lines,
                comment_type="line",
                following_code=following,
            )
            continue

        # Check for docstring """ or '''
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            start_line = i + 1
            block_lines = [line]

            # Single line docstring
            if len(stripped) > 3 and stripped.endswith(quote):
                end_line = start_line
                i += 1
            else:
                i += 1
                while i < total:
                    dline = raw_lines[i]
                    block_lines.append(dline)
                    if quote in dline:
                        break
                    i += 1
                end_line = i + 1
                i += 1

            following = _find_following_code(raw_lines, end_line)
            yield CommentBlock(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                lines=block_lines,
                comment_type="docstring",
                following_code=following,
            )
            continue

        i += 1


def _find_following_code(raw_lines: list[str], end_line_1_indexed: int) -> str:
    """Find the first non-comment non-empty line of code following the comment block."""
    idx = end_line_1_indexed
    while idx < len(raw_lines):
        line = raw_lines[idx].strip()
        if line and not line.startswith("//") and not line.startswith("#") and not line.startswith("/*") and not line.startswith("*"):
            return line
        idx += 1
    return ""


# -----------------------------------------------------------------------------
# Analysis & DDD Heuristics
# -----------------------------------------------------------------------------

def analyze_block(block: CommentBlock, min_lines: int = 3) -> Finding | None:
    """Evaluate comment block against Domain-Driven Design principles."""
    cleaned = block.cleaned_text
    if not cleaned:
        return None

    # Filter out pure decorative dividers
    non_decorative = [l for l in block.lines if not any(p.match(l.strip()) for p in DECORATIVE_PATTERNS)]
    if not non_decorative and block.line_count >= 2:
        return Finding(
            block=block,
            smell="DECORATIVE_DIVIDER",
            severity="LOW",
            recommendation="DELETE: eliminate visual banner lines; group code by conceptual contours instead.",
            estimated_saved_lines=block.line_count,
            matched_patterns=["decorative separator"],
        )

    # Filter by minimum line threshold
    if block.line_count < min_lines:
        return None

    # Check for "Why" signals
    has_why = any(p.search(cleaned) for p in WHY_SIGNALS)

    # 1. Procedural Re-Narration (Play-by-Play Announcer)
    procedural_matches = [p.pattern for p in PROCEDURAL_PATTERNS if p.search(cleaned)]
    if procedural_matches:
        if has_why:
            # Contains both: recommend distilling to only the invariant/why
            saved = max(1, block.line_count - 1)
            return Finding(
                block=block,
                smell="PROCEDURAL_WITH_INVARIANT",
                severity="MEDIUM",
                recommendation="DISTILL_TO_INVARIANT: eliminate procedural walkthrough; retain only the core invariant or rationale.",
                estimated_saved_lines=saved,
                matched_patterns=procedural_matches,
            )
        else:
            # Pure procedural re-narration
            saved = block.line_count if block.comment_type == "line" else max(1, block.line_count - 1)
            return Finding(
                block=block,
                smell="PROCEDURAL_NARRATION",
                severity="HIGH",
                recommendation="DELETE_OR_DISTILL: code is the exact specification of behavior. Express intent via Intention-Revealing Selectors and remove procedural step-by-step narration.",
                estimated_saved_lines=saved,
                matched_patterns=procedural_matches,
            )

    # 2. Redundant Signature Echo (The Echo Chamber)
    if block.following_code:
        norm_code = re.sub(r"[^a-zA-Z0-9_]", " ", block.following_code).lower().split()
        norm_comment = re.sub(r"[^a-zA-Z0-9_]", " ", cleaned).lower().split()
        if norm_code and norm_comment:
            # Look for function/struct name in comment
            name_candidates = [token for token in norm_code if len(token) > 3 and token not in {"func", "function", "pub", "fn", "def", "async", "mut", "class", "struct", "enum"}]
            if name_candidates:
                target_name = name_candidates[0]
                # If comment is basically just the function name rephrased
                if target_name in norm_comment and len(norm_comment) < 15 and not has_why:
                    return Finding(
                        block=block,
                        smell="REDUNDANT_SIGNATURE_ECHO",
                        severity="MEDIUM",
                        recommendation="DELETE: comment duplicates the Intention-Revealing name and parameter types of the declaration.",
                        estimated_saved_lines=block.line_count,
                        matched_patterns=[f"duplicates symbol '{target_name}'"],
                    )

    # 3. Verbose Explanation without "Why"
    if block.line_count >= 5 and not has_why:
        saved = max(1, block.line_count - 1)
        return Finding(
            block=block,
            smell="VERBOSE_HOW_WITHOUT_WHY",
            severity="MEDIUM",
            recommendation="DISTILL_TO_RATIONALE: multi-line explanation lacks domain invariants or rationale. Distill into a 1-line statement of why this exists, or let code speak for itself.",
            estimated_saved_lines=saved,
            matched_patterns=["lengthy explanation without invariant"],
        )

    # 4. Low Information Density (Bloated Docstring / Line Comment)
    tokens = cleaned.split()
    tokens_per_line = len(tokens) / block.line_count if block.line_count > 0 else 0
    if block.line_count >= 4 and tokens_per_line < 4.0 and not has_why:
        return Finding(
            block=block,
            smell="LOW_INFORMATION_DENSITY",
            severity="LOW",
            recommendation="CONDENSE: vertical layout contains low information density; consolidate into a single concise invariant line.",
            estimated_saved_lines=max(1, block.line_count - 1),
            matched_patterns=[f"{tokens_per_line:.1f} words per line"],
        )

    return None


# -----------------------------------------------------------------------------
# Reporting & CLI
# -----------------------------------------------------------------------------

def scan_path(target_path: Path, min_lines: int, extensions: set[str]) -> list[Finding]:
    """Scan file or directory for comment simplification candidates."""
    findings: list[Finding] = []

    if target_path.is_file():
        files = [target_path]
    else:
        files = []
        for root, dirs, filenames in os.walk(target_path):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for fn in filenames:
                p = Path(root) / fn
                if p.suffix.lower() in extensions:
                    files.append(p)

    for f in sorted(files):
        logging.debug("scanning %s", f)
        for block in extract_comment_blocks(f):
            finding = analyze_block(block, min_lines=min_lines)
            if finding:
                findings.append(finding)

    return findings


def print_text_report(findings: list[Finding], max_findings: int = 50) -> None:
    """Print readable terminal report with color and clear DDD advice."""
    if not findings:
        print("no comment simplification candidates found (clean codebase).")
        return

    total_scanned_blocks = len(findings)
    total_lines = sum(f.block.line_count for f in findings)
    total_saved = sum(f.estimated_saved_lines for f in findings)
    pct = (total_saved / total_lines * 100) if total_lines > 0 else 0

    print("================================================================================")
    print("CODE-DOCUMENTATION SIMPLIFICATION REPORT (DOMAIN-DRIVEN DESIGN AUDIT)")
    print("================================================================================")
    print(f"Candidates Found: {total_scanned_blocks}")
    print(f"Current Comment Lines: {total_lines}")
    print(f"Estimated Reducible Lines: {total_saved} ({pct:.1f}% reduction)")
    print("--------------------------------------------------------------------------------")

    for idx, f in enumerate(findings[:max_findings], start=1):
        rel_path = f.block.file_path
        try:
            rel_path = f.block.file_path.relative_to(Path.cwd())
        except ValueError:
            pass

        print(f"\n[{idx}] {rel_path}:{f.block.start_line}-{f.block.end_line} ({f.block.line_count} lines, {f.severity})")
        print(f"    Smell:          {f.smell}")
        print(f"    Action:         {f.recommendation}")
        print(f"    Lines Saved:    ~{f.estimated_saved_lines} lines")
        print(f"    Snippet:        \"{f.block.cleaned_text[:120]}...\"")
        if f.block.following_code:
            print(f"    Following Code: {f.block.following_code[:100]}")

    if len(findings) > max_findings:
        print(f"\n... and {len(findings) - max_findings} more findings (use --max-findings to increase).")

    print("\n--------------------------------------------------------------------------------")
    print("DDD SIMPLIFICATION RULES OF THUMB:")
    print("  1. Code specifies exact behavior; comments illuminate intent, invariants, and why.")
    print("  2. Intention-Revealing Interfaces replace procedural 'how/what' walkthroughs.")
    print("  3. Express state constraints as Assertions/Invariants (e.g. '// Invariant: ...').")
    print("  4. If an identifier or type can express the concept, rename it and delete the comment.")
    print("================================================================================")


def main() -> int:
    default_log_level = os.environ.get("LOG_LEVEL", "info").lower()
    log_level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }

    parser = argparse.ArgumentParser(
        description="Scan code comments for verbosity and procedural narration, proposing DDD simplifications."
    )
    parser.add_argument(
        "--path", "-p",
        type=Path,
        default=Path("."),
        help="Path to file or directory to scan (default: current directory)."
    )
    parser.add_argument(
        "--min-lines", "-m",
        type=int,
        default=3,
        help="Minimum comment lines in a block to trigger analysis (default: 3)."
    )
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json", "summary"],
        default="text",
        help="Output format (default: text)."
    )
    parser.add_argument(
        "--ext",
        type=str,
        default="",
        help="Comma-separated file extensions to scan (e.g. .rs,.swift,.py)."
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        default=50,
        help="Maximum findings to display in text report (default: 50)."
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warn", "error"],
        default=default_log_level,
        help="Log verbosity level (default: from LOG_LEVEL or info)."
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=log_level_map.get(args.log_level, logging.INFO),
        format="%(levelname)s: %(message)s"
    )

    if args.ext:
        extensions = {e.strip() if e.strip().startswith(".") else f".{e.strip()}" for e in args.ext.split(",")}
    else:
        extensions = DEFAULT_EXTENSIONS

    findings = scan_path(args.path, min_lines=args.min_lines, extensions=extensions)

    if args.format == "json":
        data = {
            "total_findings": len(findings),
            "total_lines": sum(f.block.line_count for f in findings),
            "estimated_saved_lines": sum(f.estimated_saved_lines for f in findings),
            "findings": [f.to_dict() for f in findings],
        }
        print(json.dumps(data, indent=2))
    elif args.format == "summary":
        total_lines = sum(f.block.line_count for f in findings)
        total_saved = sum(f.estimated_saved_lines for f in findings)
        pct = (total_saved / total_lines * 100) if total_lines > 0 else 0
        print(f"findings: {len(findings)} | comment_lines: {total_lines} | lines_saved: {total_saved} ({pct:.1f}%)")
    else:
        print_text_report(findings, max_findings=args.max_findings)

    return 0


if __name__ == "__main__":
    sys.exit(main())
