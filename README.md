# PixelMirror_v2

PixelMirror_v2 is a high-performance, real-time screen and audio mirroring application. It allows you to mirror your desktop to multiple client devices, with low-latency input forwarding for remote control.

## Features

*   **Real-time Screen & Audio Mirroring:** Stream your desktop and audio to multiple clients in real-time.
*   **Low-Latency Input Forwarding:** Control your host machine from the client with mouse and keyboard input.
*   **High-Performance Streaming:** Utilizes a delta-based streaming protocol with direct binary data transfer over WebSockets for efficient and low-bandwidth streaming.
*   **Cross-Platform Clients:** Includes a desktop client built with Tkinter and a web-based client for broader accessibility.
*   **Secure Communication:** All communication between the client and server is secured with TLS/SSL encryption.
*   **Modular Architecture:** Designed with a modular and extensible architecture, making it easy to add new features and maintain the codebase.

## Getting Started

### Prerequisites

Install the required dependencies:

```bash
pip install -r requirements.txt
```

### Running the Server

```bash
python main.py --mode server
```

### Running the Client

```bash
python main.py --mode client
```