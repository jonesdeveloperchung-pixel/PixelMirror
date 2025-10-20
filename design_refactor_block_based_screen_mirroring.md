
Author: Jones Chung

# 🚀 Design Refactor: Block‑Based Screen Mirroring  
**Goal** – Replace the “full‑screen JPEG per frame” strategy with a *delta‑only* approach that

* Splits the screen into **64 × 64 pixel tiles**  
* Detects which tiles changed since the last frame  
* Sends **only the changed tiles** (plus a small header)  

Result: higher frame‑rate, lower bandwidth, and less CPU overhead on both sides.

---

## 1. High‑Level Flow

```
┌─────────────────────┐          1. Capture          ┌───────────────────────┐
│  Server Screen      │  ──────────────────────►  │  Tile Cache (256x256) │
│  Capture Module     │          2. Tile Δ‑Check    │  (pixel data, hash)   │
└─────────────────────┘          3. Encode Δs      └───────────────────────┘
                                 │
                                 ▼
                          ┌─────────────────────┐
                          │  Network Sender     │
                          └─────────────────────┘
                                 │
                                 ▼
                          ┌─────────────────────┐
                          │  WebSocket Frame    │
                          └─────────────────────┘
                                 │
                                 ▼
                          ┌─────────────────────┐
                          │  Client Receiver    │
                          └─────────────────────┘
                                 │
                                 ▼
                          ┌─────────────────────┐
                          │  Local Tile Cache   │
                          └─────────────────────┘
                                 │
                                 ▼
                          ┌─────────────────────┐
                          │  Canvas Update      │
                          └─────────────────────┘
```

### 1️⃣ Capture & Partition  
* **Server** captures the full screen once per frame from the **selected monitor**.
* Screen is split into a grid of `TILE_SIZE` × `TILE_SIZE` pixels (configurable).
  * If the screen dimensions aren’t multiples of `TILE_SIZE`, the right‑most/bottom tiles are padded or truncated.

### 2️⃣ Detect Changes  
* For each tile, compute a lightweight hash (e.g., MD5 or `numpy`’s `np.sum` + `np.dot`).  
* Compare with the hash stored in the **server’s tile cache** (the previous frame’s cache).  
* Tiles that differ are flagged as *changed*.

### 3️⃣ Build the Delta Payload  
* If *no* tiles changed → send a minimal “empty delta” header (no image data).  
* If *many* tiles changed ( > `FALLBACK_THRESHOLD` of the grid, configurable ) → fall back to sending the **full screen** for that frame (JPEG/PNG).
* Otherwise, construct a **delta frame**:

| Field | Size | Purpose |
|-------|------|---------|
| `frame_id` | 4 B | 32‑bit sequence number (increasing, wrap‑around) |
| `n_tiles` | 2 B | Number of changed tiles in this delta |
| **Per‑tile** | | |
| `x_tile` | 2 B | X index of tile (0‑maxX) |
| `y_tile` | 2 B | Y index of tile (0‑maxY) |
| `tile_w` | 2 B | Width of tile (normally 64, last column may be < 64) |
| `tile_h` | 2 B | Height of tile |
| `data_len` | 4 B | Length of the compressed tile data |
| `data` | `data_len` B | Tile image (PNG or WebP) – compressed **individually** |

> **Why PNG/WebP?**  
> Small tiles compress extremely well with lossless formats; JPEG adds needless artefacts for such a tiny area.

### 3️⃣ Send Over WebSocket  
* The frame is sent as a single binary message (no JSON).  
* `struct.pack('>I H', frame_id, n_tiles)` starts the frame.  
* Each tile header is `struct.pack('>HHHHI', x, y, w, h, data_len)` followed by `data`.

> **Ordering & Reliability** –  
> `frame_id` allows the client to detect missed frames (e.g., drop if `frame_id` isn’t the next expected value).  
> Optional: include a CRC on the entire message for integrity.

---

## 2. Detailed Component Design

