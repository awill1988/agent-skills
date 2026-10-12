import json
from pathlib import Path
import tempfile
import unittest

from collection_validation import frontmatter, heading_anchors, markdown_link_errors
from validate_collection import validate


def make_collection(root):
    skill = root / "skills/example"
    (skill / "agents").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: example\ndescription: Does one thing.\nargument-hint: '[input]'\n---\n# Example\n")
    (skill / "agents/openai.yaml").write_text(
        'interface:\n  display_name: "Example"\n  short_description: "A useful example skill for testing"\n'
        '  default_prompt: "Use $example to complete the task."\n'
    )
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin/marketplace.json").write_text(json.dumps({
        "name": "awill1988-agent-skills", "plugins": [{
            "name": "example", "source": "./", "skills": ["./skills/example"],
            "displayName": "Example", "description": "Does one thing.",
            "category": "development", "keywords": ["example"],
        }],
    }))
    (root / ".agents/plugins").mkdir(parents=True)
    (root / ".agents/plugins/marketplace.json").write_text(json.dumps({
        "name": "awill1988-agent-skills", "plugins": [{
            "name": "awill1988-agent-skills", "source": {"source": "local", "path": "./"},
        }],
    }))
    (root / "plugin.json").write_text(json.dumps({"name": "awill1988-agent-skills", "description": "Example collection"}))
    (root / "README.md").write_text("[example](skills/example)\n")
    return skill


class MarkdownTests(unittest.TestCase):
    def test_duplicate_headings_and_punctuation(self):
        self.assertEqual(heading_anchors("# Hello, `world`!\n## Hello, world!\n## Résumé\n"),
                         {"hello-world", "hello-world-1", "résumé"})

    def test_anchor_collision(self):
        self.assertEqual(heading_anchors("# a\n# a\n# a-1\n# a\n"), {"a", "a-1", "a-1-1", "a-2"})

    def test_code_examples_are_not_links(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            content = '`[text](url)`\n\n```md\n[also](missing.md)\n```\n'
            self.assertEqual(markdown_link_errors(content, path), [])

    def test_fragments_and_reference_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ref.md").write_text("# Setup\n## Setup\n")
            text = "# Main\n[good](#main) [other](ref.md#setup-1) [bad](ref.md#absent) [gone][missing]\n\n[missing]: gone.md\n"
            errors = markdown_link_errors(text, root / "SKILL.md")
            self.assertEqual(len(errors), 2)
            self.assertTrue(any("heading fragment" in error for error in errors))
            self.assertTrue(any("gone.md" in error for error in errors))

    def test_reference_paths_resolve_from_document(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "references").mkdir()
            (root / "SKILL.md").write_text("# Main\n")
            (root / "references/note.md").write_text("# Note\n")
            text = "[root](../SKILL.md#main) [sibling](note.md#note)"
            self.assertEqual(markdown_link_errors(text, root / "references/guide.md", root), [])
            self.assertTrue(markdown_link_errors("[escape](../../outside.md)", root / "references/guide.md", root))

    def test_explicit_html_anchor(self):
        self.assertEqual(markdown_link_errors('<a id="stable"></a>\n\n[link](#stable)', Path('/tmp/example.md')), [])


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.skill = make_collection(self.root)

    def test_short_description_and_client_extension_valid(self):
        self.assertEqual(validate(self.root), ([], []))

    def test_missing_interface_fails(self):
        (self.skill / "agents/openai.yaml").unlink()
        self.assertTrue(validate(self.root)[0])

    def test_duplicate_catalog_entry_fails(self):
        path = self.root / ".claude-plugin/marketplace.json"
        data = json.loads(path.read_text())
        data["plugins"] *= 2
        path.write_text(json.dumps(data))
        self.assertTrue(any("exactly once" in error for error in validate(self.root)[0]))

    def test_bad_path_and_prompt_fail(self):
        path = self.root / ".claude-plugin/marketplace.json"
        data = json.loads(path.read_text())
        data["plugins"][0]["skills"] = ["./skills/missing"]
        path.write_text(json.dumps(data))
        ui = self.skill / "agents/openai.yaml"
        ui.write_text(ui.read_text().replace("$example", "$wrong"))
        errors, _ = validate(self.root)
        self.assertTrue(any("select exactly" in error for error in errors))
        self.assertTrue(any("default prompt" in error for error in errors))

    def test_long_entrypoint_warns_without_failing(self):
        path = self.skill / "SKILL.md"
        path.write_text(path.read_text() + "detail\n" * 501)
        errors, warnings = validate(self.root)
        self.assertFalse(errors)
        self.assertTrue(warnings)

    def test_incomplete_scaffold_fails(self):
        path = self.skill / "SKILL.md"
        path.write_text(path.read_text() + "TODO: complete from the interview.\n")
        self.assertTrue(any("unfinished" in error for error in validate(self.root)[0]))

    def test_reference_fragment_validated(self):
        folder = self.skill / "references"
        folder.mkdir()
        (folder / "guide.md").write_text("[bad](../SKILL.md#absent)")
        self.assertTrue(any("fragment" in error for error in validate(self.root)[0]))

    def test_yaml_mapping_and_folded_description(self):
        data, _ = frontmatter("---\nname: example\ndescription: >-\n  First line\n  second line\nmetadata:\n  version: '1.0'\n---\n# Title")
        self.assertEqual(data["description"], "First line second line")
        self.assertEqual(data["metadata"], {"version": "1.0"})
        with self.assertRaises(ValueError):
            frontmatter("---\n- list\n---\n")


if __name__ == "__main__":
    unittest.main()
