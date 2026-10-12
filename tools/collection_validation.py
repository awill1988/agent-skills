"""Portable skill metadata and Markdown validation shared by CI and authoring."""

from html.parser import HTMLParser
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
import yaml


def frontmatter(content):
    match = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", content, re.S)
    if not match:
        raise ValueError("missing or unclosed YAML frontmatter")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")
    return data, content[match.end():]


def tokens(content):
    if content.startswith("---\n"):
        try:
            _, content = frontmatter(content)
        except (ValueError, yaml.YAMLError):
            pass
    return MarkdownIt("commonmark").parse(content)


def inline_text(children):
    return "".join(
        inline_text(token.children) if token.children else token.content
        for token in children or []
        if token.type in ("text", "code_inline", "image", "softbreak", "hardbreak")
    )


class HtmlAnchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.anchors = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if value and (key == "id" or (tag == "a" and key == "name")):
                self.anchors.add(value)


def heading_anchors(content):
    parsed = tokens(content)
    anchors = set()
    html = HtmlAnchors()
    for index, token in enumerate(parsed):
        if token.type == "heading_open":
            text = inline_text(parsed[index + 1].children).lower()
            base = "".join(
                char for char in text
                if char in " -_" or unicodedata.category(char)[0] in "LMN"
            ).replace(" ", "-")
            slug, suffix = base, 0
            while slug in anchors:
                suffix += 1
                slug = f"{base}-{suffix}"
            anchors.add(slug)
        if token.type == "html_block":
            html.feed(token.content)
        for child in token.children or []:
            if child.type == "html_inline":
                html.feed(child.content)
    return anchors | html.anchors


def markdown_link_errors(content, document, boundary=None, read=None):
    """Validate real links, including reference-style links, without reading code spans."""
    document = Path(document).resolve()
    read = read or (lambda path: path.read_text() if path.is_file() else None)
    errors = []
    for token in tokens(content):
        for child in token.children or []:
            if child.type not in ("link_open", "image"):
                continue
            target = child.attrGet("href" if child.type == "link_open" else "src")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            path = (document.parent / unquote(parsed.path)).resolve() if parsed.path else document
            if boundary and not path.is_relative_to(Path(boundary).resolve()):
                errors.append(f"packaged link escapes skill: {target}")
                continue
            if path.is_dir():
                if parsed.fragment:
                    errors.append(f"directory link has no heading target: {target}")
                continue
            if path.suffix.lower() not in (".md", ".markdown"):
                if not path.exists():
                    errors.append(f"missing link target: {target}")
                continue
            linked = content if path == document else read(path)
            if linked is None:
                errors.append(f"missing link target: {target}")
            elif parsed.fragment and unquote(parsed.fragment) not in heading_anchors(linked):
                errors.append(f"missing heading fragment: {target}")
    return errors
