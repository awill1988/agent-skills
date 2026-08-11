#!/usr/bin/env python3
"""scan claude code session transcripts for one standup window.

emits a markdown digest of the day's typed prompts, turn conclusions, decision
points, and file edits — the layer that prs and tickets do not record.

the jsonl entry format is internal to claude code and changes between releases,
so every field read here is optional: a miss is counted and skipped, never
raised. non-zero miss counts in the digest header mean the schema moved.
"""

import argparse
import collections
import glob
import json
import os
import sys
from datetime import datetime, timezone

# clock times render in the machine's own zone, derived rather than named — the
# reader's day is whatever their laptop says it is.
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
ASK_TOOL = "AskUserQuestion"
ANSWER_PREFIX = "Your questions have been answered:"


class Misses:
    """counts of records dropped for shape reasons — schema-drift canary."""

    def __init__(self):
        self.unparseable_lines = 0
        self.missing_timestamp = 0
        self.unreadable_files = 0

    def any(self):
        return bool(self.unparseable_lines or self.missing_timestamp or self.unreadable_files)

    def render(self):
        return (
            f"{self.unparseable_lines} unparseable lines, "
            f"{self.missing_timestamp} records missing timestamp, "
            f"{self.unreadable_files} unreadable files"
        )


def default_projects_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "projects")


def local_hhmm(ts):
    """iso-8601 utc timestamp -> local HH:MM, or '--:--' if unparseable."""
    try:
        return (
            datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%H:%M")
        )
    except (ValueError, AttributeError):
        return "--:--"


def local_date(ts):
    try:
        return (
            datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
        )
    except (ValueError, AttributeError):
        return "?"


def local_zone_label():
    """the machine's current zone abbreviation, e.g. MDT — never assumed."""
    return datetime.now().astimezone().strftime("%Z")


def normalize_bound(value, label):
    """accept iso-8601 with or without a trailing Z; return a comparable utc string."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        sys.exit(f"error: --{label} is not iso-8601: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def record_time(rec, misses):
    ts = rec.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        misses.missing_timestamp += 1
        return None


def text_of(content):
    """tool_result content is a string or a list of blocks; flatten to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def collapse(text, limit):
    """squeeze whitespace and truncate — digests are read, not diffed."""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rstrip() + " …"


def parse_answer(result_text):
    """pull (question, chosen) pairs out of an AskUserQuestion tool_result.

    the result reads: Your questions have been answered: "<q>"="<a>", "<q>"="<a>".
    trailing prose ('selected preview:', 'You can now continue…') is discarded.
    """
    if ANSWER_PREFIX not in result_text:
        return []
    body = result_text.split(ANSWER_PREFIX, 1)[1]
    pairs = []
    chunks = body.split('"')
    # chunks alternate: sep, question, '=', answer, sep, question, '=', answer, …
    i = 1
    while i + 2 < len(chunks):
        question, sep, answer = chunks[i], chunks[i + 1], chunks[i + 2]
        if sep.strip() == "=":
            pairs.append((question.strip(), answer.strip()))
            i += 3
        else:
            i += 1
    return pairs


