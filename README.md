# DCS Lua Composer Action

[![CI Status](https://github.com/yolowingpixie/dcs-lua-composer-action/actions/workflows/ci.yml/badge.svg)](https://github.com/yolowingpixie/dcs-lua-composer-action/actions/workflows/test-action.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

This GitHub Action takes a modular DCS World Lua project from a source directory and intelligently composes it into a single, sanitized Lua file suitable for direct use in a mission. It handles dependency resolution, specific file ordering (header, namespace, entrypoint, footer), and applies DCS-friendly sanitization.

## The Problem This Solves

DCS World mission scripting often involves loading a single Lua file. As projects grow, managing a single massive Lua file becomes unwieldy and error-prone. This action allows developers to:

*   **Write Modular Code:** Structure your Lua project into multiple files and subdirectories.
*   **Manage Dependencies:** Use standard `require "module.name"` syntax while developing. This is stripped out and modules are intelligently inlined in the final build!
*   **Automate Build Process:** Automatically combine modules in the correct loading order based on each module's dependency requirements.
*   **Ensure DCS Compatibility:** Transforms logging calls, removes disallowed statements (`package`, `require`), and optionally enforces stricter checks for DCS environment limitations (`os`, `io`, `lfs`, `loadlib`), erroring on `goto`.
*   **Maintain a Clear Structure:** Enforce a specific composition order for critical project files.

## Features

*   **Topological Sorting:** Core Lua modules are sorted based on their `require` dependencies.
*   **Directory-Affinity Packing:** The sort attempts to group files from the same subdirectory if dependencies allow.
*   **External Dependencies:** Inject external Lua libraries from GitHub releases, URLs, or local files with inline license support.
*   **Configurable File Roles:** Specify files for Header, Namespace, Entrypoint, and Footer.
*   **Lua Sanitization & Transformation:**
    *   Removes `require` statements (after dependency analysis).
    *   Transforms `print(...)` statements to `env.info(...)`.
    *   Transforms `log.info(...)` to `env.info(...)`.
    *   Transforms `log.warning(...)` to `env.warning(...)`.
    *   Transforms `log.error(...)` to `env.error(...)`.
    *   Removes other `log.anythingelse(...)` calls.
    *   Removes entire lines containing the `package` keyword.
    *   Removes `loadlib(...)` calls and issues a build warning.
    *   **Errors the build** if a `goto` statement is found.
    *   **Optional Strict DCS Sanitization:** (Default: `true`) If enabled, fails the build if usage of `os.*`, `io.*`, or `lfs.*` functions/tables is detected in Lua modules. `loadlib` is handled separately (removed with warning).
*   **Build Information:** Prepends a comment block to the output file detailing sources and build time.
*   **Python-based:** Uses `luaparser` for accurate Lua analysis and robust processing.
*   **`uv` Integration:** Leverages `uv` for Python environment and execution.

## Scoping Options

The composer supports two scoping modes for the generated script:

### Global Scope (Default)
```
scope: "global"
```
- All code runs in the global Lua scope
- Variables declared without `local` become global
- Traditional single-file script behavior
- Header and footer files remain in global scope

### Local Scope
```
scope: "local"
```
- Main content (dependencies, namespace, core modules, entrypoint) is wrapped in a `do...end` block
- Provides better encapsulation and prevents global namespace pollution
- Header and footer files remain in global scope for setup/cleanup
- Variables declared without `local` are scoped to the `do` block instead of globally

**Example output structure with local scope:**
```lua
-- Header content (global scope)
-- Build information

-- Beginning of local scope
do
    -- Dependencies
    -- Namespace
    -- Core modules
    -- Entrypoint
-- End of local scope
end

-- Footer content (global scope)
```

## Inputs

| Input                   | Description                                                                                                                               | Required | Default                     |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------- | --------------------------- |
| `source_directory`      | Source directory containing all Lua and text files. Relative to the repository root.                                                        | `true`   | `src`                       |
| `output_file`           | Path for the final combined Lua file. Relative to the repository root.                                                                    | `true`   | `dist/mission_script.lua`   |
| `header_file`           | Optional: Relative path *from source_directory* to the header file. Included verbatim at the top.                                         | `false`  | `''`                         |
| `namespace_file`        | Required: Relative path *from source_directory* to the namespace definition file. Sanitized.                                              | `true`   | *N/A*                       |
| `entrypoint_file`       | Required: Relative path *from source_directory* to the main entry point file. Loaded after core modules. Sanitized.                         | `true`   | *N/A*                       |
| `footer_file`           | Optional: Relative path *from source_directory* to the footer file. Included verbatim at the bottom.                                      | `false`  | `''`                         |
| `dcs_strict_sanitize`   | If true (default), fails build on os, io, lfs usage. `loadlib` is always removed with a warning. Print/log are always transformed.      | `false`  | `true`                      |
| `scope`                 | Scope for the generated script. `global` (default) generates normal global scope, `local` wraps content in do...end blocks for local scoping. | `false`  | `global`                    |

## Outputs

| Output            | Description                               |
| ----------------- | ----------------------------------------- |
| `built_file_path` | The path to the generated Lua file.         |

## How to Call Action in Your Own Pipeline

To use this action from the GitHub Marketplace:

```yaml
name: Build DCS Mission Script

on:
  push:
    branches: [ main ]
    paths:
      - 'src/**' # Or your Lua source directory
      - '.github/workflows/build-mission.yml' # This workflow file
  pull_request:
    paths:
      - 'src/**'

jobs:
  build_lua:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Compose DCS Lua Script
        id: composer_build
        uses: yolowingpixie/dcs-lua-composer-action@v1
        with:
          source_directory: 'src'                                 # Your Lua source root
          output_file: 'dist/MyMission.lua'                     # Desired output path
          # header_file: 'my_header.txt'                        # Optional, path relative to source_directory
          namespace_file: 'core/my_namespace.lua'             # Required, path relative to source_directory
          entrypoint_file: 'main.lua'                           # Required, path relative to source_directory
          # footer_file: 'my_footer.txt'                        # Optional, path relative to source_directory
          # dcs_strict_sanitize: 'false'                        # Optional, default is true
          # scope: 'local'                                      # Optional, default is 'global'

      - name: Verify Build Output
        run: |
          echo "Built Lua file path: ${{ steps.composer_build.outputs.built_file_path }}"
          ls -lh ${{ steps.composer_build.outputs.built_file_path }}
          # Add more checks if needed (e.g., line count, specific content)

      - name: Upload Mission Script Artifact
        uses: actions/upload-artifact@v4
        with:
          name: dcs-mission-script-${{ github.sha }}
          path: ${{ steps.composer_build.outputs.built_file_path }}
          if-no-files-found: error
```

**Using as a Local Action:**

If you are developing this action or using it within the same repository where the action code resides (e.g., in `.github/actions/your-action-name/`), you can call it using a local path:
```yaml
# ...
      - name: Compose DCS Lua Script (Local)
        id: composer_build
        # If action.yml is in the root of your repository:
        # uses: ./
        # If action.yml is in .github/actions/dcs-lua-composer/ within your repository:
        uses: ./.github/actions/dcs-lua-composer
        with:
          # ... your inputs ...
```

**Important:**
*   When using the marketplace version, always specify a version tag (e.g., `@v1`, `@v1.0.0`) for stability.

## Configuration File Support (.composerrc)

Starting from version 3.x, the action supports reading configuration from a `.composerrc` file in your repository root. This allows you to define default values for all action inputs without having to specify them in every workflow file.

### Using .composerrc

Create a `.composerrc` file in your repository root with your preferred configuration:

```json
{
  "source_directory": "src",
  "output_file": "dist/mission_script.lua",
  "header_file": "header.lua",
  "namespace_file": "namespace.lua",
  "entrypoint_file": "main.lua",
  "footer_file": "",
  "dcs_strict_sanitize": true,
  "scope": "global"
}
```

### Priority Rules

When both `.composerrc` and action inputs are provided:
- **Action inputs take priority** over `.composerrc` values
- If an input is not specified in the action, the value from `.composerrc` is used
- If neither is specified, the action's default values are used

### Example Usage with .composerrc

With a `.composerrc` file in place, your workflow can be simplified:

```yaml
- name: Compose DCS Lua Script
  uses: yolowingpixie/dcs-lua-composer-action@v3
  with:
    # Only override specific values as needed
    output_file: 'dist/MySpecialMission.lua'
    scope: 'local'  # Override scope for better encapsulation
    # All other values come from .composerrc
```

### Configuration Reference

All action inputs can be specified in `.composerrc`:

| Key | Description | Type |
|-----|-------------|------|
| `source_directory` | Source directory containing Lua files | string |
| `output_file` | Path for the final combined Lua file | string |
| `header_file` | Optional header file (relative to source_directory) | string |
| `namespace_file` | Required namespace definition file | string |
| `entrypoint_file` | Required main entry point file | string |
| `footer_file` | Optional footer file | string |
| `dcs_strict_sanitize` | Enable strict DCS sanitization | boolean |
| `scope` | Scope for generated script: `global` or `local` | string |
| `dependencies` | External dependencies to inject | array |

### External Dependencies

Starting from version 4.x, the action supports injecting external Lua dependencies. Dependencies are fetched and included in the final build, with their licenses inline when specified.

#### Dependency Configuration

Dependencies are configured in the `.composerrc` file:

```json
{
  "dependencies": [
    {
      "name": "mist",
      "type": "github_release",
      "source": "mrSkortch/MissionScriptingTools@latest",
      "file": "mist.lua",
      "license": "LICENSE",
      "description": "Mission Scripting Tools for DCS"
    },
    {
      "name": "custom-utils",
      "type": "url",
      "source": "https://example.com/utils.lua",
      "license": "https://example.com/LICENSE.txt"
    },
    {
      "name": "local-lib",
      "type": "local",
      "source": "external/libs/helper.lua",
      "license": "external/libs/LICENSE"
    }
  ]
}
```

#### Dependency Types

1. **GitHub Release** (`github_release`):
   - Fetches files from GitHub releases
   - Supports `@latest` to get the most recent release
   - Requires `file` field to specify which file to download

2. **URL** (`url`):
   - Downloads files from any accessible URL
   - Optional `license` field for license URL

3. **Local** (`local`):
   - Includes files from your repository
   - Paths are relative to repository root
   - Security: Cannot access files outside repository

#### Dependency Fields

| Field | Description | Required |
|-------|-------------|----------|
| `name` | Unique identifier for the dependency | Yes |
| `type` | One of: `github_release`, `url`, `local` | Yes |
| `source` | Source location (varies by type) | Yes |
| `file` | Filename to download (GitHub releases only) | Yes (for github_release) |
| `license` | License file/URL to include inline | No |
| `description` | Human-readable description | No |

Dependencies are injected after the header but before your namespace and core modules, ensuring they're available to your entire script.

See `.composerrc.example`, `.composerrc.example.detailed`, and `.composerrc.example.dependencies` in the repository for more examples.

## Local Development and Testing

This project uses `Taskfile.yml` ([Task](https://taskfile.dev/)) for managing development tasks and `pytest` for testing.

1.  **Install `uv`**: Follow instructions at [astral.sh/uv](https://astral.sh/uv).
2.  **Install `task`**: Follow instructions at [taskfile.dev](https://taskfile.dev/installation/).
3.  **Setup & Install Dependencies**:
    ```bash
    task setup
    ```
4.  **Run Tests**:
    ```bash
    task test
    ```
    Or simply `task` for the default build and test.

    To install and use pre-commit hooks (for automatic linting/formatting before commits):
    ```bash
    task pre-commit-install # Installs hooks into your .git/hooks
    # Now, hooks will run automatically on `git commit`
    # To run all hooks manually on all files:
    task pre-commit-run
    ```

## License

This project is licensed under the terms of the [MIT License](LICENSE).

## Contributing

Contributions, issues, and feature requests are welcome! Feel free to check [issues page](https://github.com/yolowingpixie/dcs-lua-composer-action/issues).
