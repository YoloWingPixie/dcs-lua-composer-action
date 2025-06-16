#!/usr/bin/env python3
"""
Test that generates actual output files to examine the composed result with dependencies.
"""

import json
import subprocess
import sys
from pathlib import Path

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "tests" / "output_examples"


def run_composer_test(test_name, working_dir, src_dir, output_file, dependencies, namespace_content, main_content):
    """Run a composer test and generate output."""
    print(f"\n{'='*60}")
    print(f"Running test: {test_name}")
    print(f"{'='*60}")

    # Create source directory
    src_path = working_dir / src_dir
    src_path.mkdir(parents=True, exist_ok=True)

    # Create namespace and main files
    (src_path / "namespace.lua").write_text(namespace_content)
    (src_path / "main.lua").write_text(main_content)

    # Run composer
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "composer.py"),
        str(src_path),
        str(output_file),
        "--namespace", "namespace.lua",
        "--entrypoint", "main.lua",
        "--dependencies", json.dumps(dependencies)
    ]

    result = subprocess.run(cmd, cwd=working_dir, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        return False

    print(f"✅ Output generated: {output_file}")
    print(f"   File size: {output_file.stat().st_size:,} bytes")
    print(f"   Lines: {len(output_file.read_text().splitlines()):,}")
    return True


def test_with_test_lib():
    """Generate output with our small test library."""
    test_dir = PROJECT_ROOT / "tests" / "fixtures" / "dependency_test"
    output_file = OUTPUT_DIR / "example_with_test_lib.lua"

    dependencies = [{
        "name": "test-lib",
        "type": "local",
        "source": "external_deps/test_lib.lua",
        "license": "external_deps/LICENSE",
        "description": "Small test library for integration testing"
    }]

    namespace_content = """-- Test Mission Namespace
TestMission = {
    name = "Test Mission with Dependencies",
    version = "1.0.0"
}"""

    main_content = """-- Main entry point
function TestMission.start()
    -- Use the test library
    local message = TestLib.greet("DCS World")
    env.info(message)

    local result = TestLib.add(42, 58)
    env.info("The answer is: " .. result)
end

TestMission.start()"""

    return run_composer_test(
        "Test Library Example",
        test_dir,
        "src",
        output_file,
        dependencies,
        namespace_content,
        main_content
    )


def test_with_mist():
    """Generate output with mock MIST-like dependency."""
    test_dir = OUTPUT_DIR / "mist_test"
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create a mock MIST-like file for demonstration
    mock_mist_dir = test_dir / "mock_deps"
    mock_mist_dir.mkdir(exist_ok=True)

    # Create a simplified mock MIST
    mock_mist_content = """-- Mock MIST (Mission Scripting Tools)
-- This is a simplified mock for demonstration purposes
-- Real MIST is much more comprehensive

mist = {}
mist.majorVersion = 4
mist.minorVersion = 5
mist.build = 126

-- Core MIST tables
mist.flagFuncs = {}
mist.mapObjs = {}
mist.DBs = {}
mist.dynAdd = {}
mist.utils = {}
mist.vec = {}
mist.goRoute = {}
mist.ground = {}

-- Some basic MIST utilities
mist.utils.get2DDist = function(point1, point2)
    local xDiff = point1.x - point2.x
    local zDiff = point1.z - point2.z
    return math.sqrt(xDiff * xDiff + zDiff * zDiff)
end

mist.utils.get3DDist = function(point1, point2)
    local xDiff = point1.x - point2.x
    local yDiff = (point1.y or 0) - (point2.y or 0)
    local zDiff = point1.z - point2.z
    return math.sqrt(xDiff * xDiff + yDiff * yDiff + zDiff * zDiff)
end

mist.utils.makeVec3 = function(vec2, y)
    if not vec2.z then
        return {x = vec2.x, y = y or 0, z = vec2.y}
    else
        return {x = vec2.x, y = y or vec2.y or 0, z = vec2.z}
    end
end

-- Scheduler function
mist.scheduleFunction = function(fn, vars, time)
    timer.scheduleFunction(fn, vars, time)
end

-- Message functions
mist.message = {}
mist.message.add = function(msgTable)
    trigger.action.outText(msgTable.text or "", msgTable.displayTime or 10)
end

env.info("MIST " .. mist.majorVersion .. "." .. mist.minorVersion .. "." .. mist.build .. " loaded")

return mist"""

    (mock_mist_dir / "mist.lua").write_text(mock_mist_content)

    # Create mock license
    (mock_mist_dir / "LICENSE").write_text("""MIST License
Free to use for DCS World mission making.
See https://github.com/mrSkortch/MissionScriptingTools for details.""")

    output_file = OUTPUT_DIR / "example_with_mist_like.lua"

    dependencies = [{
        "name": "mist",
        "type": "local",
        "source": "mock_deps/mist.lua",
        "license": "mock_deps/LICENSE",
        "description": "Mission Scripting Tools - Popular DCS scripting framework (Mock)"
    }]

    namespace_content = """-- Advanced Mission using MIST
AdvancedMission = {
    name = "MIST-Enhanced Mission",
    version = "2.0.0"
}"""

    main_content = """-- Main mission script using MIST
function AdvancedMission.init()
    env.info("Initializing Advanced Mission with MIST")

    -- Check if MIST is loaded
    if mist then
        env.info("MIST version: " .. (mist.majorVersion or "unknown"))

        -- Example: Schedule a function using MIST
        mist.scheduleFunction(function()
            env.info("This message is scheduled by MIST!")
        end, {}, timer.getTime() + 10)

        -- Example: Use MIST utilities
        local vec3 = {x = 100, y = 0, z = 200}
        local distance = mist.utils.get2DDist({x = 0, z = 0}, vec3)
        env.info("Distance from origin: " .. distance)
    else
        env.warning("MIST not loaded!")
    end
end

AdvancedMission.init()"""

    return run_composer_test(
        "MIST Dependency Example",
        test_dir,
        "src",
        output_file,
        dependencies,
        namespace_content,
        main_content
    )


def test_multiple_dependencies():
    """Generate output with multiple dependencies."""
    test_dir = OUTPUT_DIR / "multi_dep_test"
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create some local test dependencies
    deps_dir = test_dir / "deps"
    deps_dir.mkdir(exist_ok=True)

    # First dependency - utilities
    (deps_dir / "utils.lua").write_text("""-- Utility Library
Utils = {}

function Utils.formatTime(seconds)
    local hours = math.floor(seconds / 3600)
    local mins = math.floor((seconds % 3600) / 60)
    local secs = seconds % 60
    return string.format("%02d:%02d:%02d", hours, mins, secs)
end

function Utils.randomPoint(center, radius)
    local angle = math.random() * 2 * math.pi
    local r = math.sqrt(math.random()) * radius
    return {
        x = center.x + r * math.cos(angle),
        z = center.z + r * math.sin(angle)
    }
end

return Utils""")

    (deps_dir / "utils_license.txt").write_text("""Public Domain
No rights reserved.""")

    # Second dependency - logger
    (deps_dir / "logger.lua").write_text("""-- Enhanced Logger
Logger = {
    levels = {
        DEBUG = 1,
        INFO = 2,
        WARN = 3,
        ERROR = 4
    },
    currentLevel = 2
}

function Logger:log(level, message)
    if level >= self.currentLevel then
        local prefix = ""
        if level == self.levels.DEBUG then prefix = "[DEBUG]"
        elseif level == self.levels.WARN then prefix = "[WARN]"
        elseif level == self.levels.ERROR then prefix = "[ERROR]"
        else prefix = "[INFO]" end

        env.info(prefix .. " " .. message)
    end
end

return Logger""")

    output_file = OUTPUT_DIR / "example_with_multiple_deps.lua"

    dependencies = [
        {
            "name": "utils",
            "type": "local",
            "source": "deps/utils.lua",
            "license": "deps/utils_license.txt",
            "description": "Utility functions"
        },
        {
            "name": "logger",
            "type": "local",
            "source": "deps/logger.lua",
            "description": "Enhanced logging system"
        }
    ]

    namespace_content = """-- Complex Mission with Multiple Dependencies
ComplexMission = {
    name = "Multi-Dependency Mission",
    version = "3.0.0"
}"""

    main_content = """-- Mission using multiple dependencies
function ComplexMission.run()
    -- Use Logger
    Logger:log(Logger.levels.INFO, "Mission starting...")

    -- Use Utils
    local missionTime = 3661  -- 1 hour, 1 minute, 1 second
    local timeStr = Utils.formatTime(missionTime)
    Logger:log(Logger.levels.INFO, "Mission time: " .. timeStr)

    -- Generate random point
    local base = {x = 1000, z = 2000}
    local randomPos = Utils.randomPoint(base, 500)
    Logger:log(Logger.levels.DEBUG, string.format("Random position: x=%.2f, z=%.2f", randomPos.x, randomPos.z))

    -- Another random point
    local enemyBase = {x = 5000, z = 8000}
    local enemyPos = Utils.randomPoint(enemyBase, 1000)
    Logger:log(Logger.levels.INFO, string.format("Enemy spotted at: x=%.2f, z=%.2f", enemyPos.x, enemyPos.z))

    -- Calculate mission progress
    local progress = 75.5
    Logger:log(Logger.levels.WARN, "Mission " .. progress .. "% complete")

    Logger:log(Logger.levels.INFO, "Mission initialized successfully!")
end

ComplexMission.run()"""

    return run_composer_test(
        "Multiple Dependencies Example",
        test_dir,
        "src",
        output_file,
        dependencies,
        namespace_content,
        main_content
    )


def main():
    """Run all tests and generate example outputs."""
    print("Generating example outputs with dependencies...")
    OUTPUT_DIR.mkdir(exist_ok=True)

    results = []

    # Run tests
    results.append(("Test Library", test_with_test_lib()))
    results.append(("Multiple Dependencies", test_multiple_dependencies()))
    results.append(("MIST Integration", test_with_mist()))

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    for name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{name}: {status}")

    print(f"\nOutput files generated in: {OUTPUT_DIR}")
    print("\nYou can examine these files to see how dependencies are injected:")
    for file in sorted(OUTPUT_DIR.glob("*.lua")):
        print(f"  - {file.name}")


if __name__ == "__main__":
    main()
