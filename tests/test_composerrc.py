"""Unit tests for .composerrc functionality."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import read_composerrc


class TestComposerRC(unittest.TestCase):
    """Test cases for .composerrc reading and parsing."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.composerrc_path = Path(self.test_dir) / ".composerrc"

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_read_valid_composerrc(self):
        """Test reading a valid .composerrc file."""
        config = {
            "source_directory": "src",
            "output_file": "dist/output.lua",
            "namespace_file": "namespace.lua",
            "entrypoint_file": "main.lua",
            "dcs_strict_sanitize": True,
        }

        with open(self.composerrc_path, "w") as f:
            json.dump(config, f)

        result = read_composerrc.read_composerrc(self.test_dir)
        self.assertEqual(result, config)

    def test_missing_composerrc(self):
        """Test behavior when .composerrc doesn't exist."""
        result = read_composerrc.read_composerrc(self.test_dir)
        self.assertEqual(result, {})

    def test_invalid_json(self):
        """Test handling of invalid JSON in .composerrc."""
        with open(self.composerrc_path, "w") as f:
            f.write("{ invalid json }")

        with self.assertRaises(SystemExit) as cm:
            with patch("sys.stderr"):
                read_composerrc.read_composerrc(self.test_dir)
        self.assertEqual(cm.exception.code, 1)

    def test_validate_config_valid_keys(self):
        """Test validation with all valid keys."""
        config = {
            "source_directory": "src",
            "output_file": "dist/output.lua",
            "header_file": "header.lua",
            "namespace_file": "namespace.lua",
            "entrypoint_file": "main.lua",
            "footer_file": "footer.lua",
            "dcs_strict_sanitize": True,
            "scope": "local",
        }

        validated = read_composerrc.validate_config(config)
        self.assertEqual(validated, config)

    def test_validate_config_invalid_keys(self):
        """Test validation filters out invalid keys."""
        config = {"source_directory": "src", "invalid_key": "value", "another_invalid": 123}

        with patch("builtins.print") as mock_print:
            validated = read_composerrc.validate_config(config)

        self.assertEqual(validated, {"source_directory": "src"})
        # Check that warning was printed
        mock_print.assert_called_once()
        warning_msg = mock_print.call_args[0][0]
        self.assertIn("Unknown keys", warning_msg)
        self.assertIn("invalid_key", warning_msg)
        self.assertIn("another_invalid", warning_msg)

    def test_validate_config_scope_values(self):
        """Test validation with different scope values."""
        # Test with global scope
        config_global = {
            "source_directory": "src",
            "namespace_file": "namespace.lua",
            "scope": "global"
        }
        validated_global = read_composerrc.validate_config(config_global)
        self.assertEqual(validated_global["scope"], "global")

        # Test with local scope
        config_local = {
            "source_directory": "src",
            "namespace_file": "namespace.lua",
            "scope": "local"
        }
        validated_local = read_composerrc.validate_config(config_local)
        self.assertEqual(validated_local["scope"], "local")

    def test_output_for_github_actions(self):
        """Test GitHub Actions output generation."""
        config = {"source_directory": "src", "output_file": "dist/output.lua", "dcs_strict_sanitize": True}

        # Test with GITHUB_OUTPUT environment variable
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            output_file = f.name

        try:
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}):
                read_composerrc.output_for_github_actions(config)

            with open(output_file) as f:
                content = f.read()

            self.assertIn("rc_source_directory=src\n", content)
            self.assertIn("rc_output_file=dist/output.lua\n", content)
            self.assertIn("rc_dcs_strict_sanitize=true\n", content)
        finally:
            os.unlink(output_file)

    def test_output_for_github_actions_legacy(self):
        """Test GitHub Actions output generation with legacy format."""
        config = {"source_directory": "src", "dcs_strict_sanitize": False}

        # Test without GITHUB_OUTPUT (legacy mode)
        with patch.dict(os.environ, {}, clear=True):
            with patch("builtins.print") as mock_print:
                read_composerrc.output_for_github_actions(config)

            # Check legacy output format
            calls = [call[0][0] for call in mock_print.call_args_list]
            self.assertIn("::set-output name=rc_source_directory::src", calls)
            self.assertIn("::set-output name=rc_dcs_strict_sanitize::false", calls)

    def test_main_with_composerrc(self):
        """Test main function with .composerrc present."""
        config = {"source_directory": "src", "namespace_file": "namespace.lua"}

        with open(self.composerrc_path, "w") as f:
            json.dump(config, f)

        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            output_file = f.name

        try:
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}):
                with patch("sys.argv", ["read_composerrc.py", self.test_dir]):
                    with patch("builtins.print") as mock_print:
                        read_composerrc.main()

            # Check notice was printed
            notice_calls = [call[0][0] for call in mock_print.call_args_list if "::notice::" in call[0][0]]
            self.assertTrue(any(".composerrc file found" in call for call in notice_calls))
        finally:
            os.unlink(output_file)

    def test_main_without_composerrc(self):
        """Test main function without .composerrc present."""
        with patch("sys.argv", ["read_composerrc.py", self.test_dir]):
            with patch("builtins.print") as mock_print:
                read_composerrc.main()

        # Check notice was printed
        notice_calls = [call[0][0] for call in mock_print.call_args_list if "::notice::" in call[0][0]]
        self.assertTrue(any("No .composerrc file found" in call for call in notice_calls))

    def test_main_invalid_args(self):
        """Test main function with invalid arguments."""
        with patch("sys.argv", ["read_composerrc.py"]):
            with self.assertRaises(SystemExit) as cm:
                with patch("sys.stderr"):
                    read_composerrc.main()
            self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
