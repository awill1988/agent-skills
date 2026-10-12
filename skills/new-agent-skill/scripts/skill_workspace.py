#!/usr/bin/env python3
"""Locate a writable collection checkout and scaffold skills without overwrites."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def config_path():
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "awill1988-agent-skills" / "config.json"


def validate_repo(raw_path):
    repo = Path(raw_path).expanduser().resolve(strict=True)
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    if Path(result.stdout.strip()).resolve() != repo:
        raise ValueError("choose the checkout root, not a subdirectory")
    for relative in ("skills", ".claude-plugin/marketplace.json", "plugin.json", "README.md"):
        if not (repo / relative).exists():
            raise ValueError(f"collection checkout is missing {relative}")
    if (repo / "skills").is_symlink():
        raise ValueError("skills directory must belong to the checkout")
    manifest = json.loads((repo / "plugin.json").read_text())
    if not isinstance(manifest, dict) or manifest.get("name") != "awill1988-agent-skills":
        raise ValueError("path is not the awill1988 agent-skills collection")
    installed_paths = ("plugins/cache", ".claude/plugins", ".codex/plugins",
                       ".gemini/config/plugins", ".gemini/antigravity-cli/plugins")
    if any(part in repo.as_posix() for part in installed_paths) or not os.access(repo / "skills", os.W_OK):
        raise ValueError("choose a writable clone outside the plugin cache")
    return repo


def configure(path, raw_repo):
    repo = validate_repo(raw_repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    # This file is private machine state, never a tracked package resource.
    descriptor, temporary = tempfile.mkstemp(prefix=".config-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"repo_path": str(repo)}, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return repo


def locate(path):
    if not path.is_file():
        raise ValueError("repository location is not configured; run configure <clone-path>")
    try:
        data = json.loads(path.read_text())
        raw_repo = data["repo_path"]
        if not isinstance(raw_repo, str) or not raw_repo.strip():
            raise ValueError("repo_path must be a nonempty string")
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError("invalid repository memory; run configure <clone-path>") from error
    return validate_repo(raw_repo)


def scaffold(repo, slug, description, display_name, short_description):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or len(slug) > 64:
        raise ValueError("slug must be 1-64 lowercase letters, digits, and single hyphens")
    if not 1 <= len(description.strip()) <= 1024 or not display_name.strip():
        raise ValueError("provide a display name and a 1-1024 character description")
    if not 25 <= len(short_description) <= 64:
        raise ValueError("short description must contain 25-64 characters")
    destination = repo / "skills" / slug
    destination.mkdir()  # Exclusive creation protects existing skills and symlinks.
    try:
        (destination / "agents").mkdir()
        (destination / "SKILL.md").write_text(
            f"---\nname: {slug}\ndescription: {json.dumps(description)}\nlicense: MIT\n---\n\n"
            f"# {display_name}\n\n"
            "## Workflow\n\nTODO: complete from the interview.\n\n"
            "## Completion\n\nTODO: define observable success and representative examples.\n"
        )
        interface = {
            "display_name": display_name,
            "short_description": short_description,
            "default_prompt": f"Use ${slug} to complete its documented workflow.",
        }
        (destination / "agents/openai.yaml").write_text(
            "interface:\n" + "".join(f"  {key}: {json.dumps(value)}\n" for key, value in interface.items())
        )
    except Exception:
        shutil.rmtree(destination)
        raise
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=config_path(), help="override machine configuration path")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("locate", help="print the validated remembered checkout")
    setup = commands.add_parser("configure", help="validate and remember a checkout")
    setup.add_argument("path")
    create = commands.add_parser("scaffold", help="create an unregistered draft without overwriting files")
    create.add_argument("slug")
    for flag in ("description", "display-name", "short-description"):
        create.add_argument(f"--{flag}", required=True)
    args = parser.parse_args()
    try:
        if args.command == "configure":
            result = configure(args.config, args.path)
        else:
            result = locate(args.config)
            if args.command == "scaffold":
                result = scaffold(result, args.slug, args.description, args.display_name, args.short_description)
        print(result)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