def read_records(path, misses):
    try:
        with open(path, errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        misses.unreadable_files += 1
        return []
    records = []
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            misses.unparseable_lines += 1
            continue
        if isinstance(rec, dict):
            records.append(rec)
    return records


def scan_file(path, floor, ceil, max_turn_chars, misses):
    """extract one session's in-window activity, or None if it had none."""
    records = read_records(path, misses)
    if not records:
        return None

    title = None
    last_prompt = None
    cwd = None
    branch = None
    session_id = os.path.basename(path)[:-6]

    prompts = []
    turns = []
    decisions = []
    edits = collections.Counter()
    tools = collections.Counter()
    stamps = []

    ask_inputs = {}  # tool_use_id -> question text, for pairing with its result
    pending_turn = None  # [in_window, timestamp, text] for the open assistant turn

    def close_turn():
        if pending_turn and pending_turn[0] and pending_turn[2]:
            turns.append((pending_turn[1], collapse(pending_turn[2], max_turn_chars)))

    for rec in records:
        rtype = rec.get("type")

        if rtype == "ai-title" and isinstance(rec.get("aiTitle"), str):
            title = rec["aiTitle"]
            continue
        if rtype == "last-prompt" and isinstance(rec.get("lastPrompt"), str):
            last_prompt = rec["lastPrompt"]
            continue
        if rtype not in ("user", "assistant"):
            continue
        if rec.get("isSidechain"):
            continue

        when = record_time(rec, misses)
        if when is None:
            continue
        in_window = floor <= when <= ceil
        ts = rec.get("timestamp")
        if in_window:
            stamps.append(ts)
            if isinstance(rec.get("cwd"), str):
                cwd = rec["cwd"]
            if isinstance(rec.get("gitBranch"), str) and rec["gitBranch"]:
                branch = rec["gitBranch"]

        message = rec.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")

        if rtype == "user":
            if rec.get("promptSource") == "typed" and isinstance(content, str):
                close_turn()
                pending_turn = [in_window, ts, ""]
                if in_window:
                    prompts.append((ts, collapse(content, 700)))
                continue
            # tool results: the only one worth reading is an answered question
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    question = ask_inputs.pop(block.get("tool_use_id"), None)
                    if question is None or not in_window:
                        continue
                    for asked, chosen in parse_answer(text_of(block.get("content"))):
                        decisions.append((ts, asked, chosen))
            continue

        # assistant
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and isinstance(block.get("text"), str):
                if pending_turn is None:
                    pending_turn = [in_window, ts, ""]
                text = block["text"].strip()
                if text:
                    pending_turn[0] = in_window
                    pending_turn[1] = ts
                    pending_turn[2] = text
            elif btype == "tool_use" and in_window:
                name = block.get("name")
                if isinstance(name, str):
                    tools[name] += 1
                    if name == ASK_TOOL:
                        ask_inputs[block.get("id")] = summarize_questions(block.get("input"))
                    elif name in EDIT_TOOLS:
                        target = (block.get("input") or {}).get("file_path")
                        if isinstance(target, str):
                            edits[target] += 1

    close_turn()

    if not stamps:
        return None

    stamps.sort()
    return {
        "path": path,
        "session_id": session_id,
        "project": os.path.basename(os.path.dirname(path)),
        "cwd": cwd,
        "branch": branch,
        "title": title or last_prompt or (prompts[0][1] if prompts else "untitled"),
        "start": stamps[0],
        "end": stamps[-1],
        "prompts": prompts,
        "turns": turns,
        "decisions": decisions,
        "edits": edits,
        "tools": tools,
    }


def summarize_questions(ask_input):
    """the question text(s) an AskUserQuestion call posed."""
    if not isinstance(ask_input, dict):
        return "(question)"
    questions = ask_input.get("questions")
    if not isinstance(questions, list):
        return "(question)"
    asked = [q.get("question") for q in questions if isinstance(q, dict) and q.get("question")]
    return " / ".join(asked) if asked else "(question)"


def short_path(target, cwd):
    """render an edited file relative to the session's cwd when it sits under it."""
    if cwd and target.startswith(cwd.rstrip("/") + "/"):
        return target[len(cwd.rstrip("/")) + 1 :]
    return target.replace(os.path.expanduser("~"), "~", 1)


def render(sessions, floor, ceil, misses, max_turn_chars):
    out = []
    projects = sorted({s["project"] for s in sessions})
    zone = local_zone_label()
    window = f"{local_date(floor.isoformat())} → {local_date(ceil.isoformat())}"
    out.append(f"# sessions {window} — {len(sessions)} sessions, {len(projects)} project dirs")
    out.append(
        f"# window: {floor.strftime('%Y-%m-%dT%H:%M:%SZ')} .. "
        f"{ceil.strftime('%Y-%m-%dT%H:%M:%SZ')} · clock times in {zone}"
    )
    out.append(f"# schema misses: {misses.render()}")
    if misses.any():
        out.append("# WARNING: non-zero misses — the transcript format may have moved; treat this digest as partial")
    out.append("")

    for session in sorted(sessions, key=lambda s: (s["project"], s["start"])):
        label = session["cwd"] or session["project"]
        out.append(f"## {os.path.basename(label.rstrip('/'))} · {collapse(session['title'], 90)}")
        meta = [f"session {session['session_id'][:8]}"]
        if session["branch"]:
            meta.append(f"branch {session['branch']}")
        meta.append(f"{local_hhmm(session['start'])}–{local_hhmm(session['end'])} {zone}")
        if session["cwd"]:
            meta.append(f"cwd {short_path(session['cwd'], None)}")
        out.append(" · ".join(meta))

        if session["edits"]:
            rendered = ", ".join(
                f"{short_path(p, session['cwd'])} ×{n}" for p, n in session["edits"].most_common(12)
            )
            extra = len(session["edits"]) - 12
            out.append(f"edits: {rendered}" + (f", +{extra} more files" if extra > 0 else ""))
        if session["tools"]:
            out.append(
                "tools: "
                + ", ".join(f"{name} ×{n}" for name, n in session["tools"].most_common(8))
            )

        if session["prompts"]:
            out.append("")
            out.append("prompts")
            for ts, text in session["prompts"]:
                out.append(f"  {local_hhmm(ts)} > {text}")
        if session["decisions"]:
            out.append("")
            out.append("decisions")
            for ts, asked, chosen in session["decisions"]:
                out.append(f"  {local_hhmm(ts)} {collapse(asked, 160)} → {collapse(chosen, 160)}")
        if session["turns"]:
            out.append("")
            out.append("turns")
            for ts, text in session["turns"]:
                out.append(f"  {local_hhmm(ts)} {text}")
        out.append("")

    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--floor", required=True, help="window floor, iso-8601 utc (e.g. 2026-08-03T07:00:00Z)")
    ap.add_argument("--ceil", required=True, help="window ceiling, iso-8601 utc")
    ap.add_argument("--out", required=True, help="digest path to write")
    ap.add_argument("--projects-dir", default=default_projects_dir(),
                    help="transcript root (default: $CLAUDE_CONFIG_DIR/projects)")
    ap.add_argument("--max-turn-chars", type=int, default=1200,
                    help="truncate each turn conclusion to this many chars (default: 1200)")
    args = ap.parse_args()

    floor = normalize_bound(args.floor, "floor")
    ceil = normalize_bound(args.ceil, "ceil")
    if ceil <= floor:
        sys.exit(f"error: --ceil ({args.ceil}) is not after --floor ({args.floor})")

    root = os.path.expanduser(args.projects_dir)
    if not os.path.isdir(root):
        sys.exit(f"error: transcript root not found: {root} (set CLAUDE_CONFIG_DIR or pass --projects-dir)")

    misses = Misses()
    sessions = []
    for path in sorted(glob.glob(os.path.join(root, "*", "*.jsonl"))):
        # mtime before the floor cannot hold in-window records; skip the read
        try:
            if os.stat(path).st_mtime < floor.timestamp():
                continue
        except OSError:
            misses.unreadable_files += 1
            continue
        session = scan_file(path, floor, ceil, args.max_turn_chars, misses)
        if session:
            sessions.append(session)

    digest = render(sessions, floor, ceil, misses, args.max_turn_chars)
    with open(args.out, "w") as fh:
        fh.write(digest)

    print(f"digest: {args.out}")
    print(
        f"sessions: {len(sessions)} · "
        f"prompts: {sum(len(s['prompts']) for s in sessions)} · "
        f"decisions: {sum(len(s['decisions']) for s in sessions)} · "
        f"turns: {sum(len(s['turns']) for s in sessions)} · "
        f"files edited: {len({p for s in sessions for p in s['edits']})}"
    )
    print(f"schema misses: {misses.render()}")
    if not sessions:
        print("no in-window session activity — report from the artifact sources alone")


if __name__ == "__main__":
    main()
