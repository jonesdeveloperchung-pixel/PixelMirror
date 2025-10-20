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

Author: Jones Chung
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
import struct
import hashlib
import mss

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

# Constants for tile-based mirroring
TILE_SIZE = 64
FALLBACK_THRESHOLD = 0.7 # If more than 70% tiles change, send full frame

# --------------------------------------------------------------------------- #
# 1. Data Models
# --------------------------------------------------------------------------- #

class ConnectionStatus(Enum):
    """Represents the current connection state of the WebSocket."""
    CONNECTED = auto()
    DISCONNECTED = auto()


@dataclass(frozen=True)
class ResolutionOption:
    """Describes a screen resolution with width, height, and a descriptive label."""
    width: int
    height: int
    label: str


@dataclass(frozen=True)
class AudioOutputDevice:
    """Placeholder for audio device information. Not fully implemented in this demo."""
    name: str
    device_type: str


# --------------------------------------------------------------------------- #
# 2. Interfaces (Abstract Base Classes)
# --------------------------------------------------------------------------- #

from abc import ABC, abstractmethod


class INetworkManager(ABC):
    """Defines the contract for network operations (connect, disconnect, send, receive, get_status)."""

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
    """Defines the contract for input handling (capturing local input, processing remote input)."""

    @abstractmethod
    async def capture_and_send_input(self) -> None:
        """Capture local input events and forward them."""
        ...

    @abstractmethod
    async def process_remote_input(self, data: Dict[str, Any]) -> None:
        """Process input data received from the remote side."""
        ...


class ISettingsManager(ABC):
    """Defines the contract for settings persistence (saving and loading settings)."""

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

    def __init__(self, filename: str = ".pixelmirror.ini") -> None:
        """Initializes the SettingsManager, loading settings from the specified INI file."""
        self._config = configparser.ConfigParser()
        self._path = Path.home() / filename
        if self._path.exists():
            self._config.read(self._path)
        else:
            self._config["DEFAULT"] = {}
            with open(self._path, "w") as f:
                self._config.write(f)

    def _write(self) -> None:
        """Internal helper to write the current settings to the file."""
        with open(self._path, "w") as f:
            self._config.write(f)

    def save_setting(self, key: str, value: Any) -> None:
        """Saves a specific setting (key-value pair) to the configuration."""
        self._config["DEFAULT"][key] = str(value)
        self._write()

    def load_setting(self, key: str, default: Any = None) -> Any:
        """Loads a setting by its key. Returns a default value if the key is not found."""
        return self._config["DEFAULT"].get(key, default)


# --------------------------------------------------------------------------- #
# 4. Server Implementation
# --------------------------------------------------------------------------- #

