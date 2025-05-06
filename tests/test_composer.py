import datetime  # Import at the top level of the test file
import re

# Make sure composer.py is importable, assuming it's in the parent directory
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import composer


# Helper function to create a file with content
def create_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# --- Tests for find_lua_files ---
def test_find_lua_files_empty(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    assert composer.find_lua_files(src_dir) == []


def test_find_lua_files_basic(tmp_path):
    # Use a sub-tmp_path for file creation to keep it clean
    project_dir = tmp_path / "project_src"
    project_dir.mkdir()

    # Helper to create files for this specific test
    def _create_file(path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    _create_file(project_dir / "file1.lua", "content1")
    _create_file(project_dir / "file2.txt", "content2")  # Non-lua file
    _create_file(project_dir / "sub" / "file3.lua", "content3")

    expected_files = sorted([project_dir / "file1.lua", project_dir / "sub" / "file3.lua"])
    actual_files = sorted(composer.find_lua_files(project_dir))
    assert actual_files == expected_files


# --- Tests for get_module_name_from_path ---
def test_get_module_name_from_path(tmp_path):
    src_dir = tmp_path / "project_src"
    src_dir.mkdir()

    path1 = src_dir / "module.lua"
    assert composer.get_module_name_from_path(path1, src_dir) == "module"

    path2 = src_dir / "package" / "submodule.lua"
    assert composer.get_module_name_from_path(path2, src_dir) == "package.submodule"

    path3 = src_dir / "another.module.with.dots.lua"
    assert composer.get_module_name_from_path(path3, src_dir) == "another.module.with.dots"


# --- Tests for get_path_from_module_name ---
def test_get_path_from_module_name(tmp_path):
    src_dir = tmp_path / "project_src"
    src_dir.mkdir()

    assert composer.get_path_from_module_name("module", src_dir) == src_dir / "module.lua"
    assert composer.get_path_from_module_name("package.submodule", src_dir) == src_dir / "package" / "submodule.lua"


# --- Tests for parse_dependencies ---
def test_parse_dependencies_none(tmp_path):
    src_dir = tmp_path / "src"
    file_path = src_dir / "main.lua"
    # Re-add _create_file or use the one from find_lua_files_basic if it was meant to be global
    create_file(file_path, "print('hello')")
    assert composer.parse_dependencies(file_path, src_dir) == set()


def test_parse_dependencies_simple(tmp_path):
    src_dir = tmp_path / "src"
    file_path = src_dir / "main.lua"
    create_file(file_path, """require "module1"\nrequire("module2")""")
    assert composer.parse_dependencies(file_path, src_dir) == {"module1", "module2"}


def test_parse_dependencies_with_comments_and_variants(tmp_path):
    src_dir = tmp_path / "src"
    file_path = src_dir / "main.lua"
    create_file(
        file_path,
        """
-- require "commented_out"
local mod1 = require('module.one') -- comment after
require "module.two"; -- with semicolon
--[[
  require "multiline_commented_out"
--]]
local str = "fake require 'not.a.module'"
""",
    )
    assert composer.parse_dependencies(file_path, src_dir) == {
        "module.one",
        "module.two",
    }


# --- Tests for sanitize_content ---
def test_sanitize_print(tmp_path):
    file_path = tmp_path / "test.lua"
    content = "print(\"Hello\")\nlocal a = 1\nprint('world');"
    # Transformed to env.info
    expected = "env.info(\"Hello\")\nlocal a = 1\nenv.info('world');"
    assert composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True) == expected


def test_sanitize_log_info(tmp_path):
    file_path = tmp_path / "test.lua"
    content = 'log.info("Starting script")\nlocal b = 2'
    expected = 'env.info("Starting script")\nlocal b = 2'
    assert composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True) == expected


def test_sanitize_log_warning(tmp_path):
    file_path = tmp_path / "test.lua"
    content = 'log.warning("Problem detected")\nlocal c = 3'
    expected = 'env.warning("Problem detected")\nlocal c = 3'
    assert composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True) == expected


def test_sanitize_log_error(tmp_path):
    file_path = tmp_path / "test.lua"
    content = 'log.error("Critical failure");\nlocal d = 4'
    expected = 'env.error("Critical failure");\nlocal d = 4'
    assert composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True) == expected


def test_sanitize_log_other_removed(tmp_path):
    file_path = tmp_path / "test.lua"
    content = 'log.debug("Value is nil")\nlog.trace("Entering func");\nlocal e = 5'
    expected = "\n\nlocal e = 5"  # Other log levels are removed entirely
    assert composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True) == expected


