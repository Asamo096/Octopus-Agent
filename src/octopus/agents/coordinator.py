"""Agent coordinator -- orchestrates multiple agents for complex tasks.

Supports spawning agents, running them in parallel or sequentially,
and background worker agents with per-worker budgets.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from octopus.agents.base import AgentDefinition
from octopus.agents.llm_agent import LLMAgent
from octopus.core.kernel import Kernel
from octopus.providers.base import Provider
from octopus.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker agent (Pattern 9)
# ---------------------------------------------------------------------------


@dataclass
class WorkerConfig:
    """Configuration for a background worker agent.

    Workers run autonomously with their own budget constraints
    and optional tool restrictions.
    """

    task: str
    agent_type: str = "general"
    model: str | None = None
    max_turns: int = 10
    max_cost_usd: float | None = None
    allowed_tools: list[str] | None = None
    isolation: Literal["none", "worktree"] = "none"


class WorkerAgent:
    """Background agent worker that runs autonomously.

    Each worker has its own message history, budget, and execution context.
    The coordinator injects task context and monitors progress.

    Usage:
        config = WorkerConfig(task="Fix the lint errors", max_turns=5)
        worker = WorkerAgent("w1", config, provider, kernel, registry)
        await worker.start()
        result = await worker.wait(timeout=60)
    """

    def __init__(
        self,
        worker_id: str,
        config: WorkerConfig,
        provider: Provider,
        kernel: Kernel,
        registry: ToolRegistry,
    ) -> None:
        self.worker_id = worker_id
        self.config = config
        self._provider = provider
        self._kernel = kernel
        self._registry = registry
        self._agent: LLMAgent | None = None
        self._task: asyncio.Task[str] | None = None
        self.result: str | None = None
        self.status: str = "pending"

    async def start(self) -> None:
        """Start the worker in the background."""
        self.status = "running"
        self._task = asyncio.create_task(self._run(), name=f"worker-{self.worker_id}")

    async def _run(self) -> str:
        """Execute the worker's task."""
        try:
            definition = AgentDefinition(
                name=f"worker-{self.worker_id}",
                description=f"Background worker: {self.config.task[:80]}",
                model=self.config.model,
                tools=self.config.allowed_tools or [],
                max_turns=self.config.max_turns,
            )

            self._agent = LLMAgent(
                definition,
                self._kernel,
                self._provider,
                self._registry,
            )

            self.result = await self._agent.run(self.config.task)
            self.status = "completed"
            return self.result
        except asyncio.CancelledError:
            self.status = "cancelled"
            raise
        except Exception as exc:
            self.status = "failed"
            self.result = f"Worker failed: {exc}"
            logger.error("Worker %s failed: %s", self.worker_id, exc)
            return self.result

    async def wait(self, timeout: float | None = None) -> str | None:
        """Wait for the worker to complete.

        Args:
            timeout: Maximum seconds to wait. None means wait forever.

        Returns:
            The worker's result text, or None if it hasn't completed.

        Raises:
            asyncio.TimeoutError: If timeout is exceeded.
        """
        if self._task is None:
            return self.result

        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except TimeoutError:
            raise
        return self.result

    def cancel(self) -> None:
        """Cancel the running worker."""
        if self._agent:
            asyncio.ensure_future(self._agent.stop())
        if self._task and not self._task.done():
            self._task.cancel()
            self.status = "cancelled"


# ---------------------------------------------------------------------------
# Agent coordinator
# ---------------------------------------------------------------------------


