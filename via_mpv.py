import tkinter as tk
from tkinter import filedialog, messagebox
# import mpv  <- REMOVED FROM HERE
import pysrt
import os
import sys
import logging
from tkinter import TclError

# --- Setup Logging ---
log_file_path = os.path.join(os.path.expanduser("~"), "subtitle_repeater_mpv.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, 'w', 'utf-8')
    ]
)


class MPVPlayerApp:
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

        # This will be populated by _initialize_mpv
        self.mpv = None

        # Font setup...
        if sys.platform == "win32":
            font_family = "Segoe UI"
        elif sys.platform == "darwin":
            font_family = "Helvetica"
        else:
            font_family = "Arial"
        self.font_normal = (font_family, 10)
        self.font_large_bold = (font_family, 12, "bold")
        self.font_label = (font_family, 10, "bold")

        # State variables...
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

        self.create_widgets()

        # Call the initializer method. It will handle the import and setup.
        if not self._initialize_mpv():
            logging.error("MPV initialization failed. Exiting application.")
            # The error message is shown inside _initialize_mpv, so we just destroy the window.
            master.destroy()
            return

        # Observers setup...
        self.player.observe_property('time-pos', self._on_time_pos_change)
        self.player.observe_property('duration', self._on_duration_change)
        self.player.observe_property('pause', self._on_pause_change)
        self.player.observe_property('fullscreen', self._on_fullscreen_change)

        self.master.bind('<Key>', self.handle_keypress)
        self.master.focus_set()

        try:
            temp_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
            self.temp_sub_path = os.path.join(temp_dir, "temp_subs_mpv.srt")
        except Exception as e:
            logging.error(f"Could not determine temp directory: {e}", exc_info=True)
            messagebox.showerror("Startup Error", "Could not create a path for temporary files.")
            master.destroy()
            return

    # --- MODIFIED METHOD: Handles lazy import and initialization ---
    def _initialize_mpv(self):
        """
        Tries to import and initialize the MPV player. If the DLL is not found,
        it prompts the user to locate it manually.
        Returns True on success, False on failure.
        """
        player_opts = {
            'wid': str(self.video_frame.winfo_id()),
            'input_default_bindings': False,
            'input_vo_keyboard': False,
            'ytdl': False,
            'hwdec': 'auto-safe'
        }

        try:
            # --- LAZY IMPORT ---
            # Try to import and initialize in one go. This is the normal path.
            logging.info("Attempting to import and initialize MPV...")
            import mpv
            self.mpv = mpv  # Store the module reference

            def mpv_log_handler(level, prefix, text):
                if 'dropping frame' in text: return
                logging.info(f"mpv: [{prefix}] {text.strip()}")

            player_opts['log_handler'] = mpv_log_handler

            self.player = self.mpv.MPV(**player_opts)
            logging.info("MPV instance created successfully.")
            return True

        except (ImportError, OSError, AttributeError) as e:
            # Catches:
            # - ImportError: The python-mpv library raises this if the C-lib is not found.
            # - OSError: A lower-level error for the same reason.
            # - AttributeError: Can happen if the import succeeds but mpv.MPV is not found (corrupt install).
            logging.warning(f"Standard MPV initialization failed: {e}")

            # Since the GUI exists, we can now ask the user for help.
            if sys.platform == "win32":
                lib_name = "mpv-1.dll"
                file_types = (("MPV DLL", "*.dll"), ("All files", "*.*"))
            elif sys.platform == "darwin":
                lib_name = "libmpv.dylib"
                file_types = (("MPV Dylib", "*.dylib"), ("All files", "*.*"))
            else:  # Linux
                lib_name = "libmpv.so"
                file_types = (("MPV Shared Object", "*.so"), ("All files", "*.*"))

            user_response = messagebox.askyesno(
                "MPV Library Not Found",
                f"The MPV library ({lib_name}) was not found.\n\n"
                f"This can happen if MPV is not installed or not in your system's PATH. "
                f"Would you like to manually locate the file?"
            )

            if not user_response:
                messagebox.showerror("MPV Error", "MPV is required for this application to run.")
                return False

            dll_path = filedialog.askopenfilename(
                title=f"Please locate {lib_name}",
                filetypes=file_types
            )

            if not dll_path:
                messagebox.showerror("MPV Error", "No MPV library file was selected. The application cannot continue.")
                return False

            # Now, try to initialize again, passing the dll_path directly.
            try:
                logging.info(f"Re-initializing MPV with user-provided path: {dll_path}")
                # We need to re-import here, as the previous attempt failed completely
                # but the user has now provided a path that the library can use.
                import mpv
                self.mpv = mpv

                # The log handler might not be defined if the first block failed early
                if 'log_handler' not in player_opts:
                    def mpv_log_handler(level, prefix, text):
                        if 'dropping frame' in text: return
                        logging.info(f"mpv: [{prefix}] {text.strip()}")

                    player_opts['log_handler'] = mpv_log_handler

                self.player = self.mpv.MPV(dll_path=dll_path, **player_opts)
                logging.info("MPV instance created successfully using custom path.")
                return True
            except Exception as e2:
                logging.error(f"Failed to initialize MPV with path '{dll_path}': {e2}", exc_info=True)
                messagebox.showerror(
                    "MPV Load Error",
                    f"The selected file could not be loaded as an MPV library.\n\nError: {e2}"
                )
                return False

    def create_widgets(self):
        # This function is unchanged
        # UI Setup...
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
        volume_label = tk.Label(volume_frame, text="Volume", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR,
                                font=self.font_label)
        volume_label.pack(side=tk.LEFT)
        self.volume_slider = tk.Scale(volume_frame, from_=0, to=100, orient=tk.HORIZONTAL, command=self.set_volume,
                                      showvalue=0, length=120, troughcolor='#555', bg=self.FRAME_COLOR,
                                      highlightthickness=0, activebackground=self.ACCENT_COLOR)
        self.volume_slider.set(100)
        self.volume_slider.pack(side=tk.LEFT, padx=5)
        repeat_frame = tk.Frame(controls_container, bg=self.FRAME_COLOR)
        repeat_frame.pack(side=tk.RIGHT, padx=10, pady=5)
        repeat_label = tk.Label(repeat_frame, text="Repeat", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR,
                                font=self.font_label)
        repeat_label.pack(side=tk.LEFT)
        self.repeat_count = tk.Spinbox(repeat_frame, from_=1, to=5, width=5, justify=tk.CENTER, font=self.font_normal)
        self.repeat_count.pack(side=tk.LEFT, padx=0)
        advanced_frame = tk.LabelFrame(self.master, text="Subtitle Settings", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR,
                                       padx=10, pady=10, font=self.font_label)
        advanced_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        advanced_frame.columnconfigure(2, weight=1)
        sync_label = tk.Label(advanced_frame, text="Delay (sec):", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR,
                              font=self.font_normal)
        sync_label.grid(row=0, column=0, sticky="w", pady=2, padx=(0, 5))
        self.sync_delay_entry = tk.Entry(advanced_frame, width=7, font=self.font_normal)
        self.sync_delay_entry.insert(0, "0.0")
        self.sync_delay_entry.grid(row=0, column=1, sticky="w")
        self.apply_settings_btn = tk.Button(advanced_frame, text="Apply Delay", command=self.process_subtitles,
                                            state=tk.DISABLED, bg=self.ACCENT_COLOR, fg=self.TEXT_COLOR,
                                            font=self.font_normal, activebackground=self.ACCENT_COLOR_ACTIVE,
                                            activeforeground=self.TEXT_COLOR)
        self.apply_settings_btn.grid(row=0, column=2, sticky="e", padx=(20, 0))

    # --- THE REST OF YOUR CODE IS UNCHANGED AND CORRECT ---

    def _on_time_pos_change(self, name, value):
        if value is None: return
        current_time_sec = value
        current_time_ms = int(current_time_sec * 1000)

        if not self.is_slider_dragging:
            if self.player.duration:
                self.progress_slider.set(int((current_time_sec / self.player.duration) * 1000))
        self.time_label.config(text=self.sec_to_time_str(current_time_sec))

        if self.is_repeating_active and not self.player.pause and not self.is_handling_repeat:
            if self.subtitles and 0 <= self.subtitle_index < len(self.subtitles):
                current_cue = self.subtitles[self.subtitle_index]
                if current_cue.start.ordinal <= current_time_ms < current_cue.end.ordinal:
                    time_until_end_ms = current_cue.end.ordinal - current_time_ms
                    try:
                        delay_ms = int(max(1, time_until_end_ms))
                        self.repeat_timer_id = self.master.after(delay_ms, self.handle_repeat)
                    except (TclError, ValueError) as e:
                        logging.error(f"Failed to set repeat timer: {e}")

    def handle_repeat(self):
        self.is_handling_repeat = True
        self.repeat_timer_id = None

        if not hasattr(self, 'player') or self.player.pause or not self.is_repeating_active or not self.subtitles:
            self.is_handling_repeat = False
            return

        try:
            max_repeats = int(self.repeat_count.get())
        except (ValueError, TclError):
            max_repeats = 1

        if self.repeat_counter < max_repeats - 1:
            self.repeat_counter += 1
            current_cue = self.subtitles[self.subtitle_index]
            base_start_time_ms = current_cue.start.ordinal
            seek_time_ms = base_start_time_ms - 500 if self.subtitle_index > 0 and (base_start_time_ms - 500) > \
                                                       self.subtitles[
                                                           self.subtitle_index - 1].end.ordinal else base_start_time_ms
            final_seek_time_sec = max(0, seek_time_ms / 1000.0)
            logging.info(
                f"Repeating subtitle #{self.subtitle_index + 1} ({self.repeat_counter}/{max_repeats - 1}). Seeking.")
            self.player.pause = True
            self.player.time_pos = final_seek_time_sec

            def delayed_resume():
                self.resume_timer_id = None
                if self.player and self.player.pause:
                    self.player.pause = False
                self.is_handling_repeat = False

            self.resume_timer_id = self.master.after(1000, delayed_resume)
        else:
            if self.subtitle_index < len(self.subtitles) - 1:
                self.subtitle_index += 1
                self.repeat_counter = 0
            self.is_handling_repeat = False

    def play_pause(self, *args):
        if self.is_handling_repeat:
            return
        self.reset_repeat_state()
        self.player.pause = not self.player.pause
        if not self.player.pause and self.player.time_pos:
            self.update_subtitle_index_on_seek(int(self.player.time_pos * 1000))
        self.master.focus_set()

    def start_session(self):
        self.reset_app_state()
        video_path = filedialog.askopenfilename(title="Step 1: Select Video File",
                                                filetypes=(("Video files", "*.mp4 *.mkv *.avi *.mov"),
                                                           ("All files", "*.*")))
        if not video_path:
            logging.info("Video selection cancelled.")
            return
        subtitle_path = filedialog.askopenfilename(title="Step 2: Select Subtitle File",
                                                   filetypes=(("SubRip files", "*.srt"), ("All files", "*.*")))
        if not subtitle_path:
            logging.info("Subtitle selection cancelled.")
            return
        self.video_path = video_path
        logging.info(f"Loading video: {self.video_path}")
        try:
            self.player.pause = True
            self.player.loadfile(self.video_path, 'replace')
            self.master.title(f"Subtitle Repeater - {os.path.basename(self.video_path)}")
        except Exception as e:
            logging.error(f"Error loading video '{self.video_path}': {e}", exc_info=True)
            messagebox.showerror("Video Error", f"Could not load the video file.\nError: {e}")
            return
        if not self.load_and_process_subtitles(subtitle_path):
            self.reset_app_state()
            return
        self.play_pause_btn.config(state=tk.NORMAL)
        self.prev_subtitle_btn.config(state=tk.NORMAL)
        self.skip_subtitle_btn.config(state=tk.NORMAL)
        self.apply_settings_btn.config(state=tk.NORMAL)
        self.is_repeating_active = True
        logging.info("Session loaded successfully. Ready for playback.")
        self.master.focus_set()

    def load_and_process_subtitles(self, path):
        logging.info(f"Loading subtitle: {path}")
        encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1252', 'iso-8859-1', 'cp1251']
        loaded_subs = None
        for encoding in encodings_to_try:
            try:
                loaded_subs = pysrt.open(path, encoding=encoding)
                logging.info(f"Successfully loaded subtitle with encoding: {encoding}")
                break
            except Exception:
                continue
        if not loaded_subs:
            logging.error("Could not decode subtitle file.")
            messagebox.showerror("Subtitle Error", "Could not decode subtitle file. Please try converting it to UTF-8.")
            return False
        self.original_subtitles = loaded_subs
        self.process_subtitles()
        return True

    def process_subtitles(self):
        if not self.original_subtitles: return
        self.reset_repeat_state()
        processed_subs = self.original_subtitles.copy()
        try:
            delay_sec = float(self.sync_delay_entry.get())
            if delay_sec != 0.0:
                processed_subs.shift(seconds=delay_sec)
                logging.info(f"Applied {delay_sec}s delay to subtitles.")
        except ValueError:
            messagebox.showerror("Error", "Invalid delay value. Please enter a number.")
            return
        self.subtitles = processed_subs
        self._apply_processed_subtitles_to_player()
        if self.player.time_pos:
            self.update_subtitle_index_on_seek(int(self.player.time_pos * 1000))
        self.master.focus_set()

    def reset_app_state(self):
        logging.info("Resetting application state.")
        self.reset_repeat_state()
        if hasattr(self, 'player') and self.player:
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
        if value is None or value <= 0: return
        self.duration_label.config(text=self.sec_to_time_str(value))

    def _on_pause_change(self, name, value):
        self.play_pause_btn.config(text="Play" if value else "Pause")

    def _on_fullscreen_change(self, name, value):
        self.fullscreen_btn.config(text="Exit Fullscreen" if value else "Fullscreen")

    def reset_repeat_state(self):
        self.cancel_all_timers()
        self.is_handling_repeat = False

    def on_slider_press(self, event):
        self.reset_repeat_state()
        self.is_slider_dragging = True

    def on_slider_release(self, event):
        self.is_slider_dragging = False
        self.seek()
        self.master.focus_set()

    def seek(self):
        self.reset_repeat_state()
        if not self.player.duration or self.player.duration <= 0: return
        pos = self.progress_slider.get()
        seek_time_sec = self.player.duration * (pos / 1000.0)
        self.player.time_pos = seek_time_sec
        self.update_subtitle_index_on_seek(int(seek_time_sec * 1000))
        logging.info(f"Seek to {self.sec_to_time_str(seek_time_sec)} ({pos / 10}%)")

    def cancel_all_timers(self):
        if self.repeat_timer_id: self.master.after_cancel(self.repeat_timer_id); self.repeat_timer_id = None
        if self.resume_timer_id: self.master.after_cancel(self.resume_timer_id); self.resume_timer_id = None

    def _apply_processed_subtitles_to_player(self):
        if not self.subtitles or not self.temp_sub_path: return False
        try:
            self.subtitles.save(self.temp_sub_path, encoding='utf-8')
            if self.video_path:
                self.player.sub_add(self.temp_sub_path)
                logging.info(f"Processed subtitles set from temp file: {self.temp_sub_path}")
            return True
        except Exception as e:
            logging.error(f"Failed to save or set temporary subtitle file: {e}", exc_info=True)
            messagebox.showerror("File Error", f"Could not create temporary subtitle file.\nError: {e}")
            return False

    def skip_subtitle(self, *args):
        if not self.subtitles or self.subtitle_index >= len(self.subtitles) - 1: return
        self.reset_repeat_state()
        self.subtitle_index += 1
        self.repeat_counter = 0
        self.player.time_pos = max(0, self.subtitles[self.subtitle_index].start.ordinal / 1000.0)
        if self.player.pause: self.play_pause()
        self.master.focus_set()

    def previous_subtitle(self, *args):
        if not self.subtitles or self.subtitle_index <= 0: return
        self.reset_repeat_state()
        self.subtitle_index -= 1
        self.repeat_counter = 0
        self.player.time_pos = max(0, self.subtitles[self.subtitle_index].start.ordinal / 1000.0)
        if self.player.pause: self.play_pause()
        self.master.focus_set()

    def toggle_fullscreen(self, *args):
        self.player.fullscreen = not self.player.fullscreen;
        self.master.focus_set()

    def set_volume(self, value):
        if hasattr(self, 'player') and self.player:
            self.player.volume = int(value)

    def update_subtitle_index_on_seek(self, time_ms):
        if not self.subtitles: return
        self.reset_repeat_state()
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal <= time_ms < cue.end.ordinal: self.subtitle_index = i; self.repeat_counter = 0; return
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal > time_ms: self.subtitle_index = i; self.repeat_counter = 0; return
        self.subtitle_index = len(self.subtitles) - 1 if self.subtitles else 0
        self.repeat_counter = 0

    def sec_to_time_str(self, sec):
        if sec is None or sec < 0: sec = 0
        m, s = divmod(sec, 60);
        h, m = divmod(m, 60)
        return f"{int(h):02}:{int(m):02}:{int(s):02}"

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


if __name__ == "__main__":
    logging.info("================== Application Starting (MPV Edition) ==================")
    root = tk.Tk()
    app = MPVPlayerApp(root)


    def on_closing():
        logging.info("Window closed by user. Terminating MPV.")
        if hasattr(app, 'player') and app.player:
            app.player.terminate()
        if hasattr(app, 'temp_sub_path') and app.temp_sub_path and os.path.exists(app.temp_sub_path):
            try:
                os.remove(app.temp_sub_path)
            except OSError as e:
                logging.error(f"Error removing temp file on exit: {e}")
        root.destroy()
        logging.info("================== Application Closed ==================")


    # Check if the root window still exists. It might have been destroyed in __init__ if MPV failed.
    if 'normal' == root.state():
        root.protocol("WM_DELETE_WINDOW", on_closing)
        root.mainloop()
    else:
        logging.warning("Application did not start because root window was destroyed during initialization.")