def test_sanitize_require(tmp_path):
    file_path = tmp_path / "test.lua"
    content = 'require "mymodule"\nlocal c = 3'
    expected = "local c = 3"
    assert composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True) == expected


def test_sanitize_package_line_removal(tmp_path):
    file_path = tmp_path / "test.lua"
    content = "local x = package.path\nlocal y = 1\n  package.loaded['foo'] = nil -- indented"
    expected = "local y = 1\n"
    assert composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True) == expected


def test_sanitize_goto_failure(tmp_path):
    file_path = tmp_path / "test_goto.lua"
    content = "local x = 1\ngoto mylabel\n::mylabel::"
    with pytest.raises(
        Exception,
        match=r"Disallowed 'goto' statement found in .*?test_goto.lua on line 2: goto mylabel",
    ):
        composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True)


def test_sanitize_goto_in_comment(tmp_path):
    file_path = tmp_path / "test_goto_comment.lua"
    content = "-- goto mylabel should be fine\nlocal y = 2"
    expected = "-- goto mylabel should be fine\nlocal y = 2"
    assert composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True) == expected


def test_sanitize_verbatim_content(tmp_path):
    file_path = tmp_path / "header.txt"
    content = 'print("This should stay")\nrequire "module" -- also stays'
    # Verbatim content is not sanitized, regardless of strict flag, as is_lua_module=False
    assert composer.sanitize_content(content, file_path, is_lua_module=False, dcs_strict_sanitize=True) == content


# --- Tests for strict DCS sanitization flag ---
def test_sanitize_strict_os_fails(tmp_path):
    file_path = tmp_path / "test_strict_os.lua"
    content = "local t = os.time()"
    with pytest.raises(Exception, match=r"Disallowed DCS API usage \(os\.time\)"):
        composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True)


def test_sanitize_strict_os_passes_when_false(tmp_path):
    file_path = tmp_path / "test_strict_os_pass.lua"
    content = "local t = os.time()"
    # Expect content back unmodified because strict check is off, and os.time isn't otherwise sanitized
    assert composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=False) == content


def test_sanitize_strict_io_fails(tmp_path):
    file_path = tmp_path / "test_strict_io.lua"
    content = "local f = io.open('file')"
    with pytest.raises(Exception, match=r"Disallowed DCS API usage \(io\.open\)"):
        composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True)


def test_sanitize_strict_lfs_fails(tmp_path):
    file_path = tmp_path / "test_strict_lfs.lua"
    content = "local d = lfs.writedir()"
    with pytest.raises(Exception, match=r"Disallowed DCS API usage \(lfs\.writedir\)"):
        composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True)


def test_sanitize_loadlib_removed_with_warning(tmp_path, capsys):
    file_path = tmp_path / "test_loadlib_warn.lua"
    content = "local a = 1\nlocal mylib = loadlib('some.path.dll', 'luaopen_somelib')\nlocal b = 2"
    # Expect the loadlib line to be removed, collapsing newlines.
    expected_content = "local a = 1\nlocal b = 2"

    sanitized = composer.sanitize_content(
        content, file_path, is_lua_module=True, dcs_strict_sanitize=True
    )  # strict flag doesn't affect loadlib warning/removal
    assert sanitized.strip() == expected_content.strip()  # Use strip to handle potential subtle newline differences

    captured = capsys.readouterr()
    assert (
        f"WARNING: [{file_path}] Disallowed 'loadlib' call found and was removed: loadlib('some.path.dll', 'luaopen_somelib')"
        in captured.out
    )


def test_sanitize_strict_local_var_ok(tmp_path):
    # Ensure naming a local variable 'os' or 'io' doesn't trigger the strict check
    file_path = tmp_path / "test_strict_local_var.lua"
    # Removing the ambiguous os.foo = 1, just testing local declarations
    content = "local os = {}\nlocal lfs = nil\nlocal io = 'hello'"
    # Should pass without error when strict=True because os/lfs/io are locals, not stdlib calls/indices
    sanitized = composer.sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True)
    assert sanitized == content  # Nothing should be removed/changed


# --- Tests for topological_sort ---
def test_topological_sort_simple_chain(tmp_path):
    graph_complete = {"A": set(), "B": {"A"}, "C": {"B"}}
    modules = {"A", "B", "C"}
    # Create dummy paths for the module_to_path_map
    dummy_src_dir = tmp_path / "dummy_src"
    module_to_path_map = {
        "A": dummy_src_dir / "A.lua",
        "B": dummy_src_dir / "B.lua",
        "C": dummy_src_dir / "C.lua",
    }
    # Create the dummy files/directories so Path().parent works
    (dummy_src_dir).mkdir(exist_ok=True)
    for p in module_to_path_map.values():
        p.touch()
    assert composer.topological_sort(graph_complete, modules, module_to_path_map) == [
        "A",
        "B",
        "C",
    ]


