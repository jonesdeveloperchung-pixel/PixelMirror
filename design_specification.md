# PixelMirror_v2 Design Specification

## 1. Introduction

This document details the design and architecture of the PixelMirror_v2 application. This new version of PixelMirror will build upon the existing features of the original PixelMirror project, and will incorporate new features and design improvements for better performance, modularity, and user experience. The `pixelmirror.py` script from the original project serves as a foundational reference for the core screen mirroring and input forwarding mechanisms, providing a proven and workable design to build upon.

## 2. Key Features

### 2.1. Core Features (from original PixelMirror)

*   **Real-time Screen Mirroring:** Stream desktop content from a server PC to client devices.
*   **Low-Latency Input Forwarding:** Enable remote control of the server PC via mouse and keyboard input from the client.
*   **Delta-Based Streaming:** Utilize a binary WebSocket protocol to send only changed screen tiles, significantly reducing bandwidth and CPU usage.
*   **Tile-Based Updates:** Divide the screen into configurable 64x64 pixel tiles, using hashing to detect changes.
*   **Dynamic Fallback:** Automatically switch to sending a full JPEG frame when a large portion of the screen changes to maintain performance.
*   **Configurable Compression:** Employ WebP for individual tile compression and JPEG for full frames, with adjustable quality settings.
*   **Automatic Reconnection:** The client automatically attempts to reconnect to the server with an exponential backoff strategy for robust connections.
*   **Settings Persistence:** Configuration settings are saved and loaded from an INI file.
*   **Multi-Monitor Support:** The server can capture a specific monitor or the entire virtual screen.
*   **Client-side Full Redraw:** Clients can request a full screen refresh from the server.
*   **Comprehensive Logging and Error Handling:** Detailed logging and robust exception handling for debugging and graceful recovery.

### 2.2. New Features and Improvements (for PixelMirror_v2)

*   **Direct Binary Data Transfer:** Eliminate base64 encoding in favor of sending raw binary data over WebSockets for improved performance and reduced memory overhead.
*   **`ConnectionManager` Abstraction:** Introduce a `ConnectionManager` abstract base class to create a clearer and more modular network interface for both the client and server.
*   **UI Enhancements:** Improve the client-side UI to prevent flickering by using a single canvas item for screen updates. Updates will be handled in a thread-safe manner, and the UI will display the current connection status and a real-time latency indicator.
*   **Audio Streaming:** Add the capability to stream audio from the server to the client using the Real-time Transport Protocol (RTP).
*   **Web-Based Client:** Create a web-based client that can connect to the server, in addition to the desktop client.
*   **Enhanced Security:** Implement TLS/SSL encryption and an authentication mechanism for secure communication.
*   **Jitter Buffer & Packet Loss Compensation:** Implement a jitter buffer and packet loss compensation techniques to ensure a smooth stream, especially on unreliable networks.

## 3. Architecture

### 3.1. High-Level Design

PixelMirror_v2 will follow a client-server architecture. The server will be responsible for capturing the screen and audio, encoding the data, and streaming it to the clients. The clients will connect to the server, decode the data, and display the mirrored screen and play the audio.

### 3.2. Design Patterns

*   **Client-Server Architecture**: Clear separation between the PC (server) and the viewing device (client).
*   **Delta-Based Streaming**: Transmits only the changed portions of the screen to minimize latency and bandwidth.
*   **Strategy Pattern**: Allows for interchangeable components, such as different compression algorithms or network protocols.
*   **Observer Pattern**: Decouples the UI from the network logic, allowing for asynchronous updates.
*   **ConnectionManager Abstraction**: A `ConnectionManager` abstract base class will provide a modular and clearly defined network interface for both the client and server.

### 3.3. Key Components

1.  **ScreenCaptureModule**: Captures the screen and partitions it into tiles.
2.  **AudioCaptureModule**: Captures the system's audio output.
3.  **TilePartitioner**: Divides the screen into a grid for efficient comparison.
4.  **HashCache**: Stores tile hashes to detect changes between frames.
5.  **DeltaBuilder**: Constructs delta frames containing only the changed tiles.
6.  **Encoder**: Compresses tiles using WebP, full frames using JPEG, and audio using a suitable codec (e.g., Opus).
7.  **Protocol**: Serializes data into a compact binary format for transmission.
8.  **NetworkManager**: Manages the WebSocket connections and data transfer, using the `ConnectionManager` abstraction.
9.  **ClientUI**: The client-side user interface, which will be implemented as both a desktop application (using Tkinter) and a web-based application.

## 5. Development Ground Rules

This section outlines the key architectural ground rules for the PixelMirror_v2 project, with a strong emphasis on modularity and reusability.

### 5.1. Requirement Analysis

*   **Core Functionality:** The system will provide real-time screen and audio mirroring from a server to multiple clients. Users will be able to view the mirrored screen and hear the audio on client devices, and remotely control the server with mouse and keyboard input. The system must be easily extendable to support new data stream types in the future.
*   **Key Constraints & Assumptions:**
    *   The application must support a low-latency stream with minimal buffering.
    *   The application will primarily be used on local networks.
    *   We assume a stable network connection between the server and clients.
*   **Stakeholder or System Dependencies:**
    *   The desktop client will be built using Tkinter.
    *   The web client will be built using standard web technologies (HTML, CSS, JavaScript).

### 5.2. Technical Approach

*   **Architecture Overview:** A client-server architecture will be used. The application will be structured as a two-tier architecture:
    *   **Server Tier:** A Python application will handle screen and audio capture, encoding, and streaming.
    *   **Client Tier:** Desktop (Tkinter) and web-based clients will receive and display the stream.
