import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import mpv
import threading
import time
import os
import re


class SubtitleEntry:
    def __init__(self, start_time, end_time, text):
        self.start_time = start_time
        self.end_time = end_time
        self.text = text


class ForeignLanguageLearningPlayer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Foreign Language Learning Player")
        self.root.geometry("900x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # MPV player setup
        self.player = None
        self.video_file = None
        self.subtitle_file = None
        self.subtitles = []
        self.current_subtitle_index = 0
        self.repeat_count = tk.IntVar(value=1)
        self.current_repeats = 0
        self.is_playing = False
        self.is_fullscreen = False
        self.position_update_thread = None
        self.stop_position_thread = False

        self.setup_ui()

    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Video container frame (takes most space)
        video_frame = ttk.LabelFrame(main_frame, text="Video Player")
        video_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self.video_container = tk.Frame(video_frame, bg='black')
        self.video_container.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)

        # Bottom control panel - more compact
        control_panel = ttk.LabelFrame(main_frame, text="Controls")
        control_panel.pack(fill=tk.X)

        # Row 1: File selection
        file_row = ttk.Frame(control_panel)
        file_row.pack(fill=tk.X, padx=5, pady=2)

        ttk.Button(file_row, text="Video", command=self.choose_video, width=10).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(file_row, text="Subtitle", command=self.choose_subtitle, width=10).pack(side=tk.LEFT, padx=(0, 10))

        # Repeat settings in same row
        ttk.Label(file_row, text="Repeat:").pack(side=tk.LEFT, padx=(0, 3))
        repeat_spinbox = ttk.Spinbox(file_row, from_=1, to=10, width=4, textvariable=self.repeat_count)
        repeat_spinbox.pack(side=tk.LEFT, padx=(0, 10))

        # Fullscreen button
        self.fullscreen_button = ttk.Button(file_row, text="Fullscreen", command=self.toggle_fullscreen, width=12)
        self.fullscreen_button.pack(side=tk.RIGHT)

        # Row 2: Playback controls
        playback_row = ttk.Frame(control_panel)
        playback_row.pack(fill=tk.X, padx=5, pady=2)

        self.play_button = ttk.Button(playback_row, text="Play", command=self.toggle_play_pause, width=8)
        self.play_button.pack(side=tk.LEFT, padx=(0, 3))

        ttk.Button(playback_row, text="Stop", command=self.stop, width=8).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(playback_row, text="← Prev", command=self.previous_subtitle, width=8).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(playback_row, text="Next →", command=self.next_subtitle, width=8).pack(side=tk.LEFT, padx=(0, 10))

        # Status info
        self.status_label = ttk.Label(playback_row, text="Load video and subtitle files to begin")
        self.status_label.pack(side=tk.LEFT, padx=(10, 0))

        # Row 3: File info - very compact
        info_row = ttk.Frame(control_panel)
        info_row.pack(fill=tk.X, padx=5, pady=(0, 3))

        self.file_info_label = ttk.Label(info_row, text="No files loaded", foreground="gray", font=('Arial', 8))
        self.file_info_label.pack(anchor=tk.W)

    def choose_video(self):
        file_path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm"),
                ("All files", "*.*")
            ]
        )
        if file_path:
            self.video_file = file_path
            self.update_file_info()
            self.status_label.config(text="Video loaded. Select subtitle file.")

    def choose_subtitle(self):
        if not self.video_file:
            messagebox.showwarning("Warning", "Please select a video file first.")
            return

        file_path = filedialog.askopenfilename(
            title="Select Subtitle File",
            filetypes=[
                ("Subtitle files", "*.srt *.vtt *.ass"),
                ("All files", "*.*")
            ]
        )
        if file_path:
            self.subtitle_file = file_path
            self.update_file_info()
            self.load_subtitles()
            self.initialize_player()

    def update_file_info(self):
        video_name = os.path.basename(self.video_file) if self.video_file else "No video"
        subtitle_name = os.path.basename(self.subtitle_file) if self.subtitle_file else "No subtitle"
        self.file_info_label.config(text=f"Video: {video_name} | Subtitle: {subtitle_name}")

    def load_subtitles(self):
        """Load and parse SRT subtitle file"""
        self.subtitles = []
        try:
            with open(self.subtitle_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Simple SRT parser
            subtitle_blocks = re.split(r'\n\s*\n', content.strip())

            for block in subtitle_blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    # Parse time format: 00:00:20,000 --> 00:00:24,400
                    time_line = lines[1]
                    time_match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})',
                                          time_line)

                    if time_match:
                        start_h, start_m, start_s, start_ms, end_h, end_m, end_s, end_ms = map(int, time_match.groups())
                        start_time = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000
                        end_time = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000

                        # Clean subtitle text
                        text = '\n'.join(lines[2:])
                        # Remove HTML tags if any
                        text = re.sub(r'<[^>]+>', '', text)
                        self.subtitles.append(SubtitleEntry(start_time, end_time, text.strip()))

            self.status_label.config(text=f"Loaded {len(self.subtitles)} subtitles. Ready to play!")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load subtitle file: {str(e)}")

    def initialize_player(self):
        """Initialize MPV player with video file"""
        try:
            if self.player:
                self.player.terminate()

            # Update the video container to ensure it's ready for embedding
            self.video_container.update()
            wid = self.video_container.winfo_id()

            self.player = mpv.MPV(
                wid=str(wid),
                vo='x11',
                keep_open='yes',
                pause=True,
                # Subtitle styling for better visibility
                sub_font_size=24,
                sub_color='#FFFFFF',
                sub_border_color='#000000',
                sub_border_size=2,
                sub_shadow_offset=1,
                sub_shadow_color='#000000',
                sub_pos=90,  # Position subtitles at bottom
                # Enable fullscreen toggle
                fs=False
            )

            self.player.play(self.video_file)

            # Load subtitle file into MPV
            if self.subtitle_file:
                self.player.sub_add(self.subtitle_file)
                self.player.sub_visibility = True

            self.current_subtitle_index = 0
            self.current_repeats = 0

            # Start position monitoring thread
            self.stop_position_thread = False
            if self.position_update_thread and self.position_update_thread.is_alive():
                self.stop_position_thread = True
                self.position_update_thread.join()

            self.position_update_thread = threading.Thread(target=self.monitor_position, daemon=True)
            self.position_update_thread.start()

            self.status_label.config(text="Ready to play!")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to initialize player: {str(e)}")

    def monitor_position(self):
        """Monitor video position and handle subtitle repeat logic"""
        while not self.stop_position_thread and self.player:
            try:
                if self.is_playing and self.subtitles and self.current_subtitle_index < len(self.subtitles):
                    current_time = self.player.time_pos or 0
                    current_subtitle = self.subtitles[self.current_subtitle_index]

                    # Check if we've reached the end of current subtitle
                    if current_time >= current_subtitle.end_time:
                        self.current_repeats += 1

                        if self.current_repeats < self.repeat_count.get():
                            # Repeat current subtitle
                            self.player.seek(current_subtitle.start_time, reference='absolute')
                            self.root.after(0, lambda: self.status_label.config(
                                text=f"Subtitle {self.current_subtitle_index + 1}/{len(self.subtitles)} - Repeat {self.current_repeats + 1}/{self.repeat_count.get()}"
                            ))
                        else:
                            # Move to next subtitle
                            self.current_repeats = 0
                            self.current_subtitle_index += 1

                            if self.current_subtitle_index < len(self.subtitles):
                                next_subtitle = self.subtitles[self.current_subtitle_index]
                                self.player.seek(next_subtitle.start_time, reference='absolute')
                                self.root.after(0, lambda: self.status_label.config(
                                    text=f"Subtitle {self.current_subtitle_index + 1}/{len(self.subtitles)} - Repeat 1/{self.repeat_count.get()}"
                                ))
                            else:
                                # End of subtitles
                                self.is_playing = False
                                self.player.pause = True
                                self.root.after(0, lambda: self.play_button.config(text="Play"))
                                self.root.after(0, lambda: self.status_label.config(text="Finished all subtitles."))

                time.sleep(0.1)

            except Exception as e:
                print(f"Monitor error: {e}")
                time.sleep(0.5)

    def toggle_play_pause(self):
        if not self.player or not self.subtitles:
            messagebox.showwarning("Warning", "Please load both video and subtitle files first.")
            return

        if self.is_playing:
            self.pause()
        else:
            self.play()

    def play(self):
        if self.player and self.subtitles:
            if self.current_subtitle_index < len(self.subtitles):
                current_subtitle = self.subtitles[self.current_subtitle_index]
                self.player.seek(current_subtitle.start_time, reference='absolute')

            self.player.pause = False
            self.is_playing = True
            self.play_button.config(text="Pause")
            self.status_label.config(
                text=f"Playing - Subtitle {self.current_subtitle_index + 1}/{len(self.subtitles)} - Repeat {self.current_repeats + 1}/{self.repeat_count.get()}")

    def pause(self):
        if self.player:
            self.player.pause = True
            self.is_playing = False
            self.play_button.config(text="Play")
            self.status_label.config(text="Paused")

    def stop(self):
        if self.player:
            self.player.pause = True
            self.is_playing = False
            self.current_subtitle_index = 0
            self.current_repeats = 0
            self.play_button.config(text="Play")
            if self.subtitles:
                self.player.seek(self.subtitles[0].start_time, reference='absolute')
            self.status_label.config(text="Stopped")

    def previous_subtitle(self):
        if self.subtitles and self.current_subtitle_index > 0:
            self.current_subtitle_index -= 1
            self.current_repeats = 0
            if self.player:
                subtitle = self.subtitles[self.current_subtitle_index]
                self.player.seek(subtitle.start_time, reference='absolute')
                self.status_label.config(text=f"Subtitle {self.current_subtitle_index + 1}/{len(self.subtitles)}")

    def next_subtitle(self):
        if self.subtitles and self.current_subtitle_index < len(self.subtitles) - 1:
            self.current_subtitle_index += 1
            self.current_repeats = 0
            if self.player:
                subtitle = self.subtitles[self.current_subtitle_index]
                self.player.seek(subtitle.start_time, reference='absolute')
                self.status_label.config(text=f"Subtitle {self.current_subtitle_index + 1}/{len(self.subtitles)}")

    def toggle_fullscreen(self):
        if not self.player:
            messagebox.showwarning("Warning", "Please load a video file first.")
            return

        try:
            if self.is_fullscreen:
                # Exit fullscreen
                self.player.fullscreen = False
                self.fullscreen_button.config(text="Fullscreen")
                self.is_fullscreen = False

                # Re-embed the player in the tkinter window
                wid = self.video_container.winfo_id()
                self.player.wid = str(wid)

            else:
                # Enter fullscreen
                self.player.fullscreen = True
                self.fullscreen_button.config(text="Exit Fullscreen")
                self.is_fullscreen = True

        except Exception as e:
            print(f"Fullscreen toggle error: {e}")
            messagebox.showerror("Error", f"Failed to toggle fullscreen: {str(e)}")

    def on_closing(self):
        """Handle window close event"""
        self.stop_position_thread = True

        if self.position_update_thread and self.position_update_thread.is_alive():
            self.position_update_thread.join(timeout=1)

        if self.player:
            self.player.terminate()

        self.root.quit()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    # Check if python-mpv is available
    try:
        import mpv
    except ImportError:
        print("Error: python-mpv is required but not installed.")
        print("Please install it using: pip install python-mpv")
        print("You may also need to install MPV player on your system.")
        exit(1)

    app = ForeignLanguageLearningPlayer()
    app.run()