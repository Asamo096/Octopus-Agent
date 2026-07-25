"""
Octopus Agent Permissions - Permission engine for harness governance.
"""

from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum
import fnmatch
import os
from pathlib import Path


class PermissionMode(Enum):
    """Permission modes."""
    DEFAULT = "default"      # Confirm mutating operations
    PLAN = "plan"            # Block all writes
    FULL_AUTO = "full_auto"  # Allow everything


@dataclass
class PermissionResult:
    """Result of a permission check."""
    allowed: bool
    reason: Optional[str] = None
    requires_approval: bool = False


class PermissionEngine:
    """Multi-level permission checker."""
    
    # Sensitive paths that are always blocked
    SENSITIVE_PATHS = [
        "~/.ssh/*",
        "~/.aws/*",
        "~/.gnupg/*",
        "**/.env",
        "**/.env.*",
        "**/id_rsa*",
        "**/id_ed25519*",
        "**/id_ecdsa*",
        "**/id_dsa*",
        "**/.gitconfig",
        "**/.netrc",
        "**/.npmrc",
        "**/.pypirc",
    ]
    
    # Safe commands that are allowed by default
    SAFE_COMMANDS = {
        'ls', 'cat', 'grep', 'find', 'wc', 'head', 'tail',
        'git', 'git status', 'git log', 'git diff',
        'python', 'python3', 'pip', 'pip3',
        'node', 'npm', 'yarn',
        'cargo', 'rustc',
        'go',
    }
    
    # Dangerous commands that require approval
    DANGEROUS_COMMANDS = {
        'rm -rf', 'rm -r', 'rm -f',
        'sudo', 'su',
        'chmod 777', 'chmod 7777',
        'chown', 'chgrp',
        'mkfs', 'fdisk',
        'dd', 'shred',
        'wget', 'curl',
        'eval', 'exec',
        'shutdown', 'reboot', 'halt',
    }
    
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        """Initialize the permission engine."""
        self.settings = settings or {}
        self.mode = PermissionMode(self.settings.get('mode', 'default'))
        
        # Additional sensitive paths from settings
        self.sensitive_paths = self.SENSITIVE_PATHS.copy()
        if 'sensitive_paths' in self.settings:
            self.sensitive_paths.extend(self.settings['sensitive_paths'])
        
        # Allowed paths
        self.allowed_paths: List[str] = self.settings.get('allowed_paths', [])
        
        # Custom safe/dangerous commands
        self.safe_commands: Set[str] = set(self.settings.get('safe_commands', []))
        self.dangerous_commands: Set[str] = set(self.settings.get('dangerous_commands', []))
    
    def check(self, tool_call: Any, context: Any) -> PermissionResult:
        """Check if tool call is allowed."""
        # In full auto mode, allow everything
        if self.mode == PermissionMode.FULL_AUTO:
            return PermissionResult(allowed=True)
        
        # In plan mode, block all writes
        if self.mode == PermissionMode.PLAN:
            if self._is_write_operation(tool_call):
                return PermissionResult(
                    allowed=False,
                    reason="Write operations blocked in plan mode"
                )
        
        # Check tool-specific permissions
        if tool_call.tool_name in ['write_file', 'edit_file']:
            return self._check_file_operation(tool_call, context)
        elif tool_call.tool_name == 'shell':
            return self._check_shell_operation(tool_call, context)
        elif tool_call.tool_name == 'read_file':
            return self._check_read_operation(tool_call, context)
        
        # Default allow for unknown tools
        return PermissionResult(allowed=True)
    
    def _is_write_operation(self, tool_call: Any) -> bool:
        """Check if the tool call is a write operation."""
        write_tools = {'write_file', 'edit_file', 'shell'}
        return tool_call.tool_name in write_tools
    
    def _check_file_operation(self, tool_call: Any, context: Any) -> PermissionResult:
        """Check file operation permissions."""
        path = tool_call.arguments.get('path', '')
        if not path:
            return PermissionResult(
                allowed=False,
                reason="No path specified"
            )
        
        # Expand user path
        expanded_path = os.path.expanduser(path)
        
        # Check if path is sensitive
        if self._is_sensitive_path(expanded_path):
            return PermissionResult(
                allowed=False,
                reason=f"Access to sensitive path blocked: {path}",
                requires_approval=False
            )
        
        # Check if path is in allowed paths
        if self.allowed_paths and not self._is_path_allowed(expanded_path):
            return PermissionResult(
                allowed=False,
                reason=f"Path not in allowed paths: {path}",
                requires_approval=True
            )
        
        # In default mode, require approval for write operations
        if self.mode == PermissionMode.DEFAULT:
            return PermissionResult(
                allowed=True,
                requires_approval=True
            )
        
        return PermissionResult(allowed=True)
    
    def _check_shell_operation(self, tool_call: Any, context: Any) -> PermissionResult:
        """Check shell command permissions."""
        command = tool_call.arguments.get('command', '')
        if not command:
            return PermissionResult(
                allowed=False,
                reason="No command specified"
            )
        
        # Check if command is dangerous
        if self._is_dangerous_command(command):
            return PermissionResult(
                allowed=False,
                reason=f"Dangerous command requires approval: {command}",
                requires_approval=True
            )
        
        # Check if command is safe
        if self._is_safe_command(command):
            return PermissionResult(allowed=True)
        
        # In default mode, require approval for unknown commands
        if self.mode == PermissionMode.DEFAULT:
            return PermissionResult(
                allowed=True,
                requires_approval=True
            )
        
        return PermissionResult(allowed=True)
    
    def _check_read_operation(self, tool_call: Any, context: Any) -> PermissionResult:
        """Check read operation permissions."""
        path = tool_call.arguments.get('path', '')
        if not path:
            return PermissionResult(
                allowed=False,
                reason="No path specified"
            )
        
        # Expand user path
        expanded_path = os.path.expanduser(path)
        
        # Check if path is sensitive
        if self._is_sensitive_path(expanded_path):
            return PermissionResult(
                allowed=False,
                reason=f"Access to sensitive path blocked: {path}"
            )
        
        # Read operations are generally allowed
        return PermissionResult(allowed=True)
    
    def _is_sensitive_path(self, path: str) -> bool:
        """Check if a path matches sensitive path patterns."""
        for pattern in self.sensitive_paths:
            if fnmatch.fnmatch(path, pattern):
                return True
            # Also check with expanded user path
            expanded_pattern = os.path.expanduser(pattern)
            if fnmatch.fnmatch(path, expanded_pattern):
                return True
        return False
    
    def _is_path_allowed(self, path: str) -> bool:
        """Check if a path is in the allowed paths."""
        for allowed_path in self.allowed_paths:
            expanded_allowed = os.path.expanduser(allowed_path)
            if path.startswith(expanded_allowed):
                return True
        return False
    
    def _is_safe_command(self, command: str) -> bool:
        """Check if a command is safe."""
        # Check base command
        base_command = command.split()[0] if command else ''
        if base_command in self.safe_commands:
            return True
        
        # Check full command
        if command in self.safe_commands:
            return True
        
        return False
    
    def _is_dangerous_command(self, command: str) -> bool:
        """Check if a command is dangerous."""
        # Check if command contains dangerous patterns
        for dangerous in self.dangerous_commands:
            if dangerous in command:
                return True
        
        # Check built-in dangerous commands
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous in command:
                return True
        
        return False
    
    def add_sensitive_path(self, pattern: str):
        """Add a sensitive path pattern."""
        if pattern not in self.sensitive_paths:
            self.sensitive_paths.append(pattern)
    
    def add_allowed_path(self, path: str):
        """Add an allowed path."""
        if path not in self.allowed_paths:
            self.allowed_paths.append(path)
    
    def add_safe_command(self, command: str):
        """Add a safe command."""
        self.safe_commands.add(command)
    
    def add_dangerous_command(self, command: str):
        """Add a dangerous command."""
        self.dangerous_commands.add(command)
