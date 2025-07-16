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
    A video player with a focus on flicker-free repeating of subtitle lines.
    """

    def __init__(self, master):
        self.master = master
        master.title("Subtitle Repeater")
        master.geometry("800x650")
        master.configure(bg='black')

        # --- State Variables ---
        self.video_path = None
        self.subtitle_path = None
        self.subtitles = None
        self.raw_subtitles = None
        self.temp_sub_path = None
        self.subtitle_index = 0
        self.repeat_counter = 0
        self.is_paused = True
        self.is_repeating_active = False
        self.is_fullscreen = False
        self.is_slider_dragging = False
        self.repeat_timer_id = None

        try:
            logging.info("Initializing VLC instance...")
            vlc_args = []
            if sys.platform.startswith('linux'):
                vlc_args.append('--no-xlib')
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))
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

        # Create a persistent temp file path on startup
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
        self.video_frame = tk.Frame(self.master, bg="black")
        self.video_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        time_frame = tk.Frame(self.master, bg='#2c2c2c')
        time_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.time_label = tk.Label(time_frame, text="00:00:00", fg="white", bg='#2c2c2c', font=("Helvetica", 10))
        self.time_label.pack(side=tk.LEFT, padx=10)
        self.progress_slider = tk.Scale(time_frame, from_=0, to=1000, orient=tk.HORIZONTAL, showvalue=0,
                                        troughcolor='#555', bg='#2c2c2c', highlightthickness=0,
                                        activebackground='#e04a00')
        self.progress_slider.pack(fill=tk.X, expand=True, padx=5)
        self.duration_label = tk.Label(time_frame, text="00:00:00", fg="white", bg='#2c2c2c', font=("Helvetica", 10))
        self.duration_label.pack(side=tk.RIGHT, padx=10)
        self.progress_slider.bind("<ButtonPress-1>", self.on_slider_press)
        self.progress_slider.bind("<ButtonRelease-1>", self.on_slider_release)

        controls_container = tk.Frame(self.master, bg="#2c2c2c")
        controls_container.pack(fill=tk.X, padx=10, pady=5)

        self.play_pause_btn = tk.Button(controls_container, text="▶", command=self.play_pause, width=4, bg="#3a3a3a",
                                        fg="white", font=("Helvetica", 12))
        self.play_pause_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.prev_subtitle_btn = tk.Button(controls_container, text="⬅", command=self.previous_subtitle,
                                           state=tk.DISABLED, bg="#3a3a3a", fg="white", font=("Helvetica", 12))
        self.prev_subtitle_btn.pack(side=tk.LEFT, padx=(5, 0), pady=5)
        self.skip_subtitle_btn = tk.Button(controls_container, text="➡", command=self.skip_subtitle, state=tk.DISABLED,
                                           bg="#3a3a3a", fg="white", font=("Helvetica", 12))
        self.skip_subtitle_btn.pack(side=tk.LEFT, padx=(5, 15), pady=5)

        self.load_video_btn = tk.Button(controls_container, text="Video", command=self.load_video, bg="#3a3a3a",
                                        fg="white")
        self.load_video_btn.pack(side=tk.LEFT, padx=5, pady=5)
        self.load_subs_btn = tk.Button(controls_container, text="Subs", command=self.load_subtitle, bg="#3a3a3a",
                                       fg="white")
        self.load_subs_btn.pack(side=tk.LEFT, padx=(0, 15), pady=5)

        repeat_label = tk.Label(controls_container, text="Repeat", fg="white", bg="#2c2c2c", font=("Helvetica", 12))
        repeat_label.pack(side=tk.LEFT, padx=(5, 0), pady=5)
        self.repeat_count = tk.Spinbox(controls_container, from_=1, to=10, width=3, justify=tk.CENTER)
        self.repeat_count.pack(side=tk.LEFT, padx=(0, 15), pady=5)

        volume_label = tk.Label(controls_container, text="Volume", fg="white", bg="#2c2c2c", font=("Helvetica", 12))
        volume_label.pack(side=tk.LEFT, padx=(5, 0), pady=5)
        self.volume_slider = tk.Scale(controls_container, from_=0, to=100, orient=tk.HORIZONTAL,
                                      command=self.set_volume, showvalue=0, length=120, troughcolor='#555',
                                      bg='#2c2c2c', highlightthickness=0, activebackground='#e04a00')
        self.volume_slider.set(100)
        self.volume_slider.pack(side=tk.LEFT, padx=5, pady=5)

        self.fullscreen_btn = tk.Button(controls_container, text="⛶", command=self.toggle_fullscreen, bg="#3a3a3a",
                                        fg="white", font=("Helvetica", 12))
        self.fullscreen_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        advanced_frame = tk.LabelFrame(self.master, text="Subtitle Settings", fg="white", bg="#2c2c2c", padx=10,
                                       pady=10)
        advanced_frame.pack(fill=tk.X, padx=10, pady=10)
        advanced_frame.columnconfigure(2, weight=1)

        sync_label = tk.Label(advanced_frame, text="Delay (sec):", fg="white", bg="#2c2c2c")
        sync_label.grid(row=0, column=0, sticky="w", pady=2, padx=(0, 5))
        self.sync_delay_entry = tk.Entry(advanced_frame, width=5)
        self.sync_delay_entry.insert(0, "0.0")
        self.sync_delay_entry.grid(row=0, column=1, sticky="w")

        self.apply_settings_btn = tk.Button(advanced_frame, text="⚙️ Apply", command=self.process_subtitles,
                                            state=tk.DISABLED, bg="#007acc", fg="white")
        self.apply_settings_btn.grid(row=0, column=2, sticky="e", padx=(20, 0))

    def on_slider_press(self, event):
        self.cancel_scheduled_repeat()
        self.is_slider_dragging = True

    def on_slider_release(self, event):
        self.is_slider_dragging = False
        self.seek()
        # Ensure focus returns to the main window after slider interaction
        self.master.focus_set()

    def seek(self):
        self.cancel_scheduled_repeat()
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

                if self.is_repeating_active and not self.is_paused and self.repeat_timer_id is None:
                    if self.subtitles and self.subtitle_index < len(self.subtitles):
                        current_cue = self.subtitles[self.subtitle_index]
                        if current_cue.start.ordinal <= current_time < current_cue.end.ordinal:
                            time_until_end = current_cue.end.ordinal - current_time
                            self.repeat_timer_id = self.master.after(time_until_end, self.handle_repeat)

            self.master.after(10, self.update_ui)
        except tk.TclError:
            logging.info("TclError caught, likely window closed. Shutting down UI loop.")
        except Exception as e:
            logging.error(f"Unexpected error in UI update loop: {e}", exc_info=True)

    def handle_repeat(self):
        self.repeat_timer_id = None
        if self.is_paused or not self.is_repeating_active: return

        try:
            max_repeats = int(self.repeat_count.get())
        except (ValueError, tk.TclError):
            max_repeats = 1

        current_cue = self.subtitles[self.subtitle_index]
        if self.repeat_counter < max_repeats - 1:
            self.repeat_counter += 1
            self.player.set_time(max(0, current_cue.start.ordinal))
            logging.info(
                f"Repeating subtitle #{self.subtitle_index + 1} (Repeat {self.repeat_counter}/{max_repeats - 1})")
        elif self.subtitle_index < len(self.subtitles) - 1:
            self.subtitle_index += 1
            self.repeat_counter = 0
            logging.info(f"Advancing to subtitle #{self.subtitle_index + 1}")

    def cancel_scheduled_repeat(self):
        if self.repeat_timer_id:
            self.master.after_cancel(self.repeat_timer_id)
            self.repeat_timer_id = None
            logging.info("Cancelled scheduled repeat.")

    def load_video(self, *args):
        self.cancel_scheduled_repeat()
        path = filedialog.askopenfilename(title="Select Video File",
                                          filetypes=(("Video files", "*.mp4 *.mkv *.avi *.mov"), ("All files", "*.*")))
        if not path: return

        self.video_path = path
        logging.info(f"Loading video: {self.video_path}")
        try:
            media = self.vlc_instance.media_new(self.video_path)
            self.player.set_media(media)

            def embed_video():
                video_widget_id = self.video_frame.winfo_id()
                if sys.platform == "win32":
                    self.player.set_hwnd(video_widget_id)
                elif sys.platform == "darwin":
                    self.player.set_nsobject(video_widget_id)
                else:
                    self.player.set_xwindow(video_widget_id)

                if self.subtitles:
                    self._apply_processed_subtitles_to_player()
                self.play_pause()
                # Ensure focus returns to the main window after video load
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
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logging.error(f"Error parsing subtitle file with encoding {encoding}: {e}", exc_info=True)
                messagebox.showerror("Subtitle Error", f"Could not parse subtitle file.\nError: {e}")
                return

        if loaded_subs:
            self.raw_subtitles = loaded_subs
            self.apply_settings_btn.config(state=tk.NORMAL)
            self.process_subtitles()
        else:
            logging.error("Could not decode subtitle file with any of the common encodings.")
            messagebox.showerror("Subtitle Error", "Could not decode subtitle file. Please try converting it to UTF-8.")
        # Ensure focus returns to the main window after subtitle load
        self.master.focus_set()

    def process_subtitles(self):
        if not self.raw_subtitles:
            logging.warning("process_subtitles called with no raw subtitles loaded.")
            messagebox.showwarning("Warning", "No subtitles loaded to process.")
            return

        self.cancel_scheduled_repeat()
        logging.info("Processing subtitles...")

        # Create a deep copy of the SubRipFile object to apply shifts without modifying original.
        processed_subs = self.raw_subtitles.copy()

        info_message = "Settings applied."

        try:
            delay_sec = float(self.sync_delay_entry.get())
            if delay_sec != 0.0:
                processed_subs.shift(seconds=delay_sec)
                logging.info(f"Shifted all cues by {delay_sec} seconds.")
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
        # Ensure focus returns to the main window after applying settings
        self.master.focus_set()

    def _apply_processed_subtitles_to_player(self):
        if not self.subtitles or not self.temp_sub_path:
            return False
        try:
            self.subtitles.save(self.temp_sub_path, encoding='utf-8')
            if self.player.get_media():
                if self.player.video_set_subtitle_file(self.temp_sub_path) == 1:
                    logging.info(f"Processed subtitles set from temporary file: {self.temp_sub_path}")
                    return True
                else:
                    logging.error(f"VLC failed to set subtitle file: {self.temp_sub_path}")
                    messagebox.showwarning("VLC Warning", "VLC could not load the processed subtitles.")
                    return False
            return True  # Return true even if no media, it will be applied when media loads
        except Exception as e:
            logging.error(f"Failed to save or set temporary subtitle file: {e}", exc_info=True)
            messagebox.showerror("File Error", f"Could not create temporary subtitle file.\nError: {e}")
            return False

    def play_pause(self, *args):
        if not self.player.get_media(): self.load_video(); return

        self.cancel_scheduled_repeat()
        if self.player.is_playing():
            self.player.pause()
            self.play_pause_btn.config(text="▶")
            self.is_paused = True
        else:
            if self.is_paused:
                self.update_subtitle_index_on_seek(self.player.get_time())
            self.player.play()
            self.play_pause_btn.config(text="❚❚")
            self.is_paused = False
        # Ensure focus returns to the main window after play/pause
        self.master.focus_set()

    def stop(self, *args):
        self.cancel_scheduled_repeat()
        self.player.stop()
        self.play_pause_btn.config(text="▶")
        self.is_paused = True
        self.progress_slider.set(0)
        self.time_label.config(text="00:00:00")
        self.subtitle_index = 0
        self.repeat_counter = 0
        # Ensure focus returns to the main window after stop
        self.master.focus_set()

    def skip_subtitle(self, *args):
        if not self.subtitles or self.subtitle_index >= len(self.subtitles) - 1: return
        self.cancel_scheduled_repeat()
        self.subtitle_index += 1
        self.repeat_counter = 0
        next_cue = self.subtitles[self.subtitle_index]
        self.player.set_time(max(0, next_cue.start.ordinal))
        if self.is_paused: self.play_pause()
        logging.info(f"Skipped to subtitle #{self.subtitle_index + 1}")
        # Ensure focus returns to the main window after skip
        self.master.focus_set()

    def previous_subtitle(self, *args):
        if not self.subtitles or self.subtitle_index <= 0: return
        self.cancel_scheduled_repeat()
        self.subtitle_index -= 1
        self.repeat_counter = 0
        prev_cue = self.subtitles[self.subtitle_index]
        self.player.set_time(max(0, prev_cue.start.ordinal))
        if self.is_paused: self.play_pause()
        logging.info(f"Went back to subtitle #{self.subtitle_index + 1}")
        # Ensure focus returns to the main window after previous
        self.master.focus_set()

    def toggle_fullscreen(self, *args):
        self.is_fullscreen = not self.is_fullscreen
        self.master.attributes("-fullscreen", self.is_fullscreen)
        self.update_fullscreen_button()
        # Ensure focus returns to the main window after fullscreen toggle
        self.master.focus_set()

    def update_fullscreen_button(self):
        self.fullscreen_btn.config(text="Exit ⛶" if self.is_fullscreen else "⛶")

    def set_volume(self, value):
        self.player.audio_set_volume(int(value))

    def update_subtitle_index_on_seek(self, time_ms):
        if not self.subtitles: return

        self.cancel_scheduled_repeat()
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal <= time_ms < cue.end.ordinal:
                self.subtitle_index = i;
                self.repeat_counter = 0;
                return
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal > time_ms:
                self.subtitle_index = i;
                self.repeat_counter = 0;
                return
        self.subtitle_index = len(self.subtitles) - 1 if self.subtitles else 0
        self.repeat_counter = 0

    def ms_to_time_str(self, ms):
        if ms < 0: ms = 0
        s, ms = divmod(ms, 1000);
        m, s = divmod(s, 60);
        h, m = divmod(m, 60)
        return f"{h:02}:{m:02}:{s:02}"

    def handle_keypress(self, event):
        # If the focus is on an Entry or Spinbox, let it handle the keypress
        # This prevents global shortcuts from interfering with text input
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
    root.mainloop()
    logging.info("================== Application Closed ==================")