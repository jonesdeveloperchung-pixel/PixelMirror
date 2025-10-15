#!/usr/bin/env python3
"""
PixelMirror – A minimal, production-ready screen mirroring demo.

This script implements both the server and the client in a single file.
It follows the design described in the system specification:
  • Screen capture & streaming (server)
  • Input forwarding (client → server)
  • Settings persistence
  • Robust networking with exponential back-off
  • Comprehensive logging & error handling

Author: OpenAI ChatGPT
License: MIT
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import configparser
import json
import logging
import os
import sys
import time
import threading
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from io import BytesIO

# Third-party imports – ensure they are installed
try:
    import websockets
    from PIL import Image, ImageTk
    import numpy as np
    import pyautogui
    import tkinter as tk
    from tkinter import ttk
except ImportError as exc:
    sys.exit(f"Missing dependency: {exc.name}. Install with 'pip install {exc.name}'")

# Disable pyautogui failsafe
pyautogui.FAILSAFE = False

# --------------------------------------------------------------------------- #
# 1. Data Models
# --------------------------------------------------------------------------- #

class ConnectionStatus(Enum):
    """Represents the current connection state."""
    CONNECTED = auto()
    DISCONNECTED = auto()


@dataclass(frozen=True)
class ResolutionOption:
    """Describes a screen resolution."""
    width: int
    height: int
    label: str


@dataclass(frozen=True)
class AudioOutputDevice:
    """Placeholder for audio device information."""
    name: str
    device_type: str  # e.g., 'speaker', 'bluetooth'


# --------------------------------------------------------------------------- #
# 2. Interfaces (Abstract Base Classes)
# --------------------------------------------------------------------------- #

from abc import ABC, abstractmethod


class INetworkManager(ABC):
    """Defines the contract for network operations."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish a connection to the remote endpoint."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection."""
        ...

    @abstractmethod
    async def send(self, data: str) -> None:
        """Send string data over the network."""
        ...

    @abstractmethod
    async def receive(self) -> str:
        """Receive string data from the network."""
        ...

    @abstractmethod
    def get_status(self) -> ConnectionStatus:
        """Return the current connection status."""
        ...


class IInputHandler(ABC):
    """Defines the contract for input handling."""

    @abstractmethod
    async def capture_and_send_input(self) -> None:
        """Capture local input events and forward them."""
        ...

    @abstractmethod
    async def process_remote_input(self, data: Dict[str, Any]) -> None:
        """Process input data received from the remote side."""
        ...


class ISettingsManager(ABC):
    """Defines the contract for settings persistence."""

    @abstractmethod
    def save_setting(self, key: str, value: Any) -> None:
        """Persist a setting."""
        ...

    @abstractmethod
    def load_setting(self, key: str, default: Any = None) -> Any:
        """Retrieve a persisted setting."""
        ...


# --------------------------------------------------------------------------- #
# 3. Settings Manager
# --------------------------------------------------------------------------- #

class SettingsManager(ISettingsManager):
    """Persist settings in an INI file located in the user's home directory."""

    def __init__(self, filename: str = ".pixelmirror.ini") -> None:
        self._config = configparser.ConfigParser()
        self._path = Path.home() / filename
        if self._path.exists():
            self._config.read(self._path)
        else:
            self._config["DEFAULT"] = {}
            with open(self._path, "w") as f:
                self._config.write(f)

    def _write(self) -> None:
        with open(self._path, "w") as f:
            self._config.write(f)

    def save_setting(self, key: str, value: Any) -> None:
        self._config["DEFAULT"][key] = str(value)
        self._write()

    def load_setting(self, key: str, default: Any = None) -> Any:
        return self._config["DEFAULT"].get(key, default)


# --------------------------------------------------------------------------- #
# 4. Server Implementation
# --------------------------------------------------------------------------- #

