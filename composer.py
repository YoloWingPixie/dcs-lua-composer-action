import os
import re
import argparse
from collections import defaultdict
from pathlib import Path
import datetime
import luaparser.ast as ast
import luaparser.astnodes as astnodes

# Disallowed patterns for regex removal/replacement (package lines)
# print and log are handled by specific regex transformations now if not removed by strict checks.
# require is handled by its own pattern for removal.
DISALLOWED_LINE_PATTERNS = {
    # package line removal is handled by this pattern
    re.compile(r"^[ \t]*[^\r\n]*\bpackage\b[^\r\n]*\r?\n?", re.MULTILINE): "", 
}

# Pattern to find 'require' statements for REMOVAL during sanitization
REQUIRE_REMOVAL_PATTERN = re.compile(r""" # Use verbose multi-line definition for clarity
    require\s*\(?\s* # 'require' followed by optional '('
    ['"]([^'"]+)['"] # module name in single or double quotes (captured for parsing)
    \s*\)?            # optional ')'
    (?:\s*;)?         # Optional trailing semicolon for removal
""", re.VERBOSE)

# Patterns for print/log transformation
PRINT_TRANSFORM_PATTERN = re.compile(r"\bprint\s*(\([^\)]*\))" ) # captures arguments in group 1
LOG_INFO_TRANSFORM_PATTERN = re.compile(r"\blog\.info\s*(\([^\)]*\))")
LOG_WARNING_TRANSFORM_PATTERN = re.compile(r"\blog\.warning\s*(\([^\)]*\))")
LOG_ERROR_TRANSFORM_PATTERN = re.compile(r"\blog\.error\s*(\([^\)]*\))")
LOG_OTHER_REMOVAL_PATTERN = re.compile(r"\blog\.[a-zA-Z_][a-zA-Z0-9_]*\s*\([^\)]*\)(?:\s*;)?")

# Pattern to find the loadlib call for warning messages
LOADLIB_CALL_PATTERN = re.compile(r"\bloadlib\s*\(.*?\)(?:\s*;)?") 
# Pattern to remove the entire line containing loadlib
LOADLIB_LINE_REMOVAL_PATTERN = re.compile(r"^[ \t]*[^\r\n]*\bloadlib\b[^\r\n]*\r?\n?", re.MULTILINE)

def find_lua_files(src_dir):
    """Finds all .lua files in the source directory."""
    lua_files = []
    for root, _, files in os.walk(src_dir):
        for file in files:
            if file.endswith(".lua"):
                lua_files.append(Path(root) / file)
    return lua_files

def get_module_name_from_path(file_path, src_dir_path):
    """Converts a file path to a Lua module name (assuming .lua extension)."""
    relative_path = file_path.relative_to(src_dir_path)
    return str(relative_path.with_suffix('')).replace(os.sep, '.')

def get_path_from_module_name(module_name, src_dir_path):
    """Converts a Lua module name to a file path."""
    return src_dir_path / Path(module_name.replace('.', os.sep) + ".lua")

def parse_dependencies(file_path, src_dir_path):
    """Parses a Lua file to find its dependencies (required modules) using luaparser."""
    dependencies = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            # We are looking for Call nodes, where the function being called is a Name node with id 'require'
            if isinstance(node, astnodes.Call) and \
               isinstance(node.func, astnodes.Name) and \
               node.func.id == 'require':
                # Check if arguments exist and the first argument is a String node
                if node.args and isinstance(node.args[0], astnodes.String):
                    dependencies.add(node.args[0].s)
                # DCS might use require(Modulename) without quotes if Modulename is a global var
                # but this script assumes standard require "module.name" or require("module.name")
                # For simplicity, we'll stick to string arguments for require.

    except Exception as e:
        # Catch luaparser specific errors if any, or file errors
        print(f"Error reading or parsing dependencies from {file_path} with luaparser: {e}")
    return dependencies

