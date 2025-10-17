import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import vlc
import threading
import time
import os
import sys


class LanguageLearningPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Foreign Language Learning Video Player")
        self.root.geometry("800x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # VLC setup
        self.instance = vlc.Instance('--no-xlib')
        self.player = self.instance.media_player_new()

        # Variables
        self.video_path = None
        self.subtitle_path = None
        self.is_playing = False
        self.is_paused = False
        self.repeat_count = 1
        self.current_repeats = 0
        self.subtitle_start_time = 0
        self.subtitle_end_time = 0
        self.is_fullscreen = False
        self.subtitles = []
        self.current_subtitle_index = -1

        self.setup_ui()
        self.setup_player_events()

    def setup_ui(self):
        # Main frame
        main_frame = tk.Frame(self.root, bg='black')
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Video frame
        self.video_frame = tk.Frame(main_frame, bg='black', height=400)
        self.video_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.video_frame.pack_propagate(False)

        # Control panel
        control_frame = tk.Frame(main_frame, bg='lightgray', height=120)
        control_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        control_frame.pack_propagate(False)

        # File selection frame
        file_frame = tk.Frame(control_frame)
        file_frame.pack(pady=5)

        tk.Button(file_frame, text="Select Video", command=self.select_video,
                  width=12, bg='lightblue').pack(side=tk.LEFT, padx=5)
        tk.Button(file_frame, text="Select Subtitle", command=self.select_subtitle,
                  width=12, bg='lightgreen').pack(side=tk.LEFT, padx=5)

        # Playback controls frame
        playback_frame = tk.Frame(control_frame)
        playback_frame.pack(pady=5)

        tk.Button(playback_frame, text="Play", command=self.play,
                  width=8, bg='green', fg='white').pack(side=tk.LEFT, padx=2)
        tk.Button(playback_frame, text="Pause", command=self.pause,
                  width=8, bg='orange', fg='white').pack(side=tk.LEFT, padx=2)
        tk.Button(playback_frame, text="Stop", command=self.stop,
                  width=8, bg='red', fg='white').pack(side=tk.LEFT, padx=2)

        tk.Button(playback_frame, text="Previous Sub", command=self.previous_subtitle,
                  width=10, bg='blue', fg='white').pack(side=tk.LEFT, padx=2)
        tk.Button(playback_frame, text="Next Sub", command=self.next_subtitle,
                  width=10, bg='blue', fg='white').pack(side=tk.LEFT, padx=2)

        # Repeat and fullscreen controls
        controls_frame = tk.Frame(control_frame)
        controls_frame.pack(pady=5)

        tk.Label(controls_frame, text="Repeat Count:").pack(side=tk.LEFT, padx=5)
        self.repeat_var = tk.StringVar(value="1")
        repeat_spinbox = tk.Spinbox(controls_frame, from_=1, to=10, width=5,
                                    textvariable=self.repeat_var, command=self.update_repeat_count)
        repeat_spinbox.pack(side=tk.LEFT, padx=5)

        tk.Button(controls_frame, text="Fullscreen", command=self.toggle_fullscreen,
                  width=10, bg='purple', fg='white').pack(side=tk.LEFT, padx=10)

        # Status label
        self.status_label = tk.Label(control_frame, text="Select a video and subtitle file to begin",
                                     bg='lightgray', fg='black')
        self.status_label.pack(pady=5)

    def setup_player_events(self):
        # Set the video output to the tkinter frame
        if sys.platform.startswith('linux'):
            self.player.set_xwindow(self.video_frame.winfo_id())
        elif sys.platform == "win32":
            self.player.set_hwnd(self.video_frame.winfo_id())
        elif sys.platform == "darwin":
            self.player.set_nsobject(self.video_frame.winfo_id())

    def select_video(self):
        video_file = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video files", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm")]
        )
        if video_file:
            self.video_path = video_file
            self.status_label.config(text=f"Video: {os.path.basename(video_file)}")
            self.load_video()

    def select_subtitle(self):
        subtitle_file = filedialog.askopenfilename(
            title="Select Subtitle File",
            filetypes=[("Subtitle files", "*.srt *.vtt *.ass *.ssa")]
        )
        if subtitle_file:
            self.subtitle_path = subtitle_file
            self.status_label.config(text=f"Subtitle: {os.path.basename(subtitle_file)}")
            self.load_subtitles()

    def load_video(self):
        if self.video_path:
            media = self.instance.media_new(self.video_path)
            self.player.set_media(media)
            self.status_label.config(text="Video loaded. Ready to play.")

    def load_subtitles(self):
        if not self.subtitle_path:
            return

        self.subtitles = []
        try:
            with open(self.subtitle_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Simple SRT parser
            if self.subtitle_path.endswith('.srt'):
                self.parse_srt(content)
            else:
                messagebox.showwarning("Warning", "Only SRT subtitles are fully supported")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load subtitles: {str(e)}")

    def parse_srt(self, content):
        blocks = content.strip().split('\n\n')
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                try:
                    time_line = lines[1]
                    start_time, end_time = time_line.split(' --> ')

                    start_ms = self.time_to_milliseconds(start_time.strip())
                    end_ms = self.time_to_milliseconds(end_time.strip())

                    text = '\n'.join(lines[2:])

                    self.subtitles.append({
                        'start': start_ms,
                        'end': end_ms,
                        'text': text
                    })
                except:
                    continue

        self.status_label.config(text=f"Loaded {len(self.subtitles)} subtitles")

    def time_to_milliseconds(self, time_str):
        # Convert "HH:MM:SS,mmm" to milliseconds
        time_part, ms_part = time_str.split(',')
        hours, minutes, seconds = map(int, time_part.split(':'))
        milliseconds = int(ms_part)

        total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
        return total_ms

    def play(self):
        if not self.video_path:
            messagebox.showwarning("Warning", "Please select a video file first")
            return

        if self.is_paused:
            self.player.pause()
            self.is_paused = False
            self.status_label.config(text="Playing (resumed)")
        else:
            self.player.play()
            self.is_playing = True
            self.is_paused = False
            self.status_label.config(text="Playing")

        # Start monitoring for subtitle repetition
        if self.subtitles and not hasattr(self, 'monitor_thread'):
            self.monitor_thread = threading.Thread(target=self.monitor_playback, daemon=True)
            self.monitor_thread.start()

    def pause(self):
        if self.is_playing:
            self.player.pause()
            self.is_paused = True
            self.status_label.config(text="Paused")

    def stop(self):
        self.player.stop()
        self.is_playing = False
        self.is_paused = False
        self.current_repeats = 0
        self.current_subtitle_index = -1
        self.status_label.config(text="Stopped")

    def update_repeat_count(self):
        try:
            self.repeat_count = int(self.repeat_var.get())
        except ValueError:
            self.repeat_count = 1

    def previous_subtitle(self):
        if self.subtitles and self.current_subtitle_index > 0:
            self.current_subtitle_index -= 1
            self.play_subtitle(self.current_subtitle_index)

    def next_subtitle(self):
        if self.subtitles and self.current_subtitle_index < len(self.subtitles) - 1:
            self.current_subtitle_index += 1
            self.play_subtitle(self.current_subtitle_index)

    def play_subtitle(self, index):
        if 0 <= index < len(self.subtitles):
            subtitle = self.subtitles[index]
            self.player.set_time(subtitle['start'])
            self.current_repeats = 0
            self.subtitle_start_time = subtitle['start']
            self.subtitle_end_time = subtitle['end']

            if not self.is_playing:
                self.play()

            self.status_label.config(text=f"Playing subtitle {index + 1}: {subtitle['text'][:50]}...")

    def monitor_playback(self):
        while self.is_playing:
            if not self.is_paused and self.subtitles:
                current_time = self.player.get_time()

                # Find current subtitle
                for i, subtitle in enumerate(self.subtitles):
                    if subtitle['start'] <= current_time <= subtitle['end']:
                        if self.current_subtitle_index != i:
                            self.current_subtitle_index = i
                            self.current_repeats = 0
                            self.subtitle_start_time = subtitle['start']
                            self.subtitle_end_time = subtitle['end']
                        break

                # Check if we need to repeat
                if (self.current_subtitle_index >= 0 and
                        current_time >= self.subtitle_end_time and
                        self.current_repeats < self.repeat_count - 1):
                    self.current_repeats += 1
                    self.player.set_time(self.subtitle_start_time)

                    subtitle = self.subtitles[self.current_subtitle_index]
                    self.status_label.config(
                        text=f"Repeat {self.current_repeats + 1}/{self.repeat_count}: {subtitle['text'][:50]}...")

            time.sleep(0.1)

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.player.set_fullscreen(False)
            self.is_fullscreen = False
        else:
            self.player.set_fullscreen(True)
            self.is_fullscreen = True

    def on_closing(self):
        self.stop()
        if self.player:
            self.player.release()
        if self.instance:
            self.instance.release()
        self.root.quit()
        self.root.destroy()
        sys.exit(0)


def main():
    try:
        import vlc
    except ImportError:
        print("Error: python-vlc is required. Install it with: pip install python-vlc")
        print("Also make sure VLC Media Player is installed on your system.")
        return

    root = tk.Tk()
    app = LanguageLearningPlayer(root)
    root.mainloop()


if __name__ == "__main__":
    main()