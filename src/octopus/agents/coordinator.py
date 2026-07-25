"""Agent coordinator — orchestrates multiple agents for complex tasks."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from octopus.agents.base import AgentDefinition
from octopus.agents.llm_agent import LLMAgent
from octopus.core.kernel import Kernel
from octopus.providers.base import Provider
from octopus.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """Orchestrates multiple agents for complex multi-step tasks.

    Supports:
    - Spawning agents with specific definitions
    - Running agents in parallel or sequentially
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
        self._parent_session_id = parent_session_id or f"coordinator-{uuid.uuid4().hex[:8]}"
        self._agents: dict[str, LLMAgent] = {}
        self._tasks: dict[str, asyncio.Task[str]] = {}
        self._results: dict[str, str] = {}

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
        """Stop all running agents."""
        for agent_id in list(self._agents.keys()):
            await self.stop(agent_id)

    def list_agents(self) -> list[dict[str, Any]]:
        """List all agents and their status."""
        result = []
        for agent_id, agent in self._agents.items():
            task = self._tasks.get(agent_id)
            status = "completed" if agent_id in self._results else "running"
            if task and task.done() and agent_id not in self._results:
                status = "completed"
            result.append({
                "id": agent_id,
                "name": agent.name,
                "status": status,
            })
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