def topological_sort(dependencies_graph, all_modules_to_sort, module_to_path_map):
    """Performs a topological sort on the dependency graph with directory-affinity tie-breaking."""
    in_degree = {module: 0 for module in all_modules_to_sort}
    adj = defaultdict(list)
    # Using a list for the queue to allow for selective picking
    processing_queue = [] 
    sorted_order = []
    current_directory_context = None

    # Build adjacency list and in_degree count
    for module, deps in dependencies_graph.items():
        if module not in all_modules_to_sort:
            continue
        for dep in deps:
            if dep in all_modules_to_sort:
                adj[dep].append(module)
                in_degree[module] += 1

    # Initialize queue with nodes having in_degree 0
    for module in all_modules_to_sort:
        if in_degree[module] == 0:
            processing_queue.append(module)
    
    processing_queue.sort() # Initial sort for deterministic behavior if no context yet

    # Process queue
    while processing_queue:
        module_to_process = None
        # Try to find a module in the current directory context
        if current_directory_context:
            context_candidates = sorted([
                m for m in processing_queue 
                if Path(module_to_path_map[m]).parent == current_directory_context
            ])
            if context_candidates:
                module_to_process = context_candidates[0]

        # If no module found in current context, or no context yet, pick from the whole queue (alphabetically)
        if not module_to_process:
            # Ensure queue is sorted for deterministic fallback pick
            processing_queue.sort() 
            module_to_process = processing_queue[0]
        
        processing_queue.remove(module_to_process)
        sorted_order.append(module_to_process)
        current_directory_context = Path(module_to_path_map[module_to_process]).parent

        # Sort neighbors to process them in a deterministic order for adding to queue
        # This primarily affects which modules *become available* next, influencing future tie-breaks.
        sorted_neighbors = sorted(adj[module_to_process])

        for neighbor in sorted_neighbors:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                processing_queue.append(neighbor)
                # Keep the queue sorted for consistent picking when context doesn't apply
                # or when picking the first from a context set.
                # This could be optimized, but ensures determinism.
                processing_queue.sort()

    if len(sorted_order) != len(all_modules_to_sort):
        missing_from_sorted = all_modules_to_sort - set(sorted_order)
        problematic_modules = {mod for mod, degree in in_degree.items() if degree > 0}
        raise Exception(
            f"Circular dependency detected or missing modules among core modules. "
            f"Processed: {len(sorted_order)}/{len(all_modules_to_sort)}. "
            f"Problematic modules (involved in cycle or with unresolved deps): {problematic_modules}. "
            f"Modules not included in sorted output: {missing_from_sorted}"
        )
    return sorted_order