| Component | Responsibility | Key Algorithms | Notes |
|-----------|----------------|----------------|-------|
| **ScreenCaptureModule** | Capture the whole screen once per frame from the selected monitor. | `mss.mss().grab()` (or `pyautogui.screenshot()` for full redraws). | Keep resolution constant. Configurable `monitor_id`. |
| **TilePartitioner** | Split image into `TILE_SIZE` × `TILE_SIZE` tiles, pad if necessary. | Simple `numpy` slicing. | Configurable `tile_size`. Cache tile width/height for each position. |
| **HashCache** | Store last‑frame pixel data + hash per tile. | MD5 or `np.tobytes().tobytes()` → `hashlib.sha1`. | Memory: 510 tiles × 64×64 × 3 bytes ≈ 600 kB for a 1080p screen. |
| **DeltaBuilder** | Compare current tile to cache → build list of changed tiles. | `if hash != cache_hash`. | Configurable `fallback_threshold`. Use `np.array_equal` or block‑wise diff. |
| **Encoder** | Compress each changed tile individually (WebP) or full frame (JPEG). | `PIL.Image.save(..., format='WEBP', quality=webp_quality)` or `PIL.Image.save(..., format='JPEG', quality=jpeg_quality)`. | Configurable `webp_quality` and `jpeg_quality`. |
| **Protocol** | Serialize delta frame into binary message. | `struct.pack`, `bytes.join`. | Keep header minimal (< 10 B). |
| **NetworkSender** | Send binary over `websockets`. | `await websocket.send(binary_message)`. | Handles reconnection on client. Configurable `capture_interval` and `reconnect_delay`. |
| **ClientReceiver** | Unpack binary frame, update local screen buffer. | `struct.unpack`, `PIL.Image.frombytes`. | Keeps a full local image buffer. Configurable `default_width` and `default_height`. |
| **CanvasUpdater** | Draw updated local screen buffer onto Tkinter `PhotoImage`. | `img.thumbnail`, `ImageTk.PhotoImage`, `canvas.create_image`/`canvas.itemconfig`. | Redraws entire canvas from updated buffer. |

---

## 3. Algorithmic Highlights

### 3.1 Tile Change Detection (Server)

```python
# pseudocode
def capture_and_diff(prev_tile_hashes, TILE_SIZE, FALLBACK_THRESHOLD):
    full_img = capture_screen()          # e.g., 1920×1080
    tiles = partition(full_img, TILE_SIZE, TILE_SIZE)  # list of (x, y, img)
    changed_tiles = []

    for x, y, img in tiles:
        new_hash = hashlib.sha1(img.tobytes()).digest()
        if prev_tile_hashes[(x, y)] != new_hash:
            compressed = compress_tile(img)    # WebP
            changed_tiles.append((x, y, compressed))
            prev_tile_hashes[(x, y)] = new_hash
    return changed_tiles
```

* **First frame**: send **all** tiles (full screen).
* Subsequent frames: only send `changed_tiles`.
* If `len(changed_tiles) > FALLBACK_THRESHOLD * total_tiles` → fallback to full frame.

### 3.2 Client Side Delta Application

```python
# pseudocode
def apply_delta(local_screen_buffer, delta_tiles):
    for x, y, data in delta_tiles:
        tile_img = decompress_tile(data)   # WebP → RGB array
        local_screen_buffer.paste(tile_img, (x*TILE_SIZE, y*TILE_SIZE))
    return local_screen_buffer

def update_canvas(local_screen_buffer):
    # Resize local_screen_buffer to canvas dimensions
    # Convert to PhotoImage
    # Update single canvas image item
    pass
```

* Maintain a **full‑size `PIL.Image`** locally (`local_screen_buffer`).
* On each received delta frame, overwrite the affected tiles in `local_screen_buffer`.
* After applying all tiles, push the updated `local_screen_buffer` to the Tkinter canvas (redrawing the entire canvas from this buffer).
---

## 4. Handling Edge Cases

| Case | Strategy |
|------|----------|
| **Partial tiles (screen size not divisible by `TILE_SIZE`)** | Pad last column/row with black or ignore the overflow area. |
| **Massive screen changes (e.g., new window covering half the screen)** | Detect > `FALLBACK_THRESHOLD` of tiles changed → send a *full frame* (JPEG/PNG). |
| **Out‑of‑order frames** | Include a monotonically increasing `frame_id`. Client discards older frames if `frame_id` < expected. |
| **Security** | Keep the TLS/TLS handshake unchanged; just modify the payload format. |

---

## 5. Expected Gains

