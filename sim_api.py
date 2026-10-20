"""
Golf simulator API clients.

Two TCP protocols are supported, selected at startup with --target:

  ogs       OpenGolfSim device API (default)       127.0.0.1:3111
  munigolf  GSPro Open Connect v1 (Muni Golf)      127.0.0.1:9210
  gspro     GSPro Open Connect v1 (GSPro,          127.0.0.1:921
            OpenGolf Connect, ...)

Both clients expose the same interface to the main loop:

  maintain(using_ball)      connect / reconnect and send heartbeats
  poll()                    -> list of (event, value) tuples
                               ("club", "<internal club name>")
                               ("result", <dict>)   shot acknowledged by the sim
  send_shot(ball, metrics)  -> True if the payload was sent
  close()
"""
import socket
import json
import select
import time
import math

CONNECT_RETRY_INTERVAL = 5.0  # seconds between connection attempts


class _TcpJsonClient:
    """Shared TCP + streamed-JSON plumbing."""

    label = "API"
    heartbeat_interval = 0.5

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self._buffer = ""
        self._last_attempt = 0.0
        self._last_heartbeat = time.time()
        self._last_error = None

    @property
    def connected(self):
        return self.sock is not None

    def maintain(self, using_ball=True):
        if self.sock is None:
            now = time.time()
            if now - self._last_attempt < CONNECT_RETRY_INTERVAL:
                return
            self._last_attempt = now
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(2.0)
                self.sock.connect((self.host, self.port))
                self._buffer = ""
                print(f"SUCCESS: Connected to {self.label} API at {self.host}:{self.port}")
                self._last_error = None
                self._on_connect(using_ball)
                self._last_heartbeat = time.time()
            except Exception as e:
                # Report each distinct failure once instead of every retry.
                err = str(e)
                if err != self._last_error:
                    print(f"[API] Cannot connect to {self.label} at {self.host}:{self.port}: {err} "
                          f"(retrying every {CONNECT_RETRY_INTERVAL:.0f}s)")
                    self._last_error = err
                self._drop()
            return

        if time.time() - self._last_heartbeat > self.heartbeat_interval:
            try:
                self._send(self._heartbeat_payload(using_ball))
                self._last_heartbeat = time.time()
            except Exception:
                print(f"{self.label} heartbeat failed.")
                self._drop()

    def poll(self):
        events = []
        if self.sock is None:
            return events
        try:
            readable, _, _ = select.select([self.sock], [], [], 0)
            if not readable:
                return events
            new_data = self.sock.recv(4096).decode('utf-8')
            if not new_data:
                self._drop()
                return events
            self._buffer += new_data
            decoder = json.JSONDecoder()
            while self._buffer:
                self._buffer = self._buffer.lstrip()
                if not self._buffer:
                    break
                try:
                    msg, end_index = decoder.raw_decode(self._buffer)
                except json.JSONDecodeError:
                    break
                self._buffer = self._buffer[end_index:]
                if isinstance(msg, dict):
                    events.extend(self._handle_message(msg))
        except Exception as e:
            print(f"{self.label} receive error: {e}")
            self._drop()
        return events

    def send_shot(self, ball, metrics):
        if self.sock is None:
            return False
        try:
            self._send(self._shot_payload(ball, metrics))
            print(f">> Shot data sent to {self.label} API.")
            return True
        except Exception as e:
            print(f"Error sending to {self.label} API: {e}")
            self._drop()
            return False

    def close(self):
        self._drop()

    # ── helpers ───────────────────────────────────────────────────────────

    def _send(self, payload):
        self.sock.sendall(json.dumps(payload).encode('utf-8'))

    def _drop(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    # ── protocol hooks ────────────────────────────────────────────────────

    def _on_connect(self, using_ball):
        pass

    def _heartbeat_payload(self, using_ball):
        raise NotImplementedError

    def _shot_payload(self, ball, metrics):
        raise NotImplementedError

    def _handle_message(self, msg):
        raise NotImplementedError


class OpenGolfSimClient(_TcpJsonClient):
    """OpenGolfSim device API (original OptiSender behaviour)."""

    label = "OpenGolfSim"
    heartbeat_interval = 0.5

    def _on_connect(self, using_ball):
        self._send(self._heartbeat_payload(using_ball))

    def _heartbeat_payload(self, using_ball):
        return {"type": "device", "status": "ready"}

    def _shot_payload(self, ball, metrics):
        return {
            "type": "shot",
            "shot": {
                "ballSpeed": ball.ball_speed,
                "verticalLaunchAngle": ball.launch_angle,
                "horizontalLaunchAngle": ball.launch_direction,
                "spinSpeed": ball.total_spin,
                "spinAxis": ball.spin_axis
            }
        }

    def _handle_message(self, msg):
        if msg.get("status") != 200 and msg.get("code") != 200:
            print(f"\n[API IN] {json.dumps(msg)}")

        if msg.get("type") == "player":
            club_data = msg.get("data", {}).get("club", {})
            cid = club_data.get("id", "")
            if cid:
                if cid == "DR" or cid == "1W": new_club = "Driver"
                elif cid == "PT": new_club = "Putter"
                elif cid in ["AW", "UW"]: new_club = "GW"
                else: new_club = cid
                return [("club", new_club)]

        elif msg.get("type") == "result":
            return [("result", msg.get("data", {}).get("result", {}))]

        return []


# GSPro Open Connect club codes -> OptiSender tuning club names.
# The tuning profile only has one hybrid (5H) and no 2I/1I, so those are
# mapped to the closest available profile.
GSPRO_CLUB_MAP = {
    "DR": "Driver",
    "W2": "3W", "W3": "3W",
    "W4": "5W", "W5": "5W", "W6": "5W", "W7": "5W", "W8": "5W", "W9": "5W",
    "H2": "5H", "H3": "5H", "H4": "5H", "H5": "5H", "H6": "5H", "H7": "5H",
    "H8": "5H", "H9": "5H",
    "I1": "3I", "I2": "3I", "I3": "3I", "I4": "4I", "I5": "5I", "I6": "6I",
    "I7": "7I", "I8": "8I", "I9": "9I",
    "PW": "PW", "GW": "GW", "AW": "GW", "UW": "GW", "SW": "SW", "LW": "LW",
    "PT": "Putter",
}


class GSProConnectClient(_TcpJsonClient):
    """
    GSPro Open Connect API v1 — the "Open Connect API" launch-monitor option
    in Muni Golf, also accepted by GSPro and OpenGolf Connect (:921).

    Messages sent: one JSON object per shot / heartbeat.
    Messages received: {"Code": 200, ...} shot acknowledged,
                       {"Code": 201, "Player": {"Handed", "Club", ...}} player/club change,
                       {"Code": 5xx, ...} error.
    Speeds in mph, angles in degrees, spin in rpm.
    """

    label = "Open Connect"
    heartbeat_interval = 2.0
    device_id = "OptiSender"

    def __init__(self, host, port):
        super().__init__(host, port)
        self._shot_number = 0
        self._awaiting_ack = False

    def _on_connect(self, using_ball):
        self._send(self._heartbeat_payload(using_ball))

    def _base_payload(self):
        return {
            "DeviceID": self.device_id,
            "Units": "Yards",
            "ShotNumber": self._shot_number,
            "APIversion": "1",
        }

    def _heartbeat_payload(self, using_ball):
        payload = self._base_payload()
        payload["ShotDataOptions"] = {
            "ContainsBallData": False,
            "ContainsClubData": False,
            "LaunchMonitorIsReady": True,
            "LaunchMonitorBallDetected": bool(using_ball),
            "IsHeartBeat": True,
        }
        return payload

    def _shot_payload(self, ball, metrics):
        self._shot_number += 1
        self._awaiting_ack = True
        axis_rad = math.radians(ball.spin_axis)
        payload = self._base_payload()
        payload["BallData"] = {
            "Speed": round(ball.ball_speed, 2),
            "SpinAxis": round(ball.spin_axis, 2),
            "TotalSpin": round(ball.total_spin, 1),
            "BackSpin": round(ball.total_spin * math.cos(axis_rad), 1),
            "SideSpin": round(ball.total_spin * math.sin(axis_rad), 1),
            "HLA": round(ball.launch_direction, 2),
            "VLA": round(ball.launch_angle, 2),
        }
        # Sensor face angle is inverted from Trackman (see OptiSender face label);
        # Open Connect expects + = open.
        payload["ClubData"] = {
            "Speed": round(metrics['speed'], 2),
            "Path": round(metrics['path_deg'], 2),
            "FaceToTarget": round(-metrics['face_angle'], 2),
        }
        payload["ShotDataOptions"] = {
            "ContainsBallData": True,
            "ContainsClubData": True,
            "LaunchMonitorIsReady": True,
            "LaunchMonitorBallDetected": True,
            "IsHeartBeat": False,
        }
        return payload

    def _handle_message(self, msg):
        code = msg.get("Code")
        events = []

        if code != 200:
            print(f"\n[API IN] {json.dumps(msg)}")

        player = msg.get("Player")
        if isinstance(player, dict):
            club_code = str(player.get("Club") or "").upper()
            if club_code:
                events.append(("club", GSPRO_CLUB_MAP.get(club_code, club_code)))

        # Code 200 is also returned for heartbeats — only treat it as a shot
        # result when a shot is actually waiting for acknowledgement.
        if code == 200 and self._awaiting_ack:
            self._awaiting_ack = False
            events.append(("result", {}))
        elif isinstance(code, int) and code >= 500:
            self._awaiting_ack = False

        return events


TARGETS = {
    "ogs":      (OpenGolfSimClient,  3111),
    "munigolf": (GSProConnectClient, 9210),
    "gspro":    (GSProConnectClient, 921),
}


def create_client(target, host="127.0.0.1", port=None):
    cls, default_port = TARGETS[target]
    return cls(host, port or default_port)
