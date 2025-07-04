import argparse
import datetime
import io
import json
import os
import re
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import luaparser.ast as ast
import luaparser.astnodes as astnodes

from dependency_manager import DependencyManager, load_dependencies_config

# Suppress specific SyntaxWarnings from luaparser.printers
# Match common invalid escape sequence messages if they are consistent, or by module and category
warnings.filterwarnings(
    "ignore", message=r".*invalid escape sequence '\\c'.*", category=SyntaxWarning, module="luaparser.printers"
)
warnings.filterwarnings(
    "ignore", message=r".*invalid escape sequence '\\8'.*", category=SyntaxWarning, module="luaparser.printers"
)
warnings.filterwarnings(
    "ignore", message=r".*invalid escape sequence '\\9'.*", category=SyntaxWarning, module="luaparser.printers"
)
# Fallback if messages are less predictable but we trust the module source of warning:
# warnings.filterwarnings("ignore", category=SyntaxWarning, module="luaparser\.printers")

# Disallowed patterns for regex removal/replacement (package lines)
# print and log are handled by specific regex transformations now if not removed by strict checks.
# require is handled by its own pattern for removal.
DISALLOWED_LINE_PATTERNS = {
    # package line removal is handled by this pattern
    re.compile(r"^[ \t]*[^\r\n]*\bpackage\b[^\r\n]*\r?\n?", re.MULTILINE): "",
}

# Pattern to find 'require' statements for REMOVAL during sanitization
REQUIRE_REMOVAL_PATTERN = re.compile(
    r""" # Use verbose multi-line definition for clarity
    require\s*\(?\s* # 'require' followed by optional '('
    ['"]([^'"]+)['"] # module name in single or double quotes (captured for parsing)
    \s*\)?            # optional ')'
    (?:\s*;)?         # Optional trailing semicolon for removal
""",
    re.VERBOSE,
)


def _find_balanced_parentheses(text, start_pos):
    """Find the matching closing parenthesis for an opening parenthesis at start_pos."""
    if start_pos >= len(text) or text[start_pos] != "(":
        return -1

    paren_count = 1
    pos = start_pos + 1
    in_string = False
    escape_next = False
    string_char = None

    while pos < len(text) and paren_count > 0:
        char = text[pos]

        if escape_next:
            escape_next = False
        elif char == "\\":
            escape_next = True
        elif not in_string:
            if char in ['"', "'"]:
                in_string = True
                string_char = char
            elif char == "(":
                paren_count += 1
            elif char == ")":
                paren_count -= 1
        elif in_string and char == string_char:
            in_string = False
            string_char = None

        pos += 1

    return pos - 1 if paren_count == 0 else -1


def _safe_regex_replace(pattern, replacement, text, is_removal=False):
    """Safely replace function calls while handling nested parentheses properly."""
    result = []
    last_end = 0

    for match in pattern.finditer(text):
        # Add text before this match
        result.append(text[last_end : match.start()])

        # Find the opening parenthesis in the original text starting from match position
        paren_start_in_text = text.find("(", match.start())
        if paren_start_in_text == -1 or paren_start_in_text >= match.end() + 10:  # Safety margin
            # No parentheses found nearby, handle as simple replacement
            if is_removal:
                pass  # Skip adding anything for removal
            else:
                result.append(match.expand(replacement))
            last_end = match.end()
        else:
            # Find the balanced closing parenthesis
            paren_end = _find_balanced_parentheses(text, paren_start_in_text)

            if paren_end == -1:
                # Unbalanced parentheses, keep original
                result.append(text[match.start() : match.end()])
                last_end = match.end()
            else:
                # Extract the full function call with balanced parentheses
                if is_removal:
                    # For removal, skip adding anything and also skip any trailing semicolon
                    next_pos = paren_end + 1
                    if next_pos < len(text) and text[next_pos : next_pos + 1] == ";":
                        next_pos += 1
                    last_end = next_pos
                else:
                    # For transformation, apply the replacement
                    args = text[paren_start_in_text : paren_end + 1]
                    result.append(replacement + args)
                    last_end = paren_end + 1

    # Add remaining text
    result.append(text[last_end:])
    return "".join(result)


