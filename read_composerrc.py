#!/usr/bin/env python3
"""
Read .composerrc configuration file and output values for GitHub Actions.
"""

import json
import os
import sys
from pathlib import Path


def read_composerrc(workspace_path):
    """
    Read .composerrc file from the workspace root.

    Returns:
        dict: Configuration values from .composerrc, or empty dict if not found
    """
    composerrc_path = Path(workspace_path) / ".composerrc"

    if not composerrc_path.exists():
        return {}

    try:
        with open(composerrc_path) as f:
            config = json.load(f)
        return config
    except json.JSONDecodeError as e:
        print(f"::error::Invalid JSON in .composerrc: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"::error::Error reading .composerrc: {e}", file=sys.stderr)
        sys.exit(1)


def validate_config(config):
    """
    Validate configuration values.

    Args:
        config (dict): Configuration from .composerrc

    Returns:
        dict: Validated configuration
    """
    valid_keys = {
        "source_directory",
        "output_file",
        "header_file",
        "namespace_file",
        "entrypoint_file",
        "footer_file",
        "dcs_strict_sanitize",
        "dependencies",
    }

    # Filter out any invalid keys
    validated = {k: v for k, v in config.items() if k in valid_keys}

    # Warn about invalid keys
    invalid_keys = set(config.keys()) - valid_keys
    if invalid_keys:
        print(f"::warning::Unknown keys in .composerrc will be ignored: {', '.join(invalid_keys)}")

    return validated


def output_for_github_actions(config):
    """
    Output configuration as environment variables for GitHub Actions.

    Args:
        config (dict): Configuration values
    """
    # Output each config value as an environment variable
    # GitHub Actions will pick these up and use them
    for key, value in config.items():
        # Special handling for dependencies (output as JSON)
        if key == "dependencies" and isinstance(value, list):
            value = json.dumps(value)
        # Convert boolean values to string
        elif isinstance(value, bool):
            value = "true" if value else "false"

        # Output in GitHub Actions format
        # Using GITHUB_OUTPUT for newer actions
        output_file = os.getenv("GITHUB_OUTPUT", "")
        if output_file:
            with open(output_file, "a") as f:
                f.write(f"rc_{key}={value}\n")
        else:
            # Fallback for older GitHub Actions
            print(f"::set-output name=rc_{key}::{value}")


def main():
    if len(sys.argv) != 2:
        print("Usage: read_composerrc.py <workspace_path>", file=sys.stderr)
        sys.exit(1)

    workspace_path = sys.argv[1]

    # Read .composerrc
    config = read_composerrc(workspace_path)

    if config:
        print("::notice::.composerrc file found and loaded")

        # Validate configuration
        validated_config = validate_config(config)

        # Output for GitHub Actions
        output_for_github_actions(validated_config)
    else:
        print("::notice::No .composerrc file found, using action inputs only")


if __name__ == "__main__":
    main()
