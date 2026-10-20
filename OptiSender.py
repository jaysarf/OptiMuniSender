import time
import argparse
try:
    from pynput import keyboard
except ImportError:
    keyboard = None
    print("Warning: pynput not found. Install via 'pip install pynput'.")

import queue
import threading
import simulation
from simulation import SimulationWindow
from ballphysics import PhysicsEngine
from opti_reader import OptiReader
from data_filters import OptiFilter
from shot_processor import ShotProcessor
from overlay_display import OverlayDisplay
from tuning_editor import TuningEditor
import sim_api

CLUBS = ["Driver", "3W", "5W", "5H", "3I", "4I", "5I", "6I", "7I", "8I", "9I", "PW", "GW", "SW", "LW", "Putter"]

def main():
    """
    Connects to an OptiShot device and reads swing data packets.
    Includes updated HID report formatting for hardware compatibility.
    """
    parser = argparse.ArgumentParser(description="OptiShot 2 bridge for golf simulators")
    parser.add_argument("--target", choices=sorted(sim_api.TARGETS), default="ogs",
                        help="Simulator API: ogs (OpenGolfSim, default), "
                             "munigolf / gspro (GSPro Open Connect v1)")
    parser.add_argument("--host", default="127.0.0.1", help="Simulator API host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None,
                        help="Simulator API port (default 3111 for ogs, 9210 for munigolf, 921 for gspro)")
    args = parser.parse_args()
    api = sim_api.create_client(args.target, args.host, args.port)

    # Initialize Physics Engine
    physics = PhysicsEngine()
    reader = OptiReader()
    filters = OptiFilter()
    processor = ShotProcessor()
    
    print("--- OptiSender v2 with Physics ---")
    print(f"Simulator API: {api.label} at {api.host}:{api.port}")
    user_club = "Driver" # Default to Driver on start
    print(f"Selected Club: {user_club}")

    simulation_mode = False
    last_keep_alive_time = time.time()
    last_reconnect_attempt = 0
    KEEP_ALIVE_INTERVAL = 30.0   # seconds between keep-alive pings
    RECONNECT_INTERVAL  = 10.0   # seconds between reconnect attempts
    sim_ready_timer     = None   # fallback timer when API result doesn't arrive
    
    # Simulation Input State
    sim_input = {"trigger": False, "club_shift": 0, "toggle_ball": False,
                 "toggle_handed": False, "toggle_pin": False, "toggle_tuning": False}
    using_ball = True
    left_handed = False
    print("Ball Mode: ON (press 'B' to toggle)")
    print("Handedness: Right-Handed (press 'H' to toggle)")

    overlay = OverlayDisplay(sim_input)
    tuning_editor = TuningEditor(overlay)
    sim_packet_queue = queue.Queue()
    sim_window = SimulationWindow(overlay, sim_packet_queue, sim_input)

    ctrl_held = {"value": False}

    def on_press(key):
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            ctrl_held["value"] = True
            return
        if not ctrl_held["value"]:
            return
        vk = getattr(key, 'vk', None)
        if vk is not None:
            vk_upper = vk & ~0x20  # normalize to uppercase virtual key
            if vk_upper == ord('S'):
                sim_input["trigger"] = True
            elif vk_upper == ord('B'):
                sim_input["toggle_ball"] = True
            elif vk_upper == ord('H'):
                sim_input["toggle_handed"] = True
            elif vk_upper == ord('D'):
                sim_input["toggle_pin"] = True
            elif vk_upper == ord('T'):
                sim_input["toggle_tuning"] = True
        if key == keyboard.Key.space:
            sim_input["trigger"] = True
        # Club cycling via keyboard disabled — club selection comes from OGS API
        # if key == keyboard.Key.up:
        #     sim_input["club_shift"] = 1
        # elif key == keyboard.Key.down:
        #     sim_input["club_shift"] = -1

    def on_release(key):
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            ctrl_held["value"] = False

    listener = None

    try:
        if not reader.connect():
            raise ConnectionError("Hardware not found")
        print("\nReady for a swing. Waiting for data...")
    except (IOError, ValueError, ConnectionError) as ex:
        print(f"Connection failed: {ex}")
        print("Device not found or not accessible. Switching to SIMULATION MODE.")
        simulation_mode = True

    overlay.push_state({"using_ball": using_ball, "left_handed": left_handed, "club": user_club, "source": "Ready", "hand_label": "LH" if left_handed else "RH", "simulation_mode": simulation_mode})
    if simulation_mode:
        sim_window.show()

    # Enable keyboard listener
    if keyboard:
        print("\n[INPUT] Keyboard control active (hold Ctrl).")
        # Club cycling via keyboard disabled — club selection comes from OGS API
        # print("  Ctrl+Up / Ctrl+Down : Cycle Club Selection")
        print("  Ctrl+B              : Toggle Ball On/Off")
        print("  Ctrl+H              : Toggle Left/Right Handed")
        print("  Ctrl+D              : Toggle Overlay Always-On-Top")
        print("  Ctrl+T              : Open/Close Tuning Editor")
        if simulation_mode:
            print("  Ctrl+Space / Ctrl+S : Trigger Simulated Swing")
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
    else:
        print("\n[INPUT] 'pynput' not found. Manual controls disabled.")

    try:
        while True:
            # Check for ball toggle
            if sim_input["toggle_ball"]:
                sim_input["toggle_ball"] = False
                using_ball = not using_ball
                print(f"*** BALL MODE: {'ON' if using_ball else 'OFF'} ***")
                overlay.push_state({"using_ball": using_ball, "left_handed": left_handed})

            # Check for handedness toggle
            if sim_input["toggle_handed"]:
                sim_input["toggle_handed"] = False
                left_handed = not left_handed
                print(f"*** HANDEDNESS: {'Left-Handed' if left_handed else 'Right-Handed'} ***")
                overlay.push_state({"using_ball": using_ball, "left_handed": left_handed})
                sim_window.set_handed(left_handed)

            # Check for overlay pin toggle
            if sim_input["toggle_pin"]:
                sim_input["toggle_pin"] = False
                overlay.push_state({"_toggle_pin": True})

            # Check for tuning editor toggle
            if sim_input["toggle_tuning"]:
                sim_input["toggle_tuning"] = False
                tuning_editor.toggle()

            # Reload physics if tuning was saved or reverted
            if tuning_editor.reload_needed.is_set():
                tuning_editor.reload_needed.clear()
                physics = PhysicsEngine()
                print("[TUNING] Physics engine reloaded.")

            # Manual club change disabled — club selection comes from OGS API
            # if sim_input["club_shift"] != 0:
            #     direction = sim_input["club_shift"]
            #     sim_input["club_shift"] = 0
            #     try:
            #         current_idx = CLUBS.index(user_club)
            #     except ValueError:
            #         current_idx = 0
            #     new_idx = (current_idx + direction) % len(CLUBS)
            #     user_club = CLUBS[new_idx]
            #     print(f"*** MANUAL CLUB SELECT: {user_club} ***")
            #     overlay.push_state({"club": user_club, "source": "Manual", "hand_label": "LH" if left_handed else "RH"})

            # Connect / reconnect and send heartbeats
            api.maintain(using_ball)

            # Check for incoming API messages
            for event, value in api.poll():
                if event == "club":
                    if value != user_club:
                        user_club = value
                        print(f"*** CLUB UPDATED TO: {user_club} ***")
                        overlay.push_state({"club": user_club, "source": "API", "hand_label": "LH" if left_handed else "RH"})
                        sim_window.set_club(user_club)

                elif event == "result":
                    if "carry" in value or "total" in value:
                        print(f"\n[API] SHOT RESULT: Carry: {value.get('carry', 0):.1f} | Total: {value.get('total', 0):.1f}")
                    else:
                        print("\n[API] Shot received by simulator.")
                    if sim_ready_timer is not None:
                        sim_ready_timer.cancel()
                    sim_ready_timer = threading.Timer(3.0, sim_window.set_ready)
                    sim_ready_timer.daemon = True
                    sim_ready_timer.start()

            now = time.time()

            # Keep-alive ping to prevent device sleep
            if not simulation_mode and reader.is_connected:
                if now - last_keep_alive_time > KEEP_ALIVE_INTERVAL:
                    reader.keep_alive()
                    reader.set_led_green()
                    last_keep_alive_time = now

            # Reconnect logic: if device disconnected, fall to sim and retry
            if not simulation_mode and not reader.is_connected:
                print("[DEVICE] OptiShot disconnected — switching to SIMULATION MODE.")
                print("  S / ENTER: Trigger Simulated Swing while reconnecting...")
                simulation_mode = True
                last_reconnect_attempt = now
                overlay.push_state({"simulation_mode": True})
                sim_window.show()

            if simulation_mode and not reader.is_connected:
                if now - last_reconnect_attempt > RECONNECT_INTERVAL:
                    last_reconnect_attempt = now
                    print("[DEVICE] Attempting to reconnect to OptiShot...")
                    if reader.reconnect():
                        simulation_mode = False
                        last_keep_alive_time = now
                        print("[DEVICE] OptiShot reconnected — resuming hardware input.")
                        print("\nReady for a swing. Waiting for data...")
                        overlay.push_state({"simulation_mode": False})
                        sim_window.hide()

            # Get Swing Data
            data           = None
            direct_metrics = None
            shot_club      = user_club  # may be overridden by sim window packet
            skip_dup_check = False
            if not simulation_mode:
                data = reader.read_raw()
            else:
                # Manual simulation window packet — direct metrics injection (no HID round-trip)
                try:
                    item      = sim_packet_queue.get_nowait()
                    shot_club = item["club"]
                    skip_dup_check = True  # every button press is intentional
                    if "metrics" in item:
                        direct_metrics = item["metrics"]
                    else:
                        data = item["data"]
                except queue.Empty:
                    pass
                # Keyboard random-shot trigger (Ctrl+Space / Ctrl+S) — still uses HID path
                if data is None and direct_metrics is None and sim_input["trigger"]:
                    print("\n[SIMULATION] Triggering random simulated swing...")
                    data = simulation.generate_simulated_shot(user_club)
                    sim_input["trigger"] = False

            if direct_metrics is not None:
                print(f"--- Valid Swing Detected ---")
                metrics = direct_metrics
            elif data:
                # Duplicate filter applies to hardware and keyboard triggers only.
                if not skip_dup_check and filters.is_duplicate(data):
                    continue
                if not filters.is_valid_swing(data):
                    continue
                print(f"--- Valid Swing Detected ---")
                metrics = processor.process_raw_buffer(data, using_ball=using_ball)
            else:
                metrics = None

            if metrics:
                ball = physics.calculate_ball_flight(metrics, shot_club)

                path_val = metrics['path_deg']
                eff_path = path_val

                # Sensor output is inverted from Trackman for both RH and LH — negate for label.
                face = metrics['face_angle']
                eff_face = -face
                if eff_face > 0.5:
                    face_label = f"Open {abs(face):.1f}°"
                elif eff_face < -0.5:
                    face_label = f"Closed {abs(face):.1f}°"
                else:
                    face_label = f"Square {abs(face):.1f}°"

                # Derive face contact label
                min_b = metrics['raw_min_back']
                max_b = metrics['raw_max_back']
                if max_b == 0:   contact_label = "Missed"
                elif max_b <= 2: contact_label = "Extreme Toe"
                elif max_b == 3: contact_label = "Toe"
                elif min_b >= 5: contact_label = "Far Heel"
                elif min_b == 4: contact_label = "Heel"
                else:            contact_label = "Center"

                # Spin axis is already in world-space convention after physics fix.
                axis = ball.spin_axis
                eff_axis = axis
                if eff_axis > 10:    shape_label = "Slice"
                elif eff_axis > 3:   shape_label = "Fade"
                elif eff_axis > -3:  shape_label = "Straight"
                elif eff_axis > -10: shape_label = "Draw"
                else:                shape_label = "Hook"

                source = 'SIMULATED' if simulation_mode else 'OptiShot'
                hand_label = 'LH' if left_handed else 'RH'
                W = 38
                print("\n" + "=" * W)
                print(f"  CLUB: {shot_club}  [{source}] [{hand_label}]")
                print("=" * W)
                print(f"  {'CLUB METRICS':}")
                print(f"    Club Speed  : {metrics['speed']:.1f} mph")
                print(f"    Face Angle  : {face_label}")
                print(f"    Swing Path  : {eff_path:+.1f}°")
                print(f"    Face Contact: {contact_label}")
                real_smash = (ball.ball_speed / metrics['speed']) if metrics['speed'] > 0 else 0.0
                print(f"    Smash Factor: {real_smash:.2f}")
                print("-" * W)
                print(f"  {'BALL FLIGHT':}")
                print(f"    Ball Speed  : {ball.ball_speed:.1f} mph")
                print(f"    Launch (V)  : {ball.launch_angle:.1f}°")
                print(f"    Launch (H)  : {ball.launch_direction:+.1f}°")
                print(f"    Total Spin  : {ball.total_spin:.0f} rpm")
                print(f"    Spin Axis   : {ball.spin_axis:+.1f}°")
                print(f"    Shot Shape  : {shape_label}")
                print("=" * W + "\n")

                overlay.push_state({
                    "using_ball":   using_ball,
                    "left_handed":  left_handed,
                    "club":         shot_club,
                    "source":       source,
                    "hand_label":   hand_label,
                    "club_speed":   f"{metrics['speed']:.1f}",
                    "face_angle":   face_label,
                    "swing_path":   f"{eff_path:+.1f}°",
                    "face_contact": contact_label,
                    "smash_factor": f"{real_smash:.2f}",
                    "ball_speed":   f"{ball.ball_speed:.1f}",
                    "launch_v":     f"{ball.launch_angle:.1f}",
                    "launch_h":     f"{ball.launch_direction:+.1f}",
                    "total_spin":   f"{ball.total_spin:.0f}",
                    "spin_axis":    f"{ball.spin_axis:+.1f}",
                    "shot_shape":   shape_label,
                })

                api.send_shot(ball, metrics)

                # Device LED Feedback Loop
                if not simulation_mode:
                    try:
                        reader.set_led_red()
                        time.sleep(2.5)
                        reader.set_led_green()
                        last_keep_alive_time = time.time()
                        print("\nReady for a swing. Waiting for data...")
                    except Exception:
                        print("[DEVICE] Communication lost during LED feedback.")
                        reader.is_connected = False
                else:
                    # Cancel any previous fallback and start a new one.
                    # Primary trigger: API "result" message (same as pad LED going green).
                    # Fallback (2.5s): fires if API is not connected or doesn't respond.
                    if sim_ready_timer is not None:
                        sim_ready_timer.cancel()
                    sim_ready_timer = threading.Timer(12.0, sim_window.set_ready)
                    sim_ready_timer.daemon = True
                    sim_ready_timer.start()

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        if not simulation_mode:
            try:
                reader.disconnect()
            except Exception:
                pass
        api.close()
        if listener:
            listener.stop()

if __name__ == '__main__':
    main()