def sanitize_content(content, file_path, is_lua_module=True, dcs_strict_sanitize=True):
    """Removes or replaces disallowed Lua statements. Uses luaparser for goto and optional strict DCS checks."""
    if not is_lua_module:
        return content

    original_content_for_error_reporting = content # Keep a copy for error context

    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            # 1. Goto Check (always active for Lua modules)
            if isinstance(node, astnodes.Goto):
                line_num = node.first_token.line if node.first_token else 'unknown'
                offending_line_text = ""
                if node.start_char is not None and node.stop_char is not None:
                    line_start = original_content_for_error_reporting.rfind('\n', 0, node.start_char) + 1
                    line_end = original_content_for_error_reporting.find('\n', node.stop_char)
                    if line_end == -1:
                        line_end = len(original_content_for_error_reporting)
                    offending_line_text = original_content_for_error_reporting[line_start:line_end].strip()
                raise Exception(f"Disallowed 'goto' statement found in {file_path} on line {line_num}: {offending_line_text}")

            # 2. Strict DCS Sanitization Checks (if enabled)
            if dcs_strict_sanitize:
                # Check for os, io, lfs, usage (loadlib is now handled differently)
                offending_id = None
                node_for_error = node # For line number context
                
                # Removed direct Name check for os,io,lfs as it was too broad.
                # Focus on Call and Index for actual library usage.

                if isinstance(node, astnodes.Call):
                    # if isinstance(node.func, astnodes.Name) and node.func.id == "loadlib":
                    #     pass # loadlib is now removed with a warning, not a strict error
                    if isinstance(node.func, astnodes.Name) and node.func.id in ["os", "io", "lfs"]:
                         offending_id = node.func.id + "() call pattern (potential direct library call)"

                if isinstance(node, astnodes.Index) and isinstance(node.value, astnodes.Name):
                    if node.value.id in ["os", "io", "lfs"]:
                        idx_text = node.idx.s if isinstance(node.idx, astnodes.String) else (node.idx.id if isinstance(node.idx, astnodes.Name) else "complex_index")
                        offending_id = f"{node.value.id}.{idx_text}"

                if offending_id:
                    line_num = node_for_error.first_token.line if node_for_error.first_token else 'unknown'
                    err_line_text = ""
                    if node_for_error.start_char is not None and node_for_error.stop_char is not None:
                        line_start = original_content_for_error_reporting.rfind('\n', 0, node_for_error.start_char) + 1
                        line_end = original_content_for_error_reporting.find('\n', node_for_error.stop_char)
                        if line_end == -1:
                            line_end = len(original_content_for_error_reporting)
                        err_line_text = original_content_for_error_reporting[line_start:line_end].strip()
                    raise Exception(f"Disallowed DCS API usage ({offending_id}) found in {file_path} on line {line_num}: {err_line_text}")

        # Phase 3: Regex-based transformations and removals
        processed_content = content

        # Handle loadlib: Warn and remove (entire line)
        for match in LOADLIB_CALL_PATTERN.finditer(processed_content): # Use specific pattern for finding/warning
            print(f"WARNING: [{file_path}] Disallowed 'loadlib' call found and was removed: {match.group(0)}")
        processed_content = LOADLIB_LINE_REMOVAL_PATTERN.sub("", processed_content) # Use line removal pattern for sub

        # Remove require statements
        processed_content = REQUIRE_REMOVAL_PATTERN.sub("", processed_content)

        # Remove lines containing the `package` keyword
        for pattern, replacement in DISALLOWED_LINE_PATTERNS.items():
            processed_content = pattern.sub(replacement, processed_content)
        
        # Transform log.* statements
        processed_content = LOG_INFO_TRANSFORM_PATTERN.sub(r"env.info\1", processed_content)
        processed_content = LOG_WARNING_TRANSFORM_PATTERN.sub(r"env.warning\1", processed_content)
        processed_content = LOG_ERROR_TRANSFORM_PATTERN.sub(r"env.error\1", processed_content)
        processed_content = LOG_OTHER_REMOVAL_PATTERN.sub("", processed_content) # Remove other log.xxx calls

        # Transform print statements
        processed_content = PRINT_TRANSFORM_PATTERN.sub(r"env.info\1", processed_content)
        
        return processed_content

    except Exception as e:
        if "Disallowed" in str(e): # Includes goto and DCS API errors
            raise 
        print(f"Error during sanitization processing for {file_path}: {e}. Returning original content for this file.")
        return content