# Improved patterns that will work with the safe replacement function
PRINT_TRANSFORM_PATTERN = re.compile(r"\bprint\s*(?=\()")
LOG_INFO_TRANSFORM_PATTERN = re.compile(r"\blog\.info\s*(?=\()")
LOG_WARNING_TRANSFORM_PATTERN = re.compile(r"\blog\.warning\s*(?=\()")
LOG_ERROR_TRANSFORM_PATTERN = re.compile(r"\blog\.error\s*(?=\()")
LOG_OTHER_REMOVAL_PATTERN = re.compile(r"\blog\.[a-zA-Z_][a-zA-Z0-9_]*\s*(?=\()")

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
    return str(relative_path.with_suffix("")).replace(os.sep, ".")


def get_path_from_module_name(module_name, src_dir_path):
    """Converts a Lua module name to a file path."""
    return src_dir_path / Path(module_name.replace(".", os.sep) + ".lua")


def parse_dependencies(file_path, src_dir_path):
    """Parses a Lua file to find its dependencies (required modules) using luaparser."""
    dependencies = set()
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        # print(f"DEBUG: Calling ast.parse in PARSE_DEPENDENCIES for {file_path}") # Optional debug

        # Suppress stdout during ast.parse
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            tree = ast.parse(content)
        finally:
            sys.stdout = old_stdout  # Restore stdout
            # captured_str = captured_output.getvalue() # For debugging the suppressed output
            # if captured_str: print(f"Suppressed from parse_dependencies({file_path}): {captured_str}")

        for node in ast.walk(tree):
            if isinstance(node, astnodes.Call) and isinstance(node.func, astnodes.Name) and node.func.id == "require":
                if node.args and isinstance(node.args[0], astnodes.String):
                    dependencies.add(node.args[0].s)
    except Exception as e:
        print(f"Error reading or parsing dependencies from {file_path} with luaparser: {e}")
    return dependencies


