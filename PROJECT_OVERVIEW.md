# PixelMirror_v2 Project Overview

## 🎯 Project Status: In-Progress

This document provides a high-level overview of the PixelMirror_v2 project, including its goals, architecture, and features. It's important to note that the `pixelmirror.py` script from the original project serves as a foundational reference for the core screen mirroring and input forwarding mechanisms, providing a proven and workable design to build upon.

## 🚀 Key Features

*   **Real-time Screen & Audio Mirroring:** Stream desktop content and audio from a server PC to client devices.
*   **Low-Latency Input Forwarding:** Enable remote control of the server PC via mouse and keyboard input from the client.
*   **Optimized Streaming:** Utilizes a delta-based streaming protocol with direct binary data transfer over WebSockets for high performance and low bandwidth usage.
*   **UI Enhancements:** The client UI will feature a real-time latency indicator to provide feedback on network performance.
*   **Robust Streaming:** The application will implement a jitter buffer and packet loss compensation to ensure a smooth stream.
*   **Modular & Extensible Architecture:** Built with a clear separation of concerns and a `ConnectionManager` abstraction for easy maintenance and future enhancements.
*   **Cross-Platform Clients:** Desktop client (Tkinter) and a web-based client.
*   **Enhanced Security:** Communication secured with TLS/SSL encryption.

## 🏗️ Architecture

PixelMirror_v2 follows a client-server architecture and leverages design patterns such as the Strategy and Observer patterns to create a flexible and maintainable codebase. The core components include modules for screen and audio capture, data encoding, and network management.

## 📖 Development Ground Rules

The project will follow a structured development process, including requirement analysis, a well-defined technical approach, a phased implementation plan, and clear deliverables and verification criteria. For more details, please refer to the `design_specification.md` document.