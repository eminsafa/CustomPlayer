import os
import tkinter as tk
from tkinter import filedialog, messagebox, TclError
import mpv
import pysrt
import sys
import logging
import atexit
from pathlib import Path

# Ensure mpv can be found by adding its path if necessary.
# This is more robust than modifying os.environ directly for the whole session.
# custom_path = r"C:\Program Files\mpv"
# if custom_path not in os.environ["PATH"]:
#     os.environ["PATH"] += os.pathsep + custom_path

# --- Setup Logging ---
log_file_path = Path.home() / "subtitle_repeater_mpv.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, 'w', 'utf-8')
    ]
)


class MPVPlayerApp:
    """A video player application for practicing with subtitles."""
    BG_COLOR = "#212121"
    FRAME_COLOR = "#2c3e50"
    BUTTON_COLOR = "#34495e"
    TEXT_COLOR = "#ecf0f1"
    ACCENT_COLOR = "#3498db"
    ACCENT_COLOR_ACTIVE = "#5dade2"

    def __init__(self, master):
        self.master = master
        master.title("Subtitle Repeater (MPV Edition)")
        master.geometry("850x700")
        master.configure(bg=self.BG_COLOR)
        master.minsize(800, 650)

        self.player = None
        self.video_path = None
        self.subtitles = None
        self.original_subtitles = None
        self.temp_sub_path = None
        self.subtitle_index = 0
        self.repeat_counter = 0
        self.is_repeating_active = False
        self.is_slider_dragging = False
        self.is_handling_repeat = False
        self.repeat_timer_id = None
        self.resume_timer_id = None

        self._setup_fonts()
        self.create_widgets()
        self._initialize_mpv()

        # Set up a robust exit handler
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        atexit.register(self.cleanup)  # Fallback for unexpected exits

    def _setup_fonts(self):
        if sys.platform == "win32":
            font_family = "Segoe UI"
        elif sys.platform == "darwin":
            font_family = "Helvetica"
        else:
            font_family = "Arial"
        self.font_normal = (font_family, 10)
        self.font_large_bold = (font_family, 12, "bold")
        self.font_label = (font_family, 10, "bold")

    def _initialize_mpv(self):
        try:
            logging.info("Initializing MPV instance...")
            temp_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path.cwd()
            self.temp_sub_path = temp_dir / "temp_subs_mpv.srt"

            player_opts = {
                'wid': str(self.video_frame.winfo_id()),
                'log_handler': lambda l, p, t: logging.info(f"mpv: [{p}] {t.strip()}"),
                'input_default_bindings': False,
                'input_vo_keyboard': False,
                'hwdec': 'auto-safe',
                'ytdl': False  # Explicitly disable ytdl for local files
            }
            self.player = mpv.MPV(**player_opts)
            logging.info("MPV instance created successfully.")

            self.player.observe_property('time-pos', self._on_time_pos_change)
            self.player.observe_property('duration', self._on_duration_change)
            self.player.observe_property('pause', self._on_pause_change)
            self.player.observe_property('fullscreen', self._on_fullscreen_change)

            self.master.bind('<Key>', self.handle_keypress)
            self.master.focus_set()

        except Exception as e:
            logging.error(f"Failed to initialize MPV: {e}", exc_info=True)
            messagebox.showerror("MPV Error",
                                 f"Could not initialize MPV. Is it installed and in your PATH?\nError: {e}")
            self.master.destroy()

    def create_widgets(self):
        self.video_frame = tk.Frame(self.master, bg="black")
        self.video_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        time_frame = tk.Frame(self.master, bg=self.FRAME_COLOR)
        time_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.time_label = tk.Label(time_frame, text="00:00:00", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR,
                                   font=self.font_normal)
        self.time_label.pack(side=tk.LEFT, padx=10)
        self.progress_slider = tk.Scale(time_frame, from_=0, to=1000, orient=tk.HORIZONTAL, showvalue=0,
                                        troughcolor='#555', bg=self.FRAME_COLOR, fg=self.TEXT_COLOR,
                                        highlightthickness=0, activebackground=self.ACCENT_COLOR)
        self.progress_slider.pack(fill=tk.X, expand=True, padx=5)
        self.duration_label = tk.Label(time_frame, text="00:00:00", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR,
                                       font=self.font_normal)
        self.duration_label.pack(side=tk.RIGHT, padx=10)
        self.progress_slider.bind("<ButtonPress-1>", self.on_slider_press)
        self.progress_slider.bind("<ButtonRelease-1>", self.on_slider_release)

        controls_container = tk.Frame(self.master, bg=self.FRAME_COLOR)
        controls_container.pack(fill=tk.X, padx=10, pady=5)

        btn_config = {'bg': self.BUTTON_COLOR, 'fg': self.TEXT_COLOR, 'font': self.font_normal, 'padx': 10, 'pady': 5}

        playback_frame = tk.Frame(controls_container, bg=self.FRAME_COLOR)
        playback_frame.pack(side=tk.LEFT, padx=5, pady=5)
        self.prev_subtitle_btn = tk.Button(playback_frame, text="Prev", command=self.previous_subtitle,
                                           state=tk.DISABLED, **btn_config)
        self.prev_subtitle_btn.pack(side=tk.LEFT, padx=(0, 2))
        self.play_pause_btn = tk.Button(playback_frame, text="Play", command=self.play_pause, width=8,
                                        state=tk.DISABLED, **btn_config)
        self.play_pause_btn.pack(side=tk.LEFT, padx=2)
        self.skip_subtitle_btn = tk.Button(playback_frame, text="Next", command=self.skip_subtitle, state=tk.DISABLED,
                                           **btn_config)
        self.skip_subtitle_btn.pack(side=tk.LEFT, padx=(2, 0))

        file_frame = tk.Frame(controls_container, bg=self.FRAME_COLOR)
        file_frame.pack(side=tk.LEFT, padx=20, pady=5)
        self.start_session_btn = tk.Button(file_frame, text="Load Video & Subs", command=self.start_session,
                                           **btn_config)
        self.start_session_btn.pack(side=tk.LEFT, padx=2)

        self.fullscreen_btn = tk.Button(controls_container, text="Fullscreen", command=self.toggle_fullscreen,
                                        **btn_config)
        self.fullscreen_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        volume_frame = tk.Frame(controls_container, bg=self.FRAME_COLOR)
        volume_frame.pack(side=tk.RIGHT, padx=10, pady=5)
        tk.Label(volume_frame, text="Volume", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR, font=self.font_label).pack(
            side=tk.LEFT)
        self.volume_slider = tk.Scale(volume_frame, from_=0, to=100, orient=tk.HORIZONTAL, command=self.set_volume,
                                      showvalue=0, length=120, troughcolor='#555', bg=self.FRAME_COLOR,
                                      highlightthickness=0, activebackground=self.ACCENT_COLOR)
        self.volume_slider.set(100)
        self.volume_slider.pack(side=tk.LEFT, padx=5)

        repeat_frame = tk.Frame(controls_container, bg=self.FRAME_COLOR)
        repeat_frame.pack(side=tk.RIGHT, padx=10, pady=5)
        tk.Label(repeat_frame, text="Repeat", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR, font=self.font_label).pack(
            side=tk.LEFT)
        self.repeat_count = tk.Spinbox(repeat_frame, from_=1, to=10, width=5, justify=tk.CENTER, font=self.font_normal)
        self.repeat_count.pack(side=tk.LEFT, padx=0)

        advanced_frame = tk.LabelFrame(self.master, text="Subtitle Settings", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR,
                                       padx=10, pady=10, font=self.font_label)
        advanced_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        advanced_frame.columnconfigure(2, weight=1)
        tk.Label(advanced_frame, text="Delay (sec):", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR,
                 font=self.font_normal).grid(row=0, column=0, sticky="w", pady=2, padx=(0, 5))
        self.sync_delay_entry = tk.Entry(advanced_frame, width=7, font=self.font_normal)
        self.sync_delay_entry.insert(0, "0.0")
        self.sync_delay_entry.grid(row=0, column=1, sticky="w")
        self.apply_settings_btn = tk.Button(advanced_frame, text="Apply Delay", command=self.process_subtitles,
                                            state=tk.DISABLED, bg=self.ACCENT_COLOR, fg=self.TEXT_COLOR,
                                            font=self.font_normal, activebackground=self.ACCENT_COLOR_ACTIVE,
                                            activeforeground=self.TEXT_COLOR)
        self.apply_settings_btn.grid(row=0, column=2, sticky="e", padx=(20, 0))

    def _on_time_pos_change(self, name, value):
        if value is None or self.player is None: return

        if not self.is_slider_dragging and self.player.duration:
            self.progress_slider.set(int((value / self.player.duration) * 1000))
        self.time_label.config(text=self.sec_to_time_str(value))

        if not (self.is_repeating_active and not self.player.pause and not self.is_handling_repeat):
            return

        if self.subtitles and 0 <= self.subtitle_index < len(self.subtitles):
            current_cue = self.subtitles[self.subtitle_index]
            current_time_ms = int(value * 1000)

            if current_cue.start.ordinal <= current_time_ms < current_cue.end.ordinal:
                time_until_end_ms = current_cue.end.ordinal - current_time_ms
                delay_ms = max(1, time_until_end_ms)
                self.is_handling_repeat = True  # Set lock *before* scheduling
                self.repeat_timer_id = self.master.after(delay_ms, self.handle_repeat)

    def handle_repeat(self):
        self.repeat_timer_id = None
        if not self.is_repeating_active or self.player.pause or not self.subtitles:
            self.is_handling_repeat = False
            return

        try:
            max_repeats = int(self.repeat_count.get())
        except (ValueError, TclError):
            max_repeats = 1  # Default to 1 if spinbox is invalid or destroyed

        if self.repeat_counter < max_repeats - 1:
            self.repeat_counter += 1
            current_cue = self.subtitles[self.subtitle_index]

            # Seek to just before the subtitle starts for a small pre-roll
            seek_time_ms = current_cue.start.ordinal
            if self.subtitle_index > 0:
                prev_cue_end = self.subtitles[self.subtitle_index - 1].end.ordinal
                seek_time_ms = max(prev_cue_end + 1, seek_time_ms - 300)

            self.player.pause = True
            self.player.time_pos = seek_time_ms / 1000.0

            # Briefly pause then resume to allow video to buffer and avoid stutter
            self.resume_timer_id = self.master.after(100, self.resume_playback)
        else:
            # Move to the next subtitle if one exists
            if self.subtitle_index < len(self.subtitles) - 1:
                self.subtitle_index += 1
            # Reset counter for the next subtitle cycle and unlock
            self.repeat_counter = 0
            self.is_handling_repeat = False

    def resume_playback(self):
        self.resume_timer_id = None
        if self.player and self.player.pause:
            self.player.pause = False
        self.is_handling_repeat = False

    def play_pause(self, *args):
        if not self.player or not self.video_path: return
        self.reset_repeat_state()
        self.player.pause = not self.player.pause
        if not self.player.pause and self.player.time_pos:
            self.update_subtitle_index(int(self.player.time_pos * 1000))
        self.master.focus_set()

    def start_session(self):
        self.reset_app_state()
        video_path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=(("Video files", "*.mp4 *.mkv *.avi *.mov"), ("All files", "*.*"))
        )
        if not video_path: return

        subtitle_path = filedialog.askopenfilename(
            title="Select Subtitle File",
            filetypes=(("SubRip files", "*.srt"), ("All files", "*.*"))
        )
        if not subtitle_path: return

        self.video_path = Path(video_path)
        try:
            self.player.loadfile(str(self.video_path), 'replace')
            self.player.pause = True
            self.master.title(f"Subtitle Repeater - {self.video_path.name}")
        except Exception as e:
            messagebox.showerror("Video Error", f"Could not load the video file.\nError: {e}")
            return

        if not self._load_and_process_subtitles(Path(subtitle_path)):
            self.reset_app_state()
            return

        self.play_pause_btn.config(state=tk.NORMAL)
        self.prev_subtitle_btn.config(state=tk.NORMAL)
        self.skip_subtitle_btn.config(state=tk.NORMAL)
        self.apply_settings_btn.config(state=tk.NORMAL)
        self.is_repeating_active = True
        self.master.focus_set()

    def _load_and_process_subtitles(self, path):
        encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1252', 'iso-8859-1', 'cp1251']
        for encoding in encodings_to_try:
            try:
                self.original_subtitles = pysrt.open(path, encoding=encoding)
                logging.info(f"Successfully loaded subtitle with encoding: {encoding}")
                self.process_subtitles()
                return True
            except Exception:
                continue
        messagebox.showerror("Subtitle Error", "Could not decode subtitle file. Please try converting it to UTF-8.")
        return False

    def process_subtitles(self):
        if not self.original_subtitles: return
        self.reset_repeat_state()
        processed_subs = self.original_subtitles.copy()
        try:
            delay_sec = float(self.sync_delay_entry.get())
            if delay_sec != 0.0:
                processed_subs.shift(seconds=delay_sec)
        except ValueError:
            messagebox.showerror("Error", "Invalid delay value. Please enter a number.")
            return

        self.subtitles = processed_subs
        self._apply_processed_subtitles_to_player()
        if self.player.time_pos:
            self.update_subtitle_index(int(self.player.time_pos * 1000))
        self.master.focus_set()

    def _apply_processed_subtitles_to_player(self):
        if not self.subtitles or not self.temp_sub_path: return
        try:
            self.subtitles.save(str(self.temp_sub_path), encoding='utf-8')
            if self.video_path:
                self.player.sub_load(str(self.temp_sub_path))
        except Exception as e:
            messagebox.showerror("File Error", f"Could not create temporary subtitle file.\nError: {e}")

    def reset_app_state(self):
        self.reset_repeat_state()
        if self.player:
            self.player.command('stop')

        self.video_path = None
        self.subtitles = None
        self.original_subtitles = None
        self.subtitle_index = 0
        self.repeat_counter = 0
        self.is_repeating_active = False

        self.play_pause_btn.config(state=tk.DISABLED, text="Play")
        self.prev_subtitle_btn.config(state=tk.DISABLED)
        self.skip_subtitle_btn.config(state=tk.DISABLED)
        self.apply_settings_btn.config(state=tk.DISABLED)
        self.progress_slider.set(0)
        self.time_label.config(text="00:00:00")
        self.duration_label.config(text="00:00:00")
        self.master.title("Subtitle Repeater (MPV Edition)")

    def _on_duration_change(self, name, value):
        if value is not None and value > 0:
            self.duration_label.config(text=self.sec_to_time_str(value))

    def _on_pause_change(self, name, value):
        self.play_pause_btn.config(text="Play" if value else "Pause")

    def _on_fullscreen_change(self, name, value):
        self.fullscreen_btn.config(text="Exit Fullscreen" if value else "Fullscreen")

    def on_slider_press(self, event):
        self.reset_repeat_state()
        self.is_slider_dragging = True

    def on_slider_release(self, event):
        self.is_slider_dragging = False
        if self.player.duration:
            pos = self.progress_slider.get()
            seek_time_sec = self.player.duration * (pos / 1000.0)
            self.player.time_pos = seek_time_sec
            self.update_subtitle_index(int(seek_time_sec * 1000))
        self.master.focus_set()

    def skip_subtitle(self, *args):
        if not self.subtitles or self.subtitle_index >= len(self.subtitles) - 1: return
        self.reset_repeat_state()
        self.subtitle_index += 1
        self.repeat_counter = 0
        self.player.time_pos = self.subtitles[self.subtitle_index].start.ordinal / 1000.0
        if self.player.pause: self.play_pause()
        self.master.focus_set()

    def previous_subtitle(self, *args):
        if not self.subtitles or self.subtitle_index <= 0: return
        self.reset_repeat_state()
        self.subtitle_index -= 1
        self.repeat_counter = 0
        self.player.time_pos = self.subtitles[self.subtitle_index].start.ordinal / 1000.0
        if self.player.pause: self.play_pause()
        self.master.focus_set()

    def update_subtitle_index(self, time_ms):
        """More efficient single-pass search for the correct subtitle index."""
        if not self.subtitles: return
        self.reset_repeat_state()

        # Find the first subtitle that starts *after* the current time
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal > time_ms:
                # We are between cue i-1 and cue i.
                self.subtitle_index = max(0, i - 1)
                self.repeat_counter = 0
                return

        # If no subtitle starts after time_ms, we are at or after the last one.
        self.subtitle_index = len(self.subtitles) - 1
        self.repeat_counter = 0

    def toggle_fullscreen(self, *args):
        if self.player:
            self.player.fullscreen = not self.player.fullscreen
        self.master.focus_set()

    def set_volume(self, value):
        if self.player: self.player.volume = int(value)

    def handle_keypress(self, event):
        if isinstance(event.widget, (tk.Entry, tk.Spinbox)): return
        key = event.keysym.lower()
        if key == 'space' and self.play_pause_btn['state'] == tk.NORMAL:
            self.play_pause()
        elif key == 'f':
            self.toggle_fullscreen()
        elif key == 'right' and self.skip_subtitle_btn['state'] == tk.NORMAL:
            self.skip_subtitle()
        elif key == 'left' and self.prev_subtitle_btn['state'] == tk.NORMAL:
            self.previous_subtitle()

    def sec_to_time_str(self, seconds):
        if seconds is None or seconds < 0: seconds = 0
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{int(h):02}:{int(m):02}:{int(s):02}"

    def reset_repeat_state(self):
        self.cancel_all_timers()
        self.is_handling_repeat = False

    def cancel_all_timers(self):
        if self.repeat_timer_id:
            self.master.after_cancel(self.repeat_timer_id)
            self.repeat_timer_id = None
        if self.resume_timer_id:
            self.master.after_cancel(self.resume_timer_id)
            self.resume_timer_id = None

    def cleanup(self):
        """Cleanly terminate the player and remove temporary files."""
        logging.info("Starting cleanup...")
        if self.player:
            try:
                self.player.terminate()
                self.player = None
                logging.info("MPV player terminated.")
            except Exception as e:
                logging.error(f"Error terminating MPV: {e}")

        if self.temp_sub_path and self.temp_sub_path.exists():
            try:
                self.temp_sub_path.unlink()
                logging.info(f"Removed temp file: {self.temp_sub_path}")
            except OSError as e:
                logging.error(f"Error removing temp file on exit: {e}")

    def on_closing(self):
        """Handles the window close event."""
        logging.info("Window close event triggered.")
        self.cancel_all_timers()
        self.master.destroy()
        logging.info("================== Application Closed ==================")


if __name__ == "__main__":
    logging.info("================== Application Starting ==================")
    root = tk.Tk()
    app = MPVPlayerApp(root)
    root.mainloop()