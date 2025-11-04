import tkinter as tk
from PIL import Image, ImageTk
from io import BytesIO

from core.debug import Debug

class ClientUI:
    """A class for the client UI."""

    def __init__(self, root, debug: Debug = Debug()):
        self.root = root
        self.root.title("PixelMirror Client")
        self.canvas = tk.Canvas(root, width=800, height=600)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.image_item = self.canvas.create_image(0, 0, anchor=tk.NW)
        self.photo = None
        self._debug = debug

        # Status bar
        self.status_frame = tk.Frame(root, bd=1, relief=tk.SUNKEN)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.connection_status_label = tk.Label(self.status_frame, text="Status: Disconnected", anchor=tk.W)
        self.connection_status_label.pack(side=tk.LEFT, padx=5)

        self.latency_label = tk.Label(self.status_frame, text="Latency: N/A", anchor=tk.E)
        self.latency_label.pack(side=tk.RIGHT, padx=5)

    def update_frame(self, img):
        """Update the frame on the canvas."""
        self._debug.log("ClientUI", f"Updating frame with image of size {img.size}")
        try:
            self.photo = ImageTk.PhotoImage(img)
            self.canvas.itemconfig(self.image_item, image=self.photo)
        except Exception as e:
            self._debug.log("ClientUI", f"Error updating frame: {e}")

    def update_connection_status(self, status: str):
        """Update the connection status display."""
        self.connection_status_label.config(text=f"Status: {status}")
        self._debug.log("ClientUI", f"Connection status updated to: {status}")

    def update_latency(self, latency_ms: float):
        """Update the latency display."""
        self.latency_label.config(text=f"Latency: {latency_ms:.2f} ms")
        self._debug.log("ClientUI", f"Latency updated to: {latency_ms:.2f} ms")

