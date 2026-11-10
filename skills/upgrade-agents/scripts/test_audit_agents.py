#!/usr/bin/env python3
"""Unit tests for audit_agents.py."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_agents  # noqa: E402


class SemverAndReleaseTests(unittest.TestCase):
    def test_parse_semver_tag_enforces_stable_and_prefix(self) -> None:
        self.assertEqual(
            audit_agents.parse_semver_tag("rust-v0.160.1", "rust-v"),
            ((0, 160, 1), "0.160.1", True),
        )
        self.assertEqual(
            audit_agents.parse_semver_tag("rust-v0.161.0-alpha.2", "rust-v"),
            ((0, 161, 0), "0.161.0-alpha.2", False),
        )
        # Wrong prefix in monorepo is rejected cleanly.
        self.assertEqual(
            audit_agents.parse_semver_tag("sdk-v1.4.0", "rust-v"),
            (None, "", False),
        )
        self.assertEqual(
            audit_agents.parse_semver_tag("1.2.17", ""),
            ((1, 2, 17), "1.2.17", True),
        )
        self.assertEqual(
            audit_agents.parse_semver_tag("v2.1.290-canary.1", "v"),
            ((2, 1, 290), "2.1.290-canary.1", False),
        )

    def test_hex_or_digest_to_sri(self) -> None:
        digest = hashlib.sha256(b"stable-release-payload").hexdigest()
        sri = audit_agents.hex_or_digest_to_sri(f"sha256:{digest}")
        self.assertIsNotNone(sri)
        assert sri is not None
        self.assertTrue(sri.startswith("sha256-"))
        self.assertEqual(audit_agents.hex_or_digest_to_sri(sri), sri)
        self.assertIsNone(audit_agents.hex_or_digest_to_sri("md5:1234"))

    def test_audit_releases_skips_prereleases_and_aggregates_delta(self) -> None:
        fake_releases = [
            {
                "tag_name": "rust-v0.162.0-alpha.1",
                "draft": False,
                "prerelease": True,
                "published_at": "2026-11-09T00:00:00Z",
                "html_url": "https://example.test/0.162.0-alpha.1",
                "body": "- Experimental preview flag",
                "assets": [],
            },
            {
                "tag_name": "rust-v0.161.0",
                "draft": False,
                "prerelease": False,
                "published_at": "2026-11-08T00:00:00Z",
                "html_url": "https://example.test/0.161.0",
                "body": "- Deprecated `features.rmcp_client` in config.toml\n- Added local `code_mode_host` developer mode",
                "assets": [
                    {
                        "name": "codex-package-aarch64-apple-darwin.tar.gz",
                        "browser_download_url": "https://example.test/codex.tar.gz",
                        "size": 1024,
                        "digest": "sha256:" + ("ab" * 32),
                    }
                ],
            },
            {
                "tag_name": "rust-v0.160.2",
                "draft": False,
                "prerelease": False,
                "published_at": "2026-11-02T00:00:00Z",
                "html_url": "https://example.test/0.160.2",
                "body": "- Added OTEL metrics telemetry opt-out `otel.metrics_exporter = \"none\"`",
                "assets": [],
            },
            {
                "tag_name": "rust-v0.160.1",
                "draft": False,
                "prerelease": False,
                "published_at": "2026-10-25T00:00:00Z",
                "html_url": "https://example.test/0.160.1",
                "body": "- Older release note that should not appear in delta",
                "assets": [],
            },
        ]

        with mock.patch.object(audit_agents, "github_api_get_json", return_value=fake_releases), \
             mock.patch.object(audit_agents, "github_fetch_raw_file", return_value=None):
            report = audit_agents.audit_releases(
                audit_agents.KNOWN_AGENTS["codex"],
                since_version="0.160.1",
                include_changelog=False,
            )

        self.assertTrue(report["update_available"])
        latest = report["latest_stable"]
        assert isinstance(latest, dict)
        self.assertEqual(latest["version"], "0.161.0")
        self.assertEqual(len(report["skipped_newer_prereleases"]), 1)  # type: ignore[arg-type]
        scanned_tags = [r["tag"] for r in report["releases_scanned"]]  # type: ignore[union-attr]
        self.assertEqual(scanned_tags, ["rust-v0.161.0", "rust-v0.160.2"])

        signals = report["signals"]
        assert isinstance(signals, dict)
        self.assertEqual(len(signals["stale_and_deprecated"]), 1)
        self.assertEqual(len(signals["privacy_and_telemetry"]), 1)
        self.assertEqual(len(signals["dev_mode_and_features"]), 1)
        self.assertTrue(latest["assets"][0]["sri"].startswith("sha256-"))


class RedactionWrapperAndProbeTests(unittest.TestCase):
    def test_secret_redaction_preserves_booleans_and_masks_tokens(self) -> None:
        raw_cfg = {
            "telemetry": {"enabled": False},
            "apiKey": "sk-proj-1234567890abcdefghijkl",
            "nested": {
                "webhook_url": "https://user:pass@example.test/hook",
                "authTokenEnabled": False,
            },
            "mcpServers": {
                "custom-local": {"command": "local-mcp"},
            },
        }
        flat = audit_agents.flatten_config(raw_cfg)
        by_key = {item["key"]: item for item in flat}
        self.assertIs(by_key["telemetry.enabled"]["value"], False)
        self.assertEqual(by_key["apiKey"]["value"], "<REDACTED>")
        self.assertEqual(by_key["nested.webhook_url"]["value"], "<REDACTED>")
        self.assertIs(by_key["nested.authTokenEnabled"]["value"], False)
        # User-named map entries under mcpServers should still validate child schema properties like `command`.
        self.assertTrue(by_key["mcpServers.custom-local.command"]["schema_candidate"])

    def test_wrapper_chain_traces_to_wrapped_payload_and_probes_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / ".demoagent-wrapped"
            payload.write_bytes(
                b"#!/bin/sh\n"
                b"if [ \"$1\" = \"--help\" ]; then echo '--dev-mode --disable-telemetry'; exit 0; fi\n"
                b"DEMOAGENT_DISABLE_TELEMETRY DEMOAGENT_DEV_MODE valid_setting telemetry_enabled\n"
            )
            payload.chmod(0o755)

            inner_wrap = root / "demoagent"
            inner_wrap.write_text(
                "#!/usr/bin/env bash\n"
                f'export DEMOAGENT_API_TOKEN="sk-secret-value-1234567890"\n'
                f'exec "{payload}" "$@"\n',
                encoding="utf-8",
            )
            inner_wrap.chmod(0o755)

            outer_link = root / "outer-demoagent"
            outer_link.symlink_to(inner_wrap)

            cfg_file = root / "settings.json"
            cfg_file.write_text(
                json.dumps({
                    "valid_setting": True,
                    "telemetry_enabled": False,
                    "obsolete_legacy_toggle": True,
                }),
                encoding="utf-8",
            )

            spec = audit_agents.parse_agent_override("demoagent=example/demoagent:v")
            result = audit_agents.probe_agent_binary(
                spec,
                binary_override=outer_link,
                extra_config_files=[cfg_file],
            )

            trace = result["trace"]
            assert isinstance(trace, dict)
            self.assertEqual(Path(str(trace["payload_binary"])).resolve(), payload.resolve())
            self.assertEqual(trace["wrapper_env"]["DEMOAGENT_API_TOKEN"], "<REDACTED>")

            unmatched = [item["key"] for item in result["unmatched_config_keys"]]  # type: ignore[union-attr]
            self.assertIn("obsolete_legacy_toggle", unmatched)
            self.assertNotIn("valid_setting", unmatched)


class SkillHygieneTests(unittest.TestCase):
    def test_no_hardcoded_home_paths_or_ai_attribution(self) -> None:
        skill_root = SCRIPT_DIR.parent
        home_re = re.compile(r"/(Users|home)/[A-Za-z0-9._-]+")
        ai_re = re.compile(r"(co-authored-by|generated-by|assisted-by):", re.IGNORECASE)
        for path in skill_root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            # Avoid matching regex literals inside this test file itself.
            if path.resolve() == Path(__file__).resolve():
                continue
            self.assertIsNone(home_re.search(text), f"hardcoded home path found in {path}")
            self.assertIsNone(ai_re.search(text), f"AI attribution found in {path}")


if __name__ == "__main__":
    unittest.main()
