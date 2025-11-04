import asyncio
import argparse
import tkinter as tk
from io import BytesIO
import threading
import time

from core.capture import ScreenCapture
from core.encoder import JpegEncoder
from core.network_manager import ServerNetworkManager, ClientNetworkManager
from client_ui import ClientUI
from core.debug import Debug
from core.decoder import JpegDecoder

def on_receive(data, ui, debug, decoder):
    debug.log("main", f"Received raw data of size {len(data)}")
    decoded_frame, timestamp = decoder.decode(data)
    
    # Calculate latency
    latency_ms = (time.time() - timestamp) * 1000
    ui.root.after(0, ui.update_latency, latency_ms)

    ui.root.after(0, ui.update_frame, decoded_frame.get_data())

async def run_server(args, debug):
    capture = ScreenCapture(debug=debug)
    encoder = JpegEncoder(debug=debug)
    network_manager = ServerNetworkManager(args.host, args.port, debug=debug)

    await network_manager.start()

    try:
        for frame in capture.capture_gen():
            encoded_frame = encoder.encode(frame)
            await network_manager.send(encoded_frame)
            debug.log("main", f"Sent frame of size {len(encoded_frame)}")
            await asyncio.sleep(0.1)  # Limit frame rate
    finally:
        await network_manager.stop()

async def run_client(args, debug):
    root = tk.Tk()
    ui = ClientUI(root, debug=debug)
    decoder = JpegDecoder(debug=debug)
    network_manager = ClientNetworkManager(args.host, args.port, 
                                           lambda data: on_receive(data, ui, debug, decoder), 
                                           ui.update_connection_status, 
                                           ui.update_latency, 
                                           debug=debug)

    # Create a new event loop for the asyncio tasks
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Start the network manager in the asyncio loop
    loop.create_task(network_manager.start())

    # Function to run the asyncio event loop in a separate thread
    def start_asyncio_loop_in_thread():
        loop.run_forever()

    asyncio_thread = threading.Thread(target=start_asyncio_loop_in_thread, daemon=True)
    asyncio_thread.start()

    # Set a protocol for when the window is closed
    def on_closing():
        debug.log("main", "Tkinter window closing, stopping network manager.")
        asyncio.run_coroutine_threadsafe(network_manager.stop(), loop)
        loop.call_soon_threadsafe(loop.stop)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()

async def main():
    parser = argparse.ArgumentParser(description="PixelMirror v2")
    parser.add_argument("--mode", choices=["server", "client"], required=True)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    debug = Debug(args.debug)

    if args.mode == "server":
        await run_server(args, debug)
    else:
        await run_client(args, debug)

if __name__ == "__main__":
    asyncio.run(main())


