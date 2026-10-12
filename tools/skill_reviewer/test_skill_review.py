#!/usr/bin/env python3
"""
test_skill_review.py — Unit and integration tests for Agent Skills CI reviewer.
"""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from best_practices import RULES, RULE_MAP
from skill_review import (
    SkillChange,
    build_markdown_report,
    evaluate_skill,
    lint_skill_files,
    parse_yaml_frontmatter,
    parse_model_disposition,
    extract_skill_metadata,
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


class SkillLintTests(unittest.TestCase):
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

        findings = lint_skill_files("valid-skill", self.temp_dir)
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

        findings = lint_skill_files("mismatched-dir", self.temp_dir)
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

        findings = lint_skill_files("broken-links", self.temp_dir)
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

        findings = lint_skill_files("bloated-skill", self.temp_dir)
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

        findings = lint_skill_files("ai-attributed", self.temp_dir)
        rule_codes = [f.rule_code for f in findings]
        self.assertIn("AI001", rule_codes)


class LifecycleEvaluationTests(unittest.TestCase):
    def test_unstructured_model_output_cannot_approve(self):
        with self.assertRaises(ValueError):
            parse_model_disposition("looks fine")
        self.assertEqual(parse_model_disposition("DISPOSITION: APPROVE"), "APPROVE")

    def test_missing_model_cannot_approve(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = SkillChange(name="example", change_type="UPDATED")
            with patch("skill_review.extract_git_diff_text", return_value="diff"), \
                 patch("skill_review.lint_skill_files", return_value=[]), \
                 patch("skill_review.extract_skill_metadata", return_value="metadata"), \
                 patch("skill_review.resolve_runner", return_value=None):
                evaluate_skill(skill, "base", "HEAD", Path(directory), False, Path(directory))
            self.assertEqual(skill.disposition, "COMMENT")
            self.assertFalse(skill.model_review_completed)
            report = build_markdown_report("local", skill.disposition, {skill.name: skill})
            self.assertIn("Skill Lint:", report)

    def test_deleted_skill_is_not_approved_without_review(self) -> None:
        skill = SkillChange(name="old-deprecated-skill", change_type="DELETED")
        evaluate_skill(
            skill=skill,
            base="origin/main",
            head="HEAD",
            root_dir=Path("/repo"),
            mock=True,
            cache_dir=Path("/cache"),
        )
        self.assertEqual(skill.disposition, "COMMENT")
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
        report = build_markdown_report("PR #99", "COMMENT", {"removed-skill": skill})
        self.assertIn("Skill Lint: PR #99", report)
        self.assertIn("| `removed-skill` | **DELETED** | 🟡 COMMENT |", report)
        self.assertIn("deletion requires review", report)


class MetadataAndAssessmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.skills_dir = self.temp_dir / "skills"
        self.skills_dir.mkdir(parents=True)
        plugin_dir = self.temp_dir / ".claude-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "marketplace.json").write_text('{"plugins": [{"name": "comprehension-skill"}]}', encoding="utf-8")
        (self.temp_dir / "README.md").write_text("# Readme\n- [`comprehension-skill`](skills/comprehension-skill)", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_extract_skill_metadata_extracts_workflows_and_assets(self) -> None:
        skill_dir = self.skills_dir / "comprehension-skill"
        skill_dir.mkdir()
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "guide.md").write_text("# Reference", encoding="utf-8")

        (skill_dir / "SKILL.md").write_text("""---
name: comprehension-skill
description: A specialized skill for testing semantic understanding synthesis and workflow extraction.
license: MIT
---

# Comprehension Skill

## Workflow
1. Initial discovery and context gathering.
2. Structural modeling and decision logging.
3. Verification against compliance invariants.
""", encoding="utf-8")

        summary = extract_skill_metadata(
            skill_name="comprehension-skill",
            root_dir=self.temp_dir,
            ref="HEAD",
            change_type="NEW",
            diff_text="",
            files=["skills/comprehension-skill/SKILL.md", "skills/comprehension-skill/references/guide.md"],
        )
        self.assertIn("testing semantic understanding synthesis", summary)
        self.assertIn("Initial discovery and context gathering", summary)
        self.assertIn("1 reference guide(s)", summary)

    def test_evaluate_skill_populates_reasoning_trace(self) -> None:
        skill_dir = self.skills_dir / "comprehension-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: comprehension-skill
description: A specialized skill for testing semantic understanding synthesis and workflow extraction.
license: MIT
---
# Clean Body
""", encoding="utf-8")

        skill = SkillChange(
            name="comprehension-skill",
            change_type="NEW",
            files=["skills/comprehension-skill/SKILL.md"]
        )
        evaluate_skill(
            skill=skill,
            base="origin/main",
            head="HEAD",
            root_dir=self.temp_dir,
            mock=True,
            cache_dir=self.temp_dir / "cache",
        )
        self.assertEqual(skill.disposition, "COMMENT")
        self.assertFalse(skill.model_review_completed)
        self.assertNotIn("Skill Review", build_markdown_report("local", skill.disposition, {skill.name: skill}))
        self.assertGreater(len(skill.reasoning_trace), 4)
        stages = [s["stage"] for s in skill.reasoning_trace]
        self.assertIn("1. Lifecycle Classification", stages)
        self.assertIn("2. Frontmatter Specification", stages)
        self.assertIn("3. Progressive Disclosure", stages)

    def test_build_markdown_report_includes_details_and_anchor(self) -> None:
        skill = SkillChange(
            name="demo-skill",
            change_type="NEW",
            functional_summary="**Purpose & Scope**: Demonstrates understanding.",
            reasoning_trace=[{
                "stage": "1. Lifecycle Classification",
                "scope": "Diff",
                "status": "🟢 PASSED",
                "rationale": "Classified as NEW.",
            }],
            model_reasoning="Model concurs with clean implementation.",
            model_latency=1.23,
        )
        report = build_markdown_report("PR #10", "APPROVE", {"demo-skill": skill})
        self.assertIn("<!-- agent-skills-review:report -->", report)
        self.assertIn("#### 📋 Extracted Metadata", report)
        self.assertIn("Demonstrates understanding", report)
        self.assertIn("<details>", report)
        self.assertIn("🧠 <b>Validation Checks and Model Assessment</b>", report)
        self.assertIn("Model concurs with clean implementation", report)
        self.assertIn("1.23s latency", report)


if __name__ == "__main__":
    unittest.main()
