#!/usr/bin/env python3
"""
Tests for the dependency manager functionality.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add parent directory to path to import dependency_manager
sys.path.insert(0, str(Path(__file__).parent.parent))

from dependency_manager import Dependency, DependencyManager, load_dependencies_config


class TestDependency:
    """Test the Dependency class."""

    def test_valid_github_release_dependency(self):
        """Test creating a valid GitHub release dependency."""
        config = {
            "name": "test-lib",
            "type": "github_release",
            "source": "owner/repo@v1.0.0",
            "file": "test-lib.lua",
            "license": "LICENSE",
            "description": "Test library",
        }
        dep = Dependency(config)
        assert dep.name == "test-lib"
        assert dep.type == "github_release"
        assert dep.source == "owner/repo@v1.0.0"
        assert dep.file == "test-lib.lua"
        assert dep.license == "LICENSE"
        assert dep.description == "Test library"

    def test_valid_url_dependency(self):
        """Test creating a valid URL dependency."""
        config = {
            "name": "remote-lib",
            "type": "url",
            "source": "https://example.com/lib.lua",
            "license": "https://example.com/LICENSE",
        }
        dep = Dependency(config)
        assert dep.name == "remote-lib"
        assert dep.type == "url"
        assert dep.source == "https://example.com/lib.lua"
        assert dep.license == "https://example.com/LICENSE"

    def test_valid_local_dependency(self):
        """Test creating a valid local dependency."""
        config = {
            "name": "local-lib",
            "type": "local",
            "source": "libs/local-lib.lua",
            "license": "libs/LICENSE",
        }
        dep = Dependency(config)
        assert dep.name == "local-lib"
        assert dep.type == "local"
        assert dep.source == "libs/local-lib.lua"

    def test_missing_name(self):
        """Test that missing name raises ValueError."""
        config = {"type": "url", "source": "https://example.com/lib.lua"}
        with pytest.raises(ValueError, match="must have a 'name' field"):
            Dependency(config)

    def test_missing_type(self):
        """Test that missing type raises ValueError."""
        config = {"name": "test", "source": "https://example.com/lib.lua"}
        with pytest.raises(ValueError, match="must have a 'type' field"):
            Dependency(config)

    def test_invalid_type(self):
        """Test that invalid type raises ValueError."""
        config = {"name": "test", "type": "invalid", "source": "test.lua"}
        with pytest.raises(ValueError, match="invalid type"):
            Dependency(config)

    def test_missing_source(self):
        """Test that missing source raises ValueError."""
        config = {"name": "test", "type": "url"}
        with pytest.raises(ValueError, match="must have a 'source' field"):
            Dependency(config)

    def test_github_release_missing_file(self):
        """Test that GitHub release without file raises ValueError."""
        config = {
            "name": "test",
            "type": "github_release",
            "source": "owner/repo@v1.0.0",
        }
        with pytest.raises(ValueError, match="must specify a 'file' field"):
            Dependency(config)


class TestDependencyManager:
    """Test the DependencyManager class."""

    def test_cache_directory_creation(self):
        """Test that cache directory is created."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir) / "test-cache"
            manager = DependencyManager(cache_dir)
            assert cache_dir.exists()
            assert cache_dir.is_dir()

    @patch("urllib.request.urlopen")
    def test_fetch_github_release(self, mock_urlopen):
        """Test fetching from GitHub release."""
        # Mock the API response for latest release
        api_response = Mock()
        api_response.__enter__ = Mock(return_value=api_response)
        api_response.__exit__ = Mock(return_value=None)
        api_response.read.return_value = json.dumps({"tag_name": "v1.2.3"}).encode()

        # Mock the file download response
        file_response = Mock()
        file_response.__enter__ = Mock(return_value=file_response)
        file_response.__exit__ = Mock(return_value=None)
        file_response.read.return_value = b"-- Test Lua content\nprint('Hello')"

        # Configure urlopen to return different responses based on URL
        def urlopen_side_effect(url):
            if "api.github.com" in url:
                return api_response
            else:
                return file_response

        mock_urlopen.side_effect = urlopen_side_effect

        manager = DependencyManager()
        dep = Dependency(
            {
                "name": "test-lib",
                "type": "github_release",
                "source": "owner/repo@latest",
                "file": "lib.lua",
            }
        )

        content, license_content = manager.fetch_dependency(dep, Path("."))
        assert content == "-- Test Lua content\nprint('Hello')"
        assert license_content is None

    @patch("urllib.request.urlopen")
    def test_fetch_url(self, mock_urlopen):
        """Test fetching from URL."""
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = b"-- URL Lua content"
        mock_urlopen.return_value = response

        manager = DependencyManager()
        dep = Dependency(
            {
                "name": "url-lib",
                "type": "url",
                "source": "https://example.com/lib.lua",
            }
        )

        content, license_content = manager.fetch_dependency(dep, Path("."))
        assert content == "-- URL Lua content"
        assert license_content is None

    def test_fetch_local(self):
        """Test fetching from local file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_path = Path(tmp_dir)
            lua_file = base_path / "libs" / "local.lua"
            lua_file.parent.mkdir(parents=True)
            lua_file.write_text("-- Local Lua content")

            manager = DependencyManager()
            dep = Dependency(
                {
                    "name": "local-lib",
                    "type": "local",
                    "source": "libs/local.lua",
                }
            )

            content, license_content = manager.fetch_dependency(dep, base_path)
            assert content == "-- Local Lua content"
            assert license_content is None

    def test_fetch_local_with_license(self):
        """Test fetching local file with license."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_path = Path(tmp_dir)
            lua_file = base_path / "libs" / "local.lua"
            license_file = base_path / "libs" / "LICENSE"
            lua_file.parent.mkdir(parents=True)
            lua_file.write_text("-- Local Lua content")
            license_file.write_text("MIT License")

            manager = DependencyManager()
            dep = Dependency(
                {
                    "name": "local-lib",
                    "type": "local",
                    "source": "libs/local.lua",
                    "license": "libs/LICENSE",
                }
            )

            content, license_content = manager.fetch_dependency(dep, base_path)
            assert content == "-- Local Lua content"
            assert license_content == "MIT License"

    def test_fetch_local_outside_base_path(self):
        """Test that fetching files outside base path raises error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_path = Path(tmp_dir) / "project"
            base_path.mkdir()

            manager = DependencyManager()
            dep = Dependency(
                {
                    "name": "bad-lib",
                    "type": "local",
                    "source": "../../../etc/passwd",
                }
            )

            with pytest.raises(ValueError, match="outside the project"):
                manager.fetch_dependency(dep, base_path)

    def test_format_dependency_block(self):
        """Test formatting dependency block."""
        manager = DependencyManager()
        dep = Dependency(
            {
                "name": "test-lib",
                "type": "url",
                "source": "https://example.com/lib.lua",
                "description": "A test library",
            }
        )

        lua_content = "-- Test content\nfunction test() end"
        license_content = "MIT License\nCopyright 2024"

        block = manager.format_dependency_block(dep, lua_content, license_content)

        assert "-- External Dependency: test-lib" in block
        assert "-- Description: A test library" in block
        assert "-- Source: https://example.com/lib.lua" in block
        assert "-- License:" in block
        assert "-- MIT License" in block
        assert "-- Copyright 2024" in block
        assert "-- Test content" in block
        assert "function test() end" in block

    @patch("urllib.request.urlopen")
    def test_caching(self, mock_urlopen):
        """Test that downloads are cached."""
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = b"-- Cached content"
        mock_urlopen.return_value = response

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir) / "cache"
            manager = DependencyManager(cache_dir)

            # First fetch
            content1 = manager._download_with_cache("https://example.com/lib.lua", "test_lib")
            assert content1 == "-- Cached content"
            assert mock_urlopen.call_count == 1

            # Second fetch should use cache
            content2 = manager._download_with_cache("https://example.com/lib.lua", "test_lib")
            assert content2 == "-- Cached content"
            assert mock_urlopen.call_count == 1  # Should not increase


class TestLoadDependenciesConfig:
    """Test the load_dependencies_config function."""

    def test_load_valid_config(self):
        """Test loading valid dependencies configuration."""
        config = {
            "dependencies": [
                {
                    "name": "lib1",
                    "type": "url",
                    "source": "https://example.com/lib1.lua",
                },
                {
                    "name": "lib2",
                    "type": "local",
                    "source": "libs/lib2.lua",
                },
            ]
        }

        deps = load_dependencies_config(config)
        assert len(deps) == 2
        assert deps[0].name == "lib1"
        assert deps[1].name == "lib2"

    def test_load_empty_config(self):
        """Test loading empty dependencies."""
        config = {"dependencies": []}
        deps = load_dependencies_config(config)
        assert len(deps) == 0

    def test_load_no_dependencies_key(self):
        """Test loading config without dependencies key."""
        config = {}
        deps = load_dependencies_config(config)
        assert len(deps) == 0

    def test_load_invalid_dependency(self):
        """Test that invalid dependency raises error."""
        config = {
            "dependencies": [
                {
                    "name": "valid",
                    "type": "url",
                    "source": "https://example.com/valid.lua",
                },
                {
                    # Missing required fields
                    "type": "url",
                },
            ]
        }

        with pytest.raises(ValueError):
            load_dependencies_config(config)
