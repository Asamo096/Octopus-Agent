"""Workflow engine — executes deterministic multi-agent workflows."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from octopus.agents.coordinator import WorkerAgent, WorkerConfig
from octopus.core.kernel import Kernel
from octopus.providers.base import Provider
from octopus.tools.base import ToolRegistry
from octopus.workflow.schema import (
    PhaseDefinition,
    PhaseResult,
    PhaseStrategy,
    WorkflowDefinition,
    WorkflowResult,
)

logger = logging.getLogger(__name__)


async def run_workflow(
    workflow: WorkflowDefinition,
    provider: Provider,
    kernel: Kernel,
    registry: ToolRegistry,
    *,
    task: str,
    extra_context: dict[str, Any] | None = None,
) -> WorkflowResult:
    """Execute a workflow with the given task.

    Args:
        workflow: The workflow definition to execute.
        provider: LLM provider for agent execution.
        kernel: Kernel for permission/audit pipeline.
        registry: Tool registry for agent tool access.
        task: The user's task description.
        extra_context: Optional additional context variables.

    Returns:
        WorkflowResult with phase-level results and overall status.
    """
    start_time = time.monotonic()
    results: list[PhaseResult] = []

    # Build context from task and extra data
    context = {"task": task, **(extra_context or {})}

    try:
        for phase in workflow.phases:
            logger.info("Executing phase: %s (strategy: %s)", phase.title, phase.strategy)

            phase_result = await _execute_phase(
                phase=phase,
                context=context,
                previous_results=results,
                provider=provider,
                kernel=kernel,
                registry=registry,
            )
            results.append(phase_result)

            if not phase_result.success:
                logger.warning(
                    "Phase '%s' failed after %d retries: %s",
                    phase.title,
                    phase_result.retries,
                    phase_result.error,
                )
                # Don't stop on phase failure — continue to next phase
                # so we get partial results

    except Exception as exc:
        logger.error("Workflow '%s' failed: %s", workflow.name, exc)
        return WorkflowResult(
            workflow_name=workflow.name,
            success=False,
            phases=results,
            total_duration_seconds=time.monotonic() - start_time,
            error=str(exc),
        )

    all_success = all(r.success for r in results) if results else False
    return WorkflowResult(
        workflow_name=workflow.name,
        success=all_success,
        phases=results,
        total_duration_seconds=time.monotonic() - start_time,
    )


async def _execute_phase(
    phase: PhaseDefinition,
    context: dict[str, Any],
    previous_results: list[PhaseResult],
    provider: Provider,
    kernel: Kernel,
    registry: ToolRegistry,
) -> PhaseResult:
    """Execute a single workflow phase with retry logic."""
    phase_start = time.monotonic()
    last_error: str | None = None

    for attempt in range(phase.max_retries + 1):
        try:
            if phase.strategy == PhaseStrategy.SEQUENTIAL:
                output = await _run_sequential_phase(phase, context, previous_results,
                                                      provider, kernel, registry)
            elif phase.strategy == PhaseStrategy.PARALLEL:
                output = await _run_parallel_phase(phase, context, previous_results,
                                                    provider, kernel, registry)
            elif phase.strategy == PhaseStrategy.PIPELINE:
                output = await _run_pipeline_phase(phase, context, previous_results,
                                                    provider, kernel, registry)
            else:
                output = await _run_sequential_phase(phase, context, previous_results,
                                                      provider, kernel, registry)

            return PhaseResult(
                title=phase.title,
                success=True,
                output=output,
                duration_seconds=time.monotonic() - phase_start,
                retries=attempt,
            )
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "Phase '%s' attempt %d/%d failed: %s",
                phase.title,
                attempt + 1,
                phase.max_retries + 1,
                exc,
            )
            if attempt < phase.max_retries:
                await asyncio.sleep(1.0 * (attempt + 1))  # Backoff

    return PhaseResult(
        title=phase.title,
        success=False,
        error=last_error,
        duration_seconds=time.monotonic() - phase_start,
        retries=phase.max_retries,
    )


async def _run_sequential_phase(
    phase: PhaseDefinition,
    context: dict[str, Any],
    previous: list[PhaseResult],
    provider: Provider,
    kernel: Kernel,
    registry: ToolRegistry,
) -> str:
    """Run a phase as a single sequential agent task."""
    prompt = _build_prompt(phase, context, previous)
    config = WorkerConfig(task=prompt, max_turns=20)
    worker = WorkerAgent(
        f"phase_{phase.title}", config, provider, kernel, registry
    )
    await worker.start()
    result = await worker.wait(timeout=phase.timeout_seconds)
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(result["error"])
    return str(result) if result else ""


async def _run_parallel_phase(
    phase: PhaseDefinition,
    context: dict[str, Any],
    previous: list[PhaseResult],
    provider: Provider,
    kernel: Kernel,
    registry: ToolRegistry,
) -> str:
    """Run multiple agent tasks in parallel."""
    items = phase.parallel_items or [""]
    prompt = _build_prompt(phase, context, previous)
    workers = []

    for i, item in enumerate(items):
        task_prompt = prompt.replace("{item}", item)
        config = WorkerConfig(task=task_prompt, max_turns=20)
        worker = WorkerAgent(
            f"phase_{phase.title}_{i}", config, provider, kernel, registry
        )
        workers.append(worker)

    # Start all workers
    start_futures = [asyncio.ensure_future(w.start()) for w in workers]
    await asyncio.gather(*start_futures, return_exceptions=True)

    # Wait for all results
    results = []
    for w in workers:
        try:
            r = await w.wait(timeout=phase.timeout_seconds)
            results.append(str(r) if r else "")
        except TimeoutError:
            results.append(f"[Timeout: {phase.title}]")

    return "\n\n".join(r for r in results if r)


async def _run_pipeline_phase(
    phase: PhaseDefinition,
    context: dict[str, Any],
    previous: list[PhaseResult],
    provider: Provider,
    kernel: Kernel,
    registry: ToolRegistry,
) -> str:
    """Run items through stages independently (no barrier between stages)."""
    items = phase.parallel_items or [""]
    if not items:
        return ""

    prompt = _build_prompt(phase, context, previous)
    results: list[str] = []

    # Pipeline: each item flows through all stages independently
    for i, item in enumerate(items):
        task_prompt = prompt.replace("{item}", item)
        config = WorkerConfig(task=task_prompt, max_turns=15)
        worker = WorkerAgent(
            f"pipeline_{phase.title}_{i}", config, provider, kernel, registry
        )
        await worker.start()
        try:
            r = await worker.wait(timeout=phase.timeout_seconds)
            results.append(str(r) if r else "")
        except TimeoutError:
            results.append(f"[Timeout: {phase.title}]")

    return "\n\n".join(r for r in results if r)


def _build_prompt(
    phase: PhaseDefinition,
    context: dict[str, Any],
    previous: list[PhaseResult],
) -> str:
    """Build a prompt from a phase template."""
    # Build context from previous results
    prev_text = ""
    for r in previous:
        status = "OK" if r.success else "FAILED"
        prev_text += f"\nPhase '{r.title}' [{status}]:\n{r.output or r.error or '(no output)'}\n"

    return phase.prompt_template.format(
        task=context.get("task", ""),
        previous_results=prev_text,
        **context,
    )
