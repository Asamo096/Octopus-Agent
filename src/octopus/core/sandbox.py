"""
Octopus Agent Sandbox - Filesystem sandbox isolation.
"""

from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import os
import re


class OperationType(Enum):
    """Types of filesystem operations."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"


@dataclass
class SandboxResult:
    """Result of a sandbox validation."""
    valid: bool
    reason: Optional[str] = None
    path: Optional[str] = None


class Sandbox:
    """Filesystem sandbox isolation."""
    
    # Default sensitive paths
    DEFAULT_SENSITIVE_PATHS = [
        "~/.ssh",
        "~/.aws",
        "~/.gnupg",
        "~/.env",
        "**/.env",
        "**/.env.*",
        "**/id_rsa*",
        "**/id_ed25519*",
        "**/id_ecdsa*",
        "**/id_dsa*",
    ]
    
    # Default allowed paths
    DEFAULT_ALLOWED_PATHS = [
        "~/*",
        "/tmp/*",
    ]
    
    # Dangerous command patterns
    DANGEROUS_COMMAND_PATTERNS = [
        r'rm\s+-rf',
        r'rm\s+-r\s+/',
        r'rm\s+-f\s+/',
        r'sudo\s+',
        r'su\s+',
        r'chmod\s+777',
        r'chmod\s+7777',
        r'chown\s+',
        r'chgrp\s+',
        r'mkfs\.',
        r'fdisk\s+',
        r'dd\s+if=',
        r'shred\s+',
        r'wget\s+',
        r'curl\s+',
        r'eval\s+',
        r'exec\s+',
        r'shutdown\s+',
        r'reboot\s+',
        r'halt\s+',
    ]
    
    # Safe command patterns
    SAFE_COMMAND_PATTERNS = [
        r'^ls\s*',
        r'^cat\s+',
        r'^grep\s+',
        r'^find\s+',
        r'^wc\s+',
        r'^head\s+',
        r'^tail\s+',
        r'^git\s+status',
        r'^git\s+log',
        r'^git\s+diff',
        r'^python\s+',
        r'^python3\s+',
        r'^pip\s+',
        r'^pip3\s+',
        r'^node\s+',
        r'^npm\s+',
        r'^yarn\s+',
        r'^cargo\s+',
        r'^rustc\s+',
        r'^go\s+',
    ]
    
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        """Initialize the sandbox."""
        self.settings = settings or {}
        self.enabled = self.settings.get('enabled', True)
        
        # Sensitive paths
        self.sensitive_paths: List[str] = self.DEFAULT_SENSITIVE_PATHS.copy()
        if 'sensitive_paths' in self.settings:
            self.sensitive_paths.extend(self.settings['sensitive_paths'])
        
        # Allowed paths
        self.allowed_paths: List[str] = self.DEFAULT_ALLOWED_PATHS.copy()
        if 'allowed_paths' in self.settings:
            self.allowed_paths.extend(self.settings['allowed_paths'])
        
        # Command safety
        self.dangerous_patterns: List[str] = self.DANGEROUS_COMMAND_PATTERNS.copy()
        if 'dangerous_patterns' in self.settings:
            self.dangerous_patterns.extend(self.settings['dangerous_patterns'])
        
        self.safe_patterns: List[str] = self.SAFE_COMMAND_PATTERNS.copy()
        if 'safe_patterns' in self.settings:
            self.safe_patterns.extend(self.settings['safe_patterns'])
    
    def validate_path(self, path: Path, operation: OperationType) -> SandboxResult:
        """Check if path is within allowed workspace."""
        if not self.enabled:
            return SandboxResult(valid=True)
        
        # Expand user path
        expanded_path = os.path.expanduser(str(path))
        path_obj = Path(expanded_path)
        
        # Check if path is sensitive
        if self._is_sensitive_path(path_obj):
            return SandboxResult(
                valid=False,
                reason=f"Access to sensitive path blocked: {path}",
                path=str(path)
            )
        
        # For write operations, check if path is in allowed paths
        if operation in [OperationType.WRITE, OperationType.DELETE]:
            if not self._is_path_allowed(path_obj):
                return SandboxResult(
                    valid=False,
                    reason=f"Path not in allowed workspace: {path}",
                    path=str(path)
                )
        
        # For read operations, allow if not sensitive
        return SandboxResult(valid=True, path=str(path))
    
    def validate_command(self, command: str) -> SandboxResult:
        """Check if shell command is safe."""
        if not self.enabled:
            return SandboxResult(valid=True)
        
        # Check if command is dangerous
        if self._is_dangerous_command(command):
            return SandboxResult(
                valid=False,
                reason=f"Dangerous command blocked: {command}",
                path=None
            )
        
        # Check if command is safe
        if self._is_safe_command(command):
            return SandboxResult(valid=True, path=None)
        
        # Unknown commands require approval
        return SandboxResult(
            valid=True,
            reason="Unknown command - requires approval",
            path=None
        )
    
    def _is_sensitive_path(self, path: Path) -> bool:
        """Check if a path matches sensitive path patterns."""
        path_str = str(path)
        
        for pattern in self.sensitive_paths:
            # Expand user in pattern
            expanded_pattern = os.path.expanduser(pattern)
            
            # Convert glob pattern to regex
            regex_pattern = self._glob_to_regex(expanded_pattern)
            
            if re.match(regex_pattern, path_str):
                return True
            
            # Also check with fnmatch
            import fnmatch
            if fnmatch.fnmatch(path_str, expanded_pattern):
                return True
        
        return False
    
    def _is_path_allowed(self, path: Path) -> bool:
        """Check if a path is in the allowed paths."""
        path_str = str(path)
        
        for pattern in self.allowed_paths:
            # Expand user in pattern
            expanded_pattern = os.path.expanduser(pattern)
            
            # Convert glob pattern to regex
            regex_pattern = self._glob_to_regex(expanded_pattern)
            
            if re.match(regex_pattern, path_str):
                return True
            
            # Also check with fnmatch
            import fnmatch
            if fnmatch.fnmatch(path_str, expanded_pattern):
                return True
        
        return False
    
    def _is_dangerous_command(self, command: str) -> bool:
        """Check if a command is dangerous."""
        for pattern in self.dangerous_patterns:
            if re.search(pattern, command):
                return True
        
        return False
    
    def _is_safe_command(self, command: str) -> bool:
        """Check if a command is safe."""
        for pattern in self.safe_patterns:
            if re.match(pattern, command):
                return True
        
        return False
    
    def _glob_to_regex(self, pattern: str) -> str:
        """Convert a glob pattern to a regex pattern."""
        # Escape special regex characters
        pattern = re.escape(pattern)
        
        # Convert glob wildcards to regex
        pattern = pattern.replace(r'\*', '.*')
        pattern = pattern.replace(r'\?', '.')
        
        # Handle ** for recursive matching
        pattern = pattern.replace(r'\*\*', '.*')
        
        return f'^{pattern}$'
    
    def add_sensitive_path(self, pattern: str):
        """Add a sensitive path pattern."""
        if pattern not in self.sensitive_paths:
            self.sensitive_paths.append(pattern)
    
    def add_allowed_path(self, pattern: str):
        """Add an allowed path pattern."""
        if pattern not in self.allowed_paths:
            self.allowed_paths.append(pattern)
    
    def add_dangerous_pattern(self, pattern: str):
        """Add a dangerous command pattern."""
        if pattern not in self.dangerous_patterns:
            self.dangerous_patterns.append(pattern)
    
    def add_safe_pattern(self, pattern: str):
        """Add a safe command pattern."""
        if pattern not in self.safe_patterns:
            self.safe_patterns.append(pattern)