*   **Technology Stack:**
    *   **Server:** Python with `websockets`, `mss`, `Pillow`, `pyautogui`, and a suitable audio library.
    *   **Desktop Client:** Python with `tkinter`, `websockets`, and `Pillow`.
    *   **Web Client:** HTML, CSS, JavaScript.
    *   **API:** WebSocket-based binary protocol.
*   **Design Patterns & Best Practices:**
    *   **Model-View-Controller (MVC):** The application will be structured using the MVC pattern to separate concerns.
    *   **Dependency Injection:** To improve testability and modularity, use dependency injection to manage dependencies between components.
    *   **SOLID Principles:** Apply SOLID principles to create maintainable and adaptable code.
    *   **Configuration Management:** Utilize environment variables for configurable parameters (e.g., port, tile size).
*   **Security, Scalability, and Performance Considerations:**
    *   **Security:** Use WSS (WebSocket Secure) for all communication. Implement an authentication mechanism to control access to the server.
    *   **Scalability:** Design the application to handle multiple client connections simultaneously.
    *   **Performance:** Optimize the screen and audio capture process. Use efficient encoding and decoding techniques. Minimize latency in the streaming pipeline.

### 5.3. Phased Development Plan

This project will be developed in phases, with each phase having a minimum acceptable design and validation criteria.

#### Phase 1: Core Component Design

*   **Minimum Acceptable Design:**
    *   A clear and complete definition of the interfaces for the core components: `Streamable`, `Capture`, `Encoder`, and `NetworkManager`.
    *   The interfaces should be documented with their methods, parameters, and return types.
*   **Minimum Acceptable Validation:**
    *   A peer review of the interface definitions to ensure they are clear, complete, and meet the requirements.

#### Phase 2: Server-Side Development

*   **Minimum Acceptable Design:**
    *   A functional server that can capture the screen, encode it as a full JPEG frame, and send it over a WebSocket connection.
    *   The server should implement the `Capture`, `Encoder`, and `NetworkManager` interfaces from Phase 1.
*   **Minimum Acceptable Validation:**
    *   Unit tests for the server-side components.
    *   A simple test client that can connect to the server, receive the image data, and save it to a file.

#### Phase 3: Client-Side Development (Desktop) - Complete

*   **Minimum Acceptable Design:** A functional desktop client that can connect to the server, receive the image data, and display it in a window. The client should implement the `NetworkManager` and `Decoder` interfaces.
*   **Minimum Acceptable Validation:** Unit tests for the client-side components. Manual testing of the desktop client to ensure it can connect to the server and display the mirrored screen.
    *Confirmed working by user.*

#### Phase 4: Advanced Streaming Features - Complete

*   **Minimum Acceptable Design:**
    *   **Delta-based Streaming:** Implementation of delta-based streaming (sending only changed tiles) on the server.
    *   **Tile Decoding and Screen Buffer Updates:** Implementation of tile decoding and screen buffer updates on the client.
    *   **Audio Streaming:** Implementation of Opus-encoded audio streaming over WebSockets on both the server and client.
*   **Minimum Acceptable Validation:**
    *   **Delta-based Streaming:** Unit tests for tile hashing, change detection, and delta payload packing on the server. Integration tests to verify client correctly receives and applies delta frames.
    *   **Audio Streaming:** Unit tests for audio capture and encoding on the server. Unit tests for audio decoding and playback on the client. Integration tests to ensure synchronized audio and video streams.

#### Phase 5: Web Client Development

*   **Minimum Acceptable Design:**
    *   A functional web client that can connect to the server, receive the stream, and display it in a web browser.
    *   The web client should be implemented using standard web technologies (HTML, CSS, JavaScript).
*   **Minimum Acceptable Validation:**
    *   Manual testing of the web client to ensure it can connect to the server and display the mirrored screen.

#### Phase 6: Integration & Final Testing

*   **Minimum Acceptable Design:**
    *   A complete and integrated system with all features implemented.
*   **Minimum Acceptable Validation:**
    *   A comprehensive suite of integration tests that verify the end-to-end functionality of the system.
    *   User acceptance testing (UAT) to ensure the application meets user expectations.

### 5.4. Deliverables & Verification

*   **Artifacts to Produce:**
    *   `Streamable` Interface Definition.
    *   API Endpoint Specifications (binary protocol).
    *   Configuration File Structure.
    *   Server and Client Code Repositories.
*   **Suggested Unit/Integration Test Cases:**
    *   "Create Session" – Tests the successful creation of a new streaming session.
    *   "Retrieve Stream Data" – Verifies accurate retrieval and decoding of stream data.
    *   "Update Session Data" – Confirms the modification of session data (e.g., changing stream quality).
    *   "Delete Session" - Checks that a session is successfully terminated.
*   **Acceptance Criteria for Each Feature:**
    *   Session creation is successful and a new session is established.
    *   Stream data can be retrieved and decoded correctly.
    *   Session parameters can be updated accurately.
    *   Sessions can be successfully deleted.
*   **CI/CD Pipeline:**
    *   A CI/CD pipeline will be set up using GitHub Actions to automate the build, testing, and deployment process.

### 5.5. Telemetry & Analytics

*   The application will collect telemetry data to monitor and improve performance. This data will include:
    *   **Latency:** Real-time latency metrics will be collected and displayed on the client UI.
    *   **Bandwidth:** The application will monitor bandwidth usage to help diagnose performance issues.
    *   **Battery:** The client application will monitor battery usage to ensure it is not excessively draining the battery.