class AgentCoordinator:
    """Orchestrates multiple agents for complex multi-step tasks.

    Supports:
    - Spawning agents with specific definitions
    - Running agents in parallel or sequentially
    - Background worker agents with per-worker budgets
    - Inter-agent communication via shared results
    - Collecting and merging results

    Usage:
        coordinator = AgentCoordinator(kernel, provider, registry)
        agent_id = await coordinator.spawn(definition, "Fix the bug")
        result = await coordinator.wait(agent_id)
    """

    def __init__(
        self,
        kernel: Kernel,
        provider: Provider,
        registry: ToolRegistry,
        *,
        parent_session_id: str | None = None,
    ) -> None:
        self._kernel = kernel
        self._provider = provider
        self._registry = registry
        self._parent_session_id = (
            parent_session_id or f"coordinator-{uuid.uuid4().hex[:8]}"
        )
        self._agents: dict[str, LLMAgent] = {}
        self._tasks: dict[str, asyncio.Task[str]] = {}
        self._results: dict[str, str] = {}
        self._workers: dict[str, WorkerAgent] = {}

    async def spawn(
        self,
        definition: AgentDefinition,
        task: str,
        *,
        wait: bool = False,
    ) -> str:
        """Spawn an agent to work on a task.

        Args:
            definition: Agent definition
            task: The task to execute
            wait: If True, wait for completion before returning

        Returns:
            Agent ID (used for wait/stop/result)
        """
        agent_id = f"{definition.name}-{uuid.uuid4().hex[:8]}"

        agent = LLMAgent(
            definition,
            self._kernel,
            self._provider,
            self._registry,
            parent_session_id=self._parent_session_id,
        )
        self._agents[agent_id] = agent

        # Start the agent as an asyncio task
        task_obj = asyncio.create_task(
            agent.run(task),
            name=f"agent-{agent_id}",
        )
        self._tasks[agent_id] = task_obj

        if wait:
            result = await task_obj
            self._results[agent_id] = result
            return agent_id

        logger.info("Spawned agent %s for task: %s", agent_id, task[:100])
        return agent_id

    async def wait(self, agent_id: str) -> str:
        """Wait for an agent to complete and return its result.

        Args:
            agent_id: The agent ID returned by spawn()

        Returns:
            The agent's final text response
        """
        if agent_id in self._results:
            return self._results[agent_id]

        task = self._tasks.get(agent_id)
        if task is None:
            return f"Agent {agent_id} not found"

        result = await task
        self._results[agent_id] = result
        return result

    async def stop(self, agent_id: str) -> None:
        """Stop a running agent."""
        agent = self._agents.get(agent_id)
        if agent:
            await agent.stop()
        task = self._tasks.get(agent_id)
        if task and not task.done():
            task.cancel()

    async def stop_all(self) -> None:
        """Stop all running agents and workers."""
        for agent_id in list(self._agents.keys()):
            await self.stop(agent_id)
        for worker_id in list(self._workers.keys()):
            self.stop_worker(worker_id)

    def list_agents(self) -> list[dict[str, Any]]:
        """List all agents and their status."""
        result = []
        for agent_id, agent in self._agents.items():
            task = self._tasks.get(agent_id)
            status = "completed" if agent_id in self._results else "running"
            if task and task.done() and agent_id not in self._results:
                status = "completed"
            result.append(
                {
                    "id": agent_id,
                    "name": agent.name,
                    "status": status,
                }
            )
        return result

    def get_result(self, agent_id: str) -> str | None:
        """Get the result of a completed agent (non-blocking)."""
        return self._results.get(agent_id)

    async def run_parallel(
        self,
        tasks: list[tuple[AgentDefinition, str]],
    ) -> list[str]:
        """Run multiple agents in parallel and return all results.

        Args:
            tasks: List of (definition, task_text) tuples

        Returns:
            List of results in the same order as tasks
        """
        agent_ids = []
        for definition, task_text in tasks:
            agent_id = await self.spawn(definition, task_text)
            agent_ids.append(agent_id)

        # Wait for all to complete
        results = []
        for agent_id in agent_ids:
            result = await self.wait(agent_id)
            results.append(result)

        return results

    async def run_sequential(
        self,
        tasks: list[tuple[AgentDefinition, str]],
        *,
        pass_results: bool = False,
    ) -> list[str]:
        """Run agents sequentially, optionally passing results forward.

        Args:
            tasks: List of (definition, task_text) tuples
            pass_results: If True, each task receives the previous result

        Returns:
            List of results in order
        """
        results: list[str] = []
        for definition, task_text in tasks:
            full_task = task_text
            if pass_results and results:
                full_task = f"{task_text}\n\nPrevious result:\n{results[-1]}"

            agent_id = await self.spawn(definition, full_task, wait=True)
            result = self._results.get(agent_id, "")
            results.append(result)

        return results

    # -------------------------------------------------------------------
    # Worker agent management (Pattern 9)
    # -------------------------------------------------------------------

    def spawn_worker(self, config: WorkerConfig) -> str:
        """Spawn a background worker agent.

        The worker runs autonomously with its own budget constraints.
        Use start_worker() to begin execution and wait_worker() to
        collect results.

        Args:
            config: Worker configuration

        Returns:
            Worker ID for later reference
        """
        worker_id = uuid.uuid4().hex[:8]
        worker = WorkerAgent(
            worker_id=worker_id,
            config=config,
            provider=self._provider,
            kernel=self._kernel,
            registry=self._registry,
        )
        self._workers[worker_id] = worker
        logger.info("Spawned worker %s for task: %s", worker_id, config.task[:100])
        return worker_id

    async def start_worker(self, worker_id: str) -> None:
        """Start a previously spawned worker."""
        worker = self._workers.get(worker_id)
        if worker is None:
            raise KeyError(f"Worker {worker_id} not found")
        await worker.start()

    async def wait_worker(
        self, worker_id: str, timeout: float | None = None
    ) -> str | None:
        """Wait for a worker to complete and return its result.

        Args:
            worker_id: The worker ID returned by spawn_worker()
            timeout: Maximum seconds to wait

        Returns:
            The worker's result text
        """
        worker = self._workers.get(worker_id)
        if worker is None:
            return None
        return await worker.wait(timeout=timeout)

    def stop_worker(self, worker_id: str) -> None:
        """Cancel a running worker."""
        worker = self._workers.get(worker_id)
        if worker:
            worker.cancel()

    def list_workers(self) -> list[dict[str, Any]]:
        """List all workers and their status."""
        return [
            {
                "id": w.worker_id,
                "status": w.status,
                "task": w.config.task[:100],
            }
            for w in self._workers.values()
        ]