def topological_sort(dependencies_graph, all_modules_to_sort, module_to_path_map):
    """Performs a topological sort on the dependency graph with directory-affinity tie-breaking."""
    in_degree = dict.fromkeys(all_modules_to_sort, 0)
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

    processing_queue.sort()  # Initial sort for deterministic behavior if no context yet

    # Process queue
    while processing_queue:
        module_to_process = None
        # Try to find a module in the current directory context
        if current_directory_context:
            context_candidates = sorted(
                [m for m in processing_queue if Path(module_to_path_map[m]).parent == current_directory_context]
            )
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

    original_content_for_error_reporting = content  # Keep a copy for error context

    try:
        # print(f"DEBUG: Calling ast.parse in SANITIZE_CONTENT for {file_path}") # Optional debug

        # Suppress stdout during ast.parse for goto check
        old_stdout_sanitize = sys.stdout
        sys.stdout = io.StringIO()
        try:
            tree = ast.parse(content)
        finally:
            sys.stdout = old_stdout_sanitize  # Restore stdout
            # captured_str_sanitize = captured_output_sanitize.getvalue()
            # if captured_str_sanitize: print(f"Suppressed from sanitize_content({file_path}): {captured_str_sanitize}")

        for node in ast.walk(tree):
            # 1. Goto Check (always active for Lua modules)
            if isinstance(node, astnodes.Goto):
                line_num = node.first_token.line if node.first_token else "unknown"
                offending_line_text = ""
                if node.start_char is not None and node.stop_char is not None:
                    line_start = original_content_for_error_reporting.rfind("\n", 0, node.start_char) + 1
                    line_end = original_content_for_error_reporting.find("\n", node.stop_char)
                    if line_end == -1:
                        line_end = len(original_content_for_error_reporting)
                    offending_line_text = original_content_for_error_reporting[line_start:line_end].strip()
                raise Exception(
                    f"Disallowed 'goto' statement found in {file_path} on line {line_num}: {offending_line_text}"
                )

            # 2. Strict DCS Sanitization Checks (if enabled)
            if dcs_strict_sanitize:
                # Check for os, io, lfs, usage (loadlib is now handled differently)
                offending_id = None
                node_for_error = node  # For line number context

                # Removed direct Name check for os,io,lfs as it was too broad.
                # Focus on Call and Index for actual library usage.

                if isinstance(node, astnodes.Call):
                    # if isinstance(node.func, astnodes.Name) and node.func.id == "loadlib":
                    #     pass # loadlib is now removed with a warning, not a strict error
                    if isinstance(node.func, astnodes.Name) and node.func.id in [
                        "os",
                        "io",
                        "lfs",
                    ]:
                        offending_id = node.func.id + "() call pattern (potential direct library call)"

                if isinstance(node, astnodes.Index) and isinstance(node.value, astnodes.Name):
                    if node.value.id in ["os", "io", "lfs"]:
                        idx_text = (
                            node.idx.s
                            if isinstance(node.idx, astnodes.String)
                            else (node.idx.id if isinstance(node.idx, astnodes.Name) else "complex_index")
                        )
                        offending_id = f"{node.value.id}.{idx_text}"

                if offending_id:
                    line_num = node_for_error.first_token.line if node_for_error.first_token else "unknown"
                    err_line_text = ""
                    if node_for_error.start_char is not None and node_for_error.stop_char is not None:
                        line_start = original_content_for_error_reporting.rfind("\n", 0, node_for_error.start_char) + 1
                        line_end = original_content_for_error_reporting.find("\n", node_for_error.stop_char)
                        if line_end == -1:
                            line_end = len(original_content_for_error_reporting)
                        err_line_text = original_content_for_error_reporting[line_start:line_end].strip()
                    raise Exception(
                        f"Disallowed DCS API usage ({offending_id}) found in {file_path} on line {line_num}: {err_line_text}"
                    )

        # Phase 3: Regex-based transformations and removals
        processed_content = content

        # Handle loadlib: Warn and remove (entire line)
        for match in LOADLIB_CALL_PATTERN.finditer(processed_content):  # Use specific pattern for finding/warning
            print(f"WARNING: [{file_path}] Disallowed 'loadlib' call found and was removed: {match.group(0)}")
        processed_content = LOADLIB_LINE_REMOVAL_PATTERN.sub("", processed_content)  # Use line removal pattern for sub

        # Remove require statements
        processed_content = REQUIRE_REMOVAL_PATTERN.sub("", processed_content)

        # Remove lines containing the `package` keyword
        for pattern, replacement in DISALLOWED_LINE_PATTERNS.items():
            processed_content = pattern.sub(replacement, processed_content)

        # Transform log.* statements using safe replacement
        processed_content = _safe_regex_replace(LOG_INFO_TRANSFORM_PATTERN, "env.info", processed_content)
        processed_content = _safe_regex_replace(LOG_WARNING_TRANSFORM_PATTERN, "env.warning", processed_content)
        processed_content = _safe_regex_replace(LOG_ERROR_TRANSFORM_PATTERN, "env.error", processed_content)
        processed_content = _safe_regex_replace(LOG_OTHER_REMOVAL_PATTERN, "", processed_content, is_removal=True)

        # Transform print statements using safe replacement
        processed_content = _safe_regex_replace(PRINT_TRANSFORM_PATTERN, "env.info", processed_content)

        return processed_content

    except Exception as e:
        if "Disallowed" in str(e):  # Includes goto and DCS API errors
            raise
        print(f"Error during sanitization processing for {file_path}: {e}. Returning original content for this file.")
        return content


