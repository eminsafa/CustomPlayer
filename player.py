import tkinter as tk
from tkinter import filedialog, messagebox
import vlc
import pysrt
import os
import sys
import logging

# --- Setup Logging ---
log_file_path = os.path.join(os.path.expanduser("~"), "subtitle_repeater.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, 'w', 'utf-8')
    ]
)


class VLCPlayerApp:
    """
    A video player with a focus on flicker-free repeating of subtitle lines,
    featuring a refined UI and smarter repeat logic.
    """
    # --- NEW: Design Constants ---
    BG_COLOR = "#212121"
    FRAME_COLOR = "#2c3e50"
    BUTTON_COLOR = "#34495e"
    TEXT_COLOR = "#ecf0f1"
    ACCENT_COLOR = "#3498db"
    ACCENT_COLOR_ACTIVE = "#5dade2"

    def __init__(self, master):
        self.master = master
        master.title("Subtitle Repeater")
        master.geometry("850x700")
        master.configure(bg=self.BG_COLOR)
        # Set a minimum size for better layout management
        master.minsize(800, 650)

        # --- NEW: Font Setup ---
        if sys.platform == "win32":
            font_family = "Segoe UI"
        elif sys.platform == "darwin":
            font_family = "Helvetica"
        else:  # Linux and others
            font_family = "Arial"

        self.font_normal = (font_family, 10)
        self.font_large_bold = (font_family, 12, "bold")
        self.font_label = (font_family, 10, "bold")

        # --- State Variables ---
        self.video_path = None
        self.subtitle_path = None
        self.subtitles = None
        self.original_subtitles = None
        self.temp_sub_path = None
        self.subtitle_index = 0
        self.repeat_counter = 0
        self.is_paused = True
        self.is_repeating_active = False
        self.is_fullscreen = False
        self.is_slider_dragging = False
        self.repeat_timer_id = None
        self.resume_timer_id = None

        try:
            logging.info("Initializing VLC instance...")
            vlc_args = ["--no-xlib"]  # Helps with performance and compatibility on some Linux systems
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
                plugin_path = os.path.join(base_path, 'plugins')
                if os.path.exists(plugin_path):
                    os.environ['VLC_PLUGIN_PATH'] = plugin_path
                    logging.info(f"VLC_PLUGIN_PATH set to: {plugin_path}")

            self.vlc_instance = vlc.Instance(vlc_args)
            self.player = self.vlc_instance.media_player_new()
            logging.info("VLC instance and player created successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize VLC: {e}", exc_info=True)
            messagebox.showerror("VLC Error", f"Could not initialize VLC. Is it installed?\nError: {e}")
            master.destroy()
            return

        self.create_widgets()
        self.master.bind('<Key>', self.handle_keypress)
        self.master.focus_set()

        try:
            temp_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
            self.temp_sub_path = os.path.join(temp_dir, "temp_subs.srt")
        except Exception as e:
            logging.error(f"Could not determine temp directory: {e}", exc_info=True)
            messagebox.showerror("Startup Error", "Could not create a path for temporary files.")
            master.destroy()
            return

        self.master.after(100, self.update_ui)

    def create_widgets(self):
        # --- Video Frame ---
        self.video_frame = tk.Frame(self.master, bg="black")
        self.video_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        # --- Progress Bar and Time Display ---
        time_frame = tk.Frame(self.master, bg=self.FRAME_COLOR)
        time_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.time_label = tk.Label(time_frame, text="00:00:00", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR,
                                   font=self.font_normal)
        self.time_label.pack(side=tk.LEFT, padx=10)
        self.progress_slider = tk.Scale(
            time_frame, from_=0, to=1000, orient=tk.HORIZONTAL, showvalue=0,
            troughcolor='#555', bg=self.FRAME_COLOR, fg=self.TEXT_COLOR,
            highlightthickness=0, activebackground=self.ACCENT_COLOR
        )
        self.progress_slider.pack(fill=tk.X, expand=True, padx=5)
        self.duration_label = tk.Label(time_frame, text="00:00:00", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR,
                                       font=self.font_normal)
        self.duration_label.pack(side=tk.RIGHT, padx=10)
        self.progress_slider.bind("<ButtonPress-1>", self.on_slider_press)
        self.progress_slider.bind("<ButtonRelease-1>", self.on_slider_release)

        # --- Main Controls Container ---
        controls_container = tk.Frame(self.master, bg=self.FRAME_COLOR)
        controls_container.pack(fill=tk.X, padx=10, pady=5)

        # --- NEW: Reorganized Controls into Frames ---
        btn_config = {'bg': self.BUTTON_COLOR, 'fg': self.TEXT_COLOR, 'font': self.font_normal, 'padx': 10, 'pady': 5}

        # Playback Controls (Left)
        playback_frame = tk.Frame(controls_container, bg=self.FRAME_COLOR)
        playback_frame.pack(side=tk.LEFT, padx=5, pady=5)
        self.prev_subtitle_btn = tk.Button(playback_frame, text="Prev", command=self.previous_subtitle,
                                           state=tk.DISABLED, **btn_config)
        self.prev_subtitle_btn.pack(side=tk.LEFT, padx=(0, 2))
        self.play_pause_btn = tk.Button(playback_frame, text="Play", command=self.play_pause, width=8,
                                        **btn_config)
        self.play_pause_btn.pack(side=tk.LEFT, padx=2)
        self.skip_subtitle_btn = tk.Button(playback_frame, text="Next", command=self.skip_subtitle, state=tk.DISABLED,
                                           **btn_config)
        self.skip_subtitle_btn.pack(side=tk.LEFT, padx=(2, 0))

        # File Loading Controls (Left)
        file_frame = tk.Frame(controls_container, bg=self.FRAME_COLOR)
        file_frame.pack(side=tk.LEFT, padx=20, pady=5)
        self.load_video_btn = tk.Button(file_frame, text="Load Video", command=self.load_video, **btn_config)
        self.load_video_btn.pack(side=tk.LEFT, padx=2)
        self.load_subs_btn = tk.Button(file_frame, text="Load Subs", command=self.load_subtitle, **btn_config)
        self.load_subs_btn.pack(side=tk.LEFT, padx=2)

        # Fullscreen Button (Right)
        self.fullscreen_btn = tk.Button(controls_container, text="Fullscreen", command=self.toggle_fullscreen,
                                        **btn_config)
        self.fullscreen_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        # Volume Controls (Right)
        volume_frame = tk.Frame(controls_container, bg=self.FRAME_COLOR)
        volume_frame.pack(side=tk.RIGHT, padx=10, pady=5)
        volume_label = tk.Label(volume_frame, text="Volume", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR,
                                font=self.font_label)
        volume_label.pack(side=tk.LEFT)
        self.volume_slider = tk.Scale(
            volume_frame, from_=0, to=100, orient=tk.HORIZONTAL, command=self.set_volume,
            showvalue=0, length=120, troughcolor='#555', bg=self.FRAME_COLOR,
            highlightthickness=0, activebackground=self.ACCENT_COLOR
        )
        self.volume_slider.set(100)
        self.volume_slider.pack(side=tk.LEFT, padx=5)

        # Repeat Controls (Right)
        repeat_frame = tk.Frame(controls_container, bg=self.FRAME_COLOR)
        repeat_frame.pack(side=tk.RIGHT, padx=10, pady=5)
        repeat_label = tk.Label(repeat_frame, text="Repeat", fg=self.TEXT_COLOR, bg=self.FRAME_COLOR,
                                font=self.font_label)
        repeat_label.pack(side=tk.LEFT)
        self.repeat_count = tk.Spinbox(repeat_frame, from_=1, to=5, width=50, justify=tk.CENTER, font=self.font_normal)
        self.repeat_count.pack(side=tk.LEFT, padx=0)

        # --- Subtitle Settings Frame ---
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
        self.apply_settings_btn = tk.Button(
            advanced_frame, text="Apply Delay", command=self.process_subtitles,
            state=tk.DISABLED, bg=self.ACCENT_COLOR, fg=self.TEXT_COLOR, font=self.font_normal,
            activebackground=self.ACCENT_COLOR_ACTIVE, activeforeground=self.TEXT_COLOR
        )
        self.apply_settings_btn.grid(row=0, column=2, sticky="e", padx=(20, 0))

    def on_slider_press(self, event):
        self.cancel_all_timers()
        self.is_slider_dragging = True

    def on_slider_release(self, event):
        self.is_slider_dragging = False
        self.seek()
        self.master.focus_set()

    def seek(self):
        self.cancel_all_timers()
        if not self.player.get_media() or self.player.get_length() <= 0:
            return
        pos = self.progress_slider.get()
        time_ms = int(self.player.get_length() * (pos / 1000.0))
        self.player.set_time(max(0, time_ms))
        self.update_subtitle_index_on_seek(time_ms)
        logging.info(f"Seek to {self.ms_to_time_str(time_ms)} ({pos / 10}%)")

    def update_ui(self):
        try:
            if self.player.get_media() and self.player.get_length() > 0:
                current_time = self.player.get_time()
                if not self.is_slider_dragging:
                    self.progress_slider.set(int(self.player.get_position() * 1000))
                self.time_label.config(text=self.ms_to_time_str(current_time))
                self.duration_label.config(text=self.ms_to_time_str(self.player.get_length()))

                if self.is_fullscreen != self.master.attributes('-fullscreen'):
                    self.is_fullscreen = self.master.attributes('-fullscreen')
                    self.update_fullscreen_button()

                if self.is_repeating_active and not self.is_paused and self.repeat_timer_id is None and self.resume_timer_id is None:
                    if self.subtitles and 0 <= self.subtitle_index < len(self.subtitles):
                        current_cue = self.subtitles[self.subtitle_index]
                        if current_cue.start.ordinal <= current_time < current_cue.end.ordinal:
                            time_until_end = current_cue.end.ordinal - current_time
                            self.repeat_timer_id = self.master.after(int(time_until_end), self.handle_repeat)

            self.master.after(480, self.update_ui)
        except tk.TclError:
            logging.info("TclError caught, likely window closed. Shutting down UI loop.")
        except Exception as e:
            logging.error(f"Unexpected error in UI update loop: {e}", exc_info=True)

    def handle_repeat(self):
        """
        Handles repeating a subtitle. Seeks back, waits 1 second, then resumes.
        Tries to start 0.5s early if there's no collision with the previous subtitle.
        """
        self.repeat_timer_id = None
        if self.is_paused or not self.is_repeating_active or not self.subtitles:
            return

        try:
            max_repeats = int(self.repeat_count.get())
        except (ValueError, tk.TclError):
            max_repeats = 1

        if self.repeat_counter < max_repeats - 1:
            self.repeat_counter += 1
            current_cue = self.subtitles[self.subtitle_index]

            # --- IMPROVED: Calculate smart seek time ---
            base_start_time = current_cue.start.ordinal
            seek_time = base_start_time
            early_start_time = base_start_time - 500  # 0.5 seconds early

            can_start_early = True
            if self.subtitle_index > 0:
                previous_cue = self.subtitles[self.subtitle_index - 1]
                if early_start_time <= previous_cue.end.ordinal:
                    can_start_early = False
                    logging.info(
                        f"Early start for sub #{self.subtitle_index + 1} collides with previous. Using normal start time.")

            if can_start_early:
                seek_time = early_start_time
                logging.info(f"Using early start time for sub #{self.subtitle_index + 1}")

            final_seek_time = max(0, seek_time)
            # --- END IMPROVEMENT ---

            logging.info(
                f"Repeating subtitle #{self.subtitle_index + 1} (Rep {self.repeat_counter}/{max_repeats - 1}). Seeking to {self.ms_to_time_str(final_seek_time)}.")

            # 1. Pause the video for a smooth seek.
            self.player.set_pause(1)
            # 2. Seek to the calculated time.
            self.player.set_time(int(final_seek_time))

            # 3. Schedule the video to play again after a 1-second delay.
            def delayed_resume():
                self.resume_timer_id = None
                if self.player and not self.is_paused:
                    logging.info("Resuming play after 1s delay.")
                    self.player.play()

            self.resume_timer_id = self.master.after(1500, delayed_resume)

        else:  # Done repeating, advance to the next subtitle.
            if self.subtitle_index < len(self.subtitles) - 1:
                self.subtitle_index += 1
                self.repeat_counter = 0
                logging.info(f"Advancing to subtitle #{self.subtitle_index + 1}")

    def cancel_all_timers(self):
        """Cancels any pending repeat or resume actions."""
        if self.repeat_timer_id:
            self.master.after_cancel(self.repeat_timer_id)
            self.repeat_timer_id = None
        if self.resume_timer_id:
            self.master.after_cancel(self.resume_timer_id)
            self.resume_timer_id = None

    def load_video(self, *args):
        self.cancel_all_timers()
        path = filedialog.askopenfilename(title="Select Video File",
                                          filetypes=(("Video files", "*.mp4 *.mkv *.avi *.mov"), ("All files", "*.*")))
        if not path: return

        self.video_path = path
        logging.info(f"Loading video: {self.video_path}")
        try:
            media = self.vlc_instance.media_new_path(self.video_path)
            self.player.set_media(media)

            def embed_video():
                video_widget_id = self.video_frame.winfo_id()
                if sys.platform == "win32":
                    self.player.set_hwnd(video_widget_id)
                elif sys.platform == "darwin":
                    self.player.set_nsobject(video_widget_id)
                else:
                    self.player.set_xwindow(video_widget_id)

                if self.subtitles: self._apply_processed_subtitles_to_player()
                self.play_pause()
                self.master.focus_set()

            self.master.after(200, embed_video)
            self.master.title(f"Subtitle Repeater - {os.path.basename(self.video_path)}")
        except Exception as e:
            logging.error(f"Error loading video '{self.video_path}': {e}", exc_info=True)
            messagebox.showerror("Video Error", f"Could not load the video file.\nError: {e}")

    def load_subtitle(self, *args):
        path = filedialog.askopenfilename(title="Select Subtitle File",
                                          filetypes=(("SubRip files", "*.srt"), ("All files", "*.*")))
        if not path: return

        self.subtitle_path = path
        logging.info(f"Loading subtitle: {self.subtitle_path}")
        encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1252', 'iso-8859-1', 'cp1251']
        loaded_subs = None
        for encoding in encodings_to_try:
            try:
                loaded_subs = pysrt.open(self.subtitle_path, encoding=encoding)
                logging.info(f"Successfully loaded subtitle with encoding: {encoding}")
                break
            except Exception as e:
                logging.debug(f"Failed to load subtitle with encoding {encoding}: {e}")
                continue

        if loaded_subs:
            self.original_subtitles = loaded_subs
            self.apply_settings_btn.config(state=tk.NORMAL)
            self.process_subtitles()
        else:
            logging.error("Could not decode subtitle file with any common encodings.")
            messagebox.showerror("Subtitle Error", "Could not decode subtitle file. Please try converting it to UTF-8.")
        self.master.focus_set()

    def process_subtitles(self):
        if not self.original_subtitles:
            logging.warning("process_subtitles called with no original subtitles loaded.")
            messagebox.showwarning("Warning", "No subtitles loaded to process.")
            return

        self.cancel_all_timers()
        logging.info("Processing subtitles with new settings...")
        processed_subs = self.original_subtitles.copy()
        info_message = "Settings applied."

        try:
            delay_sec = float(self.sync_delay_entry.get())
            if delay_sec != 0.0:
                processed_subs.shift(seconds=delay_sec)
                logging.info(f"Shifted all cues by {delay_sec} seconds (relative to original).")
                info_message = f"Subtitles shifted by {delay_sec} seconds."
        except ValueError:
            logging.error(f"Invalid delay value entered: '{self.sync_delay_entry.get()}'")
            messagebox.showerror("Error", "Invalid delay value. Please enter a number.")
            return

        self.subtitles = processed_subs
        if self._apply_processed_subtitles_to_player():
            messagebox.showinfo("Settings Applied", info_message)

        self.is_repeating_active = True
        self.skip_subtitle_btn.config(state=tk.NORMAL)
        self.prev_subtitle_btn.config(state=tk.NORMAL)
        self.update_subtitle_index_on_seek(self.player.get_time())
        self.master.focus_set()

    def _apply_processed_subtitles_to_player(self):
        if not self.subtitles or not self.temp_sub_path: return False
        try:
            self.subtitles.save(self.temp_sub_path, encoding='utf-8')
            if self.player.get_media():
                if self.player.video_set_subtitle_file(self.temp_sub_path) == 0:
                    logging.info(f"Processed subtitles set from temporary file: {self.temp_sub_path}")
                else:
                    logging.warning(f"VLC failed to set subtitle file: {self.temp_sub_path}. Trying slave method.")
                    self.player.add_slave(vlc.MediaSlaveType.subtitle, self.temp_sub_path, True)
            return True
        except Exception as e:
            logging.error(f"Failed to save or set temporary subtitle file: {e}", exc_info=True)
            messagebox.showerror("File Error", f"Could not create temporary subtitle file.\nError: {e}")
            return False

    def play_pause(self, *args):
        if self.resume_timer_id is not None:
            logging.info("Ignoring play/pause command during 1s repeat delay.")
            return
        if not self.player.get_media():
            self.load_video()
            return

        self.cancel_all_timers()
        if self.player.is_playing():
            self.player.pause()
            self.play_pause_btn.config(text="Play")
            self.is_paused = True
        else:
            if self.is_paused: self.update_subtitle_index_on_seek(self.player.get_time())
            self.player.play()
            self.play_pause_btn.config(text="Pause")
            self.is_paused = False
        self.master.focus_set()

    def stop(self, *args):
        self.cancel_all_timers()
        self.player.stop()
        self.play_pause_btn.config(text="Play")
        self.is_paused = True
        self.progress_slider.set(0)
        self.time_label.config(text="00:00:00")
        self.subtitle_index = 0
        self.repeat_counter = 0
        self.master.focus_set()

    def skip_subtitle(self, *args):
        if not self.subtitles or self.subtitle_index >= len(self.subtitles) - 1: return
        self.cancel_all_timers()
        self.subtitle_index += 1
        self.repeat_counter = 0
        next_cue = self.subtitles[self.subtitle_index]
        self.player.set_time(max(0, int(next_cue.start.ordinal)))
        if self.is_paused: self.play_pause()
        logging.info(f"Skipped to subtitle #{self.subtitle_index + 1}")
        self.master.focus_set()

    def previous_subtitle(self, *args):
        if not self.subtitles or self.subtitle_index <= 0: return
        self.cancel_all_timers()
        self.subtitle_index -= 1
        self.repeat_counter = 0
        prev_cue = self.subtitles[self.subtitle_index]
        self.player.set_time(max(0, int(prev_cue.start.ordinal)))
        if self.is_paused: self.play_pause()
        logging.info(f"Went back to subtitle #{self.subtitle_index + 1}")
        self.master.focus_set()

    def toggle_fullscreen(self, *args):
        self.is_fullscreen = not self.is_fullscreen
        self.master.attributes("-fullscreen", self.is_fullscreen)
        self.update_fullscreen_button()
        self.master.focus_set()

    def update_fullscreen_button(self):
        self.fullscreen_btn.config(text="Exit Fullscreen" if self.is_fullscreen else "Fullscreen")

    def set_volume(self, value):
        if self.player: self.player.audio_set_volume(int(value))

    def update_subtitle_index_on_seek(self, time_ms):
        if not self.subtitles: return
        self.cancel_all_timers()
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal <= time_ms < cue.end.ordinal:
                self.subtitle_index = i
                self.repeat_counter = 0
                return
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal > time_ms:
                self.subtitle_index = i
                self.repeat_counter = 0
                return
        self.subtitle_index = len(self.subtitles) - 1 if self.subtitles else 0
        self.repeat_counter = 0

    def ms_to_time_str(self, ms):
        if ms < 0: ms = 0
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02}:{m:02}:{s:02}"

    def handle_keypress(self, event):
        if isinstance(event.widget, (tk.Entry, tk.Spinbox)): return
        key = event.keysym.lower()
        if key == 'space':
            self.play_pause()
        elif key == 's':
            self.stop()
        elif key == 'f':
            self.toggle_fullscreen()
        elif key == 'right':
            self.skip_subtitle()
        elif key == 'left':
            self.previous_subtitle()


if __name__ == "__main__":
    logging.info("================== Application Starting ==================")
    root = tk.Tk()
    app = VLCPlayerApp(root)


    def on_closing():
        logging.info("Window closed by user. Stopping player.")
        if app.player:
            app.player.stop()
            app.player.release()
        # Clean up temp file
        if app.temp_sub_path and os.path.exists(app.temp_sub_path):
            try:
                os.remove(app.temp_sub_path)
                logging.info(f"Removed temporary subtitle file: {app.temp_sub_path}")
            except OSError as e:
                logging.error(f"Error removing temp file on exit: {e}")
        root.destroy()
        logging.info("================== Application Closed ==================")


    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()