# PixelMirror

A minimal, production-ready screen mirroring application that allows real-time desktop mirroring from PC to client devices.

## Features

- Real-time screen capture and streaming
- Low-latency input forwarding (mouse and keyboard)
- Robust networking with automatic reconnection
- Settings persistence
- Comprehensive logging and error handling
- WebSocket-based communication

## Prerequisites

Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Running the Server (PC)

Start the server on the PC that you want to mirror:

```bash
python pixelmirror.py --mode server --host 0.0.0.0 --port 8765
```

- `--host 0.0.0.0`: Binds to all network interfaces (allows connections from other devices)
- `--port 8765`: Port number for the WebSocket server

### Running the Client

Start the client on the device that will display the mirrored screen:

```bash
python pixelmirror.py --mode client --host <SERVER_IP> --port 8765
```

Replace `<SERVER_IP>` with the IP address of the PC running the server.

For local testing, you can use:

```bash
python pixelmirror.py --mode client --host 127.0.0.1 --port 8765
```

## How It Works

1. **Server**: Captures the desktop screen using `pyautogui`, compresses it to JPEG format, encodes it as Base64, and streams it over WebSocket
2. **Client**: Receives the image data, displays it in a Tkinter window, and forwards mouse/keyboard events back to the server
3. **Input Forwarding**: Mouse movements, clicks, and key presses in the client window are sent to the server and executed on the host machine

## Architecture

The application follows a modular design with clear separation of concerns:

- **Network Manager**: Handles WebSocket communication
- **Input Handler**: Manages input capture and forwarding
- **Settings Manager**: Persists user preferences
- **UI Layer**: Provides the user interface (Tkinter-based)

## Configuration

Settings are automatically saved to `~/.pixelmirror.ini` in the user's home directory.

## Troubleshooting

1. **Connection Issues**: Ensure the server is running and the firewall allows connections on the specified port
2. **Performance**: Adjust the capture interval in the `capture_loop` method for better performance
3. **Input Not Working**: Make sure the client window has focus for keyboard events

## Security Note

This demo implementation does not include encryption. For production use, consider adding TLS/SSL encryption for secure communication.

## Requirements Met

This implementation satisfies the core requirements from the PixelMirror specification:

- ✅ Real-time desktop mirroring
- ✅ Low-latency input forwarding
- ✅ Robust connection handling with reconnection
- ✅ Settings persistence
- ✅ Comprehensive error handling and logging
- ✅ Modular, maintainable architecture