"""Octopus Agent Bridge — GUI-CLI IPC."""

from .protocol import IPCMessage, MessageType
from .server import BridgeServer, create_bridge_server

__all__ = [
    "BridgeServer",
    "create_bridge_server",
    "IPCMessage",
    "MessageType",
]
