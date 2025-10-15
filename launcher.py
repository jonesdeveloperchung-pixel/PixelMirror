#!/usr/bin/env python3
"""
PixelMirror Launcher - Interactive launcher for PixelMirror application.
"""

import subprocess
import sys
import socket
import time

def get_local_ip():
    """Get the local IP address."""
    try:
        # Connect to a remote address to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

def main():
    print("=" * 50)
    print("         PixelMirror Launcher")
    print("=" * 50)
    print()
    
    # Get local IP
    local_ip = get_local_ip()
    
    print("Choose an option:")
    print("1. Start Server (Mirror this PC's screen)")
    print("2. Start Client (View mirrored screen)")
    print("3. Run Tests")
    print("4. Exit")
    print()
    
    while True:
        choice = input("Enter your choice (1-4): ").strip()
        
        if choice == "1":
            print(f"\nStarting server on {local_ip}:8765...")
            print("Other devices can connect using this IP address.")
            print("Press Ctrl+C to stop the server.")
            print("-" * 50)
            try:
                subprocess.run([sys.executable, "pixelmirror.py", "--mode", "server", "--host", "0.0.0.0", "--port", "8765"])
            except KeyboardInterrupt:
                print("\nServer stopped.")
            break
            
        elif choice == "2":
            print("\nStarting client...")
            host = input(f"Enter server IP address (default: {local_ip}): ").strip()
            if not host:
                host = local_ip
            
            port = input("Enter port (default: 8765): ").strip()
            if not port:
                port = "8765"
            
            print(f"Connecting to {host}:{port}...")
            print("-" * 50)
            try:
                subprocess.run([sys.executable, "pixelmirror.py", "--mode", "client", "--host", host, "--port", port])
            except KeyboardInterrupt:
                print("\nClient stopped.")
            break
            
        elif choice == "3":
            print("\nRunning tests...")
            print("-" * 50)
            subprocess.run([sys.executable, "test_setup.py"])
            print("\nPress Enter to continue...")
            input()
            
        elif choice == "4":
            print("Goodbye!")
            break
            
        else:
            print("Invalid choice. Please enter 1, 2, 3, or 4.")

if __name__ == "__main__":
    main()