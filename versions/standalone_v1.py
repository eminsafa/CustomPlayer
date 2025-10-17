import tkinter as tk
from tkinter import filedialog, messagebox
import vlc
import pysrt
import os
import sys
import logging
import subprocess
import time

# --- Setup Logging ---
log_file_path = os.path.join(os.path.expanduser("~"), "subtitle_repeater.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, 'w', 'utf-8')
    ]
)

class VLCControllerApp:
    """
    A controller for a standalone VLC player with a focus on flicker-free repeating of subtitle lines.
    Subtitles are rendered in a Tkinter widget for full control.
    """

    def __init__(self, master):
        self.master = master
        master.title("Subtitle Repeater Controller")
        master.geometry("800x250")
        master.configure(bg='black')

        # --- State Variables ---
        self.video_path = None
        self.subtitle_path = None
        self.subtitles = None
        self.original_subtitles = None
        self.subtitle_index = 0
        self.repeat_counter = 0
        self.is_paused = True
        self.is_repeating_active = False
        self.is_slider_dragging = False
        self.repeat_timer_id = None
        self.resume_timer_id = None
        self.last_current_time_str = ""
        self.last_duration_time_str = ""
        self.currently_displayed_subtitle_index = None
        self.vlc_process = None

        try:
            logging.info("Initializing VLC instance...")
            # Note: We are not creating a media player here initially.
            # We will launch VLC as a separate process.
            self.vlc_instance = vlc.Instance("--no-xlib" if sys.platform.startswith('linux') else "")
            self.player = self.vlc_instance.media_player_new()
            logging.info("VLC instance created successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize VLC: {e}", exc_info=True)
            messagebox.showerror("VLC Error", f"Could not initialize VLC. Is it installed?\nError: {e}")
            master.destroy()
            return

        self.create_widgets()
        self.master.bind('<Key>', self.handle_keypress)
        self.master.focus_set()
        self.master.after(100, self.update_ui)

    def create_widgets(self):
        # The video frame is no longer needed as video plays in a separate window.
        self.subtitle_display_label = tk.Label(
            self.master,
            text="Load a video to begin.",
            fg="white",
            bg="black",
            font=("Helvetica", 16, "bold"),
            wraplength=780,
            justify=tk.CENTER,
            height=2
        )
        self.subtitle_display_label.pack(pady=20, padx=10, fill=tk.X)

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
                                        fg="white", font=("Helvetica", 12));
        self.play_pause_btn.pack(side=tk.LEFT, padx=5, pady=5)
        self.prev_subtitle_btn = tk.Button(controls_container, text="⬅", command=self.previous_subtitle,
                                           state=tk.DISABLED, bg="#3a3a3a", fg="white", font=("Helvetica", 12));
        self.prev_subtitle_btn.pack(side=tk.LEFT, padx=(5, 0), pady=5)
        self.skip_subtitle_btn = tk.Button(controls_container, text="➡", command=self.skip_subtitle, state=tk.DISABLED,
                                           bg="#3a3a3a", fg="white", font=("Helvetica", 12));
        self.skip_subtitle_btn.pack(side=tk.LEFT, padx=(5, 15), pady=5)
        self.load_video_btn = tk.Button(controls_container, text="Video", command=self.load_video, bg="#3a3a3a",
                                        fg="white");
        self.load_video_btn.pack(side=tk.LEFT, padx=5, pady=5)
        self.load_subs_btn = tk.Button(controls_container, text="Subs", command=self.load_subtitle, bg="#3a3a3a",
                                       fg="white");
        self.load_subs_btn.pack(side=tk.LEFT, padx=(0, 15), pady=5)
        repeat_label = tk.Label(controls_container, text="Repeat", fg="white", bg="#2c2c2c", font=("Helvetica", 12));
        repeat_label.pack(side=tk.LEFT, padx=(5, 0), pady=5)
        self.repeat_count = tk.Spinbox(controls_container, from_=1, to=10, width=3, justify=tk.CENTER);
        self.repeat_count.pack(side=tk.LEFT, padx=(0, 15), pady=5)
        volume_label = tk.Label(controls_container, text="Volume", fg="white", bg="#2c2c2c", font=("Helvetica", 12));
        volume_label.pack(side=tk.LEFT, padx=(5, 0), pady=5)
        self.volume_slider = tk.Scale(controls_container, from_=0, to=100, orient=tk.HORIZONTAL,
                                      command=self.set_volume, showvalue=0, length=120, troughcolor='#555',
                                      bg='#2c2c2c', highlightthickness=0, activebackground='#e04a00');
        self.volume_slider.set(100);
        self.volume_slider.pack(side=tk.LEFT, padx=5, pady=5)
        # Fullscreen button is removed as it's controlled by the standalone VLC player

    def on_slider_press(self, event):
        self.cancel_all_scheduled_actions()
        self.is_slider_dragging = True

    def on_slider_release(self, event):
        self.is_slider_dragging = False
        self.seek()
        self.master.focus_set()

    def seek(self):
        if not self.player.get_media() or self.player.get_length() <= 0: return
        pos = self.progress_slider.get()
        self.player.set_position(pos / 1000.0)
        self.update_subtitle_index_on_seek(self.player.get_time(), reset_counter=True)

    def update_ui(self):
        try:
            if self.player.get_media() and self.player.get_length() > 0:
                current_time = self.player.get_time()
                if not self.is_slider_dragging: self.progress_slider.set(int(self.player.get_position() * 1000))
                current_time_str = self.ms_to_time_str(current_time)
                if current_time_str != self.last_current_time_str: self.time_label.config(
                    text=current_time_str); self.last_current_time_str = current_time_str
                duration_str = self.ms_to_time_str(self.player.get_length())
                if duration_str != self.last_duration_time_str: self.duration_label.config(
                    text=duration_str); self.last_duration_time_str = duration_str
                self.update_tkinter_subtitle(current_time)
                if self.is_repeating_active and not self.is_paused and self.repeat_timer_id is None:
                    if self.subtitles and self.subtitle_index < len(self.subtitles):
                        current_cue = self.subtitles[self.subtitle_index]
                        if current_cue.start.ordinal <= current_time < current_cue.end.ordinal:
                            time_until_end = int(current_cue.end.ordinal) - current_time
                            self.repeat_timer_id = self.master.after(time_until_end, self.handle_repeat)
            self.master.after(20, self.update_ui)
        except tk.TclError:
            logging.info("TclError caught, likely window closed.")
        except Exception as e:
            logging.error(f"Unexpected error in UI loop: {e}", exc_info=True)

    def update_tkinter_subtitle(self, current_time_ms):
        if not self.subtitles: return
        active_index = None
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal <= current_time_ms < cue.end.ordinal: active_index = i; break
        if active_index != self.currently_displayed_subtitle_index:
            new_text = self.subtitles[active_index].text if active_index is not None else ""
            self.subtitle_display_label.config(text=new_text)
            self.currently_displayed_subtitle_index = active_index

    def handle_repeat(self):
        self.repeat_timer_id = None
        if self.is_paused or not self.is_repeating_active: return
        try:
            max_repeats = int(self.repeat_count.get())
        except (ValueError, tk.TclError):
            max_repeats = 1

        if not self.subtitles or self.subtitle_index >= len(self.subtitles): return

        current_cue = self.subtitles[self.subtitle_index]
        if self.repeat_counter < max_repeats - 1:
            self.repeat_counter += 1
            logging.info(f"Repeating subtitle #{self.subtitle_index + 1} (Repeat {self.repeat_counter}/{max_repeats})")
            self.player.set_time(int(current_cue.start.ordinal))
        elif self.subtitle_index < len(self.subtitles) - 1:
            self.subtitle_index += 1
            self.repeat_counter = 0
            logging.info(f"Advancing to subtitle #{self.subtitle_index + 1}")

    def cancel_all_scheduled_actions(self):
        if self.repeat_timer_id: self.master.after_cancel(self.repeat_timer_id); self.repeat_timer_id = None
        if self.resume_timer_id: self.master.after_cancel(self.resume_timer_id); self.resume_timer_id = None

    def load_video(self, *args):
        self.cancel_all_scheduled_actions()
        path = filedialog.askopenfilename(title="Select Video File",
                                          filetypes=(("Video files", "*.mp4 *.mkv *.avi *.mov"), ("All files", "*.*")))
        if not path: return
        self.video_path = path
        logging.info(f"Loading video: {self.video_path}")

        if self.vlc_process:
            self.vlc_process.terminate()

        try:
            # Launch VLC as a standalone process
            vlc_executable = r"C:\Program Files\VideoLAN\VLC\vlc.exe" # Adjust this path if necessary
            self.vlc_process = subprocess.Popen([vlc_executable, self.video_path])
            time.sleep(2) # Give VLC time to start

            media = self.vlc_instance.media_new(self.video_path)
            self.player.set_media(media)

            self.master.title(f"Subtitle Repeater Controller - {os.path.basename(self.video_path)}")
            self.play_pause()
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
                loaded_subs = pysrt.open(self.subtitle_path, encoding=encoding);
                break
            except Exception:
                continue
        if loaded_subs:
            self.original_subtitles = loaded_subs;
            self.process_subtitles()
        else:
            logging.error("Could not decode subtitle file with any common encodings.");
            messagebox.showerror("Subtitle Error", "Could not decode subtitle file. Try converting to UTF-8.")
        self.master.focus_set()

    def process_subtitles(self):
        if not self.original_subtitles: messagebox.showwarning("Warning", "No subtitles loaded."); return
        self.cancel_all_scheduled_actions()
        self.subtitles = self.original_subtitles.copy()
        self.is_repeating_active = True
        self.skip_subtitle_btn.config(state=tk.NORMAL);
        self.prev_subtitle_btn.config(state=tk.NORMAL)
        self.update_subtitle_index_on_seek(self.player.get_time(), reset_counter=True)
        self.master.focus_set()

    def play_pause(self, *args):
        if not self.player.get_media(): return
        self.cancel_all_scheduled_actions()
        if self.player.is_playing():
            self.player.pause();
            self.play_pause_btn.config(text="▶");
            self.is_paused = True
        else:
            self.player.play();
            self.play_pause_btn.config(text="❚❚");
            self.is_paused = False
        self.master.focus_set()

    def stop(self, *args):
        self.cancel_all_scheduled_actions();
        self.player.stop();
        if self.vlc_process:
            self.vlc_process.terminate()
            self.vlc_process = None
        self.play_pause_btn.config(text="▶");
        self.is_paused = True
        self.progress_slider.set(0);
        self.time_label.config(text="00:00:00");
        self.last_current_time_str = "00:00:00"
        self.subtitle_index = 0;
        self.repeat_counter = 0;
        self.master.focus_set()

    def skip_subtitle(self, *args):
        if not self.subtitles or self.subtitle_index >= len(self.subtitles) - 1: return
        self.subtitle_index += 1
        next_cue = self.subtitles[self.subtitle_index]
        self.player.set_time(int(next_cue.start.ordinal))
        self.master.focus_set()

    def previous_subtitle(self, *args):
        if not self.subtitles or self.subtitle_index <= 0: return
        self.subtitle_index -= 1
        prev_cue = self.subtitles[self.subtitle_index]
        self.player.set_time(int(prev_cue.start.ordinal))
        self.master.focus_set()

    def set_volume(self, value):
        self.player.audio_set_volume(int(value))

    def update_subtitle_index_on_seek(self, time_ms, reset_counter=True):
        if not self.subtitles: return
        self.cancel_all_scheduled_actions()
        new_index = 0
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal <= time_ms < cue.end.ordinal:
                new_index = i
                break
        self.subtitle_index = new_index
        if reset_counter:
            self.repeat_counter = 0

    def ms_to_time_str(self, ms):
        if ms < 0: ms = 0
        s, ms = divmod(ms, 1000);
        m, s = divmod(s, 60);
        h, m = divmod(m, 60)
        return f"{h:02}:{m:02}:{s:02}"

    def handle_keypress(self, event):
        if isinstance(event.widget, (tk.Entry, tk.Spinbox)): return
        key = event.keysym.lower()
        if key == 'space':
            self.play_pause()
        elif key == 's':
            self.stop()
        elif key == 'right':
            self.skip_subtitle()
        elif key == 'left':
            self.previous_subtitle()

    def on_closing(self):
        if self.vlc_process:
            self.vlc_process.terminate()
        self.master.destroy()


if __name__ == "__main__":
    logging.info("================== Application Starting ==================")
    root = tk.Tk()
    app = VLCControllerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
    logging.info("================== Application Closed ==================")