def test_topological_sort_multiple_dependencies(tmp_path):
    graph_complete = {"A": set(), "B": set(), "C": {"A", "B"}, "D": {"C"}}
    modules = {"A", "B", "C", "D"}
    dummy_src_dir = tmp_path / "dummy_src"
    module_to_path_map = {
        "A": dummy_src_dir / "A.lua",
        "B": dummy_src_dir / "B.lua",
        "C": dummy_src_dir / "C.lua",
        "D": dummy_src_dir / "D.lua",
    }
    (dummy_src_dir).mkdir(exist_ok=True)
    for p in module_to_path_map.values():
        p.touch()
    result = composer.topological_sort(graph_complete, modules, module_to_path_map)
    assert len(result) == 4
    assert result.index("A") < result.index("C")
    assert result.index("B") < result.index("C")
    assert result.index("C") < result.index("D")
    assert result == ["A", "B", "C", "D"] or result == ["B", "A", "C", "D"]


def test_topological_sort_circular_dependency(tmp_path):
    graph = {"A": {"C"}, "B": {"A"}, "C": {"B"}}
    modules = {"A", "B", "C"}
    dummy_src_dir = tmp_path / "dummy_src"
    module_to_path_map = {
        "A": dummy_src_dir / "A.lua",
        "B": dummy_src_dir / "B.lua",
        "C": dummy_src_dir / "C.lua",
    }
    (dummy_src_dir).mkdir(exist_ok=True)
    for p in module_to_path_map.values():
        p.touch()
    with pytest.raises(Exception, match="Circular dependency detected"):
        composer.topological_sort(graph, modules, module_to_path_map)


# --- Tests for build_project (more integration-like, focus on key aspects) ---
@pytest.fixture
def sample_project_structure_basic(tmp_path):
    # This fixture is for the older basic_composition test, ensure it uses its own sub-tmp_path
    src = tmp_path / "basic_test_project"
    # Re-add _create_file or ensure it's accessible globally in this test file
    create_file(src / "header.txt", "-- HEADER --")
    create_file(src / "ns" / "main_ns.lua", 'ProjectNS = {}\nprint("NS loaded")')
    create_file(
        src / "core" / "utils.lua",
        """require "core.data"\nProjectNS.utils_loaded = true\nprint("utils print")""",
    )
    create_file(src / "core" / "data.lua", 'ProjectNS.data_loaded = true\nprint("data print")')
    create_file(
        src / "app" / "main_app.lua",
        """require "core.utils"\nProjectNS.app_start = function() print("App Start") end""",
    )
    create_file(src / "footer.txt", "-- FOOTER --")
    return src


def test_build_project_basic_composition(tmp_path, sample_project_structure_basic, mocker):
    mocked_now = datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    mocker.patch("composer.datetime.datetime")
    composer.datetime.datetime.now.return_value = mocked_now

    src_dir = sample_project_structure_basic
    output_file = tmp_path / "dist" / "final.lua"

    composer.build_project(
        src_dir=str(src_dir),
        output_file=str(output_file),
        header_file_rel="header.txt",
        namespace_file_rel="ns/main_ns.lua",
        entrypoint_file_rel="app/main_app.lua",
        footer_file_rel="footer.txt",
    )

    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "-- HEADER --" in content
    assert "-- FOOTER --" in content
    assert f"-- Combined and Sanitized Lua script generated on {mocked_now.isoformat()}" in content
    assert "ProjectNS = {}" in content
    assert 'print("NS loaded")' not in content
    assert 'env.info("NS loaded")' in content
    assert "ProjectNS.data_loaded = true" in content
    assert "ProjectNS.utils_loaded = true" in content
    assert content.find("ProjectNS.data_loaded = true") < content.find("ProjectNS.utils_loaded = true")
    assert 'print("data print")' not in content
    assert 'env.info("data print")' in content
    assert 'print("utils print")' not in content
    assert 'env.info("utils print")' in content
    assert re.search(
        r"ProjectNS\.app_start\s*=\s*function\(\s*\)\s*env\.info\(\"App Start\"\)\s*end",
        content,
    ), "Transformed app_start function not found or incorrect"
    assert 'print("App Start")' not in content


