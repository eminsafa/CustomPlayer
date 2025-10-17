import tkinter as tk
from tkinter import filedialog, messagebox
import pysrt
import os
import sys
import logging
import time

# --- Setup Logging ---
log_file_path = os.path.join(os.path.expanduser("~"), "subtitle_repeater.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(log_file_path, 'w', 'utf-8')]
)

# This is necessary on Windows to find the VLC DLLs
# Ensure this path is correct for your VLC installation
os.add_dll_directory(r"C:\Program Files\VideoLAN\VLC")
import vlc


class VLCControllerApp:
    """
    A minimal, always-on-top controller for a standalone VLC player.
    Uses direct python-vlc bindings for reliable control.
    """

    def __init__(self, master):
        self.master = master
        master.title("VLC Subtitle Controller")
        master.geometry("750x220+100+100")  # Increased height

        # --- Create a borderless, always-on-top window ---
        master.overrideredirect(True)
        master.attributes('-topmost', True)  # <-- FIX: Keeps controller on top
        master.configure(bg='#2e2e2e')

        # --- Variables for window dragging ---
        self._offset_x = 0
        self._offset_y = 0
        master.bind('<Button-1>', self.click_window)
        master.bind('<B1-Motion>', self.drag_window)

        # --- State Variables ---
        self.subtitles = None
        self.subtitle_index = 0
        self.repeat_counter = 0
        self.is_slider_dragging = False
        self.repeat_timer_id = None

        try:
            logging.info("Initializing VLC instance...")
            self.vlc_instance = vlc.Instance()
            self.player = self.vlc_instance.media_player_new()
            logging.info("VLC instance and player created successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize VLC: {e}", exc_info=True)
            messagebox.showerror("VLC Error", f"Could not initialize VLC. Is it installed?\nError: {e}")
            master.destroy()
            return

        self.create_widgets()
        self.master.after(100, self.update_ui)

    def click_window(self, event):
        # Don't drag if clicking on a button, slider, or spinbox
        if event.widget.winfo_class() not in ('Button', 'Scale', 'Spinbox', 'TSpinbox'):
            self._offset_x = event.x
            self._offset_y = event.y

    def drag_window(self, event):
        if event.widget.winfo_class() not in ('Button', 'Scale', 'Spinbox', 'TSpinbox'):
            x = self.master.winfo_pointerx() - self._offset_x
            y = self.master.winfo_pointery() - self._offset_y
            self.master.geometry(f'+{x}+{y}')

    def create_widgets(self):
        # --- Custom Title Bar (for dragging and closing) ---
        title_bar = tk.Frame(self.master, bg='#1c1c1c')
        title_bar.pack(side=tk.TOP, fill=tk.X)
        title_bar.bind('<Button-1>', self.click_window)
        title_bar.bind('<B1-Motion>', self.drag_window)

        tk.Label(title_bar, text="VLC Subtitle Controller", fg="white", bg="#1c1c1c", font=("Segoe UI", 10)).pack(
            side=tk.LEFT, padx=10)
        tk.Button(title_bar, text='✕', command=self.on_closing, bg='#1c1c1c', fg='white', width=4, relief='flat',
                  font=("Arial", 10, "bold"), activebackground='red').pack(side=tk.RIGHT)

        content_frame = tk.Frame(self.master, bg="#2e2e2e", padx=15, pady=10)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # --- Subtitle Display ---
        self.subtitle_display_label = tk.Label(
            content_frame, text="Load a video and subtitle file to begin.", fg="white", bg="#2e2e2e",
            font=("Segoe UI", 16), wraplength=700, justify=tk.CENTER, height=2
        )
        self.subtitle_display_label.pack(pady=(5, 15), fill=tk.X)

        # --- Progress Bar and Time ---
        time_frame = tk.Frame(content_frame, bg='#2e2e2e')
        time_frame.pack(fill=tk.X, pady=5)
        self.time_label = tk.Label(time_frame, text="00:00:00", fg="white", bg='#2e2e2e', font=("Segoe UI", 10))
        self.time_label.pack(side=tk.LEFT, padx=(0, 10))
        self.progress_slider = tk.Scale(time_frame, from_=0, to=1000, orient=tk.HORIZONTAL, showvalue=0,
                                        troughcolor='#555', bg='#2e2e2e', highlightthickness=0,
                                        activebackground='#0078d4', relief='flat')
        self.progress_slider.pack(fill=tk.X, expand=True)
        self.progress_slider.bind("<ButtonPress-1>", lambda e: setattr(self, 'is_slider_dragging', True))
        self.progress_slider.bind("<ButtonRelease-1>", self.on_slider_release)
        self.duration_label = tk.Label(time_frame, text="00:00:00", fg="white", bg='#2e2e2e', font=("Segoe UI", 10))
        self.duration_label.pack(side=tk.RIGHT, padx=(10, 0))

        # --- Controls ---
        controls_container = tk.Frame(content_frame, bg="#2e2e2e")
        controls_container.pack(fill=tk.X, pady=10)

        btn_style = {'bg': "#4a4a4a", 'fg': "white", 'relief': 'flat', 'font': ("Segoe UI", 10, "bold"), 'width': 12,
                     'pady': 5}

        self.play_pause_btn = tk.Button(controls_container, text="Play", **btn_style, command=self.play_pause)
        self.play_pause_btn.pack(side=tk.LEFT, padx=5)

        tk.Button(controls_container, text="Previous", **btn_style, command=self.previous_subtitle).pack(side=tk.LEFT,
                                                                                                         padx=5)
        tk.Button(controls_container, text="Next", **btn_style, command=self.skip_subtitle).pack(side=tk.LEFT, padx=5)

        tk.Button(controls_container, text="Load Video", **btn_style, command=self.load_video).pack(side=tk.LEFT,
                                                                                                    padx=(20, 5))
        tk.Button(controls_container, text="Load Subs", **btn_style, command=self.load_subtitle).pack(side=tk.LEFT,
                                                                                                      padx=5)

        tk.Label(controls_container, text="Repeat:", fg="white", bg="#2e2e2e").pack(side=tk.LEFT, padx=(20, 0))
        self.repeat_count = tk.Spinbox(controls_container, from_=1, to=10, width=3, justify=tk.CENTER)
        self.repeat_count.pack(side=tk.LEFT, padx=5)

        self.volume_slider = tk.Scale(controls_container, from_=0, to=100, orient=tk.HORIZONTAL,
                                      command=self.set_volume, length=120, troughcolor='#555', bg='#2e2e2e',
                                      highlightthickness=0, activebackground='#0078d4', relief='flat')
        self.volume_slider.set(100)
        self.volume_slider.pack(side=tk.RIGHT, padx=5)
        tk.Label(controls_container, text="Volume:", fg="white", bg="#2e2e2e").pack(side=tk.RIGHT)

    def load_video(self):
        path = filedialog.askopenfilename(filetypes=(("Video files", "*.mp4 *.mkv *.avi *.mov"), ("All files", "*.*")))
        if not path: return

        if self.player.is_playing():
            self.player.stop()

        media = self.vlc_instance.media_new(path)
        self.player.set_media(media)
        self.player.play()  # This will launch VLC in a new window automatically

        # A small delay to allow the player to start and report its state
        time.sleep(0.5)
        self.play_pause_btn.config(text="Pause")

    def load_subtitle(self, *args):
        path = filedialog.askopenfilename(filetypes=(("SubRip files", "*.srt"),))
        if not path: return

        for encoding in ['utf-8', 'utf-8-sig', 'cp1252', 'iso-8859-1']:
            try:
                self.subtitles = pysrt.open(path, encoding=encoding)
                logging.info(f"Loaded subtitles with '{encoding}' encoding.")
                self.update_subtitle_index_on_seek(self.player.get_time())
                return
            except Exception:
                continue
        messagebox.showerror("Subtitle Error", "Could not decode subtitle file.")

    def play_pause(self):
        if self.player.get_media():
            self.player.pause()  # This single command toggles play/pause
            if self.player.is_playing():
                self.play_pause_btn.config(text="Pause")
            else:
                self.play_pause_btn.config(text="Play")

    def update_ui(self):
        if self.player.get_media():
            if not self.is_slider_dragging:
                position = self.player.get_position()
                self.progress_slider.set(int(position * 1000))

            current_time = self.player.get_time()
            self.time_label.config(text=self.ms_to_time_str(current_time))
            self.duration_label.config(text=self.ms_to_time_str(self.player.get_length()))

            self.update_tkinter_subtitle(current_time)
            self.handle_repeat(current_time)

        self.master.after(200, self.update_ui)

    def update_tkinter_subtitle(self, current_time_ms):
        if not self.subtitles: return

        active_cue_text = ""
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal <= current_time_ms < cue.end.ordinal:
                self.subtitle_index = i
                active_cue_text = cue.text_without_tags.replace('\n', ' ')
                break

        self.subtitle_display_label.config(text=active_cue_text)

    def handle_repeat(self, current_time_ms):
        if not self.subtitles or not self.player.is_playing(): return

        cue = self.subtitles[self.subtitle_index]

        # Schedule the check just before the subtitle ends
        if cue.start.ordinal <= current_time_ms < cue.end.ordinal:
            if self.repeat_timer_id:
                self.master.after_cancel(self.repeat_timer_id)

            time_until_end = cue.end.ordinal - current_time_ms
            self.repeat_timer_id = self.master.after(time_until_end, self.perform_repeat_check)

    def perform_repeat_check(self):
        self.repeat_timer_id = None
        if not self.player.is_playing(): return

        max_repeats = int(self.repeat_count.get())
        if self.repeat_counter < max_repeats - 1:
            self.repeat_counter += 1
            logging.info(f"Repeating subtitle #{self.subtitle_index + 1}")
            cue = self.subtitles[self.subtitle_index]
            self.player.set_time(cue.start.ordinal)
        else:
            self.repeat_counter = 0  # Reset for the next subtitle

    def skip_subtitle(self):
        if not self.subtitles or self.subtitle_index >= len(self.subtitles) - 1: return
        self.subtitle_index += 1
        self.repeat_counter = 0
        next_cue = self.subtitles[self.subtitle_index]
        self.player.set_time(next_cue.start.ordinal)

    def previous_subtitle(self):
        if not self.subtitles or self.subtitle_index <= 0: return
        self.subtitle_index -= 1
        self.repeat_counter = 0
        prev_cue = self.subtitles[self.subtitle_index]
        self.player.set_time(prev_cue.start.ordinal)

    def set_volume(self, value):
        # This now correctly controls the standalone VLC instance
        if self.player:
            self.player.audio_set_volume(int(value))

    def on_slider_release(self, event):
        self.is_slider_dragging = False
        if self.player.get_media():
            new_pos = self.progress_slider.get() / 1000.0
            self.player.set_position(new_pos)
            self.update_subtitle_index_on_seek(self.player.get_time())

    def update_subtitle_index_on_seek(self, time_ms):
        if not self.subtitles: return
        new_index = 0
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal > time_ms:
                new_index = max(0, i - 1)
                break
        else:
            new_index = len(self.subtitles) - 1
        self.subtitle_index = new_index
        self.repeat_counter = 0

    def ms_to_time_str(self, ms):
        if ms < 0: ms = 0
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02}:{m:02}:{s:02}"

    def on_closing(self):
        logging.info("Closing application...")
        if self.player:
            self.player.stop()
            self.player.release()
        self.master.destroy()


if __name__ == "__main__":
    logging.info("================== Application Starting ==================")
    root = tk.Tk()
    app = VLCControllerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()