def build_project(src_dir, output_file, header_file_rel, namespace_file_rel, entrypoint_file_rel, footer_file_rel, dcs_strict_sanitize=True):
    src_dir_path = Path(src_dir).resolve()
    output_file_path = Path(output_file).resolve()
    output_file_path.parent.mkdir(parents=True, exist_ok=True)

    # --- Resolve paths for all specified files ---
    header_path = (src_dir_path / header_file_rel).resolve() if header_file_rel else None
    namespace_path = (src_dir_path / namespace_file_rel).resolve() # Required
    entrypoint_path = (src_dir_path / entrypoint_file_rel).resolve() # Required
    footer_path = (src_dir_path / footer_file_rel).resolve() if footer_file_rel else None

    # --- Validate existence of required and optional files if specified ---
    if not namespace_path.is_file():
        raise FileNotFoundError(f"REQUIRED Namespace file '{namespace_file_rel}' not found at {namespace_path}")
    if not entrypoint_path.is_file():
        raise FileNotFoundError(f"REQUIRED Entrypoint file '{entrypoint_file_rel}' not found at {entrypoint_path}")
    if header_file_rel and not header_path.is_file():
        raise FileNotFoundError(f"Header file '{header_file_rel}' specified but not found at {header_path}")
    if footer_file_rel and not footer_path.is_file():
        raise FileNotFoundError(f"Footer file '{footer_file_rel}' specified but not found at {footer_path}")

    # --- Discover all .lua files and map them ---
    all_lua_file_paths = find_lua_files(src_dir_path)
    module_to_path = {
        get_module_name_from_path(p, src_dir_path): p for p in all_lua_file_paths
    }
    path_to_module = {v: k for k, v in module_to_path.items()}

    # --- Identify core Lua modules for topological sorting ---
    # These are all .lua files excluding the specific fixed-order files.
    # Note: Header/Footer might not be .lua files, so they won't be in all_lua_file_paths if so.
    # The check `p not in fixed_order_paths` correctly handles this.
    fixed_order_paths = {p for p in [header_path, namespace_path, entrypoint_path, footer_path] if p}
    core_module_paths = [p for p in all_lua_file_paths if p not in fixed_order_paths]
    
    core_module_names_to_sort = {path_to_module[p] for p in core_module_paths if p in path_to_module}

    dependencies_graph = {}
    for core_module_path_item in core_module_paths:
        # Ensure it's a module we can get a name for (should always be true here)
        core_module_name_item = path_to_module.get(core_module_path_item)
        if not core_module_name_item: 
            continue 

        deps = parse_dependencies(core_module_path_item, src_dir_path)
        dependencies_graph[core_module_name_item] = {
            dep for dep in deps
            if dep in core_module_names_to_sort # Only sort based on other *core* modules
        }
    
    print("Core modules identified for topological sort:", sorted(list(core_module_names_to_sort)))
    if dependencies_graph:
        print("Dependencies for core modules:")
        for mod, deps in dependencies_graph.items():
            print(f"  {mod}: {deps if deps else '{}'}")
    print("-" * 30)

    sorted_core_module_names = []
    if core_module_names_to_sort:
        try:
            # Pass the module_to_path map to the sort function
            sorted_core_module_names = topological_sort(dependencies_graph, core_module_names_to_sort, module_to_path)
        except Exception as e:
            print(f"Error during topological sort of core modules: {e}")
            # Optionally, print more graph details here for debugging if needed
            return

    # --- Construct the final output ---
    final_lua_code = []

    # 1. Optional Header File Content (verbatim - no strict sanitization applied here by default rule)
    if header_path and header_path.is_file():
        with open(header_path, 'r', encoding='utf-8') as f:
            # Headers are typically non-Lua or special; dcs_strict_sanitize probably shouldn't apply here by default
            final_lua_code.append(sanitize_content(f.read(), header_path, is_lua_module=False, dcs_strict_sanitize=False))
        final_lua_code.append("\n")

    # 2. Autogenerated Build Information
    current_time_utc = datetime.datetime.now(tz=datetime.timezone.utc)
    final_lua_code.append(f"-- Combined and Sanitized Lua script generated on {current_time_utc.isoformat()}\n")
    final_lua_code.append("-- THIS IS A RELEASE FILE. DO NOT EDIT THIS FILE DIRECTLY. EDIT SOURCE FILES AND REBUILD.\n")
    if header_file_rel:
        final_lua_code.append(f"-- Header File: {header_file_rel}\n")
    final_lua_code.append(f"-- Namespace File: {namespace_file_rel}\n")
    final_lua_code.append(f"-- Entrypoint File: {entrypoint_file_rel}\n")
    if footer_file_rel:
        final_lua_code.append(f"-- Footer File: {footer_file_rel}\n")
    final_lua_code.append(f"-- Core Modules Order: {', '.join(sorted_core_module_names) if sorted_core_module_names else 'None'}\n")
    final_lua_code.append("\n")

    # 3. Required Namespace File Content (sanitized)
    final_lua_code.append(f"-- Namespace Content from: {namespace_path.relative_to(src_dir_path)}\n")
    with open(namespace_path, 'r', encoding='utf-8') as f:
        final_lua_code.append(sanitize_content(f.read(), namespace_path, is_lua_module=True, dcs_strict_sanitize=dcs_strict_sanitize))
    final_lua_code.append("\n")

    # 4. Core Modules Content (topologically sorted and sanitized)
    if sorted_core_module_names:
        print("\nFinal calculated loading order for core modules:")
        for i, module_name in enumerate(sorted_core_module_names):
            print(f"  {i+1}. {module_name} (Path: {module_to_path[module_name].relative_to(src_dir_path)})")

        for module_name in sorted_core_module_names:
            file_path = module_to_path[module_name]
            final_lua_code.append(f"\n-- Core Module Content from: {file_path.relative_to(src_dir_path)}\n")
            final_lua_code.append(f"-- Module Name: {module_name}\n")
            with open(file_path, 'r', encoding='utf-8') as f:
                final_lua_code.append(sanitize_content(f.read(), file_path, is_lua_module=True, dcs_strict_sanitize=dcs_strict_sanitize))
            final_lua_code.append("\n")
    else:
        print("\nNo core modules to process.")


    # 5. Required Entrypoint File Content (sanitized)
    final_lua_code.append(f"\n-- Entrypoint Content from: {entrypoint_path.relative_to(src_dir_path)}\n")
    with open(entrypoint_path, 'r', encoding='utf-8') as f:
        final_lua_code.append(sanitize_content(f.read(), entrypoint_path, is_lua_module=True, dcs_strict_sanitize=dcs_strict_sanitize))
    final_lua_code.append("\n")

    # 6. Optional Footer File Content (verbatim - no strict sanitization applied here by default rule)
    if footer_path and footer_path.is_file():
        final_lua_code.append(f"\n-- Footer Content from: {footer_path.relative_to(src_dir_path)}\n")
        with open(footer_path, 'r', encoding='utf-8') as f:
            final_lua_code.append(sanitize_content(f.read(), footer_path, is_lua_module=False, dcs_strict_sanitize=False))
        final_lua_code.append("\n")
    
    # --- Write the output file ---
    try:
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write("".join(final_lua_code))
        print(f"\nSuccessfully built: {output_file_path}")
        print(f"Total lines in output: {len(''.join(final_lua_code).splitlines())}")
    except Exception as e:
        print(f"Error writing output file {output_file_path}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Builds a single Lua file from a modular project for DCS, with specific file ordering.",
        formatter_class=argparse.RawTextHelpFormatter # For better help text display
    )
    parser.add_argument("src_dir", help="Source directory containing all Lua and text files.")
    parser.add_argument("output_file", help="Path for the final combined Lua file.")
    
    parser.add_argument("--header", dest="header_file_rel", default=None,
                        help="Optional: Relative path from src_dir to the header file.\nIncluded verbatim at the very top.")
    parser.add_argument("--namespace", dest="namespace_file_rel", required=True,
                        help="Required: Relative path from src_dir to the namespace definition file.\nLoaded after header (if any) and build info. Sanitized.")
    parser.add_argument("--entrypoint", dest="entrypoint_file_rel", required=True,
                        help="Required: Relative path from src_dir to the main entry point file.\nLoaded after core modules. Sanitized.")
    parser.add_argument("--footer", dest="footer_file_rel", default=None,
                        help="Optional: Relative path from src_dir to the footer file.\nIncluded verbatim at the very bottom.")
    parser.add_argument("--dcs-strict-sanitize", dest="dcs_strict_sanitize", type=lambda x: (str(x).lower() == 'true'), default=True,
                        help="If true (default), enforce stricter DCS sanitization (fail on os, io, lfs, loadlib). Else, skip these checks.")

    args = parser.parse_args()

    build_project(
        args.src_dir,
        args.output_file,
        args.header_file_rel,
        args.namespace_file_rel,
        args.entrypoint_file_rel,
        args.footer_file_rel,
        args.dcs_strict_sanitize
    ) 