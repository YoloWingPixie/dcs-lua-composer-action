#!/usr/bin/env python3
"""
Integration tests for the dependency injection functionality.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def run_composer(working_dir, args):
    """Run the composer script with given arguments."""
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "composer.py"),
    ] + args

    result = subprocess.run(
        cmd,
        cwd=working_dir,
        capture_output=True,
        text=True,
    )

    return result


class TestDependencyIntegration:
    """Integration tests for dependency functionality."""

    def test_local_dependency_integration(self):
        """Test end-to-end integration with local dependency."""
        # Use the test fixture directory
        test_dir = PROJECT_ROOT / "tests" / "fixtures" / "dependency_test"

        # Read the .composerrc to get configuration
        with open(test_dir / ".composerrc") as f:
            config = json.load(f)

        # Run the composer
        result = run_composer(
            test_dir,
            [
                str(test_dir / config["source_directory"]),
                str(test_dir / config["output_file"]),
                "--namespace",
                config["namespace_file"],
                "--entrypoint",
                config["entrypoint_file"],
                "--dependencies",
                json.dumps(config["dependencies"]),
            ],
        )

        # Check that the build succeeded
        assert result.returncode == 0, f"Build failed: {result.stderr}"

        # Check the output file exists
        output_file = test_dir / config["output_file"]
        assert output_file.exists()

        # Read and verify the output content
        content = output_file.read_text()

        # Verify dependency injection
        assert "-- External Dependency: test-lib" in content
        assert "-- Description: Small test library for integration testing" in content
        assert "-- Source: external_deps/test_lib.lua" in content

        # Verify license inclusion
        assert "-- License:" in content
        assert "-- MIT License" in content
        assert "-- Copyright (c) 2024 Test Library" in content

        # Verify the dependency code is included
        assert "TestLib = {}" in content
        assert "function TestLib.greet(name)" in content
        assert "function TestLib.add(a, b)" in content

        # Verify namespace comes after dependencies
        namespace_pos = content.find("MyMission = {")
        testlib_pos = content.find("TestLib = {}")
        assert testlib_pos < namespace_pos, "Dependencies should come before namespace"

        # Verify main code can use the dependency
        assert "TestLib.greet" in content
        assert "TestLib.add" in content

        # Verify sanitization was applied
        assert "env.info(greeting)" in content
        assert 'env.info("Sum from TestLib: " .. sum)' in content

        # Clean up
        if output_file.exists():
            output_file.unlink()
            output_file.parent.rmdir()

    @pytest.mark.skip(reason="URL mocking doesn't work across subprocess boundaries")
    @patch("dependency_manager.urllib.request.urlopen")
    def test_url_dependency_integration(self, mock_urlopen):
        """Test integration with URL-based dependency."""
        # Create a temporary test environment
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)
            src_dir = test_dir / "src"
            src_dir.mkdir()

            # Create minimal test files
            (src_dir / "namespace.lua").write_text("TestNS = {}")
            (src_dir / "main.lua").write_text("print('Using UtilLib: ' .. UtilLib.version)")

            # Mock URL responses
            lib_response = Mock()
            lib_response.read.return_value = b"UtilLib = { version = '2.0' }\nfunction UtilLib.test() return true end"

            license_response = Mock()
            license_response.read.return_value = b"Apache License 2.0"

            def urlopen_side_effect(url):
                if "utils.lua" in url:
                    return lib_response
                elif "LICENSE" in url:
                    return license_response
                else:
                    raise Exception(f"Unexpected URL: {url}")

            mock_urlopen.side_effect = urlopen_side_effect

            # Run composer with URL dependency
            dependencies = [
                {
                    "name": "util-lib",
                    "type": "url",
                    "source": "https://example.com/utils.lua",
                    "license": "https://example.com/LICENSE",
                    "description": "Utility library from URL",
                }
            ]

            result = run_composer(
                test_dir,
                [
                    str(src_dir),
                    str(test_dir / "output.lua"),
                    "--namespace",
                    "namespace.lua",
                    "--entrypoint",
                    "main.lua",
                    "--dependencies",
                    json.dumps(dependencies),
                ],
            )

            assert result.returncode == 0, f"Build failed: {result.stderr}"

            # Verify output
            output_content = (test_dir / "output.lua").read_text()
            assert "-- External Dependency: util-lib" in output_content
            assert "-- Source: https://example.com/utils.lua" in output_content
            assert "-- Apache License 2.0" in output_content
            assert "UtilLib = { version = '2.0' }" in output_content
            assert "env.info('Using UtilLib: ' .. UtilLib.version)" in output_content

    def test_multiple_dependencies_order(self):
        """Test that multiple dependencies are injected in declaration order."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)
            src_dir = test_dir / "src"
            deps_dir = test_dir / "deps"
            src_dir.mkdir()
            deps_dir.mkdir()

            # Create test dependencies
            (deps_dir / "lib1.lua").write_text("Lib1 = { name = 'First' }")
            (deps_dir / "lib2.lua").write_text("Lib2 = { name = 'Second' }")
            (deps_dir / "lib3.lua").write_text("Lib3 = { name = 'Third' }")

            # Create minimal source files
            (src_dir / "namespace.lua").write_text("NS = {}")
            (src_dir / "main.lua").write_text("print(Lib1.name .. Lib2.name .. Lib3.name)")

            # Define dependencies in specific order
            dependencies = [
                {"name": "lib1", "type": "local", "source": "deps/lib1.lua"},
                {"name": "lib2", "type": "local", "source": "deps/lib2.lua"},
                {"name": "lib3", "type": "local", "source": "deps/lib3.lua"},
            ]

            result = run_composer(
                test_dir,
                [
                    str(src_dir),
                    str(test_dir / "output.lua"),
                    "--namespace",
                    "namespace.lua",
                    "--entrypoint",
                    "main.lua",
                    "--dependencies",
                    json.dumps(dependencies),
                ],
            )

            assert result.returncode == 0, f"Build failed: {result.stderr}"

            # Check order in output
            content = (test_dir / "output.lua").read_text()
            lib1_pos = content.find("Lib1 = { name = 'First' }")
            lib2_pos = content.find("Lib2 = { name = 'Second' }")
            lib3_pos = content.find("Lib3 = { name = 'Third' }")
            ns_pos = content.find("NS = {}")

            # Verify correct order
            assert lib1_pos < lib2_pos < lib3_pos < ns_pos, (
                "Dependencies should be in declaration order and before namespace"
            )

    def test_dependency_sanitization(self):
        """Test that dependencies are properly sanitized."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)
            src_dir = test_dir / "src"
            deps_dir = test_dir / "deps"
            src_dir.mkdir()
            deps_dir.mkdir()

            # Create dependency with code that needs sanitization
            dep_content = """
            -- Test dependency
            local TestDep = {}

            function TestDep.init()
                print("Initializing TestDep")
                log.info("TestDep ready")
                log.warning("This is a warning")
                log.error("This is an error")
            end

            return TestDep
            """
            (deps_dir / "testdep.lua").write_text(dep_content)

            # Create minimal source files
            (src_dir / "namespace.lua").write_text("NS = {}")
            (src_dir / "main.lua").write_text("-- Main")

            dependencies = [{"name": "testdep", "type": "local", "source": "deps/testdep.lua"}]

            result = run_composer(
                test_dir,
                [
                    str(src_dir),
                    str(test_dir / "output.lua"),
                    "--namespace",
                    "namespace.lua",
                    "--entrypoint",
                    "main.lua",
                    "--dependencies",
                    json.dumps(dependencies),
                ],
            )

            assert result.returncode == 0, f"Build failed: {result.stderr}"

            # Verify sanitization
            content = (test_dir / "output.lua").read_text()
            assert 'env.info("Initializing TestDep")' in content
            assert 'env.info("TestDep ready")' in content
            assert 'env.warning("This is a warning")' in content
            assert 'env.error("This is an error")' in content
            assert "print(" not in content
            assert "log.info(" not in content
