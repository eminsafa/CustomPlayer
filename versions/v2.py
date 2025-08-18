import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import vlc
import pysrt
import os
import sys


class SubtitleRepeaterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Subtitle Repeater Player (V2 - Efficient)")
        self.root.geometry("800x600")

        # --- VLC Setup ---
        try:
            self.vlc_instance = vlc.Instance()
            self.player = self.vlc_instance.media_player_new()
        except NameError:
            messagebox.showerror("VLC Error", "VLC is not installed. Please install VLC from videolan.org.")
            self.root.destroy()
            return
        except Exception as e:
            messagebox.showerror("VLC Error",
                                 f"Could not initialize VLC. Error: {e}\n(Is your Python/VLC architecture mismatched? e.g., 32-bit vs 64-bit)")
            self.root.destroy()
            return

        # --- State Variables ---
        self.video_path = None
        self.subtitles = None
        self.is_playing = False
        self.is_paused = False
        self.current_subtitle_index = 0
        self.in_repeat_loop = False
        self.repeat_counter = 0
        self.repeat_start_time = 0
        self.repeat_end_time = 0
        # Flag to prevent slider updates from re-triggering seek logic
        self.is_user_seeking = False

        # --- UI Setup ---
        self.create_widgets()
        self.update_ui()

    def create_widgets(self):
        # --- Video Frame ---
        self.video_frame = tk.Frame(self.root, bg="black")
        self.video_frame.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

        # Set the video output window
        if sys.platform.startswith('win'):
            self.player.set_hwnd(self.video_frame.winfo_id())
        elif sys.platform.startswith('darwin'):
            self.player.set_nsobject(self.video_frame.winfo_id())
        else:  # Linux
            self.player.set_xwindow(self.video_frame.winfo_id())

        # --- Subtitle Display ---
        self.subtitle_label = tk.Label(self.root, text="Load a video and subtitles to begin.",
                                       font=("Arial", 14), wraplength=780, justify="center")
        self.subtitle_label.pack(pady=10, fill=tk.X, padx=10)

        # --- Controls Frame ---
        controls_frame = tk.Frame(self.root)
        controls_frame.pack(pady=5, fill=tk.X)

        # --- Progress Bar ---
        self.progress_scale = ttk.Scale(controls_frame, from_=0, to=1000, orient=tk.HORIZONTAL, command=self.on_seek)
        self.progress_scale.bind("<ButtonPress-1>", self.on_slider_press)
        self.progress_scale.bind("<ButtonRelease-1>", self.on_slider_release)
        self.progress_scale.pack(fill=tk.X, padx=10, expand=True)

        # --- Buttons and Repeats Frame ---
        buttons_frame = tk.Frame(controls_frame)
        buttons_frame.pack(pady=5)

        self.play_pause_button = tk.Button(buttons_frame, text="Play", width=10, command=self.play_pause)
        self.play_pause_button.grid(row=0, column=0, padx=5)

        tk.Label(buttons_frame, text="Repeat Count:").grid(row=0, column=1, padx=(10, 2))
        self.repeat_spinbox = tk.Spinbox(buttons_frame, from_=1, to=10, width=5)
        self.repeat_spinbox.grid(row=0, column=2, padx=5)
        self.repeat_spinbox.delete(0, "end")
        self.repeat_spinbox.insert(0, "3")

        self.open_video_button = tk.Button(buttons_frame, text="Open Video", command=self.open_video)
        self.open_video_button.grid(row=0, column=3, padx=5)

        self.open_srt_button = tk.Button(buttons_frame, text="Open Subtitle (.srt)", command=self.open_srt)
        self.open_srt_button.grid(row=0, column=4, padx=5)

    def open_video(self):
        self.video_path = filedialog.askopenfilename(
            filetypes=(("Video files", "*.mp4 *.mkv *.avi"), ("All files", "*.*"))
        )
        if not self.video_path: return

        self.player.set_media(self.vlc_instance.media_new(self.video_path))
        self.play_pause_button.config(text="Play")
        self.is_playing = False
        self.is_paused = True
        self.reset_playback_state()

        # Auto-load subtitles with the same name
        srt_path = os.path.splitext(self.video_path)[0] + ".srt"
        if os.path.exists(srt_path):
            self.load_srt(srt_path)

    def open_srt(self):
        srt_path = filedialog.askopenfilename(filetypes=(("SRT files", "*.srt"),))
        if srt_path:
            self.load_srt(srt_path)

    def load_srt(self, srt_path):
        """Loads an SRT file, trying multiple common encodings."""
        encodings_to_try = ['utf-8', 'latin-1', 'windows-1252']
        loaded_subtitles = None
        for enc in encodings_to_try:
            try:
                loaded_subtitles = pysrt.open(srt_path, encoding=enc)
                print(f"Successfully loaded subtitle with encoding: {enc}")
                break
            except (UnicodeDecodeError, IOError):
                continue

        if loaded_subtitles:
            self.subtitles = loaded_subtitles
            self.reset_playback_state()
            messagebox.showinfo("Success", f"Subtitles loaded: {len(self.subtitles)} lines found.")
        else:
            self.subtitles = None
            messagebox.showerror("Error", "Could not load subtitle file. Unsupported encoding or corrupt file.")

    def reset_playback_state(self):
        self.current_subtitle_index = 0
        self.in_repeat_loop = False
        self.subtitle_label.config(text="")

    def play_pause(self):
        if not self.player.get_media():
            messagebox.showwarning("No Video", "Please open a video file first.")
            return

        if self.player.is_playing():
            self.player.pause()
            self.play_pause_button.config(text="Play")
            self.is_paused = True
        else:
            self.player.play()
            self.play_pause_button.config(text="Pause")
            self.is_paused = False

        self.is_playing = not self.is_paused

    def on_slider_press(self, event):
        self.is_user_seeking = True

    def on_slider_release(self, event):
        self.on_seek(self.progress_scale.get())
        self.is_user_seeking = False

    def on_seek(self, value):
        if not self.is_user_seeking: return  # Only seek on explicit user action
        if self.player.get_media():
            pos = float(value) / 1000.0
            self.player.set_position(pos)

            # When seeking, find the correct new subtitle and exit any repeat loop
            if self.subtitles:
                target_time_ms = self.player.get_length() * pos
                self.find_subtitle_for_time(target_time_ms)
                self.in_repeat_loop = False
                self.subtitle_label.config(text="")

    def find_subtitle_for_time(self, time_ms):
        """Finds the index of the subtitle active at, or coming after, a given time."""
        if not self.subtitles: return
        for i, sub in enumerate(self.subtitles):
            if sub.end.ordinal > time_ms:
                self.current_subtitle_index = i
                return
        self.current_subtitle_index = len(self.subtitles)  # Reached end

    def update_ui(self):
        """The main loop that drives the subtitle logic."""
        if not self.player.is_playing():
            self.root.after(150, self.update_ui)
            return

        current_time_ms = self.player.get_time()

        # Update progress bar only if user is not dragging it
        if not self.is_user_seeking:
            length = self.player.get_length()
            if length > 0:
                pos = current_time_ms / length * 1000
                self.progress_scale.set(pos)

        if not self.subtitles or self.current_subtitle_index >= len(self.subtitles):
            self.subtitle_label.config(text="")  # No more subs
            self.root.after(100, self.update_ui)
            return

        # --- STATE MACHINE: EITHER REPEATING OR LOOKING FOR NEXT SUB ---

        if self.in_repeat_loop:
            # STATE 1: We are in a repeat loop for a single subtitle
            if current_time_ms >= self.repeat_end_time or current_time_ms < self.repeat_start_time:
                self.repeat_counter += 1
                max_repeats = int(self.repeat_spinbox.get())

                if self.repeat_counter < max_repeats:
                    # EFFICIENT JUMP: Seek back to the start only once per repetition
                    self.player.set_time(self.repeat_start_time)
                else:
                    # Repetitions are done, exit loop and move to next subtitle
                    self.in_repeat_loop = False
                    self.current_subtitle_index += 1
                    self.subtitle_label.config(text="")
        else:
            # STATE 2: We are in normal playback, looking for the next subtitle to trigger
            sub = self.subtitles[self.current_subtitle_index]
            sub_start_ms = sub.start.ordinal
            sub_end_ms = sub.end.ordinal

            if sub_start_ms <= current_time_ms < sub_end_ms:
                # We have entered a new subtitle's timeframe. Start the repeat loop.
                self.in_repeat_loop = True
                self.repeat_counter = 0
                self.repeat_start_time = sub_start_ms
                self.repeat_end_time = sub_end_ms

                # Display the subtitle text and jump to the beginning for a clean first play
                self.subtitle_label.config(text=sub.text_without_tags)
                self.player.set_time(self.repeat_start_time)

        # Schedule the next update
        self.root.after(100, self.update_ui)


if __name__ == "__main__":
    root = tk.Tk()
    app = SubtitleRepeaterApp(root)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()