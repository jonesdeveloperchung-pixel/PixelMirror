#!/usr/bin/env python3
"""
PixelMirror Launcher
--------------------
This script serves as an interactive command‑line launcher for the
PixelMirror screen‑mirroring application.  It offers a simple menu
to start the application in either server or client mode, run the
included test suite, or exit the program.

Design concept
~~~~~~~~~~~~~~
The launcher is intentionally minimalistic yet functional:

* **Separation of concerns** – the launcher only deals with user
  interaction and process spawning.  The actual mirroring logic
  lives in *pixelmirror.py*, keeping this script lightweight and
  easy to maintain.

* **Platform‑independence** – by invoking the Python interpreter
  via ``sys.executable`` we ensure that the same interpreter
  used to run the launcher is also used to run the target scripts,
  avoiding path or environment issues on Windows, macOS, or Linux.

* **Graceful shutdown** – the server and client processes are
  launched with ``subprocess.run`` inside a ``try/except KeyboardInterrupt``
  block so the user can stop them with ``Ctrl+C``.  This pattern
  keeps the launcher responsive and cleanly terminates child
  processes when the user cancels the operation.

* **Automatic IP discovery** – ``get_local_ip`` attempts to discover
  the host machine’s local IP address by opening a UDP socket to
  a public DNS server (8.8.8.8).  If that fails, it falls back to
  localhost.  The discovered address is then presented as the
  default when a client connects.

* **Extensibility** – the menu structure makes it trivial to add
  new options in the future.  Each block that launches a subprocess
  is self‑contained, so adding a new mode would simply involve
  inserting another ``elif`` clause.

The code below has been annotated with comments to explain
the purpose of each block and the reasoning behind the
chosen implementation details.
"""

import subprocess  # For spawning the PixelMirror application.
import sys         # To access the current Python interpreter.
import socket      # To determine the local IP address.
import time        # (Imported but not used; kept for potential future timing needs.)

def get_local_ip():
    """
    Determine the host machine's local IP address.

    Returns:
        str: The IPv4 address of the first non‑loopback interface that
             can reach an external endpoint, or ``127.0.0.1`` on failure.
    """
    try:
        # Connect to a public DNS server to let the OS choose the
        # appropriate interface.  No data is actually sent.
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        # Fallback to localhost if we cannot determine a real address.
        return "127.0.0.1"

def main():
    """Main entry point – displays a menu and handles user input."""
    print("=" * 50)
    print("         PixelMirror Launcher")
    print("=" * 50)
    print()

    # Get local IP once, to display as default and for client connection.
    local_ip = get_local_ip()

    # Display menu options.
    print("Choose an option:")
    print("1. Start Server (Mirror this PC's screen)")
    print("2. Start Client (View mirrored screen)")
    print("3. Run Tests")
    print("4. Exit")
    print()

    # Loop until the user selects a valid option that completes the task.
    while True:
        choice = input("Enter your choice (1-4): ").strip()

        if choice == "1":
            # ---------- Server mode ----------
            print(f"\nStarting server on {local_ip}:8765...")
            print("Other devices can connect using this IP address.")
            print("Press Ctrl+C to stop the server.")
            print("-" * 50)
            try:
                # Launch pixelmirror.py in server mode.  All arguments are
                # passed explicitly to avoid reliance on environment variables.
                subprocess.run(
                    [
                        sys.executable,  # Use the same interpreter.
                        "python",  # Explicitly specify python to avoid issues on Windows.
                        "pixelmirror.py",
                        "--mode", "server",
                        "--host", "0.0.0.0",
                        "--port", "8765",
                    ]
                )
            except KeyboardInterrupt:
                print("\nServer stopped.")
            break  # Exit after launching (or after user stops the server).

        elif choice == "2":
            # ---------- Client mode ----------
            print("\nStarting client...")
            host = input(f"Enter server IP address (default: {local_ip}): ").strip()
            if not host:
                host = local_ip  # Use local IP if user presses Enter.

            port = input("Enter port (default: 8765): ").strip()
            if not port:
                port = "8765"

            print(f"Connecting to {host}:{port}...")
            print("-" * 50)
            try:
                subprocess.run(
                    [
                        sys.executable,
                        "pixelmirror.py",
                        "--mode", "client",
                        "--host", host,
                        "--port", port,
                    ]
                )
            except KeyboardInterrupt:
                print("\nClient stopped.")
            break  # Exit after launching.

        elif choice == "3":
            # ---------- Run tests ----------
            print("\nRunning tests...")
            print("-" * 50)
            # Execute the test harness script.
            subprocess.run([sys.executable, "test_setup.py"])
            print("\nPress Enter to continue...")
            input()  # Pause so user can read test output.

        elif choice == "4":
            # ---------- Exit ----------
            print("Goodbye!")
            break

        else:
            # ---------- Invalid input ----------
            print("Invalid choice. Please enter 1, 2, 3, or 4.")

if __name__ == "__main__":
    main()