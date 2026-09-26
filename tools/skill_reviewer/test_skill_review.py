#!/usr/bin/env python3
"""
test_skill_review.py — Unit and integration tests for Agent Skills CI reviewer.
"""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from best_practices import RULES, RULE_MAP
from skill_review import (
    SkillChange,
    build_markdown_report,
    evaluate_skill,
    evaluate_static_smells,
    parse_yaml_frontmatter,
)


class FrontmatterParserTests(unittest.TestCase):
    def test_parses_valid_frontmatter(self) -> None:
        content = """---
name: my-skill
description: A clear third-person description of what this skill does and when to use it.
license: MIT
---

# Title
Body text here.
"""
        fm, body, errors = parse_yaml_frontmatter(content)
        self.assertEqual(len(errors), 0)
        self.assertEqual(fm.get("name"), "my-skill")
        self.assertEqual(fm.get("license"), "MIT")
        self.assertIn("Title", body)

    def test_detects_missing_frontmatter(self) -> None:
        content = "# Just a markdown file\nNo frontmatter here."
        _, _, errors = parse_yaml_frontmatter(content)
        self.assertGreater(len(errors), 0)
        self.assertIn("FM001", errors[0])


class SmellEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.skills_dir = self.temp_dir / "skills"
        self.skills_dir.mkdir(parents=True)
        # Create minimal marketplace.json and README.md
        plugin_dir = self.temp_dir / ".claude-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "marketplace.json").write_text('{"plugins": [{"name": "valid-skill"}]}', encoding="utf-8")
        (self.temp_dir / "README.md").write_text("# Readme\n- [`valid-skill`](skills/valid-skill)", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_clean_skill_passes_with_no_findings(self) -> None:
        skill_dir = self.skills_dir / "valid-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: valid-skill
description: An expertly engineered skill that handles operations cleanly and describes what and when.
license: MIT
---

# Valid Skill
Clear instructions for the agent.
""", encoding="utf-8")

        findings = evaluate_static_smells("valid-skill", self.temp_dir)
        self.assertEqual(len(findings), 0)

    def test_detects_name_mismatch(self) -> None:
        skill_dir = self.skills_dir / "mismatched-dir"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: other-name
description: A valid description that explains what the skill does and when to activate it.
---
# Body
""", encoding="utf-8")

        findings = evaluate_static_smells("mismatched-dir", self.temp_dir)
        rule_codes = [f.rule_code for f in findings]
        self.assertIn("FM002", rule_codes)

    def test_detects_broken_relative_links(self) -> None:
        skill_dir = self.skills_dir / "broken-links"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: broken-links
description: A skill that has broken relative markdown links pointing to nowhere.
---
# Broken Links
Read [reference](references/missing.md) and run [script](scripts/missing.sh).
""", encoding="utf-8")

        findings = evaluate_static_smells("broken-links", self.temp_dir)
        rule_codes = [f.rule_code for f in findings]
        self.assertIn("PD002", rule_codes)

    def test_detects_progressive_disclosure_line_bloat(self) -> None:
        skill_dir = self.skills_dir / "bloated-skill"
        skill_dir.mkdir()
        bloated_body = "\n".join([f"Line {i}: excessive procedural narrative" for i in range(550)])
        (skill_dir / "SKILL.md").write_text(f"""---
name: bloated-skill
description: A skill that dumps an entire textbook into SKILL.md violating progressive disclosure.
---
{bloated_body}
""", encoding="utf-8")

        findings = evaluate_static_smells("bloated-skill", self.temp_dir)
        rule_codes = [f.rule_code for f in findings]
        self.assertIn("PD001", rule_codes)

    def test_detects_ai_attribution(self) -> None:
        skill_dir = self.skills_dir / "ai-attributed"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: ai-attributed
description: A skill that unfortunately contains co-authored-by agent attribution tags.
---
# Body
Co-Authored-By: Assistant <ai@example.com>
""", encoding="utf-8")

        findings = evaluate_static_smells("ai-attributed", self.temp_dir)
        rule_codes = [f.rule_code for f in findings]
        self.assertIn("AI001", rule_codes)


class LifecycleEvaluationTests(unittest.TestCase):
    def test_deleted_skill_is_auto_approved_without_review(self) -> None:
        skill = SkillChange(name="old-deprecated-skill", change_type="DELETED")
        evaluate_skill(
            skill=skill,
            base="origin/main",
            head="HEAD",
            root_dir=Path("/repo"),
            mock=True,
            cache_dir=Path("/cache"),
        )
        self.assertEqual(skill.disposition, "APPROVE")
        self.assertEqual(len(skill.findings), 0)
        self.assertIn("deleted", skill.summary)
        self.assertIn("Skipping", skill.summary)

    def test_build_markdown_report_includes_deleted_skill_notice(self) -> None:
        skill = SkillChange(name="removed-skill", change_type="DELETED")
        evaluate_skill(
            skill=skill,
            base="origin/main",
            head="HEAD",
            root_dir=Path("/repo"),
            mock=True,
            cache_dir=Path("/cache"),
        )
        report = build_markdown_report("PR #99", "APPROVE", {"removed-skill": skill})
        self.assertIn("## 🟢 Agent Skills Review: PR #99 — `APPROVE`", report)
        self.assertIn("| `removed-skill` | **DELETED** | 🟢 APPROVE |", report)
        self.assertIn("This skill was deleted in this change. Skipping quality review and approving deletion.", report)


if __name__ == "__main__":
    unittest.main()
