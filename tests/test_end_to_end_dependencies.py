#!/usr/bin/env python3
"""
End-to-end test that verifies the actual output with dependencies.
"""

import subprocess
import sys
from pathlib import Path

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent


def test_end_to_end_with_dependencies():
    """Test the complete composed output with dependencies."""
    test_dir = PROJECT_ROOT / "tests" / "fixtures" / "dependency_test"
    output_file = test_dir / "dist" / "test_mission.lua"

    # Run the composer directly
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "composer.py"),
        str(test_dir / "src"),
        str(output_file),
        "--namespace",
        "namespace.lua",
        "--entrypoint",
        "main.lua",
        "--dependencies",
        '[{"name": "test-lib", "type": "local", "source": "external_deps/test_lib.lua", "license": "external_deps/LICENSE", "description": "Small test library for integration testing"}]',
    ]

    result = subprocess.run(cmd, cwd=test_dir, capture_output=True, text=True)

    print("STDOUT:")
    print(result.stdout)
    print("STDERR:")
    print(result.stderr)

    assert result.returncode == 0, f"Composer failed: {result.stderr}"
    assert output_file.exists(), "Output file was not created"

    # Read and print the output
    content = output_file.read_text()
    print("\n" + "=" * 80)
    print("GENERATED OUTPUT:")
    print("=" * 80)
    print(content)
    print("=" * 80)

    # Verify the structure
    lines = content.split("\n")

    # Find key sections
    dep_start = None
    namespace_start = None
    main_start = None

    for i, line in enumerate(lines):
        if "-- External Dependency: test-lib" in line:
            dep_start = i
        elif "MyMission = {" in line:
            namespace_start = i
        elif "function MyMission.init()" in line:
            main_start = i

    # Verify order
    assert dep_start is not None, "Dependency section not found"
    assert namespace_start is not None, "Namespace section not found"
    assert main_start is not None, "Main section not found"
    assert dep_start < namespace_start < main_start, (
        f"Incorrect order: dep={dep_start}, ns={namespace_start}, main={main_start}"
    )

    # Verify dependency content
    assert "TestLib = {}" in content
    assert "function TestLib.greet(name)" in content
    assert "-- MIT License" in content

    # Verify sanitization
    assert "env.info(greeting)" in content
    assert 'env.info("Sum from TestLib: " .. sum)' in content
    assert 'env.info("Mission initialized: " .. MyMission.name)' in content

    # Clean up
    if output_file.exists():
        output_file.unlink()
        if output_file.parent.exists():
            output_file.parent.rmdir()

    print("\n✅ End-to-end test passed!")


if __name__ == "__main__":
    test_end_to_end_with_dependencies()
