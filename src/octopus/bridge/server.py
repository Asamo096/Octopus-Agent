"""IPC server — WebSocket server for GUI-CLI communication.

The Python backend starts a WebSocket server that the Tauri frontend
connects to. Messages are JSON-encoded IPCMessage objects.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from octopus.bridge.protocol import IPCMessage, MessageType

logger = logging.getLogger(__name__)

# Type alias for message handlers
Handler = Callable[[IPCMessage], Coroutine[Any, Any, IPCMessage | None]]


class BridgeServer:
    """WebSocket server for GUI-CLI IPC."""

    def __init__(self) -> None:
        self._clients: set[Any] = set()
        self._handlers: dict[MessageType, Handler] = {}
        self._port: int = 0
        self._server: Any = None

    def on(self, type: MessageType, handler: Handler) -> None:
        """Register a handler for a message type."""
        self._handlers[type] = handler

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        """Start the WebSocket server. Returns the port number."""
        try:
            import websockets.server

            self._server = await websockets.server.serve(  # type: ignore[attr-defined]
                self._handle_connection,
                host,
                port,
            )
            self._port = self._server.sockets[0].getsockname()[1]

            # Write port to well-known file for the GUI to find
            port_file = Path.home() / ".octopus" / "port"
            port_file.parent.mkdir(parents=True, exist_ok=True)
            port_file.write_text(str(self._port))

            logger.info("Bridge server started on %s:%d", host, self._port)
            return self._port

        except ImportError:
            logger.warning("websockets not installed, bridge server disabled")
            return 0

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Remove port file
        port_file = Path.home() / ".octopus" / "port"
        if port_file.exists():
            port_file.unlink()

        logger.info("Bridge server stopped")

    async def broadcast(self, message: IPCMessage) -> None:
        """Send a message to all connected clients."""
        if not self._clients:
            return

        data = json.dumps(message.to_dict())
        disconnected = set()
        for client in self._clients:
            try:
                await client.send(data)
            except Exception:
                disconnected.add(client)

        self._clients -= disconnected

    async def _handle_connection(self, websocket: Any) -> None:
        """Handle a new WebSocket connection."""
        self._clients.add(websocket)
        logger.info("Client connected (%d total)", len(self._clients))

        try:
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                    message = IPCMessage.from_dict(data)
                    await self._dispatch(message)
                except Exception as e:
                    logger.error("Error handling message: %s", e)
                    error_msg = IPCMessage(
                        id=str(uuid.uuid4()),
                        type=MessageType.ERROR,
                        payload={"error": str(e)},
                    )
                    await websocket.send(json.dumps(error_msg.to_dict()))
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info("Client disconnected (%d remaining)", len(self._clients))

    async def _dispatch(self, message: IPCMessage) -> None:
        """Dispatch a message to the registered handler."""
        handler = self._handlers.get(message.type)
        if handler:
            response = await handler(message)
            if response:
                await self.broadcast(response)
        else:
            logger.warning("No handler for message type: %s", message.type)


def create_bridge_server() -> BridgeServer:
    """Create a bridge server with default handlers."""
    server = BridgeServer()

    # Default status handler
    async def handle_status(msg: IPCMessage) -> IPCMessage | None:
        return IPCMessage(
            id=msg.id,
            type=MessageType.STATUS,
            payload={"status": "ok", "version": "0.1.0"},
        )

    server.on(MessageType.STATUS, handle_status)
    return server
