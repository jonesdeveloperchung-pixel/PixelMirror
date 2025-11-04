from abc import ABC, abstractmethod
import asyncio
from typing import Set, Callable, Optional

import websockets

from .debug import Debug

class NetworkManager(ABC):
    """An interface for managing network connections."""

    @abstractmethod
    async def start(self):
        """Start the network manager."""
        pass

    @abstractmethod
    async def stop(self):
        """Stop the network manager."""
        pass

    @abstractmethod
    async def send(self, data: bytes):
        """Send data over the network."""
        pass

class ServerNetworkManager(NetworkManager):
    """A class for managing a WebSocket server."""

    def __init__(self, host: str, port: int, debug: Debug = Debug()):
        self._host = host
        self._port = port
        self._server = None
        self._clients: Set[websockets.WebSocketServerProtocol] = set()
        self._debug = debug

    async def _handler(self, websocket: websockets.WebSocketServerProtocol):
        self._clients.add(websocket)
        self._debug.log("ServerNetworkManager", f"Client connected: {websocket.remote_address}")
        try:
            await websocket.wait_closed()
        finally:
            self._clients.remove(websocket)
            self._debug.log("ServerNetworkManager", f"Client disconnected: {websocket.remote_address}")

    async def start(self):
        self._server = await websockets.serve(self._handler, self._host, self._port)
        self._debug.log("ServerNetworkManager", f"Server started at {self._host}:{self._port}")

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._debug.log("ServerNetworkManager", "Server stopped")

    async def send(self, data: bytes):
        if self._clients:
            self._debug.log("ServerNetworkManager", f"Sending data to {len(self._clients)} clients")
            tasks = [asyncio.create_task(client.send(data)) for client in self._clients]
            await asyncio.wait(tasks)

class ClientNetworkManager(NetworkManager):
    """A class for managing a WebSocket client."""

    def __init__(self, host: str, port: int, on_receive: Callable[[bytes], None], 
                 on_status_update: Callable[[str], None], on_latency_update: Callable[[float], None], debug: Debug = Debug()):
        self._host = host
        self._port = port
        self._on_receive = on_receive
        self._on_status_update = on_status_update
        self._on_latency_update = on_latency_update
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._debug = debug

    async def start(self):
        try:
            self._on_status_update("Connecting...")
            self._websocket = await websockets.connect(f"ws://{self._host}:{self._port}")
            self._debug.log("ClientNetworkManager", f"Connected to server at {self._host}:{self._port}")
            self._on_status_update("Connected")
            asyncio.create_task(self._receive_loop())
        except Exception as e:
            self._debug.log("ClientNetworkManager", f"Connection failed: {e}")
            self._on_status_update(f"Connection Failed: {e}")

    async def stop(self):
        if self._websocket:
            await self._websocket.close()
            self._debug.log("ClientNetworkManager", "Connection closed")
            self._on_status_update("Disconnected")

    async def send(self, data: bytes):
        if self._websocket:
            await self._websocket.send(data)
            self._debug.log("ClientNetworkManager", f"Sent data of size {len(data)}")

    async def _receive_loop(self):
        while True:
            try:
                message = await self._websocket.recv()
                if isinstance(message, bytes):
                    self._debug.log("ClientNetworkManager", f"Received data of size {len(message)}")
                    # Placeholder for latency calculation. This would typically involve
                    # sending a timestamp from client to server and back.
                    # For now, we'll just update with a dummy value or based on actual RTT if implemented.
                    # self._on_latency_update(some_calculated_latency)
                    self._on_receive(message)
            except websockets.exceptions.ConnectionClosedOK:
                self._debug.log("ClientNetworkManager", "Connection closed gracefully.")
                self._on_status_update("Disconnected")
                break
            except Exception as e:
                self._debug.log("ClientNetworkManager", f"Error in receive loop: {e}")
                self._on_status_update(f"Error: {e}")
                break