class ServerNetworkManager(INetworkManager):

    def __init__(self, host: str, port: int, settings: SettingsManager, input_handler: ServerInputHandler, monitor_id: int = 0, tile_size: int = 64, fallback_threshold: float = 0.7, capture_interval: float = 0.1, webp_quality: int = 80, jpeg_quality: int = 70) -> None:
        """Initializes the ServerNetworkManager with network settings and screen capture parameters."""
        self.host = host
        self.port = port
        self.settings = settings
        self.input_handler = input_handler # Store the input handler
        self._status = ConnectionStatus.DISCONNECTED
        self._server: Optional[websockets.server.WebSocketServer] = None
        self._clients: set[websockets.WebSocketServerProtocol] = set()
        self._capture_task: Optional[asyncio.Task] = None
        self._logger = logging.getLogger("ServerNetworkManager")
        self._prev_tile_hashes: Dict[Tuple[int, int], bytes] = {}
        self._frame_id = 0
        self._monitor_id = monitor_id # Use the monitor_id passed as an argument
        self._tile_size = tile_size # Store configurable tile size
        self._fallback_threshold = fallback_threshold # Store configurable fallback threshold
        self._capture_interval = capture_interval # Store configurable capture interval
        self._webp_quality = webp_quality # Store configurable WebP quality
        self._jpeg_quality = jpeg_quality # Store configurable JPEG quality
        self._sct = mss.mss() # Initialize mss for screen capture
        self._screen_width, self._screen_height = self._get_screen_resolution() # Initialize screen dimensions for the selected monitor
        self._list_monitors() # Log available monitors for user information

    def _get_screen_resolution(self) -> Tuple[int, int]:
        """Retrieves the width and height of the selected monitor using the `mss` library."""
        # mss.monitors[0] is a dictionary of all monitors
        # mss.monitors[1] is the primary monitor, [2] is the second, etc.
        # We use self._monitor_id to select the desired monitor.
        monitor = self._sct.monitors[self._monitor_id]
        return monitor['width'], monitor['height']

    def _list_monitors(self) -> None:
        """Logs information about all available monitors detected by `mss`. This helps users
        identify the correct monitor ID to use for screen capturing."""
        self._logger.info("Available monitors:")
        for i, monitor in enumerate(self._sct.monitors):
            if i == 0: # mss.monitors[0] is a dictionary of all monitors, not a specific one
                self._logger.info(f"  Monitor {i}: All monitors (virtual screen)")
            else:
                self._logger.info(f"  Monitor {i}: x={monitor['left']}, y={monitor['top']}, width={monitor['width']}, height={monitor['height']}")

    async def start(self) -> None:
        """Starts the WebSocket server, making it ready to accept client connections."""
        self._server = await websockets.serve(self._handler, self.host, self.port)
        self._status = ConnectionStatus.CONNECTED
        self._logger.info(f"Server listening on {self.host}:{self.port}")

    def _partition_screen(self, image: Image.Image) -> list[tuple[int, int, Image.Image]]:
        """Splits a given screen image into smaller tiles based on `self._tile_size`.
        This is crucial for sending only changed regions (delta updates)."""
        tiles = []
        img_width, img_height = image.size
        
        for y in range(0, img_height, self._tile_size):
            for x in range(0, img_width, self._tile_size):
                # Calculate tile dimensions, handling partial tiles at edges
                tile_w = min(self._tile_size, img_width - x)
                tile_h = min(self._tile_size, img_height - y)
                
                # Crop the tile
                tile_img = image.crop((x, y, x + tile_w, y + tile_h))
                tiles.append(((x // self._tile_size), (y // self._tile_size), tile_img))
        return tiles

    def _hash_tile(self, tile_image: Image.Image) -> bytes:
        """Computes a SHA1 hash of the tile's pixel data. This hash is used to quickly
        determine if a tile has changed since the last frame."""
        # Convert to bytes and hash. Using 'tobytes()' is efficient.
        return hashlib.sha1(tile_image.tobytes()).digest()

    def _compress_tile(self, tile_image: Image.Image) -> bytes:
        """Compresses a single tile image into WebP format. WebP is chosen for its
        good compression ratio and quality for small image regions."""
        with BytesIO() as buf:
            # Use WebP for better compression on small, lossless-like tiles
            tile_image.save(buf, format="WEBP", quality=self._webp_quality) # Quality can be adjusted
            return buf.getvalue()

    def _pack_delta_payload(self, frame_id: int, changed_tiles: list[tuple[int, int, Image.Image, bytes]], full_frame_image_bytes: Optional[bytes] = None) -> bytes:
        """Packs the frame data (either a full frame or changed tiles) into a binary payload
        for efficient transmission over the WebSocket."""
        if full_frame_image_bytes:
            # Full frame fallback: type (1 byte), frame_id (4 bytes), image_data
            # Type 0x01 indicates a full frame
            header = struct.pack('>BI', 0x01, frame_id)
            self._logger.debug(f"Server packing full frame: ID={frame_id}, size={len(full_frame_image_bytes)} bytes.")
            return header + full_frame_image_bytes
        
        # Delta frame: type (1 byte), frame_id (4 bytes), n_tiles (2 bytes)
        # Type 0x00 indicates a delta frame
        n_tiles = len(changed_tiles)
        # Pack type, frame_id, and n_tiles in one go
        header_bytes = struct.pack('>BIH', 0x00, frame_id, n_tiles)
        self._logger.debug(f"Server: header_bytes packed: {header_bytes.hex()}")
        
        # Build payload as a list of byte chunks
        payload_chunks = [header_bytes]
        self._logger.debug(f"Server: Initial payload chunks: {[c.hex() for c in payload_chunks]}")

        for x_idx, y_idx, tile_img, compressed_data in changed_tiles:
            tile_w, tile_h = tile_img.size
            # Per-tile header: x_tile (2B), y_tile (2B), tile_w (2B), tile_h (2B), data_len (4B)
            data_len = len(compressed_data)
            tile_header = struct.pack('>HHHH I', x_idx, y_idx, tile_w, tile_h, data_len)
            self._logger.debug(f"Server packing tile header: x={x_idx}, y={y_idx}, w={tile_w}, h={tile_h}, data_len={data_len}. Raw header: {tile_header.hex()}")
            payload_chunks.append(tile_header)
            payload_chunks.append(compressed_data)
        
        full_payload_bytes = b''.join(payload_chunks)
        self._logger.debug(f"Server packing delta frame: ID={frame_id}, n_tiles={n_tiles}. Raw header: {header_bytes.hex()}. Full payload (first 20 bytes): {full_payload_bytes[:20].hex()}")
        return full_payload_bytes
        
        return payload.getvalue()

    async def stop(self) -> None:
        """Stops the WebSocket server and closes all client connections gracefully."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self._status = ConnectionStatus.DISCONNECTED
        self._logger.info("Server stopped")

    async def _handler(self, websocket: websockets.WebSocketServerProtocol, path: str) -> None:
        """Handles a new incoming WebSocket client connection. This method is called for each new client."""
        self._logger.debug(f"Attempting to handle new client connection from {websocket.remote_address}")
        self._clients.add(websocket)
        try:
            self._logger.info(f"Client connected: {websocket.remote_address}. Total clients: {len(self._clients)}")
            async for message in websocket:
                await self._process_message(websocket, message)
        except websockets.ConnectionClosed: # as e:
            self._logger.info(f"Client disconnected: {websocket.remote_address}. Total clients: {len(self._clients) - 1}")
        except Exception as e:
            self._logger.error(f"Error handling client {websocket.remote_address}: {e}", exc_info=True)
        finally:
            self._clients.discard(websocket)

    async def _process_message(self, websocket: websockets.WebSocketServerProtocol, message: str) -> None:
        """Processes incoming JSON messages from a connected client. This is used for input forwarding
        and client commands (like requesting a full screen redraw)."""
        self._logger.debug(f"Received message from {websocket.remote_address}: {message[:100]}...") # Log first 100 chars
        try:
            data = json.loads(message)
            if data.get("type") == "input":
                self._logger.debug(f"Processing input from {websocket.remote_address}: {data["payload"]}")
                await self.input_handler.process_remote_input(data["payload"])
            elif data.get("type") == "command":
                command = data.get("command")
                if command == "redraw_full_frame":
                    self._logger.info(f"Received redraw_full_frame command from {websocket.remote_address}. Sending full frame.")
                    # Capture a fresh full frame using mss and send it to the requesting client
                    monitor = self._sct.monitors[self._monitor_id]
                    sct_img = self._sct.grab(monitor)
                    full_img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                    self._logger.debug(f"Captured full frame for redraw: size={full_img.size}, mode={full_img.mode}, first 20 bytes of raw data={full_img.tobytes()[:20].hex()}")
                    with BytesIO() as buf:
                        full_img.save(buf, format="JPEG", quality=self._jpeg_quality)
                        full_frame_bytes = buf.getvalue()
                    payload = self._pack_delta_payload(self._frame_id, [], full_frame_bytes)
                    await websocket.send(payload)
                else:
                    self._logger.warning(f"Unknown command received from {websocket.remote_address}: {command}")
        except json.JSONDecodeError:
            self._logger.error(f"Received malformed JSON from {websocket.remote_address}: {message}")
        except Exception as e:
            self._logger.error(f"Error processing message from {websocket.remote_address}: {e}", exc_info=True)

    async def broadcast_screen(self, image_data: bytes) -> None:
        """Sends the compressed screen data (either a full frame or delta frame) to all
        currently connected clients."""
        if not self._clients:
            self._logger.debug("No clients connected, skipping screen broadcast.")
            return
        
        self._logger.debug(f"Broadcasting screen update ({len(image_data)} bytes) to {len(self._clients)} clients. First 20 bytes: {image_data[:20].hex()}")
        # Remove disconnected clients
        disconnected = []
        for client in self._clients:
            try:
                await client.send(image_data)
            except websockets.ConnectionClosed: # as e:
                self._logger.warning(f"Client {client.remote_address} disconnected during broadcast.")
                disconnected.append(client)
            except Exception as e:
                self._logger.error(f"Error sending to client {client.remote_address}: {e}", exc_info=True)
                disconnected.append(client)
        
        for client in disconnected:
            self._clients.discard(client)

    async def capture_loop(self) -> None:
        """Continuously captures the screen, detects changes, and broadcasts delta or full frames
        to all connected clients. This is the core of the server's streaming functionality."""
        self._logger.info("Starting screen capture loop")
        first_frame = True
        while True:
            try:
                self._frame_id = (self._frame_id + 1) % 0xFFFFFFFF # 32-bit wrap-around
                self._logger.debug(f"Capturing frame ID: {self._frame_id}")

                # Capture the screen using mss
                monitor = self._sct.monitors[self._monitor_id]
                sct_img = self._sct.grab(monitor)
                # Convert to PIL Image
                full_img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)

                current_tiles = self._partition_screen(full_img)
                changed_tiles_data = []
                new_tile_hashes: Dict[Tuple[int, int], bytes] = {}

                total_tiles = len(current_tiles)
                num_changed_tiles = 0

                for x_idx, y_idx, tile_img in current_tiles:
                    current_hash = self._hash_tile(tile_img)
                    new_tile_hashes[(x_idx, y_idx)] = current_hash

                    if first_frame or self._prev_tile_hashes.get((x_idx, y_idx)) != current_hash:
                        compressed_data = self._compress_tile(tile_img)
                        changed_tiles_data.append((x_idx, y_idx, tile_img, compressed_data))
                        num_changed_tiles += 1
                
                self._prev_tile_hashes = new_tile_hashes
                first_frame = False

                self._logger.debug(f"Server capture_loop: Frame ID={self._frame_id}, Changed Tiles={num_changed_tiles}/{total_tiles}.")

                # Fallback logic: if too many tiles changed, send a full JPEG frame
                if num_changed_tiles > self._fallback_threshold * total_tiles:
                    self._logger.debug(f"Fallback to full frame: {num_changed_tiles}/{total_tiles} tiles changed.")
                    with BytesIO() as buf:
                        full_img.save(buf, format="JPEG", quality=self._jpeg_quality)
                        full_frame_bytes = buf.getvalue()
                    payload = self._pack_delta_payload(self._frame_id, [], full_frame_bytes)
                else:
                    self._logger.debug(f"Sending delta frame: {num_changed_tiles}/{total_tiles} tiles changed.")
                    payload = self._pack_delta_payload(self._frame_id, changed_tiles_data)
                
                await self.broadcast_screen(payload)
                await asyncio.sleep(self._capture_interval)
            except Exception as exc:
                self._logger.exception(f"Screen capture failed: {exc}")
                await asyncio.sleep(self._capture_interval)

    async def run(self) -> None:
        """Convenience method to start the server and its continuous screen capture loop."""
        await self.start()
        self._capture_task = asyncio.create_task(self.capture_loop())

    async def shutdown(self) -> None:
        """Gracefully shuts down the server and cancels the screen capture loop."""
        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass
        await self.stop()

    # Interface methods (not used by server but required for interface compliance)
    async def connect(self) -> None:
        """Server does not initiate connections, so this method is a no-op."""
        pass

    async def disconnect(self) -> None:
        """Server disconnects by shutting down, so this calls the shutdown method."""
        await self.shutdown()

    async def send(self, data: str) -> None:
        """Server does not send generic string data via this interface; it broadcasts screen data."""
        pass

    async def receive(self) -> str:
        """Server does not receive generic string data via this interface; it processes client messages in _process_message."""
        return ""

    def get_status(self) -> ConnectionStatus:
        """Returns the current connection status of the server."""
        return self._status


class ServerInputHandler(IInputHandler):
    """Handles input events received from clients. In this server implementation,
    it would typically translate remote input into local system actions (e.g., moving mouse, typing keys)."""

    async def capture_and_send_input(self) -> None:
        """The server does not capture its own local input to send, so this method is a no-op."""
        pass

    async def process_remote_input(self, data: Dict[str, Any]) -> None:
        """Processes input data received from a client and translates it into local system actions.
        For example, a 'mouse_move' action from the client would move the server's mouse cursor."""
        action = data.get("action")
        if action == "mouse_move":
            pyautogui.moveTo(data["x"], data["y"])
        elif action == "mouse_click":
            pyautogui.click(data["x"], data["y"])
        elif action == "key_press":
            pyautogui.press(data["key"])


# --------------------------------------------------------------------------- #
# 5. Client Implementation
# --------------------------------------------------------------------------- #

class ClientNetworkManager(INetworkManager):

    def __init__(self, host: str, port: int, settings: SettingsManager, reconnect_delay: float = 1.0, default_width: int = 1920, default_height: int = 1080, tile_size: int = 64) -> None:
        """Initializes the ClientNetworkManager with network settings and screen buffer parameters."""
        # Network configuration
        self.host = host
        self.port = port
        self.settings = settings # Reference to the settings manager
        self._status = ConnectionStatus.DISCONNECTED # Current connection status of the client
        self._ws: Optional[websockets.WebSocketClientProtocol] = None # The WebSocket client instance
        self._receive_task: Optional[asyncio.Task] = None # Task for the continuous message receiving loop
        self._logger = logging.getLogger("ClientNetworkManager") # Logger for client-specific messages

        # Reconnection and screen buffer parameters
        self._reconnect_delay = reconnect_delay  # Initial delay before attempting to reconnect
        self._default_width = default_width # Default width for local screen buffer if no full frame yet
        self._default_height = default_height # Default height for client buffer if no full frame yet
        self._on_screen_update: Optional[callable] = None # Callback function to update the UI with new screen data
        self._local_screen_buffer: Optional[Image.Image] = None # Stores the current state of the mirrored screen locally
        self._tile_size = tile_size # Store the tile size received from the server or default
    async def connect(self) -> None:
        """Attempts to establish a connection to the WebSocket server with an exponential back-off strategy.
        This ensures the client keeps trying to connect without overwhelming the server."""
        while True:
            try:
                self._logger.debug(f"Attempting to connect to ws://{self.host}:{self.port}")
                self._ws = await websockets.connect(f"ws://{self.host}:{self.port}")
                self._status = ConnectionStatus.CONNECTED
                self._logger.info(f"Connected to {self.host}:{self.port}")
                self._receive_task = asyncio.create_task(self._receive_loop())
                # After successful connection, request a full frame from the server
                await self.send(json.dumps({"type": "command", "command": "redraw_full_frame"}))
                self._reconnect_delay = self._reconnect_delay  # Reset delay on successful connection
                break
            except (OSError, websockets.InvalidURI, ConnectionRefusedError) as exc:
                self._logger.warning(f"Connection failed: {exc}. Retrying in {self._reconnect_delay:.1f}s")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)
            except Exception as exc:
                self._logger.error(f"Unexpected error during connection: {exc}", exc_info=True)

    async def disconnect(self) -> None:
        """Closes the WebSocket connection and cleans up associated tasks."""
        self._logger.debug("Client disconnect requested.")
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

    async def _receive_loop(self) -> None:
        """Continuously receives messages from the server and dispatches them for processing.
        Binary messages are treated as screen updates, while text messages are JSON commands."""
        self._logger.debug("Client receive loop started.")
        try:
            async for message in self._ws:
                self._logger.debug(f"Received message (type: {type(message)}, size: {len(message)}) from server.")
                # Check if the message is binary (screen update) or text (JSON input).
                if isinstance(message, bytes):
                    self._logger.debug(f"Raw binary message received in _receive_loop (first 20 bytes): {message[:20].hex()}")
                    await self._handle_screen(message)
                else:
                    await self._process_json_message(message)
        except websockets.ConnectionClosed:
            self._logger.warning("Connection closed by server")
        except Exception as e:
            self._logger.error(f"Error in receive loop: {e}", exc_info=True)
        finally:
            self._status = ConnectionStatus.DISCONNECTED
            self._logger.info("Client receive loop terminated.")

    async def _process_json_message(self, message: str) -> None:
        """Handles incoming JSON messages from the server. Currently, the client does not expect
        JSON commands from the server, but this method is a placeholder for future features."""
        try:
            data = json.loads(message)
            # Currently, the client only sends input, not receives JSON commands.
            # This can be extended for future features.
            self._logger.debug(f"Processing JSON message: {data}")
        except json.JSONDecodeError:
            self._logger.error(f"Received malformed JSON: {message}")
        except Exception as e:
            self._logger.error(f"Error processing JSON message: {e}", exc_info=True)

    def _unpack_delta_payload(self, payload: bytes) -> Tuple[int, list[tuple[int, int, int, int, bytes]], Optional[bytes]]:
        """Unpacks the binary payload received from the server into frame ID, changed tile data,
        or a full image. This method understands the custom binary protocol."""
        offset = 0
        
        # Read type byte (1 byte)
        frame_type = struct.unpack('>B', payload[offset:offset+1])[0]
        offset += 1
        self._logger.debug(f"Client unpacking: Payload size={len(payload)}, Frame Type={frame_type}. Full received payload (first 20 bytes): {payload[:20].hex()}")
        
        if frame_type == 0x01: # Full frame
            frame_id = struct.unpack('>I', payload[offset:offset+4])[0]
            offset += 4
            full_image_bytes = payload[offset:]
            self._logger.debug(f"Client unpacked full frame: ID={frame_id}, image size={len(full_image_bytes)} bytes.")
            return frame_id, [], full_image_bytes
        
        elif frame_type == 0x00: # Delta frame
            # Read 4 bytes for frame_id
            frame_id_bytes = payload[offset:offset+4]
            frame_id = struct.unpack('>I', frame_id_bytes)[0]
            offset += 4

            # Read 2 bytes for n_tiles
            n_tiles_bytes = payload[offset:offset+2]
            n_tiles = struct.unpack('>H', n_tiles_bytes)[0]
            offset += 2
            self._logger.debug(f"Client unpacked delta frame header: ID={frame_id}, n_tiles={n_tiles}. Raw frame_id bytes: {frame_id_bytes.hex()}, Raw n_tiles bytes: {n_tiles_bytes.hex()}")
            self._logger.debug(f"Client _unpack_delta_payload: Iterating {n_tiles} tiles.")
            
            changed_tiles_data = []
            for i in range(n_tiles):
                tile_header_bytes = payload[offset:offset+12]
                self._logger.debug(f"  - Raw tile header bytes for tile {i+1}/{n_tiles}: {tile_header_bytes.hex()}")
                if len(tile_header_bytes) < 12:
                    self._logger.error(f"Payload too short: cannot read tile header for tile {i+1}/{n_tiles}. Remaining buffer: {len(payload) - offset} bytes.")
                    raise ValueError(f"Payload too short: cannot read tile header for tile {i+1}/{n_tiles}.")
                x_idx, y_idx, tile_w, tile_h, data_len = struct.unpack('>HHHH I', tile_header_bytes)
                offset += 12
                self._logger.debug(f"  - Client unpacking tile {i+1}/{n_tiles}: ({x_idx},{y_idx}) WxH={tile_w}x{tile_h}, expected data_len={data_len}.")
                
                compressed_data = payload[offset:offset+data_len]
                if len(compressed_data) < data_len:
                    self._logger.error(f"Payload too short: cannot read compressed data for tile {i+1}/{n_tiles}. Expected {data_len} bytes, got {len(compressed_data)}.")
                    raise ValueError(f"Payload too short: cannot read compressed data for tile {i+1}/{n_tiles}.")
                offset += data_len
                changed_tiles_data.append((x_idx, y_idx, tile_w, tile_h, compressed_data))
            
            return frame_id, changed_tiles_data, None
        else:
            self._logger.error(f"Unknown frame type received: {frame_type}")
            raise ValueError(f"Unknown frame type: {frame_type}")

    def _decompress_tile(self, compressed_data: bytes) -> Image.Image:
        """Decompresses WebP tile data back into a PIL Image object."""
        return Image.open(BytesIO(compressed_data))

    async def _handle_screen(self, payload: bytes) -> None:
        """Decodes the binary screen data received from the server (either a full frame or delta frames)
        and updates the local screen buffer. Then, it triggers a UI update."""
        try:
            # Unpack the payload to get frame ID, changed tiles data, or full image bytes.
            frame_id, changed_tiles_data, full_image_bytes = self._unpack_delta_payload(payload)
            changed_regions_pixel_coords = [] # Initialize to an empty list

            if full_image_bytes:
                self._logger.debug(f"Handling full frame (ID: {frame_id}, size: {len(full_image_bytes)} bytes).")
                # Handle full frame
                image = Image.open(BytesIO(full_image_bytes))
                self._local_screen_buffer = image
                self._logger.debug(f"Received full frame (ID: {frame_id})")
            elif changed_tiles_data: # This will be true if n_tiles > 0
                self._logger.debug(f"Handling delta frame (ID: {frame_id}) with {len(changed_tiles_data)} tiles.")
                # Handle delta frame
                if self._local_screen_buffer is None:
                    # Initialize with a black image of a reasonable default size if no full frame has been received yet.
                    # This prevents AttributeError if the first frame is a delta with no changes.
                    self._logger.warning("Received delta frame before full frame. Initializing with default size (%sx%s)." % (self._default_width, self._default_height))
                    self._local_screen_buffer = Image.new("RGB", (self._default_width, self._default_height), color = 'black')

                changed_regions_pixel_coords = []
                for x_idx, y_idx, tile_w, tile_h, compressed_data in changed_tiles_data:
                    tile_img = self._decompress_tile(compressed_data)
                    self._logger.debug(f"  - Decompressed tile: x_idx={x_idx}, y_idx={y_idx}, WxH={tile_w}x{tile_h}, Mode={tile_img.mode}, Size={tile_img.size}")
                    # Calculate pixel coordinates from tile indices
                    x_pixel = x_idx * self._tile_size # Note: self._tile_size is from server, client needs to know it or infer
                    y_pixel = y_idx * self._tile_size # For now, assuming client knows server's tile size.
                    self._logger.debug(f"  - Pasting tile at pixel coordinates: x={x_pixel}, y={y_pixel}")
                    self._local_screen_buffer.paste(tile_img, (x_pixel, y_pixel))
                    changed_regions_pixel_coords.append((x_pixel, y_pixel, tile_w, tile_h))
                self._logger.debug(f"Received delta frame (ID: {frame_id}) with {len(changed_tiles_data)} tiles.")
            # This is the case for empty delta frames (n_tiles == 0)
            elif not changed_tiles_data and not full_image_bytes:
                self._logger.debug(f"Received empty delta frame (ID: {frame_id}). No screen update needed.")
                if self._local_screen_buffer is None:
                    self._logger.warning("Received empty delta frame before full frame. Initializing with default size (%sx%s)." % (self._default_width, self._default_height))
                    self._local_screen_buffer = Image.new("RGB", (self._default_width, self._default_height), color = 'black')
            
            if self._local_screen_buffer and self._on_screen_update:
                self._on_screen_update(self._local_screen_buffer, changed_regions_pixel_coords, bool(full_image_bytes))

        except Exception as e:
            self._logger.error(f"Error handling screen update: {e}", exc_info=True)

    def set_screen_update_callback(self, callback: callable[[Image.Image, Optional[list[tuple[int, int, int, int]]], bool], None]) -> None:
        """Sets the callback function to be called when the screen is updated."""
        self._on_screen_update = callback

    async def send(self, data: str) -> None:
        """Sends string data to the connected server."""
        if self._ws and self._status == ConnectionStatus.CONNECTED:
            try:
                self._logger.debug(f"Sending data: {data[:100]}...") # Log first 100 chars
                await self._ws.send(data)
            except websockets.ConnectionClosed:
                self._status = ConnectionStatus.DISCONNECTED
                self._logger.warning("Connection closed while trying to send data.")
            except Exception as e:
                self._logger.error(f"Error sending data: {e}", exc_info=True)

    async def receive(self) -> str:
        """Receives string data from the server. This method is not used for screen data anymore,
        as screen data is handled directly in `_receive_loop`."""
        raise RuntimeError("ClientNetworkManager.receive() is not intended for direct use with screen data.")

    def get_status(self) -> ConnectionStatus:
        """Returns the current connection status of the client."""
        return self._status


class ClientInputHandler(IInputHandler):

    def __init__(self, network_manager: ClientNetworkManager) -> None:
        """Initializes the ClientInputHandler with a reference to the network manager."""
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
        """Sends input data (e.g., mouse movements, clicks, key presses) to the server."""
        try:
            message = json.dumps({"type": "input", "payload": payload})
            await self.network_manager.send(message)
        except Exception as e:
            self._logger.error(f"Error sending input: {e}")

    async def send_command(self, command: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Sends a command to the server (e.g., to request a full screen redraw)."""
        try:
            message_payload = {"type": "command", "command": command}
            if payload:
                message_payload["payload"] = payload
            message = json.dumps(message_payload)
            await self.network_manager.send(message)
        except Exception as e:
            self._logger.error(f"Error sending command: {e}")


# --------------------------------------------------------------------------- #
# 6. UI Layer (Tkinter)
# --------------------------------------------------------------------------- #

class PixelMirrorClientUI:

    def __init__(self, network_manager: ClientNetworkManager, input_handler: ClientInputHandler, loop: asyncio.AbstractEventLoop) -> None:
        """Initializes the Tkinter UI for displaying the mirrored screen and handling user input."""
        self.network_manager = network_manager
        self.input_handler = input_handler
        self.loop = loop # Store the asyncio event loop
        self.root = tk.Tk()
        self.root.title("PixelMirror – Client")
        self.root.geometry("800x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._logger = logging.getLogger("PixelMirrorClientUI")

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
        self.canvas_image_item: Optional[int] = None # Store the ID of the main canvas image item

        # Set callback for screen updates
        self.network_manager.set_screen_update_callback(self.update_screen)

        # Status label
        self.status_label = tk.Label(self.root, text="Status: Disconnected", bg="red", fg="white")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # Update status periodically
        self.update_status()

    def on_close(self) -> None:
        """Handles the window close event, quitting the Tkinter application."""
        self.root.quit()

    def on_mouse_move(self, event: tk.Event) -> None:
        """Forwards mouse movement events to the server, scaling coordinates as needed."""
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
            self.loop.call_soon_threadsafe(self.loop.create_task, self.input_handler.send_input(payload))

    def on_mouse_click(self, event: tk.Event) -> None:
        """Forwards mouse click events to the server, scaling coordinates as needed."""
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
            self.loop.call_soon_threadsafe(self.loop.create_task, self.input_handler.send_input(payload))

    def on_key_press(self, event: tk.Event) -> None:
        """Forwards keyboard press events to the server. Special keys like 'r' or 'R'
        trigger a full screen redraw request."""
        if self.network_manager.get_status() == ConnectionStatus.CONNECTED:
            if event.keysym == 'r' or event.keysym == 'R':
                self.loop.call_soon_threadsafe(self.loop.create_task, self.input_handler.send_command("redraw_full_frame"))
                self._logger.info("Sent redraw_full_frame command to server.")
            else:
                payload = {"action": "key_press", "key": event.keysym}
                self.loop.call_soon_threadsafe(self.loop.create_task, self.input_handler.send_input(payload))

    def update_screen(self, image: Image.Image, changed_regions: Optional[list[tuple[int, int, int, int]]], is_full_frame: bool) -> None:
        """Updates the Tkinter canvas with the new screen image received from the server."""
        try:
            self.current_image = image
            
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            if canvas_width <= 1 or canvas_height <= 1: # Ensure canvas is initialized
                return

            # Resize the current_image (which is _local_screen_buffer) to fit the canvas
            image_copy = image.copy()
            image_copy.thumbnail((canvas_width, canvas_height), Image.Resampling.LANCZOS)
            self.photo_image = ImageTk.PhotoImage(image_copy)
            
            # Always clear all existing tile image items when any update arrives
            # This simplifies management and ensures no old tiles are left behind
            if hasattr(self.canvas, '_tile_photo_images'):
                for tag in list(self.canvas._tile_photo_images.keys()):
                    self.canvas.delete(tag)
                self.canvas._tile_photo_images.clear()

            # Update or create the main canvas image item
            if self.canvas_image_item is None:
                self.canvas_image_item = self.canvas.create_image(canvas_width//2, canvas_height//2, image=self.photo_image, anchor=tk.CENTER)
            else:
                self.canvas.itemconfig(self.canvas_image_item, image=self.photo_image)

        except Exception as exc:
            logging.exception(f"Failed to update screen: {exc}")

    def update_status(self) -> None:
        """Updates the connection status label in the UI."""
        status = self.network_manager.get_status()
        if status == ConnectionStatus.CONNECTED:
            self.status_label.config(text=f"Status: Connected to {self.network_manager.host}:{self.network_manager.port}", bg="green")
        else:
            self.status_label.config(text="Status: Disconnected", bg="red")
        
        # Schedule next update
        self.root.after(1000, self.update_status)

    def run(self) -> None:
        """Starts the Tkinter main loop, making the UI interactive."""
        self.root.mainloop()


# --------------------------------------------------------------------------- #
# 7. Main Entry Point
# --------------------------------------------------------------------------- #

async def run_server(host: str, port: int, monitor_id: int, tile_size: int, fallback_threshold: float, capture_interval: float, webp_quality: int, jpeg_quality: int) -> None:
    """Runs the PixelMirror server, handling screen capture and streaming to clients."""
    settings = SettingsManager()
    input_handler = ServerInputHandler() # Instantiate ServerInputHandler
    server_manager = ServerNetworkManager(host, port, settings, input_handler, monitor_id=monitor_id, tile_size=tile_size, fallback_threshold=fallback_threshold, capture_interval=capture_interval, webp_quality=webp_quality, jpeg_quality=jpeg_quality)
    
    try:
        await server_manager.run()
        logging.info("Server started successfully. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down server...")
    finally:
        await server_manager.shutdown()


def run_client_sync(host: str, port: int, reconnect_delay: float, default_width: int, default_height: int, tile_size: int) -> None:
    """Runs the PixelMirror client in a synchronous manner, integrating with the Tkinter UI."""
    settings = SettingsManager()
    client_manager = ClientNetworkManager(host, port, settings, reconnect_delay=reconnect_delay, default_width=default_width, default_height=default_height, tile_size=tile_size)
    input_handler = ClientInputHandler(client_manager)
    
    # Create event loop for asyncio operations
    loop = asyncio.new_event_loop()
    
    # Start connection in background
    async def connect_and_run(event_loop):
        asyncio.set_event_loop(event_loop)
        await client_manager.connect()
    
    # Run connection in thread
    def run_async(event_loop):
        event_loop.run_until_complete(connect_and_run(event_loop))
        event_loop.run_forever()
    
    async_thread = threading.Thread(target=run_async, args=(loop,), daemon=True)
    async_thread.start()
    
    # Pass the loop to the UI
    ui = PixelMirrorClientUI(client_manager, input_handler, loop)
    
    try:
        # Start UI (blocking)
        ui.run()
    finally:
        # Cleanup
        loop.call_soon_threadsafe(loop.stop)
        asyncio.run_coroutine_threadsafe(client_manager.disconnect(), loop)


def main() -> None:
    """Main entry point of the PixelMirror application, parsing command-line arguments and starting either the server or client."""
    parser = argparse.ArgumentParser(description="PixelMirror – Screen Mirroring Demo")
    parser.add_argument("--mode", choices=["server", "client"], required=True, help="Run as server or client")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (client mode) or bind address (server mode)")
    parser.add_argument("--port", type=int, default=8765, help="Port number")
    parser.add_argument("--monitor-id", type=int, default=1, help="Monitor ID to capture (0 for all, 1 for primary, etc. - server mode only)")
    parser.add_argument("--tile-size", type=int, default=64, help="Size of tiles for delta updates (server mode only)")
    parser.add_argument("--fallback-threshold", type=float, default=0.7, help="Threshold for sending full frame instead of delta (server mode only)")
    parser.add_argument("--capture-interval", type=float, default=0.1, help="Screen capture interval in seconds (server mode only)")
    parser.add_argument("--webp-quality", type=int, default=80, help="Quality for WebP compression (0-100, server mode only)")
    parser.add_argument("--jpeg-quality", type=int, default=70, help="Quality for JPEG compression (0-100, server mode only)")
    parser.add_argument("--reconnect-delay", type=float, default=1.0, help="Initial reconnection delay in seconds (client mode only)")
    parser.add_argument("--default-width", type=int, default=1920, help="Default width for client buffer if delta frame arrives first (client mode only)")
    parser.add_argument("--default-height", type=int, default=1080, help="Default height for client buffer if delta frame arrives first (client mode only)")
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.ERROR,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if args.mode == "server":
        asyncio.run(run_server(args.host, args.port, args.monitor_id, args.tile_size, args.fallback_threshold, args.capture_interval, args.webp_quality, args.jpeg_quality))
    else:
        run_client_sync(args.host, args.port, args.reconnect_delay, args.default_width, args.default_height, args.tile_size)

if __name__ == "__main__":
    main()
