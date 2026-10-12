import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_collection_validation import make_collection
from validate_collection import validate

SCRIPT = Path(__file__).resolve().parents[1] / "skills/new-agent-skill/scripts/skill_workspace.py"
spec = importlib.util.spec_from_file_location("skill_workspace", SCRIPT)
workspace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.repo = self.root / "clone with spaces"
        self.repo.mkdir()
        make_collection(self.repo)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.config = self.root / "configuration/config.json"

    def test_first_use_and_separate_process_reuse(self):
        with self.assertRaises(ValueError):
            workspace.locate(self.config)
        workspace.configure(self.config, self.repo)
        result = subprocess.run(["python3", str(SCRIPT), "--config", str(self.config), "locate"],
                                text=True, capture_output=True, check=True)
        self.assertEqual(Path(result.stdout.strip()), self.repo.resolve())
        self.assertEqual(json.loads(self.config.read_text()), {"repo_path": str(self.repo.resolve())})

    def test_moved_repo_requires_reconfiguration(self):
        workspace.configure(self.config, self.repo)
        replacement = self.root / "moved"
        self.repo.rename(replacement)
        with self.assertRaises(FileNotFoundError):
            workspace.locate(self.config)
        workspace.configure(self.config, replacement)
        self.assertEqual(workspace.locate(self.config), replacement.resolve())

    def test_corrupt_memory_can_be_reconfigured(self):
        self.config.parent.mkdir()
        for content in ("not json", "[]", '{"repo_path":42}'):
            self.config.write_text(content)
            with self.assertRaises(ValueError):
                workspace.locate(self.config)
        workspace.configure(self.config, self.repo)
        self.assertEqual(workspace.locate(self.config), self.repo.resolve())

    def test_invalid_repo_preserves_memory(self):
        workspace.configure(self.config, self.repo)
        saved = self.config.read_bytes()
        with self.assertRaises((ValueError, subprocess.CalledProcessError)):
            workspace.configure(self.config, self.root)
        self.assertEqual(self.config.read_bytes(), saved)
        with self.assertRaises(ValueError):
            workspace.validate_repo(self.repo / "skills")

    def test_scaffold_collision_and_invalid_slug_preserve_files(self):
        def create(slug):
            return workspace.scaffold(self.repo, slug, "Reviews migrations.", "Migration Review", "Review migrations for compatibility")
        path = create("migration-review")
        before = (path / "SKILL.md").read_bytes()
        with self.assertRaises(FileExistsError):
            create("migration-review")
        self.assertEqual((path / "SKILL.md").read_bytes(), before)
        for slug in ("../escape", "Upper", "a--b", "a-", "a" * 65):
            with self.assertRaises(ValueError):
                create(slug)
        self.assertTrue((path / "agents/openai.yaml").is_file())

    def test_plugin_cache_is_rejected(self):
        cached = self.root / "plugins/cache/copy"
        cached.parent.mkdir(parents=True)
        self.repo.rename(cached)
        with self.assertRaises(ValueError):
            workspace.validate_repo(cached)

    def test_completed_registered_scaffold_validates(self):
        path = workspace.scaffold(self.repo, "new-workflow", "Creates a workflow.",
                                  "New Workflow", "Create a reusable example workflow")
        self.assertTrue(any("unfinished" in error for error in validate(self.repo)[0]))
        document = path / "SKILL.md"
        document.write_text(document.read_text().replace(
            "TODO: complete from the interview.", "Read the supplied input and produce its summary."
        ).replace("TODO: define observable success and representative examples.",
                  "The summary preserves the facts in the input."))
        catalog = self.repo / ".claude-plugin/marketplace.json"
        data = json.loads(catalog.read_text())
        data["plugins"].append({
            "name": "new-workflow", "source": "./", "skills": ["./skills/new-workflow"],
            "displayName": "New Workflow", "description": "Creates a workflow.",
            "category": "development", "keywords": ["workflow"],
        })
        catalog.write_text(json.dumps(data))
        readme = self.repo / "README.md"
        readme.write_text(readme.read_text() + "[new-workflow](skills/new-workflow)\n")
        self.assertEqual(validate(self.repo), ([], []))


if __name__ == "__main__":
    unittest.main()
