import tkinter as tk
from tkinter import filedialog, messagebox
import vlc
import pysrt
import os
import sys


class VLCPlayerApp:
    def __init__(self, master):
        self.master = master
        master.title("Subtitle Repeater")
        master.geometry("800x700")  # Reduced height due to compact UI
        master.configure(bg='black')

        # --- State Variables ---
        self.video_path = None
        self.subtitle_path = None
        self.subtitles = None
        self.raw_subtitles = None
        self.subtitle_index = 0
        self.repeat_counter = 0
        self.is_paused = True
        self.is_repeating_active = False
        self.is_fullscreen = False
        self.is_slider_dragging = False

        try:
            vlc_args = []
            if sys.platform.startswith('linux'):
                vlc_args.append('--no-xlib')
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))
            plugin_path = os.path.join(base_path, 'plugins')
            os.environ['VLC_PLUGIN_PATH'] = plugin_path
            self.vlc_instance = vlc.Instance(vlc_args)
            self.player = self.vlc_instance.media_player_new()
        except Exception as e:
            messagebox.showerror("VLC Error", f"Could not initialize VLC. Is it installed?\nError: {e}")
            master.destroy()
            return

        self.create_widgets()
        self.master.bind('<Key>', self.handle_keypress)
        self.update_ui()

    ## MODIFIED ##: Complete UI Redesign for compactness
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

        # --- Main Compact Control Bar ---
        controls_container = tk.Frame(self.master, bg="#2c2c2c")
        controls_container.pack(fill=tk.X, padx=10, pady=5)

        # Playback Controls (Left)

        self.play_pause_btn = tk.Button(controls_container, text="▶", command=self.play_pause, width=4, bg="#3a3a3a",
                                        fg="white", font=("Helvetica", 12))
        self.play_pause_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.prev_subtitle_btn = tk.Button(controls_container, text="⬅", command=self.previous_subtitle,
                                           state=tk.DISABLED, bg="#3a3a3a", fg="white", font=("Helvetica", 12))
        self.prev_subtitle_btn.pack(side=tk.LEFT, padx=(5, 0), pady=5)
        self.skip_subtitle_btn = tk.Button(controls_container, text="➡", command=self.skip_subtitle, state=tk.DISABLED,
                                           bg="#3a3a3a", fg="white", font=("Helvetica", 12))
        self.skip_subtitle_btn.pack(side=tk.LEFT, padx=(5, 15), pady=5)

        # File Controls
        self.load_video_btn = tk.Button(controls_container, text="Video", command=self.load_video, bg="#3a3a3a",
                                        fg="white")
        self.load_video_btn.pack(side=tk.LEFT, padx=5, pady=5)
        self.load_subs_btn = tk.Button(controls_container, text="Subs", command=self.load_subtitle, bg="#3a3a3a",
                                       fg="white")
        self.load_subs_btn.pack(side=tk.LEFT, padx=(0, 15), pady=5)

        # Repeater and Volume (Right)
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

        # Fullscreen (Far Right)
        self.fullscreen_btn = tk.Button(controls_container, text="⌞ ⌝", command=self.toggle_fullscreen, bg="#3a3a3a",
                                        fg="white", font=("Helvetica", 12))
        self.fullscreen_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        # --- Advanced Settings Panel (using grid) ---
        advanced_frame = tk.LabelFrame(self.master, text="Subtitle Settings", fg="white", bg="#2c2c2c", padx=10,
                                       pady=10)
        advanced_frame.pack(fill=tk.X, padx=10, pady=10)

        self.merge_subs_var = tk.BooleanVar(value=True)
        self.merge_subs_check = tk.Checkbutton(advanced_frame, text="Merge with symbol:", variable=self.merge_subs_var,
                                               fg="white", bg="#2c2c2c", selectcolor='black',
                                               activebackground="#2c2c2c", activeforeground="white")
        self.merge_subs_check.grid(row=0, column=0, sticky="w", pady=2)
        self.merge_symbol_entry = tk.Entry(advanced_frame, width=5)
        self.merge_symbol_entry.insert(0, "...")
        self.merge_symbol_entry.grid(row=0, column=1, sticky="w")

        sync_label = tk.Label(advanced_frame, text="Delay (sec):", fg="white", bg="#2c2c2c")
        sync_label.grid(row=1, column=0, sticky="w", pady=2)
        self.sync_delay_entry = tk.Entry(advanced_frame, width=5)
        self.sync_delay_entry.insert(0, "0.0")
        self.sync_delay_entry.grid(row=1, column=1, sticky="w")

        self.apply_settings_btn = tk.Button(advanced_frame, text="⚙️ Apply", command=self.process_subtitles,
                                            state=tk.DISABLED, bg="#007acc", fg="white")
        self.apply_settings_btn.grid(row=0, column=2, rowspan=2, sticky="ns", padx=(20, 5))

    def on_slider_press(self, event):
        self.is_slider_dragging = True

    def on_slider_release(self, event):
        self.is_slider_dragging = False; self.seek()

    def seek(self):
        if not self.player.get_media() or self.player.get_length() <= 0: return
        pos = self.progress_slider.get()
        time_ms = int(self.player.get_length() * (pos / 1000.0))
        self.player.set_time(max(0, time_ms))
        self.update_subtitle_index_on_seek(time_ms)

    def _get_merged_subtitles(self, subs, merge_symbol):
        merged_subs = []
        for cue in subs:
            cue.text = cue.text.replace('\r', '').strip()
            if merged_subs and merged_subs[-1].text.endswith(merge_symbol):
                last_cue = merged_subs[-1]
                prev_text = last_cue.text.removesuffix(merge_symbol).strip()
                next_text = cue.text.removeprefix(merge_symbol).strip()
                last_cue.text = f"{prev_text}\n{next_text}"
                last_cue.end = cue.end
            else:
                merged_subs.append(cue)
        return pysrt.SubRipFile(items=merged_subs)

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
                if self.is_repeating_active and not self.is_paused and self.subtitles and self.subtitle_index < len(
                        self.subtitles):
                    current_cue = self.subtitles[self.subtitle_index]
                    if current_time >= current_cue.end.ordinal:
                        max_repeats = int(self.repeat_count.get())
                        if self.repeat_counter < max_repeats - 1:
                            self.repeat_counter += 1
                            self.player.set_time(max(0, current_cue.start.ordinal))
                        elif self.subtitle_index < len(self.subtitles) - 1:
                            self.subtitle_index += 1
                            self.repeat_counter = 0
            self.master.after(100, self.update_ui)
        except tk.TclError:
            pass

    def load_video(self, *args):
        path = filedialog.askopenfilename(title="Select Video File",
                                          filetypes=(("Video files", "*.mp4 *.mkv *.avi *.mov"), ("All files", "*.*")))
        if not path: return
        self.video_path = path
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
            self.play_pause()

        self.master.after(200, embed_video)
        self.master.title(f"Subtitle Repeater - {os.path.basename(self.video_path)}")

    def load_subtitle(self, *args):
        path = filedialog.askopenfilename(title="Select Subtitle File",
                                          filetypes=(("SubRip files", "*.srt"), ("All files", "*.*")))
        if not path: return
        self.subtitle_path = path
        try:
            self.raw_subtitles = pysrt.open(self.subtitle_path, encoding='utf-8')
            self.apply_settings_btn.config(state=tk.NORMAL)
            self.process_subtitles()
        except Exception as e:
            messagebox.showerror("Subtitle Error", f"Could not load or parse subtitle file.\nError: {e}")

    def process_subtitles(self):
        if not self.raw_subtitles: messagebox.showwarning("Warning", "No subtitles loaded to process."); return
        processed_subs = pysrt.SubRipFile(items=[s for s in self.raw_subtitles])
        info_log = []
        if self.merge_subs_var.get():
            merge_symbol = self.merge_symbol_entry.get()
            if merge_symbol:
                original_count = len(processed_subs)
                processed_subs = self._get_merged_subtitles(processed_subs, merge_symbol)
                merged_count = original_count - len(processed_subs)
                info_log.append(f"Merged {merged_count} cues.")
        try:
            delay_sec = float(self.sync_delay_entry.get())
            if delay_sec != 0.0: processed_subs.shift(seconds=delay_sec); info_log.append(
                f"Shifted all cues by {delay_sec} seconds.")
        except ValueError:
            messagebox.showerror("Error", "Invalid delay value. Please enter a number."); return
        self.subtitles = processed_subs
        # Use a more robust temp file location
        temp_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
        temp_sub_path = os.path.join(temp_dir, "temp_subs.srt")
        self.subtitles.save(temp_sub_path, encoding='utf-8')
        self.player.video_set_subtitle_file(temp_sub_path)
        if info_log: messagebox.showinfo("Settings Applied", "\n".join(info_log) or "Settings re-applied.")
        self.is_repeating_active = True
        self.skip_subtitle_btn.config(state=tk.NORMAL)
        self.prev_subtitle_btn.config(state=tk.NORMAL)
        self.update_subtitle_index_on_seek(self.player.get_time())

    def play_pause(self, *args):
        if not self.player.get_media(): self.load_video(); return
        if self.player.is_playing():
            self.player.pause(); self.play_pause_btn.config(text="▶"); self.is_paused = True
        else:
            self.player.play(); self.play_pause_btn.config(text="❚❚"); self.is_paused = False

    def stop(self, *args):
        self.player.stop();
        self.play_pause_btn.config(text="▶");
        self.is_paused = True
        self.progress_slider.set(0);
        self.subtitle_index = 0;
        self.repeat_counter = 0

    def skip_subtitle(self, *args):
        if not self.subtitles or self.subtitle_index >= len(self.subtitles) - 1: return
        self.subtitle_index += 1;
        self.repeat_counter = 0
        next_cue = self.subtitles[self.subtitle_index]
        self.player.set_time(max(0, next_cue.start.ordinal))
        if self.is_paused: self.play_pause()

    def previous_subtitle(self, *args):
        if not self.subtitles or self.subtitle_index <= 0: return
        self.subtitle_index -= 1;
        self.repeat_counter = 0
        prev_cue = self.subtitles[self.subtitle_index]
        self.player.set_time(max(0, prev_cue.start.ordinal))
        if self.is_paused: self.play_pause()

    def toggle_fullscreen(self, *args):
        self.is_fullscreen = not self.is_fullscreen
        self.master.attributes("-fullscreen", self.is_fullscreen)
        self.player.set_fullscreen(self.is_fullscreen)
        self.update_fullscreen_button()

    def update_fullscreen_button(self):
        if self.is_fullscreen:
            self.fullscreen_btn.config(text="Exit ⛶")
        else:
            self.fullscreen_btn.config(text="⛶")

    def set_volume(self, value):
        self.player.audio_set_volume(int(value))

    def update_subtitle_index_on_seek(self, time_ms):
        if not self.subtitles: return
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal <= time_ms < cue.end.ordinal: self.subtitle_index = i; self.repeat_counter = 0; return
        for i, cue in enumerate(self.subtitles):
            if cue.start.ordinal > time_ms: self.subtitle_index = i; self.repeat_counter = 0; return

    def ms_to_time_str(self, ms):
        if ms < 0: ms = 0
        s, ms = divmod(ms, 1000);
        m, s = divmod(s, 60);
        h, m = divmod(m, 60)
        return f"{h:02}:{m:02}:{s:02}"

    def handle_keypress(self, event):
        if isinstance(event.widget, (tk.Entry, tk.Spinbox)): return
        key = event.keysym
        if key == 'space':
            self.play_pause()
        elif key.lower() == 's':
            self.stop()
        elif key.lower() == 'f':
            self.toggle_fullscreen()
        elif key == 'Right':
            self.skip_subtitle()
        elif key == 'Left':
            self.previous_subtitle()


if __name__ == "__main__":
    root = tk.Tk()
    app = VLCPlayerApp(root)
    root.mainloop()