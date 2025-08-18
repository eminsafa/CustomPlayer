import os
import sys
import time
import json
import argparse
from collections import deque
from dataclasses import dataclass
from typing import Optional, List, Tuple, Deque

import pygame
from pygame.locals import *
import pysubs2

# Configuration
DEFAULT_REPEAT_COUNT = 3
FONT_SIZE = 24
TEXT_COLOR = (255, 255, 255)  # White
BACKGROUND_COLOR = (0, 0, 0, 180)  # Semi-transparent black
MARGIN = 20
MAX_SUBTITLE_LINES = 2


@dataclass
class SubtitleEvent:
    start: float
    end: float
    text: str
    repeat_count: int = 0
    times_shown: int = 0


class SubtitleRepeater:
    def __init__(self, video_path: str, subtitle_path: str, repeat_count: int = DEFAULT_REPEAT_COUNT):
        pygame.init()
        pygame.display.set_caption("Subtitle Repeater")

        self.video_path = video_path
        self.subtitle_path = subtitle_path
        self.repeat_count = repeat_count
        self.clock = pygame.time.Clock()

        # Initialize video player
        self.video_size = (1280, 720)  # Default size, will be updated
        self.screen = pygame.display.set_mode(self.video_size, pygame.RESIZABLE)
        self.video_surface = pygame.Surface(self.video_size).convert()

        # Initialize font
        self.font = pygame.font.SysFont("Arial", FONT_SIZE)

        # Load subtitles
        self.subtitle_events = self._load_subtitles()
        self.current_subtitle: Optional[SubtitleEvent] = None
        self.subtitle_queue: Deque[SubtitleEvent] = deque()

        # Video playback variables
        self.playing = False
        self.video_position = 0.0
        self.last_frame_time = 0.0
        self.playback_speed = 1.0

        # Initialize video (placeholder - would use proper video backend in real implementation)
        self.video_duration = 120 * 60  # Placeholder for 2 hours

    def _load_subtitles(self) -> List[SubtitleEvent]:
        """Load subtitles from file and convert to our format"""
        subs = pysubs2.load(self.subtitle_path)
        events = []

        for line in subs:
            if line.text.strip():
                events.append(SubtitleEvent(
                    start=line.start / 1000.0,  # Convert to seconds
                    end=line.end / 1000.0,
                    text=line.text.replace("\\N", "\n")  # Convert newlines
                ))

        return events

    def _get_current_subtitle(self, current_time: float) -> Optional[SubtitleEvent]:
        """Find the subtitle that should be displayed at the current time"""
        # First check if we're in the middle of a repeat
        if self.current_subtitle and self.current_subtitle.times_shown < self.current_subtitle.repeat_count:
            if current_time < self.current_subtitle.end:
                return self.current_subtitle

        # Check the queue first
        if self.subtitle_queue and self.subtitle_queue[0].start <= current_time:
            return self.subtitle_queue.popleft()

        # Find the next subtitle in the main list
        for event in self.subtitle_events:
            if event.start <= current_time < event.end:
                return event
            elif current_time < event.start:
                break  # No need to check further

        return None

    def _handle_subtitle_repeat(self):
        """Handle repeating the current subtitle if requested"""
        if self.current_subtitle and pygame.key.get_pressed()[K_r]:
            if self.current_subtitle.times_shown == 0:  # Only increment if not already repeating
                self.current_subtitle.repeat_count = min(self.current_subtitle.repeat_count + 1, 10)

    def _draw_subtitles(self):
        """Render subtitles on the screen"""
        if not self.current_subtitle:
            return

        # Split text into lines
        lines = self.current_subtitle.text.split('\n')[:MAX_SUBTITLE_LINES]

        # Calculate text dimensions
        line_heights = []
        max_width = 0
        for line in lines:
            text_surface = self.font.render(line, True, TEXT_COLOR)
            line_heights.append(text_surface.get_height())
            max_width = max(max_width, text_surface.get_width())

        total_height = sum((line_heights) + (len(lines) - 1) * 5)  # 5px padding between lines

        # Calculate background position
        bg_width = max_width + 2 * MARGIN
        bg_height = total_height + 2 * MARGIN
        bg_x = (self.video_size[0] - bg_width) // 2
        bg_y = self.video_size[1] - bg_height - MARGIN

        # Draw background
        bg_surface = pygame.Surface((bg_width, bg_height), pygame.SRCALPHA)
        bg_surface.fill(BACKGROUND_COLOR)
        self.screen.blit(bg_surface, (bg_x, bg_y))

        # Draw text lines
        y_offset = bg_y + MARGIN
        for i, line in enumerate(lines):
            text_surface = self.font.render(line, True, TEXT_COLOR)
        text_x = (self.video_size[0] - text_surface.get_width()) // 2
        self.screen.blit(text_surface, (text_x, y_offset))
        y_offset += line_heights[i] + 5

        # Draw repeat indicator
        if self.current_subtitle.repeat_count > 0:
            repeat_text = f"Repeats left: {self.current_subtitle.repeat_count - self.current_subtitle.times_shown}"
        repeat_surface = self.font.render(repeat_text, True, (255, 200, 200))
        self.screen.blit(repeat_surface, (bg_x + 10, bg_y + 10))

    def _update_video_position(self):
        """Update the current video position based on playback state"""
        current_time = time.time()
        if self.playing:
            elapsed = current_time - self.last_frame_time
            self.video_position += elapsed * self.playback_speed
            if self.video_position > self.video_duration:
                self.video_position = 0
                self.playing = False
        self.last_frame_time = current_time

    def run(self):
        """Main application loop"""
        self.playing = True
        self.last_frame_time = time.time()

        running = True
        while running:
            # Handle events
            for event in pygame.event.get():
                if event.type == QUIT:
                    running = False
                elif event.type == KEYDOWN:
                    if event.key == K_SPACE:
                        self.playing = not self.playing
                    elif event.key == K_ESCAPE:
                        running = False
                    elif event.key == K_LEFT:
                        self.video_position = max(0, self.video_position - 5)
                    elif event.key == K_RIGHT:
                        self.video_position = min(self.video_duration, self.video_position + 5)
                    elif event.key == K_UP:
                        self.playback_speed = min(2.0, self.playback_speed + 0.1)
                    elif event.key == K_DOWN:
                        self.playback_speed = max(0.5, self.playback_speed - 0.1)
                elif event.type == VIDEORESIZE:
                    self.video_size = event.size
                    self.screen = pygame.display.set_mode(self.video_size, pygame.RESIZABLE)

            # Update video position
            self._update_video_position()

            # Handle subtitle display and repeating
            self._handle_subtitle_repeat()
            new_subtitle = self._get_current_subtitle(self.video_position)

            if new_subtitle and new_subtitle != self.current_subtitle:
                self.current_subtitle = new_subtitle
                self.current_subtitle.times_shown = 0
                if self.current_subtitle.repeat_count == 0:
                    self.current_subtitle.repeat_count = self.repeat_count

            # Update repeat counts
            if self.current_subtitle and self.video_position >= self.current_subtitle.end:
                self.current_subtitle.times_shown += 1
                if self.current_subtitle.times_shown >= self.current_subtitle.repeat_count:
                    self.current_subtitle = None
                else:
                    # Reset to start of subtitle for repeat
                    self.video_position = self.current_subtitle.start

            # Draw everything
            self.screen.fill((0, 0, 0))

            # Placeholder for video frame - in a real app this would be the actual video
            self.video_surface.fill((30, 30, 30))
            self.screen.blit(self.video_surface, (0, 0))

            # Draw subtitles
            self._draw_subtitles()

            # Draw UI elements
            status_text = f"Time: {self.video_position:.1f}s | Speed: {self.playback_speed:.1f}x | {'Playing' if self.playing else 'Paused'}"
            status_surface = self.font.render(status_text, True, (255, 255, 255))
            self.screen.blit(status_surface, (10, 10))

            pygame.display.flip()
            self.clock.tick(60)  # Cap at 60 FPS

        pygame.quit()
        sys.exit()


def main():
    parser = argparse.ArgumentParser(description="Subtitle Repeater for Movie Watching")
    parser.add_argument("video", help="Path to the video file")
    parser.add_argument("subtitles", help="Path to the subtitle file")
    parser.add_argument("-r", "--repeat", type=int, default=DEFAULT_REPEAT_COUNT,
                        help="Number of times to repeat each subtitle (default: 3)")

    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"Error: Video file not found: {args.video}")
        return

    if not os.path.exists(args.subtitles):
        print(f"Error: Subtitle file not found: {args.subtitles}")
        return

    app = SubtitleRepeater(args.video, args.subtitles, args.repeat)
    app.run()


if __name__ == "__main__":
    main()