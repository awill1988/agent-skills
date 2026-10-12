#!/usr/bin/env python3
"""Validate collection metadata, packaged references, and discovery catalogs."""

import argparse
import json
from pathlib import Path
import re
import sys

import yaml

from collection_validation import frontmatter, markdown_link_errors


def validate(root):
    errors, warnings = [], []
    skills = sorted((root / "skills").glob("*/SKILL.md"))
    names = {path.parent.name for path in skills}
    if not names:
        errors.append("collection contains no skills")
    for path in skills:
        label = str(path.relative_to(root))
        try:
            data, body = frontmatter(path.read_text())
            name = data.get("name")
            if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64 or name != path.parent.name:
                errors.append(f"{label}: invalid or mismatched name")
            description = data.get("description")
            if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
                errors.append(f"{label}: description must contain 1-1024 characters")
            metadata = data.get("metadata", {})
            if not isinstance(metadata, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in metadata.items()):
                errors.append(f"{label}: metadata must map strings to strings")
            if "tags" in data:
                errors.append(f"{label}: use catalog keywords instead of unsupported top-level tags")
            if len(body.splitlines()) > 500:
                warnings.append(f"{label}: review entrypoint size above 500 lines")
            if re.search(r"\bTODO:\s*(complete from the interview|define observable success)", body):
                errors.append(f"{label}: unfinished creator scaffold")
            ui_path = path.parent / "agents/openai.yaml"
            ui = yaml.safe_load(ui_path.read_text())["interface"]
            if not isinstance(ui.get("display_name"), str) or not ui["display_name"].strip():
                errors.append(f"{label}: missing display name")
            short = ui.get("short_description", "")
            if not isinstance(short, str) or not 25 <= len(short) <= 64:
                errors.append(f"{label}: UI description must contain 25-64 characters")
            prompt = ui.get("default_prompt", "")
            if not isinstance(prompt, str) or f"${name}" not in prompt:
                errors.append(f"{label}: default prompt must mention ${name}")
        except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as error:
            errors.append(f"{label}: {error}")
        for document in path.parent.rglob("*.md"):
            errors.extend(f"{document.relative_to(root)}: {error}" for error in markdown_link_errors(document.read_text(), document, path.parent))

    try:
        claude = json.loads((root / ".claude-plugin/marketplace.json").read_text())
        entries = claude["plugins"]
        if {entry["name"] for entry in entries} != names or len(entries) != len(names):
            errors.append("Claude catalog must register each skill exactly once")
        for entry in entries:
            name = entry["name"]
            if entry.get("source") != "./" or entry.get("skills") != [f"./skills/{name}"]:
                errors.append(f"{name}: Claude entry must select exactly its skill from the root")
            for field in ("displayName", "description", "category"):
                if not isinstance(entry.get(field), str) or not entry[field].strip():
                    errors.append(f"{name}: missing catalog {field}")
            keywords = entry.get("keywords")
            if not isinstance(keywords, list) or not keywords or any(not isinstance(k, str) or not k.strip() for k in keywords):
                errors.append(f"{name}: missing catalog keywords")
        bundle = json.loads((root / "plugin.json").read_text())
        if set(bundle) != {"name", "description"} or not all(isinstance(value, str) and value.strip() for value in bundle.values()):
            errors.append("portable manifest must contain name and description only")
        catalog = json.loads((root / ".agents/plugins/marketplace.json").read_text())
        plugins = catalog["plugins"]
        if len(plugins) != 1 or plugins[0]["name"] != bundle["name"] or plugins[0]["source"] != {"source": "local", "path": "./"}:
            errors.append("Codex catalog must expose the root bundle exactly once")
        if claude["name"] != catalog["name"] or bundle["name"] != "awill1988-agent-skills":
            errors.append("marketplace and bundle identifiers do not match the collection")
        readme = (root / "README.md").read_text()
        for name in names:
            if f"](skills/{name})" not in readme:
                errors.append(f"{name}: missing README catalog entry")
        for document in [root / "README.md", *root.glob("docs/adr/*.md")]:
            errors.extend(f"{document.relative_to(root)}: {error}" for error in markdown_link_errors(document.read_text(), document))
    except (OSError, ValueError, TypeError, KeyError) as error:
        errors.append(f"invalid collection catalog: {error}")
    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    errors, warnings = validate(args.root.resolve())
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if not errors:
        print("collection validation passed")
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
