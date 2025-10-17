import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import vlc
import re
from datetime import timedelta
import platform
import os


class LanguageLearnerPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Foreign Language Learning Player")
        self.root.geometry("800x600")

        # --- VLC Setup ---
        try:
            self.vlc_instance = vlc.Instance("--no-xlib")
            self.player = self.vlc_instance.media_player_new()
        except NameError:
            messagebox.showerror("VLC Error", "VLC is not installed or not in the system's PATH.")
            self.root.destroy()
            return

        # --- State Variables ---
        self.subtitles = []
        self.current_subtitle_index = -1
        self.current_repeat_count = 0
        self.is_paused_by_user = False
        self.video_loaded = False

        # --- GUI Setup ---
        self.create_widgets()

        # --- Bind Window Close Event ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Start the update loop
        self.update_player_state()

    def create_widgets(self):
        """Creates and places all the GUI elements in the window."""

        # --- Video Frame ---
        self.video_frame = tk.Frame(self.root, bg="black")
        self.video_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # --- Controls Frame ---
        controls_frame = tk.Frame(self.root)
        controls_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        # Set the video output to the video_frame
        # This is platform-specific
        if platform.system() == "Windows":
            self.player.set_hwnd(self.video_frame.winfo_id())
        else:  # Linux, MacOS
            self.player.set_xwindow(self.video_frame.winfo_id())

        # --- Buttons and Controls ---
        # Open Video Button
        self.open_button = tk.Button(controls_frame, text="Open Video", command=self.open_video)
        self.open_button.pack(side=tk.LEFT, padx=5)

        # Play/Pause Button
        self.play_pause_button = tk.Button(controls_frame, text="▶ Play", command=self.play_pause, state=tk.DISABLED)
        self.play_pause_button.pack(side=tk.LEFT, padx=5)

        # Repeat Count Label and Entry
        tk.Label(controls_frame, text="Repeat Count:").pack(side=tk.LEFT, padx=(10, 2))
        self.repeat_var = tk.StringVar(value="1")
        self.repeat_entry = tk.Entry(controls_frame, textvariable=self.repeat_var, width=3)
        self.repeat_entry.pack(side=tk.LEFT)

        # Fullscreen and Exit buttons on the right
        self.exit_button = tk.Button(controls_frame, text="Exit", command=self.on_closing)
        self.exit_button.pack(side=tk.RIGHT, padx=5)

        self.fullscreen_button = tk.Button(controls_frame, text="Fullscreen", command=self.toggle_fullscreen)
        self.fullscreen_button.pack(side=tk.RIGHT, padx=5)

    def open_video(self):
        """Opens a file dialog to choose a video and then another for subtitles."""
        video_path = filedialog.askopenfilename(
            title="Choose a video file",
            filetypes=(("Video files", "*.mp4 *.mkv *.avi"), ("All files", "*.*"))
        )
        if not video_path:
            return

        # Load video into VLC
        media = self.vlc_instance.media_new(video_path)
        self.player.set_media(media)
        self.video_loaded = True
        self.play_pause_button.config(state=tk.NORMAL, text="▶ Play")
        self.is_paused_by_user = True  # Start in a paused state

        # Ask for subtitles
        subtitle_path = filedialog.askopenfilename(
            title="Choose a subtitle file (SRT)",
            filetypes=(("SubRip files", "*.srt"), ("All files", "*.*"))
        )
        if subtitle_path:
            self.load_subtitle(subtitle_path)

    def load_subtitle(self, path):
        """Parses the SRT file and loads it into the player."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Simple but effective SRT parser using regex
            # Format: index\nstart --> end\ntext\n\n
            subtitle_blocks = re.findall(
                r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?(?=\n\n|\Z))',
                content
            )

            self.subtitles = []
            for block in subtitle_blocks:
                start_time = self.srt_time_to_ms(block[1])
                end_time = self.srt_time_to_ms(block[2])
                text = block[3]
                self.subtitles.append({'start': start_time, 'end': end_time, 'text': text})

            self.player.video_set_subtitle_file(path)
            messagebox.showinfo("Success", f"{len(self.subtitles)} subtitles loaded successfully.")
        except Exception as e:
            messagebox.showerror("Subtitle Error", f"Failed to parse subtitle file: {e}")
            self.subtitles = []

    def srt_time_to_ms(self, time_str):
        """Converts an SRT time string (HH:MM:SS,ms) to milliseconds."""
        h, m, s_ms = time_str.split(':')
        s, ms = s_ms.split(',')
        return int(timedelta(hours=int(h), minutes=int(m), seconds=int(s), milliseconds=int(ms)).total_seconds() * 1000)

    def play_pause(self):
        """Toggles play/pause state of the video."""
        if not self.video_loaded:
            return

        if self.player.is_playing():
            self.player.pause()
            self.is_paused_by_user = True
            self.play_pause_button.config(text="▶ Play")
        else:
            self.player.play()
            self.is_paused_by_user = False
            self.play_pause_button.config(text="❚❚ Pause")

    def toggle_fullscreen(self):
        """Toggles fullscreen mode."""
        self.player.toggle_fullscreen()

    def update_player_state(self):
        """The main loop that checks time and handles subtitle repetition."""
        if not self.video_loaded or self.is_paused_by_user or not self.player.is_playing():
            # If paused by user, or no video, do nothing.
            self.root.after(200, self.update_player_state)  # Check again later
            return

        current_time = self.player.get_time()

        # Find the currently active subtitle
        active_subtitle_found = False
        for i, sub in enumerate(self.subtitles):
            if sub['start'] <= current_time < sub['end']:
                if self.current_subtitle_index != i:
                    # We have entered a new subtitle, reset repeat count
                    self.current_subtitle_index = i
                    self.current_repeat_count = 0
                active_subtitle_found = True
                break

        if not active_subtitle_found:
            self.current_subtitle_index = -1  # No active subtitle

        # Check for repetition logic if a subtitle just ended
        if self.current_subtitle_index != -1:
            current_sub = self.subtitles[self.current_subtitle_index]
            if current_time >= current_sub['end']:
                try:
                    repeat_goal = int(self.repeat_var.get())
                except ValueError:
                    repeat_goal = 1

                self.current_repeat_count += 1

                if self.current_repeat_count < repeat_goal:
                    # Repeat the subtitle
                    self.player.set_time(current_sub['start'])
                else:
                    # Move on, do nothing and let it play to the next sub
                    pass

        # Schedule the next check
        self.root.after(50, self.update_player_state)

    def on_closing(self):
        """Handles the application exit."""
        if self.player:
            self.player.stop()
        self.root.destroy()


if __name__ == "__main__":
    # Check if VLC is installed by looking for a common installation path
    # This is a basic check and might not be foolproof
    vlc_installed = False
    if platform.system() == "Windows":
        prog_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        if os.path.exists(os.path.join(prog_files, "VideoLAN", "VLC", "vlc.exe")):
            vlc_installed = True
    elif platform.system() == "Darwin":  # MacOS
        if os.path.exists("/Applications/VLC.app"):
            vlc_installed = True
    else:  # Linux
        # On Linux, it's usually in the PATH if installed via a package manager
        vlc_installed = os.system("which vlc > /dev/null 2>&1") == 0

    if not vlc_installed:
        print("WARNING: VLC Media Player application not found in a common location.")
        print("Please ensure VLC is installed and accessible.")

    root = tk.Tk()
    app = LanguageLearnerPlayer(root)
    root.mainloop()