def build_project(
    src_dir,
    output_file,
    header_file_rel,
    namespace_file_rel,
    entrypoint_file_rel,
    footer_file_rel,
    dcs_strict_sanitize=True,
    dependencies_config=None,
    scope="global",
):
    src_dir_path = Path(src_dir).resolve()
    output_file_path = Path(output_file).resolve()
    output_file_path.parent.mkdir(parents=True, exist_ok=True)

    # --- Helper function to validate and resolve paths ---
    def validate_and_resolve_path(file_rel, file_type):
        """Validate that the resolved path is within the source directory."""
        if not file_rel:
            return None

        # Resolve the path
        resolved_path = (src_dir_path / file_rel).resolve()

        # Check if the resolved path is within the source directory
        try:
            resolved_path.relative_to(src_dir_path)
        except ValueError:
            raise ValueError(
                f"{file_type} file '{file_rel}' resolves to a path outside the source directory: {resolved_path}"
            )

        return resolved_path

    # --- Resolve paths for all specified files with validation ---
    header_path = validate_and_resolve_path(header_file_rel, "Header")
    namespace_path = validate_and_resolve_path(namespace_file_rel, "Namespace")
    entrypoint_path = validate_and_resolve_path(entrypoint_file_rel, "Entrypoint")
    footer_path = validate_and_resolve_path(footer_file_rel, "Footer")

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
    module_to_path = {get_module_name_from_path(p, src_dir_path): p for p in all_lua_file_paths}
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
            dep
            for dep in deps
            if dep in core_module_names_to_sort  # Only sort based on other *core* modules
        }

    print(
        "Core modules identified for topological sort:",
        sorted(core_module_names_to_sort),
    )
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
        with open(header_path, encoding="utf-8") as f:
            # Headers are typically non-Lua or special; dcs_strict_sanitize probably shouldn't apply here by default
            final_lua_code.append(
                sanitize_content(
                    f.read(),
                    header_path,
                    is_lua_module=False,
                    dcs_strict_sanitize=False,
                )
            )
        final_lua_code.append("\n")

    # 2. Process and inject external dependencies
    if dependencies_config:
        print("\nProcessing external dependencies...")
        dep_manager = DependencyManager()
        dependencies = load_dependencies_config({"dependencies": dependencies_config})

        for dep in dependencies:
            print(f"  - Fetching dependency: {dep.name}")
            try:
                # Use the current working directory as base for local dependencies
                # This allows dependencies to be anywhere in the repository
                lua_content, license_content = dep_manager.fetch_dependency(dep, Path.cwd())
                # Sanitize the dependency content
                sanitized_lua = sanitize_content(
                    lua_content,
                    Path(f"dependency_{dep.name}.lua"),
                    is_lua_module=True,
                    dcs_strict_sanitize=dcs_strict_sanitize,
                )
                # Format and add the dependency block
                dep_block = dep_manager.format_dependency_block(dep, sanitized_lua, license_content)
                final_lua_code.append(dep_block)
                final_lua_code.append("\n")
            except Exception as e:
                print(f"  ERROR: Failed to process dependency '{dep.name}': {e}")
                raise

    # 3. Autogenerated Build Information
    current_time_utc = datetime.datetime.now(tz=datetime.timezone.utc)
    final_lua_code.append(f"-- Combined and Sanitized Lua script generated on {current_time_utc.isoformat()}\n")
    final_lua_code.append("-- THIS IS A RELEASE FILE. DO NOT EDIT THIS FILE DIRECTLY. EDIT SOURCE FILES AND REBUILD.\n")
    if header_file_rel:
        final_lua_code.append(f"-- Header File: {header_file_rel}\n")
    if dependencies_config:
        final_lua_code.append(f"-- External Dependencies: {len(dependencies_config)} loaded\n")
    final_lua_code.append(f"-- Namespace File: {namespace_file_rel}\n")
    final_lua_code.append(f"-- Entrypoint File: {entrypoint_file_rel}\n")
    if footer_file_rel:
        final_lua_code.append(f"-- Footer File: {footer_file_rel}\n")
    final_lua_code.append(
        f"-- Core Modules Order: {', '.join(sorted_core_module_names) if sorted_core_module_names else 'None'}\n"
    )
    final_lua_code.append(f"-- Scope: {scope}\n")
    final_lua_code.append("\n")

    # Start local scope if requested (after build info, excluding header)
    if scope == "local":
        final_lua_code.append("-- Beginning of local scope\n")
        final_lua_code.append("do\n")
        final_lua_code.append("\n")

    # 4. Required Namespace File Content (sanitized)
    final_lua_code.append(f"-- Namespace Content from: {namespace_path.relative_to(src_dir_path)}\n")
    with open(namespace_path, encoding="utf-8") as f:
        final_lua_code.append(
            sanitize_content(
                f.read(),
                namespace_path,
                is_lua_module=True,
                dcs_strict_sanitize=dcs_strict_sanitize,
            )
        )
    final_lua_code.append("\n")

    # 5. Core Modules Content (topologically sorted and sanitized)
    if sorted_core_module_names:
        print("\nFinal calculated loading order for core modules:")
        for i, module_name in enumerate(sorted_core_module_names):
            print(f"  {i + 1}. {module_name} (Path: {module_to_path[module_name].relative_to(src_dir_path)})")

        for module_name in sorted_core_module_names:
            file_path = module_to_path[module_name]
            final_lua_code.append(f"\n-- Core Module Content from: {file_path.relative_to(src_dir_path)}\n")
            final_lua_code.append(f"-- Module Name: {module_name}\n")
            with open(file_path, encoding="utf-8") as f:
                final_lua_code.append(
                    sanitize_content(
                        f.read(),
                        file_path,
                        is_lua_module=True,
                        dcs_strict_sanitize=dcs_strict_sanitize,
                    )
                )
            final_lua_code.append("\n")
    else:
        print("\nNo core modules to process.")

    # 6. Required Entrypoint File Content (sanitized)
    final_lua_code.append(f"\n-- Entrypoint Content from: {entrypoint_path.relative_to(src_dir_path)}\n")
    with open(entrypoint_path, encoding="utf-8") as f:
        final_lua_code.append(
            sanitize_content(
                f.read(),
                entrypoint_path,
                is_lua_module=True,
                dcs_strict_sanitize=dcs_strict_sanitize,
            )
        )
    final_lua_code.append("\n")

    # End local scope if requested (after entrypoint, before footer)
    if scope == "local":
        final_lua_code.append("\n-- End of local scope\n")
        final_lua_code.append("end\n")

    # 7. Optional Footer File Content (verbatim - no strict sanitization applied here by default rule)
    if footer_path and footer_path.is_file():
        final_lua_code.append(f"\n-- Footer Content from: {footer_path.relative_to(src_dir_path)}\n")
        with open(footer_path, encoding="utf-8") as f:
            final_lua_code.append(
                sanitize_content(
                    f.read(),
                    footer_path,
                    is_lua_module=False,
                    dcs_strict_sanitize=False,
                )
            )
        final_lua_code.append("\n")

    # --- Write the output file ---
    try:
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write("".join(final_lua_code))
        print(f"\nSuccessfully built: {output_file_path}")
        print(f"Total lines in output: {len(''.join(final_lua_code).splitlines())}")
    except Exception as e:
        print(f"Error writing output file {output_file_path}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Builds a single Lua file from a modular project for DCS, with specific file ordering.",
        formatter_class=argparse.RawTextHelpFormatter,  # For better help text display
    )
    parser.add_argument("src_dir", help="Source directory containing all Lua and text files.")
    parser.add_argument("output_file", help="Path for the final combined Lua file.")

    parser.add_argument(
        "--header",
        dest="header_file_rel",
        default=None,
        help="Optional: Relative path from src_dir to the header file.\nIncluded verbatim at the very top.",
    )
    parser.add_argument(
        "--namespace",
        dest="namespace_file_rel",
        required=True,
        help="Required: Relative path from src_dir to the namespace definition file.\nLoaded after header (if any) and build info. Sanitized.",
    )
    parser.add_argument(
        "--entrypoint",
        dest="entrypoint_file_rel",
        required=True,
        help="Required: Relative path from src_dir to the main entry point file.\nLoaded after core modules. Sanitized.",
    )
    parser.add_argument(
        "--footer",
        dest="footer_file_rel",
        default=None,
        help="Optional: Relative path from src_dir to the footer file.\nIncluded verbatim at the very bottom.",
    )
    parser.add_argument(
        "--dcs-strict-sanitize",
        dest="dcs_strict_sanitize",
        type=lambda x: (str(x).lower() == "true"),
        default=True,
        help="If true (default), enforce stricter DCS sanitization (fail on os, io, lfs, loadlib). Else, skip these checks.",
    )
    parser.add_argument(
        "--dependencies",
        dest="dependencies",
        default=None,
        help="JSON-encoded list of external dependencies to inject.\nCan be provided via .composerrc file instead.",
    )
    parser.add_argument(
        "--scope",
        dest="scope",
        choices=["global", "local"],
        default="global",
        help="Scope for the generated script. 'global' (default) generates normal global scope, 'local' wraps content in do...end blocks for local scoping.",
    )

    args = parser.parse_args()

    # Parse dependencies if provided as command line argument
    dependencies_config = None
    if args.dependencies:
        try:
            dependencies_config = json.loads(args.dependencies)
        except json.JSONDecodeError as e:
            print(f"Error parsing dependencies JSON: {e}")
            sys.exit(1)

    build_project(
        args.src_dir,
        args.output_file,
        args.header_file_rel,
        args.namespace_file_rel,
        args.entrypoint_file_rel,
        args.footer_file_rel,
        args.dcs_strict_sanitize,
        dependencies_config,
        args.scope,
    )
