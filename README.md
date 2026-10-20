# OptiSender

A Python bridge that reads raw swing data from an **OptiShot 2** golf simulator mat over USB HID and forwards calculated ball-flight telemetry to **OpenGolfSim** or to any **GSPro Open Connect v1** simulator (e.g. [Muni Golf](https://munigolfsim.com/), [OpenGolf Connect](https://opengolfapi.org/connect/)) via a TCP socket API.

Logic and packet structure were ported from the [RepliShot](https://github.com/RepliShot) C++ project (`usbcode.cpp`, `shotprocessing.cpp`). The Python layer adds a physics/ball-flight engine, a real-time tuning editor, and a simulation mode for development without hardware.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Setup & Running](#setup--running)
4. [Overlay Display](#overlay-display)
5. [Tuning Editor](#tuning-editor)
6. [Manual Simulation Window](#manual-simulation-window)
7. [Data Flow Architecture](#data-flow-architecture)
8. [HID Hardware Reference](#hid-hardware-reference)
9. [Packet Format (60-byte HID Report)](#packet-format-60-byte-hid-report)
10. [Physics & Tuning Reference](#physics--tuning-reference)
11. [Simulation Mode](#simulation-mode)
12. [Technical Gotchas](#technical-gotchas)
13. [File Reference](#file-reference)

---

## Requirements

| Dependency | Purpose |
|---|---|
| `hidapi` | Low-level USB HID communication with OptiShot 2 |
| `pynput` | Non-blocking keyboard input for sim triggers and hotkeys |
| Python 3.9+ (Windows x64) | Tkinter is included in the standard library |

---

## Installation

### Option A — Download the pre-built executable (recommended for most users)

The easiest way to run OptiSender is to download the latest standalone Windows executable from the **GitHub Releases** page:

**[https://github.com/dffeist/Optisender/releases/latest](https://github.com/dffeist/Optisender/releases/latest)**

1. Download `OptiSender.exe` from the Assets section of the latest release.
2. Place it in any folder alongside `tuning.json` and `tuning_default.json`.
3. Run `OptiSender.exe` — no Python installation required.

> The executable bundles all dependencies. You still need the WinUSB driver for the OptiShot device (see step 3 below).

---

### Option B — Install from source (for developers and advanced users)

The following instructions are for users who want to download and run the original Python source code.

```bash
# 1. Install hidapi
pip install hidapi

# 2. Install remaining dependencies
pip install pynput

# 3. On Windows you may need WinUSB/libusb-1.0 driver installed for the OptiShot device.
#    Use Zadig (https://zadig.akeo.ie) to replace the vendor driver with WinUSB for:
#      VID: 0x0547  PID: 0x3294
```

> If `pynput` is unavailable the program still runs, but Ctrl keyboard shortcuts and simulation triggers are disabled.

---

## Setup & Running

### 1. Start order

OptiSender is designed to run **alongside** OpenGolfSim (or another golf sim UI) at the same time.  
Recommended start order:

1. Launch OpenGolfSim (or your sim front-end) first.
2. Then launch OptiSender — it will connect to the running API automatically.

If OpenGolfSim is not yet running when OptiSender starts, that is fine. OptiSender retries the API connection every 5 seconds; start OpenGolfSim at any point and the next retry window will connect.

### 2. Run OptiSender

```bash
python OptiSender.py                       # OpenGolfSim (default, 127.0.0.1:3111)
python OptiSender.py --target munigolf     # Muni Golf / GSPro Open Connect (127.0.0.1:921)
```

| Option | Default | Description |
|---|---|---|
| `--target` | `ogs` | `ogs` = OpenGolfSim device API. `munigolf` (alias `gspro`) = GSPro Open Connect API v1 |
| `--host` | `127.0.0.1` | Simulator host |
| `--port` | `3111` (ogs) / `921` (munigolf) | Simulator port — use the port shown in the simulator's Open Connect settings if it differs |

With the executable, add the options to a Windows shortcut target, e.g. `OptiSender.exe --target munigolf`.

#### Muni Golf setup

1. In Muni Golf, select the **Open Connect API** launch monitor option.
2. Start OptiSender with `--target munigolf` (add `--port <n>` if Muni Golf listens on a port other than 921).
3. When Muni Golf reports the player's club (`Code 201`), the active club in OptiSender updates automatically. GSPro club codes (`DR`, `W3`, `H4`, `I7`, `PW`, `PT`, …) are mapped to the tuning profiles in `tuning.json`. All hybrids use the `5H` profile, and `I1`/`I2` use `3I`.

Shots are sent as GSPro Open Connect v1 JSON (`BallData`: Speed mph, VLA, HLA, TotalSpin, SpinAxis, BackSpin, SideSpin; `ClubData`: Speed, Path, FaceToTarget). A heartbeat is sent every 2 seconds.

### 3. Startup behaviour

| Condition | Result |
|---|---|
| OptiShot 2 USB detected | **Hardware mode** — live swing data from the mat |
| OptiShot 2 not found | **Simulation mode** — synthetic packets for testing |
| OpenGolfSim not running | Shots processed locally and printed to console; transmitted once API connects |
| OpenGolfSim running | Shot telemetry forwarded in real time |

### 4. Keyboard controls

All shortcuts require holding **Ctrl** first. This avoids conflicts with the sim front-end and OS-level shortcuts.

| Shortcut | Available in | Action |
|---|---|---|
| `Ctrl + Space` or `Ctrl + S` | Simulation mode only | Trigger a simulated swing |
| `Ctrl + B` | Always | Toggle ball detection on / off |
| `Ctrl + H` | Always | Toggle Left / Right handed mode |
| `Ctrl + D` | Always | Toggle overlay window always-on-top |
| `Ctrl + T` | Always | Open / close the Tuning Editor window |

> **Club selection** is driven automatically by the OpenGolfSim API — when you change clubs in-game the active club updates in OptiSender. Manual keyboard cycling has been removed.

> **Note:** Keyboard controls require `pynput` (`pip install pynput`). If pynput is not installed the program still runs — controls are simply disabled.

#### Why Ctrl-modified shortcuts?

OptiSender runs alongside another program that also reads keyboard input. Plain key bindings risk being captured by whichever window has focus. Ctrl-modified shortcuts are almost never claimed by golf sim UIs and avoid common OS intercepts (`Alt+F4`, `Alt+Enter`, `Alt+Tab`). `Ctrl+C` and `Ctrl+Z` are reserved by the OS and intentionally not used.

---

## Overlay Display

A narrow floating window appears in the top-left corner of the screen when OptiSender starts. It shows live shot metrics and device state at a glance.

| Section | Content |
|---|---|
| Connection status | `● Connected` (green) or `◌ Simulation` (grey) |
| B / H indicators | Ball detection ON/OFF and Left/Right handed mode (color-coded: orange = RH, blue = LH) |
| **Tuning button** | Opens the Tuning Editor window (same as `Ctrl+T`) |
| Club name | Current club as reported by OpenGolfSim |
| Metrics grid | Club Speed, Face Angle, Path, Contact, Smash Factor from last shot |

The overlay window can be dragged anywhere on screen. The **📌 pin button** in the title bar toggles always-on-top (`Ctrl+D`).

---

## Tuning Editor

The Tuning Editor lets you adjust ball-flight characteristics in real time without restarting OptiSender. Open it with **`Ctrl+T`** or by clicking the **Tuning** button on the overlay.

### Opening and saving

- **Open:** `Ctrl+T` or click the Tuning button on the overlay. The editor always reads the current `tuning.json` on open so sliders reflect the last saved state.
- **Save:** Click **Save** and confirm the popup. `tuning.json` is written immediately and the physics engine reloads — the next swing uses the new values.
- **Cancel:** Click **Cancel** to discard all unsaved changes and close the window.
- **Revert to Defaults:** Click **Revert to Defaults** and confirm. `tuning_default.json` is copied over `tuning.json` and the physics engine reloads.
- **Unsaved changes guard:** Pressing `Ctrl+T` (or clicking the window's close button) while there are unsaved changes shows a forced-choice dialog — **Save & Close** or **Cancel Changes**. There is no plain dismiss.

### Global settings

#### Speed Calibration (1.00 – 1.20)

A multiplier applied to the raw club head speed reading from the OptiShot sensor before any other calculation. The sensor reads slightly low due to quantization in the timing hardware.

| Value | Effect |
|---|---|
| 1.00 | Raw sensor reading, no correction |
| **1.10** | **Default — compensates for typical sensor underread** |
| 1.20 | Maximum correction — use if ball speed feels too low vs a real launch monitor |

Increasing this value increases **all** of the following: ball speed, carry distance, and roll.

#### Face Compression (0% – 100%)

Controls how aggressively extreme face angle readings from the OptiShot sensor are dampened before they influence spin axis and horizontal launch direction. The OptiShot sensor becomes less reliable as face angle approaches ±30°; this setting reduces the impact of those noisy extreme readings.

The compression uses a `tanh`-based function internally (parameter `k` stored in `tuning.json`). The slider maps to a percentage for clarity:

| Slider | Internal k | Effect on ball flight |
|---|---|---|
| **0%** | k = 200 | No compression — face angle applied at full strength. Most realistic for accurate face readings. |
| **50%** | k = 15 | **Default** — a ±30° face angle reading reduces lateral ball displacement by approximately 50%. Balances realism with sensor noise tolerance. |
| **100%** | k ≈ 0 | Maximum compression — face angle has almost no effect on lateral or spin. Ball flies near-straight regardless of face angle reading. |

> Small face angles (0–10°) where the sensor is reliable are barely affected at any setting. Compression increases progressively for larger readings.

**What it changes in the shot:**
- Lower % → more slice/hook curve, more lateral ball displacement for open/closed face readings
- Higher % → flatter shot shape, less penalty for sensor noise at extreme face angles

### Per-club settings

Select a club from the dropdown. The three sliders update to show that club's current values and their valid range (semi-pro floor to 20-handicap amateur ceiling).

#### Ball Speed — Smash Factor (per club)

The ratio of ball speed to club head speed. A higher smash factor means more energy transfer from club to ball — which means more distance.

| Smash factor range | Who it represents |
|---|---|
| Lower end of range | 20-handicap amateur — off-center contact, energy loss |
| **Tuning.json default** | Mid-handicap amateur baseline |
| Upper end of range | Semi-professional — consistent center contact |

**Effect:** Increasing this value increases ball speed and carry distance for every shot with that club. It does not affect shot shape, spin, or launch angle.

#### Launch Angle / Vla — Vertical Launch Angle (per club)

The base vertical launch angle in degrees, before face angle adds a small adjustment (±a few degrees for very open or closed faces).

| Value direction | Effect |
|---|---|
| Lower angle | Flatter, more penetrating ball flight — more roll, less carry height |
| **Default** | Typical for the club's loft at mid-handicap swing speed |
| Higher angle | Higher, softer ball flight — more carry, less roll |

Each club has its own realistic range: Driver defaults around 12.5°, short irons and wedges are in the 28–35° range, reflecting the natural loft progression of the bag.

**Effect:** Changing this value directly shifts the apex height and carry/roll split of every shot with that club. It does not affect lateral shape or spin rate.

#### Base Spin / BS — Back Spin (per club)

The base back-spin rate in RPM sent to the simulator. Higher spin produces a higher, softer landing ball flight with more stopping power; lower spin produces a flatter, more penetrating flight with more roll.

| Value direction | Effect |
|---|---|
| Lower spin | Flatter flight, more roll-out after landing |
| **Default** | Typical for the club at mid-handicap contact quality |
| Higher spin | Higher flight, steeper descent angle, less roll |

Realistic spin ranges vary significantly by club:

| Club | Typical range |
|---|---|
| Driver | 1,800 – 4,500 rpm |
| 7-iron | 5,000 – 11,000 rpm |
| Pitching Wedge | 7,000 – 15,000 rpm |
| Lob Wedge | 8,500 – 18,000 rpm |

**Effect:** Spin rate affects apex height, carry distance, and stopping power. It does not affect lateral ball direction or shot shape (spin axis controls that).

### How the tuning values interact

```
Club Head Speed (from sensor × Speed Calibration)
    │
    ├─── × BallSpeed (smash factor) ──────────────→ Ball Speed (distance)
    │
    └─── via ShotProcessor → face_angle, path
              │
              ├─── face_angle through Face Compression (tanh) = eff_face
              │
              ├─── Vla + (face_angle × 0.3) ──────────────────→ Vertical Launch Angle
              ├─── (eff_face × 0.85) + (path × 0.15) ─────────→ Horizontal Launch Angle (start direction)
              └─── eff_face − path ────────────────────────────→ Spin Axis (curve direction)
                                                                   (positive = fade/slice RH)
              BS ────────────────────────────────────────────────→ Total Spin (height / stopping power)
```

---

## Manual Simulation Window

When no OptiShot hardware is detected, or if the device disconnects mid-session, OptiSender automatically opens the **Manual Simulation Window**. This window lets you specify exact shot parameters and feed them through the complete shot pipeline — identical to a real pad reading.

### When it appears

| Condition | Behaviour |
|---|---|
| No USB device found at startup | Window opens automatically alongside the overlay |
| Device disconnects mid-session | Window opens automatically; closes when the device reconnects |
| Device reconnects | Window closes automatically; hardware mode resumes |

The window cannot be closed manually — it is tied to the hardware detection state.

### Controls

| Control | Description |
|---|---|
| **Send Shot** | Builds a metrics dict directly from the current slider values and injects it into the physics engine (PhysicsEngine → Overlay → API). Does **not** generate a HID packet — no LED quantization or encoding error is introduced |
| **Right Handed / Left Handed** | Handedness toggle — color-coded orange (RH) / blue (LH), synced with `Ctrl+H` and the overlay indicator |
| **Club** | Select the club for this shot. Defaults to the club reported by OpenGolfSim; can be overridden independently for testing |
| **Club Speed (mph)** | Target club head speed in miles per hour (10–120 mph) |
| **Face Angle (°)** | Club face angle at impact in degrees. Sign convention: **positive = open** (face pointing away from golfer) for both RH and LH |
| **Club Path (°)** | Club path direction at impact in degrees. Sign convention: **positive = in-to-out** (toward target side) for both RH and LH |

### Sign conventions

Both face angle and path follow the golfer's own frame of reference regardless of handedness:

| Golfer | Positive face | Negative face | Positive path | Negative path |
|---|---|---|---|---|
| **Right-handed** | Open — pointing right | Closed — pointing left | In-to-out — left to right | Out-to-in — right to left |
| **Left-handed** | Open — pointing left | Closed — pointing right | In-to-out — right to left | Out-to-in — left to right |

The handedness conversion is applied internally before physics so the same face/path values produce the same ball flight for a RH and LH golfer when their inputs are sign-equivalent.

### Ready state

The **Send Shot** button is disabled (grey) after a shot is sent and shows `◌ Processing…` until the system is ready for the next shot:

- **Primary trigger:** OpenGolfSim sends a `result` message back (shot has been processed and displayed in-game). Ready is signalled 5 seconds after the result to allow the game screen to fully update.
- **Fallback timer:** If the API is not connected or does not respond, the button re-enables automatically after 12 seconds — matching the time needed for the game engine to cycle.

This prevents shots from being sent before the simulator is ready to receive them, mirroring the green LED behaviour of the physical pad.

### How it relates to random simulation

`Ctrl+Space` / `Ctrl+S` still triggers a **random** simulated swing using a weighted shot profile (straight, fade, draw, etc.) at the club's default speed range. The Manual Simulation Window is the precise alternative — every parameter is exact, no randomness is applied.

The Manual Simulation Window injects metrics directly — no HID encoding. `Ctrl+Space` / `Ctrl+S` random shots still encode a HID packet and run through `ShotProcessor → PhysicsEngine → API`.

---

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      OptiShot 2 Mat                     │
│  Back Sensor Row (8 LEDs)  ←  Club crosses back row     │
│  Front Sensor Row (8 LEDs) ←  Club crosses front row    │
└────────────────────┬────────────────────────────────────┘
                     │ USB HID (VID 0x0547 / PID 0x3294)
                     ▼
┌─────────────────────────────────────────────────────────┐
│                     OptiReader                          │
│  opti_reader.py                                         │
│  • Opens device, sends CMD_SENSORS_ON (0x50)            │
│  • Sets LED green (ready)                               │
│  • Reads 60-byte packets (non-blocking)                 │
│  • Controls LED: red (processing) / green (ready)       │
└────────────────────┬────────────────────────────────────┘
                     │ raw list[int], 60 bytes
                     ▼
┌─────────────────────────────────────────────────────────┐
│                     OptiFilter                          │
│  data_filters.py                                        │
│  • Duplicate guard (byte-for-byte compare vs prev)      │
│  • Validity check: packet must contain both 0x81        │
│    (back row) AND 0x4A (front row) opcodes              │
└────────────────────┬────────────────────────────────────┘
                     │ validated raw packet
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   ShotProcessor                         │
│  shot_processor.py                                      │
│                                                         │
│  PASS 1 — Speed & Ball Detection                        │
│  • Iterates 5-byte chunks, accumulates elapsed_time     │
│  • Detects ball hit by gap anomaly (gap > 0x25 then     │
│    confirmed < 0x20 on next 0x4A opcode)                │
│  • Computes swing speed:                                │
│      speed = (SENSOR_SPACING / (elapsed × 18)) × 2236.94│
│  • Back-adjusts elapsed for ball-impact duration        │
│  • Tracks min/max active LED bits across back/front rows│
│  • Derives face contact from back-row LED centroid      │
│                                                         │
│  PASS 2 — Face Angle (Trigonometric)                    │
│  • Per-chunk: measures lateral LED shift between        │
│    consecutive sensor readings (y in LED units)         │
│  • x_travel = speed_per_tick × ticks                   │
│  • angle = atan(x / y) in degrees                       │
│  • Weighted average: (front_avg + 2×back_avg) / 3       │
│  • Sign negated to match Trackman convention:           │
│    positive = open (right) for RH golfer                │
│                                                         │
│  Path: atan2(centroid_front − centroid_back, spacing)   │
│    positive = in-to-out (right) for RH golfer           │
│                                                         │
│  Returns: speed, face_angle, path_deg, contact          │
└────────────────────┬────────────────────────────────────┘
                     │ metrics dict
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   PhysicsEngine                         │
│  ballphysics.py  +  tuning.json                         │
│                                                         │
│  Sign convention (Trackman):                            │
│    face_angle > 0 = open / pointing right (RH)         │
│    path > 0       = in-to-out / rightward (RH)         │
│    Physics is RH-only; LH affects overlay labels only   │
│                                                         │
│  eff_face = k × tanh(face_angle / k)   [compression]   │
│                                                         │
│  Ball Speed   = club_speed × BallSpeed − contact_penalty│
│  Launch Angle = Vla + (face_angle × 0.3)               │
│  Horiz. Angle = (eff_face × 0.85) + (path × 0.15)      │
│  Total Spin   = BS  (per-club base spin from tuning)    │
│  Spin Axis    = eff_face − path                         │
│    positive = fade/slice (RH), negative = draw/hook (RH)│
│                                                         │
│  All base values per-club from tuning.json              │
└────────────────────┬────────────────────────────────────┘
                     │ BallFlight object
                     ▼
┌─────────────────────────────────────────────────────────┐
│              OpenGolfSim TCP API  127.0.0.1:3111        │
│                                                         │
│  Heartbeat (every 0.5 s):                               │
│    {"type":"device","status":"ready"}                   │
│                                                         │
│  Shot payload:                                          │
│    {"type":"shot","shot":{                              │
│       "ballSpeed": <mph>,                               │
│       "verticalLaunchAngle": <deg>,                     │
│       "horizontalLaunchAngle": <deg>,                   │
│       "spinSpeed": <rpm>,                               │
│       "spinAxis": <deg>                                 │
│    }}                                                   │
│                                                         │
│  Inbound events (server-pushed):                        │
│    type=player      → updates active club from API      │
│    type=result      → carry / total / roll displayed    │
└─────────────────────────────────────────────────────────┘
```

---

## HID Hardware Reference

| Property | Value |
|---|---|
| **Vendor ID (VID)** | `0x0547` |
| **Product ID (PID)** | `0x3294` |
| **Read packet size** | 60 bytes |
| **Write report size** | 61 bytes (Report ID `0x00` + 1 command byte + 59 zero bytes) |
| **Back sensor row** | 8 LEDs; bits in `data[i]` or `data[i+1]` |
| **Front sensor row** | 8 LEDs; opcode `0x4A` |
| **Inter-row spacing** | 185 hardware tick units (`SENSOR_SPACING`) |
| **LED lateral spacing** | 15 hardware tick units (`LED_SPACING`) |

### Command Bytes

| Constant | Byte | Effect |
|---|---|---|
| `CMD_SENSORS_ON` | `0x50` | Activates sensor array (sent on connect) |
| `CMD_LED_RED` | `0x51` | LED → red (device busy / processing) |
| `CMD_LED_GREEN` | `0x52` | LED → green (ready for next swing) |
| `CMD_SENSORS_OFF` | `0x80` | Deactivates sensors (sent on disconnect) |

---

## Packet Format (60-byte HID Report)

Data arrives as 12 × 5-byte chunks. Each chunk:

```
Offset +0  Back-row sensor bitmask  (bit N = LED N active)
Offset +1  Front-row sensor bitmask
Offset +2  Opcode
Offset +3  Gap high byte  (elapsed ticks, big-endian)
Offset +4  Gap low byte
```

### Opcodes

| Opcode | Meaning |
|---|---|
| `0x81` | Back sensors — initial trigger (back row, first contact) |
| `0x52` | Back sensors — subsequent / timing update |
| `0x4A` | Front sensors — club has crossed front row |

### Speed Formula

```
speed_mph = (SENSOR_SPACING / (elapsed_ticks × 18)) × 2236.94 × SpeedCalibration
```

`SENSOR_SPACING = 185` hardware ticks. The `18` divisor and `2236.94` multiplier are inherited from RepliShot's `usbcode.cpp`. `SpeedCalibration` (default 1.10) compensates for sensor underread and is adjustable in the Tuning Editor.

### Ball-Hit Detection

A ball contact is confirmed when:
1. A `0x4A` chunk has `gap > 0x25` — marks a *potential* ball read.
2. The *next* `0x4A` chunk has `gap < 0x20` — confirms ball hit.

On confirmation, elapsed time is back-adjusted by `prev_gap` to strip out the ball-impact delay from the speed calculation.

---

## Physics & Tuning Reference

All per-club constants live in [tuning.json](tuning.json). The [Tuning Editor](#tuning-editor) window provides a GUI for editing these values without touching the file directly.

### tuning.json structure

```json
{
    "SpeedCalibration": 1.10,
    "FaceCompression": { "k": 15.0 },

    "Driver": { "BallSpeed": 1.42, "Vla": 12.5, "BS": 3275 },
    "3W":     { "BallSpeed": 1.40, "Vla": 13.5, "BS": 4350 },
    ...
}
```

| Key | Type | Description |
|---|---|---|
| `SpeedCalibration` | Global float | Multiplier applied to raw sensor speed before physics |
| `FaceCompression.k` | Global float | tanh compression parameter (k=15 default, k=200 = no compression) |
| `BallSpeed` | Per-club float | Smash factor — ball speed ÷ club speed ratio |
| `Vla` | Per-club float | Base vertical launch angle in degrees |
| `BS` | Per-club int | Base back-spin in RPM |

### Sign conventions (Trackman-aligned)

| Value | Positive meaning | Negative meaning |
|---|---|---|
| `face_angle` | Open — face pointing right (RH) | Closed — face pointing left (RH) |
| `path_deg` | In-to-out — club traveling right (RH) | Out-to-in — club traveling left (RH) |
| `spin_axis` | Fade / slice (RH) | Draw / hook (RH) |

Physics is right-handed only. For left-handed players the overlay re-labels face angle (Open↔Closed), path sign, and contact (Toe↔Heel) — the physics output and API payload are unchanged.

### Contact penalty

Off-center hits reduce ball speed:

```python
contact_penalty = abs(face_contact) * 0.03
ball_speed = club_speed * (BallSpeed - contact_penalty)
```

`face_contact` is the LED centroid offset from sensor center (range ≈ −3.5 to +3.5). Center contact = 0 penalty.

---

## Simulation Mode

Activated automatically when no HID device is found. Two sub-modes are available:

### Manual Simulation Window (primary)

See [Manual Simulation Window](#manual-simulation-window) above. Provides precise control over every shot parameter.

### Random shot trigger (keyboard)

`Ctrl+Space` or `Ctrl+S` fires a randomised shot via `generate_simulated_shot(club_name)`:

1. Selects a random shot profile (straight, fade, draw, slice, hook, toe, heel) with weighted probabilities.
2. Picks a club speed within the club's natural range.
3. Encodes the target face angle and path as LED bitmasks and timing ticks via `generate_from_metrics()`.
4. Passes the result through `ShotProcessor → PhysicsEngine → API` — the same pipeline as real hardware.

The resulting packet is structurally identical to hardware output — random simulation is a faithful integration test of the HID decode pipeline.

---

## Technical Gotchas

### 1. Windows USB conflict
If you run OptiSender and the official OptiShot software at the same time, both applications attempt exclusive HID access. Whichever opens the device first wins; the other falls into simulation mode.

| Scenario | Result |
|---|---|
| OptiSender running, OEM software closed | Works fine |
| OEM software running, OptiSender starts | Falls into simulation mode |
| Both started simultaneously | Race condition — first to open wins |

### 2. Non-blocking reads need a tight poll loop
`device.set_nonblocking(1)` means `device.read(60)` returns `[]` immediately when no data is available. The main loop sleeps only 10 ms between polls (`time.sleep(0.01)`). Do not increase this significantly or short-duration swing packets may be missed.

### 3. Duplicate packet guard is byte-exact
`OptiFilter.is_duplicate` does a full 60-byte equality check. The OptiShot hardware can re-deliver the same packet on subsequent reads before the next swing. If shots are being silently dropped, verify the filter isn't matching near-identical but distinct packets.

### 4. Three Tk windows share one event loop
The overlay display (`overlay_display.py`), the Tuning Editor (`tuning_editor.py`), and the Manual Simulation Window (`simulation.py`) all run inside a single `Tk()` instance — each opens as a `Toplevel` child of the overlay's root. This avoids the Python 3.13 restriction against multiple `Tk()` instances in different threads. All UI scheduling is done via `overlay.schedule_ui()` which posts callables onto the overlay's Tk event loop.

### 5. Physics reloads on tuning save
When the Tuning Editor saves or reverts, it sets `tuning_editor.reload_needed` (a `threading.Event`). The main OptiSender loop checks this flag each iteration and recreates `PhysicsEngine()`, which re-reads `tuning.json`. The reload happens within one loop cycle (≤10 ms) of the save.

---

## File Reference

| File | Role |
|---|---|
| [OptiSender.py](OptiSender.py) | Entry point; main loop, command-line options, keyboard handler, physics reload |
| [sim_api.py](sim_api.py) | Simulator API clients: OpenGolfSim and GSPro Open Connect v1 (Muni Golf) |
| [opti_reader.py](opti_reader.py) | HID device open/close, command writes, raw 60-byte reads |
| [data_filters.py](data_filters.py) | Duplicate and validity filters before processing |
| [shot_processor.py](shot_processor.py) | 60-byte packet parser; speed, face angle, path, contact |
| [ballphysics.py](ballphysics.py) | Ball-flight physics engine; tanh face compression; reads `tuning.json` |
| [simulation.py](simulation.py) | `generate_from_metrics()` — HID packet for random shot profiles; `generate_simulated_shot()` — weighted random profiles; `SimulationWindow` — manual simulation GUI (direct metrics injection, no HID encoding) |
| [overlay_display.py](overlay_display.py) | Floating metrics overlay; Tk daemon thread; Tuning button |
| [tuning_editor.py](tuning_editor.py) | Real-time tuning GUI; per-club sliders; save/cancel/revert |
| [tuning.json](tuning.json) | Active tuning — per-club smash factor, launch angle, spin, global calibration |
| [tuning_default.json](tuning_default.json) | Factory defaults — restored by Revert to Defaults in the Tuning Editor |
| [api_monitor.py](api_monitor.py) | Standalone API traffic monitor; passive listener |
| [build.bat](build.bat) | PyInstaller onedir build script for standalone Windows exe |
