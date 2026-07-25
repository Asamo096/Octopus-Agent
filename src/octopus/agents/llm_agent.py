"""LLM-backed agent — runs an autonomous agent loop for a given task."""

from __future__ import annotations

import logging
import uuid

from octopus.agents.base import AgentDefinition
from octopus.core.kernel import Context, Kernel
from octopus.loop.engine import run_query
from octopus.loop.models import Message, Role, StreamEventType
from octopus.providers.base import Provider
from octopus.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


class LLMAgent:
    """An LLM-backed agent that runs autonomously on a task.

    Usage:
        agent = LLMAgent(definition, kernel, provider, registry)
        result = await agent.run("Fix the bug in main.py")
    """

    def __init__(
        self,
        definition: AgentDefinition,
        kernel: Kernel,
        provider: Provider,
        registry: ToolRegistry,
        *,
        parent_session_id: str | None = None,
    ) -> None:
        self.definition = definition
        self.name = definition.name
        self._kernel = kernel
        self._provider = provider
        self._registry = registry
        self._session_id = f"agent-{definition.name}-{uuid.uuid4().hex[:8]}"
        self._parent_session_id = parent_session_id
        self._stopped = False

    async def run(self, task: str) -> str:
        """Execute the agent on a task. Returns the final text response."""
        self._stopped = False

        # Build system prompt from definition
        system_prompt = self.definition.system_prompt or (
            f"You are {self.definition.name}: {self.definition.description}\n"
            f"Complete the following task. Be thorough and precise."
        )

        # Create context for this agent
        ctx = Context(
            session_id=self._session_id,
            kernel=self._kernel,
            workspace=self._kernel.workspace,
            permission_mode=self._kernel.permission_mode,
            metadata={
                "agent_name": self.name,
                "parent_session": self._parent_session_id,
            },
        )

        messages: list[Message] = [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=task),
        ]

        collected: list[str] = []
        try:
            async for event in run_query(
                messages,
                self._provider,
                self._kernel,
                self._registry,
                ctx,
                model=self.definition.model or "claude-sonnet-4-20250514",
                max_turns=self.definition.max_turns,
            ):
                if self._stopped:
                    break
                if event.type == StreamEventType.TEXT:
                    collected.append(event.text or "")
                elif event.type == StreamEventType.ERROR:
                    logger.error("Agent %s error: %s", self.name, event.error)
                    collected.append(f"[Error: {event.error}]")
        except Exception as e:
            logger.error("Agent %s failed: %s", self.name, e)
            return f"Agent failed: {e}"

        return "".join(collected)

    async def stop(self) -> None:
        """Signal the agent to stop."""
        self._stopped = True
        logger.info("Agent %s stopped", self.name)
