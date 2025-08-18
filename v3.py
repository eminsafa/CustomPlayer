import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import vlc
import pysrt
import os
import sys


class SubtitleRepeaterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Subtitle Repeater Player (V3 - Smooth Seeking)")
        self.root.geometry("800x600")

        # --- VLC Setup ---
        try:
            # Add options to reduce caching, which can help with seeking latency
            vlc_options = "--no-video-title-show --no-xlib"
            self.vlc_instance = vlc.Instance(vlc_options)
            self.player = self.vlc_instance.media_player_new()
        except Exception as e:
            messagebox.showerror("VLC Error",
                                 f"Could not initialize VLC. Error: {e}\n(Is VLC installed and is the architecture, e.g., 64-bit, correct?)")
            self.root.destroy()
            return

        # --- State Variables ---
        self.is_playing = False
        self.is_paused_by_user = True
        self.subtitles = None
        self.current_subtitle_index = 0
        self.in_repeat_loop = False
        self.repeat_counter = 0
        self.repeat_start_time = 0
        self.repeat_end_time = 0
        self.is_user_seeking = False
        self.is_system_seeking = False  # Flag for our smooth seek operation

        # --- UI Setup ---
        self.create_widgets()
        self.update_ui()

    def create_widgets(self):
        self.video_frame = tk.Frame(self.root, bg="black")
        self.video_frame.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)
        if sys.platform.startswith('win'):
            self.player.set_hwnd(self.video_frame.winfo_id())
        elif sys.platform.startswith('darwin'):
            self.player.set_nsobject(self.video_frame.winfo_id())
        else:
            self.player.set_xwindow(self.video_frame.winfo_id())

        self.subtitle_label = tk.Label(self.root, text="Load a video and subtitles to begin.", font=("Arial", 14),
                                       wraplength=780, justify="center")
        self.subtitle_label.pack(pady=10, fill=tk.X, padx=10)

        controls_frame = tk.Frame(self.root)
        controls_frame.pack(pady=5, fill=tk.X)

        self.progress_scale = ttk.Scale(controls_frame, from_=0, to=1000, orient=tk.HORIZONTAL,
                                        command=self.on_seek_preview)
        self.progress_scale.bind("<ButtonPress-1>", self.on_slider_press)
        self.progress_scale.bind("<ButtonRelease-1>", self.on_slider_release)
        self.progress_scale.pack(fill=tk.X, padx=10, expand=True)

        buttons_frame = tk.Frame(controls_frame)
        buttons_frame.pack(pady=5)
        self.play_pause_button = tk.Button(buttons_frame, text="Play", width=10, command=self.play_pause)
        self.play_pause_button.grid(row=0, column=0, padx=5)
        tk.Label(buttons_frame, text="Repeat Count:").grid(row=0, column=1, padx=(10, 2))
        self.repeat_spinbox = tk.Spinbox(buttons_frame, from_=1, to=10, width=5)
        self.repeat_spinbox.grid(row=0, column=2, padx=5)
        self.repeat_spinbox.delete(0, "end");
        self.repeat_spinbox.insert(0, "3")
        self.open_video_button = tk.Button(buttons_frame, text="Open Video", command=self.open_video)
        self.open_video_button.grid(row=0, column=3, padx=5)
        self.open_srt_button = tk.Button(buttons_frame, text="Open Subtitle (.srt)", command=self.open_srt)
        self.open_srt_button.grid(row=0, column=4, padx=5)

    def open_video(self):
        video_path = filedialog.askopenfilename(filetypes=(("Video files", "*.mp4 *.mkv *.avi"), ("All files", "*.*")))
        if not video_path: return
        self.player.set_media(self.vlc_instance.media_new(video_path))
        self.play_pause_button.config(text="Play")
        self.is_playing = False;
        self.is_paused_by_user = True
        self.reset_playback_state()
        srt_path = os.path.splitext(video_path)[0] + ".srt"
        if os.path.exists(srt_path): self.load_srt(srt_path)

    def open_srt(self):
        srt_path = filedialog.askopenfilename(filetypes=(("SRT files", "*.srt"),))
        if srt_path: self.load_srt(srt_path)

    def load_srt(self, srt_path):
        for enc in ['utf-8', 'latin-1', 'windows-1252']:
            try:
                self.subtitles = pysrt.open(srt_path, encoding=enc)
                self.reset_playback_state()
                messagebox.showinfo("Success", f"Subtitles loaded ({enc}): {len(self.subtitles)} lines found.")
                return
            except Exception:
                continue
        self.subtitles = None
        messagebox.showerror("Error", "Could not load subtitle file. Unsupported encoding or corrupt file.")

    def reset_playback_state(self):
        self.current_subtitle_index = 0
        self.in_repeat_loop = False
        self.subtitle_label.config(text="")

    def play_pause(self):
        if not self.player.get_media(): return messagebox.showwarning("No Video", "Please open a video file first.")
        if self.player.is_playing():
            self.player.pause()
            self.play_pause_button.config(text="Play")
            self.is_paused_by_user = True
        else:
            self.player.play()
            self.play_pause_button.config(text="Pause")
            self.is_paused_by_user = False
        self.is_playing = not self.is_paused_by_user

    def perform_efficient_seek(self, time_ms):
        """
        Pauses, seeks, and then plays the video. This is much smoother
        than seeking while the video is playing.
        """
        self.is_system_seeking = True
        self.player.pause()
        self.player.set_time(time_ms)
        # Give the VLC engine a moment to process the seek before playing
        self.root.after(30, self.delayed_play)


    def delayed_play(self):
        """Plays the video after a short delay and resets the system seeking flag."""
        if not self.is_paused_by_user:  # Only resume if the user didn't pause in the meantime
            self.player.play()
        self.is_system_seeking = False

    def on_slider_press(self, event):
        if self.player.get_media(): self.is_user_seeking = True

    def on_slider_release(self, event):
        if self.player.get_media() and self.is_user_seeking:
            self.is_user_seeking = False
            self.seek_from_slider(self.progress_scale.get())

    def on_seek_preview(self, value):
        # This function is called continuously while dragging
        # We only want to act on the final value in on_slider_release
        pass

    def seek_from_slider(self, value):
        pos = float(value) / 1000.0
        self.player.set_position(pos)
        if self.subtitles:
            target_time_ms = self.player.get_length() * pos
            self.find_subtitle_for_time(target_time_ms)
            self.in_repeat_loop = False
            self.subtitle_label.config(text="")

    def find_subtitle_for_time(self, time_ms):
        if not self.subtitles: return
        for i, sub in enumerate(self.subtitles):
            if sub.end.ordinal > time_ms:
                self.current_subtitle_index = i
                return
        self.current_subtitle_index = len(self.subtitles)

    def update_ui(self):
        # Continue updating even if system is seeking, but not if user paused.
        if self.is_paused_by_user and not self.is_system_seeking:
            self.root.after(150, self.update_ui)
            return

        current_time_ms = self.player.get_time()

        if not self.is_user_seeking:
            length = self.player.get_length()
            if length > 0: self.progress_scale.set(current_time_ms / length * 1000)

        if not self.subtitles or self.current_subtitle_index >= len(self.subtitles):
            self.subtitle_label.config(text="")
            self.root.after(100, self.update_ui)
            return

        if self.in_repeat_loop:
            if current_time_ms >= self.repeat_end_time or current_time_ms < self.repeat_start_time - 50:  # -50ms tolerance
                self.repeat_counter += 1
                if self.repeat_counter < int(self.repeat_spinbox.get()):
                    # THIS IS THE KEY CHANGE FOR SMOOTHNESS
                    self.perform_efficient_seek(self.repeat_start_time)
                else:
                    self.in_repeat_loop = False
                    self.current_subtitle_index += 1
                    self.subtitle_label.config(text="")
        else:
            sub = self.subtitles[self.current_subtitle_index]
            if sub.start.ordinal <= current_time_ms < sub.end.ordinal:
                self.in_repeat_loop = True
                self.repeat_counter = 0
                self.repeat_start_time = sub.start.ordinal
                self.repeat_end_time = sub.end.ordinal
                self.subtitle_label.config(text=sub.text_without_tags)
                # On first trigger, also use the efficient seek for a clean start
                self.perform_efficient_seek(self.repeat_start_time)

        self.root.after(50, self.update_ui)

    def on_closing(self):
        self.player.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = SubtitleRepeaterApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()