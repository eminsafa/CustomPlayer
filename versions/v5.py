import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import vlc
import pysrt
import os
import sys
import logging
import re
from functools import partial

# --- Setup Logging ---
log_file_path = os.path.join(os.path.expanduser("~"), "subtitle_repeater.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, 'w', 'utf-8')
    ]
)

# Set VLC plugin path for Windows (if not in PATH)
if sys.platform == "win32" and not os.environ.get('VLC_PLUGIN_PATH'):
    vlc_install_path = r"C:\Program Files\VideoLAN\VLC"
    if os.path.exists(vlc_install_path):
        os.add_dll_directory(vlc_install_path)
        logging.info(f"Added VLC DLL directory: {vlc_install_path}")
    else:
        logging.warning("VLC installation path not found. Ensure VLC is installed or its path is in system PATH.")

class VLCPlayerApp:
    """
    A video player with a focus on flicker-free repeating of subtitle lines.
    Subtitles are rendered in a Tkinter widget for full control.
    Seeking is handled with a robust pause-seek-wait-play pattern.
    """

    def __init__(self, master):
        self.master = master
        master.title("Subtitle Repeater")
        master.geometry("800x600") # More minimal height
        master.configure(bg='#282828') # Darker background for a sleek look

        # --- State Variables ---
        self.video_path = None
        self.subtitle_path = None
        self.subtitles = None
        self.original_subtitles = None
        self.subtitle_index = 0
        self.repeat_counter = 0
        self.is_paused = True
        self.is_repeating_active = False
        self.is_fullscreen = False
        self.is_slider_dragging = False
        self.repeat_timer_id = None
        self.resume_timer_id = None
        self.last_current_time_str = ""
        self.last_duration_time_str = ""
        self.currently_displayed_subtitle_index = None

        # --- Spinbox Variable ---
        self.repeat_count_var = tk.StringVar(value="1") # Use StringVar for Spinbox

        # --- VLC Instance Initialization ---
        try:
            logging.info("Initializing VLC instance...")
            vlc_args = [
                '--no-video-title-show',
                '--reset-plugins-cache',
                '--avcodec-hw=any',
                '--no-skip-frames',
                '--no-loop',
                '--no-sub-autodetect-file' # Prevent VLC from auto-loading subs
            ]

            # Adjust VLC_PLUGIN_PATH for bundled apps or specific installs
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))

            plugin_path_candidates = [
                os.path.join(base_path, 'plugins'),
                os.path.join(base_path, 'vlc', 'plugins'), # Common for some pyinstaller bundles
                os.path.join(os.path.dirname(sys.executable), 'vlc', 'plugins') # Another common bundle path
            ]
            # Add system default VLC plugin paths for non-bundled environments if not found
            if sys.platform == "win32":
                plugin_path_candidates.append(r"C:\Program Files\VideoLAN\VLC\plugins")
                plugin_path_candidates.append(r"C:\Program Files (x86)\VideoLAN\VLC\plugins")
            elif sys.platform.startswith('linux'):
                vlc_args.append('--no-xlib') # For headless/server environments, often not needed for GUI
                plugin_path_candidates.append("/usr/lib/vlc/plugins")
                plugin_path_candidates.append("/usr/local/lib/vlc/plugins")


            found_plugin_path = None
            for p_path in plugin_path_candidates:
                if os.path.exists(p_path):
                    found_plugin_path = p_path
                    break

            if found_plugin_path:
                os.environ['VLC_PLUGIN_PATH'] = found_plugin_path
                logging.info(f"VLC_PLUGIN_PATH set to: {found_plugin_path}")
            else:
                logging.warning("VLC_PLUGIN_PATH not explicitly set or found. May rely on system PATH.")

            self.vlc_instance = vlc.Instance(vlc_args)
            self.player = self.vlc_instance.media_player_new()
            logging.info("VLC instance and player created successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize VLC: {e}", exc_info=True)
            messagebox.showerror("VLC Error", f"Could not initialize VLC. Is it installed and in your PATH?\nError: {e}")
            master.destroy()
            return

        self.create_widgets()
        self.setup_key_bindings()
        self.master.focus_set()
        self.master.after(100, self.update_ui)
        self.apply_theme()


    def apply_theme(self):
        """Applies a dark theme to Tkinter widgets using ttk."""
        self.master.tk_setPalette(background='#282828', foreground='white',
                                  activeBackground='#424242', activeForeground='white')

        style = ttk.Style()
        style.theme_use('clam') # 'clam' is a good base for dark themes
        style.configure('.', background='#282828', foreground='white', font=('Helvetica', 10))
        style.configure('TFrame', background='#282828')
        style.configure('TLabel', background='#282828', foreground='white')
        style.configure('TButton', background='#424242', foreground='white', font=('Helvetica', 10, 'bold'))
        style.map('TButton', background=[('active', '#5a5a5a')])
        style.configure('Horizontal.TScale', background='#282828', troughcolor='#555555',
                        foreground='white', sliderrelief='flat', sliderthickness=20)
        style.map('Horizontal.TScale', background=[('active', '#e04a00')])

        # Specific styling for elements that are not directly ttk widgets or need overrides
        self.master.option_add('*TCombobox*Listbox.background', '#424242')
        self.master.option_add('*TCombobox*Listbox.foreground', 'white')
        self.master.option_add('*TCombobox*Listbox.selectBackground', '#e04a00')
        self.master.option_add('*TCombobox*Listbox.selectForeground', 'white')

        # Override for the specific label where we want to control font directly
        self.subtitle_display_label.config(bg='#282828', fg='white', font=("Helvetica", 18))
        self.time_label.config(background='#282828', foreground='#a0a0a0')
        self.duration_label.config(background='#282828', foreground='#a0a0a0')
        self.volume_slider.config(bg='#282828', troughcolor='#555555', fg='white', activebackground='#e04a00', highlightbackground='#282828')
        self.progress_slider.config(bg='#282828', troughcolor='#555555', fg='white', activebackground='#e04a00', highlightbackground='#282828')

        # Adjust spinbox for dark theme
        self.repeat_count.config(background='#424242', foreground='white', buttonbackground='#5a5a5a', insertbackground='white')
        self.sync_delay_entry.config(bg='#424242', fg='white', insertbackground='white')

    def create_widgets(self):
        # Video Frame
        self.video_frame = tk.Frame(self.master, bg="#1a1a1a")
        self.video_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        # Subtitle Display (Text widget for rich text formatting)
        self.subtitle_display_text = tk.Text(
            self.master,
            fg="white",
            bg="#282828",
            font=("Helvetica", 18),
            wrap=tk.WORD,
            height=3, # Adjusted height for more flexibility, still fixed
            padx=10,
            pady=10,
            relief=tk.FLAT,
            state=tk.DISABLED # Start disabled to prevent user input
        )
        self.subtitle_display_text.tag_configure("italic", font=("Helvetica", 18, "italic"))
        self.subtitle_display_text.tag_configure("bold", font=("Helvetica", 18, "bold"))
        self.subtitle_display_text.tag_configure("color_red", foreground="red")
        self.subtitle_display_text.pack(pady=5, padx=10, fill=tk.X)
        self.subtitle_display_label = self.subtitle_display_text # For compatibility with existing code

        # Time and Progress Slider
        time_frame = ttk.Frame(self.master)
        time_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.time_label = ttk.Label(time_frame, text="00:00:00")
        self.time_label.pack(side=tk.LEFT, padx=10)
        self.progress_slider = tk.Scale(time_frame, from_=0, to=1000, orient=tk.HORIZONTAL, showvalue=0,
                                        command=lambda x: self.on_slider_drag(), # Bind to drag for visual update
                                        troughcolor='#555555', bg='#282828', highlightthickness=0,
                                        activebackground='#e04a00', bd=0, sliderrelief='flat')
        self.progress_slider.pack(fill=tk.X, expand=True, padx=5)
        self.duration_label = ttk.Label(time_frame, text="00:00:00")
        self.duration_label.pack(side=tk.RIGHT, padx=10)
        self.progress_slider.bind("<ButtonPress-1>", self.on_slider_press)
        self.progress_slider.bind("<ButtonRelease-1>", self.on_slider_release)

        # Controls Container
        controls_container = ttk.Frame(self.master)
        controls_container.pack(fill=tk.X, padx=10, pady=5)

        # Play/Pause
        self.play_pause_btn = ttk.Button(controls_container, text="▶", command=self.play_pause, width=4)
        self.play_pause_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # Previous Subtitle
        self.prev_subtitle_btn = ttk.Button(controls_container, text="⏪", command=self.previous_subtitle, state=tk.DISABLED)
        self.prev_subtitle_btn.pack(side=tk.LEFT, padx=(5, 0), pady=5)

        # Skip Subtitle
        self.skip_subtitle_btn = ttk.Button(controls_container, text="⏩", command=self.skip_subtitle, state=tk.DISABLED)
        self.skip_subtitle_btn.pack(side=tk.LEFT, padx=(5, 15), pady=5)

        # Load Video
        self.load_video_btn = ttk.Button(controls_container, text="🎬 Load Video", command=self.load_video)
        self.load_video_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # Load Subtitles
        self.load_subs_btn = ttk.Button(controls_container, text="📝 Load Subs", command=self.load_subtitle)
        self.load_subs_btn.pack(side=tk.LEFT, padx=(0, 15), pady=5)

        # Repeat Count
        ttk.Label(controls_container, text="Repeat:").pack(side=tk.LEFT, padx=(5, 0), pady=5)
        self.repeat_count = tk.Spinbox(controls_container, from_=1, to=10, width=3, justify=tk.CENTER,
                                       font=("Helvetica", 10), bd=0, relief=tk.FLAT,
                                       textvariable=self.repeat_count_var) # Use textvariable
        # self.repeat_count.set(1) # This line was the error, removed
        self.repeat_count.pack(side=tk.LEFT, padx=(0, 15), pady=5)

        # Volume Slider
        ttk.Label(controls_container, text="Volume:").pack(side=tk.LEFT, padx=(5, 0), pady=5)
        self.volume_slider = tk.Scale(controls_container, from_=0, to=100, orient=tk.HORIZONTAL,
                                      command=self.set_volume, showvalue=0, length=100,
                                      troughcolor='#555555', bg='#282828', highlightthickness=0,
                                      activebackground='#e04a00', bd=0, sliderrelief='flat')
        self.volume_slider.set(100)
        self.volume_slider.pack(side=tk.LEFT, padx=5, pady=5)

        # Fullscreen Button
        self.fullscreen_btn = ttk.Button(controls_container, text="⛶ Fullscreen", command=self.toggle_fullscreen)
        self.fullscreen_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        # Advanced Settings Frame
        advanced_frame = ttk.LabelFrame(self.master, text="Subtitle Settings", padding=(10, 5))
        advanced_frame.pack(fill=tk.X, padx=10, pady=10)
        advanced_frame.columnconfigure(2, weight=1)

        ttk.Label(advanced_frame, text="Delay (sec):").grid(row=0, column=0, sticky="w", pady=2, padx=(0, 5))
        self.sync_delay_entry = tk.Entry(advanced_frame, width=5, font=("Helvetica", 10), bd=0, relief=tk.FLAT)
        self.sync_delay_entry.insert(0, "0.0")
        self.sync_delay_entry.grid(row=0, column=1, sticky="w")

        self.apply_settings_btn = ttk.Button(advanced_frame, text="⚙️ Apply Settings", command=self.process_subtitles, state=tk.DISABLED)
        self.apply_settings_btn.grid(row=0, column=2, sticky="e", padx=(20, 0))

    def setup_key_bindings(self):
        """Sets up global keyboard shortcuts."""
        self.master.bind('<Key>', self.handle_keypress)
        self.master.bind('<space>', self.play_pause)
        self.master.bind('<Right>', self.skip_subtitle)
        self.master.bind('<Left>', self.previous_subtitle)
        self.master.bind('<f>', self.toggle_fullscreen)
        self.master.bind('<Escape>', partial(self.toggle_fullscreen, force_off=True)) # Exit fullscreen on Esc
        self.master.bind('<Control-o>', self.load_video) # Ctrl+O for Open Video
        self.master.bind('<Control-s>', self.load_subtitle) # Ctrl+S for Load Subtitle
        self.master.bind('<Up>', lambda e: self.adjust_volume(5)) # Volume Up
        self.master.bind('<Down>', lambda e: self.adjust_volume(-5)) # Volume Down
        self.master.bind('<comma>', lambda e: self.seek_relative(-5000)) # Back 5 seconds
        self.master.bind('<period>', lambda e: self.seek_relative(5000)) # Forward 5 seconds

    def adjust_volume(self, delta):
        current_volume = self.volume_slider.get()
        new_volume = max(0, min(100, current_volume + delta))
        self.volume_slider.set(new_volume)
        self.set_volume(new_volume) # Ensure command is called

    def seek_relative(self, delta_ms):
        if not self.player.get_media(): return
        current_time_ms = self.player.get_time()
        new_time_ms = current_time_ms + delta_ms
        total_length_ms = self.player.get_length()
        new_time_ms = max(0, min(new_time_ms, total_length_ms - 100)) # Prevent seeking past end
        self._perform_seek_with_pause(new_time_ms)

    def on_slider_press(self, event):
        self.cancel_all_scheduled_actions()
        self.is_slider_dragging = True
        # Pause playback immediately when slider is grabbed
        if self.player.is_playing():
            self.player.pause()
            self.is_paused_before_drag = False # Remember if it was playing
        else:
            self.is_paused_before_drag = True

    def on_slider_drag(self):
        """Called repeatedly as the slider is dragged, for visual update."""
        if self.is_slider_dragging:
            pos = self.progress_slider.get()
            total_length = self.player.get_length()
            if total_length > 0:
                time_ms = int(total_length * (pos / 1000.0))
                self.time_label.config(text=self.ms_to_time_str(time_ms))

    def on_slider_release(self, event):
        self.is_slider_dragging = False
        self.seek()
        self.master.focus_set()
        # Resume playback if it was playing before drag
        if not self.is_paused_before_drag:
            self.player.play()
            self.play_pause_btn.config(text="❚❚") # Update button icon
            self.is_paused = False


    def seek(self):
        if not self.player.get_media() or self.player.get_length() <= 0: return
        pos = self.progress_slider.get()
        time_ms = int(self.player.get_length() * (pos / 1000.0))
        self._perform_seek_with_pause(time_ms)

    def _perform_seek_with_pause(self, target_time_ms, resume_delay_ms=250, update_repeat_counter=True):
        """
        Pauses, seeks, waits, then resumes. Can selectively reset the repeat counter.
        Increased efficiency: Uses is_playing() and only pauses if actually playing.
        Reduced resume_delay_ms for snappier response.
        """
        if not self.player.get_media(): return
        was_playing = self.player.is_playing()
        logging.info(f"Seeking to {self.ms_to_time_str(target_time_ms)}. Was playing: {was_playing}. Reset counter: {update_repeat_counter}.")

        # Stop scheduled repeats and resumes immediately
        self.cancel_all_scheduled_actions()

        if was_playing:
            self.player.pause() # Pause instantly
            self.play_pause_btn.config(text="▶") # Update button icon
            self.is_paused = True # Update internal state

        # Perform the seek
        self.player.set_time(max(0, target_time_ms))

        # Update subtitle index (this is crucial for accurate display after seek)
        self.update_subtitle_index_on_seek(target_time_ms, reset_counter=update_repeat_counter)

        def delayed_resume():
            self.resume_timer_id = None
            # Only resume if it was playing and no new pause/seek occurred
            if was_playing and self.player.get_state() == vlc.State.Paused and not self.is_paused:
                self.player.play()
                self.play_pause_btn.config(text="❚❚") # Update button icon
                self.is_paused = False # Update internal state
            elif was_playing and self.player.get_state() == vlc.State.Playing:
                # If player already playing due to other events, just ensure button is correct
                self.play_pause_btn.config(text="❚❚")

        # Schedule the resume after a short delay to allow VLC to stabilize
        self.resume_timer_id = self.master.after(resume_delay_ms, delayed_resume)
        logging.info(f"Seek initiated, resume scheduled for {resume_delay_ms}ms.")


    def update_ui(self):
        """
        Periodically updates the UI elements.
        Optimized to reduce redundant updates and improve responsiveness.
        """
        try:
            if self.player.get_media() and self.player.get_length() > 0:
                current_time = self.player.get_time()
                total_length = self.player.get_length()

                # Update progress slider if not being dragged
                if not self.is_slider_dragging and total_length > 0:
                    new_slider_value = int(self.player.get_position() * 1000)
                    if new_slider_value != self.progress_slider.get():
                        self.progress_slider.set(new_slider_value)

                # Update current time label only if it changes
                current_time_str = self.ms_to_time_str(current_time)
                if current_time_str != self.last_current_time_str:
                    self.time_label.config(text=current_time_str)
                    self.last_current_time_str = current_time_str

                # Update duration label only once or if duration changes
                duration_str = self.ms_to_time_str(total_length)
                if duration_str != self.last_duration_time_str:
                    self.duration_label.config(text=duration_str)
                    self.last_duration_time_str = duration_str

                # Update fullscreen state (if changed externally)
                if self.is_fullscreen != self.master.attributes('-fullscreen'):
                    self.is_fullscreen = self.master.attributes('-fullscreen')
                    self.update_fullscreen_button()

                # Update subtitle display
                self.update_tkinter_subtitle(current_time)

                # Handle repeat logic
                if self.is_repeating_active and not self.is_paused and self.repeat_timer_id is None:
                    if self.subtitles and 0 <= self.subtitle_index < len(self.subtitles):
                        current_cue = self.subtitles[self.subtitle_index]
                        # Ensure we are within the current subtitle's time range to schedule repeat
                        if current_cue.start.ordinal <= current_time < current_cue.end.ordinal:
                            time_until_end = int(current_cue.end.ordinal) - current_time
                            # Schedule repeat slightly before end to avoid flicker/gap
                            delay_before_end = min(200, time_until_end - 50) # Repeat 50ms before end, or earlier
                            if delay_before_end > 0:
                                self.repeat_timer_id = self.master.after(delay_before_end, self.handle_repeat)
                            else:
                                # If too close to end, trigger repeat almost immediately
                                self.master.after(1, self.handle_repeat)
                        elif current_time >= current_cue.end.ordinal and self.repeat_counter == 0:
                            # If we've passed the current subtitle and haven't repeated yet,
                            # it might be a case where repeat was activated mid-subtitle.
                            # Force a handle_repeat to advance if not repeating.
                            self.master.after(1, self.handle_repeat)
            else:
                # If no media, ensure UI reflects stopped state
                if not self.is_slider_dragging:
                    self.progress_slider.set(0)
                if self.player.get_state() == vlc.State.Ended:
                    self.stop() # Automatically stop when video ends

            self.master.after(50, self.update_ui) # Increased interval for performance
        except tk.TclError:
            logging.info("TclError caught, likely window closed.")
        except Exception as e:
            logging.error(f"Unexpected error in UI loop: {e}", exc_info=True)

    def update_tkinter_subtitle(self, current_time_ms):
        """
        Updates the Tkinter Text widget with the current subtitle, applying basic HTML-like styles.
        Only updates if the active subtitle index has changed or if the text itself needs refresh.
        """
        if not self.subtitles:
            if self.subtitle_display_text.get("1.0", tk.END).strip():
                self.subtitle_display_text.config(state=tk.NORMAL)
                self.subtitle_display_text.delete("1.0", tk.END)
                self.subtitle_display_text.config(state=tk.DISABLED)
                self.currently_displayed_subtitle_index = None
            return

        active_index = None
        for i, cue in enumerate(self.subtitles):
            # Give a small buffer (e.g., 50ms) to ensure subtitle is displayed even if timing is slightly off
            if cue.start.ordinal <= current_time_ms + 50 and current_time_ms < cue.end.ordinal:
                active_index = i
                break

        if active_index != self.currently_displayed_subtitle_index:
            self.subtitle_display_text.config(state=tk.NORMAL)
            self.subtitle_display_text.delete("1.0", tk.END)
            self.currently_displayed_subtitle_index = active_index

            if active_index is not None:
                new_text = self.subtitles[active_index].text
                # Process for basic HTML-like tags (<i>, <b>, <font color="...>)
                processed_text_parts = []
                current_tags = []

                # Regex to find tags and their content
                # Groups: 1=opening tag, 2=closing tag, 3=content between tags
                # This is a simplified regex, more robust parsing might be needed for complex cases
                parts = re.split(r'(<[^>]+>)(.*?)(</[^>]+>)', new_text, flags=re.IGNORECASE)

                for part in parts:
                    if not part:
                        continue

                    lower_part = part.lower()
                    if lower_part.startswith('<i'):
                        current_tags.append("italic")
                    elif lower_part.startswith('</i'):
                        if "italic" in current_tags: current_tags.remove("italic")
                    elif lower_part.startswith('<b'):
                        current_tags.append("bold")
                    elif lower_part.startswith('</b'):
                        if "bold" in current_tags: current_tags.remove("bold")
                    elif lower_part.startswith('<font color='):
                        match = re.search(r'color=["\']?([^"\'>]+)', lower_part)
                        if match:
                            color = match.group(1)
                            tag_name = f"color_{color}"
                            self.subtitle_display_text.tag_configure(tag_name, foreground=color)
                            current_tags.append(tag_name)
                    elif lower_part.startswith('</font'):
                        # Remove the last added color tag
                        for tag in reversed(current_tags):
                            if tag.startswith("color_"):
                                current_tags.remove(tag)
                                break
                    else:
                        # This is the actual text content
                        clean_text = re.sub(r'<[^>]+>', '', part) # Remove any unhandled tags
                        self.subtitle_display_text.insert(tk.END, clean_text, current_tags)
            self.subtitle_display_text.config(state=tk.DISABLED)


    def handle_repeat(self):
        """
        Manages the repetition of a subtitle line.
        More robust handling of edge cases and ensures flicker-free repeats.
        """
        self.repeat_timer_id = None # Clear timer immediately to prevent multiple triggers

        if self.is_paused or not self.is_repeating_active:
            logging.info("Repeat skipped: Player paused or repeating not active.")
            return

        try:
            # Use self.repeat_count_var.get() to retrieve the value
            max_repeats = int(self.repeat_count_var.get())
            if max_repeats < 1: max_repeats = 1 # Ensure at least 1 repeat (initial display)
        except (ValueError, tk.TclError):
            max_repeats = 1
            logging.warning("Invalid repeat count, defaulting to 1.")

        if not self.subtitles or not (0 <= self.subtitle_index < len(self.subtitles)):
            logging.info("No subtitles or current subtitle index out of bounds, cannot repeat.")
            return

        current_cue = self.subtitles[self.subtitle_index]

        if self.repeat_counter < max_repeats - 1:
            self.repeat_counter += 1
            logging.info(f"Repeating subtitle #{self.subtitle_index + 1} (Repeat {self.repeat_counter}/{max_repeats})")
            # Seek to start of current cue without resetting the repeat counter
            # Use a slightly longer delay for seek to ensure VLC has time to process
            self._perform_seek_with_pause(int(current_cue.start.ordinal), resume_delay_ms=250,
                                          update_repeat_counter=False)
        else:
            # All repeats done, advance to next subtitle
            if self.subtitle_index < len(self.subtitles) - 1:
                self.subtitle_index += 1
                self.repeat_counter = 0 # Reset for the new subtitle
                logging.info(f"Advancing to subtitle #{self.subtitle_index + 1}")
                next_cue = self.subtitles[self.subtitle_index]
                # Seek to start of next cue, resetting repeat counter
                self._perform_seek_with_pause(int(next_cue.start.ordinal), resume_delay_ms=250,
                                              update_repeat_counter=True)
            else:
                # End of subtitles, stop repeating
                logging.info("End of subtitles reached. Stopping repeat.")
                self.is_repeating_active = False
                self.play_pause() # Pause playback at the end of subtitles


    def cancel_all_scheduled_actions(self):
        """Cancels any pending after() calls for repeats or resumes."""
        if self.repeat_timer_id:
            self.master.after_cancel(self.repeat_timer_id)
            self.repeat_timer_id = None
            logging.debug("Cancelled repeat timer.")
        if self.resume_timer_id:
            self.master.after_cancel(self.resume_timer_id)
            self.resume_timer_id = None
            logging.debug("Cancelled resume timer.")

    def load_video(self, *args):
        self.cancel_all_scheduled_actions()
        path = filedialog.askopenfilename(title="Select Video File",
                                          filetypes=(("Video files", "*.mp4 *.mkv *.avi *.mov *.webm"), ("All files", "*.*")))
        if not path: return
        self.video_path = path
        logging.info(f"Loading video: {self.video_path}")
        try:
            media = self.vlc_instance.media_new(self.video_path)
            self.player.set_media(media)
            self.player.video_set_spu(0) # Disable VLC's internal subtitle renderer

            # Embed video into the Tkinter frame
            if sys.platform == "win32":
                self.player.set_hwnd(self.video_frame.winfo_id())
            elif sys.platform == "darwin":
                self.player.set_nsobject(self.video_frame.winfo_id())
            else: # Linux
                self.player.set_xwindow(self.video_frame.winfo_id())

            self.play_pause() # Automatically play after loading
            self.master.title(f"Subtitle Repeater - {os.path.basename(self.video_path)}")
            # Attempt to auto-load subtitle if it exists with same name
            self.auto_load_subtitle_for_video(path)

        except Exception as e:
            logging.error(f"Error loading video '{self.video_path}': {e}", exc_info=True)
            messagebox.showerror("Video Error", f"Could not load the video file.\nError: {e}")
        finally:
            self.master.focus_set()

    def auto_load_subtitle_for_video(self, video_path):
        """Attempts to find and load a .srt subtitle file with the same base name."""
        base_name, _ = os.path.splitext(video_path)
        potential_sub_path = base_name + ".srt"
        if os.path.exists(potential_sub_path):
            logging.info(f"Attempting to auto-load subtitle: {potential_sub_path}")
            self.load_subtitle(potential_sub_path)
        else:
            logging.info("No matching subtitle file found for auto-load.")


    def load_subtitle(self, path=None, *args):
        if not path:
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
                logging.info(f"Subtitle loaded successfully with encoding: {encoding}")
                break
            except UnicodeDecodeError:
                logging.debug(f"Failed to load subtitle with encoding: {encoding}")
                continue
            except Exception as e:
                logging.error(f"Error parsing subtitle file with encoding {encoding}: {e}", exc_info=True)
                messagebox.showerror("Subtitle Error", f"Could not parse subtitle file.\nError: {e}")
                return

        if loaded_subs:
            self.original_subtitles = loaded_subs
            self.apply_settings_btn.config(state=tk.NORMAL)
            self.process_subtitles() # Process immediately after loading
            self.skip_subtitle_btn.config(state=tk.NORMAL)
            self.prev_subtitle_btn.config(state=tk.NORMAL)
        else:
            logging.error("Could not decode subtitle file with any common encodings.")
            messagebox.showerror("Subtitle Error", "Could not decode subtitle file. Try converting to UTF-8.")
        self.master.focus_set()

    def process_subtitles(self):
        """Applies delay and activates repeating."""
        if not self.original_subtitles:
            messagebox.showwarning("Warning", "No subtitles loaded.")
            return

        self.cancel_all_scheduled_actions()
        logging.info("Processing subtitles with new settings...")
        processed_subs = self.original_subtitles.copy()
        info_message = "Settings applied."

        try:
            delay_sec = float(self.sync_delay_entry.get())
            if delay_sec != 0.0:
                processed_subs.shift(seconds=delay_sec)
                info_message = f"Subtitles shifted by {delay_sec} seconds."
        except ValueError:
            logging.error(f"Invalid delay value: '{self.sync_delay_entry.get()}'")
            messagebox.showerror("Error", "Invalid delay value. Please enter a number.")
            return

        self.subtitles = processed_subs
        messagebox.showinfo("Settings Applied", info_message)
        self.is_repeating_active = True
        self.update_subtitle_index_on_seek(self.player.get_time(), reset_counter=True)
        self.master.focus_set()

    def play_pause(self, *args):
        if not self.player.get_media():
            self.load_video() # Prompt to load video if none is loaded
            return

        self.cancel_all_scheduled_actions()

        if self.player.is_playing():
            self.player.pause()
            self.play_pause_btn.config(text="▶")
            self.is_paused = True
            logging.info("Video paused.")
        else:
            if self.is_paused: # Only update index if we were truly paused and about to play
                self.update_subtitle_index_on_seek(self.player.get_time(), reset_counter=True)
            self.player.play()
            self.play_pause_btn.config(text="❚❚")
            self.is_paused = False
            logging.info("Video playing.")

        self.master.focus_set()

    def stop(self, *args):
        """Stops playback and resets UI to initial state."""
        self.cancel_all_scheduled_actions()
        self.player.stop()
        self.play_pause_btn.config(text="▶")
        self.is_paused = True
        self.progress_slider.set(0)
        self.time_label.config(text="00:00:00")
        self.last_current_time_str = "00:00:00"
        self.duration_label.config(text="00:00:00")
        self.last_duration_time_str = "00:00:00"
        self.subtitle_index = 0
        self.repeat_counter = 0
        self.subtitle_display_text.config(state=tk.NORMAL)
        self.subtitle_display_text.delete("1.0", tk.END)
        self.subtitle_display_text.config(state=tk.DISABLED)
        self.currently_displayed_subtitle_index = None
        self.master.title("Subtitle Repeater")
        logging.info("Video stopped.")
        self.master.focus_set()

    def skip_subtitle(self, *args):
        if not self.subtitles: return
        self.cancel_all_scheduled_actions() # Stop any active repeats/resumes

        if self.subtitle_index < len(self.subtitles) - 1:
            self.subtitle_index += 1
            logging.info(f"Skipping to subtitle #{self.subtitle_index + 1}")
        else:
            logging.info("Already at the last subtitle.")
            return # Already at the last subtitle, do nothing

        next_cue = self.subtitles[self.subtitle_index]
        self._perform_seek_with_pause(int(next_cue.start.ordinal))
        self.master.focus_set()

    def previous_subtitle(self, *args):
        if not self.subtitles: return
        self.cancel_all_scheduled_actions() # Stop any active repeats/resumes

        if self.subtitle_index > 0:
            self.subtitle_index -= 1
            logging.info(f"Moving to previous subtitle #{self.subtitle_index + 1}")
        else:
            logging.info("Already at the first subtitle.")
            return # Already at the first subtitle, do nothing

        prev_cue = self.subtitles[self.subtitle_index]
        self._perform_seek_with_pause(int(prev_cue.start.ordinal))
        self.master.focus_set()

    def toggle_fullscreen(self, *args, force_off=False):
        if force_off and not self.is_fullscreen:
            return # Only force off if currently in fullscreen

        self.is_fullscreen = not self.is_fullscreen if not force_off else False
        self.master.attributes("-fullscreen", self.is_fullscreen)
        self.update_fullscreen_button()
        self.master.focus_set()
        logging.info(f"Fullscreen toggled to: {self.is_fullscreen}")

    def update_fullscreen_button(self):
        self.fullscreen_btn.config(text="Exit ⛶" if self.is_fullscreen else "⛶ Fullscreen")

    def set_volume(self, value):
        self.player.audio_set_volume(int(value))
        # No need to focus_set here, as it can interfere with other interactions

    def update_subtitle_index_on_seek(self, time_ms, reset_counter=True):
        """
        Updates the internal subtitle_index based on the current video time.
        This is crucial for ensuring the correct subtitle is processed and displayed
        after any seek operation (user seek, previous/next subtitle, or repeat).
        """
        if not self.subtitles:
            self.subtitle_index = 0
            if reset_counter: self.repeat_counter = 0
            self.currently_displayed_subtitle_index = None # Reset displayed subtitle state
            return

        new_index = 0
        found_cue = False
        for i, cue in enumerate(self.subtitles):
            # Check if current time falls within or immediately after a subtitle
            if cue.start.ordinal <= time_ms + 50 and current_time_ms < cue.end.ordinal:
                new_index = i
                found_cue = True
                break
            elif time_ms < cue.start.ordinal:
                # If we've passed the current time, this is the next logical subtitle
                new_index = i
                found_cue = True
                break

        if not found_cue:
            # If no subtitle found before or at current time, assume it's past all subtitles
            new_index = len(self.subtitles) - 1 if self.subtitles else 0


        if new_index != self.subtitle_index:
            self.subtitle_index = new_index
            logging.info(f"Subtitle index updated to {self.subtitle_index + 1} based on seek to {self.ms_to_time_str(time_ms)}.")
            # Force subtitle display update if index changes, even if time is still in it.
            self.currently_displayed_subtitle_index = None # Invalidate cache to force update

        if reset_counter:
            self.repeat_counter = 0
            logging.debug("Repeat counter reset.")

    def ms_to_time_str(self, ms):
        if ms < 0: ms = 0
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02}:{m:02}:{s:02}"

    def handle_keypress(self, event):
        """Handles keypress events for shortcuts."""
        # Ignore keypresses if an Entry or Spinbox widget has focus
        if isinstance(event.widget, (tk.Entry, tk.Spinbox)):
            return

        # Basic keysyms are handled by specific binds (e.g., <space>, <Right>),
        # but this catch-all can handle other non-bound keys if needed.
        # It's generally better to use specific binds like setup_key_bindings.
        pass


if __name__ == "__main__":
    logging.info("================== Application Starting ==================")
    root = tk.Tk()
    app = VLCPlayerApp(root)
    root.mainloop()
    logging.info("================== Application Closed ==================")