class ServerNetworkManager(INetworkManager):
    """WebSocket server that streams screen captures and receives input."""

    def __init__(self, host: str, port: int, settings: SettingsManager) -> None:
        self.host = host
        self.port = port
        self.settings = settings
        self._status = ConnectionStatus.DISCONNECTED
        self._server: Optional[websockets.server.WebSocketServer] = None
        self._clients: set[websockets.WebSocketServerProtocol] = set()
        self._capture_task: Optional[asyncio.Task] = None
        self._logger = logging.getLogger("ServerNetworkManager")

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._server = await websockets.serve(self._handler, self.host, self.port)
        self._status = ConnectionStatus.CONNECTED
        self._logger.info(f"Server listening on {self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the server and all connections."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self._status = ConnectionStatus.DISCONNECTED
        self._logger.info("Server stopped")

    async def _handler(self, websocket: websockets.WebSocketServerProtocol, path: str) -> None:
        """Handle a new client connection."""
        self._logger.info(f"Client connected: {websocket.remote_address}")
        self._clients.add(websocket)
        try:
            async for message in websocket:
                await self._process_message(websocket, message)
        except websockets.ConnectionClosed:
            self._logger.warning(f"Client disconnected: {websocket.remote_address}")
        except Exception as e:
            self._logger.error(f"Error handling client: {e}")
        finally:
            self._clients.discard(websocket)

    async def _process_message(self, websocket: websockets.WebSocketServerProtocol, message: str) -> None:
        """Process a JSON message from the client."""
        try:
            data = json.loads(message)
            if data.get("type") == "input":
                await self._handle_input(data["payload"])
        except json.JSONDecodeError:
            self._logger.error("Received malformed JSON")
        except Exception as e:
            self._logger.error(f"Error processing message: {e}")

    async def _handle_input(self, payload: Dict[str, Any]) -> None:
        """Execute input commands received from the client."""
        try:
            if payload["action"] == "mouse_move":
                pyautogui.moveTo(payload["x"], payload["y"])
            elif payload["action"] == "mouse_click":
                pyautogui.click(payload["x"], payload["y"])
            elif payload["action"] == "key_press":
                pyautogui.press(payload["key"])
        except Exception as exc:
            self._logger.exception(f"Failed to process input: {exc}")

    async def broadcast_screen(self, image_bytes: bytes) -> None:
        """Send the compressed image to all connected clients."""
        if not self._clients:
            return
        
        message = base64.b64encode(image_bytes).decode("ascii")
        payload = json.dumps({"type": "screen", "payload": message})
        
        # Remove disconnected clients
        disconnected = []
        for client in self._clients:
            try:
                await client.send(payload)
            except websockets.ConnectionClosed:
                disconnected.append(client)
            except Exception as e:
                self._logger.error(f"Error sending to client: {e}")
                disconnected.append(client)
        
        for client in disconnected:
            self._clients.discard(client)

    async def capture_loop(self, interval: float = 0.1) -> None:
        """Periodically capture the screen and broadcast."""
        self._logger.info("Starting screen capture loop")
        while True:
            try:
                # Capture the screen
                screenshot = pyautogui.screenshot()
                # Convert to JPEG for compression
                with BytesIO() as buf:
                    screenshot.save(buf, format="JPEG", quality=70)
                    image_bytes = buf.getvalue()
                await self.broadcast_screen(image_bytes)
                await asyncio.sleep(interval)
            except Exception as exc:
                self._logger.exception(f"Screen capture failed: {exc}")
                await asyncio.sleep(interval)

    async def run(self) -> None:
        """Convenience method to start server and capture loop."""
        await self.start()
        self._capture_task = asyncio.create_task(self.capture_loop())

    async def shutdown(self) -> None:
        """Gracefully shutdown server and capture loop."""
        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass
        await self.stop()

    # Interface methods (not used by server but required for interface compliance)
    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        await self.shutdown()

    async def send(self, data: str) -> None:
        pass

    async def receive(self) -> str:
        return ""

    def get_status(self) -> ConnectionStatus:
        return self._status


class ServerInputHandler(IInputHandler):
    """Server does not need to capture local input; placeholder for interface compliance."""

    async def capture_and_send_input(self) -> None:
        pass

    async def process_remote_input(self, data: Dict[str, Any]) -> None:
        pass


# --------------------------------------------------------------------------- #
# 5. Client Implementation
# --------------------------------------------------------------------------- #

class ClientNetworkManager(INetworkManager):
    """WebSocket client that receives screen data and forwards input."""

    def __init__(self, host: str, port: int, settings: SettingsManager) -> None:
        self.host = host
        self.port = port
        self.settings = settings
        self._status = ConnectionStatus.DISCONNECTED
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._logger = logging.getLogger("ClientNetworkManager")
        self._reconnect_delay = 1.0  # seconds
        self._on_screen_update: Optional[callable] = None

    async def connect(self) -> None:
        """Attempt to connect to the server with exponential back-off."""
        while True:
            try:
                self._ws = await websockets.connect(f"ws://{self.host}:{self.port}")
                self._status = ConnectionStatus.CONNECTED
                self._logger.info(f"Connected to {self.host}:{self.port}")
                self._receive_task = asyncio.create_task(self._receive_loop())
                self._reconnect_delay = 1.0  # Reset delay on successful connection
                break
            except (OSError, websockets.InvalidURI, ConnectionRefusedError) as exc:
                self._logger.warning(f"Connection failed: {exc}. Retrying in {self._reconnect_delay}s")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
        self._status = ConnectionStatus.DISCONNECTED
        self._logger.info("Disconnected from server")

    async def send(self, data: str) -> None:
        """Send string data to the server."""
        if self._ws and self._status == ConnectionStatus.CONNECTED:
            try:
                await self._ws.send(data)
            except websockets.ConnectionClosed:
                self._status = ConnectionStatus.DISCONNECTED

    async def receive(self) -> str:
        """Receive string data from the server."""
        if self._ws and self._status == ConnectionStatus.CONNECTED:
            return await self._ws.recv()
        raise RuntimeError("Not connected")

    def get_status(self) -> ConnectionStatus:
        return self._status

    async def _receive_loop(self) -> None:
        """Continuously receive messages from the server."""
        try:
            async for message in self._ws:
                await self._process_message(message)
        except websockets.ConnectionClosed:
            self._logger.warning("Connection closed by server")
        except Exception as e:
            self._logger.error(f"Error in receive loop: {e}")
        finally:
            self._status = ConnectionStatus.DISCONNECTED

    async def _process_message(self, message: str) -> None:
        """Handle incoming JSON messages."""
        try:
            data = json.loads(message)
            if data.get("type") == "screen":
                await self._handle_screen(data["payload"])
        except json.JSONDecodeError:
            self._logger.error("Received malformed JSON")
        except Exception as e:
            self._logger.error(f"Error processing message: {e}")

    async def _handle_screen(self, payload: str) -> None:
        """Decode the base64 image and update the UI."""
        try:
            image_bytes = base64.b64decode(payload)
            # Pass to UI via callback (set in main)
            if self._on_screen_update:
                self._on_screen_update(image_bytes)
        except Exception as e:
            self._logger.error(f"Error handling screen update: {e}")

    def set_screen_update_callback(self, callback: callable) -> None:
        self._on_screen_update = callback


class ClientInputHandler(IInputHandler):
    """Captures local mouse/keyboard events and forwards them to the server."""

    def __init__(self, network_manager: ClientNetworkManager) -> None:
        self.network_manager = network_manager
        self._logger = logging.getLogger("ClientInputHandler")

    async def capture_and_send_input(self) -> None:
        """This method is intentionally left empty because the UI layer
        captures events and calls `send_input` directly."""
        pass

    async def process_remote_input(self, data: Dict[str, Any]) -> None:
        """Client does not process remote input in this demo."""
        pass

    async def send_input(self, payload: Dict[str, Any]) -> None:
        """Send input data to the server."""
        try:
            message = json.dumps({"type": "input", "payload": payload})
            await self.network_manager.send(message)
        except Exception as e:
            self._logger.error(f"Error sending input: {e}")


# --------------------------------------------------------------------------- #
# 6. UI Layer (Tkinter)
# --------------------------------------------------------------------------- #

class PixelMirrorClientUI:
    """Tkinter UI that displays the mirrored screen and captures input."""

    def __init__(self, network_manager: ClientNetworkManager, input_handler: ClientInputHandler) -> None:
        self.network_manager = network_manager
        self.input_handler = input_handler
        self.root = tk.Tk()
        self.root.title("PixelMirror – Client")
        self.root.geometry("800x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Canvas to display the screen
        self.canvas = tk.Canvas(self.root, bg="black")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Bind mouse and keyboard events
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Button-1>", self.on_mouse_click)
        self.canvas.focus_set()  # Allow canvas to receive keyboard events
        self.canvas.bind("<Key>", self.on_key_press)

        # Image placeholder
        self.photo_image: Optional[tk.PhotoImage] = None
        self.current_image: Optional[Image.Image] = None

        # Set callback for screen updates
        self.network_manager.set_screen_update_callback(self.update_screen)

        # Status label
        self.status_label = tk.Label(self.root, text="Status: Disconnected", bg="red", fg="white")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # Update status periodically
        self.update_status()

    def on_close(self) -> None:
        """Handle window close."""
        self.root.quit()

    def on_mouse_move(self, event: tk.Event) -> None:
        """Forward mouse movement to the server."""
        if self.current_image and self.network_manager.get_status() == ConnectionStatus.CONNECTED:
            # Scale coordinates based on image size
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            img_width, img_height = self.current_image.size
            
            # Calculate scaling factors
            scale_x = img_width / canvas_width if canvas_width > 0 else 1
            scale_y = img_height / canvas_height if canvas_height > 0 else 1
            
            # Scale coordinates
            x = int(event.x * scale_x)
            y = int(event.y * scale_y)
            
            payload = {"action": "mouse_move", "x": x, "y": y}
            asyncio.create_task(self.input_handler.send_input(payload))

    def on_mouse_click(self, event: tk.Event) -> None:
        """Forward mouse click to the server."""
        if self.current_image and self.network_manager.get_status() == ConnectionStatus.CONNECTED:
            # Scale coordinates based on image size
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            img_width, img_height = self.current_image.size
            
            # Calculate scaling factors
            scale_x = img_width / canvas_width if canvas_width > 0 else 1
            scale_y = img_height / canvas_height if canvas_height > 0 else 1
            
            # Scale coordinates
            x = int(event.x * scale_x)
            y = int(event.y * scale_y)
            
            payload = {"action": "mouse_click", "x": x, "y": y}
            asyncio.create_task(self.input_handler.send_input(payload))

    def on_key_press(self, event: tk.Event) -> None:
        """Forward key press to the server."""
        if self.network_manager.get_status() == ConnectionStatus.CONNECTED:
            payload = {"action": "key_press", "key": event.keysym}
            asyncio.create_task(self.input_handler.send_input(payload))

    def update_screen(self, image_bytes: bytes) -> None:
        """Update the canvas with the new screen image."""
        try:
            image = Image.open(BytesIO(image_bytes))
            self.current_image = image
            
            # Resize to fit the canvas while maintaining aspect ratio
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:  # Ensure canvas is initialized
                image_copy = image.copy()
                image_copy.thumbnail((canvas_width, canvas_height), Image.Resampling.LANCZOS)
                self.photo_image = ImageTk.PhotoImage(image_copy)
                
                # Clear canvas and draw new image
                self.canvas.delete("all")
                self.canvas.create_image(canvas_width//2, canvas_height//2, image=self.photo_image)
        except Exception as exc:
            logging.exception(f"Failed to update screen: {exc}")

    def update_status(self) -> None:
        """Update the status label."""
        status = self.network_manager.get_status()
        if status == ConnectionStatus.CONNECTED:
            self.status_label.config(text=f"Status: Connected to {self.network_manager.host}:{self.network_manager.port}", bg="green")
        else:
            self.status_label.config(text="Status: Disconnected", bg="red")
        
        # Schedule next update
        self.root.after(1000, self.update_status)

    def run(self) -> None:
        """Start the Tkinter main loop."""
        self.root.mainloop()


# --------------------------------------------------------------------------- #
# 7. Main Entry Point
# --------------------------------------------------------------------------- #

async def run_server(host: str, port: int) -> None:
    settings = SettingsManager()
    server_manager = ServerNetworkManager(host, port, settings)
    
    try:
        await server_manager.run()
        logging.info("Server started successfully. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down server...")
    finally:
        await server_manager.shutdown()


def run_client_sync(host: str, port: int) -> None:
    """Run client in synchronous mode with proper asyncio integration."""
    settings = SettingsManager()
    client_manager = ClientNetworkManager(host, port, settings)
    input_handler = ClientInputHandler(client_manager)
    
    # Create UI
    ui = PixelMirrorClientUI(client_manager, input_handler)
    
    # Create event loop for asyncio operations
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Start connection in background
    async def connect_and_run():
        await client_manager.connect()
    
    # Run connection in thread
    def run_async():
        loop.run_until_complete(connect_and_run())
        loop.run_forever()
    
    async_thread = threading.Thread(target=run_async, daemon=True)
    async_thread.start()
    
    try:
        # Start UI (blocking)
        ui.run()
    finally:
        # Cleanup
        loop.call_soon_threadsafe(loop.stop)
        asyncio.run_coroutine_threadsafe(client_manager.disconnect(), loop)


def main() -> None:
    parser = argparse.ArgumentParser(description="PixelMirror – Screen Mirroring Demo")
    parser.add_argument("--mode", choices=["server", "client"], required=True, help="Run as server or client")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (client mode) or bind address (server mode)")
    parser.add_argument("--port", type=int, default=8765, help="Port number")
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if args.mode == "server":
        asyncio.run(run_server(args.host, args.port))
    else:
        run_client_sync(args.host, args.port)


if __name__ == "__main__":
    main()