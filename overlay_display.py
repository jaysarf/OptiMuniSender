import sys
import tkinter as tk
import queue
import threading


BG        = "#1a1a1a"
FG        = "#e0e0e0"
ACCENT    = "#4fc3f7"
DIM       = "#888888"
ON_COLOR  = "#66bb6a"
OFF_COLOR = "#ef5350"
FONT_HDR  = ("Consolas", 20, "bold")
FONT_VAL  = ("Consolas", 20)
FONT_LBL  = ("Consolas", 18)
WIDTH     = 160

# Tk 8.6 on Linux segfaults (libXft) when a colour-emoji font is picked to
# render emoji such as ⛳ / 📌 — use plain text outside Windows.
_EMOJI_OK  = sys.platform == "win32"
TITLE_TEXT = "⛳ OptiSender  ✥" if _EMOJI_OK else "OptiSender  ✥"
PIN_TEXT   = "📌" if _EMOJI_OK else "PIN"


class OverlayDisplay:
    """
    Narrow floating overlay for OptiSender club metrics.
    Runs in its own thread. Update via push_state(state_dict).
    """

    def __init__(self, sim_input=None):
        self._queue = queue.Queue()
        self._sim_input = sim_input
        self._tk_ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def schedule_ui(self, func):
        """Schedule a callable to run on the Tk thread. Safe to call from any thread."""
        self._tk_ready.wait()
        self._root.after(0, func)

    def push_state(self, state: dict):
        """Thread-safe update called from the main OptiSender loop."""
        self._queue.put(state)

    # ------------------------------------------------------------------

    def _run(self):
        self._root = tk.Tk()
        self._tk_ready.set()
        self._root.title("OptiSender")
        self._root.overrideredirect(True)  # remove OS title bar and buttons
        self._root.configure(bg=BG)
        self._root.geometry(f"{WIDTH}x560+13+27")
        self._root.attributes("-topmost", True)
        self._always_on_top = True
        self._left_handed = False
        self._drag_x = 0
        self._drag_y = 0

        self._build_ui()
        self._poll()
        self._root.mainloop()

    def _build_ui(self):
        root = self._root

        # ── Title / drag bar ─────────────────────────────────────────
        title_bar = tk.Frame(root, bg="#2a4a6b", cursor="fleur")
        title_bar.pack(fill="x")
        title_lbl = tk.Label(title_bar, text=TITLE_TEXT, bg="#2a4a6b", fg="#ffffff",
                             font=("Consolas", 11, "bold"), pady=4, cursor="fleur")
        title_lbl.pack(side="left", padx=6)
        self._pin_btn = tk.Button(
            title_bar, text=PIN_TEXT, bg="#2a4a6b", fg="#ffffff",
            font=("Consolas", 9), relief="flat", cursor="hand2",
            activebackground="#3a5a7b", activeforeground="#ffffff",
            command=self._toggle_pin
        )
        self._pin_btn.pack(side="right", padx=4)
        for widget in (title_bar, title_lbl):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>",     self._drag_motion)

        # ── Connection status ─────────────────────────────────────────
        self._conn_lbl = tk.Label(root, text="● Connected", bg=BG,
                                  fg=ON_COLOR, font=("Consolas", 10, "bold"), anchor="center")
        self._conn_lbl.pack(fill="x", padx=5, pady=(4, 1))

        # ── Status row (Ball / Hand) ──────────────────────────────────
        status = tk.Frame(root, bg=BG)
        status.pack(fill="x", padx=5, pady=(2, 1))
        tk.Label(status, text="B:", bg=BG, fg=DIM,
                 font=FONT_LBL).pack(side="left")
        self._ball_lbl = tk.Label(status, text="ON", bg=BG,
                                  fg=ON_COLOR, font=FONT_HDR)
        self._ball_lbl.pack(side="left", padx=(1, 8))
        tk.Label(status, text="H:", bg=BG, fg=DIM,
                 font=FONT_LBL).pack(side="left")
        self._hand_lbl = tk.Label(status, text="RH", bg=BG,
                                  fg="#f57c00", font=FONT_HDR)
        self._hand_lbl.pack(side="left", padx=(1, 0))

        # ── Tuning Editor Button ──────────────────────────────────────
        self._tuning_btn = tk.Button(
            root, text="Tuning", bg="#2a4a6b", fg="#ffffff",
            font=("Consolas", 10, "bold"), relief="flat", cursor="hand2",
            activebackground="#3a5a7b", activeforeground="#ffffff",
            command=self._handle_tuning_click
        )
        self._tuning_btn.pack(fill="x", padx=5, pady=(0, 2))

        _sep(root)

        # ── Club header ───────────────────────────────────────────────
        self._club_lbl = tk.Label(root, text="Waiting…",
                                  bg=BG, fg=ACCENT, font=FONT_HDR,
                                  anchor="center")
        self._club_lbl.pack(fill="x", padx=5, pady=(2, 0))

        _sep(root)

        # ── Club metrics ──────────────────────────────────────────────
        metrics_frame = tk.Frame(root, bg=BG)
        metrics_frame.pack(fill="x", padx=5, pady=2)

        club_rows = [
            ("Club Spd",  "club_speed",   " mph"),
            ("Face Ang",  "face_angle",   ""),
            ("Path",      "swing_path",   ""),
            ("Contact",   "face_contact", ""),
            ("Smash",     "smash_factor", ""),
        ]

        self._vars = {}
        for display_name, key, unit in club_rows:
            cell = tk.Frame(metrics_frame, bg=BG)
            cell.pack(fill="x", pady=2)
            tk.Label(cell, text=display_name, bg=BG, fg=DIM,
                     font=FONT_LBL, anchor="center").pack(fill="x")
            var = tk.StringVar(value="---")
            val_font = ("Consolas", 14) if key == "face_angle" else FONT_VAL
            self._vars[key] = (var, unit)
            tk.Label(cell, textvariable=var, bg=BG, fg=FG,
                     font=val_font, anchor="center").pack(fill="x")

    # ------------------------------------------------------------------

    def _poll(self):
        try:
            while True:
                state = self._queue.get_nowait()
                self._apply_state(state)
        except queue.Empty:
            pass
        self._root.after(50, self._poll)

    def _apply_state(self, s: dict):
        if s.get("_toggle_pin"):
            self._toggle_pin()
            return

        if "simulation_mode" in s:
            sim = s["simulation_mode"]
            self._conn_lbl.config(
                text="◌ Simulation" if sim else "● Connected",
                fg=DIM if sim else ON_COLOR
            )

        using_ball = s.get("using_ball", True)
        self._ball_lbl.config(
            text="ON" if using_ball else "OFF",
            fg=ON_COLOR if using_ball else OFF_COLOR
        )
        left_handed = s.get("left_handed", self._left_handed)
        self._left_handed = left_handed
        self._hand_lbl.config(
            text="LH" if left_handed else "RH",
            fg="#1565c0" if left_handed else "#f57c00"
        )

        club   = s.get("club", "")
        source = s.get("source", "")
        hand   = s.get("hand_label", "RH")
        if club:
            self._club_lbl.config(text=club)

        for key in ("club_speed", "face_angle", "swing_path", "face_contact", "smash_factor"):
            value = s.get(key)
            if key in self._vars and value is not None:
                if self._left_handed:
                    value = self._flip_for_lh(key, value)
                var, unit = self._vars[key]
                var.set(f"{value}{unit}" if unit else str(value))

    _CONTACT_FLIP = {
        "Toe": "Heel", "Heel": "Toe",
        "Extreme Toe": "Extreme Heel", "Extreme Heel": "Extreme Toe",
        "Far Toe": "Far Heel", "Far Heel": "Far Toe",
    }

    def _flip_for_lh(self, key, value):
        if key == "face_angle":
            if value.startswith("Open"):
                return value.replace("Open", "Closed", 1)
            if value.startswith("Closed"):
                return value.replace("Closed", "Open", 1)
        elif key == "swing_path":
            try:
                num = float(value.replace("°", "").replace("+", ""))
                return f"{-num:+.1f}°"
            except ValueError:
                pass
        elif key == "face_contact":
            return self._CONTACT_FLIP.get(value, value)
        return value

    def _handle_tuning_click(self):
        if self._sim_input:
            self._sim_input["toggle_tuning"] = True

    def _toggle_pin(self):
        self._always_on_top = not self._always_on_top
        self._root.attributes("-topmost", self._always_on_top)
        self._pin_btn.config(fg=ACCENT if self._always_on_top else DIM)

    def _drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_motion(self, event):
        x = self._root.winfo_x() + event.x - self._drag_x
        y = self._root.winfo_y() + event.y - self._drag_y
        self._root.geometry(f"+{x}+{y}")


def _sep(parent):
    tk.Frame(parent, bg="#333333", height=1).pack(fill="x", pady=2)
