import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sys
import os
import threading
import time

# --- Third-party deps ---
# pip install python-mpv pysubs2
try:
    import mpv
except Exception as e:
    raise SystemExit("python-mpv is required. Install with: pip install python-mpv")

try:
    import pysubs2
except Exception as e:
    raise SystemExit("pysubs2 is required. Install with: pip install pysubs2")


class SubtitleRepeaterPlayer:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Foreign Language Learner Player — MPV")
        self.root.geometry("1000x620")
        self.root.minsize(800, 500)

        # State
        self.sub_intervals = []  # list of dicts: {start: float, end: float}
        self.current_sub_idx = None
        self.repeats_done = 0
        self.repeat_count = tk.IntVar(value=1)  # 1 => no repeat
        self.is_fullscreen = False
        self.poll_interval_ms = 100

        # --- UI ---
        self._build_ui()
        # Ensure video frame is realized before creating MPV (needs a valid window id)
        self.root.update_idletasks()
        self._create_mpv()

        # WM close should fully exit
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)

        # Keyboard shortcuts
        self.root.bind("<space>", lambda e: self.toggle_play_pause())
        self.root.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.root.bind("<F>", lambda e: self.toggle_fullscreen())
        self.root.bind("<Escape>", self._escape_fullscreen)

        # Start polling loop
        self.root.after(self.poll_interval_ms, self._poll_playback)

    def _build_ui(self):
        # Top controls
        top = ttk.Frame(self.root)
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=8)

        self.btn_open = ttk.Button(top, text="Open Video", command=self.open_video_and_sub)
        self.btn_open.pack(side=tk.LEFT)

        self.btn_play = ttk.Button(top, text="Play", command=self.play)
        self.btn_play.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_pause = ttk.Button(top, text="Pause", command=self.pause)
        self.btn_pause.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Label(top, text="Repeat per subtitle:").pack(side=tk.LEFT)
        self.spin_repeat = ttk.Spinbox(top, from_=1, to=20, textvariable=self.repeat_count, width=4)
        self.spin_repeat.pack(side=tk.LEFT, padx=(4, 12))

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        self.btn_full = ttk.Button(top, text="Fullscreen", command=self.toggle_fullscreen)
        self.btn_full.pack(side=tk.LEFT)

        self.btn_exit = ttk.Button(top, text="Exit", command=self.exit_app)
        self.btn_exit.pack(side=tk.RIGHT)

        # Video area (where MPV renders)
        self.video_frame = ttk.Frame(self.root)
        self.video_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=8)

        # A little status bar at the bottom
        self.status = tk.StringVar(value="Idle. Open a video to start.")
        status_bar = ttk.Label(self.root, textvariable=self.status, anchor="w")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _create_mpv(self):
        # Create MPV instance, embedding into the Tk frame via the window id
        self.root.update_idletasks()
        wid = self.video_frame.winfo_id()
        # mpv options:
        #  - osc: on-screen controller (optional)
        #  - input_default_bindings: allow default keybinds in the embedded player
        #  - input_vo_keyboard: allow keyboard focus in the video area
        self.player = mpv.MPV(
            wid=wid,
            vo='gpu',
            osc=True,
            input_default_bindings=True,
            input_vo_keyboard=True,
            ytdl=False,
        )

        # When a new file is loaded, clear subtitle repeat state
        @self.player.event_callback('file-loaded')
        def _on_file_loaded(_):
            self.status.set("Loaded: " + (self.player.filename or "(unknown)"))
            self.current_sub_idx = None
            self.repeats_done = 0

        # Ensure pausing works reliably
        self.player.pause = True

    # --- Core features ---
    def open_video_and_sub(self):
        video_path = filedialog.askopenfilename(
            title="Choose a video",
            filetypes=[
                ("Video files", ".mp4 .mkv .webm .avi .mov .m4v .mpg .mpeg"),
                ("All files", "*.*"),
            ],
        )
        if not video_path:
            return

        # Ask subtitle right after
        sub_path = filedialog.askopenfilename(
            title="Choose a subtitle",
            filetypes=[
                ("Subtitle files", ".srt .ass .ssa .vtt"),
                ("All files", "*.*"),
            ],
        )
        if not sub_path:
            # still load video, but no repeat-by-subtitle logic without subs
            self.sub_intervals = []
        else:
            try:
                self._load_sub_intervals(sub_path)
            except Exception as e:
                messagebox.showerror("Subtitle Error", f"Failed to read subtitle file:\n{e}")
                self.sub_intervals = []

        # Load into MPV
        self.player.command('loadfile', video_path, 'replace')
        if sub_path:
            # Add for display in mpv as well
            try:
                self.player.command('sub-add', sub_path, 'select')
            except Exception:
                pass

        self.status.set("Playing…")
        self.player.pause = False

    def _load_sub_intervals(self, sub_path):
        subs = pysubs2.load(sub_path)
        intervals = []
        for ev in subs.events:
            # times are in milliseconds
            start = ev.start / 1000.0
            end = ev.end / 1000.0
            if end > start:
                intervals.append({"start": start, "end": end})
        # sort just in case
        intervals.sort(key=lambda x: x["start"])
        self.sub_intervals = intervals
        self.current_sub_idx = None
        self.repeats_done = 0
        self.status.set(f"Loaded {len(intervals)} subtitles. Repeat set to {self.repeat_count.get()}x")

    def play(self):
        try:
            self.player.pause = False
            self.status.set("Playing…")
        except Exception:
            pass

    def pause(self):
        try:
            self.player.pause = True
            self.status.set("Paused.")
        except Exception:
            pass

    def toggle_play_pause(self):
        try:
            self.player.pause = not bool(self.player.pause)
            self.status.set("Paused." if self.player.pause else "Playing…")
        except Exception:
            pass

    def toggle_fullscreen(self):
        # Fullscreen the Tk window itself so ALL UI fills the screen
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)
        self.btn_full.configure(text="Exit Fullscreen" if self.is_fullscreen else "Fullscreen")

    def _escape_fullscreen(self, _evt=None):
        if self.is_fullscreen:
            self.toggle_fullscreen()

    def exit_app(self):
        try:
            if hasattr(self, 'player') and self.player:
                # properly quit mpv
                self.player.command('quit')
        except Exception:
            pass
        self.root.destroy()
        sys.exit(0)

    # --- Polling logic for subtitle-repeat ---
    def _poll_playback(self):
        try:
            # If player isn't loaded yet, just reschedule
            t = self.player.time_pos  # may be None if no file loaded
        except Exception:
            t = None

        if t is not None and not self.player.pause and self.sub_intervals:
            self._maybe_repeat_at_subtitle_boundary(t)

        # Keep polling
        self.root.after(self.poll_interval_ms, self._poll_playback)

    def _maybe_repeat_at_subtitle_boundary(self, t_now: float):
        # Determine which subtitle interval we're in
        idx = self._find_current_sub_idx(t_now)

        if idx is None:
            # Outside of any subtitle; reset state so next entry starts fresh
            self.current_sub_idx = None
            self.repeats_done = 0
            return

        if idx != self.current_sub_idx:
            # Entered a new subtitle
            self.current_sub_idx = idx
            self.repeats_done = 0

        # If repeat count is 1, do nothing (no repeat)
        repeat_target = max(1, int(self.repeat_count.get() or 1))
        interval = self.sub_intervals[idx]
        start, end = interval["start"], interval["end"]

        # If we've reached the end of the subtitle, and need to repeat
        # Add a small epsilon to avoid jitter near the exact boundary
        epsilon = 0.03
        if t_now >= (end - epsilon):
            if repeat_target > 1 and self.repeats_done < (repeat_target - 1):
                # Seek back to the start of the subtitle, do NOT unpause if paused
                # Only do this while playing (we checked pause earlier)
                try:
                    self.player.seek(start, reference='absolute')
                    self.repeats_done += 1
                    self.status.set(f"Repeating subtitle {self.repeats_done+1}/{repeat_target}")
                except Exception:
                    pass
            else:
                # Done repeating; let it continue naturally
                pass

    def _find_current_sub_idx(self, t_now: float):
        # Fast path: if we have a current index, check it and neighbors
        if self.current_sub_idx is not None:
            i = self.current_sub_idx
            if 0 <= i < len(self.sub_intervals):
                interval = self.sub_intervals[i]
                if interval["start"] - 0.05 <= t_now < interval["end"] + 0.05:
                    return i
                # try next
                if i + 1 < len(self.sub_intervals):
                    interval2 = self.sub_intervals[i + 1]
                    if interval2["start"] - 0.05 <= t_now < interval2["end"] + 0.05:
                        return i + 1
                # try prev
                if i - 1 >= 0:
                    interval0 = self.sub_intervals[i - 1]
                    if interval0["start"] - 0.05 <= t_now < interval0["end"] + 0.05:
                        return i - 1
        # Fallback: binary search
        lo, hi = 0, len(self.sub_intervals) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            st, en = self.sub_intervals[mid]["start"], self.sub_intervals[mid]["end"]
            if t_now < st:
                hi = mid - 1
            elif t_now >= en:
                lo = mid + 1
            else:
                return mid
        return None


def main():
    root = tk.Tk()
    # Improve ttk styling a bit
    try:
        from tkinter import TclError
        style = ttk.Style(root)
        if sys.platform == "darwin":
            style.theme_use('aqua')
        else:
            # use clam if available
            style.theme_use('clam')
    except Exception:
        pass

    app = SubtitleRepeaterPlayer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
