#!/usr/bin/env python3
"""
Dependency manager for fetching and processing external Lua dependencies.
"""

import hashlib
import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Dependency:
    """Represents a single external dependency."""

    def __init__(self, config: dict):
        self.name = config.get("name", "")
        self.type = config.get("type", "")  # "github_release", "url", "local"
        self.source = config.get("source", "")
        self.file = config.get("file", "")  # For github_release type
        self.license = config.get("license", "")  # Optional license file/URL
        self.description = config.get("description", "")

        # Validate required fields
        if not self.name:
            raise ValueError("Dependency must have a 'name' field")
        if not self.type:
            raise ValueError(f"Dependency '{self.name}' must have a 'type' field")
        if self.type not in ["github_release", "url", "local"]:
            raise ValueError(f"Dependency '{self.name}' has invalid type: {self.type}")
        if not self.source:
            raise ValueError(f"Dependency '{self.name}' must have a 'source' field")

        # Additional validation for github_release
        if self.type == "github_release" and not self.file:
            raise ValueError(f"GitHub release dependency '{self.name}' must specify a 'file' field")


class DependencyManager:
    """Manages fetching and processing of external dependencies."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "dcs-lua-composer-cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_dependency(self, dep: Dependency, base_path: Path) -> Tuple[str, Optional[str]]:
        """
        Fetch a dependency and return its content and optional license content.

        Args:
            dep: The dependency to fetch
            base_path: Base path for resolving local dependencies

        Returns:
            Tuple of (lua_content, license_content)
        """
        if dep.type == "github_release":
            return self._fetch_github_release(dep)
        elif dep.type == "url":
            return self._fetch_url(dep)
        elif dep.type == "local":
            return self._fetch_local(dep, base_path)
        else:
            raise ValueError(f"Unknown dependency type: {dep.type}")

    def _fetch_github_release(self, dep: Dependency) -> Tuple[str, Optional[str]]:
        """Fetch a file from a GitHub release."""
        # Parse the source to extract owner, repo, and tag
        # Expected format: owner/repo@tag or owner/repo@latest
        match = re.match(r"^([^/]+)/([^@]+)@(.+)$", dep.source)
        if not match:
            raise ValueError(
                f"Invalid GitHub release source format for '{dep.name}': {dep.source}. "
                "Expected format: owner/repo@tag"
            )

        owner, repo, tag = match.groups()

        # Handle 'latest' tag
        if tag == "latest":
            # Get the latest release tag
            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
            try:
                with urllib.request.urlopen(api_url) as response:
                    release_data = json.loads(response.read().decode())
                    tag = release_data["tag_name"]
            except Exception as e:
                raise RuntimeError(f"Failed to fetch latest release for {owner}/{repo}: {e}")

        # Construct the download URL
        file_url = f"https://github.com/{owner}/{repo}/releases/download/{tag}/{dep.file}"

        # Fetch the Lua file
        lua_content = self._download_with_cache(file_url, f"{dep.name}_{tag}_{dep.file}")

        # Fetch license if specified
        license_content = None
        if dep.license:
            license_url = f"https://github.com/{owner}/{repo}/releases/download/{tag}/{dep.license}"
            try:
                license_content = self._download_with_cache(
                    license_url, f"{dep.name}_{tag}_{dep.license}"
                )
            except Exception as e:
                print(f"Warning: Failed to fetch license for '{dep.name}': {e}")

        return lua_content, license_content

    def _fetch_url(self, dep: Dependency) -> Tuple[str, Optional[str]]:
        """Fetch a file from a URL."""
        # Fetch the Lua file
        lua_content = self._download_with_cache(dep.source, f"{dep.name}_main")

        # Fetch license if specified
        license_content = None
        if dep.license:
            try:
                license_content = self._download_with_cache(dep.license, f"{dep.name}_license")
            except Exception as e:
                print(f"Warning: Failed to fetch license for '{dep.name}': {e}")

        return lua_content, license_content

    def _fetch_local(self, dep: Dependency, base_path: Path) -> Tuple[str, Optional[str]]:
        """Fetch a file from the local filesystem."""
        # Resolve the path relative to the base path
        file_path = (base_path / dep.source).resolve()

        # Security check: ensure the resolved path is within allowed boundaries
        # Resolve base_path too to handle symlinks correctly
        try:
            file_path.relative_to(base_path.resolve())
        except ValueError:
            raise ValueError(
                f"Local dependency '{dep.name}' resolves to a path outside the project: {file_path}"
            )

        if not file_path.exists():
            raise FileNotFoundError(f"Local dependency '{dep.name}' not found at: {file_path}")

        # Read the Lua file
        with open(file_path, "r", encoding="utf-8") as f:
            lua_content = f.read()

        # Read license if specified
        license_content = None
        if dep.license:
            license_path = (base_path / dep.license).resolve()
            try:
                license_path.relative_to(base_path.resolve())
                if license_path.exists():
                    with open(license_path, "r", encoding="utf-8") as f:
                        license_content = f.read()
                else:
                    print(f"Warning: License file not found for '{dep.name}': {license_path}")
            except ValueError:
                print(f"Warning: License path for '{dep.name}' is outside project boundaries")

        return lua_content, license_content

    def _download_with_cache(self, url: str, cache_key: str) -> str:
        """Download a file with caching support."""
        # Create a hash of the URL for the cache filename
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        cache_file = self.cache_dir / f"{cache_key}_{url_hash}.cached"

        # Check if cached version exists
        if cache_file.exists():
            print(f"Using cached version of {url}")
            with open(cache_file, "r", encoding="utf-8") as f:
                return f.read()

        # Download the file
        print(f"Downloading {url}")
        try:
            with urllib.request.urlopen(url) as response:
                content = response.read().decode("utf-8")

            # Save to cache
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(content)

            return content
        except Exception as e:
            raise RuntimeError(f"Failed to download {url}: {e}")

    def format_dependency_block(
        self, dep: Dependency, lua_content: str, license_content: Optional[str]
    ) -> str:
        """Format a dependency with its license for injection into the composed file."""
        lines = []

        # Add dependency header
        lines.append(f"\n-- External Dependency: {dep.name}")
        if dep.description:
            lines.append(f"-- Description: {dep.description}")
        lines.append(f"-- Source: {dep.source}")
        if dep.type == "github_release":
            lines.append(f"-- File: {dep.file}")

        # Add license if available
        if license_content:
            lines.append("-- License:")
            for line in license_content.strip().split("\n"):
                lines.append(f"-- {line}" if line else "--")

        lines.append("")  # Empty line before content

        # Add the Lua content
        lines.append(lua_content)

        return "\n".join(lines)


def load_dependencies_config(config_data: dict) -> List[Dependency]:
    """Load dependencies from configuration."""
    dependencies = []

    deps_config = config_data.get("dependencies", [])
    if not isinstance(deps_config, list):
        raise ValueError("Dependencies must be a list")

    for dep_config in deps_config:
        try:
            dependencies.append(Dependency(dep_config))
        except ValueError as e:
            print(f"Error loading dependency: {e}")
            raise

    return dependencies
