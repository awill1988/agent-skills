#!/usr/bin/env python3
"""
test_scan_comments.py — Unit tests for the comment scanner and DDD analyzer.
"""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scan_comments import (
    analyze_block,
    extract_comment_blocks,
    scan_path,
    CommentBlock,
)


class CommentExtractorTests(unittest.TestCase):
    def test_extract_rust_line_comments(self) -> None:
        with tempfile.NamedTemporaryFile("w+", suffix=".rs", delete=False) as f:
            f.write("""// Line 1
// Line 2
// Line 3
fn do_something() {}
""")
            temp_path = Path(f.name)

        try:
            blocks = list(extract_comment_blocks(temp_path))
            self.assertEqual(len(blocks), 1)
            self.assertEqual(blocks[0].start_line, 1)
            self.assertEqual(blocks[0].end_line, 3)
            self.assertEqual(blocks[0].line_count, 3)
            self.assertEqual(blocks[0].comment_type, "line")
            self.assertEqual(blocks[0].following_code, "fn do_something() {}")
        finally:
            temp_path.unlink()

    def test_extract_python_docstring(self) -> None:
        with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=False) as f:
            f.write('''def calculate():
    """
    First calculate X.
    Then loop over Y.
    Finally return Z.
    """
    return 42
''')
            temp_path = Path(f.name)

        try:
            blocks = list(extract_comment_blocks(temp_path))
            self.assertEqual(len(blocks), 1)
            self.assertEqual(blocks[0].comment_type, "docstring")
            self.assertEqual(blocks[0].start_line, 2)
            self.assertEqual(blocks[0].end_line, 6)
        finally:
            temp_path.unlink()


class DDDAnalysisTests(unittest.TestCase):
    def test_detects_procedural_narration(self) -> None:
        block = CommentBlock(
            file_path=Path("test.rs"),
            start_line=1,
            end_line=4,
            lines=[
                "// First we loop through all input packets.",
                "// Then we check if the packet header matches.",
                "// Finally we push the packet to the output buffer.",
            ],
            comment_type="line",
            following_code="pub fn process_packets() {}",
        )
        finding = analyze_block(block, min_lines=3)
        self.assertIsNotNone(finding)
        self.assertEqual(finding.smell, "PROCEDURAL_NARRATION")
        self.assertEqual(finding.severity, "HIGH")
        self.assertGreater(finding.estimated_saved_lines, 0)

    def test_preserves_why_signals_in_procedural_text(self) -> None:
        block = CommentBlock(
            file_path=Path("test.rs"),
            start_line=1,
            end_line=3,
            lines=[
                "// First we parse the input record.",
                "// Invariant: template must be rights-cleared per ADR-0007.",
                "// Then return the validated template.",
            ],
            comment_type="line",
            following_code="pub fn load_template() {}",
        )
        finding = analyze_block(block, min_lines=3)
        self.assertIsNotNone(finding)
        self.assertEqual(finding.smell, "PROCEDURAL_WITH_INVARIANT")
        self.assertIn("DISTILL_TO_INVARIANT", finding.recommendation)

    def test_detects_redundant_signature_echo(self) -> None:
        block = CommentBlock(
            file_path=Path("user.swift"),
            start_line=1,
            end_line=3,
            lines=[
                "/// getUserProfile",
                "/// gets the user profile",
            ],
            comment_type="doc",
            following_code="func getUserProfile(id: String) -> Profile {",
        )
        # using min_lines=2
        finding = analyze_block(block, min_lines=2)
        self.assertIsNotNone(finding)
        self.assertEqual(finding.smell, "REDUNDANT_SIGNATURE_ECHO")


if __name__ == "__main__":
    unittest.main()
