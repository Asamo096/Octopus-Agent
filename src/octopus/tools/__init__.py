"""Octopus Agent Tools — tool protocol, registry, and built-in tools."""

from .base import Tool, ToolRegistry
from .diff import DiffTool, GitDiffTool, register_diff_tools
from .filesystem import (
    EditFileTool,
    GlobTool,
    GrepTool,
    ReadFileTool,
    WriteFileTool,
    register_filesystem_tools,
)
from .git import GitTool, register_git_tool
from .search import CodeSearchTool, WebSearchTool, register_search_tools
from .shell import ShellTool, register_shell_tool

__all__ = [
    "Tool",
    "ToolRegistry",
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "GlobTool",
    "GrepTool",
    "ShellTool",
    "GitTool",
    "DiffTool",
    "GitDiffTool",
    "WebSearchTool",
    "CodeSearchTool",
    "register_filesystem_tools",
    "register_shell_tool",
    "register_git_tool",
    "register_diff_tools",
    "register_search_tools",
]