| Metric | Before (JPEG full) | After (Delta) |
|--------|--------------------|---------------|
| **Frame size** (1080p) | ~250 kB (JPEG) | ~10 kB–50 kB (depends on #changed tiles and `webp_quality`/`jpeg_quality`) |
| **Bandwidth** | ~10 fps → 2.5 MB/s | ~10 fps → 200 kB/s (≈ 12× savings, depends on `capture_interval`) |
| **CPU (Server)** | JPEG compression on full screen | Per‑tile compression (smaller images) + hash calculation (fast) |
| **CPU (Client)** | Full repaint each frame | Full repaint from updated buffer (simplified, less flicker) |
| **Latency** | ~100 ms (depends on compression) | ~30–50 ms (tiny tiles, less compression time, depends on `capture_interval`) |

---

## 6. Prototype Implementation Sketch

> **No full code – just a high‑level outline**.  
> All modules are pure functions; swap them into your existing codebase with minimal friction.

```python
# Server side
prev_tile_hashes = defaultdict(lambda: None)   # {(x, y): hash}

async def serve_screen(websocket, TILE_SIZE, FALLBACK_THRESHOLD, CAPTURE_INTERVAL, WEBP_QUALITY, JPEG_QUALITY):
    frame_id = 0
    while True:
        frame_id += 1
        full_img = capture_screen() # from selected monitor
        changed = []
        for x, y, tile in partition(full_img, TILE_SIZE):
            h = hashlib.sha1(tile.tobytes()).digest()
            if prev_tile_hashes[(x, y)] != h:
                data = compress_tile(tile, WEBP_QUALITY)     # WebP
                changed.append((x, y, data))
                prev_tile_hashes[(x, y)] = h

        # Fallback logic
        if len(changed) > FALLBACK_THRESHOLD * total_tiles:
            full_frame_bytes = compress_full_frame(full_img, JPEG_QUALITY) # JPEG
            payload = pack_full_frame(frame_id, full_frame_bytes)
        else:
            payload = pack_delta_payload(frame_id, changed)

        await websocket.send(payload)
        await asyncio.sleep(CAPTURE_INTERVAL)   # Configurable fps
```

```python
# Client side
async def receive(websocket, DEFAULT_WIDTH, DEFAULT_HEIGHT):
    local_img = Image.new('RGB', (DEFAULT_WIDTH, DEFAULT_HEIGHT))
    while True:
        payload = await websocket.recv()
        frame_id, tiles, full_image_bytes = unpack_payload(payload)

        if full_image_bytes:
            local_img = decompress_full_frame(full_image_bytes)
        elif tiles:
            for x, y, data in tiles:
                tile = decompress_tile(data)
                local_img.paste(tile, (x*TILE_SIZE, y*TILE_SIZE))

        canvas.update_from_image(local_img) # Redraw entire canvas from local_img
```

*`pack_header`, `pack_tile`, `unpack_payload` use `struct.pack('>I H', …)` etc.*  

---

## 8. Parameter Reference

This section details all configurable command-line parameters for PixelMirror.

### Server Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `--monitor-id` | `int` | `1` | Specifies the monitor ID to capture. `0` for all monitors (virtual screen), `1` for the primary monitor, `2` for the second, etc. |
| `--tile-size` | `int` | `64` | Defines the size (width and height) of the square tiles used for delta updates in pixels. |
| `--fallback-threshold` | `float` | `0.7` | The percentage of changed tiles (0.0 to 1.0) that triggers a fallback to sending a full JPEG frame instead of a delta frame. |
| `--capture-interval` | `float` | `0.1` | The interval in seconds between screen captures on the server. Lower values increase frame rate but consume more CPU and bandwidth. |
| `--webp-quality` | `int` | `80` | The quality setting (0-100) for WebP compression used for individual tiles in delta frames. Higher values mean better quality but larger tile sizes. |
| `--jpeg-quality` | `int` | `70` | The quality setting (0-100) for JPEG compression used when sending full frames (either as fallback or on explicit redraw). Higher values mean better quality but larger frame sizes. |

### Client Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `--reconnect-delay` | `float` | `1.0` | The initial delay in seconds before the client attempts to reconnect to the server after a disconnection. This delay doubles with each failed attempt, up to a maximum. |
| `--default-width` | `int` | `1920` | The default width in pixels for the client's local screen buffer if a delta frame is received before an initial full frame. |
| `--default-height` | `int` | `1080` | The default height in pixels for the client's local screen buffer if a delta frame is received before an initial full frame. |


1. **Prototype & Benchmark** – Replace your JPEG per‑frame loop with the above pipeline; measure FPS & bandwidth.  
2. **Adaptive Tile Size** – If you notice many tiles changing every frame, switch to `32 × 32` tiles for that period.  
3. **Error Recovery** – If the client misses a delta frame, have it request a full screen on the next message.  
4. **Security** – Keep the WebSocket upgrade (`wss://`) and optional token auth from the original design.  
5. **Testing** – Add unit tests for `pack_tile/unpack_tile` and delta application logic.
---

**Summary:**  
By breaking the screen into 64×64 tiles, hashing them, and sending only the changed ones in a compact binary format, you drastically reduce the data you transmit, lower compression overhead, and accelerate both server and client rendering. This approach should bring noticeable improvements to latency, throughput, and overall user experience in your screen‑sharing tool.
