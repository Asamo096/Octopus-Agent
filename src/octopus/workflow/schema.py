"""Workflow schema definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PhaseStrategy(str, Enum):
    SEQUENTIAL = "sequential"  # Run one phase at a time
    PARALLEL = "parallel"  # Run all tasks concurrently
    PIPELINE = "pipeline"  # Pipeline: items flow through stages independently


@dataclass
class PhaseDefinition:
    """A single phase in a workflow."""

    title: str
    description: str
    prompt_template: str  # Template with {context}, {previous_result}, etc.
    strategy: PhaseStrategy = PhaseStrategy.SEQUENTIAL
    max_retries: int = 2
    timeout_seconds: int = 300
    parallel_items: list[str] | None = None  # Items to process in parallel


@dataclass
class WorkflowDefinition:
    """Complete workflow definition."""

    name: str
    description: str
    version: str = "1.0"
    phases: list[PhaseDefinition] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseResult:
    """Result of a workflow phase."""

    title: str
    success: bool
    output: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0
    retries: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    """Complete workflow execution result."""

    workflow_name: str
    success: bool
    phases: list[PhaseResult] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    error: str | None = None
