import tkinter as tk
from tkinter import filedialog, messagebox
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
        self.video_duration_ms = 0
        self.is_user_seeking = False
        ### FIX 1 ### - Flag to prevent rapid-fire repeat triggers while waiting for a seek to complete.
        self.is_awaiting_seek = False

        self.create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.update_player_state()

    def create_widgets(self):
        # --- Video Frame ---
        self.video_frame = tk.Frame(self.root, bg="black")
        self.video_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.subtitle_label = tk.Label(
            self.video_frame, text="", bg="black", fg="white",
            font=("Arial", 18, "bold"), wraplength=780
        )
        self.subtitle_label.pack(side=tk.BOTTOM, fill=tk.X, pady=20)

        # --- Progress Bar / Seeking Bar ---
        progress_frame = tk.Frame(self.root)
        progress_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        self.time_label = tk.Label(progress_frame, text="00:00")
        self.time_label.pack(side=tk.LEFT)

        self.progress_slider = tk.Scale(
            progress_frame, from_=0, to=1000, orient=tk.HORIZONTAL,
            showvalue=0, command=self.on_slider_seek, state=tk.DISABLED
        )
        self.progress_slider.bind("<ButtonPress-1>", self.on_slider_press)
        self.progress_slider.bind("<ButtonRelease-1>", self.on_slider_release)
        self.progress_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.duration_label = tk.Label(progress_frame, text="00:00")
        self.duration_label.pack(side=tk.RIGHT)

        # --- Controls Frame ---
        controls_frame = tk.Frame(self.root)
        controls_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        if platform.system() == "Windows":
            self.player.set_hwnd(self.video_frame.winfo_id())
        else:
            self.player.set_xwindow(self.video_frame.winfo_id())

        # --- Buttons and Controls ---
        self.open_button = tk.Button(controls_frame, text="Open Video", command=self.open_video)
        self.open_button.pack(side=tk.LEFT, padx=5)

        self.prev_sub_button = tk.Button(controls_frame, text="<< Prev Sub", command=self.prev_subtitle,
                                         state=tk.DISABLED)
        self.prev_sub_button.pack(side=tk.LEFT, padx=5)

        self.play_pause_button = tk.Button(controls_frame, text="▶ Play", command=self.play_pause, state=tk.DISABLED)
        self.play_pause_button.pack(side=tk.LEFT, padx=5)

        self.next_sub_button = tk.Button(controls_frame, text="Next Sub >>", command=self.next_subtitle,
                                         state=tk.DISABLED)
        self.next_sub_button.pack(side=tk.LEFT, padx=5)

        tk.Frame(controls_frame).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(controls_frame, text="Repeat Count:").pack(side=tk.LEFT, padx=(10, 2))
        self.repeat_var = tk.StringVar(value="1")
        self.repeat_entry = tk.Entry(controls_frame, textvariable=self.repeat_var, width=3)
        self.repeat_entry.pack(side=tk.LEFT)

        self.exit_button = tk.Button(controls_frame, text="Exit", command=self.on_closing)
        self.exit_button.pack(side=tk.RIGHT, padx=5)

        self.fullscreen_button = tk.Button(controls_frame, text="Fullscreen", command=self.toggle_fullscreen)
        self.fullscreen_button.pack(side=tk.RIGHT, padx=5)

    def open_video(self):
        video_path = filedialog.askopenfilename()
        if not video_path: return

        self.player.stop()
        self.subtitles = []
        self.subtitle_label.config(text="")
        self.time_label.config(text="00:00")
        self.duration_label.config(text="00:00")
        self.progress_slider.set(0)

        media = self.vlc_instance.media_new(video_path)
        self.player.set_media(media)
        self.video_loaded = True
        self.play_pause_button.config(state=tk.NORMAL, text="▶ Play")
        self.progress_slider.config(state=tk.NORMAL)
        self.is_paused_by_user = True

        self.player.play()
        self.player.pause()
        self.root.after(200, self.fetch_duration)

        subtitle_path = filedialog.askopenfilename(
            title="Choose a subtitle file (SRT)",
            filetypes=(("SubRip files", "*.srt"), ("All files", "*.*"))
        )
        if subtitle_path:
            self.load_subtitle(subtitle_path)

    def fetch_duration(self):
        duration = self.player.get_length()
        if duration == -1:
            self.root.after(200, self.fetch_duration)
            return
        self.video_duration_ms = duration
        self.duration_label.config(text=self.format_time(self.video_duration_ms))

    def load_subtitle(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            subtitle_blocks = re.findall(
                r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?(?=\n\n|\Z))',
                content
            )

            self.subtitles = []
            for block in subtitle_blocks:
                start_time = self.srt_time_to_ms(block[1])
                end_time = self.srt_time_to_ms(block[2])
                text = block[3].strip()
                self.subtitles.append({'start': start_time, 'end': end_time, 'text': text})

            ### FIX 2 ### - We remove this line to prevent VLC from drawing its own subtitles.
            ### Our custom label `self.subtitle_label` is now the only source of subtitles.
            # self.player.video_set_subtitle_file(path)

            messagebox.showinfo("Success", f"{len(self.subtitles)} subtitles loaded successfully.")
            self.prev_sub_button.config(state=tk.NORMAL)
            self.next_sub_button.config(state=tk.NORMAL)
        except Exception as e:
            messagebox.showerror("Subtitle Error", f"Failed to parse subtitle file: {e}")
            self.subtitles = []

    def srt_time_to_ms(self, time_str):
        h, m, s_ms = time_str.split(':')
        s, ms = s_ms.split(',')
        return int(timedelta(hours=int(h), minutes=int(m), seconds=int(s), milliseconds=int(ms)).total_seconds() * 1000)

    def format_time(self, ms):
        seconds = ms // 1000
        minutes = seconds // 60
        seconds %= 60
        return f"{minutes:02d}:{seconds:02d}"

    def play_pause(self):
        if not self.video_loaded: return
        if self.player.is_playing():
            self.player.pause()
            self.is_paused_by_user = True
            self.play_pause_button.config(text="▶ Play")
        else:
            self.player.play()
            self.is_paused_by_user = False
            self.play_pause_button.config(text="❚❚ Pause")

    def jump_to_subtitle(self, sub_index):
        if not (0 <= sub_index < len(self.subtitles)):
            return
        target_time = self.subtitles[sub_index]['start']
        self.player.set_time(target_time)
        self.current_subtitle_index = sub_index
        self.current_repeat_count = 0
        self.is_awaiting_seek = False  # Reset seek lock on manual jump

    def prev_subtitle(self):
        if self.current_subtitle_index > 0:
            self.jump_to_subtitle(self.current_subtitle_index - 1)

    def next_subtitle(self):
        if self.current_subtitle_index < len(self.subtitles) - 1:
            self.jump_to_subtitle(self.current_subtitle_index + 1)

    def toggle_fullscreen(self):
        self.player.toggle_fullscreen()

    def on_slider_press(self, event):
        self.is_user_seeking = True

    def on_slider_release(self, event):
        self.is_user_seeking = False
        self.on_slider_seek(self.progress_slider.get())

    def on_slider_seek(self, value):
        if self.player and self.is_user_seeking and self.video_duration_ms > 0:
            position = float(value) / 1000.0
            target_time = int(self.video_duration_ms * position)
            self.player.set_time(target_time)

    def update_player_state(self):
        if not self.video_loaded:
            self.root.after(200, self.update_player_state)
            return

        current_time = self.player.get_time()

        if self.video_duration_ms > 0 and not self.is_user_seeking:
            position = (current_time / self.video_duration_ms) * 1000
            self.progress_slider.set(position)
        self.time_label.config(text=self.format_time(current_time))

        if self.is_paused_by_user:
            self.root.after(200, self.update_player_state)
            return

        active_subtitle_found = False
        current_sub_text = ""
        for i, sub in enumerate(self.subtitles):
            if sub['start'] <= current_time < sub['end']:
                if self.current_subtitle_index != i:
                    self.current_subtitle_index = i
                    self.current_repeat_count = 0

                ### FIX 1 ### - We are now inside a subtitle's time range, so we know any
                ### previous seek has completed. We can unlock the repeat mechanism.
                self.is_awaiting_seek = False

                active_subtitle_found = True
                current_sub_text = sub['text']
                break

        if self.subtitle_label.cget("text") != current_sub_text:
            self.subtitle_label.config(text=current_sub_text)

        if not active_subtitle_found:
            self.current_subtitle_index = -1

        # Repetition logic
        if self.current_subtitle_index != -1 and not self.is_awaiting_seek:
            current_sub = self.subtitles[self.current_subtitle_index]
            if current_time >= current_sub['end']:
                try:
                    repeat_goal = int(self.repeat_var.get())
                except ValueError:
                    repeat_goal = 1

                self.current_repeat_count += 1

                if self.current_repeat_count < repeat_goal:
                    ### FIX 1 ### - Trigger the seek and immediately lock the mechanism
                    ### to prevent re-triggering on the next loop cycle.
                    self.player.set_time(current_sub['start'])
                    self.is_awaiting_seek = True

        self.root.after(50, self.update_player_state)

    def on_closing(self):
        if self.player:
            self.player.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = LanguageLearnerPlayer(root)
    root.mainloop()