def test_build_project_missing_required_files(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    create_file(src_dir / "entry.lua", "-- entry --")

    with pytest.raises(FileNotFoundError, match=r"REQUIRED Namespace file 'ns.lua' not found"):
        composer.build_project(str(src_dir), "out.lua", None, "ns.lua", "entry.lua", None)

    create_file(src_dir / "ns.lua", "-- namespace --")
    with pytest.raises(
        FileNotFoundError,
        match=r"REQUIRED Entrypoint file 'missing_entry.lua' not found",
    ):
        composer.build_project(str(src_dir), "out.lua", None, "ns.lua", "missing_entry.lua", None)


def test_build_project_goto_in_core_module_fails(tmp_path):
    src = tmp_path / "src_goto_fail"
    create_file(src / "ns.lua", "NS={}")
    create_file(src / "main.lua", "print('ok')")
    create_file(src / "core" / "bad.lua", "local a=1\ngoto oops\n::oops::\nNS.val=a")

    with pytest.raises(
        Exception,
        match=r"Disallowed 'goto' statement found in .*?bad.lua on line 2: goto oops",
    ):
        composer.build_project(
            src_dir=str(src),
            output_file=str(tmp_path / "dist" / "failed.lua"),
            header_file_rel=None,
            namespace_file_rel="ns.lua",
            entrypoint_file_rel="main.lua",
            footer_file_rel=None,
        )


def test_build_project_complex_functional(tmp_path, mocker):
    base_test_dir = Path(__file__).resolve().parent
    src_dir = base_test_dir / "functional_test_project" / "src"

    output_file = tmp_path / "dist" / "complex_new_final_script.lua"

    mocked_now = datetime.datetime(
        2023, 10, 27, 11, 0, 0, tzinfo=datetime.timezone.utc
    )  # Changed timestamp for new test
    mocker.patch("composer.datetime.datetime")
    composer.datetime.datetime.now.return_value = mocked_now

    composer.build_project(
        src_dir=str(src_dir),
        output_file=str(output_file),
        header_file_rel="header.lua",  # Corrected to .lua
        namespace_file_rel="namespace.lua",  # Corrected name
        entrypoint_file_rel="main.lua",  # Corrected name
        footer_file_rel=None,  # Corrected: No footer in new spec
    )

    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")

    # 1. Check for header (verbatim, as it's not treated as a Lua module by default in build_project if not .lua)
    #    However, our composer.py sanitize_content *is* called with is_lua_module=False if header_file_rel is not None
    #    And build_project passes header_path to sanitize_content.
    #    The user specified header.lua which *should* be treated as Lua if header_file_rel implies it.
    #    Current build_project logic for header/footer: sanitize_content(f.read(), is_lua_module=False)
    #    This means header.lua print will NOT be sanitized by current main script logic. This is okay if intended.
    assert "-- Header for New Functional Test --" in content
    assert 'MyProjectNS.header_marker = "Header Was Here"' in content
    assert 'print("header.lua print check")' in content  # Print stays due to is_lua_module=False for header

    # 2. Check for build info
    assert f"-- Combined and Sanitized Lua script generated on {mocked_now.isoformat()}" in content
    assert "-- Header File: header.lua" in content
    assert "-- Namespace File: namespace.lua" in content
    assert "-- Entrypoint File: main.lua" in content
    assert "-- Footer File:" not in content  # No footer means the line isn't there

    # 3. Check for namespace content (sanitized)
    assert 'MyProjectNS.namespace_version = "1.0-new"' in content
    assert 'print("namespace.lua print check")' not in content

    # 4. Core Modules: Define expected sanitized content and names
    core_modules_expected_content = {
        "component.component_one": "MyProjectNS.component_one_loaded = true",
        "component.component_two": "MyProjectNS.component_two_loaded = true",
        "component.component_three": "MyProjectNS.component_three_loaded = true",
        "controller.controller": "MyProjectNS.controller_loaded = true",
        "manager": "MyProjectNS.manager_loaded = true",
        "feature.feature_one": "MyProjectNS.feature_one_loaded = true",
        "feature.feature_two": "MyProjectNS.feature_two_loaded = true",
        "feature.feature_three": "MyProjectNS.feature_three_loaded = true",
        "feature.feature_four": "MyProjectNS.feature_four_loaded = true",
        "feature.feature_five": "MyProjectNS.feature_five_loaded = true",
        "service": "MyProjectNS.service_loaded = true",
    }

    for name, snippet in core_modules_expected_content.items():
        assert snippet in content, f"Snippet for {name} not found."
        simple_name = name.split(".")[-1]
        assert f'print("{simple_name} print")' not in content, f"Original print from {name} still present."

        # Specific log checks based on module where they were added
        if name == "service":
            assert 'log.warning("Service is starting up with several features!")' not in content
            assert 'env.warning("Service is starting up with several features!")' in content
            assert f'env.info("{simple_name} print")' in content  # The original print is now env.info
        elif name == "feature.feature_five":
            assert 'log.error("Feature five encountered a simulated error condition!")' not in content
            assert 'env.error("Feature five encountered a simulated error condition!")' in content
            assert f'env.info("{simple_name} print")' in content  # The original print is now env.info
        else:
            # Default check for other modules that only had print
            assert f'env.info("{simple_name} print")' in content, f"Transformed env.info for {name} not found."

        assert f'require "{name}"' not in content, f"Self-require found for {name}"

    # Define expected order based on dependencies:
    # comp1, comp2, comp3, controller, manager are roots for this graph part
    idx_comp1 = content.find(core_modules_expected_content["component.component_one"])
    idx_comp2 = content.find(core_modules_expected_content["component.component_two"])
    idx_comp3 = content.find(core_modules_expected_content["component.component_three"])
    idx_ctrl = content.find(core_modules_expected_content["controller.controller"])
    idx_mgr = content.find(core_modules_expected_content["manager"])

    idx_f1 = content.find(core_modules_expected_content["feature.feature_one"])
    idx_f2 = content.find(core_modules_expected_content["feature.feature_two"])
    idx_f3 = content.find(core_modules_expected_content["feature.feature_three"])
    idx_f4 = content.find(core_modules_expected_content["feature.feature_four"])
    idx_f5 = content.find(core_modules_expected_content["feature.feature_five"])
    idx_svc = content.find(core_modules_expected_content["service"])

    # Feature 1 depends on comp 2,3
    assert idx_comp2 < idx_f1, "Comp2 should be before F1"
    assert idx_comp3 < idx_f1, "Comp3 should be before F1"

    # feature 2 depends on comp 1
    assert idx_comp1 < idx_f2, "Comp1 should be before F2"

    # feature 3 depends on both comp 1, and feature 2
    assert idx_comp1 < idx_f3, "Comp1 should be before F3"
    assert idx_f2 < idx_f3, "F2 should be before F3"

    # feature 4 depends on feature 2, and controller
    assert idx_f2 < idx_f4, "F2 should be before F4"
    assert idx_ctrl < idx_f4, "Controller should be before F4"

    # Feature 5 depends on manager and feature 4, and feature 1
    assert idx_mgr < idx_f5, "Manager should be before F5"
    assert idx_f4 < idx_f5, "F4 should be before F5"
    assert idx_f1 < idx_f5, "F1 should be before F5"

    # service depends on feature 1,3,5
    assert idx_f1 < idx_svc, "F1 should be before Service"
    assert idx_f3 < idx_svc, "F3 should be before Service"
    assert idx_f5 < idx_svc, "F5 should be before Service"

    # 5. Check for Entrypoint content (main.lua)

    # Check main execution line exists
    assert "MyProjectNS.main_executed = true" in content

    # Check comment exists - adjusted for preceding transformed print
    assert 'env.info("main.lua print check") -- This SHOULD be sanitized' in content

    # Check the overall structure of the if block using a simpler regex relying on \s+ and DOTALL
    assert re.search(r"if\s+MyProjectNS\.service_loaded\s+then.*?end", content, re.DOTALL), (
        "Sanitized if block structure not found"
    )

    # Check original print statements are gone
    assert 'print("main.lua print check")' not in content
    assert 'print("Service was indeed loaded before main execution!")' not in content
    # Check transformed prints ARE present
    assert 'env.info("main.lua print check")' in content
    assert 'env.info("Service was indeed loaded before main execution!")' in content
    # Check require is gone
    assert 'require "service"' not in content

    # 6. Check Core Modules Order string in build info
    core_order_line_match = re.search(r"-- Core Modules Order: (.*)", content)
    assert core_order_line_match is not None, "Core Modules Order comment line not found"
    sorted_core_modules_str = core_order_line_match.group(1)

    # All modules other than header, namespace, entrypoint are core
    # (comp1, comp2, comp3, controller, manager, f1, f2, f3, f4, f5, service) = 11 modules
    all_core_module_names = list(core_modules_expected_content.keys())
    for name in all_core_module_names:
        assert name in sorted_core_modules_str, (
            f"{name} not found in Core Modules Order comment: {sorted_core_modules_str}"
        )
    assert len(sorted_core_modules_str.split(", ")) == len(all_core_module_names), (
        f"Incorrect number of modules in Core Modules Order. Expected {len(all_core_module_names)}, Got {len(sorted_core_modules_str.split(', '))}. String: {sorted_core_modules_str}"
    )
